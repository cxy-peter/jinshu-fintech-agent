"""Private backup/import/verify. Run from repo root; never prints payload or URI."""
import argparse, asyncio, hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.store import Store, encoded

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def counts(value):
    return {k:len(v) for k,v in value.items() if isinstance(v,(list,dict))}
def envelope(value):
    return {"format":"jinshu-private-v1","sha256":fingerprint(value),"counts":counts(value),"value":value}
def validate(backup):
    value=backup["value"]
    if backup.get("format")!="jinshu-private-v1" or fingerprint(value)!=backup.get("sha256") or counts(value)!=backup.get("counts"):
        raise ValueError("Backup checksum/counts mismatch")
    if not isinstance(value.get("revision"),int) or value["revision"]<0:raise ValueError("Invalid revision")
    encoded(value)
    return value
async def main(args):
    if args.action=="export":
        if os.environ.get("JINSHU_STORE_READ_ONLY")!="1":raise ValueError("Freeze writes in production and set JINSHU_STORE_READ_ONLY=1 locally first")
        value=await Store().read();backup=envelope(value)
        args.file.parent.mkdir(parents=True,exist_ok=True)
        # O_EXCL prevents overwriting an earlier backup. chmod is best-effort on Windows.
        fd=os.open(args.file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(backup,f,ensure_ascii=False)
        print(json.dumps({k:backup[k] for k in ("sha256","counts")},ensure_ascii=False));return
    backup=json.loads(args.file.read_text(encoding="utf-8"));value=validate(backup)
    from pymongo import AsyncMongoClient
    database=os.environ.get("MONGODB_DB","jinshu")
    if database!="jinshu":raise ValueError("This migration only targets database jinshu")
    async with AsyncMongoClient(os.environ["MONGODB_URI"],serverSelectionTimeoutMS=8000) as client:
        col=client[database]["governed_state"]
        if args.action=="import":
            # Unique _id rejects any existing target, including simultaneous imports.
            await col.insert_one({"_id":"v1","revision":value["revision"],"value":value})
        row=await col.find_one({"_id":"v1"})
        if not row or fingerprint(row["value"])!=backup["sha256"] or counts(row["value"])!=backup["counts"]:raise ValueError("Target verification failed; do not switch storage")
        print(json.dumps({"verified":True,"database":database,"sha256":backup["sha256"],"counts":backup["counts"]},ensure_ascii=False))
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=["export","import","verify"]);parser.add_argument("file",type=Path)
    try:asyncio.run(main(parser.parse_args()))
    except Exception as exc:
        # Driver errors can contain connection endpoints; redact them from terminal output.
        print("Migration failed:",type(exc).__name__,"(source retained; no configuration changed)",file=sys.stderr);sys.exit(1)
