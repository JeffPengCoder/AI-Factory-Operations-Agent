<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Spark 实测记录：访问、告警、Research 与 Edit/Auto（2026-10-31）

这次已在现有 Spark/Kind 上实际执行验证。**访问恢复、已有告警轮询、现场只读采集、PDF 入库，以及隔离服务的 View/Edit/Auto 修复控制已验证；Research 的原生检索质量未通过，飞书尚待群机器人创建。** 本记录同时保存失败结果，不能将“Pod Running”“API 200”或模型的成功措辞当成业务验收通过。

**后续状态见[追加实测](spark_live_validation_20261031_followup.zh-CN.md)：当前 revision 12，已补测审批过期和 IRAOP Pod 重建，并部署无来源回答的 incomplete 处理。** 下列 27 项、部署表和工具索引保留 revision 10 时的原始快照；追加证据单独保存，没有覆盖原件。原生研究质量和飞书投递仍待通过。

这是脱敏公开版。真实地址/账号及凭据取用入口由部署方单独交接；`*.example.invalid`、`spark-user`、`target-lab`、`NGC_ORG_ID` 均为占位符。所有选定会话、工具结果、节点/Pod 行、指标点和向量在原始附件中完整保留。脱敏规则、全部文件大小与双份 SHA256 见 [完整证据清单](examples/alert-feishu/live-evidence-20261031/manifest.json)。

## 1. 验收结果逐项列明

| 环节 | 结果 | 实际观察 | 完整证据 |
| --- | --- | --- | --- |
| 访问/正常 | 通过 | health 200；无认证 401；有认证 200 | [final-access.json](examples/alert-feishu/live-evidence-20261031/final-access.json) |
| 访问/双层隧道都停 | 通过 | 两端无监听，HTTP 不通 | [combined-stopped.json](examples/alert-feishu/live-evidence-20261031/combined-stopped.json) |
| 访问/只有 Spark 转发 | 通过 | 本机无监听，HTTP 不通 | [remote-only.json](examples/alert-feishu/live-evidence-20261031/remote-only.json) |
| 访问/只有本机 SSH | 通过 | 本机在监听，Spark 后端缺失，HTTP 不通 | [local-listener-remote-missing.json](examples/alert-feishu/live-evidence-20261031/local-listener-remote-missing.json) |
| 访问/恢复两层 | 通过 | 200 / 401 / 200 | [combined-restored.json](examples/alert-feishu/live-evidence-20261031/combined-restored.json) |
| 访问/Pod 更换后的旧隧道 | 通过故障复现 | 两端监听仍存在，但 HTTP 不可用；重连后恢复 | [after-edit-old-tunnel-check.json](examples/alert-feishu/live-evidence-20261031/after-edit-old-tunnel-check.json) |
| 新 Alertmanager API 注入 | 未通过 | POST nginx 403；同一 run_id 告警数 0 | [remote-evidence/evidence/live-alert-create.json](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/live-alert-create.json) |
| 已有合成告警轮询 | 通过 | Auto pull false→true；导入总数 30；选定 fingerprint/annotation 保持一致 | [selected-alert-current.json](examples/alert-feishu/live-evidence-20261031/selected-alert-current.json) |
| 页面手动发起调查 | 通过，有权限缺口 | 6 个初查 toolResult；PrometheusRule get 被 RBAC 拒绝；其他读取返回 | [alert-ui-history-gateway.json](examples/alert-feishu/live-evidence-20261031/alert-ui-history-gateway.json) |
| 追加现场证据 | 通过 | 2 节点全部列；monitoring 10 个 Pod 全部列；15 分钟 31 个点全部列 | [collected-live-data.json](examples/alert-feishu/live-evidence-20261031/collected-live-data.json) |
| Embedding 认证与真实向量 | 通过 | 无认证 401；有认证 200；2 个完整 384 维向量 | [remote-evidence/evidence/embedding-probe.json](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/embedding-probe.json) |
| IRAOP/OpenSearch 就绪 | 通过 | live/health 200；OpenSearch 2.17.0；embedding 384d | [remote-evidence/evidence/iraop-direct-validation.jsonl](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/iraop-direct-validation.jsonl) |
| PDF 入库/原文下载 | 通过，存在刷新延迟 | 2 页、4 chunks、0 errors；3781 bytes；原文 SHA256 一致 | [remote-evidence/evidence/iraop-direct-validation.jsonl](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/iraop-direct-validation.jsonl) |
| IRAOP 直接查询 | 部分通过 | 50.77735306927934 秒；答案命中测试码，sources 包含第 2 页；行内编号却指向第 1 页 | [remote-evidence/evidence/iraop-direct-validation.jsonl](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/iraop-direct-validation.jsonl) |
| OpenClaw→IRAOP 首次 | 未通过 | MCP 可达，但研究返回规划文字和空 sources | [native-research-history-gateway.json](examples/alert-feishu/live-evidence-20261031/native-research-history-gateway.json) |
| OpenClaw→IRAOP 重试 | 未通过 | 两次 query 均未提供 sources | [native-research-retry-history-gateway.json](examples/alert-feishu/live-evidence-20261031/native-research-retry-history-gateway.json) |
| 告警会话→IRAOP | 未通过 | 同一告警会话两次 query sources=[]；集合/文件存在不能替代检索命中 | [alert-followup-history-gateway.json](examples/alert-feishu/live-evidence-20261031/alert-followup-history-gateway.json) |
| 模型工具协议诊断 | 发现异常，根因未证实 | compat 非流式 finish_reason=tool_calls，但解析 tool_calls 为空 | [remote-evidence/evidence/model-tool-protocol.jsonl](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/model-tool-protocol.jsonl) |
| 仅绕过 compat 的隔离实验 | 未改善 | 1.8424160638824105 秒；仍返回伪工具文本、sources=[]；未改服务配置 | [remote-evidence/evidence/research-direct-model-experiment.json](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/research-direct-model-experiment.json) |
| View 诊断与拒绝修复 | 通过 | 诊断 exit3 返回真实 failed 状态；修复策略拒绝；marker 不存在 | [repair-view-history-gateway.json](examples/alert-feishu/live-evidence-20261031/repair-view-history-gateway.json) |
| Edit 拒绝 | 通过 | Deny 后未执行，marker 不存在，服务仍 failed | [edit-after-deny-host.json](examples/alert-feishu/live-evidence-20261031/edit-after-deny-host.json) |
| Edit 批准 | 通过 | 新 Approve once 后 wrapper exit0；active/exited/success/ExecMainStatus0 | [edit-after-approve-host.json](examples/alert-feishu/live-evidence-20261031/edit-after-approve-host.json) |
| Auto 确认与执行 | 通过 | 确认 Enable Auto；逐次审批轮询始终空；wrapper exit0，主机恢复 | [auto-after-repair-host.json](examples/alert-feishu/live-evidence-20261031/auto-after-repair-host.json) |
| Auto 范围外命令 | 通过拒绝 | touch 请求被 forced-command 拒绝，exit126，文件未创建 | [auto-after-boundary-host.json](examples/alert-feishu/live-evidence-20261031/auto-after-boundary-host.json) |
| Auto 后回到 View | 通过 | 本会话 View；新 Chat 默认 View | [auto-ui-summary.json](examples/alert-feishu/live-evidence-20261031/auto-ui-summary.json) |
| Audit 可观察性 | 通过 | API 200；41 条总记录中本日 5 条模式/审批事件逐条保留 | [audit-current-events.json](examples/alert-feishu/live-evidence-20261031/audit-current-events.json) |
| 飞书真实群投递 | 待客户操作 | 用户尚未创建群机器人；8867 bytes 完整待审 payload 已离线生成；没有实际发送或收件记录 | [feishu-status.json](examples/alert-feishu/live-evidence-20261031/feishu-status.json) |


当前仍未执行的边界：新的 PrometheusRule 创建/删除、真实 GPU/NVDebug 采集、部署回滚、整机/Kind/OpenSearch PVC 重建后的资料恢复、飞书原生双向通道与真实群投递、所有生产故障的自动修复。Edit 审批过期和仅 IRAOP 无状态 Pod 重建已在[追加实测](spark_live_validation_20261031_followup.zh-CN.md)通过。未改变 L20 集群 RBAC 来绕过读取失败，也没有绕过 Alertmanager 的 403 写限制。

## 2. 当前部署和实际变更

本记录快照：开始基线为 Helm revision 8；启用 Research 后 revision 9；启用 SSH-only Edit 后 **revision 10 deployed**。沿用原有包含 Teams 定制及真实 IRAOP 子 chart 的 chart 包，没有用文档 CI 的依赖 stub 部署。[本快照全部 Helm history](examples/alert-feishu/live-evidence-20261031/helm-history-after.json)保留当时每个 revision 的原始时间和状态。当前已到 revision 12，见追加记录；原始 values、manifest 和 Secret 不进入公开证据。

所有模块开关如下：

| 模块 | enabled |
| --- | --- |
| bcm | false |
| clusters | true |
| diagnostics | false |
| edit | true |
| execution | true |
| grafana | true |
| kubernetes | true |
| observability | true |
| research | true |
| slurm | false |
| terminal | false |
| ui | true |


Edit 为 `hitl=true`、审批超时 `120000 ms`，仅 SSH 后端开启，Kubernetes/Base Command Manager 写后端都关闭。主机固定 alias=`repair-demo`，机器身份来自 `mosaic-validation-ssh`。未创建 Kind editor ClusterRoleBinding，未提供 L20 管理员凭据。

当前 namespace 中所有 Pod/容器逐行列出（就绪与重启数为快照）：

| Pod | 容器 | phase | ready | restartCount | 实际 imageID |
| --- | --- | --- | --- | --- | --- |
| iraop-cb7877-kmr2f | iraop | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/iraop@sha256:0ebc807d13891938d6d992675d29dc5c802ed5e9d6e8a10e87b9239feee80617 |
| llm-openai-compat-5d6d8c68cf-pfjvs | proxy | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/mosaic-ui@sha256:30f2479340d324a484a2d330a6749fbf2ab63ef0a24c848f1964a53d8423a0a7 |
| mosaic-cluster-monitor-76fd6d7cb5-5l5m6 | cluster-monitor | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/mosaic-ui@sha256:30f2479340d324a484a2d330a6749fbf2ab63ef0a24c848f1964a53d8423a0a7 |
| mosaic-openshell-0 | openshell-gateway | Running | True | 0 | ghcr.io/nvidia/openshell/gateway@sha256:f58377de6d305fe726159ed923d3f49d92ada42abee106268b4b69d4e09dbc5d |
| mosaic-ui-658bd7c556-j9pjf | mosaic-ui | Running | True | 0 | nvcr.io/NGC_ORG_ID/afoa-release/mosaic-ui@sha256:30f2479340d324a484a2d330a6749fbf2ab63ef0a24c848f1964a53d8423a0a7 |
| openclaw-66c66555f5-nsgqk | gateway | Running | True | 0 | ghcr.io/openclaw/openclaw@sha256:af7ea052cf216f581fb18fabada01552356c53717461c0399b623cba7ecad4b1 |
| opensearch-0 | opensearch | Running | True | 0 | docker.io/opensearchproject/opensearch@sha256:7b9517dff561f54456fad947f11820fa595a340fd1034fc63d57b77f724b3f8f |


完整 Pod/Service/PVC 对象、资源 requests/limits、Helm history、内存/磁盘、用户服务状态及全部 embedding 依赖版本见 [runtime-after.json](examples/alert-feishu/live-evidence-20261031/runtime-after.json)。它只从 values 中提取模块开关和允许的非机密配置字段，没有保存原始 values。

## 3. 本机访问与断线恢复

实际访问链路：本机浏览器 `127.0.0.1:13000` → 本机 SSH listener → Spark `127.0.0.1:13000` → `kubectl port-forward` → 当前 `mosaic-ui` Pod `:3000`。本机端口可访问是因为两层转发都在运行。仅看到一端 LISTEN 不足以确认可访问；Pod 更换后旧转发也可能仍占端口而后端失效。

给接手人使用的命令如下，先按私下交接填写变量。检查已有监听后再建连接，不要对所有 ssh/kubectl 使用 pkill：

```bash
export SPARK_HOST='spark.example.invalid'
export SPARK_USER='spark-user'
export SPARK_SSH_PORT='22'
lsof -nP -iTCP:13000 -sTCP:LISTEN
ssh -p "$SPARK_SSH_PORT" "$SPARK_USER@$SPARK_HOST" 'ss -ltnp "( sport = :13000 )"'
ssh -tt -p "$SPARK_SSH_PORT"   -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3   -L 127.0.0.1:13000:127.0.0.1:13000 "$SPARK_USER@$SPARK_HOST"   '$HOME/.local/bin/kubectl --context kind-mosaic-poc -n mosaic port-forward --address=127.0.0.1 svc/mosaic-ui 13000:3000'
```

该命令在前台运行，终端/SSH/后端 Pod 断开可能使链路失效；按主操作手册第 3 章恢复。升级之后先核对旧转发，再结束本轮已确认属于自己的进程并重新连接。最终实测 health=200，无凭据业务 API=401，有凭据=200，见 [final-access.json](examples/alert-feishu/live-evidence-20261031/final-access.json)。管理员 SSH ControlMaster 只用于复用运维连接，与上面独立的 UI 转发进程分开。

## 4. 告警注入、轮询与调查：本轮实际边界

本轮新 Alertmanager API 注入请求包含 `test_from="test from Jeff Peng"`、唯一 run_id 和 1 小时过期时间；响应为 **nginx 403**，匹配告警数为 0。完整 POST 内容、响应 headers/body 和查询结果见 [remote-evidence/evidence/live-alert-create.json](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/live-alert-create.json)。该条没有创建成功，更没有验证新 PrometheusRule 的计算。

我们改用之前已实际创建且仍 firing 的 `monitoring/mosaic-alert-smoke-test`，没有假称它是本轮新告警。fingerprint=`0fa8cbd733f54a5a`，完整 labels/annotations 和原始 `startsAt` 见 [selected-alert-current.json](examples/alert-feishu/live-evidence-20261031/selected-alert-current.json)。实际在页面将 Auto pull 从 false 开为 true，Refresh 后导入 30 条现有告警，只对该合成告警点击 **Start Investigating ❯**。Auto investigate 保持关闭，避免顺带调查另外 29 条告警。

Start Investigating 的真实 UI POST 见 [alert-investigate-ui-requests.json](examples/alert-feishu/live-evidence-20261031/alert-investigate-ui-requests.json)。它以 View 发起调查。再次点击会重建同一 sessionKey 对应的 session：旧 sessionId=`1192f07a-611e-4880-b59a-fdd43a41a0a0`、19 条消息；新 sessionId=`1e50b9f3-cb5a-4a67-ae5b-532f24b379ab`、初查 10 条消息。旧历史已先导出到 [alert-ui-before-history-api.json](examples/alert-feishu/live-evidence-20261031/alert-ui-before-history-api.json)，新初查完整结果见 [alert-ui-history-gateway.json](examples/alert-feishu/live-evidence-20261031/alert-ui-history-gateway.json)。接手人重跑前应导出旧调查。

初查拿到 6 个工具结果，包括 Prometheus 即时值、monitoring Pod 和 Service。读取 PrometheusRule 返回 Forbidden：`system:serviceaccount:mosaic-readonly:mosaic-reader` 无该资源的 get 权限。我们保留错误，没有扩大权限。

随后在同一告警会话以只读 API 追加请求，采集下列现场信息并显式调用 IRAOP。最终该会话 25 条原始消息、14 个工具结果；`hasActiveRun=false`，页面 stage 仍 `responding`。这是 UI 阶段与模型运行状态的差异，不能把 responding 直接解释为模型还在执行。原 prompt、完整 NDJSON 流及最终历史均保留。

### 4.1 节点：全部行和全部列

```bash
kubectl get nodes -o wide
```

```text
NAME         STATUS   ROLES           AGE    VERSION    INTERNAL-IP   EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION       CONTAINER-RUNTIME
target-node-1   Ready    control-plane   275d   v1.32.11   target-node-1.example.invalid   <none>        Ubuntu 22.04.4 LTS   5.15.0-1069-nvidia   containerd://1.7.25
target-node-2   Ready    <none>          271d   v1.32.11   target-node-2.example.invalid   <none>        Ubuntu 22.04.4 LTS   5.15.0-1069-nvidia   containerd://1.7.28
```

### 4.2 monitoring Pod：全部行和全部列

```bash
kubectl get pods -n monitoring -o wide
```

```text
NAME                                                       READY   STATUS                   RESTARTS        AGE    IP              NODE         NOMINATED NODE   READINESS GATES
alertmanager-kube-prometheus-stack-alertmanager-0          2/2     Running                  0               15d    private-address-11.example.invalid   target-node-2   <none>           <none>
kube-prometheus-stack-grafana-96659b767-bw7pk              0/3     ContainerStatusUnknown   4 (88d ago)     226d   private-address-06.example.invalid   target-node-1   <none>           <none>
kube-prometheus-stack-grafana-96659b767-hvkhr              3/3     Running                  0               31d    private-address-12.example.invalid   target-node-2   <none>           <none>
kube-prometheus-stack-kube-state-metrics-774cbcbd5-25jpl   1/1     Running                  1 (2d16h ago)   11d    private-address-10.example.invalid   target-node-2   <none>           <none>
kube-prometheus-stack-kube-state-metrics-774cbcbd5-nwxpj   0/1     Error                    5 (88d ago)     226d   private-address-07.example.invalid   target-node-1   <none>           <none>
kube-prometheus-stack-operator-6d64c465c4-j6bf6            1/1     Running                  0               13d    private-address-09.example.invalid   target-node-2   <none>           <none>
kube-prometheus-stack-operator-6d64c465c4-knn9w            0/1     ContainerStatusUnknown   1               226d   private-address-08.example.invalid   target-node-1   <none>           <none>
kube-prometheus-stack-prometheus-node-exporter-tgwgb       1/1     Running                  0               270d   target-node-2.example.invalid     target-node-2   <none>           <none>
kube-prometheus-stack-prometheus-node-exporter-zm2cx       1/1     Running                  0               10d    target-node-1.example.invalid     target-node-1   <none>           <none>
prometheus-kube-prometheus-stack-prometheus-0              2/2     Running                  0               31d    private-address-13.example.invalid   target-node-2   <none>           <none>
```

有健康的 Prometheus/Alertmanager，也有历史 Error/ContainerStatusUnknown Pod。不能因合成告警没有真实故障，就声称整个集群没有其他问题。这里只读取，没有修复这些工作负载。

### 4.3 指标：全部 31 点

query=`ALERTS{alertname="MosaicSyntheticAlert",alertstate="firing"}`，start=`1793413140`，end=`1793414040`，step=`30` 秒，seriesCount=`1`，pointCount=`31`，truncated=`false`。labels 完整为 `__name__=ALERTS, alertname=MosaicSyntheticAlert, alertstate=firing, mosaic_test=true, severity=warning`。完整结构见 [collected-live-data.json](examples/alert-feishu/live-evidence-20261031/collected-live-data.json)，可下载 CSV 见 [all-metric-points.csv](examples/alert-feishu/live-evidence-20261031/all-metric-points.csv)。

| timestamp（Unix 秒） | UTC | value |
| --- | --- | --- |
| 1793413140 | 2026-10-31T02:19:00+00:00 | 1 |
| 1793413170 | 2026-10-31T02:19:30+00:00 | 1 |
| 1793413200 | 2026-10-31T02:20:00+00:00 | 1 |
| 1793413230 | 2026-10-31T02:20:30+00:00 | 1 |
| 1793413260 | 2026-10-31T02:21:00+00:00 | 1 |
| 1793413290 | 2026-10-31T02:21:30+00:00 | 1 |
| 1793413320 | 2026-10-31T02:22:00+00:00 | 1 |
| 1793413350 | 2026-10-31T02:22:30+00:00 | 1 |
| 1793413380 | 2026-10-31T02:23:00+00:00 | 1 |
| 1793413410 | 2026-10-31T02:23:30+00:00 | 1 |
| 1793413440 | 2026-10-31T02:24:00+00:00 | 1 |
| 1793413470 | 2026-10-31T02:24:30+00:00 | 1 |
| 1793413500 | 2026-10-31T02:25:00+00:00 | 1 |
| 1793413530 | 2026-10-31T02:25:30+00:00 | 1 |
| 1793413560 | 2026-10-31T02:26:00+00:00 | 1 |
| 1793413590 | 2026-10-31T02:26:30+00:00 | 1 |
| 1793413620 | 2026-10-31T02:27:00+00:00 | 1 |
| 1793413650 | 2026-10-31T02:27:30+00:00 | 1 |
| 1793413680 | 2026-10-31T02:28:00+00:00 | 1 |
| 1793413710 | 2026-10-31T02:28:30+00:00 | 1 |
| 1793413740 | 2026-10-31T02:29:00+00:00 | 1 |
| 1793413770 | 2026-10-31T02:29:30+00:00 | 1 |
| 1793413800 | 2026-10-31T02:30:00+00:00 | 1 |
| 1793413830 | 2026-10-31T02:30:30+00:00 | 1 |
| 1793413860 | 2026-10-31T02:31:00+00:00 | 1 |
| 1793413890 | 2026-10-31T02:31:30+00:00 | 1 |
| 1793413920 | 2026-10-31T02:32:00+00:00 | 1 |
| 1793413950 | 2026-10-31T02:32:30+00:00 | 1 |
| 1793413980 | 2026-10-31T02:33:00+00:00 | 1 |
| 1793414010 | 2026-10-31T02:33:30+00:00 | 1 |
| 1793414040 | 2026-10-31T02:34:00+00:00 | 1 |


这证明选定窗口内该合成规则持续 firing。Alertmanager 轮询入库的对应对象才是 MOSAIC 接收的证据；不能仅凭 Prometheus ALERTS 或 Alertmanager Pod Running 推断所有后续链路都通。

## 5. Research 实际部署、入库和失败点

本轮使用独立本地 CPU embedding，没有要求用户先提供 SaaS key。模型为 `sentence-transformers/all-MiniLM-L6-v2`，固定 revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`，ONNX CPUExecutionProvider，384 维，最多 256 tokens，mean pooling + L2 normalize；超长输入返回 422，不静默截断。用户服务 `mosaic-embedding-validation.service` 绑定 Kind 可达的主机桥接地址 `:18081`，有独立 Bearer，CPUQuota=200%，MemoryMax=2Gi。未改 GPU 推理和内核参数；原有 vm.max_map_count=1048576。

这是英文小型控制语料实验，不能据此声称与默认 Nemotron 2048 维 embedding 的检索质量等价。模型文件全部列出：

| 文件 | bytes | SHA256 |
| --- | --- | --- |
| config.json | 612 | 953f9c0d463486b10a6871cc2fd59f223b2c70184f49815e7efbcab5d8908b41 |
| tokenizer.json | 466247 | be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037 |
| tokenizer_config.json | 350 | acb92769e8195aabd29b7b2137a9e6d6e25c476a4f15aa4355c233426c61576b |
| special_tokens_map.json | 112 | 303df45a03609e4ead04bc3dc1536d0ab19b5358db685b6f3da123d05ec200e3 |
| vocab.txt | 231508 | 07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3 |
| onnx/model.onnx | 90405214 | 6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452 |


真实两个 384 维向量和认证结果见 [remote-evidence/evidence/embedding-probe.json](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/embedding-probe.json)，服务实现及模型下载代码见 [embedding_server.py](examples/alert-feishu/live-evidence-20261031/embedding_server.py)、[download_embedding.py](examples/alert-feishu/live-evidence-20261031/download_embedding.py)。

真实 IRAOP 与 OpenSearch 已部署，/live 和 /health 为 200，业务接口无 Bearer 返回 401。原 chart 已有 Bearer 支持，本轮不需要为认证补丁而修改运行源码。chat 仍使用已有 Qwen + compat 服务，MAX_TOKENS=4096，depth=quick；embedding 为本地 openai flavor + 384d。实际完整 overlay 见 [research-overlay.yaml](examples/alert-feishu/live-evidence-20261031/research-overlay.yaml)。

控制 PDF 为本次自编的公开测试资料，2 页、3781 bytes，SHA256=`e65f46b9daa87b4420336d989b0951ac6d2d6fd0a479bdcaeda42862cd92e820`。原文件见 [mosaic-validation-control.pdf](examples/alert-feishu/live-evidence-20261031/mosaic-validation-control.pdf)，提取原文见 [control-source.json](examples/alert-feishu/live-evidence-20261031/control-source.json)。第 2 页的测试码 `CEDAR-NEBULA-E720C8C9` 是公开 oracle，不是密码；query 未提供它的值，要求从 PDF 找出。PDF 在 Kind 节点的专用 hostPath，挂入 IRAOP `/cm/shared/iraop-corpus`；Kind 删除重建后的持久性未验证。

入库返回 pages_extracted=2、chunks_indexed=4、errors=0、failed_chunks=[]。立即 documents 列表为空，刷新后为 **1 PDF / 4 chunks**。collection 的 doc_count=4 是索引 chunks，不能写成 4 份 PDF。原 PDF 下载为 200，SHA256 一致。初始化 hook Job 已自动删除，不能声称保存了其成功 stdout；NotFound 结果也保留在证据中。

直接 HTTP query 用时 **50.77735306927934 秒**，得到正确测试码，sources 包含第 2 页和第 1 页，但正文给测试码标 `[1]`、bibliography 中 `[1]` 却是第 1 页。**检索内容命中，不等于引用映射正确。** 原始直接响应见 [remote-evidence/evidence/iraop-direct-validation.jsonl](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/iraop-direct-validation.jsonl)，不改写原答案来掩盖错误。

两次独立 OpenClaw 实验及本次告警会话的原生 iraop_query 都得到过规划文字/伪工具文本且 `sources=[]`。本次告警会话又确认集合和文件存在，并返回文档 URL/3781 bytes，但两次 query 均无来源。`isError=false` 只说明工具传输正常，不是研究成功。不能据此断言向量索引为空或根因一定在 semantic search；研究模型可能根本未完成真实工具循环。

### 5.1 模型工具协议隔离诊断：全部 4 个样本

诊断只声明一个无副作用的 lookup_validation_document schema，强制 tool_choice=required，temperature=0，max_tokens=256，没有实际执行工具。结果如下，完整原始模型消息、usage 和 tool args 见 [remote-evidence/evidence/model-tool-protocol.jsonl](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/model-tool-protocol.jsonl)：

| case | elapsedSeconds | finish_reason | tool_calls 数 | invalid_tool_calls 数 | usage_metadata（完整） |
| --- | --- | --- | --- | --- | --- |
| compat-stream | 2.9885516823269427 | tool_calls | 1 | 0 | null |
| compat-nonstream | 1.9561825362034142 | tool_calls | 0 | 0 | {"input_tokens": 299, "output_tokens": 224, "total_tokens": 523, "input_token_details": {}, "output_token_details": {}} |
| direct-stream | 1.896834425162524 | tool_calls | 1 | 0 | null |
| direct-nonstream | 1.4304510299116373 | tool_calls | 1 | 0 | {"input_tokens": 299, "output_tokens": 162, "total_tokens": 461, "input_token_details": {}, "output_token_details": {}} |


compat 非流式的 finish_reason=tool_calls，但解析 tool_calls 为空，是实际异常线索。独立进程只把 IRAOP 的 chat base URL 改为直连模型后，仍用 **1.8424160638824105 秒**返回伪工具文本和空 sources，见 [remote-evidence/evidence/research-direct-model-experiment.json](examples/alert-feishu/live-evidence-20261031/remote-evidence/evidence/research-direct-model-experiment.json)。因此没有把“绕过 compat”作为已证实修复，也未持久修改服务 endpoint。下一步需用经过 IRAOP 研究流程验证的模型/工具协议配置做对照，先要求原生 iraop_query 稳定命中和页码正确，再验收告警知识增强。

## 6. View / Edit / Auto 的实际隔离修复

本轮与通用 root/sudo fixture 不同：**只在 Spark 用户权限下创建独立 oneshot 用户服务** `mosaic-repair-validation.service`。ExecStart 只检查专用 `repair/ready` marker；缺失时 failed/exit-code/ExecMainStatus=1。wrapper 只创建该 marker、reset-failed/start 该服务，再输出全部状态字段。没有 sudo、root、GPU 或业务服务变更。

SSH key 采用 `restrict,command=".../repair/ssh_dispatch.py"`；dispatcher 只接受下列 exact argv，其他返回 126，并记录 full argv、allowed、exitCode、stdout、stderr。不要给接手人拷贝该私钥，而应按其权限授权工具使用或创建独立受限身份。完整 provisioning 实现见 [provision_repair.py](examples/alert-feishu/live-evidence-20261031/provision_repair.py)，allowlist 与初始状态见 [remote-evidence/repair/provision-evidence.json](examples/alert-feishu/live-evidence-20261031/remote-evidence/repair/provision-evidence.json)。

```json
["systemctl","status","--user","mosaic-repair-validation.service","--no-pager"]
["journalctl","--user","-u","mosaic-repair-validation.service","--no-pager","-n","50"]
["/home/spark-user/.local/share/mosaic-validation-20261031/repair/repair.sh"]
```

真正的 UI 操作是：New Chat（可访问名称，不是字符 `+`）→ 保持 View 发诊断/测试修复 → 新 Chat 选 Edit → 第一次审批点 Deny → 再发同一请求，在新审批卡核对主机/argv 后点 Approve once → 独立主机检查 → 重置该演示 fixture → 新 Chat 选 Auto → 阅读警示并点 Enable Auto → 发同一 wrapper → 独立检查 → 尝试一次约定的范围外 touch → 切回 View → 再建新 Chat 确认默认 View。

View 下 status 返回 exit3 是因为服务 failed，stdout 已取得实际诊断，不代表 SSH 连接失败。修复调用由 View policy 拒绝。Edit Deny 后 marker 仍不存在；新的 Approve once 后 marker 存在，状态 active/exited/success、ExecMainStatus=0。Auto 没有逐次审批，wrapper 执行后同样恢复。范围外 touch 返回126且文件不存在；不能借此宣称所有其他账户/命令都已做过负向验证。

Edit 审批 ID 和全部 UI POST 见 [edit-ui-summary.json](examples/alert-feishu/live-evidence-20261031/edit-ui-summary.json)、[edit-ui-requests.json](examples/alert-feishu/live-evidence-20261031/edit-ui-requests.json)；Auto 的警示/请求/审批轮询和结果见 [auto-ui-summary.json](examples/alert-feishu/live-evidence-20261031/auto-ui-summary.json)、[auto-ui-requests.json](examples/alert-feishu/live-evidence-20261031/auto-ui-requests.json)、[auto-repair-approval-polls.json](examples/alert-feishu/live-evidence-20261031/auto-repair-approval-polls.json)、[auto-boundary-approval-polls.json](examples/alert-feishu/live-evidence-20261031/auto-boundary-approval-polls.json)。真实 UI 截图保留在内部证据，因同时显示其他私网告警，未发到公开仓库。

独立主机证据保留完整状态和执行审计：

| 时点 | 证据 |
| --- | --- |
| Edit 前 | [edit-initial-host.json](examples/alert-feishu/live-evidence-20261031/edit-initial-host.json) |
| Edit Deny 后 | [edit-after-deny-host.json](examples/alert-feishu/live-evidence-20261031/edit-after-deny-host.json) |
| Edit Approve 前 | [edit-before-approve-host.json](examples/alert-feishu/live-evidence-20261031/edit-before-approve-host.json) |
| Edit Approve 后 | [edit-after-approve-host.json](examples/alert-feishu/live-evidence-20261031/edit-after-approve-host.json) |
| Auto 重置后 | [auto-initial-host.json](examples/alert-feishu/live-evidence-20261031/auto-initial-host.json) |
| Auto 修复后 | [auto-after-repair-host.json](examples/alert-feishu/live-evidence-20261031/auto-after-repair-host.json) |
| Auto 越界拒绝后 | [auto-after-boundary-host.json](examples/alert-feishu/live-evidence-20261031/auto-after-boundary-host.json) |


六条完整 forced-command SSH 审计记录见 [remote-evidence/repair/ssh-audit.jsonl](examples/alert-feishu/live-evidence-20261031/remote-evidence/repair/ssh-audit.jsonl)。UI Audit API=200，总计41条，本日5条（Edit切换、Deny、Approve once、Auto切换、View切换）逐条完整另存 [audit-current-events.json](examples/alert-feishu/live-evidence-20261031/audit-current-events.json)。Auto 的每次执行详情以 toolResult 和主机日志为依据，不能假定每一条都在当前 Audit 列表生成独立 mutation 行。

本实验验证交互式修复控制；没有把自动告警调查切成可写模式，也没有将服务修复与 vector(1) 合成规则绑定。恢复 marker 不会让独立的合成规则自动 resolve。

## 7. 飞书：用户需要先做的事与当前发送状态

用户已明确回复 **尚未创建群机器人**。当前没有目标群、Webhook 或签名密钥，没有发送任何测试消息。不能将离线 payload/签名校验写成已送达。

本轮已经用真实告警、审核后的结论、全部节点/Pod行和31点生成完整待发消息，unsigned原始wire payload为 **8867 UTF-8 bytes**，未发送、未截断；脱敏副本见 [feishu-review-payload.json](examples/alert-feishu/live-evidence-20261031/feishu-review-payload.json)、[feishu-reviewed-analysis.txt](examples/alert-feishu/live-evidence-20261031/feishu-reviewed-analysis.txt)、[feishu-dry-run.log](examples/alert-feishu/live-evidence-20261031/feishu-dry-run.log)。公开脱敏后地址长度变化，副本大小不等于原始wire字节数；manifest分别保留二者。

由目标群的有权限用户操作（若组织禁止自定义机器人，先找群/组织管理员）：群设置 → 群机器人 → 添加机器人 → 自定义机器人；命名例如 MOSAIC Alert Test，启用签名校验；若设置关键词，填 `test from Jeff Peng`；如果启用出口 IP 白名单，由实际发送机器的出口决定。界面以[飞书官方指南](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)为准。

用户在本机终端执行以下命令，通过隐藏输入保存凭据，不贴到聊天、Git、shell history 或截图。文件放在自己的受控目录，发给执行者的只需群名和文件路径：

```bash
python3 - <<'PY'
import getpass, os
from pathlib import Path
directory=Path.home()/'.config/mosaic'
directory.mkdir(parents=True,exist_ok=True,mode=0o700)
path=directory/'feishu-test.env'
if path.exists():raise SystemExit('File exists; update it using your credential manager instead of overwriting it.')
webhook=getpass.getpass('Feishu webhook (hidden): ')
secret=getpass.getpass('Feishu signing secret (hidden): ')
if any(c in value for value in (webhook,secret) for c in '\r\n'):
    raise SystemExit('Unexpected newline')
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream:
    stream.write('FEISHU_WEBHOOK='+webhook+'\nFEISHU_SIGNING_SECRET='+secret+'\n')
print(path)
PY
```

接下来执行者读取文件到进程内存，使用主手册的 `send_feishu_report.py` 先产出完整待审 payload，再显式 `--send`。验收需要同时有 API 业务 code=0 和群里同一 run_id 的可见消息；HTTP200不够。完整证据不因消息20KB上限而删行；过大时保留原文，使用双方认可且收件人能访问的附件/证据链接。双向飞书应用机器人和 PR #74 另行配置，不是这条单向群报告路线的前置。

## 8. 全部会话和工具索引

下列每个历史均完整保留，不用模型生成的缩略表替代：

| 实验 | sessionKey | 原始消息数 | toolResult 数 | 原始文件 |
| --- | --- | --- | --- | --- |
| 首次独立 Research | agent:default:validation-research-20261031 | 16 | 7 | [完整历史](examples/alert-feishu/live-evidence-20261031/native-research-history-gateway.json) |
| 独立 Research 重试 | agent:default:validation-research-retry-20261031 | 10 | 4 | [完整历史](examples/alert-feishu/live-evidence-20261031/native-research-retry-history-gateway.json) |
| View 修复策略 | agent:default:validation-repair-view-20261031 | 6 | 2 | [完整历史](examples/alert-feishu/live-evidence-20261031/repair-view-history-gateway.json) |
| Edit 拒绝与批准 | agent:default:session-2026-10-31t02-27-16-251z | 8 | 2 | [完整历史](examples/alert-feishu/live-evidence-20261031/edit-approved-history-gateway.json) |
| Auto 修复与边界 | agent:default:session-2026-10-31t02-29-24-691z | 8 | 2 | [完整历史](examples/alert-feishu/live-evidence-20261031/auto-boundary-history-gateway.json) |
| 告警初查与现场/Research 追加 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 25 | 14 | [完整历史](examples/alert-feishu/live-evidence-20261031/alert-followup-history-gateway.json) |


以下逐行列出这六个会话中的全部工具结果；完整每条 content/details/错误字段见 [tool-results-complete.json](examples/alert-feishu/live-evidence-20261031/tool-results-complete.json)，工具参数/提示词在对应 request、NDJSON 和历史中按服务实际返回保留。

| 序号 | sessionKey | messageIndex（0起） | toolName | toolCallId | isError |
| --- | --- | --- | --- | --- | --- |
| 1 | agent:default:validation-research-20261031 | 2 | iraop_list_collections | call_459bfad6778d425a8321b87b | False |
| 2 | agent:default:validation-research-20261031 | 4 | iraop_query | call_aaa28bfb334343979c265584 | False |
| 3 | agent:default:validation-research-20261031 | 6 | iraop_list_documents | call_3b8eeddb37cd48a9a2ccd0ee | False |
| 4 | agent:default:validation-research-20261031 | 8 | iraop_get_document | call_4d12cb89e67a49da909ca1a8 | False |
| 5 | agent:default:validation-research-20261031 | 10 | exec | call_136d85f45a0244a38a5d0a6f | True |
| 6 | agent:default:validation-research-20261031 | 12 | read | call_1e89da1003e8456fa9d75d3d | True |
| 7 | agent:default:validation-research-20261031 | 14 | exec | call_e29b37622b6b455aa7855104 | True |
| 8 | agent:default:validation-research-retry-20261031 | 2 | iraop_query | call_4edbab4cf8144ca3bbec1ead | False |
| 9 | agent:default:validation-research-retry-20261031 | 4 | iraop_list_collections | call_16da93d1930a4214898f2aca | False |
| 10 | agent:default:validation-research-retry-20261031 | 6 | iraop_list_documents | call_fce72cdf13134574b3032a22 | False |
| 11 | agent:default:validation-research-retry-20261031 | 8 | iraop_query | call_e9aac0b3fb33488ca536ae99 | False |
| 12 | agent:default:validation-repair-view-20261031 | 2 | run_remote_ssh | call_75bc1a32d5b14f699daf0855 | True |
| 13 | agent:default:validation-repair-view-20261031 | 4 | run_remote_ssh | call_1f856a1050ea4e70a3200f17 | True |
| 14 | agent:default:session-2026-10-31t02-27-16-251z | 2 | run_remote_ssh | call_9b00eb375bbf443582d47ea3 | True |
| 15 | agent:default:session-2026-10-31t02-27-16-251z | 6 | run_remote_ssh | call_ae6e5e3f7b5f4ce2a11b7fa1 | False |
| 16 | agent:default:session-2026-10-31t02-29-24-691z | 2 | run_remote_ssh | call_f1b4ae6a325844cabbbc8e9f | False |
| 17 | agent:default:session-2026-10-31t02-29-24-691z | 6 | run_remote_ssh | call_83a51ddff6a24267b7563d0c | True |
| 18 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 2 | run_kubectl | call_2bfe5d27711648568a1e329a | True |
| 19 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 3 | observability_query | call_d3a615c5941c42bca27379dd | False |
| 20 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 4 | run_kubectl | call_22fdb2f03e5e4e14b3dcc363 | False |
| 21 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 6 | observability_query | call_9e50d6937fcf435f9d03e375 | False |
| 22 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 7 | run_kubectl | call_c355e58377fa464b9ca5f793 | False |
| 23 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 8 | run_kubectl | call_11f6618bca5a4df39bc6512e | False |
| 24 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 12 | run_kubectl | call_57d58a6d0eb34bb9bf6ca371 | False |
| 25 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 13 | run_kubectl | call_74d723d5d18640578f7faea9 | False |
| 26 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 14 | observability_range_query | call_c12d7205bbcf493cb2dd29e2 | False |
| 27 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 15 | iraop_query | call_c3c8782c1dca437eb7a5a6a7 | False |
| 28 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 17 | iraop_list_collections | call_c155b5a2ea2b416eaf9c9d8d | False |
| 29 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 19 | iraop_list_documents | call_c6c35a2a098447cb8747d315 | False |
| 30 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 21 | iraop_query | call_c18dff3032d2475588e6c40b | False |
| 31 | agent:default:alert-alertmanager-0fa8cbd733f54a5a | 23 | iraop_get_document | call_d495fe94b0824f779cba0bdb | False |


原始模型回答里存在未证实的归因（如 zero-series 说明分组/静默、必须 Edit 才能读取文档）和缩写表/省略点。这些原答案完整保留作为模型表现证据，**本记录的事实表与工具原文才是审核后的结论**。没有把原模型摘要直接当成交接证据。

## 9. 给接手人的现有状态、重跑和撤销

保留 Research、CPU embedding 和 SSH-only Edit 供后续验证；普通新会话默认 View。只读告警调查与交互修复使用不同 session。接手人须取得自己的 Spark SSH 授权、UI 登录方式、部署映射/凭据库授权、这次 chart 与回滚备份的位置；可执行旧操作者的命令不代表可借用其私钥。

下面的用户服务命令必须由 **fixture 所属的 `spark-user` 账号**或经授权的维护入口执行。接手人可以使用自己获授权的公钥登录该账号；如果另有个人 Linux 账号，其 `$HOME` 和 `systemctl --user` 指向的是另一套用户目录/服务，不能直接当成本轮 fixture。交付者须明确维护账号和执行方式，不靠复制前任私钥取得访问。现场已读回该服务所属用户 `Linger=yes`、embedding unit=`enabled`；主机重启后的恢复仍未实测。

在正确维护身份下检查本轮服务与日志：

```bash
export PATH="$HOME/.local/bin:$PATH"
export LIVE_WORK="$HOME/.local/share/mosaic-validation-20261031"
helm --kube-context kind-mosaic-poc -n mosaic history mosaic
kubectl --context kind-mosaic-poc -n mosaic get pods,svc,pvc
systemctl --user show mosaic-embedding-validation.service mosaic-repair-validation.service   -p Id -p ActiveState -p SubState -p Result -p ExecMainStatus -p InvocationID
journalctl --user -u mosaic-repair-validation.service --no-pager -o short-iso
cat "$LIVE_WORK/repair/ssh-audit.jsonl"
test -f "$LIVE_WORK/repair/ready"
```

仅重置本轮演示 fixture（由部署方允许的账号执行）：

```bash
systemctl --user stop mosaic-repair-validation.service
rm -f "$LIVE_WORK/repair/ready"
systemctl --user reset-failed mosaic-repair-validation.service
if systemctl --user start mosaic-repair-validation.service; then
  printf '%s\n' 'Unexpected success; inspect fixture.'
else
  printf '%s\n' 'Expected isolated failure: marker absent.'
fi
systemctl --user show mosaic-repair-validation.service   -p ActiveState -p SubState -p Result -p ExecMainStatus -p InvocationID
```

再用新交互会话进行第 6 章的 exact wrapper 测试，或由维护人运行该 wrapper 恢复；不要为演示尝试真实服务/驱动命令。

回滚方案**未实际执行**：先导出证据，若仅撤销 Edit，回滚到本轮 revision9；若撤销本轮全部 chart 变更，回滚到原 revision8。确认目标 revision 内容后，由部署管理员执行：

```bash
export RESTORE_REVISION='9'
helm --kube-context kind-mosaic-poc -n mosaic rollback mosaic "$RESTORE_REVISION" --wait --timeout 20m
kubectl --context kind-mosaic-poc -n mosaic get pods
```

Helm rollback 不会自动删除本轮手工创建的用户服务、凭据 Secret、Kind corpus 或 authorized_keys 限制公钥。维护人需先确认无其他使用者，再撤销对应公钥行/Secret并清理这一个 prefix。不要覆盖整个 authorized_keys、删除已有密钥或直接打包整个工作目录；其中有密钥、token 和私有备份。撤销 embedding 会使当前 Research 失去 embedding 端点，应与回滚/替代配置协调。

## 10. 测试脚本本身的失败与证据范围

保留首次 health超时后重试成功、SSH偶发超时、Edit脚本误用字符 `+` 定位、Auto脚本首次停在 HTML警示检查、以及告警轮询脚本误以为同一 sessionKey 的消息数必增等失败日志。后者在独立 API 确认模型结束后只中断了轮询脚本，未中断已完成的调查。修正后的 selector 使用 New Chat / Enable Auto；告警完成判据同时核对 sessionId 是否更换，见对应完整脚本和日志。脚本选择器失败不等于产品审批失败，产品返回200也不等于研究质量通过。

公开附件是实测脚本与证据快照，包含现场占位符和版本前提，不是能对任意环境直接运行的安装器。原内部证据还保留完整浏览器图/DOM、所有30条告警和所有日期Audit；公开集合只发布本测试选定对象，保留该对象的全部行/列/消息。原始 chart/values/Secret 和私有镜像源码不发布。
