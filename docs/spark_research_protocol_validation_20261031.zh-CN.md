<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Spark Research 实测续篇：工具调用协议修复与原生检索证据

**后续更新：** [最新补测与交接状态](spark_research_feishu_followup_20261031.zh-CN.md)已核验全部4条实际向量、上传自动入库及其原件下载404缺口，并完成飞书真实收件；运行修复已提交[NVIDIA PR #86](https://github.com/NVIDIA/AI-Factory-Operations-Agent/pull/86)，Tests/build成功。本文保留此前235份完整证据和当时快照，下面“飞书待创建”等措辞指原记录时点。

核验日期：2026-10-31。**当前部署为 Helm revision 15，Research 兼容开关开启，临时请求追踪已关闭。原生 HTTP、MCP 和三次 MOSAIC View 查询均从控制 PDF 取得正确测试码和来源；最后一次携带实际测试告警上下文。** 这是控制文档的检索验收，不是业务知识库、任意问题或生产修复能力的质量认证。飞书真实投递仍待客户创建测试群及自定义机器人。

本篇接续[revision12 追加记录](spark_live_validation_20261031_followup.zh-CN.md)和[最初完整实测](spark_live_validation_20261031.zh-CN.md)。旧失败结果和原始记录全部保留，本篇新增后续证据，不把旧快照改写成成功。

## 1. 还需要谁做什么

1. **客户在飞书建测试群、添加自定义机器人**，开启签名校验，通过凭据库或受保护文件授权发送者使用 Webhook/签名密钥。随后发送完整告警与经审核的研究报告，并到群里核对同一 run ID。当前无真实收件记录，创建机器人不会自动开启报告转发，见[操作手册第7章](spark_alert_feishu_runbook.zh-CN.md#7-将告警与分析发到飞书)。
2. **知识库负责人提供获准的业务 PDF 和检查问题/页码**。目前只有1个控制PDF、4个chunks；本轮通过说明搜索执行、来源传递和页面答案链路可用，不能证明业务故障归因正确。无命中、错误引用、超时以及更复杂的 deep research 仍需扩大验收。
3. **监控/集群管理员处理现有权限缺口**：Alertmanager 新 POST 仍是此前的403，PrometheusRule读取仍有RBAC限制。本轮使用保留的合成告警，没有新建规则、注入GPU错误或绕过管理员授权。
4. **接手人取得自己的访问授权与当前制品位置**。不能复用原操作者电脑上的临时隧道或假定能读Kubernetes Secret。需要真实定制chart、values/备份的内部访问方式、SSH/UI凭据取用授权及维护人，见[完整交接清单](spark_alert_feishu_runbook.zh-CN.md#交付者需要另行交给接手人的资料)。
5. **页面子代理事件、恢复范围继续跟进**：本轮CDP EventSource和fetch SSE未捕获到对应事件，不能声称已独立验证事件POST。真实HTTP/SSE测试覆盖发送契约；主机重启、Kind重建、PVC恢复、部署回滚和生产服务修复仍未验收。

## 2. 问题在哪里，修复做了什么

之前的IRAOP agent拿到了工具列表，但把“我要搜索”、伪工具文字或查询JSON当普通回答返回，没有实际运行OpenSearch。本轮首先复现：只指定named tool，或再关闭thinking，仍不产生tool_calls。原生HTTP200不等于搜索执行。

现场实际vLLM为`0.21.0+2325b6f0.dev`。通过导入已安装类读回：`Qwen3CoderToolParser.supports_required_and_named=false`，`Qwen3XMLToolParser=true`。现场使用前者；当前服务的named分支依赖该标记，非流式路径可能只返回空tool_calls，流式路径把真正的query参数放在content。这里确认的是该现场的协议行为。模型在auto规划阶段也可能提前停止，不能断言只换parser就修复所有agent行为。

模型卡的[Spark示例](https://huggingface.co/nvidia/Qwen3.6-35B-A3B-NVFP4)使用`qwen3_xml`；[vLLM工具调用文档](https://docs.vllm.ai/en/v0.21.0/features/tool_calling/)说明named/required调用机制。现场原始配置与已安装源码/类标记证据分别保留，不用最新文档替代实际运行版本。

实际类标记完整读回：
```text
{"vllmVersion": "0.21.0+2325b6f0.dev", "Qwen3CoderToolParser.supports_required_and_named": false, "Qwen3XMLToolParser.supports_required_and_named": true}

```

资源读回（完整字段，GPU memory查询不可用也原样保留）：

```json
{
  "at": "2026-10-31T06:07:50.892205+00:00",
  "commands": [
    {
      "argv": [
        "free",
        "-b"
      ],
      "exitCode": 0,
      "stdout": "               total        used        free      shared  buff/cache   available\nMem:     130662936576 103932764160  1577533440  4469739520 30542974976 26730172416\nSwap:    17179865088   144674816 17035190272\n",
      "stderr": ""
    },
    {
      "argv": [
        "df",
        "-B1",
        "/home/spark-user"
      ],
      "exitCode": 0,
      "stdout": "Filesystem         1B-blocks         Used     Available Use% Mounted on\n/dev/nvme0n1p2 4031871553536 131791917056 3695238787072   4% /\n",
      "stderr": ""
    }
  ]
}
```

没有启动第二个GPU模型，也没有重启或修改共享`nemoclaw-vllm`。原服务启动命令含未固定版本的pip install；直接重启可能同时改变依赖。现有LLM兼容代理扩展了一个**默认关闭**的选项：

```yaml
llm:
  requestCompatibility:
    enabled: true
    researchToolCalls:
      enabled: false
      auditEnabled: false
```

开启后，只对带`task`和query-only `opensearch_search` schema的初始研究请求选择该只读搜索，关闭这一轮thinking，并要求完整JSON参数。若上游已返回合法tool call，保留；若整个content恰好是合法的`{"query":"..."}`，只补上named tool envelope，交给原agent执行真正的OpenSearch。不会捏造检索结果或答案，不从任意散文里抽取JSON。缺失DONE、截断、超限、错误工具或参数不合法时失败；collection范围仍由IRAOP控制。

显式选择其他工具、工具结果后的综合回答、无task的子代理和不相关OpenClaw请求保留原行为。默认配置仍只保留原有reasoning_effort=none处理。部署没有增加GPU实例或集群编辑权限。

修复及完整源码在[代码PR#2](https://github.com/JeffPengCoder/AI-Factory-Operations-Agent/pull/2)，新增提交`c3a2048`，尚未合并到main。源码/测试/安装说明的完整base-relative补丁见

[code-pr-complete.diff](examples/alert-feishu/protocol-evidence-20261031/code-pr-complete.diff)。生成的agent文档包也随PR更新；其检查结果见后文。

## 3. 所有完整agent对照

以下八个agent运行均先独立查询真实索引，保留全部命中、原文和分数；表中每一行是一次完整运行。前3行只改变首轮选择策略，第二组验证最小协议归一化，第三组验证实际Node候选服务；这些隔离实验本身不等于原生服务部署验收。

| case | modelMode | seed | 秒 | 消息数 | 全部toolEvents | sourceSink数 | sources数 | 原文 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-cases/baseline-seeded | baseline-seeded | 101 | 3.8851402080617845 | 2 | [] | 0 | 0 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/agent-cases/baseline-seeded/agent-state.json) |
| agent-cases/force-search-first | force-search-first | 101 | 1.6392981898970902 | 2 | [] | 0 | 0 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first/agent-state.json) |
| agent-cases/force-search-first-no-thinking | force-search-first-no-thinking | 101 | 0.6446090820245445 | 2 | [] | 0 | 0 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first-no-thinking/agent-state.json) |
| normalization/baseline | baseline-seeded | 101 | 1.9678172781132162 | 2 | [] | 0 | 0 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/normalization/baseline/agent-state.json) |
| normalization/normalized-101 | normalize-first-search | 101 | 5.990955532062799 | 4 | [{"event": "on_tool_start", "name": "opensearch_search"}, {"event": "on_tool_end", "name": "opensearch_search"}] | 3 | 2 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-101/agent-state.json) |
| normalization/normalized-202 | normalize-first-search | 202 | 3.371415846981108 | 4 | [{"event": "on_tool_start", "name": "opensearch_search"}, {"event": "on_tool_end", "name": "opensearch_search"}] | 3 | 2 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-202/agent-state.json) |
| node-candidate/seed101 | node-candidate | 101 | 6.0805488880723715 | 4 | [{"event": "on_tool_start", "name": "opensearch_search"}, {"event": "on_tool_end", "name": "opensearch_search"}] | 3 | 2 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed101/agent-state.json) |
| node-candidate/seed202 | node-candidate | 202 | 4.627059806138277 | 4 | [{"event": "on_tool_start", "name": "opensearch_search"}, {"event": "on_tool_end", "name": "opensearch_search"}] | 3 | 2 | [全部状态/消息](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed202/agent-state.json) |


### agent-cases/baseline-seeded：完整返回答案

```text
I'll search for the document in the indexed knowledge base and retrieve the specific information you need.

```json
{
  "action": "tool_call",
  "name": "task",
  "arguments": {
    "prompt": "I need to find information from the indexed document \"mosaic-validation-control.pdf\" with reference \"MOSAIC-KB-20261031\". Please search the knowledge base thoroughly and return:\n\n1. The exact filename of the document as it appears in the index\n2. On page 2, locate the \"Operator Decision and Evidence\" section\n3. Find the \"public verification code\" that is printed in that section on page 2\n4. Confirm that this document is referenced as \"MOSAIC-KB-20261031\"\n5. Look for any information about whether an automated alert investigation may directly repair a service\n\nPlease return ALL findings with exact text quotes, including the verification code value, section headings, and any text about automated alert investigations and service repairs.",
    "subagent_type": "research-agent"
  }
}
```
```

全部结果字段：[agent-cases/baseline-seeded/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/baseline-seeded/trace-summary.json)；全部命中/内容/分数：[agent-cases/baseline-seeded/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/baseline-seeded/direct-hybrid-search.json)；时间、问题、包版本：[agent-cases/baseline-seeded/metadata.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/baseline-seeded/metadata.json)。


### agent-cases/force-search-first：完整返回答案

```text
{
  "query": "mosaic-validation-control.pdf"
}
```

全部结果字段：[agent-cases/force-search-first/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first/trace-summary.json)；全部命中/内容/分数：[agent-cases/force-search-first/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first/direct-hybrid-search.json)；时间、问题、包版本：[agent-cases/force-search-first/metadata.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first/metadata.json)。


### agent-cases/force-search-first-no-thinking：完整返回答案

```text
{
  "query": "MOSAIC-KB-20261031 public verification code Operator Decision and Evidence page 2"
}
```

全部结果字段：[agent-cases/force-search-first-no-thinking/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first-no-thinking/trace-summary.json)；全部命中/内容/分数：[agent-cases/force-search-first-no-thinking/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first-no-thinking/direct-hybrid-search.json)；时间、问题、包版本：[agent-cases/force-search-first-no-thinking/metadata.json](examples/alert-feishu/protocol-evidence-20261031/agent-cases/force-search-first-no-thinking/metadata.json)。


### normalization/baseline：完整返回答案

```text
I'll search for the referenced document and perform the analysis.

<think>- Let me search for the file first.
</think>
```

全部结果字段：[normalization/baseline/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/normalization/baseline/trace-summary.json)；全部命中/内容/分数：[normalization/baseline/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/normalization/baseline/direct-hybrid-search.json)；时间、问题、包版本：[normalization/baseline/metadata.json](examples/alert-feishu/protocol-evidence-20261031/normalization/baseline/metadata.json)。


### normalization/normalized-101：完整返回答案

```text
## Results

### Public Verification Code

**Citation:** `mosaic-validation-control.pdf`, page 2

**Code:** `CEDAR-NEBULA-E720C8C9`

This is explicitly printed under the **Operator Decision and Evidence** section on page 2, referenced against **MOSAIC-KB-20261031**.

---

### Can an Automated Alert Investigation Directly Repair a Service?

**No.** Per the document:

> *"Automatic alert investigations remain read-only."*

The indexed text makes a clear separation between investigation and repair:

1. **Alert investigation** — read-only. An automated alert investigation can gather evidence, review Prometheus state, Alertmanager fingerprints, logs, and service state, but it cannot alter anything.

2. **Repair** — requires a *separate authorized interactive repair conversation*. The document instructs:

   > *"Use a separate authorized interactive repair conversation, preserving the alert ID, investigation session key, research sources and repair session key."*

3. **Access mode gating** — different modes behave differently:
   - **View mode** must block the repair operation entirely.
   - **Edit mode** with Human-in-the-Loop (HITL) enabled must await specific approval.
   - **Auto mode** executes the same authorized demo repair *without per-operation approval*, but this still operates in a separate context from the read-only investigation.

4. **Completion evidence** — any repair must be documented with exact tool arguments, `toolCallId`, exit status, full service state before and after, logs, and an independently observed restored condition.

In short: an automated alert investigation is strictly read-only. A separate, authorized repair session (subject to the mode's approval gating) is required to actually repair a service.
```

全部结果字段：[normalization/normalized-101/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-101/trace-summary.json)；全部命中/内容/分数：[normalization/normalized-101/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-101/direct-hybrid-search.json)；时间、问题、包版本：[normalization/normalized-101/metadata.json](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-101/metadata.json)。


### normalization/normalized-202：完整返回答案

```text
## Answer

### Public Verification Code

The public verification code printed in the **Operator Decision and Evidence** section on **page 2** of the indexed document is:

> **CEDAR-NEBULA-E720C8C9**

**Source citation:** `mosaic-validation-control.pdf`, page 2, indexed under the collection *mosaic-validation-20261031*, referencing MOSAIC-KB-20261031.

### Can an Automated Alert Investigation Directly Repair a Service?

**No — automated alert investigations are read-only and cannot directly repair a service.** 

Per the same document (page 2), the text states explicitly:

> *"Automatic alert investigations remain read-only."*

Instead, a separate **authorized interactive repair conversation** must be used, which preserves:
- the alert ID
- the investigation session key
- research sources
- the repair session key

Completion evidence requires exact tool arguments, `toolCallId`, exit status, full service state before and after, logs, and an independently observed restored condition.
```

全部结果字段：[normalization/normalized-202/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-202/trace-summary.json)；全部命中/内容/分数：[normalization/normalized-202/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-202/direct-hybrid-search.json)；时间、问题、包版本：[normalization/normalized-202/metadata.json](examples/alert-feishu/protocol-evidence-20261031/normalization/normalized-202/metadata.json)。


### node-candidate/seed101：完整返回答案

```text
## Answer

Based on the indexed document **mosaic-validation-control.pdf**, here is the evidence:

### 1. Public Verification Code

**Filename:** `mosaic-validation-control.pdf`  
**Page:** 2

The public verification code printed in the **Operator Decision and Evidence** section on page 2 is:

> **CEDAR-NEBULA-E720C8C9**

Exact text from the document:

> "Public verification code: CEDAR-NEBULA-E720C8C9"

### 2. Can an Automated Alert Investigation Directly Repair a Service?

**No.** An automated alert investigation **may not** directly repair a service. The document on page 2 of `mosaic-validation-control.pdf` explicitly states:

> "Automatic alert investigations remain read-only. Use a separate authorized interactive repair conversation, preserving the alert ID, investigation session key, research sources and repair session key."

**Explanation:**

- Automated alert investigations are **read-only by design**. They can gather evidence, analyze root causes, and investigate the condition of services — but they cannot execute repair actions.
- To actually repair a service, a **separate authorized interactive repair conversation** must be initiated. This separate session must preserve:
  - The alert ID
  - The investigation session key
  - Research sources
  - The repair session key
- Completion evidence for a repair requires tool arguments, `toolCallId`, exit status, full service state before and after, logs, and an independently observed restored condition — which further confirms that repair is a distinct, separate operation from automated investigation.

This separation enforces a critical operational safety boundary: automation investigates, humans (or authorized interactive sessions) authorize and execute repairs.
```

全部结果字段：[node-candidate/seed101/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed101/trace-summary.json)；全部命中/内容/分数：[node-candidate/seed101/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed101/direct-hybrid-search.json)；时间、问题、包版本：[node-candidate/seed101/metadata.json](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed101/metadata.json)。


### node-candidate/seed202：完整返回答案

```text
## Results

**Public Verification Code (Page 2):** `CEDAR-NEBULA-E720C8C9`

Citation: `mosaic-validation-control.pdf`, page 2, under the heading **Operator Decision and Evidence**, referencing `MOSAIC-KB-20261031`.

---

**Can an automated alert investigation directly repair a service? No.**

The document explicitly states on page 2:

> *"Automatic alert investigations remain read-only. Use a separate authorized interactive repair conversation, preserving the alert ID, investigation session key, research sources and repair session key."*

This means an automated alert investigation **cannot** directly repair a service. It is constrained to read-only operations. Any repair must occur through a separate, authorized interactive repair conversation. The document further specifies that the completion evidence for any repair must include exact tool arguments, `toolCallId`, exit status, full service state before and after, logs, and an independently observed restored condition.
```

全部结果字段：[node-candidate/seed202/trace-summary.json](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed202/trace-summary.json)；全部命中/内容/分数：[node-candidate/seed202/direct-hybrid-search.json](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed202/direct-hybrid-search.json)；时间、问题、包版本：[node-candidate/seed202/metadata.json](examples/alert-feishu/protocol-evidence-20261031/node-candidate/seed202/metadata.json)。

两次Python归一化、两次Node候选都实际执行opensearch_search，分别有3个记录命中、2个去重来源；模型问题中均未包含oracle。候选端口18082仅用于先行测试，持久部署使用既有Service端口8000。候选原始审计已在Pod替换前导出。

## 4. 六组named请求的全部原始返回

这是协议诊断，没有在这些重放里执行模型生成的工具。所有请求确实携带named opensearch_search，完整原请求及私有系统提示留在内部包。以下各case公开完整结果和原始响应字节；没有把空tool_calls或JSON文字当搜索成功。


### compat-nonstream

```json
{
  "case": "compat-nonstream",
  "url": "http://llm-openai-compat:8000/v1",
  "stream": false,
  "httpStatus": 200,
  "contentType": "application/json",
  "elapsedSeconds": 0.6330956341698766,
  "fullResponse": {
    "id": "chatcmpl-91b1847900ae8074",
    "object": "chat.completion",
    "created": 1793425625,
    "prompt_routed_experts": null,
    "model": "nvidia/Qwen3.6-35B-A3B-NVFP4",
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": "",
          "refusal": null,
          "annotations": null,
          "audio": null,
          "function_call": null,
          "tool_calls": [],
          "reasoning": null
        },
        "logprobs": null,
        "finish_reason": "stop",
        "stop_reason": null,
        "token_ids": null,
        "routed_experts": null
      }
    ],
    "service_tier": null,
    "system_fingerprint": "vllm-0.21.0+2325b6f0.dev-9f46b229",
    "usage": {
      "prompt_tokens": 7893,
      "total_tokens": 7928,
      "completion_tokens": 35,
      "prompt_tokens_details": null
    },
    "prompt_logprobs": null,
    "prompt_token_ids": null,
    "prompt_text": null,
    "kv_transfer_params": null
  }
}
```

逐字响应：[named-wire/compat-nonstream-response.raw](examples/alert-feishu/protocol-evidence-20261031/named-wire/compat-nonstream-response.raw)。


### compat-stream

```json
{
  "case": "compat-stream",
  "url": "http://llm-openai-compat:8000/v1",
  "stream": true,
  "httpStatus": 200,
  "contentType": "text/event-stream; charset=utf-8",
  "elapsedSeconds": 0.6905068033374846,
  "fullContent": "{\n  \"query\": \"MOSAIC-KB-20261031 public verification code Operator Decision Evidence section page 2\"\n}",
  "allToolCallDeltas": [],
  "finishReasons": [
    "stop"
  ]
}
```

逐字响应：[named-wire/compat-stream-response.raw](examples/alert-feishu/protocol-evidence-20261031/named-wire/compat-stream-response.raw)。


### direct-nonstream

```json
{
  "case": "direct-nonstream",
  "url": "http://spark-kind-bridge.example.invalid:8000/v1",
  "stream": false,
  "httpStatus": 200,
  "contentType": "application/json",
  "elapsedSeconds": 0.6965185720473528,
  "fullResponse": {
    "id": "chatcmpl-a29f473a64fa73b2",
    "object": "chat.completion",
    "created": 1793425627,
    "prompt_routed_experts": null,
    "model": "nvidia/Qwen3.6-35B-A3B-NVFP4",
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": "",
          "refusal": null,
          "annotations": null,
          "audio": null,
          "function_call": null,
          "tool_calls": [],
          "reasoning": null
        },
        "logprobs": null,
        "finish_reason": "stop",
        "stop_reason": null,
        "token_ids": null,
        "routed_experts": null
      }
    ],
    "service_tier": null,
    "system_fingerprint": "vllm-0.21.0+2325b6f0.dev-9f46b229",
    "usage": {
      "prompt_tokens": 7893,
      "total_tokens": 7932,
      "completion_tokens": 39,
      "prompt_tokens_details": null
    },
    "prompt_logprobs": null,
    "prompt_token_ids": null,
    "prompt_text": null,
    "kv_transfer_params": null
  }
}
```

逐字响应：[named-wire/direct-nonstream-response.raw](examples/alert-feishu/protocol-evidence-20261031/named-wire/direct-nonstream-response.raw)。


### direct-stream

```json
{
  "case": "direct-stream",
  "url": "http://spark-kind-bridge.example.invalid:8000/v1",
  "stream": true,
  "httpStatus": 200,
  "contentType": "text/event-stream; charset=utf-8",
  "elapsedSeconds": 0.6698545948602259,
  "fullContent": "{\n  \"query\": \"MOSAIC-KB-20261031 public verification code Operator Decision Evidence section page 2\"\n}",
  "allToolCallDeltas": [],
  "finishReasons": [
    "stop"
  ]
}
```

逐字响应：[named-wire/direct-stream-response.raw](examples/alert-feishu/protocol-evidence-20261031/named-wire/direct-stream-response.raw)。


### direct-default-thinking-nonstream

```json
{
  "case": "direct-default-thinking-nonstream",
  "url": "http://spark-kind-bridge.example.invalid:8000/v1",
  "stream": false,
  "httpStatus": 200,
  "contentType": "application/json",
  "elapsedSeconds": 1.6729872319847345,
  "fullResponse": {
    "id": "chatcmpl-9ddac745ef6e2f88",
    "object": "chat.completion",
    "created": 1793425798,
    "prompt_routed_experts": null,
    "model": "nvidia/Qwen3.6-35B-A3B-NVFP4",
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": "",
          "refusal": null,
          "annotations": null,
          "audio": null,
          "function_call": null,
          "tool_calls": [],
          "reasoning": "The user is asking me to:\n1. Find a PDF file called \"mosaic-validation-control.pdf\" from indexed documents\n2. Reference MOSAIC-KB-20261031\n3. Find the public verification code in the Operator Decision and Evidence section on page 2\n4. Cite the exact filename and page inline\n5. Explain whether an automated alert investigation may directly repair a service\n6. Perform the document search and return evidence\n\nLet me start by searching for the PDF file and reading it.\n"
        },
        "logprobs": null,
        "finish_reason": "stop",
        "stop_reason": null,
        "token_ids": null,
        "routed_experts": null
      }
    ],
    "service_tier": null,
    "system_fingerprint": "vllm-0.21.0+2325b6f0.dev-9f46b229",
    "usage": {
      "prompt_tokens": 7891,
      "total_tokens": 8038,
      "completion_tokens": 147,
      "prompt_tokens_details": null
    },
    "prompt_logprobs": null,
    "prompt_token_ids": null,
    "prompt_text": null,
    "kv_transfer_params": null
  }
}
```

逐字响应：[named-wire-thinking/direct-default-thinking-nonstream-response.raw](examples/alert-feishu/protocol-evidence-20261031/named-wire-thinking/direct-default-thinking-nonstream-response.raw)。


### direct-default-thinking-stream

```json
{
  "case": "direct-default-thinking-stream",
  "url": "http://spark-kind-bridge.example.invalid:8000/v1",
  "stream": true,
  "httpStatus": 200,
  "contentType": "text/event-stream; charset=utf-8",
  "elapsedSeconds": 3.39587530400604,
  "fullContent": "\n\nI'll search for the referenced PDF document and examine the specific section you mentioned.\n\n`write_todos`:\n```\n- Search for and locate mosaic-validation-control.pdf\n- Read page 2, Operator Decision and Evidence section\n- Identify the public verification code\n- Address the automated alert investigation question\n- Compile evidence with citations\n```\n</think>\n\n{\"tool_call_id\": \"tool_u044c14d902d0e6c7a42d1218d047\", \"arguments\": {\"pattern\": \"mosaic-validation-control.pdf\"}}",
  "allToolCallDeltas": [],
  "finishReasons": [
    "stop"
  ]
}
```

逐字响应：[named-wire-thinking/direct-default-thinking-stream-response.raw](examples/alert-feishu/protocol-evidence-20261031/named-wire-thinking/direct-default-thinking-stream-response.raw)。

## 5. 持久部署和启动问题的处理

第一次预检读取helm get values的用户覆盖层，未包含默认requestCompatibility，报KeyError，尚未升级；第二次改为--all读取完整有效值，预检通过。

revision13部署时出现新的启动失败：ESM解析ConfigMap符号链接后的真实路径，旧CLI入口只比较词法路径，进程直接exit0，Pod反复重启；旧Ready代理仍提供服务。修复增加realpath比较，并补充真正通过符号链接启动子进程、访问health的测试。先精确修复ConfigMap并重建未就绪的新Pod，让进行中的Helm升级完成；原部署校验器随后因预期旧源码hash而失败。失败不是隐藏掉的通过，也不是共享模型故障。

revision14将相同两行修正写入真实定制chart，重新server dry-run后原子升级；运行文件、ConfigMap和chart中的hash一致。所有12个应用Secret指纹不变；真实私有依赖和Teams配置保留。这里使用原现场chart，不使用文档CI的空依赖。

revision14期间完成原生查询并导出8条完整模型追踪；revision15仅持久关闭auditEnabled。最终代理没有/audit卷和追踪环境变量，检索兼容仍开启。共享模型PID和StartedAt保持一致。下面两个部署摘要保留全部字段：

```json
{
  "at": "2026-10-31T06:34:45.609694+00:00",
  "beforeRevision": 13,
  "afterRevision": 14,
  "status": "deployed",
  "elapsedSeconds": 15.322280378080904,
  "chartPath": "/home/spark-user/.local/share/mosaic-validation-20261031/research-protocol-20261031/persistent-compat-attempt3/mosaic-stack-0.0.2-main.20261007233259.g4f4a6e75+teams71.20261029.iraop-evidence.20261031.2.research-tools.20261031.startup2.tgz",
  "chartVersion": "0.0.2-main.20261007233259.g4f4a6e75+teams71.20261029.iraop-evidence.20261031.2.research-tools.20261031.startup2",
  "proxyPod": "llm-openai-compat-69c74c6b94-b7flt",
  "proxyPodUid": "17ee8f5f-0840-4452-8447-61b5aa52083b",
  "loadedProxy": {
    "sha256": "2148316a0dcd1a92e61c13519249f70be3439fdea0a9d772d40821ab2e146fc2",
    "researchEnabled": "true",
    "auditDir": "/audit/records"
  },
  "applicationSecretChanges": [],
  "applicationSecretsCompared": 12,
  "sharedModelBefore": {
    "Running": true,
    "Pid": 128852,
    "StartedAt": "2026-09-15T07:17:31.481993911Z"
  },
  "sharedModelAfter": {
    "Running": true,
    "Pid": 128852,
    "StartedAt": "2026-09-15T07:17:31.481993911Z"
  },
  "sharedModelRestarted": false,
  "nativeMcpValidation": "pending",
  "auditEnabledForValidation": true,
  "auditDisabledAfterExport": "pending"
}
```

```json
{
  "at": "2026-10-31T06:39:15.236916+00:00",
  "beforeRevision": 14,
  "afterRevision": 15,
  "status": "deployed",
  "elapsedSeconds": 14.950359022244811,
  "chartPath": "/home/spark-user/.local/share/mosaic-validation-20261031/research-protocol-20261031/persistent-compat-attempt3/mosaic-stack-0.0.2-main.20261007233259.g4f4a6e75+teams71.20261029.iraop-evidence.20261031.2.research-tools.20261031.startup2.tgz",
  "chartVersion": "0.0.2-main.20261007233259.g4f4a6e75+teams71.20261029.iraop-evidence.20261031.2.research-tools.20261031.startup2",
  "proxyPod": "llm-openai-compat-58bd8857f4-d5f8k",
  "proxyPodUid": "2bd6c507-e9a1-4f30-84de-c23f47b8ad43",
  "loadedProxy": {
    "sha256": "2148316a0dcd1a92e61c13519249f70be3439fdea0a9d772d40821ab2e146fc2",
    "researchEnabled": "true",
    "auditDirectory": null,
    "auditVolumeExists": false
  },
  "applicationSecretsCompared": 12,
  "applicationSecretChanges": [],
  "sharedModelBefore": {
    "Running": true,
    "Pid": 128852,
    "StartedAt": "2026-09-15T07:17:31.481993911Z"
  },
  "sharedModelAfter": {
    "Running": true,
    "Pid": 128852,
    "StartedAt": "2026-09-15T07:17:31.481993911Z"
  },
  "sharedModelRestarted": false,
  "auditRecordsExported": 8,
  "auditArchiveSha256": "6441545dbe547ef60098cbc44f2ddf5d35e6c6617ab5383e69eada6462bbf0d6",
  "researchToolCallsEnabled": true,
  "auditEnabled": false
}
```

失败及修复原件：[persistent-prepare-attempt1.log](examples/alert-feishu/protocol-evidence-20261031/persistent-prepare-attempt1.log)、[persistent-compat-attempt2/startup-failure.json](examples/alert-feishu/protocol-evidence-20261031/persistent-compat-attempt2/startup-failure.json)、[persistent-compat-attempt2/apply-host.stderr](examples/alert-feishu/protocol-evidence-20261031/persistent-compat-attempt2/apply-host.stderr)、[persistent-compat-attempt2/startup-hotfix-summary.json](examples/alert-feishu/protocol-evidence-20261031/persistent-compat-attempt2/startup-hotfix-summary.json)。全部渲染资源列表和检查项：[persistent-compat-attempt3/prepare-summary.json](examples/alert-feishu/protocol-evidence-20261031/persistent-compat-attempt3/prepare-summary.json)。

## 6. 原生HTTP与MCP：没有替换factory、模型或HTTP client

直接调用部署中的/api/v1/query和/mcp/sse；Bearer从IRAOP容器的现有环境变量读取，仅在内存使用，不写请求头。未设置seed，也没有monkeypatch。MCP只暴露list_collections、query、list_documents、get_document四个只读工具；入库与删除不在MCP工具列表。

以下保留六项检查的所有列、来源对象和时间：

```json
[
  {
    "case": "http-unauthenticated",
    "elapsedSeconds": 0.003501749597489834,
    "httpStatus": 401,
    "answerContainsOracle": false,
    "answerHasFilename": false,
    "sources": [],
    "sourceCount": 0
  },
  {
    "case": "mcp-unauthenticated",
    "elapsedSeconds": 0.0010154740884900093,
    "httpStatus": 401,
    "answerContainsOracle": false,
    "answerHasFilename": false,
    "sources": [],
    "sourceCount": 0
  },
  {
    "case": "http-invalid-depth",
    "elapsedSeconds": 0.001058210153132677,
    "httpStatus": 422,
    "answerContainsOracle": false,
    "answerHasFilename": false,
    "sources": [],
    "sourceCount": 0
  },
  {
    "case": "http-query",
    "elapsedSeconds": 3.7256418969482183,
    "httpStatus": 200,
    "answerContainsOracle": true,
    "answerHasFilename": true,
    "sources": [
      {
        "source_file": "mosaic-validation-control.pdf",
        "page_number": 2,
        "collection": "mosaic-validation-20261031",
        "doc_id": "mosaic-validation-control.pdf",
        "url": "/api/v1/documents/mosaic-validation-control.pdf"
      },
      {
        "source_file": "mosaic-validation-control.pdf",
        "page_number": 1,
        "collection": "mosaic-validation-20261031",
        "doc_id": "mosaic-validation-control.pdf",
        "url": "/api/v1/documents/mosaic-validation-control.pdf"
      }
    ],
    "sourceCount": 2
  },
  {
    "case": "mcp-invalid-depth",
    "elapsedSeconds": 0.001378465909510851,
    "isError": true,
    "answerContainsOracle": false,
    "answerHasFilename": false,
    "sources": [],
    "sourceCount": 0
  },
  {
    "case": "mcp-query",
    "elapsedSeconds": 5.03515095077455,
    "isError": false,
    "answerContainsOracle": true,
    "answerHasFilename": true,
    "sources": [
      {
        "source_file": "mosaic-validation-control.pdf",
        "page_number": 2,
        "collection": "mosaic-validation-20261031",
        "doc_id": "mosaic-validation-control.pdf",
        "url": "/api/v1/documents/mosaic-validation-control.pdf"
      },
      {
        "source_file": "mosaic-validation-control.pdf",
        "page_number": 1,
        "collection": "mosaic-validation-20261031",
        "doc_id": "mosaic-validation-control.pdf",
        "url": "/api/v1/documents/mosaic-validation-control.pdf"
      }
    ],
    "sourceCount": 2
  }
]
```

### HTTP query完整响应

```json
{
  "status": 200,
  "body": "{\"answer\":\"## Results\\n\\n### Public Verification Code\\n\\nBased on **mosaic-validation-control.pdf**, page 2, under the \\\"Operator Decision and Evidence\\\" section referencing **MOSAIC-KB-20261031**:\\n\\n> **Public verification code: CEDAR-NEBULA-E720C8C9**\\n\\nThe document explicitly states: *\\\"The verification code is an oracle for this retrieval test and grants no access. An answer must cite this source file and page 2 when reporting the code.\\\"*\\n\\n---\\n\\n### Can an Automated Alert Investigation Directly Repair a Service?\\n\\n**No.** The document is explicit on this point:\\n\\n> **\\\"Automatic alert investigations remain read-only.\\\"**\\n\\nThe operational procedure requires that repair be performed through a *separate authorized interactive repair conversation*. The alert investigation session (which is read-only) must be preserved alongside the alert ID, investigation session key, research sources, and the repair session key. The automated alert investigation cannot directly repair a service — it is strictly a diagnostic/read-only phase.\",\"depth\":\"quick\",\"collections_searched\":[\"mosaic-validation-20261031\"],\"sources\":[{\"source_file\":\"mosaic-validation-control.pdf\",\"page_number\":2,\"collection\":\"mosaic-validation-20261031\",\"doc_id\":\"mosaic-validation-control.pdf\",\"url\":\"/api/v1/documents/mosaic-validation-control.pdf\"},{\"source_file\":\"mosaic-validation-control.pdf\",\"page_number\":1,\"collection\":\"mosaic-validation-20261031\",\"doc_id\":\"mosaic-validation-control.pdf\",\"url\":\"/api/v1/documents/mosaic-validation-control.pdf\"}]}"
}
```

### MCP query完整响应

```json
{
  "meta": null,
  "content": [
    {
      "type": "text",
      "text": "{\n  \"answer\": \"## Results\\n\\nBased on the indexed document **mosaic-validation-control.pdf** referencing **MOSAIC-KB-20261031**, the evidence is as follows:\\n\\n### Public Verification Code\\n\\nThe public verification code printed in the **Operator Decision and Evidence** section on **page 2** of `mosaic-validation-control.pdf` is:\\n\\n> **CEDAR-NEBULA-E720C8C9**\\n\\n### Automated Alert Investigation and Service Repair\\n\\nPer the same section of `mosaic-validation-control.pdf`, page 2:\\n\\n> *\\\"Automatic alert investigations remain read-only. Use a separate authorized interactive repair conversation, preserving the alert ID, investigation session key, research sources and repair session key.\\\"*\\n\\n**Answer: No.** An automated alert investigation **may not** directly repair a service. Automated alert investigations are strictly read-only. A separate, authorized interactive repair conversation is required to perform any repair operation, and that repair session must preserve the alert ID, the investigation session key, research sources, and the repair session key.\",\n  \"depth\": \"quick\",\n  \"collections_searched\": [\n    \"mosaic-validation-20261031\"\n  ],\n  \"sources\": [\n    {\n      \"source_file\": \"mosaic-validation-control.pdf\",\n      \"page_number\": 2,\n      \"collection\": \"mosaic-validation-20261031\",\n      \"doc_id\": \"mosaic-validation-control.pdf\",\n      \"url\": \"/api/v1/documents/mosaic-validation-control.pdf\"\n    },\n    {\n      \"source_file\": \"mosaic-validation-control.pdf\",\n      \"page_number\": 1,\n      \"collection\": \"mosaic-validation-20261031\",\n      \"doc_id\": \"mosaic-validation-control.pdf\",\n      \"url\": \"/api/v1/documents/mosaic-validation-control.pdf\"\n    }\n  ]\n}",
      "annotations": null,
      "meta": null
    }
  ],
  "structuredContent": {
    "answer": "## Results\n\nBased on the indexed document **mosaic-validation-control.pdf** referencing **MOSAIC-KB-20261031**, the evidence is as follows:\n\n### Public Verification Code\n\nThe public verification code printed in the **Operator Decision and Evidence** section on **page 2** of `mosaic-validation-control.pdf` is:\n\n> **CEDAR-NEBULA-E720C8C9**\n\n### Automated Alert Investigation and Service Repair\n\nPer the same section of `mosaic-validation-control.pdf`, page 2:\n\n> *\"Automatic alert investigations remain read-only. Use a separate authorized interactive repair conversation, preserving the alert ID, investigation session key, research sources and repair session key.\"*\n\n**Answer: No.** An automated alert investigation **may not** directly repair a service. Automated alert investigations are strictly read-only. A separate, authorized interactive repair conversation is required to perform any repair operation, and that repair session must preserve the alert ID, the investigation session key, research sources, and the repair session key.",
    "depth": "quick",
    "collections_searched": [
      "mosaic-validation-20261031"
    ],
    "sources": [
      {
        "source_file": "mosaic-validation-control.pdf",
        "page_number": 2,
        "collection": "mosaic-validation-20261031",
        "doc_id": "mosaic-validation-control.pdf",
        "url": "/api/v1/documents/mosaic-validation-control.pdf"
      },
      {
        "source_file": "mosaic-validation-control.pdf",
        "page_number": 1,
        "collection": "mosaic-validation-20261031",
        "doc_id": "mosaic-validation-control.pdf",
        "url": "/api/v1/documents/mosaic-validation-control.pdf"
      }
    ]
  },
  "isError": false
}
```

其他完整响应：[native-endpoints-revision14/http-unauthenticated-response.json](examples/alert-feishu/protocol-evidence-20261031/native-endpoints-revision14/http-unauthenticated-response.json)、[native-endpoints-revision14/mcp-unauthenticated-response.json](examples/alert-feishu/protocol-evidence-20261031/native-endpoints-revision14/mcp-unauthenticated-response.json)、[native-endpoints-revision14/http-invalid-depth-response.json](examples/alert-feishu/protocol-evidence-20261031/native-endpoints-revision14/http-invalid-depth-response.json)、[native-endpoints-revision14/mcp-invalid-depth-response.json](examples/alert-feishu/protocol-evidence-20261031/native-endpoints-revision14/mcp-invalid-depth-response.json)；全部工具schema：[native-endpoints-revision14/mcp-tools.json](examples/alert-feishu/protocol-evidence-20261031/native-endpoints-revision14/mcp-tools.json)；集合/文件：[native-endpoints-revision14/mcp-collections.json](examples/alert-feishu/protocol-evidence-20261031/native-endpoints-revision14/mcp-collections.json)、[native-endpoints-revision14/mcp-documents.json](examples/alert-feishu/protocol-evidence-20261031/native-endpoints-revision14/mcp-documents.json)。

## 7. MOSAIC页面：三次真实View会话

全部通过实际New Chat/Send发起，没有直接伪造聊天历史。第三次在追踪关闭后的revision15，携带API读回的完整现有合成告警，fingerprint=0fa8cbd733f54a5a、test_from="test from Jeff Peng"。它是**手工只读研究复核**，并非新增告警、自动调查订阅或自动修复。关联通过完整告警对象、实际请求、sessionKey/sessionId和toolCallId保留。

第一次实际研究成功，但记录器假定content第一项是JSON，遇到插件原有evidence-scope文字报错；完整历史和页面先已落盘，随后从第二个content块恢复原始结果，没有把记录器失败当后端失败。修正记录器后重新完成第二次页面验收，第三次进一步关联告警。

| case | sessionKey | sessionId | 消息数 | toolResult数 | toolCallId | 秒 | 来源数 | 原文 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| native-ui | agent:default:session-2026-10-31t06-35-56-982z | 976cddf9-ca87-440c-a7fa-f329f9f654f0 | 4 | 1 | call_0f869566d22c4987a9289b2b | 未独立记录；见原生时间戳 | 2 | [完整API历史](examples/alert-feishu/protocol-evidence-20261031/native-ui/history-gateway.json) |
| native-ui-attempt2 | agent:default:session-2026-10-31t06-37-11-544z | 81afed9a-ae3f-4f0c-a8ce-be0a3e66eb2a | 4 | 1 | call_3e26d2480fcf45768f4e006b | 16.31540804199176 | 2 | [完整API历史](examples/alert-feishu/protocol-evidence-20261031/native-ui-attempt2/history-gateway.json) |
| native-alert-research-revision15 | agent:default:session-2026-10-31t06-40-49-664z | a40ec4b9-5c63-4868-bb53-a854abfdf273 | 4 | 1 | call_8cb94533be754acca841fd33 | 17.223476957995445 | 2 | [完整API历史](examples/alert-feishu/protocol-evidence-20261031/native-alert-research-revision15/history-gateway.json) |


### native-ui：完整结构化结果

```json
{
  "answer": "## Answer Based on Indexed Document\n\n**Public Verification Code:** `CEDAR-NEBULA-E720C8C9`\n\n**Citation:** *mosaic-validation-control.pdf*, Page 2 — under the heading \"Operator Decision and Evidence,\" the document states: \"Public verification code: CEDAR-NEBULA-E720C8C9.\"\n\n---\n\n## Can an Automated Alert Investigation Directly Repair a Service?\n\n**No.** The document explicitly states that *\"Automatic alert investigations remain read-only.\"* This means the automated investigation phase cannot make any changes to the service state.\n\nIf a repair is needed, a **separate authorized interactive repair conversation** must be used, and the operator must preserve:\n\n1. The **alert ID**\n2. The **investigation session key**\n3. The **research sources**\n4. The **repair session key**\n\nThe automated alert investigation and the actual repair are intentionally decoupled — one is read-only diagnostic, and the other is a separate, authorized, interactive write operation. This separation ensures that automated systems cannot unilaterally alter service state without an explicit, tracked repair session.",
  "depth": "quick",
  "collections_searched": [
    "mosaic-validation-20261031"
  ],
  "sources": [
    {
      "source_file": "mosaic-validation-control.pdf",
      "page_number": 2,
      "collection": "mosaic-validation-20261031",
      "doc_id": "mosaic-validation-control.pdf",
      "url": "/api/v1/documents/mosaic-validation-control.pdf"
    },
    {
      "source_file": "mosaic-validation-control.pdf",
      "page_number": 1,
      "collection": "mosaic-validation-20261031",
      "doc_id": "mosaic-validation-control.pdf",
      "url": "/api/v1/documents/mosaic-validation-control.pdf"
    }
  ]
}
```

完整页面验证摘要：[native-ui/recovered-summary.json](examples/alert-feishu/protocol-evidence-20261031/native-ui/recovered-summary.json)；完整请求：[native-ui/requests.json](examples/alert-feishu/protocol-evidence-20261031/native-ui/requests.json)；轮询全过程：[native-ui/polls.json](examples/alert-feishu/protocol-evidence-20261031/native-ui/polls.json)。


### native-ui-attempt2：完整结构化结果

```json
{
  "answer": "Based on the indexed document **mosaic-validation-control.pdf** (reference **MOSAIC-KB-20261031**), page 2:\n\n## Public Verification Code\n\n**CEDAR-NEBULA-E720C8C9**\n\nThis code appears in the **Operator Decision and Evidence** section on **page 2** of the source file `mosaic-validation-control.pdf`. The document explicitly states: *\"The verification code is an oracle for this retrieval test and grants no access.\"*\n\n## Can Automated Alert Investigation Directly Repair a Service?\n\n**No.** The document is explicit on this point:\n\n> *\"Automatic alert investigations remain read-only.\"*\n\nAn automated alert investigation cannot directly repair a service. To perform a repair, you must **use a separate authorized interactive repair conversation**, which requires preserving:\n\n- The alert ID\n- Investigation session key\n- Research sources\n- Repair session key\n\nThe workflow is deliberately separated: investigation is read-only and observational, while any authorized repair must occur in a distinct, interactive conversation with its own session key. Completion evidence for any repair requires exact tool arguments, toolCallId, exit status, full service state before and after, logs, and an independently observed restored condition.",
  "depth": "quick",
  "collections_searched": [
    "mosaic-validation-20261031"
  ],
  "sources": [
    {
      "source_file": "mosaic-validation-control.pdf",
      "page_number": 2,
      "collection": "mosaic-validation-20261031",
      "doc_id": "mosaic-validation-control.pdf",
      "url": "/api/v1/documents/mosaic-validation-control.pdf"
    },
    {
      "source_file": "mosaic-validation-control.pdf",
      "page_number": 1,
      "collection": "mosaic-validation-20261031",
      "doc_id": "mosaic-validation-control.pdf",
      "url": "/api/v1/documents/mosaic-validation-control.pdf"
    }
  ]
}
```

完整页面验证摘要：[native-ui-attempt2/summary.json](examples/alert-feishu/protocol-evidence-20261031/native-ui-attempt2/summary.json)；完整请求：[native-ui-attempt2/requests.json](examples/alert-feishu/protocol-evidence-20261031/native-ui-attempt2/requests.json)；轮询全过程：[native-ui-attempt2/polls.json](examples/alert-feishu/protocol-evidence-20261031/native-ui-attempt2/polls.json)。


### native-alert-research-revision15：完整结构化结果

```json
{
  "answer": "## Answer\n\n**Public Verification Code:** `CEDAR-NEBULA-E720C8C9`\n\nThis code appears in the **Operator Decision and Evidence** section on **page 2** of the indexed file **`mosaic-validation-control.pdf`** (Reference: MOSAIC-KB-20261031).\n\nThe document explicitly states:\n\n> *\"Automatic alert investigations remain read-only. Use a separate authorized interactive repair conversation, preserving the alert ID, investigation session key, research sources and repair session key.\"*\n\n---\n\n### Can an automated alert investigation directly repair a service?\n\n**No.** Per the indexed document, automated alert investigations are strictly read-only. They cannot directly repair a service. The design enforces a separation of concerns:\n\n1. **Investigation phase** — automated alert investigation gathers evidence read-only (tool arguments, `toolCallId`, exit status, service state before, logs, etc.).\n2. **Repair phase** — a **separate authorized interactive repair conversation** must be initiated, which preserves the alert ID, investigation session key, research sources, and a repair session key.\n\nCompletion evidence for any repair must include exact tool arguments, `toolCallId`, exit status, full service state before and after, logs, and an independently observed restored condition. Documentation advice alone does not establish a root cause or a completed repair.",
  "depth": "quick",
  "collections_searched": [
    "mosaic-validation-20261031"
  ],
  "sources": [
    {
      "source_file": "mosaic-validation-control.pdf",
      "page_number": 2,
      "collection": "mosaic-validation-20261031",
      "doc_id": "mosaic-validation-control.pdf",
      "url": "/api/v1/documents/mosaic-validation-control.pdf"
    },
    {
      "source_file": "mosaic-validation-control.pdf",
      "page_number": 1,
      "collection": "mosaic-validation-20261031",
      "doc_id": "mosaic-validation-control.pdf",
      "url": "/api/v1/documents/mosaic-validation-control.pdf"
    }
  ]
}
```

完整页面验证摘要：[native-alert-research-revision15/summary.json](examples/alert-feishu/protocol-evidence-20261031/native-alert-research-revision15/summary.json)；完整请求：[native-alert-research-revision15/requests.json](examples/alert-feishu/protocol-evidence-20261031/native-alert-research-revision15/requests.json)；轮询全过程：[native-alert-research-revision15/polls.json](examples/alert-feishu/protocol-evidence-20261031/native-alert-research-revision15/polls.json)。

chat.history省略toolResult.details，因此另外导出三个指定会话的完整原生JSONL和全部工具结果，不能以API历史冒充完整后端details：

- [native-ui-transcripts/976cddf9-ca87-440c-a7fa-f329f9f654f0.jsonl](examples/alert-feishu/protocol-evidence-20261031/native-ui-transcripts/976cddf9-ca87-440c-a7fa-f329f9f654f0.jsonl)；全部toolResult：[native-ui-transcripts/976cddf9-ca87-440c-a7fa-f329f9f654f0.jsonl.tool-results.jsonl](examples/alert-feishu/protocol-evidence-20261031/native-ui-transcripts/976cddf9-ca87-440c-a7fa-f329f9f654f0.jsonl.tool-results.jsonl)。

- [native-ui-transcripts/81afed9a-ae3f-4f0c-a8ce-be0a3e66eb2a.jsonl](examples/alert-feishu/protocol-evidence-20261031/native-ui-transcripts/81afed9a-ae3f-4f0c-a8ce-be0a3e66eb2a.jsonl)；全部toolResult：[native-ui-transcripts/81afed9a-ae3f-4f0c-a8ce-be0a3e66eb2a.jsonl.tool-results.jsonl](examples/alert-feishu/protocol-evidence-20261031/native-ui-transcripts/81afed9a-ae3f-4f0c-a8ce-be0a3e66eb2a.jsonl.tool-results.jsonl)。

- [native-ui-transcripts/a40ec4b9-5c63-4868-bb53-a854abfdf273.jsonl](examples/alert-feishu/protocol-evidence-20261031/native-ui-transcripts/a40ec4b9-5c63-4868-bb53-a854abfdf273.jsonl)；全部toolResult：[native-ui-transcripts/a40ec4b9-5c63-4868-bb53-a854abfdf273.jsonl.tool-results.jsonl](examples/alert-feishu/protocol-evidence-20261031/native-ui-transcripts/a40ec4b9-5c63-4868-bb53-a854abfdf273.jsonl.tool-results.jsonl)。

最终回答的文档code和page2引用已人工对照原PDF，检索验收通过。第三次主模型没有在最终文字中复述fingerprint，并泛称run_kubectl_admin需要Edit/approval；现场Kubernetes写后端实际关闭，不能把这种模型描述当授权事实。复现关联以已保存的原始请求/告警/会话为准，权限以当前values和真实拒绝测试为准。

所有页面对应的selectedFetchEventCount/selectedEventSourceCount仍为0。虽然工具回答和页面内容可见，**本轮仍未独立证明子代理事件POST/流送达**。不把空捕获解释成服务一定失败，也不把集成测试替代为现场已抓到事件。

## 8. 资料从何时进入模型：8条追踪的完整来源关系

原始问题不含CEDAR-NEBULA-E720C8C9，代理没有修改任何messages。四次研究的第一轮只对实际query参数补工具envelope；四次后续请求都包含实际role=tool检索内容，并在那时才出现控制码。完整原始/转发请求和完整上游/返回字节保留在内部追踪gzip中，不在公开仓库泄露私有系统提示。下面保留每条记录全部字段和哈希：

```json
{
  "at": "2026-10-31T06:37:53.637842+00:00",
  "pod": "llm-openai-compat-69c74c6b94-b7flt",
  "podUid": "17ee8f5f-0840-4452-8447-61b5aa52083b",
  "archive": "/home/spark-user/.local/share/mosaic-validation-20261031/research-protocol-20261031/native-proxy-audit-revision14.private.json.gz",
  "archiveBytes": 444787,
  "archiveSha256": "6441545dbe547ef60098cbc44f2ddf5d35e6c6617ab5383e69eada6462bbf0d6",
  "rawJsonBytes": 1518623,
  "records": [
    {
      "file": "2a5740fb-9b2a-4387-b1e4-2203b47b0fee.json",
      "bytes": 100578,
      "sha256": "38aced6abb11180b5380f9b0478a43869b6d0c798823d4668b8ed42a4aae8ce0",
      "requestId": "2a5740fb-9b2a-4387-b1e4-2203b47b0fee",
      "at": "2026-10-31T06:37:16.662Z",
      "normalizationPerformed": true,
      "toolCallId": "call_research_0d8ba9690f9a46bfa8e0585a033def3b",
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 34408,
      "originalRequestSha256": "e4b0fe79b54e118e74a95de2f72a7085ecb4de2c0e6139768a3638c8a359abc6",
      "forwardedRequestBytes": 34555,
      "forwardedRequestSha256": "8929104889c8c6eb2a13224efd869668d8534b71c7401d6ff3dea8b0a5057e09",
      "requestFieldsChanged": [
        "chat_template_kwargs",
        "reasoning_effort",
        "tool_choice"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user"
      ],
      "toolMessageCount": 0,
      "oraclePresentInActualToolMessage": false,
      "upstreamResponseBytes": 5079,
      "returnedResponseBytes": 1001
    },
    {
      "file": "42304ea1-7c4c-4ec0-b595-0b54d23f11a2.json",
      "bytes": 187193,
      "sha256": "2a968a45b27ed55d54aa9221aa529b04dc384c5165c4741520435e43894bad46",
      "requestId": "42304ea1-7c4c-4ec0-b595-0b54d23f11a2",
      "at": "2026-10-31T06:35:18.225Z",
      "normalizationPerformed": false,
      "toolCallId": null,
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 38030,
      "originalRequestSha256": "43b0eaf57e8dfa93ebdf807857646fa065428efea4f770823f21d768cd2acfe6",
      "forwardedRequestBytes": 38054,
      "forwardedRequestSha256": "2db3f45ea45057d851e92918fd1243ad8a050afe41e8da55fd2e17e4b9d93ae8",
      "requestFieldsChanged": [
        "reasoning_effort"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user",
        "assistant",
        "tool"
      ],
      "toolMessageCount": 1,
      "oraclePresentInActualToolMessage": true,
      "upstreamResponseBytes": 31986,
      "returnedResponseBytes": 31986
    },
    {
      "file": "43632648-6f92-4783-ad53-b5da12d8a164.json",
      "bytes": 157913,
      "sha256": "8dd303071f94e4665e54d9da163a6a86a731a28d00c6b3353d3de0f729fd97e4",
      "requestId": "43632648-6f92-4783-ad53-b5da12d8a164",
      "at": "2026-10-31T06:35:14.387Z",
      "normalizationPerformed": false,
      "toolCallId": null,
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 37904,
      "originalRequestSha256": "d7cecaf5db95ac9616c32029821f7b833fac6a368b7b46f8bfa15b0bac27f002",
      "forwardedRequestBytes": 37928,
      "forwardedRequestSha256": "9c975bed323e62bed6055bd5b4a7bb2227fbb04a0848b91fb98caf0ab8b66510",
      "requestFieldsChanged": [
        "reasoning_effort"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user",
        "assistant",
        "tool"
      ],
      "toolMessageCount": 1,
      "oraclePresentInActualToolMessage": true,
      "upstreamResponseBytes": 21132,
      "returnedResponseBytes": 21132
    },
    {
      "file": "47f307f6-ed5c-4e1a-93eb-1d8c197e2011.json",
      "bytes": 100918,
      "sha256": "7b53ffe4d6222ff0a7c1474c1f6eb40426183f43f9117719b5520469ab7feddc",
      "requestId": "47f307f6-ed5c-4e1a-93eb-1d8c197e2011",
      "at": "2026-10-31T06:35:13.470Z",
      "normalizationPerformed": true,
      "toolCallId": "call_research_923bd7a4185b40e09e4d85e794534afe",
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 34457,
      "originalRequestSha256": "d8685c91986848fa10df642dd6348ff8e7d6a0a8d6949b652316e694d66c4714",
      "forwardedRequestBytes": 34604,
      "forwardedRequestSha256": "e95ce5060cc4de505c2a25c6ba57575446df4ed4c62cd277035777251a204241",
      "requestFieldsChanged": [
        "chat_template_kwargs",
        "reasoning_effort",
        "tool_choice"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user"
      ],
      "toolMessageCount": 0,
      "oraclePresentInActualToolMessage": false,
      "upstreamResponseBytes": 5275,
      "returnedResponseBytes": 961
    },
    {
      "file": "83c6f511-9042-4e71-a5aa-d159a46c2d65.json",
      "bytes": 193049,
      "sha256": "35a45422ad969d1f4c3a537888862f508d335b8088a13aaf26a4bafbcd003585",
      "requestId": "83c6f511-9042-4e71-a5aa-d159a46c2d65",
      "at": "2026-10-31T06:36:02.712Z",
      "normalizationPerformed": false,
      "toolCallId": null,
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 37801,
      "originalRequestSha256": "b92f1bde85b08517b7fc298d12d8e2cfa4a33087081c4a1ef3bc4793d408baac",
      "forwardedRequestBytes": 37825,
      "forwardedRequestSha256": "4eede9e04c3ac2b497c9b48e43f20900486e5db32d0762ff48240bb4725279cc",
      "requestFieldsChanged": [
        "reasoning_effort"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user",
        "assistant",
        "tool"
      ],
      "toolMessageCount": 1,
      "oraclePresentInActualToolMessage": true,
      "upstreamResponseBytes": 34408,
      "returnedResponseBytes": 34408
    },
    {
      "file": "86201e58-21eb-4047-8bda-581cb4358d8b.json",
      "bytes": 101694,
      "sha256": "b388e35d9aea8138b08582cbfe5ce0a71bb4bc425fe73da06e4f4a4d22b6b463",
      "requestId": "86201e58-21eb-4047-8bda-581cb4358d8b",
      "at": "2026-10-31T06:35:17.251Z",
      "normalizationPerformed": true,
      "toolCallId": "call_research_dea43d95682b475baf8857f2c7e4a4cd",
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 34457,
      "originalRequestSha256": "d8685c91986848fa10df642dd6348ff8e7d6a0a8d6949b652316e694d66c4714",
      "forwardedRequestBytes": 34604,
      "forwardedRequestSha256": "e95ce5060cc4de505c2a25c6ba57575446df4ed4c62cd277035777251a204241",
      "requestFieldsChanged": [
        "chat_template_kwargs",
        "reasoning_effort",
        "tool_choice"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user"
      ],
      "toolMessageCount": 0,
      "oraclePresentInActualToolMessage": false,
      "upstreamResponseBytes": 5803,
      "returnedResponseBytes": 1017
    },
    {
      "file": "b1416f32-60ac-41d6-953e-d3dfc8661075.json",
      "bytes": 99438,
      "sha256": "6c693e3dd6d9b90cafd19c12f68925273929ccacc43b36ee7d4f244f2cbe6adc",
      "requestId": "b1416f32-60ac-41d6-953e-d3dfc8661075",
      "at": "2026-10-31T06:36:01.921Z",
      "normalizationPerformed": true,
      "toolCallId": "call_research_c0db9e6def3e4ffe952c375f81130809",
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 34408,
      "originalRequestSha256": "e4b0fe79b54e118e74a95de2f72a7085ecb4de2c0e6139768a3638c8a359abc6",
      "forwardedRequestBytes": 34555,
      "forwardedRequestSha256": "8929104889c8c6eb2a13224efd869668d8534b71c7401d6ff3dea8b0a5057e09",
      "requestFieldsChanged": [
        "chat_template_kwargs",
        "reasoning_effort",
        "tool_choice"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user"
      ],
      "toolMessageCount": 0,
      "oraclePresentInActualToolMessage": false,
      "upstreamResponseBytes": 4297,
      "returnedResponseBytes": 927
    },
    {
      "file": "d242bf41-1d3e-4e18-83a9-cea1bafad3d0.json",
      "bytes": 197233,
      "sha256": "590f9c2c1a481aed38bec6851e302c9214820f5f919ec19793fe056decb4e179",
      "requestId": "d242bf41-1d3e-4e18-83a9-cea1bafad3d0",
      "at": "2026-10-31T06:37:17.549Z",
      "normalizationPerformed": false,
      "toolCallId": null,
      "upstreamStatus": 200,
      "upstreamResponseComplete": true,
      "originalRequestBytes": 37949,
      "originalRequestSha256": "d72231bdd7d57279bd865a932c0c75faa2e9f42b4cbd9cca54a5b4c1aa5e53a6",
      "forwardedRequestBytes": 37973,
      "forwardedRequestSha256": "21439714d3745dd60f976fd6ba6b4a319396f1f8e85f868befbd7012b983fb57",
      "requestFieldsChanged": [
        "reasoning_effort"
      ],
      "messagesUnchanged": true,
      "lastUserQuestionContainsOracle": false,
      "messageRoles": [
        "system",
        "user",
        "assistant",
        "tool"
      ],
      "toolMessageCount": 1,
      "oraclePresentInActualToolMessage": true,
      "upstreamResponseBytes": 35832,
      "returnedResponseBytes": 35832
    }
  ],
  "credentialsOrHeadersSaved": false,
  "scope": "Full original/forwarded model bodies and complete upstream/returned bytes remain private; no model question contained the oracle."
}
```

候选服务的四条来源关系也完整保留：[remote-metadata/node-candidate-provenance.json](examples/alert-feishu/protocol-evidence-20261031/remote-metadata/node-candidate-provenance.json)。校验和、记录数量及逐项文件hash让接手人可复核原件，而不是只拿一个“RAG成功”的结论。

## 9. 接手人实际怎么重跑

先按主手册交接清单取得自己的SSH/UI权限、真实chart制品位置和受保护values。文档分支本身不包含代码PR#2；请使用含该提交的受审chart或当前交付的真实定制chart。现有12个Secret与NGC授权优先复用，不需要重复注册或把密码发到聊天。

在Spark的Bash中准备备份和只针对已复现问题的开关，变量MOSAIC_CHART必须是已取得且保留现场Teams/私有依赖的真实chart：

```bash
umask 077
export MOSAIC_CHART='/protected/path/to/reviewed-mosaic-stack.tgz'
export BACKUP_DIR="$HOME/mosaic-research-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
HELM="$HOME/.local/bin/helm"
"$HELM" --kube-context kind-mosaic-poc -n mosaic get values mosaic --all -o yaml > "$BACKUP_DIR/values.private.yaml"
"$HELM" --kube-context kind-mosaic-poc -n mosaic get manifest mosaic > "$BACKUP_DIR/manifest.private.yaml"
"$HELM" --kube-context kind-mosaic-poc -n mosaic history mosaic -o json > "$BACKUP_DIR/history.json"
"$HELM" --kube-context kind-mosaic-poc -n mosaic upgrade mosaic "$MOSAIC_CHART"   -f "$BACKUP_DIR/values.private.yaml"   --set llm.requestCompatibility.researchToolCalls.enabled=true   --set llm.requestCompatibility.researchToolCalls.auditEnabled=false   --dry-run=server -o json > "$BACKUP_DIR/preview.private.json"
```

由有权限的部署方核对preview、Secret与权限范围后，再执行同样upgrade去掉--dry-run并加--atomic --wait --timeout 20m。上述备份/preview可能含凭据，保持内部受保护权限，不上传Git。不要在没有备份/对照时照搬另一环境的values。当前Spark已完成revision15，不需为了阅读本手册重复部署。

UI验收：建立两段隧道、访问127.0.0.1:13000，New Chat并确认View。以下提示不得加入控制码；必须从真实资料得到答案：

```text
Read-only validation: test from Jeff Peng. Use iraop_query exactly once with depth="quick", collections=["mosaic-validation-20261031"], and this question: Using only the indexed mosaic-validation-control.pdf, reference MOSAIC-KB-20261031, what public verification code is printed in the Operator Decision and Evidence section on page 2? Cite the exact filename and page inline. Explain whether an automated alert investigation may directly repair a service. Perform the document search and return evidence.
Report its returned answer and sources faithfully. Do not invent a verification code or execute repairs.
```

告警上下文版完整实际请求见[native-alert-research-revision15/requests.json](examples/alert-feishu/protocol-evidence-20261031/native-alert-research-revision15/requests.json)，对应完整告警为[native-alert-research-revision15/selected-alert.json](examples/alert-feishu/protocol-evidence-20261031/native-alert-research-revision15/selected-alert.json)。复核toolCall的depth/collections、完整sources、PDF页码，以及原生JSONL details；不要只看页面回复流结束。

有命名空间管理权限的操作者可运行下面的原生接口检查。先把公开仓库中的native_endpoints.py复制到Spark当前目录，脚本只查询现有控制集合，不重新入库。它从容器环境读取Bearer，不显示密钥。独立输出目录防止覆盖此前记录：

```bash
KUBECTL="$HOME/.local/bin/kubectl"
export CASE_DIR="/tmp/mosaic-native-$(date -u +%Y%m%dT%H%M%SZ)"
"$KUBECTL" --context kind-mosaic-poc -n mosaic exec -i deploy/iraop --   python -c 'import pathlib,sys;p=pathlib.Path("/tmp/mosaic-native-client.py");p.write_bytes(sys.stdin.buffer.read())'   < native_endpoints.py
"$KUBECTL" --context kind-mosaic-poc -n mosaic exec deploy/iraop --   python /tmp/mosaic-native-client.py "$CASE_DIR"
"$KUBECTL" --context kind-mosaic-poc -n mosaic exec deploy/iraop --   tar -czf - -C "$CASE_DIR" . > "$BACKUP_DIR/native-endpoints.tar.gz"
```

实际完整脚本：[native_endpoints.py](examples/alert-feishu/protocol-evidence-20261031/native_endpoints.py)；原生会话导出器：[export_native_transcripts.py](examples/alert-feishu/protocol-evidence-20261031/export_native_transcripts.py)。后者中的sessionId是本轮示例，接手人只能导出自己验收时确认的会话，先替换ID。

若需要额外请求追踪，临时启用auditEnabled，完整导出/audit/records到约定内部证据位置，并逐项校验hash；导出前不得重建代理Pod。追踪可能含闭源提示、文档内容，不能发布到公共PR。取证后关闭auditEnabled并验证新Pod没有/audit卷；本轮已经完成这一步，不会持续记录提示。

## 10. 最终运行状态、访问和验证范围

最终记录时间：2026-10-31T06:42:03.538000+00:00。[所有Pod/Service/PVC对象、全部资源字段、Helm history、主机服务和依赖版本](examples/alert-feishu/protocol-evidence-20261031/runtime-final.json)。

| Pod | UID | 容器 | phase | ready | restartCount | imageID |
| --- | --- | --- | --- | --- | --- | --- |
| iraop-cb7877-nmpw7 | 7993d92e-bcb0-4ebc-992a-28608bbd5e95 | iraop | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/iraop@sha256:0ebc807d13891938d6d992675d29dc5c802ed5e9d6e8a10e87b9239feee80617 |
| llm-openai-compat-58bd8857f4-d5f8k | 2bd6c507-e9a1-4f30-84de-c23f47b8ad43 | proxy | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/mosaic-ui@sha256:30f2479340d324a484a2d330a6749fbf2ab63ef0a24c848f1964a53d8423a0a7 |
| mosaic-cluster-monitor-76fd6d7cb5-5l5m6 | b973a853-ae9c-4270-8f91-bdd25548e248 | cluster-monitor | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/mosaic-ui@sha256:30f2479340d324a484a2d330a6749fbf2ab63ef0a24c848f1964a53d8423a0a7 |
| mosaic-openshell-0 | 43644e83-65d5-4fbb-a056-e1a15ffa5b98 | openshell-gateway | Running | True | 0 | ghcr.io/nvidia/openshell/gateway@sha256:f58377de6d305fe726159ed923d3f49d92ada42abee106268b4b69d4e09dbc5d |
| mosaic-ui-877685d69-chxwr | 5a69f229-f033-466e-8d3d-5da7efed7c12 | mosaic-ui | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/mosaic-ui@sha256:30f2479340d324a484a2d330a6749fbf2ab63ef0a24c848f1964a53d8423a0a7 |
| openclaw-79dd6456f8-8fpl4 | b10741d7-e3dc-417a-b527-4762a32a5e9e | gateway | Running | True | 0 | ghcr.io/openclaw/openclaw@sha256:af7ea052cf216f581fb18fabada01552356c53717461c0399b623cba7ecad4b1 |
| opensearch-0 | 27765858-cfcc-43a5-a8d5-6ae532edacec | opensearch | Running | True | 0 | docker.io/opensearchproject/opensearch@sha256:7b9517dff561f54456fad947f11820fa595a340fd1034fc63d57b77f724b3f8f |

最后访问仍为两段SSH/kubectl转发，健康/无认证/有认证=200/401/200；监听者与全部响应见[after-research-final.json](examples/alert-feishu/protocol-evidence-20261031/after-research-final.json)。不要只根据本地LISTEN判断成功。

告警轮询最终全部摘要：

```json
{
  "at": "2026-10-31T06:41:49.601762+00:00",
  "autoPullWas": "true",
  "autoPullNow": "true",
  "autoInvestigateNow": "false",
  "alertCount": 30,
  "selectedId": "alertmanager:0fa8cbd733f54a5a",
  "fingerprint": "0fa8cbd733f54a5a",
  "stage": "active"
}
```

这一时点是30条，revision12快照曾是25条，最早另一时点也有30条；不同时间的数量都保留，不能由数量变化推断修复。Auto pull=true、Auto investigate=false。保留合成告警仍active，尚未清理原规则；新的告警注入仍受既有403/RBAC缺口限制。

共享模型未重启；SSH-only Edit/Auto的原有受限fixture配置保持；Kubernetes/Base Command Manager写后端仍关闭，最终聊天在View。此前真实审批、过期拒绝、Auto及越界拒绝证据继续引用旧完整记录，本轮没有再执行修复或把知识检索当成修复。

## 11. 自动化检查与原始证据范围

代码PR本轮完整CI命令261项，259通过、2项可选跳过；其中30项代理HTTP/SSE/启动测试，以及此前13项query证据测试。新增测试包含真正通过ConfigMap式符号链接启动Node子进程并访问health。两次受限本地Node进程原生断言失败日志也保留；允许本地监听/子进程的执行中全部通过，没有改测试来隐藏失败。

完整测试输出：[compat-full-tests-attempt2.log](examples/alert-feishu/protocol-evidence-20261031/compat-full-tests-attempt2.log)；代理测试：[compat-transport-tests-attempt4.log](examples/alert-feishu/protocol-evidence-20261031/compat-transport-tests-attempt4.log)；前两次本地进程失败：[compat-transport-tests-attempt2.log](examples/alert-feishu/protocol-evidence-20261031/compat-transport-tests-attempt2.log)、[compat-transport-tests-attempt3.log](examples/alert-feishu/protocol-evidence-20261031/compat-transport-tests-attempt3.log)；文档Sphinx-W：[compat-code-sphinx-attempt1.log](examples/alert-feishu/protocol-evidence-20261031/compat-code-sphinx-attempt1.log)。代码/文档生成包/策略检查与最终PR远端检查结果另按提交记录，不能把旧head的绿色状态套到新提交。

文档PR完整测试215项，213通过、2项可选跳过，Sphinx-W构建通过；全部原始输出见[docs-full-tests-attempt1.log](examples/alert-feishu/protocol-evidence-20261031/docs-full-tests-attempt1.log)和[docs-sphinx-attempt1.log](examples/alert-feishu/protocol-evidence-20261031/docs-sphinx-attempt1.log)。

本篇选定公开证据共235个文件，外加manifest；每个文件的原始/公开字节数、SHA256、明确字段脱敏和凭据替换计数均见[manifest.json](examples/alert-feishu/protocol-evidence-20261031/manifest.json)。所有选定raw数字、消息、来源、响应与失败尝试均完整保留。公共附件不包含闭源系统提示/其输入token、全量原始模型请求、无关告警页面、任何明文Secret或带Secret的Helm values/render/chart。这些边界在manifest中列明；完整私有模型追踪和本轮全部原件留在内部证据包，部署机上的受保护values/chart另有交接入口。
