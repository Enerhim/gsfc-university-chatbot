import json,threading
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field
from typing import Literal
from .store import ROOT,DATA,CONFIG,db,stats,retrieve
from .chat import answer
app=FastAPI(title='ORBIT • GSFC University',docs_url='/api/docs')
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
@app.middleware('http')
async def origin_guard(request:Request,call_next):
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD') and origin and origin not in ('http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:8001','http://localhost:8001','http://127.0.0.1:5173','http://localhost:5173'):return JSONResponse({'detail':'Origin not allowed'},status_code=403)
    r=await call_next(request);r.headers['X-Content-Type-Options']='nosniff';r.headers['Cache-Control']='no-store';return r
class HistoryMessage(BaseModel):
    role:Literal["user","assistant"]
    content:str=Field(max_length=5000)
class Query(BaseModel):
    question:str=Field(min_length=3,max_length=1500)
    scope:Literal['personal']='personal'
    model:str|None=Field(default=None,max_length=150)
    history:list[HistoryMessage]=Field(default_factory=list,max_length=20)
@app.get('/api/status')
def status():
    s=stats()
    try:
        r=httpx.get(CONFIG['ollama_url']+'/api/tags',timeout=3);r.raise_for_status();models=[m['name'] for m in r.json()['models']];s['model_ready']=CONFIG['chat_model'] in models
    except Exception:s['model_ready']=False
    s.update(model=CONFIG['chat_model'],local_only=True,mail_batches=len(list((DATA/'raw').glob('mail-[0-9]*.json'))))
    report=ROOT/'evaluation/report.json'
    if report.exists():s['evaluation']=json.loads(report.read_text()).get('summary',{})
    return s
capability_cache:dict[str,bool]={}
def _can_answer(m):
    key=m.get('digest') or m['name']
    if key not in capability_cache:
        try:
            info=httpx.post(CONFIG['ollama_url']+'/api/show',json={'model':m['name']},timeout=15);info.raise_for_status()
            capability_cache[key]='completion' in info.json().get('capabilities',[])
        except httpx.HTTPError:
            # Ollama can stall /api/show while it loads a model; fall back to the family name rather than hiding every model.
            return 'bert' not in m.get('details',{}).get('family','') and 'embed' not in m['name']
    return capability_cache[key]
@app.get('/api/models')
def local_models():
    try:r=httpx.get(CONFIG['ollama_url']+'/api/tags',timeout=10);r.raise_for_status()
    except httpx.HTTPError:raise HTTPException(503,'Ollama is unavailable')
    tags=r.json().get('models',[])
    with ThreadPoolExecutor(8) as pool:usable=list(pool.map(_can_answer,tags))
    try:loaded=[m['name'] for m in httpx.get(CONFIG['ollama_url']+'/api/ps',timeout=3).json().get('models',[])]
    except Exception:loaded=[]
    return {'models':[m['name'] for m,ok in zip(tags,usable) if ok],'default':CONFIG['chat_model'],'loaded':loaded}
class LoadRequest(BaseModel):
    model:str=Field(max_length=150)
@app.post('/api/models/load')
def load_model(q:LoadRequest):
    if q.model not in local_models()['models']:raise HTTPException(422,'Choose an installed answer model')
    # An empty generate request makes Ollama load the weights into memory and return once ready.
    try:r=httpx.post(CONFIG['ollama_url']+'/api/generate',json={'model':q.model,'keep_alive':'20m'},timeout=300);r.raise_for_status()
    except httpx.HTTPError:raise HTTPException(503,'Could not load the model into memory')
    return {'model':q.model,'loaded':True,'load_seconds':round(r.json().get('load_duration',0)/1e9,1)}
@app.post('/api/chat')
def chat(q:Query):
    selected=q.model or CONFIG['chat_model']
    if selected not in local_models()['models']:raise HTTPException(422,'Choose an installed answer model')
    return answer(q.question,'personal',history=[m.model_dump() for m in q.history],model=selected)
@app.get('/api/search')
def search(q:str,scope:Literal['personal']='personal'):return retrieve(q[:1500],scope,15)
@app.get('/api/sources')
def sources(q:str='',scope:Literal['personal']='personal',offset:int=0):
    with db() as c:
        where="WHERE (title LIKE ? OR url LIKE ?)"+(" AND visibility='public'" if scope=='public' else '')
        return [dict(r) for r in c.execute('SELECT id,url,title,kind,visibility,published,fetched,length(text) characters FROM documents '+where+' ORDER BY fetched DESC LIMIT 60 OFFSET ?',('%'+q+'%','%'+q+'%',max(offset,0)))]
@app.get('/api/source/{doc_id}')
def source(doc_id:str,scope:Literal['personal']='personal'):
    with db() as c:r=c.execute('SELECT * FROM documents WHERE id=?',(doc_id,)).fetchone()
    if not r or (scope=='public' and r['visibility']!='public'):raise HTTPException(404)
    return dict(r)
@app.get('/api/coverage')
def coverage():
    with db() as c:
        failures=[dict(r) for r in c.execute("SELECT * FROM crawl WHERE status NOT IN ('ok','redirect') LIMIT 200")]
        faculty=[dict(r) for r in c.execute("SELECT title,url FROM documents WHERE url LIKE '%FacultyProfile.aspx%'")]
        domains=[dict(r) for r in c.execute('SELECT host,count(DISTINCT url) urls,min(source) discovered_from FROM links GROUP BY host ORDER BY urls DESC')]
    manifest=DATA/'sync-manifest.json'
    return {'stats':stats(),'failures':failures,'faculty':faculty,'domains':domains,'sync':json.loads(manifest.read_text()) if manifest.exists() else {'mail':'Sync in progress','attachments':'Sync in progress'}}
@app.get('/api/evaluation')
def evaluation():
    p=ROOT/'evaluation/report.json';return json.loads(p.read_text()) if p.exists() else {'summary':{'status':'Not run'},'results':[]}
refresh_lock=threading.Lock();refresh_state={'running':False}
@app.post('/api/refresh')
def refresh():
    if not refresh_lock.acquire(False):return {'status':'already_running'}
    def work():
        refresh_state.update(running=True,error=None)
        try:
            from .crawl import run
            from .mail import import_exports
            from .embed import run as embed
            run(limit=CONFIG['max_pages'],refresh=True);import_exports();embed()
        except Exception as e:refresh_state['error']=str(e)
        finally:refresh_state['running']=False;refresh_lock.release()
    threading.Thread(target=work,daemon=True).start();return {'status':'started','note':'Refreshes public pages and saved exports. New Gmail requires a connector sync.'}
@app.get('/api/refresh')
def refresh_status():return refresh_state
DIST=ROOT/'frontend/dist'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/{path:path}')
    def ui(path:str):
        if path.startswith('api/'):raise HTTPException(404)
        return FileResponse(DIST/'index.html')
