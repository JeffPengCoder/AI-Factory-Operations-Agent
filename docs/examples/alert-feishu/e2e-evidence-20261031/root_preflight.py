#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read-only administrator preflight; no kubeconfig or Secret values are exported."""
from datetime import datetime,timezone
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SSH=['ssh','-S','/private/tmp/mosaic-e2e-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import json,subprocess,shutil
rows=[]
for args in [['hostname'],['id'],['kubectl','config','current-context'],['kubectl','get','nodes','-o','wide'],['kubectl','get','prometheus','-n','monitoring','-o','json'],['kubectl','get','prometheusrule','-n','monitoring','mosaic-alert-smoke-test','-o','json'],['kubectl','get','pods','-n','monitoring','-o','custom-columns=NAME:.metadata.name,NODE:.spec.nodeName,PHASE:.status.phase,IMAGES:.spec.containers[*].image'],['kubectl','get','namespace','mosaic-e2e-20261031t075722z','-o','json'],['kubectl','get','prometheusrule','-n','monitoring','mosaic-e2e-20261031t075722z','-o','json'],['crictl','images','-o','json']]:
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=25)
  rows.append({'argv':args,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 except (OSError,subprocess.TimeoutExpired) as e:rows.append({'argv':args,'errorType':type(e).__name__,'message':str(e)})
print(json.dumps(rows))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=180)
(ROOT/'root-preflight.stderr').write_text(p.stderr)
assert p.returncode==0,p.stderr
rows=json.loads(p.stdout)
(ROOT/'root-preflight.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'commands':rows},ensure_ascii=False,indent=2)+'\n')
for row in rows:
 args=row['argv']
 if args[:3]==['kubectl','get','prometheus'] and row.get('exitCode')==0:
  d=json.loads(row['stdout']);print(json.dumps({'prometheus':[{'name':x['metadata']['name'],'ruleSelector':x['spec'].get('ruleSelector'),'ruleNamespaceSelector':x['spec'].get('ruleNamespaceSelector')} for x in d['items']]}))
 elif args[:2]==['crictl','images'] and row.get('exitCode')==0:
  d=json.loads(row['stdout']);print(json.dumps({'cachedSmallImages':[x.get('repoTags',[]) for x in d.get('images',[]) if any(y in ' '.join(x.get('repoTags',[])).lower() for y in ['busybox','prometheus','node-exporter'])]}))
 elif args[:3]==['kubectl','get','prometheusrule'] and 'mosaic-alert-smoke-test' in args:continue
 else:print(json.dumps({'argv':args,'exitCode':row.get('exitCode'),'stdout':row.get('stdout'),'errorType':row.get('errorType')}))
