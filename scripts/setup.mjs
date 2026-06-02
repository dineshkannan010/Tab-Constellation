#!/usr/bin/env node
// Tab Constellation — first-time setup. Cross-platform (Windows/macOS/Linux).
// Creates the Python venv, installs Python deps (incl. ML libs), and runs
// npm install for the frontend. Uses only Node built-ins — no new packages.
//
//   node scripts/setup.mjs
//
// Override the Python interpreter if needed:
//   PYTHON=python3.12 node scripts/setup.mjs

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { existsSync, writeFileSync } from 'node:fs';

const isWin = process.platform === 'win32';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const apiDir = join(root, 'api');
const webDir = join(root, 'web');
const venvPython = join(apiDir, 'venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');

function run(cmd, args, cwd) {
  console.log(`\n> ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, { cwd, stdio: 'inherit', shell: isWin });
  if (r.status !== 0) {
    console.error(`\nFailed: ${cmd} ${args.join(' ')}`);
    process.exit(r.status ?? 1);
  }
}

// 1. Find a Python >= 3.11.
function findPython() {
  const candidates = [process.env.PYTHON, 'python3.13', 'python3.12', 'python3.11', 'python3', 'python', 'py'].filter(Boolean);
  for (const cmd of candidates) {
    const r = spawnSync(cmd, ['-c', 'import sys;print("%d.%d" % sys.version_info[:2])'], { encoding: 'utf8', shell: isWin });
    if (r.status === 0) {
      const [maj, min] = r.stdout.trim().split('.').map(Number);
      if (maj === 3 && min >= 11) {
        console.log(`Using Python ${r.stdout.trim()} (${cmd})`);
        return cmd;
      }
    }
  }
  console.error('No Python >= 3.11 found. Install one or set PYTHON=/path/to/python.');
  process.exit(1);
}

// 2. Ensure api/.env exists (Neo4j password must match docker-compose.yml).
const envPath = join(apiDir, '.env');
if (!existsSync(envPath)) {
  writeFileSync(envPath, 'NEO4J_PASSWORD=constellation\n');
  console.log('created api/.env');
}

const python = findPython();

// 3. Create the venv + install Python deps (base + ML libs from the README).
run(python, ['-m', 'venv', 'venv'], apiDir);
run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip'], apiDir);
run(venvPython, ['-m', 'pip', 'install', '-r', 'requirements.txt',
  'sentence-transformers', 'neo4j', 'qdrant-client', 'transformers', 'torch', 'python-dotenv'], apiDir);

// 4. Install the frontend.
run(isWin ? 'npm.cmd' : 'npm', ['install'], webDir);

console.log('\n✓ Setup complete. Start everything with:  node scripts/dev.mjs');
console.log('  (First run downloads ~450MB of ML models on first ingest — one time only.)');
