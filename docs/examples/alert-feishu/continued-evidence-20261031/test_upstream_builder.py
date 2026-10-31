#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Verify the rendered upstream installation builder's opt-in Research control."""
import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parent/'upstream-builder'
ROOT.mkdir(exist_ok=True)
CHROME='/Users/operator/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
records=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path=CHROME)
 page=browser.new_page(viewport={'width':1500,'height':1100})
 try:
  page.goto('http://127.0.0.1:18785/docs/installation_builder.html',wait_until='networkidle')
  form=page.locator('#install-command-builder')
  research=form.locator('input[name="research"]')
  compat=form.locator('input[name="researchToolCalls"]')
  code=form.locator('pre code')
  def capture(name):
   text=code.inner_text()
   records.append({'case':name,'researchChecked':research.is_checked(),'compatibilityChecked':compat.is_checked(),'compatibilityVisible':compat.is_visible(),'completeGeneratedCommand':text,'prerequisites':form.locator('.builder-prerequisites').inner_text()})
   (ROOT/(name+'.html')).write_text(page.content());page.screenshot(path=str(ROOT/(name+'.png')),full_page=True)
  expect(compat).to_be_hidden();expect(code).to_contain_text('llm.requestCompatibility.researchToolCalls.enabled=false');capture('default')
  research.check();expect(compat).to_be_visible();expect(compat).not_to_be_checked();expect(code).to_contain_text('llm.requestCompatibility.researchToolCalls.enabled=false');capture('research-default')
  compat.check();expect(code).to_contain_text('llm.requestCompatibility.researchToolCalls.enabled=true');expect(code).to_contain_text('llm.requestCompatibility.enabled=true');assert 'auditEnabled=true' not in code.inner_text();capture('research-opt-in')
  research.uncheck();expect(compat).to_be_hidden();expect(code).to_contain_text('llm.requestCompatibility.researchToolCalls.enabled=false');capture('research-disabled')
 finally:
  (ROOT/'observations.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n');browser.close()
print(json.dumps({'cases':len(records),'allPassed':True}))
