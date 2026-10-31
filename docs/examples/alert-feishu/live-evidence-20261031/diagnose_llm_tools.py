#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Real model wire-format diagnosis, with a harmless nonexecuted tool schema."""
import asyncio
import json
import os
import time
from langchain_openai import ChatOpenAI

TOOL={'type':'function','function':{'name':'lookup_validation_document','description':'Look up the verification code in a document.','parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}}

async def main():
    for name,url,streaming in [('compat-stream','http://llm-openai-compat:8000/v1',True),('compat-nonstream','http://llm-openai-compat:8000/v1',False),('direct-stream','http://spark-kind-bridge.example.invalid:8000/v1',True),('direct-nonstream','http://spark-kind-bridge.example.invalid:8000/v1',False)]:
        started=time.monotonic()
        try:
            model=ChatOpenAI(base_url=url,api_key=os.environ['NVIDIA_CHAT_API_KEY'],model=os.environ['NVIDIA_CHAT_MODEL'],max_tokens=256,temperature=0,streaming=streaming,max_retries=0)
            m=await model.bind_tools([TOOL],tool_choice='required').ainvoke('Use lookup_validation_document to look up the public verification code on page 2 of mosaic-validation-control.pdf. Do not answer the question yourself.')
            result={'case':name,'elapsedSeconds':time.monotonic()-started,'message':m.model_dump()}
        except Exception as e:
            result={'case':name,'elapsedSeconds':time.monotonic()-started,'errorType':type(e).__name__,'error':str(e)}
        print(json.dumps(result,default=str),flush=True)

asyncio.run(main())
