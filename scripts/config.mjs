import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export function ensureApiKey(root) {
  const envFile = join(root, '.env');
  if (!existsSync(envFile)) {
    writeFileSync(envFile, `API_KEY=${randomBytes(24).toString('hex')}\n`, { mode: 0o600 });
  }
  const match = readFileSync(envFile, 'utf8').match(/^API_KEY\s*=\s*([^\r\n#]+)\s*$/m);
  const key = match?.[1]?.trim().replace(/^['"]|['"]$/g, '');
  if (!key) throw new Error('O .env não contém uma API_KEY válida. Remova esse arquivo para gerar outra chave automaticamente.');
  return key;
}
