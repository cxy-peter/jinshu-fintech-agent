"""Start the same Jinshu workbench with an explicitly enabled local folder.

python scripts/run_local_folder.py --root F:\\JinshuData
No files are uploaded automatically. Retrieval-only works without a model key.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='金枢本地资料工作台')
    parser.add_argument('--root', default=os.environ.get('JINSHU_LOCAL_FOLDER_ROOT') or
                        (r'F:\JinshuData' if os.name == 'nt' else str(Path.home() / 'JinshuData')))
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--scan', action='store_true', help='启动前扫描一次，平时可在资料中心手动扫描')
    args = parser.parse_args()
    if os.environ.get('VERCEL'):
        parser.error('本地文件夹服务不允许在Vercel运行。')
    if not 1 <= args.port <= 65535:
        parser.error('端口需为1至65535。')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.local_library import validate_root, _linked
    root = Path(args.root).expanduser()
    if not root.is_absolute():
        parser.error('--root 需要绝对路径。')
    # The explicitly selected folder may be created; no drive is recursively read.
    try:
        if any(p.exists() and _linked(p) for p in (root, *root.parents)):
            raise ValueError('资料目录的父路径不可包含符号链接或目录联接。')
        root.mkdir(parents=True, exist_ok=True)
        root = validate_root(str(root))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    os.environ['JINSHU_LOCAL_FOLDER_ENABLED'] = '1'
    os.environ['JINSHU_LOCAL_FOLDER_ROOT'] = str(root)
    os.environ.setdefault('JINSHU_DATA_DIR', str(Path.home() / '.jinshu' / 'local-workbench'))
    from core.app import create_app
    app = create_app()
    if not hasattr(app.state, 'local_library'):
        parser.error('当前工作台未接入本地资料模块，请更新完整代码。')
    app.state.local_library.configure(str(root))
    if args.scan:
        print(app.state.local_library.scan()['scan'])
    print(f'本地工作台：http://127.0.0.1:{args.port}/')
    print(f'资料目录：{root}。进入资料中心点击扫描；检索不会自动上传文件。')
    import uvicorn
    # Disable proxy headers so untrusted X-Forwarded-For cannot forge loopback.
    uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()
