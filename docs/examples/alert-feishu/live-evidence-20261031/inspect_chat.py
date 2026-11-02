#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read one chat's full current history without sending anything."""
import base64,json,sys,urllib.parse,urllib.request
from probe_access import BASE,ROOT,read_ui_credentials
name,key=sys.argv[1:3]
c=read_ui_credentials()
auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode()
req=urllib.request.Request(BASE+'/api/openclaw/chat?'+urllib.parse.urlencode({'sessionKey':key,'limit':1000}),headers={'Authorization':'Basic '+auth})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=120) as r:data=json.load(r)
(ROOT/(name+'-history-api.json')).write_text(json.dumps(data,indent=2)+'\n')
h=json.loads(data['history']['stdout'])
(ROOT/(name+'-history-gateway.json')).write_text(json.dumps(h,indent=2)+'\n')
print(json.dumps({'sessionKey':key,'hasActiveRun':data.get('hasActiveRun'),'messages':len(h.get('messages',[])),'lastMessages':h.get('messages',[])[-2:]},ensure_ascii=False))
