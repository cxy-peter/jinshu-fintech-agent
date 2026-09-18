"""Services-only bounded children; keep original headings and page/table provenance."""
import hashlib
from .ingestion import TableAwareChunker

class LiveChunker(TableAwareChunker):
    def __init__(self):super().__init__(min_chars=80,max_chars=330)
    def chunk(self,doc):
        parents=super().chunk(doc); out=[]
        for n,parent in enumerate(parents):
            text=parent['content']; meta=parent.get('metadata',{})
            if meta.get('has_table'):
                lines=text.splitlines(); header=lines[:2]; groups=[]; buffer=list(header)
                for row in lines[2:]:
                    if sum(map(len,buffer))+len(row)>360 and len(buffer)>2:
                        groups.append('\n'.join(buffer)); buffer=list(header)
                    buffer.append(row)
                if len(buffer)>2:groups.append('\n'.join(buffer))
                if not groups:groups=[text]
            else:
                groups=[]
                for start in range(0,len(text),285):
                    groups.append(text[start:start+330])
                    if start+330>=len(text):break
            for part in groups:
                out.append(parent|{'content':part,'content_hash':hashlib.sha256(part.encode()).hexdigest(),
                    'char_count':len(part),'metadata':meta|{'parent_id':f'section-{n}','services_bounded':True}})
        for n,c in enumerate(out):c['chunk_index']=n
        return out
