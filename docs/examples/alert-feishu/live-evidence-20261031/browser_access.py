#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Private browser smoke check; no auth headers/cookies are recorded."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from probe_access import BASE, ROOT, read_ui_credentials


CHROME = "/Users/operator/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"


def main():
    label = sys.argv[1] if len(sys.argv)>1 else "browser-initial"
    credentials = read_ui_credentials()
    result = {"startedAt": datetime.now(timezone.utc).isoformat(), "responses": [], "blockedInvestigationSubmissions": 0}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROME)
        context = browser.new_context(http_credentials=credentials, viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        def block_auto(route):
            result["blockedInvestigationSubmissions"] += 1
            route.abort()

        # Access testing must not initiate investigations for unrelated alerts.
        page.route("**/api/openclaw/chat/stream", block_auto)
        page.on("response", lambda r: result["responses"].append({"path": urlparse(r.url).path, "status": r.status}))
        response = page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        result["navigationStatus"] = response.status if response else None
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
            result["networkIdle"] = True
        except PlaywrightTimeout:
            result["networkIdle"] = False
        page.locator("body").wait_for(state="visible")
        result["url"] = page.url
        result["title"] = page.title()
        result["buttons"] = page.get_by_role("button").all_text_contents()
        result["inputs"] = page.locator("input").evaluate_all("els => els.map(e => ({type:e.type,name:e.name,placeholder:e.placeholder}))")
        (ROOT / (label+".html")).write_text(page.content())
        (ROOT / (label+".txt")).write_text(page.locator("body").inner_text())
        page.screenshot(path=str(ROOT / (label+".png")), full_page=True)
        result["finishedAt"] = datetime.now(timezone.utc).isoformat()
        (ROOT / (label+".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        print(json.dumps({k: result[k] for k in ["navigationStatus", "title", "url", "buttons", "inputs", "blockedInvestigationSubmissions"]}, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
