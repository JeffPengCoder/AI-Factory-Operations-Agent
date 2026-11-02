#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read-only live GPU baseline; complete selected command outputs, no credentials."""
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent
SSH = ['ssh','-S','/private/tmp/mosaic-gpu-rca-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote = r'''import json,subprocess,shutil,re,time
from datetime import datetime,timezone
commands=[
 ['hostname'],['uname','-a'],['id'],['nvidia-smi','-L'],['nvidia-smi','-q','-x'],
 ['nvidia-smi','--query-gpu=index,uuid,pci.bus_id,name,driver_version,utilization.gpu,memory.used,memory.total','--format=csv'],
 ['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name,used_gpu_memory','--format=csv'],
 ['dcgmi','--version'],['nv-hostengine','--version'],['nv-hostengine','--help'],['dcgmi','test','--help'],
 ['kubectl','config','current-context'],['kubectl','get','nodes','-o','wide'],
 ['kubectl','get','pods','-A','-o','json'],
 ['kubectl','get','configmaps','-n','gpu-operator','-o','json'],
 ['kubectl','get','prometheus','-n','monitoring','-o','json'],
 ['crictl','images','-o','json'], ['ss','-ltnp'],
]
rows=[]
for argv in commands:
 start=time.monotonic()
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=30)
  rows.append({'at':datetime.now(timezone.utc).isoformat(),'argv':argv,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'elapsedSeconds':time.monotonic()-start})
 except (OSError,subprocess.TimeoutExpired) as e:
  rows.append({'at':datetime.now(timezone.utc).isoformat(),'argv':argv,'errorType':type(e).__name__,'elapsedSeconds':time.monotonic()-start})
p=subprocess.run(['journalctl','-k','-b','--no-pager','-o','short-iso'],capture_output=True,text=True,timeout=30)
selected=[line for line in p.stdout.splitlines() if re.search(r'NVRM|Xid|PCIe Bus Error|AER:|nvidia|ECC',line,re.I)]
rows.append({'at':datetime.now(timezone.utc).isoformat(),'argv':['journalctl','-k','-b','--no-pager','-o','short-iso'],'selectionRegex':'NVRM|Xid|PCIe Bus Error|AER:|nvidia|ECC (case insensitive)','selectedLines':selected,'selectedLineCount':len(selected),'exitCode':p.returncode,'stderr':p.stderr})
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'readonly':True,'commands':rows}))
'''
p = subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=400)
(ROOT/'gpu-baseline.private.stderr').write_text(p.stderr)
if p.returncode: raise SystemExit('Readonly collector SSH failed, exit '+str(p.returncode))
data=json.loads(p.stdout)
(ROOT/'gpu-baseline.private.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
for r in data['commands']:
 if r['argv'][0] in ['nvidia-smi','dcgmi','nv-hostengine'] and r['argv']!=['nvidia-smi','-q','-x']:
  print(json.dumps(r,ensure_ascii=False))
 elif r['argv'][:3]==['kubectl','get','pods'] and r.get('exitCode')==0:
  pods=json.loads(r['stdout'])['items'];print(json.dumps({'gpuPods':[{'name':p['metadata']['name'],'namespace':p['metadata']['namespace'],'node':p['spec'].get('nodeName'),'images':[c['image'] for c in p['spec']['containers']]} for p in pods if any(x in p['metadata']['name'].lower() for x in ['dcgm','gpu-operator'])]}))
 elif r['argv'][0]=='journalctl':print(json.dumps({'kernelSelectedLineCount':r['selectedLineCount'],'exitCode':r['exitCode']}))
