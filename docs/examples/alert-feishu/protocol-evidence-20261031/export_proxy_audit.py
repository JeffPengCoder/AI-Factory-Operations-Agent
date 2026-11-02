#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Export full private proxy records before Pod replacement and verify provenance."""
from datetime import datetime, timezone
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031'
K=[str(Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
DEST=ROOT/'native-proxy-audit-revision14.private.json.gz'
assert not DEST.exists(), 'Do not overwrite an evidence snapshot.'
pods=json.loads(subprocess.check_output(K+['get','pods','-l','app=llm-openai-compat','-o','json']))['items']
pod=next(p for p in pods if not p['metadata'].get('deletionTimestamp') and all(c['ready'] for c in p['status'].get('containerStatuses',[])))
code='''const fs=require('fs'),crypto=require('crypto');const dir='/audit/records';console.log(JSON.stringify({files:fs.readdirSync(dir).sort().filter(x=>x.endsWith('.json')).map(path=>{const raw=fs.readFileSync(dir+'/'+path);return {path,bytes:raw.length,sha256:crypto.createHash('sha256').update(raw).digest('hex'),base64:raw.toString('base64')}})}));'''
raw=subprocess.check_output(K+['exec',pod['metadata']['name'],'--','node','-e',code],timeout=90)
DEST.write_bytes(gzip.compress(raw,mtime=0));DEST.chmod(0o600)
data=json.loads(raw);assert len(data['files'])>=4
records=[]
for f in data['files']:
    content=base64.b64decode(f['base64'])
    assert len(content)==f['bytes'] and hashlib.sha256(content).hexdigest()==f['sha256']
    r=json.loads(content)
    original_bytes=base64.b64decode(r['originalRequestBase64'])
    forwarded_bytes=base64.b64decode(r['forwardedRequestBase64'])
    original=json.loads(original_bytes);forwarded=json.loads(forwarded_bytes)
    messages=original['messages']
    questions=[m.get('content','') for m in messages if m.get('role')=='user']
    oracle='CEDAR-NEBULA-E720C8C9'
    last_question=json.dumps(questions[-1],ensure_ascii=False) if questions else ''
    tool_messages=[m for m in messages if m.get('role')=='tool']
    record={'file':f['path'],'bytes':f['bytes'],'sha256':f['sha256'],'requestId':r['id'],'at':r['at'],
            'normalizationPerformed':r.get('normalizationPerformed'),'toolCallId':r.get('toolCallId'),
            'upstreamStatus':r.get('upstreamStatus'),'upstreamResponseComplete':r.get('upstreamResponseComplete'),
            'originalRequestBytes':len(original_bytes),'originalRequestSha256':hashlib.sha256(original_bytes).hexdigest(),
            'forwardedRequestBytes':len(forwarded_bytes),'forwardedRequestSha256':hashlib.sha256(forwarded_bytes).hexdigest(),
            'requestFieldsChanged':[key for key in sorted(set(original)|set(forwarded)) if original.get(key)!=forwarded.get(key)],
            'messagesUnchanged':messages==forwarded['messages'],'lastUserQuestionContainsOracle':oracle in last_question,
            'messageRoles':[m['role'] for m in messages],'toolMessageCount':len(tool_messages),
            'oraclePresentInActualToolMessage':any(oracle in json.dumps(m,ensure_ascii=False) for m in tool_messages),
            'upstreamResponseBytes':len(base64.b64decode(r['upstreamResponseBase64'])),
            'returnedResponseBytes':len(base64.b64decode(r['returnedResponseBase64']))}
    assert record['messagesUnchanged'] and not record['lastUserQuestionContainsOracle']
    assert record['upstreamStatus']==200 and record['upstreamResponseComplete']
    records.append(record)
assert sum(r['normalizationPerformed'] is True for r in records)>=2
assert sum(r['oraclePresentInActualToolMessage'] for r in records)>=2
summary={'at':datetime.now(timezone.utc).isoformat(),'pod':pod['metadata']['name'],'podUid':pod['metadata']['uid'],
         'archive':str(DEST),'archiveBytes':DEST.stat().st_size,'archiveSha256':hashlib.sha256(DEST.read_bytes()).hexdigest(),
         'rawJsonBytes':len(raw),'records':records,'credentialsOrHeadersSaved':False,
         'scope':'Full original/forwarded model bodies and complete upstream/returned bytes remain private; no model question contained the oracle.'}
(ROOT/'native-proxy-provenance-revision14.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
