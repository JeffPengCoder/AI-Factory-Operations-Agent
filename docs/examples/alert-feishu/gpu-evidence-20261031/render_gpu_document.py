#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Render every source table row to a standalone Chinese PDF, never a summary."""
import hashlib,json
from pathlib import Path
from markdown_it import MarkdownIt
from weasyprint import HTML
from bs4 import BeautifulSoup
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parent
DOCS=Path('/private/tmp/afoa-spark-alert-runbook-20261030/docs')
source=DOCS/'spark_gpu_alert_research_feishu_20261031.zh-CN.md'
OUT=Path('/Users/operator/workspace/system-sa/aiops/output/pdf');OUT.mkdir(parents=True,exist_ok=True)
md=MarkdownIt('commonmark',{'html':True}).enable('table')
body=md.render(source.read_text());soup=BeautifulSoup(body,'html.parser')
tables=soup.find_all('table');rows=sum(len(t.find_all('tr'))-1 for t in tables)
for a in soup.find_all('a',href=True):
 if not a['href'].startswith(('http:','https:','#')):a['href']='https://github.com/JeffPengCoder/AI-Factory-Operations-Agent/blob/docs/spark-alert-feishu-runbook/docs/'+a['href']
for img in soup.find_all('img',src=True):
 img['src']=str(DOCS/img['src'])
style='''@page {size:A4; margin:17mm 15mm 18mm; @bottom-left{content:"Jeff Peng · GPU experiment · evidence record";font-size:8pt;color:#777} @bottom-right{content:counter(page);font-size:8pt;color:#777}}
body{font-family:"PingFang SC",Arial,sans-serif;font-size:9.6pt;line-height:1.5;color:#172432}
h1{font-size:21pt;line-height:1.3;color:#345700;margin:0 0 12pt}h2{font-size:15pt;line-height:1.3;margin:20pt 0 9pt;color:#345700;break-after:avoid}h3{font-size:12pt;margin:15pt 0 7pt;break-after:avoid}h4{font-size:10pt;margin:12pt 0 5pt;break-after:avoid}
p{margin:6pt 0 9pt}a{color:#376000;text-decoration:none;overflow-wrap:anywhere}img{width:100%;height:auto}table{border-collapse:collapse;table-layout:fixed;width:100%;font-size:7.3pt;line-height:1.35;margin:10pt 0 14pt}thead{display:table-header-group}tr{break-inside:avoid}th,td{border:0.5pt solid #cbd3d9;padding:4pt;vertical-align:top;overflow-wrap:anywhere;word-break:break-all}th{background:#e8f1da;color:#203b00;font-weight:600}tbody tr:nth-child(even){background:#f6f8fa}pre{background:#f4f6f8;border-left:2pt solid #78a530;padding:8pt;font-family:Menlo,monospace;font-size:7.2pt;line-height:1.4;white-space:pre-wrap;overflow-wrap:anywhere}code{font-family:Menlo,monospace;font-size:0.9em;overflow-wrap:anywhere}strong{font-weight:600}'''
html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>GPU实验与无人值守归因验收</title><style>'+style+'</style><body>'+str(soup)+'</body></html>'
path=OUT/'spark-gpu-validation-20261031-external.html';path.write_text(html)
pdf=OUT/'spark-gpu-validation-20261031-external.pdf';HTML(string=html,base_url=str(DOCS)).write_pdf(pdf)
reader=PdfReader(pdf)
assert '无人值守' in ''.join(p.extract_text() for p in reader.pages)
result={'source':str(source),'tables':len(tables),'dataRows':rows,'pages':len(reader.pages),'pdfBytes':pdf.stat().st_size,'pdfSha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'allTablesRendered':True,'sourceReduced':False}
(ROOT/'gpu-document-render.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
