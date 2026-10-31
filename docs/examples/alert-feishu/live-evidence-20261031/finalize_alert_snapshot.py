#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read-only completion capture after the UI reset an existing alert session."""
import base64
from datetime import datetime,timezone
import json,urllib.parse,urllib.request
from probe_access import ROOT,BASE,read_ui_credentials
KEY='agent:default:alert-alertmanager-0fa8cbd733f54a5a'
c=read_ui_credentials(); auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with opener.open(urllib.request.Request(BASE+path,headers={'Authorization':'Basic '+auth}),timeout=90) as r:return json.load(r)
data=get('/api/openclaw/chat?'+urllib.parse.urlencode({'sessionKey':KEY,'limit':1000}))
history=json.loads(data['history']['stdout'])
before=json.loads((ROOT/'alert-ui-before-history-api.json').read_text())
old=json.loads(before['history']['stdout'])
assert data['hasActiveRun'] is False
assert history['sessionId']!=old['sessionId']
alerts=get('/api/alerts')
selected=[a for a in alerts['alerts'] if a.get('fingerprint')=='0fa8cbd733f54a5a']
assert len(selected)==1
for name,value in [('alert-ui-history-api.json',data),('alert-ui-history-gateway.json',history),('selected-alert-after-investigation.json',selected[0])]:
    (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
tools=[x for x in history['messages'] if x.get('role')=='toolResult']
summary={'at':datetime.now(timezone.utc).isoformat(),'sessionKey':KEY,'beforeSessionId':old['sessionId'],'sessionId':history['sessionId'],'beforeMessageCount':before['rawMessageCount'],'afterMessageCount':data['rawMessageCount'],'sessionReplaced':True,'hasActiveRun':False,'stage':selected[0]['stage'],'tools':[{'toolCallId':x.get('toolCallId'),'toolName':x.get('toolName'),'isError':x.get('isError')} for x in tools],'harnessNote':'Original poll expected message growth from 19; UI created a new session with 10 messages. Poll-only browser harness was interrupted after independent API confirmed completion; it did not abort the already completed model run.'}
(ROOT/'alert-ui-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
