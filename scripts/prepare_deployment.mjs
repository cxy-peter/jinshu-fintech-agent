/** Copy only the complete runtime, not the user's local documents or credentials. */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

export const ROOT_FILES = ['index.py', 'requirements.txt', 'pyproject.toml',
  'vercel.json', '.python-version', '.vercelignore', 'scripts/build_unified.py'];
export const ROOT_DIRS = ['unified', 'jinshu', 'engine/backend/app', 'data/synthetic'];
const TYPES = new Set(['.py', '.js', '.css', '.html', '.md', '.csv', '.json', '.txt', '.example']);
const SKIP_DIRS = new Set(['__pycache__', 'node_modules', 'private_corpus', 'private_reference',
  'workspace', 'models', 'uploads']);
export function included(relative) {
  const parts = relative.split(/[\\/]/);
  return !parts.some(x => x.startsWith('.') || SKIP_DIRS.has(x)) &&
    TYPES.has(path.extname(relative).toLowerCase()) && !/secret|credential/i.test(path.basename(relative));
}
export function prepareDeployment(source, destination) {
  source = fs.realpathSync(source);
  destination = path.resolve(destination);
  // Never recursively copy into the source or overwrite an existing directory.
  if (destination === source || destination.startsWith(source + path.sep))
    throw new Error('Deployment directory must be outside the source tree.');
  if (fs.existsSync(destination)) throw new Error('Deployment destination already exists.');
  const parent = fs.realpathSync(path.dirname(destination));
  if (parent === source || parent.startsWith(source + path.sep))
    throw new Error('Deployment parent resolves into the source tree.');
  fs.mkdirSync(destination);
  const hashes = {};
  function copy(relative, explicit = false) {
    // Reject symlinked components, including ancestors of explicitly allowed files.
    let at = source;
    for (const component of relative.split('/')) {
      at = path.join(at, component);
      if (fs.lstatSync(at).isSymbolicLink()) throw new Error('Runtime symlink rejected: ' + relative);
    }
    const input = path.join(source, relative), stat = fs.lstatSync(input);
    if (stat.isDirectory()) {
      for (const item of fs.readdirSync(input).sort()) {
        if (item.startsWith('.') || SKIP_DIRS.has(item)) continue;
        copy(relative + '/' + item);
      }
      return;
    }
    if (!stat.isFile() || (!explicit && !included(relative))) return;
    const content = fs.readFileSync(input), output = path.join(destination, relative);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, content);
    hashes[relative] = createHash('sha256').update(content).digest('hex');
  }
  try {
    for (const name of ROOT_FILES) copy(name, true);
    for (const name of ROOT_DIRS) copy(name);
    for (const name of ['jinshu/runtime.py', 'unified/app.py', 'unified/web/index.html',
      'unified/web/provider.js', 'engine/backend/app/main.py', 'data/synthetic/documents.json']) {
      if (!hashes[name]) throw new Error('Required full-runtime file missing: ' + name);
    }
    fs.writeFileSync(path.join(destination, 'release-manifest.json'), JSON.stringify({
      canonical_repository: 'cxy-peter/jinshu-fintech-agent',
      entrypoint: 'index:app', files: hashes,
      scope: 'source packaging only; no cloud deployment or inference verified'
    }, null, 2));
    return hashes;
  } catch (error) {
    fs.rmSync(destination, { recursive: true, force: true });
    throw error;
  }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const destination = process.argv[2];
  if (!destination) { console.error('Usage: node scripts/prepare_deployment.mjs <new-directory>'); process.exitCode = 1; }
  else {
    try {
      const source = fileURLToPath(new URL('..', import.meta.url));
      const files = prepareDeployment(source, destination);
      console.log(`Staged ${Object.keys(files).length} runtime files. No network calls made.`);
    } catch (error) { console.error(error.message); process.exitCode = 1; }
  }
}
