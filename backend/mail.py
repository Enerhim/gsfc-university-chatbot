"""Import full MIME exports, attachment extractions and Takeout .mbox files locally."""
import base64,json,re,mailbox,email.utils,hashlib
from pathlib import Path
from bs4 import BeautifulSoup
from .store import DATA,ingest,db,now

def decode(data):
    try:return base64.urlsafe_b64decode((data or '')+'='*(-len(data or '')%4)).decode('utf-8',errors='replace')
    except Exception:return ''
def parts(p):
    yield p
    for child in (p.get('parts') or []):yield from parts(child)
def import_exports():
    count=0;pending=[]
    for file in sorted((DATA/'raw').glob('mail-[0-9]*.json')):
        for msg in json.loads(file.read_text()):
            p=msg.get('payload',{});headers={h['name'].lower():h['value'] for h in p.get('headers',[])}
            plain=[];html=[]
            for part in parts(p):
                mime=part.get('mime_type','');body=part.get('body') or {}
                if part.get('filename'):
                    pending.append({'message_id':msg['id'],'filename':part['filename'],'mime_type':mime,'attachment_id':body.get('attachment_id'),'subject':headers.get('subject','')})
                    continue
                content=body.get('content') or body.get('text') or decode(body.get('base64_url_content') or body.get('data',''))
                if mime=='text/plain':plain.append(content)
                elif mime=='text/html':html.append(BeautifulSoup(content,'html.parser').get_text('\n',strip=True))
            text='\n'.join(plain or html)
            if not text.strip():continue # Never index snippets as a full message.
            title=headers.get('subject','Untitled message')
            body='Subject: '+title+'\nFrom: '+headers.get('from','')+'\nDate: '+headers.get('date','')+'\n\n'+text
            published=''
            try:published=email.utils.parsedate_to_datetime(headers.get('date','')).isoformat()
            except Exception:pass
            ingest('https://mail.google.com/mail/u/0/#all/'+msg['id'],title,body,'mail','private',published,{'message_id':msg['id'],'thread_id':msg.get('thread_id'),'from':headers.get('from','')})
            count+=1
    (DATA/'attachment-inventory.json').write_text(json.dumps(pending,indent=2))
    for file in sorted((DATA/'raw').glob('attachment-*.json')):
        obj=json.loads(file.read_text());text=obj.get('text','')
        if text:ingest(obj['url'],obj['title'],text,'attachment','private',obj.get('published',''),obj.get('metadata',{}))
    print(json.dumps({'messages_processed':count,'attachment_parts':len(pending)}),flush=True)

def import_mbox(path):
    count=0
    for message in mailbox.mbox(path):
        body=[]
        for part in message.walk():
            if part.get_content_type()=='text/plain' and not part.get_filename():body.append((part.get_payload(decode=True) or b'').decode(part.get_content_charset() or 'utf8',errors='replace'))
        key=hashlib.sha256((message.get('Message-ID','')+str(count)).encode()).hexdigest()
        ingest('mbox:'+key,message.get('Subject','Untitled'),'\n'.join(body),'mail','private',metadata={'import_file':Path(path).name})
        count+=1
    print({'imported':count})
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--mbox');a=p.parse_args()
    import_mbox(a.mbox) if a.mbox else import_exports()
