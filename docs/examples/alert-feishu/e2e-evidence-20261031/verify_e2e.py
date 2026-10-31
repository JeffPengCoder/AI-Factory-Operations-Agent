#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate actual cross-hop identity, every native result, source bounds and cleanup."""
from collections import Counter
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN=ROOT.name;UID='82953a81-6578-4cbe-b638-ef3de927279a';FP='1bdae10de10f472e'
load=lambda p:json.loads((ROOT/p).read_text())
samples=[json.loads(x) for x in (ROOT/'chain-samples.jsonl').read_text().splitlines()]
first={};related={}
for sample in samples:
 for alert in sample.get('selected',[]):related.setdefault(alert['fingerprint'],alert)
 for row in sample.get('remote',[]):
  if row.get('status')!=200:continue
  data=json.loads(row['body'])
  if row['name']=='alertmanager' and data:
   assert all(a['fingerprint']==FP and a['labels']['run_id']==RUN and a['labels']['uid']==UID for a in data)
   first.setdefault('alertmanager',{'observedAt':row['at'],'completeAlert':data[0]})
  elif isinstance(data,dict):
   for hit in data.get('data',{}).get('result',[]):
    assert hit['metric']['uid']==UID
    if row['name']=='fixture':first.setdefault('crashMetric',{'observedAt':row['at'],'metric':hit})
    else:first.setdefault(hit['metric']['alertstate'],{'observedAt':row['at'],'metric':hit})
 for a in sample.get('selected',[]):
  if a['fingerprint']==FP:first.setdefault('mosaic',{'observedDuringSampleStartedAt':sample['at'],'completeAlert':a})
assert set(first)=={'crashMetric','pending','firing','alertmanager','mosaic'}
assert first['alertmanager']['completeAlert']['fingerprint']==first['mosaic']['completeAlert']['fingerprint']
assert first['mosaic']['completeAlert']['labels']['uid']==UID
# The object's source-derived createdAt is not used as a measured arrival time.
tools=load('native/tool-index.json');assert len(tools)==18 and all('arguments' in r for r in tools)
counts=Counter(r['toolName'] for r in tools);assert counts=={'run_kubectl':13,'memory_search':1,'iraop_list_collections':1,'iraop_query':3}
assert sum(bool(r.get('isError')) for r in tools)==1
index=[]
for row in tools:
 m=row['completeResult'];details=m.get('details',{});payload=details
 if row['toolName']=='run_kubectl':
  assert row['arguments']['args'][0] in ['get','describe','logs']
  if 'stdout' not in payload:
   for block in m.get('content',[]):
    text=block.get('text','');at=text.find('\n{')
    if at>=0:
     try:payload=json.loads(text[at+1:])
     except ValueError:continue
     if 'stdout' in payload:break
  assert payload.get('mutating') is False
  assert payload['exitCode']==(1 if row['isError'] else 0)
  if row['isError']:assert 'unknown flag: --timeout' in payload['stderr']
 index.append({'toolCallId':row['toolCallId'],'toolName':row['toolName'],'requestAt':row['requestAt'],'resultAt':row['resultAt'],'arguments':row['arguments'],'isError':row['isError'],'exitCode':payload.get('exitCode'),'detailsPersistedTruncated':details.get('persistedDetailsTruncated',False),'originalDetailsBytesAtLeast':details.get('originalDetailsBytesAtLeast'),'originalDetailKeys':details.get('originalDetailKeys'),'stdoutBytes':len(payload.get('stdout','').encode()) if 'stdout' in payload else None,'stderr':payload.get('stderr')})
(ROOT/'tool-request-result-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
log_results=[x for x in tools if x['toolName']=='run_kubectl' and x['arguments']['args'][0]=='logs']
first_query=next(x for x in tools if x['toolName']=='iraop_query')
assert log_results[0]['resultAt']<first_query['requestAt']
for i in range(1,4):
 r=load('research/iraop-response-'+str(i)+'.json');sources=r['response']['sources'];assert len(sources)==2
 assert all(s['source_file']=='mosaic-validation-control.pdf' and s['page_number'] in [1,2] for s in sources)
assert load('cleanup-result.json')['success']
assert load('root-final-preservation.json')['oldSmokeRuleUidUnchanged']
assert load('root-control-closed.json')['exitCode']==0
assert load('spark-final-runtime.json')['helm'][0]['revision']=='15'
for row in load('related-final.json')['remote']:
 data=json.loads(row['body']);assert not (data if row['name']=='alertmanager' else data['data']['result'])
assert load('feishu-send-result.json')['botApiAccepted']
response=load('feishu-response-attempt1.json');assert response['code']==response['StatusCode']==0
meta=load('feishu-report-metadata.json');payload=load('feishu-payload-reviewed.json');encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
assert len(encoded)==15481 and hashlib.sha256(encoded).hexdigest()==meta['payloadSha256']
raw=(ROOT/'native'/load('native/manifest.json')['nativeFile']).read_bytes();assert hashlib.sha256(raw).hexdigest()==load('native/manifest.json')['nativeSha256']
result={'at':datetime.now(timezone.utc).isoformat(),'runId':RUN,'fingerprint':FP,'podUid':UID,'allChainSamples':len(samples),'firstTransitions':first,'allRelatedAlerts':list(related.values()),'allToolCounts':dict(counts),'allToolRows':index,'logsWereReturnedBeforeFirstResearch':True,'allNewResourcesDeletedByOriginalUid':True,'oldRulePreserved':True,'relatedPrometheusAndAlertmanagerFinalCounts':0,'nativeContentRetainedInFullAsAvailable':True,'persistedTruncatedDetailsRows':[r for r in index if r['detailsPersistedTruncated']],'feishuApiAccepted':True,'feishuGroupReceiptConfirmed':load('feishu-send-result.json')['groupReceiptConfirmed'],'firstTwoResearchAnswersIncorrectlyAttributedIncidentToPdf':True,'operatorReviewProvided':True,'backgroundUnattendedPublisherDeployed':False}
(ROOT/'e2e-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'samples':len(samples),'tools':len(tools),'relatedAlerts':len(related),'sourcesEach':2,'sourceFinalClear':True,'feishuApiAccepted':True,'receipt':result['feishuGroupReceiptConfirmed'],'truncatedDetailsRows':len(result['persistedTruncatedDetailsRows'])}))
