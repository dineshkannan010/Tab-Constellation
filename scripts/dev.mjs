#!/usr/bin/env node
// Tab Constellation — start everything. Cross-platform (Windows/macOS/Linux).
// Brings up Qdrant + Neo4j (Docker), waits until they are healthy, then runs
// the 4 app processes (2 uvicorn, event_processor, vite) with one Ctrl+C
// stopping them all. Uses only Node built-ins — no new packages.
//
//   node scripts/dev.mjs

import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { existsSync, writeFileSync } from 'node:fs';

const isWin = process.platform === 'win32';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const apiDir = join(root, 'api');
const webDir = join(root, 'web');
const venvPython = join(apiDir, 'venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');

// --- 0. Preflight: Docker installed? venv present? ------------------------
function preflight() {
  const ver = spawnSync('docker', ['--version'], { encoding: 'utf8', shell: isWin });
  if (ver.error || ver.status !== 0) {
    console.error('Docker is not installed (or not on PATH).');
    console.error('Install Docker Desktop: https://www.docker.com/products/docker-desktop/');
    process.exit(1);
  }
  const info = spawnSync('docker', ['info'], { stdio: 'ignore', shell: isWin });
  if (info.status !== 0) {
    console.error('Docker is installed but the daemon is not running. Start Docker Desktop, then retry.');
    process.exit(1);
  }
  if (!existsSync(venvPython)) {
    console.error('Python venv not found. Run first:  node scripts/setup.mjs');
    process.exit(1);
  }
  const envPath = join(apiDir, '.env');
  if (!existsSync(envPath)) {
    writeFileSync(envPath, 'NEO4J_PASSWORD=constellation\n');
    console.log('created api/.env');
  }
}

// --- 1. Start the databases ----------------------------------------------
function composeUp() {
  console.log('Starting Qdrant + Neo4j (docker compose up -d)...');
  const r = spawnSync('docker', ['compose', 'up', '-d'], { cwd: root, stdio: 'inherit', shell: isWin });
  if (r.status !== 0) {
    console.error('docker compose up failed.');
    process.exit(1);
  }
}

// --- 2. Poll a health endpoint until it responds -------------------------
async function waitFor(name, url, timeoutMs = 120000) {
  const start = Date.now();
  process.stdout.write(`Waiting for ${name} (${url}) `);
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) { console.log('✓'); return; }
    } catch { /* not up yet */ }
    process.stdout.write('.');
    await new Promise((r) => setTimeout(r, 2000));
  }
  console.log('✗');
  throw new Error(`${name} did not become healthy within ${timeoutMs / 1000}s`);
}

// --- 3. Launch a long-running child with a colored log prefix ------------
const COLORS = { ingest: '\x1b[36m', search: '\x1b[35m', events: '\x1b[33m', web: '\x1b[32m' };
const children = [];

function start(label, cmd, args, cwd) {
  const child = spawn(cmd, args, {
    cwd,
    shell: isWin,
    detached: !isWin,           // own process group on Unix → clean group kill
    stdio: ['ignore', 'pipe', 'pipe'],
    env: process.env,
  });
  const prefix = `${COLORS[label] || ''}[${label}]\x1b[0m `;
  for (const stream of [child.stdout, child.stderr]) {
    let buf = '';
    stream.on('data', (d) => {
      buf += d.toString();
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        process.stdout.write(prefix + buf.slice(0, i) + '\n');
        buf = buf.slice(i + 1);
      }
    });
  }
  child.on('exit', (code) => {
    console.log(`${prefix}exited (code ${code})`);
    if (!shuttingDown) shutdown();   // one process dying tears the rest down
  });
  children.push(child);
}

// --- 4. Teardown: kill the whole tree, cross-platform --------------------
let shuttingDown = false;
function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log('\nStopping all app processes...');
  for (const c of children) {
    try {
      if (isWin) spawnSync('taskkill', ['/pid', String(c.pid), '/T', '/F']);
      else process.kill(-c.pid, 'SIGTERM');
    } catch { /* already gone */ }
  }
  console.log('(Databases are still running. Stop them with: docker compose down)');
  setTimeout(() => process.exit(0), 1000);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// --- main ----------------------------------------------------------------
(async () => {
  preflight();
  composeUp();
  await waitFor('Qdrant', 'http://localhost:6333/healthz');
  await waitFor('Neo4j', 'http://localhost:7474');

  console.log('\nLaunching app processes (Ctrl+C stops everything):');
  start('ingest', venvPython, ['-m', 'uvicorn', 'main:app', '--reload', '--port', '8000'], apiDir);
  start('search', venvPython, ['-m', 'uvicorn', 'qdrant_search_api:app', '--reload', '--port', '8001'], apiDir);
  start('events', venvPython, ['event_processor.py', '--watch', '--interval', '20'], apiDir);
  start('web', isWin ? 'npm.cmd' : 'npm', ['run', 'dev'], webDir);

  // Confirm the APIs are serving (mirrors the README "verify" step).
  try {
    await waitFor('Ingest API', 'http://localhost:8000/health');
    await waitFor('Search API', 'http://localhost:8001/health');
    console.log('\n✓ All services ready.');
    console.log('  App:        http://localhost:5173');
    console.log('  Next:       load the extension/ folder via chrome://extensions (Developer mode → Load unpacked)');
    console.log('  First run downloads ~450MB of ML models on first ingest — one time only.\n');
  } catch (e) {
    console.error(e.message);
  }
})();
