#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exercise upload-and-ingest in a new isolated collection, then remove only it."""
from datetime import datetime,timezone
import hashlib,json,os,traceback
import httpx
from app.opensearch_client.client import get_client
from app.opensearch_client.index_manager import get_collection_index
COLLECTION='mosaic-upload-check-20261031t071049z'
FILENAME='mosaic-upload-check-20261031t071049z.pdf'
client=get_client();index=get_collection_index(COLLECTION)
assert not client.indices.exists(index=index), 'Refuse to modify a preexisting collection.'
headers={'Authorization':'Bearer '+os.environ['IRAOP_API_KEY']}
result={'at':datetime.now(timezone.utc).isoformat(),'collection':COLLECTION,'index':index,'filename':FILENAME,'existedBefore':False,'originalControlCollection':'mosaic-validation-20261031'}
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=150) as http:
 try:
  original=http.get('/api/v1/documents/mosaic-validation-control.pdf',headers=headers);original.raise_for_status()
  result['uploadedPdfBytes']=len(original.content);result['uploadedPdfSha256']=hashlib.sha256(original.content).hexdigest()
  response=http.post('/api/v1/ingest/upload',headers=headers,data={'collection':COLLECTION},files={'file':(FILENAME,original.content,'application/pdf')})
  result['uploadResponse']={'status':response.status_code,'body':response.text}
  if client.indices.exists(index=index):
   client.indices.refresh(index=index)
   result['mapping']=client.indices.get_mapping(index=index)
   result['completeIndexedRecordsWithVectors']=client.search(index=index,body={'size':100,'query':{'match_all':{}},'sort':[{'chunk_index':'asc'}]})
   result['allChunkRows']=[{'id':h['_id'],'source_file':h['_source']['source_file'],'page_number':h['_source']['page_number'],'chunk_index':h['_source']['chunk_index'],'contentCharacters':len(h['_source']['content']),'embeddingDimensions':len(h['_source'].get('embedding',[]))} for h in result['completeIndexedRecordsWithVectors']['hits']['hits']]
  download=http.get('/api/v1/documents/'+FILENAME,headers=headers)
  result['sourcePdfDownload']={'status':download.status_code,'body':download.text if download.status_code!=200 else None,'bytes':len(download.content),'sha256':hashlib.sha256(download.content).hexdigest() if download.status_code==200 else None}
 except Exception as exc:
  result['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
 finally:
  if client.indices.exists(index=index):
   # Exact name was absent before this run. No wildcard or original collection.
   result['cleanup']=client.indices.delete(index=index)
  result['isolatedIndexExistsAfterCleanup']=client.indices.exists(index=index)
  control=get_collection_index('mosaic-validation-20261031')
  result['originalControlCountAfter']=client.count(index=control,body={'query':{'term':{'source_file':'mosaic-validation-control.pdf'}}})
print(json.dumps(result,ensure_ascii=False))
