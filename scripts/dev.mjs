import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { ensureApiKey } from './config.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const data = join(root, '.local-data');
mkdirSync(data, { recursive: true });
const apiKey = ensureApiKey(root);
const python = process.env.PYTHON || (process.platform === 'win32' ? 'py' : 'python3');
const prefix = process.platform === 'win32' && !process.env.PYTHON ? ['-3'] : [];
const children = [];
const host = '127.0.0.1';
let stopping = false;

function portFree(port) {
  return new Promise((resolve) => {
    const server = createServer();
    server.once('error', () => resolve(false));
    server.listen(port, host, () => server.close(() => resolve(true)));
  });
}

const ports = [8100, 8101, 8102, 8103, 8104, 8105, 8106, 8200, 8301, 8302];
const used = [];
for (const port of ports) if (!(await portFree(port))) used.push(port);
if (used.length) {
  console.error(`Portas em uso: ${used.join(', ')}. Feche a execução anterior antes de iniciar.`);
  process.exit(1);
}

const common = {
  ...process.env,
  PYTHONPATH: root,
  DATA_DIR: data,
  HOST: host,
  API_KEY: apiKey,
  DEV_MODE: '1',
  BROKER_URL: 'http://127.0.0.1:8101',
  REQUESTS_URL: 'http://127.0.0.1:8102',
  FLEET_HOST: host,
};

function stop() {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill();
  setTimeout(() => process.exit(), 1500).unref();
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);

function launch(name, extra = {}) {
  const child = spawn(python, [...prefix, '-m', `services.${name}.app`], {
    cwd: root, env: { ...common, ...extra }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  children.push(child);
  for (const stream of [child.stdout, child.stderr]) {
    let pending = '';
    stream.on('data', (chunk) => {
      pending += chunk.toString();
      const lines = pending.split('\n');
      pending = lines.pop();
      for (const line of lines) if (line.trim()) console.log(`[${extra.INSTANCE || name}] ${line}`);
    });
  }
  child.on('error', (error) => { console.error(`${name}: ${error.message}`); stop(); });
  child.on('exit', (code) => {
    if (!stopping) { console.error(`${name} encerrou inesperadamente (${code}).`); stop(); }
  });
}

launch('broker');
launch('requests');
launch('fleet', { TCP_PORT: '8200' });
launch('notifications');
launch('dispatch', { INSTANCE: 'dispatch-a', PORT: '8104', P2P_PORT: '8301', PEER_PORT: '8302', PEER_HOST: host });
launch('dispatch', { INSTANCE: 'dispatch-b', PORT: '8105', P2P_PORT: '8302', PEER_PORT: '8301', PEER_HOST: host });
launch('gateway', { PORT: '8100' });

console.log('\nGestão de frotas pronta para iniciar.');
console.log('Abra http://localhost:8100 no navegador.');
console.log('Use Ctrl+C para encerrar. Os dados de teste ficam em .local-data/.\n');
