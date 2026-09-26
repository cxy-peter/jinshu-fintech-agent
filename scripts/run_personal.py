"""Local-only workspace and page pack; no cloud credentials are required.

Put DEEPSEEK_API_KEY in the ignored root .env if model answers are needed.
Without a key, original-text search and deterministic business tools still work.
"""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pack', default=str(ROOT / 'private_corpus/recovered-personal-materials.json'))
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    if os.getenv('VERCEL'):
        parser.error('This launcher is for localhost only, not a cloud function.')
    pack = Path(args.pack).resolve()
    if not pack.is_file():
        parser.error('Personal pack not found. Build it with scripts/build_personal_pack.py first.')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    os.environ.update(JINSHU_STORE='sqlite', JINSHU_STORE_READ_ONLY='0',
                     JINSHU_DATA_DIR=str(ROOT / 'workspace/personal-v101'),
                     JINSHU_PERSONAL_PACK=str(pack), JINSHU_DEMO_ACCOUNTS='1')
    sys.path.insert(0, str(ROOT))
    import uvicorn
    print(f'Local Jinshu: http://127.0.0.1:{args.port}/ (originals remain local)')
    uvicorn.run('index:app', host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main()
