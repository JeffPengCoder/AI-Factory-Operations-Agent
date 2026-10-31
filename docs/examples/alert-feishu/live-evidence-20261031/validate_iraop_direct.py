#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run inside IRAOP; emit full response per step, never the auth token."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

BASE='http://127.0.0.1:8000'
COLLECTION='mosaic-validation-20261031'

def request(name,path,body=None,authenticated=True,binary=False,timeout=60):
    start=time.monotonic()
    headers={}
    if authenticated:headers['Authorization']='Bearer '+os.environ['IRAOP_API_KEY']
    if body is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:status,data=r.status,r.read()
    except urllib.error.HTTPError as e:status,data=e.code,e.read()
    event={'step':name,'at':datetime.now(timezone.utc).isoformat(),'path':path,'request':body,'httpStatus':status,'elapsedSeconds':time.monotonic()-start}
    if binary and status==200:
        event.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),bodyBase64=base64.b64encode(data).decode())
    else:
        try:event['body']=json.loads(data)
        except ValueError:event['body']=data.decode(errors='replace')
    print(json.dumps(event),flush=True)
    return event

request('live','/api/v1/live',authenticated=False)
request('health','/api/v1/health',authenticated=False)
assert request('auth-denial','/api/v1/collections',authenticated=False)['httpStatus']==401
request('collections-before','/api/v1/collections')
ingest=request('ingest','/api/v1/ingest/file',{'file_path':'/cm/shared/iraop-corpus/mosaic-validation-control.pdf','collection':COLLECTION},timeout=180)
assert ingest['httpStatus']==200
request('collections-after','/api/v1/collections')
request('documents','/api/v1/collections/'+COLLECTION+'/documents')
request('original-pdf','/api/v1/documents/mosaic-validation-control.pdf',binary=True)
question='Using only the indexed collection, what public verification code is printed on page 2 of MOSAIC-KB-20261031? Cite the source filename and page. Explain what View, Edit with HITL, and Auto permit, and whether an automated alert investigation may directly repair a service. If the document was not retrieved, say so.'
result=request('query','/api/v1/query',{'question':question,'depth':'quick','collections':[COLLECTION]},timeout=360)
assert result['httpStatus']==200
