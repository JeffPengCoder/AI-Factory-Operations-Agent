#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read-only native negative cases; use existing container credentials in memory."""
import asyncio,json,os,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path
import httpx
ROOT=Path(sys.argv[1]);ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
HEADER={'Authorization':'Bearer '+os.environ['IRAOP_API_KEY']}
BASE='http://127.0.0.1:8000'
CASES=[
 {'case':'unanswerable-gpu-serial','question':'Using only collection mosaic-validation-20261031, what is the exact hardware serial number of the failed GPU for the existing synthetic alert fingerprint 0fa8cbd733f54a5a? Perform a real document search. If the indexed documents do not explicitly provide that serial number or do not establish a failed GPU, say that the answer is unavailable. Do not infer a number or diagnose hardware from the synthetic alert. Cite the document filename and page for anything you actually find.','depth':'quick','collections':['mosaic-validation-20261031'],'expected':'The corpus contains no GPU serial or proof of a GPU fault; clearly decline to invent either.'},
 {'case':'missing-collection','question':'Using only the specified collection, search for MOSAIC-KB-20261031 Operator Decision and Evidence. Return the public verification code and exact source filename/page only if they are actually retrieved. If the collection is missing or search fails, report that failure without inventing an answer.','depth':'quick','collections':['mosaic-validation-no-such-collection-20261031'],'expected':'Missing collection must not yield a verified sourced research answer.'},
]
def save(name,value):
 p=ROOT/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
async def main():
 save('metadata.json',{'at':datetime.now(timezone.utc).isoformat(),'factoryModified':False,'modelModified':False,'auditConfigurationModified':False,'cases':CASES})
 observations=[]
 async with httpx.AsyncClient(timeout=120) as client:
  before=await client.get(BASE+'/api/v1/collections',headers=HEADER)
  save('collections-before.json',{'status':before.status_code,'body':before.text})
  assert before.status_code==200 and 'mosaic-validation-no-such-collection-20261031' not in before.text
  for case in CASES:
   body={k:case[k] for k in ['question','depth','collections']};save(case['case']+'-request.json',body)
   started=time.monotonic()
   try:
    response=await client.post(BASE+'/api/v1/query',headers=HEADER,json=body)
    item={'at':datetime.now(timezone.utc).isoformat(),'case':case['case'],'elapsedSeconds':time.monotonic()-started,'status':response.status_code,'body':response.text,'expected':case['expected']}
    try:parsed=response.json()
    except ValueError:parsed={}
    brief={'case':case['case'],'elapsedSeconds':item['elapsedSeconds'],'httpStatus':response.status_code,'sourceCount':len(parsed.get('sources',[])),'answer':parsed.get('answer'),'error':parsed.get('detail')}
   except Exception as exc:
    item={'case':case['case'],'elapsedSeconds':time.monotonic()-started,'error':str(exc),'traceback':traceback.format_exc()}
    brief={'case':case['case'],'errorType':type(exc).__name__,'elapsedSeconds':item['elapsedSeconds']}
   save(case['case']+'-response.json',item);observations.append(brief);save('observations.json',observations);print(json.dumps(brief),flush=True)
  after=await client.get(BASE+'/api/v1/collections',headers=HEADER)
  save('collections-after.json',{'status':after.status_code,'body':after.text})
  # Collection sizes can change between requests; keep full before/after.
 save('run-finished.json',{'at':datetime.now(timezone.utc).isoformat(),'casesCompleted':len(observations)})
asyncio.run(main())
