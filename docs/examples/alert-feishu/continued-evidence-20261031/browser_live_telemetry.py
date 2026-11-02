#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Validate the actual View UI and record fetch-based SSE as well as CDP SSE."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode, urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from playwright.sync_api import sync_playwright, expect, TimeoutError as PWTimeout
from browser_access import CHROME
from probe_access import BASE, read_ui_credentials

ROOT=Path(__file__).resolve().parent/'live-telemetry'
ROOT.mkdir(exist_ok=True)
assert not (ROOT/'summary.json').exists(), 'Do not overwrite a completed UI run.'
QUESTION=('Using only the indexed mosaic-validation-control.pdf, reference MOSAIC-KB-20261031, '
          'what public verification code is printed in the Operator Decision and Evidence section on page 2? '
          'Cite the exact filename and page inline. Explain whether an automated alert investigation may directly '
          'repair a service. Perform the document search and return evidence.')
PROMPT=('Read-only validation: test from Jeff Peng. Use iraop_query exactly once with depth="quick", '
        'collections=["mosaic-validation-20261031"], and this question: '+QUESTION+
        '\nReport its returned answer and sources faithfully. Do not invent a verification code or execute repairs.')
ORACLE='CEDAR-NEBULA-E720C8C9'
assert ORACLE not in PROMPT
(ROOT/'prompt.txt').write_text(PROMPT+'\n')
requests, cdp_events = [], []

def save(name,value):
    (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def page_snapshot(page,name):
    (ROOT/(name+'.html')).write_text(page.content())
    (ROOT/(name+'.txt')).write_text(page.locator('body').inner_text())
    page.screenshot(path=str(ROOT/(name+'.png')),full_page=True)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=CHROME)
    context=browser.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100})
    context.add_init_script('''
      window.__researchStreams=[];
      const originalFetch=window.fetch;
      window.fetch=async function(...args) {
        const response=await originalFetch.apply(this,args);
        const input=args[0];const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,location.href);
        if (url.pathname==='/api/ui/events' || (response.headers.get('content-type')||'').includes('application/x-ndjson') || (response.headers.get('content-type')||'').includes('text/event-stream')) {
          const record={path:url.pathname,status:response.status,contentType:response.headers.get('content-type'),chunks:[],finished:false};
          window.__researchStreams.push(record);
          const copy=response.clone();
          (async()=>{try {const reader=copy.body.getReader(),decoder=new TextDecoder();
            while(true){const {value,done}=await reader.read();if(done)break;record.chunks.push(decoder.decode(value,{stream:true}));}
            record.chunks.push(decoder.decode());record.finished=true;
          }catch(error){record.error=String(error);}})();
        }
        return response;
      };
    ''')
    page=context.new_page()
    cdp=context.new_cdp_session(page);cdp.send('Network.enable')
    cdp.on('Network.eventSourceMessageReceived',lambda event:cdp_events.append(event))
    cdp_streams={};network=[]
    def response_received(event):
        response=event['response'];path=urlparse(response['url']).path
        if path.startswith('/api/'):
            network.append({'path':path,'requestId':event['requestId'],'status':response['status'],'mimeType':response.get('mimeType')})
        if path!='/api/ui/events':return
        entry={'path':path,'requestId':event['requestId'],'status':response['status'],'mimeType':response.get('mimeType'),'chunksBase64':[]}
        cdp_streams[event['requestId']]=entry
        try:
            result=cdp.send('Network.streamResourceContent',{'requestId':event['requestId']})
            if result.get('bufferedData'):entry['chunksBase64'].append(result['bufferedData'])
        except Exception as exc:entry['captureError']=str(exc)
    def data_received(event):
        if event['requestId'] in cdp_streams and event.get('data'):
            cdp_streams[event['requestId']]['chunksBase64'].append(event['data'])
    cdp.on('Network.responseReceived',response_received)
    cdp.on('Network.dataReceived',data_received)
    def record(req):
        if req.method=='POST' and urlparse(req.url).path=='/api/openclaw/chat/stream':
            requests.append({'path':urlparse(req.url).path,'method':req.method,'body':req.post_data_json})
    page.on('request',record)
    try:
        page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
        try:page.wait_for_load_state('networkidle',timeout=10000)
        except PWTimeout:pass
        expect(page.get_by_role('button',name='view',exact=True)).to_be_visible(timeout=90000)
        page.get_by_role('button',name='New Chat',exact=True).click()
        expect(page.get_by_role('button',name='view',exact=True)).to_have_attribute('aria-pressed','true',timeout=90000)
        page_snapshot(page,'before')
        page.locator('textarea:visible').fill(PROMPT)
        started=time.monotonic();page.get_by_role('button',name='Send',exact=True).click()
        for _ in range(120):
            if requests:break
            page.wait_for_timeout(250)
        assert len(requests)==1 and requests[0]['body']['accessMode']=='view'
        key=requests[0]['body']['sessionKey'];polls=[]
        for _ in range(600):
            r=context.request.get(BASE+'/api/openclaw/chat?'+urlencode({'sessionKey':key,'limit':1000}),timeout=90000)
            assert r.status==200
            data=r.json();polls.append({'at':datetime.now(timezone.utc).isoformat(),'rawMessageCount':data.get('rawMessageCount'),'hasActiveRun':data.get('hasActiveRun')})
            if data.get('rawMessageCount',0)>=4 and data.get('hasActiveRun') is False:break
            page.wait_for_timeout(500)
        else:raise RuntimeError('Native UI research did not complete')
        page.wait_for_timeout(1500);page_snapshot(page,'after')
        history=json.loads(data['history']['stdout'])
        tools=[m for m in history['messages'] if m.get('role')=='toolResult']
        save('history-api.json',data);save('history-gateway.json',history);save('requests.json',requests);save('polls.json',polls)
        assert len(tools)==1 and tools[0]['toolName']=='iraop_query'
        tool=tools[0];call_id=tool['toolCallId']
        streams=page.evaluate('window.__researchStreams')
        frames=[]
        import base64
        cdp_selected=[]
        for stream in cdp_streams.values():
            raw=b''.join(base64.b64decode(x) for x in stream['chunksBase64'])
            stream['receivedBytes']=len(raw)
            for line in raw.decode().splitlines():
                if call_id in line:cdp_selected.append({'path':stream['path'],'line':line})
        save('cdp-streams.private.json',cdp_streams);save('network-responses.json',network)
        save('selected-cdp-ndjson.json',cdp_selected)
        for stream in streams:
            for frame in ''.join(stream['chunks']).replace('\r\n','\n').splitlines():
                if call_id in frame:frames.append({'path':stream['path'],'frame':frame})
        selected_cdp=[e for e in cdp_events if call_id in e.get('data','')]
        save('fetch-streams.private.json',streams);save('cdp-events.private.json',cdp_events)
        save('selected-ui-events.json',{'fetch':frames,'eventSource':selected_cdp})
        parsed=None
        for block in tool.get('content',[]):
            if block.get('type')!='text':continue
            try:candidate=json.loads(block.get('text',''))
            except ValueError:continue
            if isinstance(candidate,dict) and ('answer' in candidate or 'status' in candidate):
                parsed=candidate;break
        assert parsed is not None, 'No structured research response among the complete content blocks.'
        save('research-tool-response.json',parsed)
        answer=parsed.get('answer','');sources=parsed.get('sources',[])
        summary={'at':datetime.now(timezone.utc).isoformat(),'sessionKey':key,'sessionId':history['sessionId'],'toolCallId':call_id,
                 'elapsedSeconds':time.monotonic()-started,'rawMessages':len(history['messages']),'gatewayToolIsError':tool.get('isError'),
                 'status':parsed.get('status','answer-with-sources'),'sourceCount':len(sources),'sources':sources,
                 'toolAnswerContainsOracle':ORACLE in answer,'toolAnswerHasFilename':'mosaic-validation-control.pdf' in answer,
                 'uiBodyContainsOracle':ORACLE in page.locator('body').inner_text(),'selectedFetchEventCount':len(frames),
                 'selectedEventSourceCount':len(selected_cdp),'selectedCdpNdjsonCount':len(cdp_selected),'viewMode':True}
        save('summary.json',summary);print(json.dumps(summary),flush=True)
        assert parsed.get('status')!='incomplete' and ORACLE in answer and sources
        assert summary['uiBodyContainsOracle']
    finally:
        save('all-requests.json',requests)
        save('last-cdp-streams.private.json',cdp_streams);save('last-network-responses.json',network)
        try:save('last-fetch-streams.private.json',page.evaluate('window.__researchStreams'))
        except Exception:pass
        browser.close()
