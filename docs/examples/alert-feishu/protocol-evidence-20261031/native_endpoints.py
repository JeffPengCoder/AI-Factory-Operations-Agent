#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exercise deployed HTTP and MCP endpoints without replacing any factory/model."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

ROOT = Path(sys.argv[1])
ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:8000'
HEADERS = {'Authorization': 'Bearer ' + os.environ['IRAOP_API_KEY']}
QUESTION = ('Using only the indexed mosaic-validation-control.pdf, reference MOSAIC-KB-20261031, '
            'what public verification code is printed in the Operator Decision and Evidence section on page 2? '
            'Cite the exact filename and page inline. Explain whether an automated alert investigation may directly '
            'repair a service. Perform the document search and return evidence.')
ORACLE = 'CEDAR-NEBULA-E720C8C9'  # Independent response check; never sent in a question.
assert ORACLE not in QUESTION
COLLECTION = 'mosaic-validation-20261031'
observations = []

def save(name, value):
    p = ROOT / name
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    p.chmod(0o600)

def observation(name, elapsed, response, **extra):
    answer = response.get('answer', '')
    sources = response.get('sources', [])
    item = {'case': name, 'elapsedSeconds': elapsed, **extra,
            'answerContainsOracle': ORACLE in answer,
            'answerHasFilename': 'mosaic-validation-control.pdf' in answer,
            'sources': sources, 'sourceCount': len(sources)}
    observations.append(item)
    save('case-observations.json', observations)
    print(json.dumps(item), flush=True)

async def main():
    save('metadata.json', {'at': datetime.now(timezone.utc).isoformat(),
                          'question': QUESTION, 'collection': COLLECTION,
                          'modelOrFactoryMonkeypatch': False, 'seedOverride': None})
    async with httpx.AsyncClient(timeout=300) as client:
        for name, path in [('http-unauthenticated', '/api/v1/collections'),
                           ('mcp-unauthenticated', '/mcp/sse')]:
            start = time.monotonic()
            r = await client.get(BASE + path)
            save(name + '-response.json', {'status': r.status_code, 'body': r.text})
            observation(name, time.monotonic() - start, {}, httpStatus=r.status_code)
            assert r.status_code == 401
        start = time.monotonic()
        r = await client.post(BASE + '/api/v1/query', headers=HEADERS,
                              json={'question': QUESTION, 'depth': 'invalid', 'collections': [COLLECTION]})
        save('http-invalid-depth-response.json', {'status': r.status_code, 'body': r.text})
        observation('http-invalid-depth', time.monotonic() - start, {}, httpStatus=r.status_code)
        assert r.status_code == 422
        body = {'question': QUESTION, 'depth': 'quick', 'collections': [COLLECTION]}
        save('http-query-request.json', body)
        start = time.monotonic()
        r = await client.post(BASE + '/api/v1/query', headers=HEADERS, json=body)
        save('http-query-response.json', {'status': r.status_code, 'body': r.text})
        result = r.json()
        observation('http-query', time.monotonic() - start, result, httpStatus=r.status_code)
        assert r.status_code == 200 and result.get('sources') and ORACLE in result.get('answer', '')

    async with sse_client(BASE + '/mcp/sse', headers=HEADERS, timeout=20, sse_read_timeout=300) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=300)) as session:
            save('mcp-initialize.json', (await session.initialize()).model_dump(mode='json'))
            tools = await session.list_tools()
            save('mcp-tools.json', tools.model_dump(mode='json'))
            assert set(t.name for t in tools.tools) == {'list_collections', 'query', 'list_documents', 'get_document'}
            save('mcp-collections.json', (await session.call_tool('list_collections', {})).model_dump(mode='json'))
            save('mcp-documents.json', (await session.call_tool('list_documents', {'collection': COLLECTION})).model_dump(mode='json'))
            start = time.monotonic()
            invalid = await session.call_tool('query', {'question': QUESTION, 'depth': 'invalid', 'collections': [COLLECTION]})
            save('mcp-invalid-depth-response.json', invalid.model_dump(mode='json'))
            observation('mcp-invalid-depth', time.monotonic() - start, {}, isError=invalid.isError)
            assert invalid.isError
            args = {'question': QUESTION, 'depth': 'quick', 'collections': [COLLECTION]}
            save('mcp-query-request.json', args)
            start = time.monotonic()
            result = await session.call_tool('query', args)
            raw = result.model_dump(mode='json')
            save('mcp-query-response.json', raw)
            parsed = result.structuredContent
            if not isinstance(parsed, dict) or 'answer' not in parsed:
                parsed = next((json.loads(c.text) for c in result.content if c.type == 'text' and c.text.lstrip().startswith('{')), {})
            save('mcp-query-parsed.json', parsed)
            observation('mcp-query', time.monotonic() - start, parsed, isError=result.isError)
            assert not result.isError and parsed.get('sources') and ORACLE in parsed.get('answer', '')
    save('run-exit.json', {'exitCode': 0})

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except BaseException:
        save('run-exit.json', {'exitCode': 1, 'traceback': traceback.format_exc()})
        raise
