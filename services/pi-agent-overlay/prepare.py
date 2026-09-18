"""Copy upstream into a build workspace; never alter engine/ in the source repository."""
from pathlib import Path
import shutil,sys
root=Path(__file__).resolve().parents[2];target=Path(sys.argv[1]).resolve()
if target==(root/'engine/services/pi-agent').resolve():raise ValueError('Do not overwrite upstream')
shutil.copytree(root/'engine/services/pi-agent',target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('node_modules','dist'))
shutil.copy2(target/'src/agents.ts',target/'src/agents.upstream.ts')
shutil.copy2(Path(__file__).with_name('agents.ts'),target/'src/agents.ts')
p=target/'src/server.ts';s=p.read_text();old='runtime.runtime, body.agentType, body.systemPrompt, body.prompt, outputMode, allowedTools,'
assert old in s
s=s.replace(old,old+' timeoutMs,');p.write_text(s)
shutil.copy2(Path(__file__).with_name('contract.mjs'),target/'contract.mjs')
print(target)
