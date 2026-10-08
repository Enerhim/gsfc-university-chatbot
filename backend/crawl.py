"""Resumable public crawl. Never follows mailbox links automatically."""
import concurrent.futures, io, json, re, time, urllib.robotparser, subprocess
from urllib.parse import urljoin,urlsplit,urlunsplit,parse_qsl,urlencode
from collections import deque
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .store import CONFIG,DATA,db,ingest,record
UA='GSFCStudentResearchBot/1.0 (local university knowledge index)'
class CurlClient:
    def get(self,url):
        r=subprocess.run(['curl','-sS','--max-time','40','--max-filesize',str(CONFIG['max_file_mb']*1024*1024),'-w','\n%{http_code}\n%{content_type}\n%{redirect_url}',url],capture_output=True)
        if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[:200])
        body,code,typ,redirect=r.stdout.rsplit(b'\n',3)
        return httpx.Response(int(code),content=body,headers={'content-type':typ.decode(),'location':redirect.decode()},request=httpx.Request('GET',url))
client=CurlClient()
robots={}
def allowed(url):
    p=urlsplit(url); h=(p.hostname or '').lower()
    try: port=p.port
    except ValueError:return False
    return p.scheme in ('http','https') and not p.username and (port in (None,80,443)) and any(h==d or h.endswith('.'+d) for d in CONFIG['allowed_domains'])
def canonical(url):
    p=urlsplit(url)
    return urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_')]),''))
def permit(url):
    p=urlsplit(url);origin=f'{p.scheme}://{p.netloc}'
    if origin not in robots:
        rp=urllib.robotparser.RobotFileParser();rp.set_url(origin+'/robots.txt')
        try:
            r=client.get(rp.url)
            for _ in range(5):
                if not r.is_redirect:break
                target=urljoin(str(r.request.url),r.headers.get('location',''))
                if not allowed(target):break
                r=client.get(target)
            if r.status_code==200:rp.parse(r.text.splitlines())
            elif r.status_code in (404,410):rp.parse([])
            else:rp.parse(['User-agent: *','Disallow: /'])
        except Exception:rp.parse(['User-agent: *','Disallow: /'])
        robots[origin]=rp
    return robots[origin].can_fetch(UA,url)
def fetch(url):
    try:
        if not permit(url):record(url,'robots_denied');return []
        r=client.get(url)
        if r.is_redirect:
            target=canonical(urljoin(url,r.headers.get('location','')))
            record(url,'redirect',target);return [target] if allowed(target) else []
        r.raise_for_status()
        if len(r.content)>CONFIG['max_file_mb']*1024*1024:record(url,'oversize');return []
        typ=r.headers.get('content-type','');links=[];title=urlsplit(url).path;kind='web';meta={}
        if 'pdf' in typ or url.lower().endswith('.pdf'):
            pdf=PdfReader(io.BytesIO(r.content));pages=[p.extract_text() or '' for p in pdf.pages]
            text='\n\n'.join(f'[Page {i+1}]\n{p}' for i,p in enumerate(pages));kind='document'
            meta={'pages':len(pages),'empty_pages':[i+1 for i,p in enumerate(pages) if len(p.strip())<20]}
            if len(text.strip())<50:record(url,'needs_ocr');return []
        elif 'html' in typ:
            soup=BeautifulSoup(r.text,'html.parser')
            title=(soup.title.get_text(' ',strip=True) if soup.title else title)
            headings=soup.select('h1,h2'); meaningful=[h.get_text(' ',strip=True) for h in headings if h.get_text(strip=True)]
            if meaningful:title=' | '.join(meaningful[:3])[:250]
            for a in soup.select('a[href]'):
                u=canonical(urljoin(url,a['href']))
                if urlsplit(u).scheme not in ('https','http'):continue
                with db() as c:c.execute('INSERT OR IGNORE INTO links VALUES(?,?,?)',(u,url,urlsplit(u).hostname))
                if allowed(u) and not re.search(r'\.(jpg|jpeg|png|gif|svg|mp4|mp3|zip|css|js|woff2?)(?:\?|$)',u,re.I):links.append(u)
            for el in soup.select('script,style,noscript,nav,header,footer'):el.decompose()
            for el in soup.select('.sidebar-lft,.accessibility-container,.continrleft-menu'):el.decompose()
            main=soup.select_one('.contright') or soup.find('main')
            if main is None or len(main.get_text(strip=True))<30:main=soup.body or soup
            heading=soup.select_one('.innertitle')
            if heading:title=heading.get_text(' ',strip=True)
            text=main.get_text('\n',strip=True)
            # Remove recurrent announcement ticker preceding page-specific text where possible.
            meta={'linked_from':url,'last_modified':r.headers.get('last-modified','')}
        elif 'wordprocessingml' in typ or url.lower().endswith('.docx'):
            from docx import Document
            text='\n'.join(p.text for p in Document(io.BytesIO(r.content)).paragraphs);kind='document'
        elif 'text/plain' in typ:text=r.text
        else:record(url,'unsupported',typ);return []
        if len(text.strip())<30:
            record(url,'needs_browser_render');return links
        ingest(url,title,text,kind,metadata=meta)
        record(url,'ok',str(len(text)))
        return links
    except Exception as e:record(url,'failed',str(e));return []

def run(limit=None,refresh=False):
    limit=limit or CONFIG['max_pages']
    with db() as c:
        done=set() if refresh else {r[0] for r in c.execute("SELECT url FROM crawl WHERE (status='ok' AND url IN (SELECT url FROM documents)) OR status IN ('unsupported','needs_ocr')")}
        prior=[r[0] for r in c.execute('SELECT DISTINCT url FROM links') if allowed(r[0])]
    queue=deque(CONFIG['seeds']+prior);seen=set(done);count=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        while queue and count<limit:
            batch=[]
            while queue and len(batch)<4 and count+len(batch)<limit:
                u=queue.popleft()
                if u in seen or not allowed(u):continue
                seen.add(u);batch.append(u)
            if not batch:continue
            for links in pool.map(fetch,batch):queue.extend(links)
            count+=len(batch)
            if count%20==0:print(json.dumps({'processed':count,'queued':len(queue)}),flush=True)
            time.sleep(.5)
    with db() as c:
        domains=[dict(r) for r in c.execute('SELECT host,count(DISTINCT url) urls,min(source) discovered_from FROM links GROUP BY host ORDER BY urls DESC')]
    (DATA/'discovered-domains.json').write_text(json.dumps(domains,indent=2))
    print(json.dumps({'processed':count,'remaining_queue':len(queue),'domains':len(domains)}),flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int);p.add_argument('--refresh',action='store_true');a=p.parse_args();run(a.limit,a.refresh)
