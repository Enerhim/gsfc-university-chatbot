import httpx,numpy as np,json,time
from .store import CONFIG,db

def embedding(texts):
    r=httpx.post(CONFIG['ollama_url']+'/api/embed',json={'model':CONFIG['embedding_model'],'input':texts,'truncate':True,'keep_alive':'10m'},timeout=180)
    r.raise_for_status();return r.json()['embeddings']
def run():
    done=0
    while True:
        with db() as c:rows=c.execute('SELECT id,text FROM chunks WHERE embedding IS NULL OR embedding_model!=? LIMIT 24',(CONFIG['embedding_model'],)).fetchall()
        if not rows:break
        vecs=embedding(['search_document: '+r['text'] for r in rows])
        with db() as c:
            for row,vec in zip(rows,vecs):c.execute('UPDATE chunks SET embedding=?,embedding_model=? WHERE id=?',(np.array(vec,dtype=np.float32).tobytes(),CONFIG['embedding_model'],row['id']))
        done+=len(rows)
        if done%240==0:print(json.dumps({'embedded':done}),flush=True)
    print(json.dumps({'embedded':done,'complete':True}),flush=True)
if __name__=='__main__':run()
