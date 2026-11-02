#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Scoped configuration and authoritative driver-log checks; read only."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SSH=['ssh','-S','/private/tmp/mosaic-gpu-rca-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import json,subprocess,re,glob,os,urllib.request,urllib.parse,urllib.error,time
from datetime import datetime,timezone
rows=[]
commands=[
 ['kubectl','get','configmaps','-n','nvidia-gpu-operator','-o','json'],
 ['kubectl','get','pod','nvidia-dcgm-exporter-qz8j6','-n','nvidia-gpu-operator','-o','json'],
 ['kubectl','logs','nvidia-dcgm-exporter-qz8j6','-n','nvidia-gpu-operator','--timestamps','--since=1h'],
 ['dcgmi','discovery','-l'],['dcgmi','dmon','--help'],
 ['find','/usr/share','-maxdepth','5','-name','dcgm_agent.py'],
 ['docker','image','ls','--format','{{json .}}'],
]
for argv in commands:
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=25)
  rows.append({'at':datetime.now(timezone.utc).isoformat(),'argv':argv,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 except (OSError,subprocess.TimeoutExpired) as e:rows.append({'argv':argv,'errorType':type(e).__name__})
p=subprocess.run(['dmesg','--time-format','iso'],capture_output=True,text=True,timeout=20)
lines=[s for s in p.stdout.splitlines() if re.search('NVRM|Xid|PCIe Bus Error|AER:|nvidia|ECC',s,re.I)]
rows.append({'argv':['dmesg','--time-format','iso'],'selectionRegex':'NVRM|Xid|PCIe Bus Error|AER:|nvidia|ECC (case insensitive)','exitCode':p.returncode,'selectedLines':lines,'stderr':p.stderr})
queries=['count by (__name__) ({__name__=~"DCGM_.*"})','up{job=~".*dcgm.*"}']
for q in queries:
 url='http://target-node-1.example.invalid:30090/api/v1/query?'+urllib.parse.urlencode({'query':q})
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=20) as r:status,body=r.status,r.read().decode()
  rows.append({'at':datetime.now(timezone.utc).isoformat(),'query':q,'httpStatus':status,'body':body,'proxyUsed':False})
 except urllib.error.HTTPError as e:rows.append({'query':q,'httpStatus':e.code,'body':e.read().decode(),'proxyUsed':False})
 except OSError as e:rows.append({'query':q,'errorType':type(e).__name__,'proxyUsed':False})
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'readonly':True,'commands':rows}))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=240)
(ROOT/'gpu-context-v2.private.stderr').write_text(p.stderr)
assert p.returncode==0,'SSH collector failed'
d=json.loads(p.stdout);(ROOT/'gpu-context-v2.private.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for x in d['commands']:
 if x.get('argv',[None])[0]=='kubectl' and x['argv'][1:3] in [['get','pod'],['get','configmaps']]:
  print(json.dumps({'argv':x['argv'],'exitCode':x.get('exitCode'),'outputStoredLocally':True}))
 else: print(json.dumps(x,ensure_ascii=False))
