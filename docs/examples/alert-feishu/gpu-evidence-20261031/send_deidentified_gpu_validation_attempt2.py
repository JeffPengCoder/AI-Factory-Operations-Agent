#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Send one reviewed report with user-specified credentials kept in memory."""
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,re,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CREDENTIALS=Path('/Users/operator/workspace/system-sa/aiops/mosaic-run/feishu.credentials')
SENDER=Path('/private/tmp/afoa-spark-alert-runbook-20261030/docs/examples/alert-feishu/send_feishu_report.py')
START=ROOT/'feishu-deidentified-send-attempt2-started.json'
previous=json.loads((ROOT/'feishu-response-attempt1.json').read_text());assert previous.get('code')==11232,'Only retry an explicitly rejected rate-limit response'
at=datetime.fromisoformat(json.loads((ROOT/'feishu-attempt1-feishu-send-result.json').read_text())['at']);assert (datetime.now(timezone.utc)-at).total_seconds()>=60,'Wait at least60seconds before this single retry'
assert not START.exists(), 'A send attempt exists. Inspect its result and the group before retrying.'
text=CREDENTIALS.read_text();values={}
try:
 value=json.loads(text)
 if isinstance(value,dict):values={str(k):str(v) for k,v in value.items()}
except ValueError:pass
if not values:
 for line in text.splitlines():
  line=line.strip()
  if not line or line.startswith('#'):continue
  if line.startswith('export '):line=line[7:].strip()
  match=re.match(r'^([A-Za-z_][A-Za-z0-9_ -]*)\s*[:=]\s*(.*?)\s*$',line)
  if match:
   key=match.group(1).strip();value=match.group(2).strip()
   if len(value)>=2 and value[0]==value[-1] and value[0] in {'"',"'"}:value=shlex.split(value)[0]
   values[key]=value
aliases={'FEISHU_WEBHOOK':['FEISHU_WEBHOOK','webhook','WEBHOOK','webhook_url','Webhook','Webhook URL','FEISHU_WEBHOOK_URL'],'FEISHU_SIGNING_SECRET':['FEISHU_SIGNING_SECRET','signing_secret','SIGNING_SECRET','secret','SECRET','sign','SIGN_SECRET','FEISHU_SECRET']}
found={}
for key,names in aliases.items():
 for name in names:
  if name in values:found[key]=values[name];break
assert found.get('FEISHU_WEBHOOK') and found.get('FEISHU_SIGNING_SECRET'), 'Required configured credentials are missing.'
CREDENTIALS.chmod(0o600)
for key,value in found.items():os.environ[key]=value
meta=json.loads((ROOT/'feishu-deidentified-report-metadata.json').read_text())
START.write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'group':'MOSAIC Alert Test','runId':meta['runId'],'payloadFileSha256':hashlib.sha256((ROOT/'feishu-payload-deidentified.json').read_bytes()).hexdigest(),'payloadEncodedSha256BeforeSigning':meta['payloadSha256'],'credentialValuesSaved':False},indent=2)+'\n')
spec=importlib.util.spec_from_file_location('mosaic_feishu_sender',SENDER);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
sys.argv=[str(SENDER),'--alert',str(ROOT/'deidentified-feishu-alert.json'),'--analysis',str(ROOT/'deidentified-feishu-validation-report.zh-CN.txt'),'--session-key',meta['researchSessionKey'],'--run-id',meta['runId'],'--evidence-url','https://github.com/JeffPengCoder/AI-Factory-Operations-Agent/pull/1','--output',str(ROOT/'feishu-payload-deidentified.json'),'--send','--response',str(ROOT/'feishu-response-attempt2.json')]
try:
 module.main()
 response=json.loads((ROOT/'feishu-response-attempt2.json').read_text());module.require_success(response)
 result={'at':datetime.now(timezone.utc).isoformat(),'group':'MOSAIC Alert Test','runId':meta['runId'],'botApiAccepted':True,'groupReceiptConfirmed':False,'completeResponseFile':'feishu-response-attempt2.json','credentialValuesSaved':False,'unattendedAcceptance':'NOT_PASSED','identityDeidentified':True,'semanticCorrectionsToQwenReport':False}
except Exception as exc:
 message=str(exc)
 for value in found.values():
  if value:message=message.replace(value,'[REDACTED_CREDENTIAL]')
 result={'at':datetime.now(timezone.utc).isoformat(),'group':'MOSAIC Alert Test','runId':meta['runId'],'botApiAccepted':False,'errorType':type(exc).__name__,'error':message,'groupReceiptConfirmed':False,'credentialValuesSaved':False}
(ROOT/'feishu-send-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
if not result['botApiAccepted']:raise SystemExit(1)
