#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Click Start Investigating on the one retained synthetic Alertmanager alert."""
from datetime import datetime, timezone
import json
from urllib.parse import urlencode, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, expect
from probe_access import ROOT,BASE,read_ui_credentials
from browser_access import CHROME

KEY='agent:default:alert-alertmanager-0fa8cbd733f54a5a'

def main():
    requests=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=CHROME)
        context=browser.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100})
        page=context.new_page()
        def get(path):
            r=context.request.get(BASE+path,timeout=90000)
            assert r.status==200,(path,r.status)
            return r.json()
        def save(label):
            (ROOT/('alert-ui-'+label+'.html')).write_text(page.content())
            (ROOT/('alert-ui-'+label+'.txt')).write_text(page.locator('body').inner_text())
            page.screenshot(path=str(ROOT/('alert-ui-'+label+'.png')),full_page=True)
            (ROOT/'alert-investigate-ui-requests.json').write_text(json.dumps(requests,indent=2)+'\n')
        def record(req):
            if req.method!='GET':
                try:body=req.post_data_json
                except Exception:body=req.post_data
                requests.append({'at':datetime.now(timezone.utc).isoformat(),'path':urlparse(req.url).path,'method':req.method,'body':body})
        page.on('request',record)
        try:
            page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
            try:page.wait_for_load_state('networkidle',timeout=10000)
            except PWTimeout:pass
            expect(page.get_by_role('switch',name='Auto investigate',exact=True)).to_have_attribute('aria-checked','false')
            expect(page.get_by_role('switch',name='Auto pull',exact=True)).to_have_attribute('aria-checked','true')
            old=get('/api/openclaw/chat?'+urlencode({'sessionKey':KEY,'limit':1000}))
            (ROOT/'alert-ui-before-history-api.json').write_text(json.dumps(old,indent=2)+'\n')
            old_count=old.get('rawMessageCount',0)
            old_id=json.loads(old['history']['stdout']).get('sessionId')
            card=page.locator('.mosaic-alert-slide-in').filter(has_text='MosaicSyntheticAlert:')
            assert card.count()==1
            card.screenshot(path=str(ROOT/'selected-alert-card-before.png'))
            card.get_by_role('button',name='Start Investigating ❯',exact=True).click()
            for _ in range(120):
                posts=[x for x in requests if x['path']=='/api/openclaw/chat/stream']
                if posts:break
                page.wait_for_timeout(250)
            assert len(posts)==1,requests
            assert posts[0]['body']['sessionKey']==KEY,posts
            assert posts[0]['body'].get('accessMode','view')=='view',posts
            save('started')
            for _ in range(720):
                data=get('/api/openclaw/chat?'+urlencode({'sessionKey':KEY,'limit':1000}))
                current_history=json.loads(data['history']['stdout'])
                replaced=current_history.get('sessionId')!=old_id
                if data.get('rawMessageCount',0)>=3 and (replaced or data.get('rawMessageCount',0)>old_count) and data.get('hasActiveRun') is False:
                    history=json.loads(data['history']['stdout'])
                    (ROOT/'alert-ui-history-api.json').write_text(json.dumps(data,indent=2)+'\n')
                    (ROOT/'alert-ui-history-gateway.json').write_text(json.dumps(history,indent=2)+'\n')
                    current=get('/api/alerts')['alerts']
                    chosen=[a for a in current if a.get('fingerprint')=='0fa8cbd733f54a5a']
                    assert len(chosen)==1
                    (ROOT/'selected-alert-after-investigation.json').write_text(json.dumps(chosen[0],indent=2)+'\n')
                    save('complete')
                    (ROOT/'alert-ui-summary.json').write_text(json.dumps({'sessionKey':KEY,'beforeMessageCount':old_count,'afterMessageCount':data['rawMessageCount'],'sessionReplaced':replaced,'newMessages':history['messages'] if replaced else history['messages'][old_count:],'at':datetime.now(timezone.utc).isoformat(),'stage':chosen[0]['stage']},indent=2)+'\n')
                    print(json.dumps({'sessionKey':KEY,'oldCount':old_count,'newCount':data['rawMessageCount'],'stage':chosen[0]['stage']}))
                    break
                page.wait_for_timeout(500)
            else:raise RuntimeError('Investigation did not finish')
        except BaseException:
            save('exception')
            raise
        finally:browser.close()

if __name__=='__main__':main()
