#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Preserve every log file for this exact Pod UID and only its kubelet messages."""
from datetime import datetime,timezone
import base64,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SSH=['ssh','-S','/private/tmp/mosaic-e2e-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import base64,hashlib,json,pathlib,subprocess
from datetime import datetime,timezone
ns='mosaic-e2e-20261031t075722z';pod='mosaic-log-fixture';uid='82953a81-6578-4cbe-b638-ef3de927279a'
root=pathlib.Path('/var/log/pods')/(ns+'_'+pod+'_'+uid)/'fixture'
files=[]
for p in sorted(root.glob('*')):
 if p.is_file():
  raw=p.read_bytes();files.append({'name':p.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()})
args=['journalctl','-u','kubelet','--since','2026-10-31 08:21:30 UTC','--until','now','--no-pager','-o','json']
p=subprocess.run(args,capture_output=True,text=True,timeout=25)
lines=[]
for line in p.stdout.splitlines():
 if uid in line or ns in line:lines.append(line)
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'logDirectory':str(root),'files':files,'kubelet':{'argv':args,'selection':'only full original JSON lines mentioning exact Pod UID or test namespace','exitCode':p.returncode,'stderr':p.stderr,'lines':lines}}))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=60)
(ROOT/'all-attempt-logs.stderr').write_text(p.stderr);assert p.returncode==0,p.stderr
result=json.loads(p.stdout);(ROOT/'all-attempt-logs.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
out=ROOT/'container-attempt-logs';out.mkdir(exist_ok=True)
for row in result['files']:
 raw=base64.b64decode(row['base64']);assert hashlib.sha256(raw).hexdigest()==row['sha256'];(out/row['name']).write_bytes(raw)
(ROOT/'kubelet-selected.jsonl').write_text('\n'.join(result['kubelet']['lines'])+'\n')
print(json.dumps({'attemptFiles':len(result['files']),'allBytes':sum(x['bytes'] for x in result['files']),'kubeletLines':len(result['kubelet']['lines'])}))
