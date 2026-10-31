#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run in IRAOP: real direct search + unmodified agent, with full local trace."""
import asyncio
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import time
import traceback

from langchain_core.messages import HumanMessage
import app.agent as factory
from app.agent import create_research_agent
from app.opensearch_client.client import get_client
from app.opensearch_client.search import hybrid_search
from app.query_service import _extract_answer,_collect_sources

QUESTION='Using only the indexed mosaic-validation-control.pdf, reference MOSAIC-KB-20261031, what public verification code is printed in the Operator Decision and Evidence section on page 2? Cite the exact filename and page inline. Explain whether an automated alert investigation may directly repair a service. Perform the document search and return evidence.'
COLLECTION='mosaic-validation-20261031'
OUTPUT=Path(sys.argv[1])
OUTPUT.mkdir(parents=True,exist_ok=True)
MODE=sys.argv[2] if len(sys.argv)>2 else 'unchanged'
SEED=int(sys.argv[3]) if len(sys.argv)>3 else None
MODEL_BASE=sys.argv[4]
import httpx
from langchain_openai import ChatOpenAI
request_records=[]
forced=False

async def record_request(request):
    global forced
    original=json.loads(await request.aread())
    body=dict(original)
    tool_names=[item.get('function',{}).get('name') for item in body.get('tools',[])]
    intervention=None
    if MODE in ['force-search-first','force-search-first-no-thinking'] and not forced and 'opensearch_search' in tool_names:
        body['tool_choice']={'type':'function','function':{'name':'opensearch_search'}}
        forced=True
        intervention='force exactly the first model call to the actual opensearch_search tool'
    if MODE=='force-search-first-no-thinking':
        body['chat_template_kwargs']={'enable_thinking':False}
    encoded=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
    request._content=encoded
    request.stream=httpx.ByteStream(encoded)
    request.headers['Content-Length']=str(len(encoded))
    sequence=len(request_records)+1
    record={'sequence':sequence,'url':str(request.url),'originalBody':original,'actualBody':body,'intervention':intervention}
    (OUTPUT/f'request-{sequence:03d}.private.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    request_records.append({'sequence':sequence,'toolCount':len(tool_names),'toolChoice':body.get('tool_choice'),'lastMessageRole':body['messages'][-1]['role'],'intervention':intervention})

HTTP_CLIENT=httpx.AsyncClient(timeout=120,event_hooks={'request':[record_request]})
def model():
    return ChatOpenAI(base_url=MODEL_BASE,api_key=factory.NVIDIA_CHAT_API_KEY,model=factory.NVIDIA_CHAT_MODEL,max_tokens=factory.MAX_TOKENS,temperature=1.0,streaming=True,max_retries=3,seed=SEED,http_async_client=HTTP_CLIENT)
factory._create_model=model

def serial(value):
    if hasattr(value,'model_dump'):return value.model_dump()
    if isinstance(value,Path):return str(value)
    return repr(value)

async def main():
    records=[]
    metadata={'at':datetime.now(timezone.utc).isoformat(),'question':QUESTION,'collection':COLLECTION,'modelMode':MODE,'seed':SEED,'packages':{name:importlib.metadata.version(name) for name in ['deepagents','langchain','langchain-openai','langgraph','httpx']}}
    (OUTPUT/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    start=time.monotonic()
    try:
        hits=await asyncio.to_thread(hybrid_search,get_client(),'MOSAIC-KB-20261031 Operator Decision Evidence page 2 verification code',[COLLECTION],3)
        direct={'elapsedSeconds':time.monotonic()-start,'hits':hits}
    except Exception as exc:
        direct={'elapsedSeconds':time.monotonic()-start,'errorType':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()}
    (OUTPUT/'direct-hybrid-search.json').write_text(json.dumps(direct,indent=2)+'\n')
    print(json.dumps({'step':'direct-search','hitCount':len(direct.get('hits',[])),'error':direct.get('error')}),flush=True)
    source_sink=[]
    agent=create_research_agent(depth='quick',collections=[COLLECTION],source_sink=source_sink)
    start=time.monotonic();result=None
    with (OUTPUT/'agent-events.private.jsonl').open('w') as stream:
        try:
            async with asyncio.timeout(240):
                async for event in agent.astream_events({'messages':[HumanMessage(content=QUESTION)]},version='v2'):
                    stream.write(json.dumps(event,default=serial)+'\n');stream.flush()
                    if event['event'] in ['on_tool_start','on_tool_end','on_chat_model_end']:
                        records.append(event)
                    if event['event']=='on_chain_end' and not event.get('parent_ids'):
                        result=event['data'].get('output')
        except Exception as exc:
            (OUTPUT/'trace-error.json').write_text(json.dumps({'errorType':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc()},indent=2)+'\n')
    (OUTPUT/'agent-records.private.json').write_text(json.dumps(records,default=serial,indent=2)+'\n')
    (OUTPUT/'agent-state.private.json').write_text(json.dumps(result,default=serial,indent=2)+'\n')
    if result:
        answer,messages=_extract_answer(result)
        sources=_collect_sources(messages,answer,source_sink)
    else:answer='';messages=[];sources=[]
    summary={'elapsedSeconds':time.monotonic()-start,'messageCount':len(messages),'toolEvents':[{'event':e['event'],'name':e['name']} for e in records if e['event'].startswith('on_tool_')],'sourceSink':source_sink,'answer':answer,'sources':sources,'resultPresent':bool(result)}
    (OUTPUT/'trace-summary.json').write_text(json.dumps(summary,default=serial,indent=2)+'\n')
    print(json.dumps({'step':'agent','elapsedSeconds':summary['elapsedSeconds'],'messageCount':len(messages),'searches':sum(e['name']=='opensearch_search' and e['event']=='on_tool_start' for e in records),'sourceHits':len(source_sink),'resultPresent':bool(result)}),flush=True)

async def run():
    try:
        await main()
    finally:
        (OUTPUT/'request-observations.json').write_text(json.dumps(request_records,indent=2)+'\n')
        await HTTP_CLIENT.aclose()
asyncio.run(run())
