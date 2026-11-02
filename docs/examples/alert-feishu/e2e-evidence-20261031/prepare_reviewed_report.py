#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Keep the full model report, full editorial diff and full reviewed unsigned payload."""
import difflib,hashlib,importlib.util,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
raw=(ROOT/'review-api/model-corrected-report.zh-CN.txt').read_text()
s=json.loads((ROOT/'review-api/summary.json').read_text());tools=json.loads((ROOT/'native/tool-index.json').read_text())
report=raw
replacements={
 '**会话密钥**: ed4679e0-f8b4-494c-852e-f63d2f9b76ab':'**会话 ID**: ed4679e0-f8b4-494c-852e-f63d2f9b76ab  \n**sessionKey**: agent:default:alert-alertmanager-1bdae10de10f472e',
 '| 告警 UID | 82953a81-6578-4cbe-b638-ef3de927279a | 此 UID 为 Pod UID，非告警 UID。告警唯一标识为指纹 1bdae10de10f472e |':'| 来源标签 uid（Pod UID） | 82953a81-6578-4cbe-b638-ef3de927279a | 告警对象 ID 为 alertmanager:1bdae10de10f472e，fingerprint 为 1bdae10de10f472e |',
 '多次重启循环（restartCount=5），每次退出码均为 23':'观测到重启计数为5；已抓到的终止记录退出码为23',
 '调查会话密钥':'调查sessionKey',
 '修复会话密钥':'修复sessionKey',
 'READY_FILE_MISSING':'REQUIRED_FILE_MISSING',
 '| iraop_query | 仅检索 PDF 通用指令，不要求诊断当前 Pod | 成功，退出码 0 |':'| iraop_query | 最后一次限定检索PDF通用指令，前两次结果及错误保留 | MCP isError=false，各返回2个来源；此处不是操作系统退出码 |',
 '## 七、工具调用记录':'## 七、模型整理的工具类型摘要（完整逐次索引附后）',
 '未执行任何写操作，未更改模式，未执行 Feishu 投递。':'调查agent未执行写操作、未更改模式，也未自行投递飞书；隔离资源由已授权运维脚本创建，本完整审核报告由操作员通过群机器人发送。',
}
for before,after in replacements.items():
 assert before in report,before;report=report.replace(before,after)
report='''操作员审核说明：本报告保留完整模型修正版，并纠正标识/术语；原始两轮调查、3次IRAOP响应、18次工具结果和完整修改diff均保留在证据附件。知识库中旧示例不等于当前现场；前两次研究有来源但含事实误归因，经人工复核纠正。\n\n自动完成：指标采集、规则评估、Alertmanager接收、MOSAIC轮询；点击本告警Start Investigating后，agent自动采集并咨询IRAOP。人工完成：测试资源创建、单条调查触发、补充取证/事实审核、调用群机器人发送。当前未部署无人值守的完整自动发布流程。\n\n'''+report
report+='\n\n## 实际逐次工具索引（18条均保留）\n\n| # | toolName | toolCallId | isError |\n| --- | --- | --- | --- |\n'
for i,row in enumerate(tools,1):report+='| '+str(i)+' | '+row['toolName']+' | '+row['toolCallId']+' | '+str(row['isError']).lower()+' |\n'
report+='\n每一条的完整参数、原始输出、请求/结果时间及3次完整知识回答均在文档PR的证据附件；未用模型摘要替代原件。部分超大MCP details由OpenClaw持久化层缩为元数据，完整可见content仍保留，此限制另行记录。\n'
(ROOT/'analysis-reviewed.internal.zh-CN.txt').write_text(report)
(ROOT/'analysis-review.full.diff').write_text(''.join(difflib.unified_diff(raw.splitlines(True),report.splitlines(True),fromfile='model-original',tofile='operator-reviewed')))
meta={'modelReportBytes':len(raw.encode()),'modelReportSha256':hashlib.sha256(raw.encode()).hexdigest(),'reviewedReportBytes':len(report.encode()),'reviewedReportSha256':hashlib.sha256(report.encode()).hexdigest(),'fullDiff':'analysis-review.full.diff','allToolRows':len(tools),'operatorReview':True}
(ROOT/'analysis-review-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
# This is a redacted copy for message delivery; complete private originals remain.
redactions={'target-node-1.example.invalid':'target-node-1.example.invalid','target-node-2.example.invalid':'target-node-2.example.invalid','continued-private-address-08.example.invalid':'metrics-pod.example.invalid','continued-private-address-07.example.invalid':'test-pod.example.invalid','target-node-1':'target-node-1','target-node-1':'target-node-1','target-node-2':'target-node-2','target-lab':'target-lab'}
def redact(text):
 for before,after in redactions.items():text=text.replace(before,after)
 return text
out=redact(report);(ROOT/'analysis-reviewed.zh-CN.txt').write_text(out)
a=json.loads((ROOT/'browser/new-alert-before-investigation.json').read_text());a=json.loads(redact(json.dumps(a,ensure_ascii=False)))
(ROOT/'feishu-alert-reviewed.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('sender','/private/tmp/afoa-spark-alert-runbook-20261030/docs/examples/alert-feishu/send_feishu_report.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
payload=m.make_payload(a,out,s['sessionKey'],ROOT.name,'https://github.com/JeffPengCoder/AI-Factory-Operations-Agent/pull/1')
encoded=m.encode_payload(payload)
(ROOT/'feishu-payload-reviewed.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
meta={'runId':ROOT.name,'researchSessionKey':s['sessionKey'],'group':'MOSAIC Alert Test','payloadBytesBeforeSigning':len(encoded),'payloadSha256':hashlib.sha256(encoded).hexdigest(),'status':'prepared-not-sent','credentialValuesSaved':False,'fullReportNotTruncated':True,'allToolIndexRows':len(tools)}
(ROOT/'feishu-report-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta))
