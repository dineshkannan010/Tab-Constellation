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

function findPython() {
  const candidates = [
    process.env.PYTHON && { cmd: process.env.PYTHON, baseArgs: [] },
    isWin && { cmd: 'py', baseArgs: ['-3'] },
    { cmd: 'python3.14', baseArgs: [] },
    { cmd: 'python3.13', baseArgs: [] },
    { cmd: 'python3.12', baseArgs: [] },
    { cmd: 'python3.11', baseArgs: [] },
    { cmd: 'python3',    baseArgs: [] },
    { cmd: 'python',     baseArgs: [] },
  ].filter(Boolean);

  // shell: false avoids cmd.exe mangling parentheses/special chars in the -c script
  const verScript = 'import sys; v=sys.version_info; print(str(v.major)+chr(46)+str(v.minor))';

  for (const { cmd, baseArgs } of candidates) {
    const r = spawnSync(cmd, [...baseArgs, '-c', verScript],
      { encoding: 'utf8', shell: false });   // <-- key change
    if (r.status === 0) {
      const [maj, min] = r.stdout.trim().split('.').map(Number);
      if (maj === 3 && min >= 11) {
        console.log(`Using Python ${r.stdout.trim()} (${cmd} ${baseArgs.join(' ')})`);
        return { cmd, baseArgs };
      }
    }
  }
  console.error('No Python >= 3.11 found. Install one or set PYTHON=/path/to/python.');
  process.exit(1);
}


const envPath = join(apiDir, '.env');
if (!existsSync(envPath)) {
  writeFileSync(envPath, 'NEO4J_PASSWORD=constellation\n');
  console.log('created api/.env');
}

const { cmd: python, baseArgs: pyArgs } = findPython();

run(python, [...pyArgs, '-m', 'venv', 'venv'], apiDir);
run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip'], apiDir);
run(venvPython, ['-m', 'pip', 'install', '-r', 'requirements.txt',
  'sentence-transformers', 'neo4j', 'qdrant-client', 'transformers', 'torch', 'python-dotenv'], apiDir);

run(isWin ? 'npm.cmd' : 'npm', ['install'], webDir);

console.log('\n✓ Setup complete. Start everything with:  node scripts/dev.mjs');
console.log('  (First run downloads ~450MB of ML models on first ingest — one time only.)');
