import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { prepareDeployment, included, ROOT_FILES, ROOT_DIRS } from '../scripts/prepare_deployment.mjs';
import { targetFromChoice, deployArguments, CLI_VERSION } from '../scripts/manual_deploy.mjs';
const root = fileURLToPath(new URL('..', import.meta.url));
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'jinshu-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const source = path.join(dir, 'source'); fs.mkdirSync(source);
  for (const entry of [...ROOT_FILES, 'jinshu/runtime.py', 'unified/app.py', 'unified/web/index.html',
    'unified/web/provider.js', 'engine/backend/app/main.py', 'data/synthetic/documents.json']) {
    const file = path.join(source, entry); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, 'fixture');
  }
  return { dir, source, destination: path.join(dir, 'release') };
}
for (const value of ['', '1', 'preview']) test(`preview default ${JSON.stringify(value)}`, () => assert.equal(targetFromChoice(value), 'preview'));
for (const value of ['2', 'production']) test(`production is explicit ${value}`, () => assert.equal(targetFromChoice(value), 'production'));
test('cancel is no deployment', () => assert.equal(targetFromChoice('0'), null));
test('invalid choice does not become production', () => assert.throws(() => targetFromChoice('yes')));
test('preview is one-click and has no production flag', () => assert.deepEqual(deployArguments('preview'), ['deploy', '--yes', '--logs']));
test('production command requires exact phrase', () => {
  assert.throws(() => deployArguments('production', ''));
  assert.throws(() => deployArguments('production', 'DEPLOY PREVIEW'));
  assert.ok(deployArguments('production', 'DEPLOY PRODUCTION').includes('--prod'));
});
test('preview does not require confirmation', () => assert.deepEqual(deployArguments('preview', ''), ['deploy', '--yes', '--logs']));
test('unknown environment is rejected', () => assert.throws(() => deployArguments('prod', 'DEPLOY PRODUCTION')));
for (const value of ['unified/.env', 'unified/.env.production', 'unified/private_corpus/a.json',
  'jinshu/__pycache__/x.pyc', 'unified/key.pem', 'unified/private.key', 'unified/credentials.json',
  'unified/web/font.woff2', 'unified/upload.pdf']) test(`excluded: ${value}`, () => assert.equal(included(value), false));
test('full runtime source files retained', () => {
  for (const value of ['jinshu/runtime.py', 'unified/web/provider.js', 'data/synthetic/products.csv']) assert.equal(included(value), true);
});
test('staging excludes all unallowlisted local data', t => {
  const f = fixture(t);
  for (const name of ['.env', '.env.production', '.vercel/project.json', 'private_corpus/account.json',
    'models/weights.json', 'workspace/trace.json', 'lite/web/app.js', 'unified/.env', 'jinshu/.env']) {
    const file = path.join(f.source, name); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, 'secret-sentinel');
  }
  const hashes = prepareDeployment(f.source, f.destination);
  for (const name of Object.keys(hashes)) assert.notEqual(fs.readFileSync(path.join(f.destination, name), 'utf8'), 'secret-sentinel');
  assert.equal(fs.existsSync(path.join(f.destination, '.env')), false);
  assert.equal(fs.existsSync(path.join(f.destination, 'lite')), false);
  assert.ok(hashes['jinshu/runtime.py']); assert.ok(hashes['unified/web/provider.js']);
  const manifest = JSON.parse(fs.readFileSync(path.join(f.destination, 'release-manifest.json')));
  assert.equal(manifest.entrypoint, 'index:app');
  assert.match(hashes['jinshu/runtime.py'], /^[a-f0-9]{64}$/);
});
test('refuses existing destination without touching it', t => {
  const f = fixture(t); fs.mkdirSync(f.destination); fs.writeFileSync(path.join(f.destination, 'keep'), 'keep');
  assert.throws(() => prepareDeployment(f.source, f.destination));
  assert.equal(fs.readFileSync(path.join(f.destination, 'keep'), 'utf8'), 'keep');
});
test('refuses destination inside source', t => {
  const f = fixture(t); assert.throws(() => prepareDeployment(f.source, path.join(f.source, 'release')));
});
test('rejects runtime file symlinks', t => {
  const f = fixture(t); const file = path.join(f.source, 'jinshu/runtime.py');
  fs.unlinkSync(file); fs.symlinkSync(path.join(f.source, 'index.py'), file);
  assert.throws(() => prepareDeployment(f.source, f.destination), /symlink/);
  assert.equal(fs.existsSync(f.destination), false);
});
test('rejects symlinked runtime parent directories', t => {
  const f = fixture(t); fs.renameSync(path.join(f.source, 'engine'), path.join(f.dir, 'engine'));
  fs.symlinkSync(path.join(f.dir, 'engine'), path.join(f.source, 'engine'));
  assert.throws(() => prepareDeployment(f.source, f.destination), /symlink/);
});
test('rejects destination parent alias into source', t => {
  const f = fixture(t); const alias = path.join(f.dir, 'alias'); fs.symlinkSync(f.source, alias);
  assert.throws(() => prepareDeployment(f.source, path.join(alias, 'release')));
});
test('missing runtime fails rather than staging a browser-only page', t => {
  const f = fixture(t); fs.unlinkSync(path.join(f.source, 'jinshu/runtime.py'));
  assert.throws(() => prepareDeployment(f.source, f.destination), /Required full-runtime/);
});
test('real source packaging includes full engine', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'jinshu-real-test-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const hashes = prepareDeployment(root, path.join(dir, 'release'));
  assert.ok(Object.keys(hashes).length >= 150);
  assert.ok(hashes['engine/backend/app/main.py']); assert.ok(hashes['unified/config.py']);
  assert.ok(hashes['jinshu/model_config.py']);
});
test('manual workflow is dispatch-only and uses canonical main', () => {
  const s = fs.readFileSync(path.join(root, '.github/workflows/manual-vercel-deploy.yml'), 'utf8');
  assert.ok(s.includes('workflow_dispatch:')); assert.ok(!/\n  (push|pull_request):/.test(s));
  assert.ok(s.includes("refs/heads/main")); assert.ok(s.includes('persist-credentials: false'));
  assert.ok(s.includes('DEPLOY PRODUCTION')); assert.ok(s.includes('contents: read'));
  assert.ok(s.includes('vercel deploy --prebuilt')); assert.ok(s.includes(`vercel@${CLI_VERSION}`));
  assert.ok(!s.includes('upload-artifact')); assert.ok(s.includes('secrets.VERCEL_TOKEN'));
});
test('automatic Git deployments disabled and no overlong excludeFiles remains', () => {
  const config=JSON.parse(fs.readFileSync(path.join(root, 'vercel.json')));
  assert.equal(config.git.deploymentEnabled, false);
  assert.equal(config.functions['index.py'].excludeFiles, undefined);
});
test('Windows launcher delegates to the simple deploy script', () => {
  assert.ok(fs.readFileSync(path.join(root, 'deploy_vercel.bat'), 'utf8').includes('node scripts\\manual_deploy.mjs'));
  const source=fs.readFileSync(path.join(root, 'scripts/manual_deploy.mjs'), 'utf8');
  assert.ok(source.includes("shell: false"));
  assert.ok(!source.includes("shell: process.platform"));
});
test('POSIX launcher help makes no network request', () => {
  const result = spawnSync('bash', [path.join(root, 'deploy_vercel.sh'), '--help'], { encoding: 'utf8' });
  assert.equal(result.status, 0); assert.ok(result.stdout.includes('DEPLOY PRODUCTION'));
});
