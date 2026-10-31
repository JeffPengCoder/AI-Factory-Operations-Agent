#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Use the actual UI streaming API and export the full Gateway history."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

from probe_access import BASE, ROOT, read_ui_credentials

name=sys.argv[1]
session_key=sys.argv[2]
prompt_path=Path(sys.argv[3])
credentials=read_ui_credentials()
token=base64.b64encode((credentials['username']+':'+credentials['password']).encode()).decode()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
payload={'prompt':prompt_path.read_text(),'sessionKey':session_key,'conciseMode':False,'accessMode':'view'}
(ROOT/(name+'-request.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
start=time.monotonic()
req=urllib.request.Request(BASE+'/api/openclaw/chat/stream',data=json.dumps(payload).encode(),headers={'Authorization':'Basic '+token,'Content-Type':'application/json'})
with opener.open(req,timeout=420) as response:
    status=response.status
    with (ROOT/(name+'-stream.jsonl')).open('wb') as out:
        while True:
            line=response.readline()
            if not line:break
            out.write(line);out.flush()
history_req=urllib.request.Request(BASE+'/api/openclaw/chat?'+urllib.parse.urlencode({'sessionKey':session_key,'limit':1000}),headers={'Authorization':'Basic '+token})
with opener.open(history_req,timeout=120) as response:
    raw=response.read()
(ROOT/(name+'-history-api.json')).write_bytes(raw)
api=json.loads(raw)
history=json.loads(api['history']['stdout']) if api.get('history',{}).get('stdout') else api
(ROOT/(name+'-history-gateway.json')).write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n')
tools=[x for x in history.get('messages',[]) if x.get('role')=='toolResult']
result={'at':datetime.now(timezone.utc).isoformat(),'sessionKey':session_key,'httpStatus':status,'elapsedSeconds':time.monotonic()-start,'rawMessages':len(history.get('messages',[])),'tools':[{'name':x.get('toolName'),'toolCallId':x.get('toolCallId'),'isError':x.get('isError')} for x in tools],'hasActiveRun':api.get('hasActiveRun')}
(ROOT/(name+'-summary.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
