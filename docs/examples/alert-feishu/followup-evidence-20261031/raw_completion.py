#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Capture raw model output before tool parsing, using the same rendered chat."""
import asyncio,json,os,time
from pathlib import Path
import httpx

OUT=Path('/tmp/mosaic-research-raw-parser-20261031');OUT.mkdir(exist_ok=True)
body=json.loads(Path('/tmp/mosaic-research-replay-20261031/first-request.private.json').read_text())['body']
BASE='http://spark-kind-bridge.example.invalid:8000'

async def main():
    headers={'Authorization':'Bearer '+os.environ['NVIDIA_CHAT_API_KEY']}
    async with httpx.AsyncClient(timeout=120) as client:
        request={'model':body['model'],'messages':body['messages'],'tools':body['tools'],'add_generation_prompt':True,'chat_template_kwargs':{'enable_thinking':False}}
        (OUT/'tokenize-request.private.json').write_text(json.dumps(request,indent=2)+'\n')
        r=await client.post(BASE+'/tokenize',json=request,headers=headers)
        (OUT/'tokenize-response.private.json').write_bytes(r.content)
        assert r.status_code==200,(r.status_code,r.text)
        tokens=r.json()['tokens']
        request={'model':body['model'],'prompt':tokens,'temperature':1.0,'seed':101,'max_tokens':4096,'stream':False,'skip_special_tokens':False,'return_token_ids':True}
        (OUT/'completion-request.private.json').write_text(json.dumps(request,indent=2)+'\n')
        start=time.monotonic()
        r=await client.post(BASE+'/v1/completions',json=request,headers=headers)
        (OUT/'completion-response.private.json').write_bytes(r.content)
        result={'httpStatus':r.status_code,'elapsedSeconds':time.monotonic()-start,'renderedPromptTokenCount':len(tokens),'response':r.json()}
        (OUT/'raw-summary.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'httpStatus':r.status_code,'elapsedSeconds':result['elapsedSeconds'],'promptTokens':len(tokens),'choices':r.json().get('choices')}),flush=True)

asyncio.run(main())
