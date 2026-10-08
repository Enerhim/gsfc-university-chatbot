import os,subprocess,tempfile
from pathlib import Path
from .store import DATA
RUNTIME=DATA/'ocr-runtime/usr'
def image_text(path):
    binary=RUNTIME/'bin/tesseract'
    env={**os.environ,'LD_LIBRARY_PATH':str(RUNTIME/'lib'),'TESSDATA_PREFIX':str(RUNTIME/'share/tessdata'),'OMP_THREAD_LIMIT':'2'}
    r=subprocess.run([str(binary),str(path),'stdout','-l','eng'],env=env,capture_output=True,text=True,timeout=120)
    if r.returncode:raise RuntimeError(r.stderr[:200])
    return r.stdout

def pdf_text(path):
    with tempfile.TemporaryDirectory(dir=DATA) as tmp:
        r=subprocess.run(['pdftoppm','-scale-to','1800','-png',str(path),tmp+'/page'],capture_output=True,timeout=300)
        if r.returncode:raise RuntimeError('PDF rasterization failed')
        return '\n\n'.join('[Scanned page '+str(i+1)+']\n'+image_text(p) for i,p in enumerate(sorted(Path(tmp).glob('*.png'))))

def recover():
    import json
    from .store import ingest
    p=DATA/'attachment-status.jsonl'
    rows=[json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
    latest={r['key']:r for r in rows}
    for key,r in latest.items():
        if r['status']!='needs_ocr_or_extraction':continue
        files=list((DATA/'attachments').glob(key+'.*'))
        if not files:continue
        path=files[0]
        try:
            if path.suffix.lower()=='.pdf':text=pdf_text(path)
            elif path.suffix.lower() in ('.png','.jpg','.jpeg','.tif','.tiff'):text=image_text(path)
            else:continue
            if len(text.strip())<40:continue
            ingest('https://mail.google.com/mail/u/0/#all/'+r['message_id']+'?attachment='+key,r['filename'],text,'attachment','private',metadata={'ocr':True,'local_file':str(path)})
            r.update(status='indexed_ocr',detail='Machine OCR; verify critical details against original')
            with p.open('a') as f:f.write(json.dumps(r)+'\n')
            print(r['filename'],flush=True)
        except Exception as e:print(str(e),flush=True)
if __name__=='__main__':recover()
