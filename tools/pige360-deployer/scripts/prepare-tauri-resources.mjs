import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(__filename), '..');
const distDir = path.join(root, 'dist');
const targetDir = path.join(root, 'src-tauri', 'dist');

function removeDir(dir) {
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const dstPath = path.join(dst, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, dstPath);
    } else if (entry.isFile()) {
      fs.copyFileSync(srcPath, dstPath);
    }
  }
}

if (!fs.existsSync(path.join(distDir, 'index.html'))) {
  console.error('[tauri-resources] dist/index.html não encontrado. Execute npm run build:web antes.');
  process.exit(1);
}

removeDir(targetDir);
copyDir(distDir, targetDir);
console.log(`[tauri-resources] dist copiado para ${path.relative(root, targetDir)}`);
