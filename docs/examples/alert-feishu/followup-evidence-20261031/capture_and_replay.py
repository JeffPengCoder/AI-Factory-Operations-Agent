#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Observe unchanged research request, then compare first-turn thinking modes."""
import asyncio,copy,json,os,time,traceback
from datetime import datetime,timezone
from pathlib import Path
import sys

import httpx
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
import app.agent as factory
from app.query_service import _extract_answer,_collect_sources

OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
QUESTION='Using only the indexed mosaic-validation-control.pdf, reference MOSAIC-KB-20261031, what public verification code is printed in the Operator Decision and Evidence section on page 2? Cite the exact filename and page inline. Explain whether an automated alert investigation may directly repair a service. Perform the document search and return evidence.'
first_request=None

def serial(x):
    if hasattr(x,'model_dump'):return x.model_dump()
    return repr(x)

async def capture(request):
    global first_request
    if first_request is None and request.url.path.endswith('/chat/completions'):
        first_request=json.loads(await request.aread())
        (OUT/'first-request.private.json').write_text(json.dumps({'url':str(request.url),'body':first_request},indent=2)+'\n')

async def replay(name,url,disable_thinking):
    body=copy.deepcopy(first_request)
    body['seed']=101
    body['stream']=True
    if disable_thinking:body['chat_template_kwargs']={'enable_thinking':False}
    (OUT/(name+'-request.private.json')).write_text(json.dumps({'url':url,'body':body},indent=2)+'\n')
    content=[];reasoning=[];calls={};finishes=[];usage=None
    start=time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90,connect=15)) as client:
            async with client.stream('POST',url,json=body,headers={'Authorization':'Bearer '+os.environ['NVIDIA_CHAT_API_KEY']}) as response:
                status=response.status_code
                with (OUT/(name+'-response.sse')).open('w') as stream:
                    async for line in response.aiter_lines():
                        stream.write(line+'\n');stream.flush()
                        if not line.startswith('data: ') or line=='data: [DONE]':continue
                        try:event=json.loads(line[6:])
                        except json.JSONDecodeError:continue
                        if event.get('usage'):usage=event['usage']
                        for choice in event.get('choices',[]):
                            delta=choice.get('delta',{})
                            if delta.get('content'):content.append(delta['content'])
                            if delta.get('reasoning_content'):reasoning.append(delta['reasoning_content'])
                            if delta.get('reasoning'):reasoning.append(delta['reasoning'])
                            if choice.get('finish_reason'):finishes.append(choice['finish_reason'])
                            for tool in delta.get('tool_calls',[]):
                                item=calls.setdefault(tool['index'],{'id':'','name':'','arguments':''})
                                if tool.get('id'):item['id']=tool['id']
                                f=tool.get('function',{})
                                if f.get('name'):item['name']+=f['name']
                                if f.get('arguments'):item['arguments']+=f['arguments']
        result={'case':name,'httpStatus':status,'elapsedSeconds':time.monotonic()-start,'content':''.join(content),'reasoning':''.join(reasoning),'toolCalls':list(calls.values()),'finishReasons':finishes,'usage':usage}
    except Exception as exc:
        result={'case':name,'elapsedSeconds':time.monotonic()-start,'error':str(exc),'errorType':type(exc).__name__,'traceback':traceback.format_exc()}
    (OUT/(name+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['content','reasoning','traceback','toolCalls']}|{'tools':[x['name'] for x in result.get('toolCalls',[])]}),flush=True)

async def main():
    client=httpx.AsyncClient(timeout=90,event_hooks={'request':[capture]})
    def model():
        return ChatOpenAI(base_url=factory.NVIDIA_CHAT_BASE_URL,api_key=factory.NVIDIA_CHAT_API_KEY,model=factory.NVIDIA_CHAT_MODEL,max_tokens=factory.MAX_TOKENS,temperature=1.0,streaming=True,max_retries=3,http_async_client=client)
    factory._create_model=model
    sink=[];start=time.monotonic()
    try:
        async with asyncio.timeout(240):
            agent=factory.create_research_agent(depth='quick',collections=['mosaic-validation-20261031'],source_sink=sink)
            state=await agent.ainvoke({'messages':[HumanMessage(content=QUESTION)]})
        answer,messages=_extract_answer(state)
        result={'elapsedSeconds':time.monotonic()-start,'answer':answer,'sourceSink':sink,'sources':_collect_sources(messages,answer,sink),'messageCount':len(messages)}
        (OUT/'capture-agent-state.private.json').write_text(json.dumps(state,default=serial,indent=2)+'\n')
    except Exception as exc:result={'elapsedSeconds':time.monotonic()-start,'errorType':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()}
    (OUT/'capture-agent-summary.json').write_text(json.dumps(result,default=serial,indent=2)+'\n')
    print(json.dumps({'captureAgent':True,'messageCount':result.get('messageCount'),'sourceHits':len(sink),'error':result.get('error')}),flush=True)
    await client.aclose()
    if first_request is None:raise RuntimeError('Request was not captured')
    compat=factory.NVIDIA_CHAT_BASE_URL.rstrip('/')+'/chat/completions'
    direct='http://spark-kind-bridge.example.invalid:8000/v1/chat/completions'
    for prefix,url in [('compat',compat),('direct',direct)]:
        for thinking in [False,True]:
            await replay(prefix+('-no-thinking' if thinking else '-default'),url,thinking)
    (OUT/'completed.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'cases':4})+'\n')

asyncio.run(main())
