#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fetch named private diagnostics without credentials or printing payloads."""
import base64,hashlib,json,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HOST='spark-user@spark.example.invalid'
SSH=['ssh','-S','/private/tmp/mosaic-live-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST]
label=sys.argv[1]
assert label.replace('-','').isalnum()
CODE='''import base64,json,os,pathlib
r=pathlib.Path('/tmp/mosaic-research-trace-%s-20261031')
names=['metadata.json','direct-hybrid-search.json','agent-events.private.jsonl','agent-records.private.json','agent-state.private.json','trace-summary.json','trace-error.json']
if %r=='replay':
 r=pathlib.Path('/tmp/mosaic-research-replay-20261031')
 names=['first-request.private.json','capture-agent-state.private.json','capture-agent-summary.json','completed.json']
 for case in ['compat-default','compat-no-thinking','direct-default','direct-no-thinking']:
  names.extend([case+'-request.private.json',case+'-response.sse',case+'-result.json'])
if %r=='raw':
 r=pathlib.Path('/tmp/mosaic-research-raw-parser-20261031')
 names=['tokenize-request.private.json','tokenize-response.private.json','completion-request.private.json','completion-response.private.json','raw-summary.json']
files={};counts={}
for name in names:
 p=r/name
 if not p.is_file():continue
 content=p.read_bytes()
 for variable in ['IRAOP_API_KEY','NVIDIA_CHAT_API_KEY','EMBEDDING_API_KEY','NVIDIA_API_KEY']:
  value=os.environ.get(variable,'').encode()
  if len(value)>=8 and value in content:
   counts.setdefault(name,{})[variable]=content.count(value)
   content=content.replace(value,b'<REDACTED_CREDENTIAL>')
 files[name]=base64.b64encode(content).decode()
print(json.dumps({'files':files,'credentialRedactions':counts}))
''' % (label,label,label)
command='$HOME/.local/bin/kubectl --context kind-mosaic-poc -n mosaic exec deploy/iraop -- python -c '+shlex.quote(CODE)
data=json.loads(subprocess.check_output(SSH+[command],timeout=120))
dest=ROOT/label;dest.mkdir(exist_ok=True)
manifest=[]
for name,encoded in data['files'].items():
 raw=base64.b64decode(encoded);(dest/name).write_bytes(raw)
 manifest.append({'file':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
(dest/'manifest.private.json').write_text(json.dumps({'files':manifest,'credentialRedactions':data['credentialRedactions']},indent=2)+'\n')
print(json.dumps({'label':label,'files':len(manifest),'bytes':sum(f['bytes'] for f in manifest),'credentialRedactions':data['credentialRedactions']}))
