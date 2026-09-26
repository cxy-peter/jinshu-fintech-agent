/** Interactive deploy from a clean runtime copy. The user's own Vercel login is required. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createInterface } from 'node:readline/promises';
import { fileURLToPath } from 'node:url';
import { prepareDeployment } from './prepare_deployment.mjs';
export const CLI_VERSION = '59.11.7';
export function targetFromChoice(choice) {
  if (choice === '' || choice === '1' || choice === 'preview') return 'preview';
  if (choice === '2' || choice === 'production') return 'production';
  if (choice === '0') return null;
  throw new Error('请选择 1 / 2 / 0；未进行部署。');
}
export function deployArguments(target, confirmation) {
  if (!['preview', 'production'].includes(target)) throw new Error('Unknown target');
  if (confirmation !== (target === 'production' ? 'DEPLOY PRODUCTION' : 'DEPLOY PREVIEW'))
    throw new Error('未收到正确确认；未进行部署。');
  return ['deploy', '--yes', '--logs', ...(target === 'production' ? ['--prod'] : [])];
}
async function main() {
  if (process.argv.includes('--help')) {
    console.log('node scripts/manual_deploy.mjs [preview|production]\n默认预览。正式发布需输入 DEPLOY PRODUCTION。需要 Node.js 22+、网络和你自己的 Vercel 登录。');
    return;
  }
  if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('请先安装 Node.js 22 或更高版本。');
  if (!process.stdin.isTTY) throw new Error('此入口需要交互终端；自动化请使用 GitHub 的 Manual Vercel Deploy 工作流。');
  const readline = createInterface({ input: process.stdin, output: process.stdout });
  const root = fileURLToPath(new URL('..', import.meta.url));
  let temporary;
  function vercel(args, cwd) {
    // Arguments are controlled here, never assembled from user shell input.
    const result = spawnSync(process.platform === 'win32' ? 'npx.cmd' : 'npx',
      ['--yes', `vercel@${CLI_VERSION}`, ...args],
      { cwd, stdio: 'inherit', shell: process.platform === 'win32', env: process.env });
    if (result.error) throw new Error('Vercel CLI 无法启动，请检查 Node/npm 和网络。');
    if (result.status !== 0) throw new Error('Vercel CLI 失败；上方原始错误为准，未确认发布成功。');
  }
  try {
    console.log('金枢｜单仓库手动发布\n1. Preview 预览版（默认，不替换正式域名）\n2. Production 正式版（会替换所选项目正式版本）\n0. 退出');
    const target = targetFromChoice(process.argv[2] || (await readline.question('选择 [1]：')).trim());
    if (!target) return;
    console.log('只上传完整运行代码和项目合成示例；不会上传根目录 .env、私人资料、模型文件或旧版网页。');
    console.log('环境变量取自你在 Vercel 中选择的项目。已有项目请选择 Link to existing，避免再建一个项目。');
    await readline.question('确认已在本机登录 Vercel（未登录可另开终端运行 npx vercel login）。按回车选择项目：');
    temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'jinshu-release-'));
    const staged = path.join(temporary, 'runtime');
    prepareDeployment(root, staged);
    const localLink = path.join(root, '.vercel', 'project.json');
    if (fs.existsSync(localLink)) {
      if (fs.lstatSync(path.dirname(localLink)).isSymbolicLink() || fs.lstatSync(localLink).isSymbolicLink())
        throw new Error('本地 .vercel/project.json 不可为符号链接。');
      const link = JSON.parse(fs.readFileSync(localLink, 'utf8'));
      fs.mkdirSync(path.join(staged, '.vercel'));
      fs.writeFileSync(path.join(staged, '.vercel', 'project.json'), JSON.stringify({
        orgId: link.orgId, projectId: link.projectId, projectName: link.projectName
      }));
    }
    // Interactive link lets the user deliberately select the authorized team/project.
    // No --yes here: never silently create or select a different project.
    readline.close();
    vercel(['link'], staged);
    const link = JSON.parse(fs.readFileSync(path.join(staged, '.vercel', 'project.json'), 'utf8'));
    if (!link.projectId || !link.orgId) throw new Error('没有有效项目关联；未部署。');
    console.log(`目标：${link.projectName || link.projectId}\n团队：${link.orgId}\n环境：${target}`);
    const confirm = createInterface({ input: process.stdin, output: process.stdout });
    let answer;
    try { answer = (await confirm.question(`输入 ${target === 'production' ? 'DEPLOY PRODUCTION' : 'DEPLOY PREVIEW'} 继续：`)).trim(); }
    finally { confirm.close(); }
    const args = deployArguments(target, answer);
    fs.mkdirSync(path.join(root, '.vercel'), { recursive: true });
    fs.writeFileSync(localLink, JSON.stringify({ orgId: link.orgId, projectId: link.projectId,
      projectName: link.projectName }, null, 2));
    vercel(args, staged);
    console.log('Vercel 命令已成功结束，部署链接见上方。还需核验 /api/status、账号及真实 DeepSeek 调用；页面能打开不等于业务服务已就绪。');
  } finally {
    readline.close();
    if (temporary) fs.rmSync(temporary, { recursive: true, force: true });
  }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
