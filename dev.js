const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const isWin = process.platform === 'win32';
const rootDir = __dirname;
const backendDir = path.join(rootDir, 'backend');
const frontendDir = path.join(rootDir, 'frontend');

function findPython() {
  const candidates = [
    path.join(backendDir, '.venv', isWin ? 'Scripts/python.exe' : 'bin/python'),
    path.join(rootDir, '.venv', isWin ? 'Scripts/python.exe' : 'bin/python'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return isWin ? 'python' : 'python3';
}

const pythonExe = findPython();
const npmCmd = isWin ? 'npm.cmd' : 'npm';

console.log('\x1b[36m%s\x1b[0m', '================================================');
console.log('\x1b[36m%s\x1b[0m', '   BIRDS EYE — DRONE 3D RECONSTRUCTION SYSTEM   ');
console.log('\x1b[36m%s\x1b[0m', '================================================');
console.log(`Backend Python : ${pythonExe}`);
console.log(`Frontend CWD   : ${frontendDir}\n`);

// Prefix output helper
function attachLogger(child, prefix, color) {
  const format = (data) => {
    const lines = data.toString().split('\n');
    lines.forEach((line) => {
      if (line.trim().length > 0) {
        console.log(`${color}${prefix}\x1b[0m ${line}`);
      }
    });
  };
  child.stdout.on('data', format);
  child.stderr.on('data', format);
}

// Start Backend
const backend = spawn(pythonExe, ['run.py'], {
  cwd: backendDir,
  env: { ...process.env, PYTHONUNBUFFERED: '1' },
});
attachLogger(backend, '[BACKEND] ', '\x1b[34m');

// Start Frontend
const frontend = spawn(npmCmd, ['run', 'dev'], {
  cwd: frontendDir,
  shell: isWin,
});
attachLogger(frontend, '[FRONTEND]', '\x1b[32m');

// Handle exit
function cleanup() {
  console.log('\n\x1b[33m[SHUTDOWN] Terminating Birds Eye processes...\x1b[0m');
  try {
    if (isWin) {
      if (backend.pid) spawn('taskkill', ['/pid', backend.pid, '/f', '/t']);
      if (frontend.pid) spawn('taskkill', ['/pid', frontend.pid, '/f', '/t']);
    } else {
      backend.kill('SIGINT');
      frontend.kill('SIGINT');
    }
  } catch (err) {
    // ignore cleanup errors
  }
  process.exit();
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);

backend.on('close', (code) => {
  console.log(`\x1b[31m[BACKEND] exited with code ${code}\x1b[0m`);
});

frontend.on('close', (code) => {
  console.log(`\x1b[31m[FRONTEND] exited with code ${code}\x1b[0m`);
});

