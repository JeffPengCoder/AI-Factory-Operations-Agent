#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Nonsecret shared runtime invariants and retained research corpus counts."""
import json,subprocess
from pathlib import Path
from gpu_access import SSH
ROOT=Path(__file__).resolve().parent
remote=r'''import json,subprocess,pathlib
from datetime import datetime,timezone
k=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic'];h=str(pathlib.Path.home()/'.local/bin/helm')
history=json.loads(subprocess.check_output([h,'--kube-context','kind-mosaic-poc','history','mosaic','-n','mosaic','-o','json']))
values=json.loads(subprocess.check_output([h,'--kube-context','kind-mosaic-poc','get','values','mosaic','-n','mosaic','-o','json']))
pods=json.loads(subprocess.check_output(k+['get','pods','-o','json']))
state=json.loads(subprocess.check_output(['docker','inspect','nemoclaw-vllm']))[0]['State']
safe={'at':datetime.now(timezone.utc).isoformat(),'deployedHelmRevision':max(x['revision'] for x in history if x['status']=='deployed'),'pods':[{'name':x['metadata']['name'],'uid':x['metadata']['uid'],'phase':x['status']['phase'],'images':[c['image'] for c in x['spec']['containers']],'containers':[{'name':c['name'],'restartCount':c['restartCount'],'ready':c['ready']} for c in x['status'].get('containerStatuses',[])]} for x in pods['items']],'moduleEnabledFlags':{key:cfg.get('enabled') for key,cfg in values.get('modules',{}).items() if isinstance(cfg,dict)},'sharedLlm':{key:state.get(key) for key in ['Pid','StartedAt','Running','Restarting','OOMKilled','ExitCode']}}
code="""import json,hashlib,pathlib
from app.opensearch_client.client import get_client
from app.opensearch_client.index_manager import get_collection_index
c=get_client();counts={}
for name in ['mosaic-validation-20261031','mosaic-gpu-validation-20261031']:counts[name]=c.count(index=get_collection_index(name),body={'query':{'match_all':{}}})
p=pathlib.Path('/cm/shared/iraop-corpus/mosaic-gpu-evidence-runbook.pdf')
print(json.dumps({'collections':counts,'gpuPdfBytes':p.stat().st_size,'gpuPdfSha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
"""
p=subprocess.run(k+['exec','-i','deploy/iraop','--','python3','-'],input=code,text=True,capture_output=True,timeout=60);assert p.returncode==0
safe['retainedCorpora']=json.loads(p.stdout)
print(json.dumps(safe))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=150)
(ROOT/'spark-final-runtime.private.stderr').write_text(p.stderr);assert p.returncode==0
d=json.loads(p.stdout);(ROOT/'spark-final-runtime.private.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'revision':d['deployedHelmRevision'],'pods':len(d['pods']),'sharedLlm':d['sharedLlm'],'collections':{k:v['count'] for k,v in d['retainedCorpora']['collections'].items()}}))
