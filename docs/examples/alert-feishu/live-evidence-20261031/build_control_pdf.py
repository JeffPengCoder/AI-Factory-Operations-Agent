#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Two-page authored control corpus; verification marker is not a credential."""
import hashlib
import json
from pathlib import Path
import secrets

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from pypdf import PdfReader

root = Path(__file__).resolve().parent
oracle = root/'control-oracle.json'
if oracle.exists():
    marker = json.loads(oracle.read_text())['verificationCode']
else:
    marker = 'CEDAR-NEBULA-'+secrets.token_hex(4).upper()
pages = [
    [
        'MOSAIC Validation Runbook',
        'Reference: MOSAIC-KB-20261031',
        'This authored document is a control corpus for the Spark validation run.',
        'A vector(1) alert is a deliberate delivery-path test. It does not show a GPU, driver or application fault. Verify the Prometheus state, Alertmanager fingerprint and the same MOSAIC alert before interpreting it.',
        'An alert injected directly through the Alertmanager API bypasses Prometheus rule evaluation. Missing Prometheus ALERTS samples for that injected run ID are expected. Do not claim a new PrometheusRule was evaluated.',
        'For an isolated user-level repair demo, the named service fails when its ready marker is absent. Read the exact service state and logs before repair. Repair only the registered demo wrapper; verify the marker and service result afterward.',
    ],
    [
        'Operator Decision and Evidence',
        'Reference: MOSAIC-KB-20261031 - page 2',
        'Public verification code: '+marker,
        'The verification code is an oracle for this retrieval test and grants no access. An answer must cite this source file and page 2 when reporting the code.',
        'View mode must block the repair operation. Edit mode with HITL enabled must await a specific approval. Refusal or expiration must leave the failed service unchanged. Auto mode executes the same authorized demo repair without per-operation approval.',
        'Automatic alert investigations remain read-only. Use a separate authorized interactive repair conversation, preserving the alert ID, investigation session key, research sources and repair session key.',
        'Completion evidence includes exact tool arguments, toolCallId, exit status, full service state before and after, logs, and an independently observed restored condition. Documentation advice alone does not establish the root cause or a completed repair.',
    ],
]
styles = getSampleStyleSheet()
styles['BodyText'].fontName = 'Helvetica'
styles['BodyText'].fontSize = 11
styles['BodyText'].leading = 16
story=[]
for i,parts in enumerate(pages):
    if i: story.append(PageBreak())
    story.append(Paragraph(parts[0],styles['Title']))
    story.append(Spacer(1,0.2*inch))
    for text in parts[1:]:
        story.append(Paragraph(text,styles['BodyText']))
        story.append(Spacer(1,0.16*inch))
def footer(canvas,doc):
    canvas.setFont('Helvetica',9)
    canvas.setFillColor(colors.grey)
    canvas.drawString(0.7*inch,0.45*inch,'MOSAIC authored validation corpus | test from Jeff Peng')
    canvas.drawRightString(7.5*inch,0.45*inch,str(doc.page))
pdf=root/'mosaic-validation-control.pdf'
SimpleDocTemplate(str(pdf),leftMargin=0.7*inch,rightMargin=0.7*inch,topMargin=0.7*inch,bottomMargin=0.8*inch).build(story,onFirstPage=footer,onLaterPages=footer)
reader=PdfReader(pdf)
assert len(reader.pages)==2
assert marker in reader.pages[1].extract_text()
(root/'control-source.json').write_text(json.dumps(pages,indent=2)+'\n')
oracle.write_text(json.dumps({'reference':'MOSAIC-KB-20261031','verificationCode':marker,'expectedPage':2,'pdf':pdf.name,'pages':2,'bytes':pdf.stat().st_size,'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()},indent=2)+'\n')
print(oracle.read_text())
