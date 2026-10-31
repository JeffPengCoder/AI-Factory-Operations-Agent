#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Isolated process experiment; changes no serving configuration."""
import asyncio,json,time
import app.agent as factory
from app.models import QueryRequest
from app.query_service import run_query

factory.NVIDIA_CHAT_BASE_URL='http://spark-kind-bridge.example.invalid:8000/v1'
question='Search the indexed contents of mosaic-validation-control.pdf, reference MOSAIC-KB-20261031. Read the Operator Decision and Evidence section on page 2. What public verification code is printed there? Return the code and the exact filename/page inline, using the actual retrieved text. Perform the document search and report evidence.'
async def main():
    start=time.monotonic()
    result=await run_query(QueryRequest(question=question,depth='quick',collections=['mosaic-validation-20261031']))
    print(json.dumps({'changedVariable':'chat base URL only, in this exec process','elapsedSeconds':time.monotonic()-start,'question':question,'response':result.model_dump()}))
asyncio.run(main())
