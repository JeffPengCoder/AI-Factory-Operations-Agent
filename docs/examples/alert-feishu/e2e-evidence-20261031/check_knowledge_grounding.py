#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Check the full actual indexed text against incident-specific source claims."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=ROOT.parent/'continued-validation-20261031T071049Z/vector-storage-proof.json'
d=json.loads(source.read_text());search=d['completeSearchResultWithAllVectors']
if 'body' in search:search=json.loads(search['body']) if isinstance(search['body'],str) else search['body']
chunks=[{'id':h['_id'],**{k:v for k,v in h['_source'].items() if k!='embedding'}} for h in search['hits']['hits']]
text='\n'.join(c['content'] for c in chunks)
checks=[{'phrase':x,'occurrencesInIndexedText':text.count(x)} for x in ['mosaic-log-fixture','fixture-input','REQUIRED_FILE_MISSING','/fixture/ready','e2e-20261031t075722z','vector(1)','Alertmanager API']]
assert all(x['occurrencesInIndexedText']==0 for x in checks[:5])
pdf=ROOT.parent/'live-validation-20261031/mosaic-validation-control.pdf';raw=pdf.read_bytes()
assert hashlib.sha256(raw).hexdigest()==d['pdfSha256']
shutil.copy2(pdf,ROOT/pdf.name)
result={'indexedPdfSha256':d['pdfSha256'],'indexedPdfBytes':len(raw),'completeTextChunksWithoutVectorCoordinates':chunks,'vectorsAvailableIn':'continued-evidence-20261031/vector-storage-proof.json (all4x384 coordinates retained there)','phraseChecks':checks,'findings':[{'id':'G1','severity':'incorrect-source-attribution','observation':'First and second IRAOP answers describe the current Kubernetes Pod as if the control PDF documents this exact implementation; the full indexed text contains none of the unique workload names/error/path/run ID. Incident context was supplied by the question and live tools.'},{'id':'G2','severity':'incorrect-alert-path','observation':'IRAOP answers and initial synthesis conflate old vector(1)/direct Alertmanager examples with this actual max_over_time CrashLoop PrometheusRule. Loaded rule and actual pending/firing metrics contradict that attribution.'},{'id':'G3','severity':'inapplicable-repair-advice','observation':'The original suggestion to touch the marker inside a read-only ConfigMap volume is inapplicable; current Kubernetes write backend is disabled, so mode selection alone cannot enable patching.'},{'id':'G4','severity':'overbroad-health-claim','observation':'Node conditions are scoped observations; they do not establish comprehensive GPU health.'}],'operatorReviewRequired':True,'originalAnswersRetained':True}
(ROOT/'knowledge-grounding-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
out=ROOT/'research';out.mkdir(exist_ok=True)
h=json.loads((ROOT/'browser/evidence-research-history-gateway.json').read_text())
responses=[]
for m in h['messages']:
 if m.get('role')!='toolResult' or m.get('toolName')!='iraop_query':continue
 for c in m.get('content',[]):
  if c.get('type')!='text':continue
  try:v=json.loads(c.get('text',''))
  except ValueError:continue
  if isinstance(v,dict) and 'answer' in v:responses.append({'toolCallId':m['toolCallId'],'isError':m.get('isError'),'response':v})
for i,row in enumerate(responses,1):(out/('iraop-response-'+str(i)+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'chunksChecked':len(chunks),'phraseChecks':checks,'originalResearchResponses':len(responses)}))
