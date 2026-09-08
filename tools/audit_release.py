"""Audit the actual Git index before a local release commit; never prints secret values."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
def main():
    entries=[]
    for row in git('ls-files','--stage','-z').decode().split('\0'):
        if not row:continue
        meta,name=row.split('\t',1);mode,oid,stage=meta.split()
        assert stage=='0'
        entries.append((name,oid))
    if not entries:raise RuntimeError('No staged files to audit')
    proc=subprocess.Popen(['git','-C',str(ROOT),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    raw,_=proc.communicate(('\n'.join(oid for _,oid in entries)+'\n').encode())
    blobs={};pos=0
    for name,oid in entries:
        end=raw.index(b'\n',pos);size=int(raw[pos:end].split()[-1]);pos=end+1
        blobs[name]=raw[pos:pos+size];pos+=size+1
    assert proc.returncode==0
    rules={
      'credential_format':r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{32,}|xox[baprs]-[A-Za-z0-9-]{20,})',
      'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
      'credential_assignment':r"""(?i)(?:password|passwd|api_key|apikey|secret|access_token|auth_token)\s*[=:]\s*["']([^"'\r\n]{8,})["']"""
    }
    findings=[];private=[];sizes=[];names={n for n,_ in entries}
    for name,oid in entries:
        data=blobs[name];sizes.append((len(data),name))
        if any(x in Path(name).parts for x in ('.venv','.venv-demo','__pycache__','.git','.cache')):raise AssertionError('Environment/cache staged: '+name)
        if Path(name).name.startswith('.env') and Path(name).name!='.env.example':raise AssertionError('Environment file staged: '+name)
        if len(data)>25*1048576:raise AssertionError('File exceeds release 25 MiB budget: '+name)
        try:s=data.decode('utf-8-sig')
        except UnicodeDecodeError:continue
        for kind,rx in rules.items():
            for m in re.finditer(rx,s):findings.append({'path':name,'kind':kind,'line':s[:m.start()].count('\n')+1})
        if re.search(r'C:[/\\]+(?:Users|goodwill_ai)',s,re.I):private.append(name)
    allowed={'models/consumo_predio/v1/metadata.json','models/consumo_predio/v2/metadata.json','simulacao/energyplus/modelo/predio_sp.osm'}
    unexpected=set(private)-allowed
    manifest=json.loads((ROOT/'docs/release/frozen_manifest.json').read_text(encoding='utf-8'))
    index={n:blobs[n] for n,oid in entries if n in manifest}
    missing=set(manifest)-set(index)
    changed=[n for n,b in index.items() if hashlib.sha256(b).hexdigest()!=manifest[n]]
    readme=git('show',':README.md').decode('utf-8')
    links=[url for _,url in re.findall(r'!?\[([^\]]*)\]\(([^)]+)\)',readme) if not url.startswith(('https:','http:','#'))]
    missing_links=[u for u in links if u.split('#')[0] not in names]
    result={'index_files':len(entries),'index_bytes':sum(x[0] for x in sizes),'largest_file':{'path':max(sizes)[1],'bytes':max(sizes)[0]},'files_over_25_mib':0,'files_over_50_mib':0,'files_over_100_mib':0,'credential_findings':findings,'reviewed_provenance_paths':private,'unexpected_private_paths':sorted(unexpected),'frozen_files_checked':len(index),'missing_frozen':sorted(missing),'changed_frozen':changed,'missing_readme_links':missing_links,'readme_image_count':len(re.findall(r'!\[',readme)),'scope':'UTF-8 staged blobs: known credential patterns, credential assignments, private keys, personal paths; binary assets reviewed by type. A negative scan is not an absolute guarantee.'}
    out=ROOT/'outputs/publication_local/index_audit.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if findings or unexpected or missing or changed or missing_links:raise SystemExit(1)
if __name__=='__main__':main()
