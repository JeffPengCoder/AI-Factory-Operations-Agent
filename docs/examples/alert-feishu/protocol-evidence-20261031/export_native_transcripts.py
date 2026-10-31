#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Export only named test sessions; preserve original JSONL lines exactly."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031/native-ui-transcripts'
ROOT.mkdir(mode=0o700,exist_ok=True)
IDS=['976cddf9-ca87-440c-a7fa-f329f9f654f0','81afed9a-ae3f-4f0c-a8ce-be0a3e66eb2a','a40ec4b9-5c63-4868-bb53-a854abfdf273']
K=[str(Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
code="""const fs=require('fs'),ids=JSON.parse(process.argv[1]);console.log(JSON.stringify(ids.map(id=>({name:id+'.jsonl',base64:fs.readFileSync('/home/node/.openclaw/agents/default/sessions/'+id+'.jsonl').toString('base64')}))));"""
files=json.loads(subprocess.check_output(K+['exec','deploy/openclaw','-c','gateway','--','node','-e',code,json.dumps(IDS)]))
manifest=[]
for f in files:
    raw=base64.b64decode(f['base64']);p=ROOT/f['name']
    if p.exists():assert p.read_bytes()==raw
    else:p.write_bytes(raw);p.chmod(0o600)
    lines=[]
    for line in raw.splitlines():
        obj=json.loads(line)
        if obj.get('type')=='message' and obj.get('message',{}).get('role')=='toolResult':lines.append(line)
    selected=bytes([10]).join(lines)+bytes([10])
    q=ROOT/(f['name']+'.tool-results.jsonl')
    if q.exists() and q.read_bytes()!=selected:
        backup=q.with_name(q.name+'.attempt1-bad-delimiter')
        assert not backup.exists();q.rename(backup)
    q.write_bytes(selected);q.chmod(0o600)
    for line in q.read_bytes().splitlines():json.loads(line)
    manifest.append({'path':p.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                     'toolResultsPath':q.name,'toolResults':len(lines),'toolResultsBytes':len(selected),
                     'toolResultsSha256':hashlib.sha256(selected).hexdigest()})
p=ROOT/'manifest.json'
if p.exists() and p.read_bytes().endswith(b'\\n'):
    p.rename(ROOT/'manifest.attempt1-bad-delimiter')
p.write_text(json.dumps(manifest,indent=2)+chr(10));p.chmod(0o600)
print(json.dumps(manifest))
