#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Restart only the IRAOP Deployment Pod; prove retention without re-ingestion."""
from datetime import datetime,timezone
import base64,hashlib,json,pathlib,subprocess,time

ROOT=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-debug/iraop-restart'
ROOT.mkdir(parents=True,exist_ok=True)
K=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
def run(args):
    start=time.monotonic();p=subprocess.run(K+args,capture_output=True,text=True)
    return {'argv':K+args,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'elapsedSeconds':time.monotonic()-start}
def obj(args):
    r=run(args+['-o','json']);assert r['exitCode']==0,r;return json.loads(r['stdout'])

SNAPSHOT=r'''
import base64,hashlib,json,os,time,urllib.request
from app.opensearch_client.client import get_client
from app.opensearch_client.search import hybrid_search
records=[]
def get(path,binary=False):
 req=urllib.request.Request('http://127.0.0.1:8000'+path,headers={'Authorization':'Bearer '+os.environ['IRAOP_API_KEY']})
 start=time.monotonic()
 with urllib.request.urlopen(req,timeout=90) as r:status=r.status;content=r.read()
 data={'path':path,'httpStatus':status,'elapsedSeconds':time.monotonic()-start}
 if binary:data.update(bytes=len(content),sha256=hashlib.sha256(content).hexdigest(),bodyBase64=base64.b64encode(content).decode())
 else:data['body']=json.loads(content)
 records.append(data);return data
get('/api/v1/live');get('/api/v1/health')
get('/api/v1/collections')
get('/api/v1/collections/mosaic-validation-20261031/documents')
get('/api/v1/documents/mosaic-validation-control.pdf',binary=True)
hits=hybrid_search(get_client(),'MOSAIC-KB-20261031 Operator Decision Evidence page 2 verification code',['mosaic-validation-20261031'],3)
print(json.dumps({'requests':records,'hybridHits':hits}))
'''
def snapshot(label,pod):
    r=run(['exec',pod,'--','python','-c',SNAPSHOT]);(ROOT/(label+'-exec.json')).write_text(json.dumps(r,indent=2)+'\n')
    assert r['exitCode']==0,r
    data=json.loads(r['stdout']);(ROOT/(label+'-data.json')).write_text(json.dumps(data,indent=2)+'\n')
    records={x['path']:x for x in data['requests']}
    docs=records['/api/v1/collections/mosaic-validation-20261031/documents']['body']
    selected=[x for x in docs if x['filename']=='mosaic-validation-control.pdf']
    assert len(selected)==1 and selected[0]['chunk_count']==4,docs
    pdf=records['/api/v1/documents/mosaic-validation-control.pdf'];assert pdf['bytes']==3781
    assert pdf['sha256']=='e65f46b9daa87b4420336d989b0951ac6d2d6fd0a479bdcaeda42862cd92e820'
    assert any(x['source_file']=='mosaic-validation-control.pdf' and x['page_number']==2 and 'CEDAR-NEBULA-E720C8C9' in x['content'] for x in data['hybridHits'])
    return data

def main():
    deploy=obj(['get','deployment/iraop'])
    assert deploy['spec']['replicas']==1 and deploy['status']['readyReplicas']==1
    labels=','.join(k+'='+v for k,v in deploy['spec']['selector']['matchLabels'].items())
    before=obj(['get','pods','-l',labels]);pods=before['items'];assert len(pods)==1
    old=pods[0];name=old['metadata']['name'];uid=old['metadata']['uid']
    assert old['status']['containerStatuses'][0]['ready']
    (ROOT/'deployment-before.json').write_text(json.dumps(deploy,indent=2)+'\n')
    (ROOT/'pods-before.json').write_text(json.dumps(before,indent=2)+'\n')
    snapshot('before',name)
    logs=run(['logs',name,'--timestamps=true'])
    (ROOT/'before-pod.log').write_text(logs['stdout'])
    assert logs['exitCode']==0,logs
    assert obj(['get','pod',name])['metadata']['uid']==uid
    deletion=run(['delete','pod',name,'--wait=true','--timeout=90s'])
    (ROOT/'delete-result.json').write_text(json.dumps(deletion,indent=2)+'\n');assert deletion['exitCode']==0,deletion
    rollout=run(['rollout','status','deployment/iraop','--timeout=180s'])
    (ROOT/'rollout-result.json').write_text(json.dumps(rollout,indent=2)+'\n');assert rollout['exitCode']==0,rollout
    after=obj(['get','pods','-l',labels]);(ROOT/'pods-after.json').write_text(json.dumps(after,indent=2)+'\n')
    new=[p for p in after['items'] if not p['metadata'].get('deletionTimestamp')];assert len(new)==1
    new=new[0];assert new['metadata']['uid']!=uid
    assert new['status']['containerStatuses'][0]['imageID']==old['status']['containerStatuses'][0]['imageID']
    assert new['status']['containerStatuses'][0]['ready']
    snapshot('after',new['metadata']['name'])
    summary={'at':datetime.now(timezone.utc).isoformat(),'oldPod':name,'oldUid':uid,'newPod':new['metadata']['name'],'newUid':new['metadata']['uid'],'sameImageID':True,'pdfBytes':3781,'pdfSha256':'e65f46b9daa87b4420336d989b0951ac6d2d6fd0a479bdcaeda42862cd92e820','documentCount':1,'chunks':4,'page2OracleRetrieved':True,'noReingestion':True,'scope':'Only IRAOP stateless Pod; OpenSearch Pod/PVC, host corpus and model service untouched.'}
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
