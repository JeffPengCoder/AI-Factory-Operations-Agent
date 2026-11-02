#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Persist one authored PDF, ingest into a fresh collection, retain all chunk vectors."""
import base64,hashlib,json,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'live-validation-20261031'))
from probe_access import SSH
pdf=ROOT/'mosaic-gpu-evidence-runbook.pdf'
assert not (ROOT/'gpu-ingestion.private.json').exists()
remote=r'''import base64,json,pathlib,subprocess,hashlib,sys
payload=json.load(sys.stdin);filename='mosaic-gpu-evidence-runbook.pdf'
data=base64.b64decode(payload['pdfBase64']);assert hashlib.sha256(data).hexdigest()==payload['sha256']
directory=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/gpu-rca-20261031t121240z';directory.mkdir(parents=True,exist_ok=True)
path=directory/filename;assert not path.exists(),'Refuse to overwrite existing PDF';path.write_bytes(data)
node='mosaic-poc-control-plane';target='/var/local/mosaic-validation-20261031/corpus/'+filename
subprocess.run(['docker','exec',node,'test','!','-e',target],check=True)
subprocess.run(['docker','cp',str(path),node+':'+target],check=True,stdout=subprocess.DEVNULL)
code=r"""import json,os,httpx,hashlib
from datetime import datetime,timezone
from app.opensearch_client.client import get_client
from app.opensearch_client.index_manager import get_collection_index
collection='mosaic-gpu-validation-20261031';filename='mosaic-gpu-evidence-runbook.pdf'
client=get_client();index=get_collection_index(collection);assert not client.indices.exists(index=index),'Collection already exists'
rows=[]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=180) as http:
 headers={'Authorization':'Bearer '+os.environ['IRAOP_API_KEY']}
 body={'file_path':'/cm/shared/iraop-corpus/'+filename,'collection':collection}
 r=http.post('/api/v1/ingest/file',headers=headers,json=body)
 rows.append({'at':datetime.now(timezone.utc).isoformat(),'method':'POST','path':'/api/v1/ingest/file','request':body,'status':r.status_code,'body':r.text});r.raise_for_status()
 for path in ['/api/v1/collections','/api/v1/collections/'+collection+'/documents']:
  r=http.get(path,headers=headers);rows.append({'method':'GET','path':path,'status':r.status_code,'body':r.text});r.raise_for_status()
 r=http.get('/api/v1/documents/'+filename,headers=headers);r.raise_for_status();rows.append({'method':'GET','path':'/api/v1/documents/'+filename,'status':r.status_code,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()})
client.indices.refresh(index=index)
count=client.count(index=index,body={'query':{'match_all':{}}})['count'];assert count<=1000
records=client.search(index=index,body={'size':1000,'query':{'match_all':{}},'sort':[{'chunk_index':'asc'}]})
assert len(records['hits']['hits'])==count
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'collection':collection,'index':index,'collectionAbsentBefore':True,'requests':rows,'count':count,'mapping':client.indices.get_mapping(index=index),'completeIndexedRecordsWithVectors':records},ensure_ascii=False))
"""
k=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
p=subprocess.run(k+['exec','-i','deploy/iraop','--','python3','-'],input=code,text=True,capture_output=True,timeout=400)
sys.stderr.write(p.stderr);sys.stdout.write(p.stdout);raise SystemExit(p.returncode)
'''
payload={'pdfBase64':base64.b64encode(pdf.read_bytes()).decode(),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
p=subprocess.run(SSH+['python3 -c '+shlex.quote(remote)],input=json.dumps(payload),text=True,capture_output=True,timeout=480)
(ROOT/'gpu-ingestion.private.stderr').write_text(p.stderr)
assert p.returncode==0,'Ingestion failed; inspect private stderr'
d=json.loads(p.stdout);(ROOT/'gpu-ingestion.private.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
hits=d['completeIndexedRecordsWithVectors']['hits']['hits']
summary={'collection':d['collection'],'chunks':d['count'],'chunkRows':[{'id':h['_id'],'page':h['_source']['page_number'],'chunk_index':h['_source']['chunk_index'],'characters':len(h['_source']['content']),'dimensions':len(h['_source'].get('embedding',[]))} for h in hits],'download':d['requests'][-1]}
(ROOT/'gpu-ingestion-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
