#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Export exact native JSONL and index every actual tool call/result without omissions."""
from datetime import datetime,timezone
import base64,hashlib,json,shlex,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from probe_access import SSH
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'native';OUT.mkdir(exist_ok=True)
s=json.loads((ROOT/'review-api/summary.json').read_text());sid=s['sessionId']
remote=r'''import base64,json,pathlib,subprocess,sys
sid=sys.argv[1]
k=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
code="const fs=require('fs');process.stdout.write(fs.readFileSync('/home/node/.openclaw/agents/default/sessions/'+process.argv[1]+'.jsonl').toString('base64'))"
raw=subprocess.check_output(k+['exec','deploy/openclaw','-c','gateway','--','node','-e',code,sid])
sys.stdout.buffer.write(raw)
'''
p=subprocess.run(SSH+['python3 -c '+shlex.quote(remote)+' '+shlex.quote(sid)],capture_output=True,timeout=60)
(ROOT/'native-export.stderr').write_bytes(p.stderr);assert p.returncode==0,p.stderr.decode()
raw=base64.b64decode(p.stdout);path=OUT/(sid+'.jsonl');assert not path.exists();path.write_bytes(raw)
records=[json.loads(line) for line in raw.splitlines() if line.strip()]
requests={};results=[];tool_lines=[]
for record in records:
 if record.get('type')!='message':continue
 m=record.get('message',{});at=record.get('timestamp') or m.get('timestamp')
 if m.get('role')=='assistant':
  for block in m.get('content',[]):
   if block.get('type')=='toolCall':requests[block['id']]={'requestAt':at,'toolName':block['name'],'arguments':block.get('arguments')}
 elif m.get('role')=='toolResult':
  call=m['toolCallId'];results.append({'toolCallId':call,**requests.get(call,{}),'resultAt':at,'toolName':m.get('toolName'),'isError':m.get('isError'),'completeResult':m})
for line in raw.splitlines():
 r=json.loads(line)
 if r.get('message',{}).get('role')=='toolResult':tool_lines.append(line)
tools=b'\n'.join(tool_lines)+b'\n';(OUT/'tool-results.jsonl').write_bytes(tools)
(OUT/'tool-index.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
manifest={'at':datetime.now(timezone.utc).isoformat(),'sessionId':sid,'sessionKey':s['sessionKey'],'nativeFile':path.name,'nativeBytes':len(raw),'nativeSha256':hashlib.sha256(raw).hexdigest(),'nativeRecords':len(records),'toolResults':len(results),'toolRequests':len(requests),'toolResultsSha256':hashlib.sha256(tools).hexdigest()}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for i,row in enumerate([r for r in results if r['toolName']=='iraop_query'],1):
 for block in row['completeResult'].get('content',[]):
  if block.get('type')!='text':continue
  try:d=json.loads(block.get('text',''))
  except ValueError:continue
  if isinstance(d,dict) and 'answer' in d:
   (ROOT/'research'/('iraop-response-'+str(i)+'.json')).write_text(json.dumps({'toolCallId':row['toolCallId'],'requestAt':row.get('requestAt'),'resultAt':row['resultAt'],'arguments':row.get('arguments'),'isError':row.get('isError'),'response':d},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(manifest),flush=True)
print(json.dumps({'toolSummary':[{'id':r['toolCallId'],'name':r['toolName'],'isError':r['isError'],'requestAt':r.get('requestAt'),'resultAt':r['resultAt']} for r in results]}),flush=True)
