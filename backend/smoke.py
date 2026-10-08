"""Small live conversation checks, not a bulk benchmark."""
import json,argparse
from .chat import answer,llm,SYSTEM,AUDITOR,context,parse,validate_claims,expand
from .store import ROOT,retrieve
from .embed import embedding

def run(debug=False):
    if debug:
        q='Who should I approach for funding for my startup?';rows=retrieve(expand(q),'public',5,embedding(['search_query: '+q])[0])
        m=llm([{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps({'conversation':[],'latest_message':q,'standalone_question':q,'retrieved_evidence':context(rows)})}],tools=True)
        print('DRAFT',m,flush=True)
        obj=parse(m['content']);claims=validate_claims(obj,rows);ids={i for c in claims for i in c['source_ids']}
        print('AUDIT',llm([{'role':'system','content':AUDITOR},{'role':'user','content':json.dumps({'question':q,'claims':claims,'evidence':context([r for r in rows if r['id'] in ids])})}],budget=100),flush=True)
        return
    history=[];results=[]
    cases=[('Who should I approach for funding for my startup?','public'),('How do I contact them?','public'),('Which faculty works on machine learning?','public'),('What is their research background?','public'),('When exactly was Ananta 2026 held?','personal'),('What is the confirmed Ananta 2050 ticket price?','public')]
    for q,scope in cases:
        if scope=='personal' or '2050' in q:history=[]
        r=answer(q,scope,history=history);results.append(r)
        print(json.dumps({k:r.get(k) for k in ['question','resolved_question','status','answer','elapsed_seconds','error']}),flush=True)
        history.extend([{'role':'user','content':q},{'role':'assistant','content':r['answer']}])
        (ROOT/'evaluation/conversation-check.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--debug',action='store_true');run(p.parse_args().debug)
