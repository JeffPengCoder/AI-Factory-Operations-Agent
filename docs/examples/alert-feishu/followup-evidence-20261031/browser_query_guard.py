#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Observe one real View-mode IRAOP query and the UI's SSE events."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode, urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from playwright.sync_api import sync_playwright, expect
from browser_access import CHROME
from probe_access import BASE, read_ui_credentials

ROOT = Path(__file__).resolve().parent/'query-guard-ui'
ROOT.mkdir(exist_ok=True)
events, requests = [], []

def save(page, label):
    (ROOT/(label+'.html')).write_text(page.content())
    (ROOT/(label+'.txt')).write_text(page.locator('body').inner_text())
    page.screenshot(path=str(ROOT/(label+'.png')), full_page=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=CHROME)
    context = browser.new_context(http_credentials=read_ui_credentials(), viewport={'width': 1500, 'height': 1050})
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    cdp.send('Network.enable')
    cdp.on('Network.eventSourceMessageReceived', lambda event: events.append(event))
    def record(req):
        if req.method == 'POST' and urlparse(req.url).path == '/api/openclaw/chat/stream':
            requests.append({'path': urlparse(req.url).path, 'method': req.method, 'body': req.post_data_json})
    page.on('request', record)
    page.goto(BASE, wait_until='domcontentloaded', timeout=60000)
    expect(page.get_by_role('button', name='view', exact=True)).to_be_visible(timeout=90000)
    page.get_by_role('button', name='New Chat', exact=True).click()
    expect(page.get_by_role('button', name='view', exact=True)).to_have_attribute('aria-pressed', 'true', timeout=90000)
    save(page, 'before')
    page.locator('textarea:visible').fill((ROOT.parent/'query-guard-prompt.txt').read_text())
    started = time.monotonic()
    page.get_by_role('button', name='Send', exact=True).click()
    for _ in range(120):
        if requests: break
        page.wait_for_timeout(250)
    assert len(requests) == 1
    key = requests[0]['body']['sessionKey']
    assert requests[0]['body']['accessMode'] == 'view'
    polls = []
    for _ in range(600):
        r = context.request.get(BASE+'/api/openclaw/chat?'+urlencode({'sessionKey': key, 'limit': 1000}), timeout=90000)
        assert r.status == 200
        data = r.json()
        polls.append({'at': datetime.now(timezone.utc).isoformat(), 'rawMessageCount': data.get('rawMessageCount'), 'hasActiveRun': data.get('hasActiveRun')})
        if data.get('rawMessageCount', 0) >= 4 and data.get('hasActiveRun') is False:
            break
        page.wait_for_timeout(500)
    else:
        raise RuntimeError('Actual UI query did not finish')
    page.wait_for_timeout(1500)
    save(page, 'after')
    history = json.loads(data['history']['stdout'])
    tools = [m for m in history['messages'] if m.get('role') == 'toolResult']
    assert len(tools) == 1 and tools[0]['toolName'] == 'iraop_query'
    status = json.loads(tools[0]['content'][0]['text'])['status']
    assert status == 'incomplete'
    call_id = tools[0]['toolCallId']
    selected = [event for event in events if call_id in event.get('data', '')]
    for name, value in [('history-api.json', data), ('history-gateway.json', history), ('requests.json', requests), ('polls.json', polls), ('sse-events.private.json', events), ('selected-sse-events.json', selected)]:
        (ROOT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    summary = {'at': datetime.now(timezone.utc).isoformat(), 'sessionKey': key, 'sessionId': history['sessionId'], 'toolCallId': call_id, 'elapsedSeconds': time.monotonic()-started, 'rawMessages': len(history['messages']), 'researchStatus': status, 'gatewayToolIsError': tools[0].get('isError'), 'selectedUIEventCount': len(selected), 'uiIncompleteTextVisible': 'IRA research incomplete' in page.locator('body').inner_text(), 'viewMode': True}
    (ROOT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary))
    browser.close()
