import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { ensureApiKey } from './config.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
ensureApiKey(root);
const result = spawnSync('docker', ['compose', 'up', '--build', '-d'], { cwd: root, stdio: 'inherit' });
if (result.error) {
  console.error('Docker Compose não está disponível. Use npm run dev para testar sem Docker.');
  process.exit(1);
}
process.exit(result.status ?? 1);
