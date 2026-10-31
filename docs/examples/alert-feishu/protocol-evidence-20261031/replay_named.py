#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Compare actual named-tool wire responses; no agent/configuration changes."""
import asyncio,copy,json,os,time
from pathlib import Path
import httpx

ROOT=Path('/tmp/mosaic-protocol-20261031/named-wire')
ROOT.mkdir(exist_ok=True)
BODY=json.loads(Path('/tmp/mosaic-protocol-20261031/force-search-first-no-thinking/request-001.private.json').read_text())['actualBody']

async def case(name,base,stream):
    request=copy.deepcopy(BODY)
    request['stream']=stream
    request['max_completion_tokens']=4096
    (ROOT/(name+'-request.private.json')).write_text(json.dumps(request,indent=2)+'\n')
    started=time.monotonic()
    async with httpx.AsyncClient(timeout=120) as client:
        response=await client.post(base+'/chat/completions',json=request,headers={'Authorization':'Bearer '+os.environ['NVIDIA_CHAT_API_KEY']})
    (ROOT/(name+'-response.private')).write_bytes(response.content)
    result={'case':name,'url':base,'stream':stream,'httpStatus':response.status_code,'contentType':response.headers.get('content-type'),'elapsedSeconds':time.monotonic()-started}
    if stream:
        content=[];calls=[];finishes=[]
        for line in response.text.splitlines():
            if not line.startswith('data: ') or line=='data: [DONE]':continue
            value=json.loads(line[6:])
            for choice in value.get('choices',[]):
                delta=choice.get('delta',{})
                if delta.get('content'):content.append(delta['content'])
                if delta.get('tool_calls'):calls.append(delta['tool_calls'])
                if choice.get('finish_reason'):finishes.append(choice['finish_reason'])
        result.update({'fullContent':''.join(content),'allToolCallDeltas':calls,'finishReasons':finishes})
    else:
        result['fullResponse']=response.json()
    (ROOT/(name+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['fullContent','allToolCallDeltas','fullResponse']}),flush=True)

async def main():
    for prefix,base in [('compat','http://llm-openai-compat:8000/v1'),('direct','http://spark-kind-bridge.example.invalid:8000/v1')]:
        for stream in [True,False]:
            await case(prefix+('-stream' if stream else '-nonstream'),base,stream)

asyncio.run(main())
