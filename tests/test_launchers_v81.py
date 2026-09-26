"""Launch command contracts; no real installation, credentials or paid services."""
import os
import pytest


@pytest.mark.parametrize('launcher', ['start_local.sh', 'start_local.bat'])
def test_default_launchers_use_same_full_entrypoint(launcher):
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    text=(root/launcher).read_text()
    assert '-m uvicorn index:app' in text
    assert '--env-file .env' in text
    assert '-m jinshu serve' not in text
    assert '--host 127.0.0.1' in text

@pytest.mark.parametrize('env_file', [False, True])
def test_posix_launcher_arguments_without_installing_or_network(tmp_path, env_file):
    import shutil,subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    shutil.copy(root/'start_local.sh', tmp_path/'start_local.sh')
    fake=tmp_path/'.venv/bin/python';fake.parent.mkdir(parents=True)
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$LAUNCH_CAPTURE"\n')
    fake.chmod(0o755)
    if env_file: (tmp_path/'.env').write_text('DEEPSEEK_MODEL=deepseek-flash\n')
    capture=tmp_path/'args.txt'
    subprocess.run(['bash',str(tmp_path/'start_local.sh')],check=True,
                   env={**os.environ,'LAUNCH_CAPTURE':str(capture)},capture_output=True,text=True)
    calls=capture.read_text().splitlines()
    assert calls[-1].startswith('-m uvicorn index:app --host 127.0.0.1 --port 8766')
    assert ('--env-file .env' in calls[-1]) == env_file
    assert all('jinshu serve' not in call for call in calls)
