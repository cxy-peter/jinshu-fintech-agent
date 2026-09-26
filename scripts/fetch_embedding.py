"""Fetch pinned public model artifacts. SHA256 checked before activation.
Weights are not committed to Git or stored as private Vercel Blob objects.
"""
import hashlib
import os
from pathlib import Path
from urllib.request import urlopen

REVISION='75c43b069aac4d136ba6bc1122f995fedcfd2781'
FILES={'onnx/model_quantized.onnx':'15b717c382bcb518ba457b93ea6850ede7f4f1cd8937454aa06972366cd19bcc',
       'tokenizer.json':'48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26'}

def fetch():
    target=Path(__file__).resolve().parents[1]/'core/models/bge-small-zh'
    target.mkdir(parents=True,exist_ok=True)
    for name,expected in FILES.items():
        path=target/Path(name).name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:continue
        with urlopen(f'https://huggingface.co/Xenova/bge-small-zh-v1.5/resolve/{REVISION}/{name}',timeout=90) as response:
            data=response.read(26_000_000)
        if hashlib.sha256(data).hexdigest()!=expected:raise RuntimeError('Embedding artifact hash mismatch: '+name)
        temp=path.with_suffix(path.suffix+'.pending');temp.write_bytes(data);os.replace(temp,path)
    print('Pinned CPU BGE model ready; weights verified, no paid API called.')

if __name__=='__main__':fetch()
