#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Real CPU ONNX embeddings; fixed model, token auth, no silent truncation."""
import hashlib
import hmac
import json
import logging
from pathlib import Path
import time
from typing import Literal
import uuid

from fastapi import FastAPI, Header, HTTPException
import numpy as np
import onnxruntime as ort
from pydantic import BaseModel, ConfigDict
from transformers import AutoTokenizer
import uvicorn

ROOT = Path(__file__).resolve().parent
META = json.loads((ROOT/'model-manifest.json').read_text())
TOKEN = (ROOT/'token').read_text().strip()
assert TOKEN, 'Local service token must be nonempty'
tokenizer = AutoTokenizer.from_pretrained(ROOT/'model', local_files_only=True, trust_remote_code=False)
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
session = ort.InferenceSession(str(ROOT/'model/onnx/model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('embedding-validation')
app = FastAPI()


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str
    input: str | list[str]
    encoding_format: Literal['float'] = 'float'


@app.get('/health')
def health():
    return {**META,'loaded':True,'providers':session.get_providers()}


@app.post('/v1/embeddings')
def embeddings(request: EmbeddingRequest, authorization: str = Header(default='')):
    started = time.monotonic()
    if not hmac.compare_digest(authorization, 'Bearer '+TOKEN):
        raise HTTPException(401,'Local embedding bearer token required')
    if request.model != META['model']:
        raise HTTPException(400,'Unexpected model')
    texts = [request.input] if isinstance(request.input,str) else request.input
    if not 1 <= len(texts) <= 64 or any(not text or len(text)>20000 for text in texts):
        raise HTTPException(400,'Expected 1-64 nonempty bounded texts')
    encoded = tokenizer(texts, padding=True, truncation=False, return_tensors='np')
    if encoded['input_ids'].shape[1] > META['maxTokens']:
        raise HTTPException(422,'Input exceeds model context; nothing silently truncated')
    inputs = {x.name: encoded[x.name].astype(np.int64) for x in session.get_inputs()}
    output = session.run(None,inputs)[0]
    mask = encoded['attention_mask'][...,None].astype(np.float32)
    pooled = (output*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1e-9)
    vectors = pooled/np.maximum(np.linalg.norm(pooled,axis=1,keepdims=True),1e-12)
    assert vectors.shape[1] == META['dimension'] and np.isfinite(vectors).all()
    tokens = int(encoded['attention_mask'].sum())
    event = {'requestId':uuid.uuid4().hex,'model':META['model'],'revision':META['revision'],'inputs':len(texts),'inputSha256':[hashlib.sha256(x.encode()).hexdigest() for x in texts],'tokens':tokens,'dimension':META['dimension'],'elapsedSeconds':time.monotonic()-started}
    log.info(json.dumps(event))
    return {'object':'list','model':META['model'],'data':[{'object':'embedding','index':i,'embedding':v.tolist()} for i,v in enumerate(vectors)],'usage':{'prompt_tokens':tokens,'total_tokens':tokens}}


if __name__ == '__main__':
    uvicorn.run(app,host='spark-kind-bridge.example.invalid',port=18081)
