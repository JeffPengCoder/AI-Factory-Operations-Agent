<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->

**最新GPU补测：** [独立GPU实验](spark_gpu_alert_research_feishu_20261031.zh-CN.md)已走通受控缓存信号→告警→只读取证→知识检索→飞书，群内已确认本轮Run ID；原始模型存在事实错误和危险日志建议，**无人值守分析未通过**。首次自主输出、补充追问和Codex纠错分别保留；Codex修订不是产品自身能力，也不等于用户本人审核。
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Spark 上的告警、调查取证与飞书投递操作手册

**后续完整链路实测：** [新故障→新告警→日志→IRAOP→审核报告→飞书](spark_e2e_alert_research_feishu_20261031.zh-CN.md)已实际执行；新规则由CrashLoop指标触发，报告API成功，原始研究误归因及人工纠正完整保留。当前仍需要单条调查触发、审核和显式发送；本轮群内收件状态见新记录。

核验日期：2026-10-31。目标是完成一轮可以回放的操作：登录 Spark → 打开 MOSAIC → 开启 Alertmanager 轮询 → 创建合成告警 → 启动只读调查 → 导出告警、工具结果和分析 → 将审核后的报告发到飞书 → 清理测试规则。IRAOP 的配置与对照实验见[Research 操作说明](spark_iraop_alert_validation.zh-CN.md)，其后是[Edit/Auto 修复说明](spark_edit_auto_repair_validation.zh-CN.md)。

**先读最新的[Research补测、自动入库与飞书真实收件](spark_research_feishu_followup_20261031.zh-CN.md)。** 当前revision15保留；原生HTTP/MCP/UI检索和全部4条384维向量已核验，飞书API成功且用户确认同一run ID收件。直接上传API自动完成切片/入库，但发现原PDF下载404，客户继续采用持久corpus+file入库。通用业务文档质量、deep研究、旧UI独立进度及生产修复仍待验收。此前完整对照见[协议实测](spark_research_protocol_validation_20261031.zh-CN.md)，最初隧道/告警/受限修复见[完整记录](spark_live_validation_20261031.zh-CN.md)。新Alertmanager写入403仍是已有缺口，不能把旧合成规则写成本轮新注入；历史数据不覆盖。

另有[revision12追加实测](spark_live_validation_20261031_followup.zh-CN.md)：补测了Edit审批过期、IRAOP Pod重建和无证据query的incomplete呈现，当时原生检索仍失败；该快照完整保留。后续在同一个 [PR #2](https://github.com/JeffPengCoder/AI-Factory-Operations-Agent/pull/2) 增加默认关闭的Research工具协议兼容选项，Spark现已回填并启用。新环境须使用含该提交的chart或交付的真实定制chart，单独切到本PR文档分支不会获得代码修复。当前使用独立UI SSH转发。

这是公开仓库版本。实际 Spark 地址、SSH 用户、目标集群地址和密码由部署方单独提供；下文变量必须按现场填写。证据中的私网地址已替换为稳定的 `*.example.invalid` 占位符，私有集群别名替换为 `target-lab`。所有时间、指标数值、序列、错误和工具结果均保留，脱敏说明与校验值见 [manifest.json](examples/alert-feishu/evidence/manifest.json)。占位地址不能用于连接。

## 1. 先明确当前状态和每一步的验收标准

当前实测现场为Helm revision `15`，chart为`mosaic-stack-0.0.2-main.20261007233259.g4f4a6e75+teams71.20261029.iraop-evidence.20261031.2.research-tools.20261031.startup2`；MOSAIC UI image tag仍为`a011dcc8`，OpenClaw仍为`2026.6.10`。基线8，9启用Research，10启用SSH-only Edit，11/12加入无证据回答处理，13/14部署协议兼容及符号链接启动修复，15关闭临时追踪。原有真实私有依赖、Teams配置和12个应用Secret保留，共享模型未重启。这些是Spark现场记录，不代表仓库main的默认版本。以下历史行按其记录时点阅读，最新证据另列。

| 环节 | 已有证据 | 本次操作应观察什么 |
| --- | --- | --- |
| Prometheus 产生合成告警 | 2026-10-29 已验证 `vector(1)` 从 pending 变为 firing | 新 `run_id` 的规则和 `ALERTS` 时序 |
| Alertmanager → MOSAIC | 2026-10-31 在 UI 恢复 Auto pull，导入 30 条现有告警，选定合成条目字段匹配 | 同一 fingerprint、完整 labels/annotations、更新的 `lastSyncAt` |
| 调查与信息收集 | 本轮选定告警会话最终 25 条消息、14 个工具结果；2 节点、10 Pod、31 指标点完整保留；PrometheusRule 读取 Forbidden | 同一 sessionKey 下的工具名、参数/查询、完整结果及错误 |
| 页面阶段 | 最初实测时条目显示responding而hasActiveRun=false；最终revision15快照为active，30条告警，见最新记录；没有据此认定已修复 | 分开核对页面阶段、模型运行状态和原始告警 |
| 飞书 Webhook 发送 | 前期仅离线验证；本轮用户建好MOSAIC Alert Test自定义机器人，5445bytes完整报告实发，API code=0/StatusCode=0，用户确认同一run ID收件 | 新环境仍须API成功响应与目标群内匹配消息双重核验 |
| OpenClaw 飞书原生通道 | [PR #74](https://github.com/NVIDIA/AI-Factory-Operations-Agent/pull/74) 截至 2026-10-31 OPEN，Spark 未启用 | 选装后验收私聊/群 @、白名单、重启后的连接 |
| IRAOP / 文档检索：前期快照 | 1 PDF/4 chunks；直接查询曾引用错误，原生query多次空sources；失败原件均保留 | 与后续修复结果对照，不能删除失败样本 |
| IRAOP / 文档检索：revision15 | 协议兼容开启、追踪关闭；原生HTTP/MCP及三次View查询返回正确控制码和文件/页码；最后一次关联现有告警 | 复核真实工具结果、PDF原文、完整JSONL details；业务文档另验 |
| View / Edit / Auto | SSH-only 隔离用户服务实测：View 拒绝；Edit Deny/Approve once 生效；Auto 执行、越界命令拒绝；已恢复 View | exact argv、审批/工具结果、独立主机状态与审计 |

当前全部模块开关如下，避免把默认子配置误读成实际运行的服务：

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

当前聊天/分析使用模型推理、skills/工具说明和实际工具证据。Research已在指定控制集合上完成带来源的原生查询；前期无来源失败与后续成功都有完整记录。业务文档尚未入库/验收，也没有自动把所有告警接入Research或自动发飞书。Hardware Agent仍关闭，不能把普通告警调查描述成已做NVDebug硬件采集。

```text
目标集群：PrometheusRule → Prometheus → Alertmanager
                                           │ HTTP GET /api/v2/alerts
Spark / Kind：MOSAIC UI 服务端 Auto pull ←───┘
                  │ /api/alerts 与事件流
操作员浏览器：Alerts → 手动 Start Investigating / Auto investigate
                  │ 调查会话与 prompt
               OpenClaw → 只读 Kubernetes / Prometheus / Grafana 工具
                  │                └→ 显式 IRAOP 查询 → OpenSearch + PDF + 模型（控制集合已验）
                  └→ 分析与工具结果 → 操作员审核 → 发送脚本 → 飞书群机器人
```

最后一段发送由本手册脚本显式执行。当前部署没有“调查结束自动发飞书”的后台链路；装飞书插件也不会自动为 Alerts 页面增加这条链路。

## 2. 操作分工和准备

| 谁操作 | 第一次需要完成 | 以后每轮测试 |
| --- | --- | --- |
| 部署/集群管理员 | 提供 Spark SSH 访问、目标集群管理员访问、Prometheus/Alertmanager 地址；确认现有 MOSAIC 只读集群连接 | 只在目标集群创建和删除本轮测试规则；读取应用证据不需要管理员写权限 |
| MOSAIC 操作员 | 登录 UI，确认连接的是目标集群，准备本地证据目录 | 开轮询、启动调查、核对结果、保存证据 |
| 飞书群所有者/被允许添加机器人的用户 | 在目标群添加自定义机器人，配置签名/关键词/出口 IP 策略，将 Webhook 和签名密钥单独交给发送者 | 在群里核对报告的 run ID；不需要为每次告警重新创建机器人 |
| 后续 IRAOP 部署方 | 准备允许入库的 PDF、embedding 服务/密钥、模型配置和持久存储 | 验证本轮确实检索了文档，并检查引用是否支持结论 |

安装 MOSAIC 不会替客户登录飞书、创建群机器人、授权第三方应用或提供 PDF 语料。这些是客户/现场管理员需要做的操作。单向群通知走自定义机器人；私聊与群中双向问答走原生应用机器人，两者凭据和用途不同。

<a id="交付者需要另行交给接手人的资料"></a>

### 交付者需要另行交给接手人的资料

本文面向第一次接手这套环境的人。**已有部署和原操作者能登录，不代表接手人拥有相同权限。** 除操作手册外，交付者还需私下交付：填好的连接参数文件、凭据取用位置及访问授权、当前部署/回滚材料。接手人用自己的账号或 SSH key，按下面的检查点逐项验收。

可复制 [handover.env.example](examples/alert-feishu/handover.env.example) 为私下交付的 `connections.env`，填真实地址/账号和凭据库条目位置；不要在该文件放明文密码、私钥或机器人 token。公开仓库只保存模板，实际填写版通过约定的内部位置交接。

| 阶段 | 需要交给接手人的信息 | 交付者要做什么 | 接手人如何验证 |
| --- | --- | --- | --- |
| 当前演示必需 | Spark 地址、SSH 端口、登录用户名 | 填 SPARK_HOST/SPARK_SSH_PORT/SPARK_USER；说明跳板机/VPN要求 | 用自己的登录方式执行第 2.2 节，确认是预期 Spark |
| 当前演示必需 | Spark SSH 登录授权 | 为接手人的账号/公钥授权，或授予其凭据库中相应密码的取用权限；已有操作者的登录能力不能代替这一步 | 本人从自己的电脑成功 SSH，不依赖他人临时连接 |
| 当前演示必需 | 网络入口、VPN/跳板和 SSH host key 指纹 | 提供接入流程、所需组/角色及经管理员核对的主机指纹 | 能到达 Spark；主机指纹与交接值一致 |
| 当前演示必需 | MOSAIC 访问方法、UI 用户和密码取得方式 | 提供两层转发命令、端口、前台/常驻方式及断线恢复方法；交付 UI 凭据库条目或授权人代取 `mosaic-ui-auth` 的流程 | 接手人在自己的电脑建立隧道、登录并成功 GET `/api/alerts/alertmanager`，记录监听者/HTTP 响应；不能假定他能读取 K8s Secret |
| 当前演示必需 | 目标集群管理地址、管理员用户/context、MOSAIC 集群别名 | 填 TARGET_HOST/TARGET_SSH_PORT/TARGET_ADMIN/TARGET_CONTEXT/TARGET_CLUSTER；明确 Kind 是管理集群 | 读回目标集群身份与 Prometheus selector，确认不是在 Kind 上注入 |
| 当前演示必需 | 创建/清理测试规则的授权人和凭据 | 二选一：授予接手人适当的管理员登录方式；或指定会执行第 5/8 节命令的集群管理员与联系方法 | `apply --dry-run=server` 成功，且测试结束时有人能删除同一规则；不是只交一个只读账号 |
| 当前演示必需 | Prometheus/Alertmanager 地址、端口、认证/CA | 填监控变量、namespace、ruleSelector 标签；若另有认证，交付其取用方式 | 经 Spark 的隧道读取两个 API；Auto pull 的 baseUrl 指向同一环境 |
| 飞书投递必需 | 飞书目标群、群负责人、机器人名称 | 选定实际收件群，并让接手人能查看群及管理/使用机器人 | 群中可找到约定的机器人，并能核对测试消息 |
| 飞书投递必需 | Webhook、签名密钥及安全设置 | 在凭据库中授权接手人取用；同时交代关键词/出口 IP 白名单和密钥维护人 | 用隐藏输入发送后，业务响应成功且同一 run ID 的消息在目标群可见 |
| 仅双向飞书可选 | App ID/Secret、允许用户/群 ID、应用发布权限 | 只有采用 PR #74 通道时才交付；说明应用管理员及凭据条目 | 允许的私聊/群 @ 可回复；未授权来源不触发 |
| 后续 IRAOP 必需 | embedding 服务端点、模型、维度及 API key 取用方式 | 提供可用服务身份、配额/网络条件及凭据库授权 | health、入库和 query 都成功；只给 chat 模型 key 不够 |
| 后续 IRAOP 必需 | 允许入库的 PDF、来源、可用范围、控制问题/页码 | 交付实际文件和允许使用的说明，不只说“镜像里有知识库” | SHA-256、文档清单、命中页码和原文可逐项核对 |
| 后续扩展/恢复必需 | chat 端点、实际模型 ID、认证方式 | 交代现有服务所在位置与凭据管理入口，授权接手人按需访问 | `/v1/models` 与实际研究查询匹配；模型重启后仍可用 |
| 后续扩展/恢复必需 | NGC 镜像/chart 授权与拉取凭据取得方式 | 说明现有 imagePullSecret 是否可用、谁能续期/恢复、接手人如何取得真实 chart | 能获得真实依赖和目标架构镜像；不把文档 stub 当作部署包 |
| 后续扩展/回滚必需 | 当前 chart（含现场定制）、values/备份位置、revision 和版本 | 交付可访问的制品位置与恢复说明；原始 values 通过内部渠道交接 | 本人可取到制品、查看 history，并知道回滚到哪个 revision |
| 长报告共享必需 | 完整证据存放位置、收件人访问权限 | 提供内部存储/附件方案，授予接手人上传及收件人读取权限 | 用收件人身份打开报告，不能只验证发送者本机链接 |
| 后续 Edit/Auto 必需 | 可修复对象、运行身份、审批人和回滚责任人 | 交代批准的主机/namespace/服务范围，提供 MOSAIC 运行身份所需授权；见修复草案 | 接手人能演示 View 拒绝、Edit 审批、Auto 执行及恢复证据 |
| 所有阶段 | 环境维护人、凭据轮换/失效日期、遗留测试资源与未完成项 | 填交接联系人和待办；注明旧测试规则是否仍在 firing | 接手人知道访问失效、测试残留或误操作时联系谁，能区分已验证与计划 |

交付时附上逐项验收记录。当前演示的最小交接是前七项访问资料，加飞书两项和操作手册；接手人不需要因登录新电脑而重装 MOSAIC。IRAOP、原生飞书和 Edit/Auto 的资料在实施对应阶段前补齐。当前案例的历史版本与证据在第 1/9 节，接手人仍需现场复核。

### 2.1 本机准备变量

以下本机命令在 **Bash** 中执行（macOS 默认 zsh 用户先运行 `bash`）。需要 Git、SSH、Python 3.9+、jq、curl（支持 `--fail-with-body`）。Spark 上已有 kubectl、Helm、Kind、Docker；非交互 SSH 不一定包含它们的 PATH。

先检出包含本文的分支，再在仓库根目录执行。若已收到填写好的连接文件，可在 Bash 中 `source /path/to/connections.env`，再设置本轮 RUN_ID/EVIDENCE_DIR；下面列出全部变量以便人工核对：

```bash
bash
export SPARK_HOST='spark.example.com'
export SPARK_USER='YOUR_SPARK_SSH_USER'
export SPARK_SSH_PORT='22'
export TARGET_HOST='target-admin.example.com'
export TARGET_ADMIN='YOUR_TARGET_ADMIN_USER'
export TARGET_SSH_PORT='22'
export TARGET_CONTEXT='kubernetes-admin@kubernetes'
export MONITORING_NS='monitoring'
export KUBECTX='kind-mosaic-poc'
export MOSAIC_NS='mosaic'
export MOSAIC_RELEASE='mosaic'
export TARGET_CLUSTER='YOUR_MOSAIC_CLUSTER_ALIAS'
export PROMETHEUS_HOST='monitoring.example.com'
export PROMETHEUS_PORT='30090'
export ALERTMANAGER_HOST='monitoring.example.com'
export ALERTMANAGER_PORT='30093'
export RUN_ID="$(date -u +%Y%m%dt%H%M%Sz)"
export EVIDENCE_DIR="$HOME/mosaic-evidence/$RUN_ID"
export MOSAIC_URL='http://127.0.0.1:13000'
export PROM_URL='http://127.0.0.1:13090'
export AM_URL='http://127.0.0.1:13093'
umask 077
mkdir -p "$EVIDENCE_DIR"
printf '%s\n' "$RUN_ID" > "$EVIDENCE_DIR/run-id.txt"
```

`TARGET_HOST` 是被监控集群的管理入口；`TARGET_CLUSTER` 是 MOSAIC 内已注册的集群别名；`kind-mosaic-poc` 是运行 MOSAIC 的管理集群。三者不要混用。在本手册中，目标集群凭据只用于规则创建/清理；模型仍使用现有只读凭据。

### 2.2 登录 Spark 并确认部署

在本机执行；密码在 SSH 提示时输入，或使用已配置的 SSH key：

```bash
ssh -p "$SPARK_SSH_PORT" "$SPARK_USER@$SPARK_HOST"
```

在 Spark 执行：

```bash
export PATH="$HOME/.local/bin:$PATH"
kubectl --context kind-mosaic-poc -n mosaic get pods -o wide
helm --kube-context kind-mosaic-poc -n mosaic status mosaic
helm --kube-context kind-mosaic-poc -n mosaic history mosaic
kubectl --context kind-mosaic-poc -n mosaic get deploy openclaw mosaic-ui \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[*].image}{"\n"}{end}'
```

预期：UI/OpenClaw Pod Ready，Helm release deployed。不要把模型服务可用与 UI 主页能打开混为一项；后续调查必须产生实际回复和工具结果。

## 3. 打开 UI 与取证接口

### 3.1 本机终端 A：打开 UI 隧道

这里使用 **SSH 本地端口转发 + Kubernetes port-forward** 两层连接。`127.0.0.1` 是执行命令/打开浏览器的那台机器自身的回环地址；同样的地址出现在本机和 Spark 上，指向各自的本机。

```text
接手人电脑上的浏览器
  http://127.0.0.1:13000
        │ 本机 SSH 进程监听 127.0.0.1:13000
        │ SSH -L：通过 SPARK_HOST:SPARK_SSH_PORT 的加密连接转发
        ▼
Spark 的 127.0.0.1:13000
        │ Spark 上 kubectl port-forward 监听此端口
        │ Kubernetes API → Kind 中的 Service/Pod
        ▼
svc/mosaic-ui → MOSAIC UI Pod 的 3000 端口
```

下面一条命令同时建立本机 SSH 转发，并在 Spark 启动 kubectl 转发。`-L` 后第一个 `127.0.0.1:13000` 是本机监听地址，第二个是 **SSH 服务端 Spark 这一侧**连接的目标地址；末尾远程命令把 Spark 的该端口接到 UI 服务。

先在终端 A 载入第 2.1 节变量或填写好的 `connections.env`，然后运行并保留此终端：

```bash
ssh -t -p "$SPARK_SSH_PORT" -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:13000:127.0.0.1:13000 \
  "$SPARK_USER@$SPARK_HOST" \
  '$HOME/.local/bin/kubectl --context kind-mosaic-poc -n mosaic port-forward --address=127.0.0.1 svc/mosaic-ui 13000:3000'
```

浏览器打开 `http://127.0.0.1:13000`。默认 UI 用户是 `operator`。UI 密码和 Spark SSH 密码是两套凭据。在 Spark 另开终端读取 UI 用户名/密码，仅用于登录，不写入取证文件或 Git：

```bash
kubectl --context kind-mosaic-poc -n mosaic get secret mosaic-ui-auth \
  -o jsonpath='{.data.username}' | base64 -d
printf '\n'
kubectl --context kind-mosaic-poc -n mosaic get secret mosaic-ui-auth \
  -o jsonpath='{.data.password}' | base64 -d
printf '\n'
```

若 Spark 的 `13000` 已占用，先 `ss -ltnp '( sport = :13000 )'` 确认既有进程确实是该服务的 port-forward，再在本机复用：

```bash
ssh -N -p "$SPARK_SSH_PORT" -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:13000:127.0.0.1:13000 "$SPARK_USER@$SPARK_HOST"
```

不要终止不明进程来抢端口。关闭隧道用 `Ctrl+C`；SSH 中断后若需重开，先检查远端端口。

这是前台访问命令，需要 SSH 连接和两端转发进程持续运行。它本身没有安装开机启动、后台常驻或自动重连服务；关闭 SSH 终端会结束本机访问，电脑休眠、网络中断、Spark/相关 Pod 重启也可能使转发失效。恢复步骤见第 3.4 节。单独关闭浏览器通常不结束仍在运行的终端隧道，但会停止由该浏览器发起的新自动调查。

每位接手人需要在**自己的电脑**上用自己的访问授权建立隧道。把 `http://127.0.0.1:13000` 发给同事，会让他的浏览器访问他自己的电脑；交付者的 SSH 隧道不会随链接转给对方。如果现场另行部署了常驻访问服务，交接时应补充其名称、运行主机/用户、启停方法、日志位置和维护人。

### 3.2 本机终端 B：准备 Basic Auth 文件

后续 curl 使用单独的临时凭据文件，避免把密码放进命令行参数。终端 B 需要第 2.1 节的变量；所有 API/文件导出命令均在这个终端执行。

```bash
export AUTH_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mosaic-auth.XXXXXX")"
export MOSAIC_NETRC="$AUTH_DIR/netrc"
trap 'rm -f "$MOSAIC_NETRC"; rmdir "$AUTH_DIR" 2>/dev/null || true' EXIT
python3 - <<'PY'
import getpass, json, os
from pathlib import Path
password = getpass.getpass('MOSAIC operator password: ')
if '\n' in password or '\r' in password:
    raise SystemExit('Password must not contain a newline')
path = Path(os.environ['MOSAIC_NETRC'])
path.write_text('machine 127.0.0.1 login operator password ' + json.dumps(password) + '\n')
path.chmod(0o600)
PY
curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" \
  "$MOSAIC_URL/api/alerts/alertmanager" | tee "$EVIDENCE_DIR/pull-before.json"
```

预期 HTTP 200、`success=true`。401 表示 UI 凭据错误；连接拒绝优先检查终端 A。临时认证文件位于证据目录之外，不打包。

### 3.3 本机终端 C：只读访问 Prometheus / Alertmanager

复制第 2.1 节所需 SSH/监控变量到终端 C，保留隧道运行：

```bash
ssh -N -p "$SPARK_SSH_PORT" -o ExitOnForwardFailure=yes \
  -L "127.0.0.1:13090:$PROMETHEUS_HOST:$PROMETHEUS_PORT" \
  -L "127.0.0.1:13093:$ALERTMANAGER_HOST:$ALERTMANAGER_PORT" \
  "$SPARK_USER@$SPARK_HOST"
```

这些目标是 **从 Spark 可以访问**的监控地址，不是浏览器中的 localhost。在当前现场监控接口不要求单独认证；客户若配置了认证/TLS，应使用其提供的凭据和 CA，不能把 UI 的 operator 凭据当作监控凭据。

### 3.4 确认连接有效，并在断线后恢复

已经渲染的页面可以在后端连接失效后继续显示。应发起新的 HTTP 请求，或刷新页面并检查新的 API 响应；看到旧页面内容不能证明隧道、UI API 或模型仍然可用。

保留终端 A，在终端 B 逐层检查。第一条在 macOS 执行；Linux 接手人可用本机的 `ss -ltnp '( sport = :13000 )'` 替代 lsof：

```bash
# 1. 本机端口：预期监听者为本轮 SSH 转发进程。
lsof -nP -iTCP:13000 -sTCP:LISTEN

# 2. Spark 端口：预期监听者为对应 UI 的 kubectl port-forward。
ssh -p "$SPARK_SSH_PORT" "$SPARK_USER@$SPARK_HOST" \
  'ss -ltnp "( sport = :13000 )"'

# 3. 新 HTTP 请求：绕过本机代理，直接验证这条回环连接。
curl --noproxy '*' --connect-timeout 3 --max-time 5 -sS \
  -o /dev/null -w 'HTTP %{http_code}\n' "$MOSAIC_URL/api/health"
```

本机无监听时 lsof 通常无输出并以非零退出；Spark 的 ss 仅有表头表示该端口无监听。`/api/health` 正常应返回 HTTP 200；HTTP 401/403 表示已有 HTTP 服务响应，需要核对所请求接口的认证/授权；`curl: (7)` 和 `HTTP 000` 表示本次没有建立成功的 HTTP 连接，先排查隧道。

完成第 3.2 节认证设置后，还要验证实际 MOSAIC API，而不是只检查任意进程占用了 13000：

```bash
curl --noproxy '*' --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" \
  --connect-timeout 3 --max-time 10 \
  "$MOSAIC_URL/api/alerts/alertmanager" \
  | tee "$EVIDENCE_DIR/access-pull-status.json"
```

预期 `success=true`，并核对 baseUrl 指向本次交接的监控环境。保存本机/Spark 监听检查的完整输出与时间，以及这次新 API 响应，作为接手人自己建立连接的证据。UI API 可访问后，聊天/模型可用性仍按第 6 节实际回复和工具结果验证。

| 检查结果 | 恢复操作 | 恢复后验收 |
| --- | --- | --- |
| 本机和 Spark 均无 13000 监听 | 在终端 A 重跑第 3.1 节第一条 SSH + kubectl 命令 | 两端有预期监听者，新 HTTP/API 请求成功 |
| Spark 有正确的 UI port-forward，本机无监听 | 复用第 3.1 节的 `ssh -N -L ...` 命令，保留终端 | 本机 SSH 监听，认证 API 返回本环境状态 |
| 本机有 SSH 监听，Spark 无转发 | 对自己这次的 SSH 终端按 Ctrl+C，确认远端端口状态后重跑完整两层命令 | 两端检查都恢复；只重开浏览器不能恢复缺失的远端转发 |
| 13000 被不明进程或另一环境占用 | 先核对进程身份、目标与运行所有者；联系维护人处理，避免连接错环境 | 确认实际监听者和 API 环境后再测试告警 |
| 端口和 HTTP 正常，但业务接口 401/403 | 核对 UI 用户/密码取得方式及权限 | 认证 API 返回成功；反复重建隧道不会修正凭据 |
| 页面还显示内容，新请求失败 | 按上述监听检查定位断点，恢复后刷新页面 | 新请求成功；截图中的旧内容不作为连接成功证据 |

上述操作只维护访问通道，不重装 MOSAIC 或创建新告警。断线后还应重新检查 Auto pull 状态；需要自动调查时，重新打开浏览器并确认 Auto investigate 设置。

## 4. 在界面打开告警轮询

1. 在 MOSAIC 页面选择 **Alerts** 页签/面板。
2. 先关闭 **Auto investigate**，以便先观察投递，再只调查本轮测试告警。
3. 打开 **Auto pull**。它让 UI **服务端进程**定时向 `MOSAIC_ALERTMANAGER_URL/api/v2/alerts` 拉取活动告警。
4. 点击 **Refresh** 可立即拉取一次。当前版本默认间隔 30 秒；按钮不是修改轮询周期或 URL 的输入框。
5. 观察出现的来源 `Alertmanager`、告警名称和阶段。若页面没有搜索框，使用浏览器查找 `MosaicSyntheticAlert` 或 `test from Jeff Peng`，并用 API 的 `run_id` 做精确筛选。

在终端 B 用 API 保存同一设置的证据：

```bash
# 与打开 Auto pull 对应；这是一个明确的设置动作。
curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" \
  -H 'Content-Type: application/json' -X POST \
  -d '{"enabled":true}' "$MOSAIC_URL/api/alerts/alertmanager" \
  > "$EVIDENCE_DIR/pull-enable.json"

# 与 Refresh 对应：立即拉取一次。
curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" -X PUT \
  "$MOSAIC_URL/api/alerts/alertmanager" > "$EVIDENCE_DIR/pull-refresh.json"

curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" \
  "$MOSAIC_URL/api/alerts/alertmanager" > "$EVIDENCE_DIR/pull-status.json"
jq '.status' "$EVIDENCE_DIR/pull-status.json"
```

验收字段：`enabled=true`、`baseUrl` 指向目标 Alertmanager、`intervalMs=30000`、`lastSyncAt` 持续更新、无 `lastError`。`lastImported=0` 只表示这次没有导入**新的**告警，可能已经拉到同一 fingerprint；结合 `lastSeenCount` 与列表判断。

若 `baseUrl` 不对，在 Spark 只读检查实际配置，不从整个 env 输出其他凭据：

```bash
kubectl --context kind-mosaic-poc -n mosaic exec deploy/mosaic-ui -- node -e \
  'console.log(process.env.MOSAIC_ALERTMANAGER_URL); console.log(process.env.MOSAIC_ALERTMANAGER_POLL_MS || "30000 (runtime default)")'
```

需要改 URL 时，应修改部署维护的 `observability.alertmanagerUrl` 并用保存的 chart/values 做受控 Helm upgrade；不要临时 `kubectl set env` 后留下与 Helm 不一致的安装。本轮现场已正确配置，无需改动。该版本轮询开关和列表是服务进程内状态，重启 UI 后重新检查；不能将它当作持久消息队列。

**Auto pull 与 Auto investigate 的执行位置不同。** 前者是服务端定时拉取；后者由当前打开 MOSAIC 网页的浏览器接收告警、创建调查会话并提交 prompt。关闭浏览器后不能依靠它启动新的自动调查；已经提交的运行是否完成需查历史/`hasActiveRun`。独立的 cluster-monitor 定时巡检不是 Alerts 的后台自动调查器。

## 5. 注入一条不影响 GPU 的测试告警

此处“注入”是创建始终满足 `vector(1)` 的 Prometheus 告警规则，不修改 DCGM 指标、GPU 温度、驱动、业务 Pod。现有 Alertmanager 路由仍可能将测试告警发送给其已有接收者，因此在约定的测试集群/窗口进行。

### 5.1 确认 Prometheus 会选中什么规则

在终端 B，通过管理员入口读取 selector：

```bash
ssh -p "$TARGET_SSH_PORT" "$TARGET_ADMIN@$TARGET_HOST" \
  "kubectl --context '$TARGET_CONTEXT' -n '$MONITORING_NS' get prometheus -o json" \
  > "$EVIDENCE_DIR/prometheus-selector.json"
jq '.items[] | {name:.metadata.name,namespace:.metadata.namespace,ruleSelector:.spec.ruleSelector,ruleNamespaceSelector:.spec.ruleNamespaceSelector}' \
  "$EVIDENCE_DIR/prometheus-selector.json"
```

当前现场是 `ruleSelector.matchLabels.release=kube-prometheus-stack`。只有现场同样使用这个 selector，才填下列值；其他安装按读回值修改模板 metadata labels，并确认 namespace 也被选中。不要默认所有集群都叫这个 Helm release。

### 5.2 生成、预览并应用规则

每轮采用新的 `RUN_ID`，避免复用旧 fingerprint 或浏览器已调查缓存。模板完整内容在 [synthetic-alert.yaml.in](examples/alert-feishu/synthetic-alert.yaml.in)。

```bash
export RULE_RELEASE='kube-prometheus-stack'
python3 - <<'PY'
import os, re
from pathlib import Path
text = Path('docs/examples/alert-feishu/synthetic-alert.yaml.in').read_text()
for key in ('RUN_ID', 'MONITORING_NS', 'RULE_RELEASE'):
    value = os.environ[key]
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', value):
        raise SystemExit(f'Invalid Kubernetes/template value: {key}')
    text = text.replace('${' + key + '}', value)
Path(os.environ['EVIDENCE_DIR'], 'synthetic-alert.yaml').write_text(text)
PY
cat "$EVIDENCE_DIR/synthetic-alert.yaml"

# 服务端 dry-run：验证 CRD/schema、管理员权限和目标 context。
ssh -p "$TARGET_SSH_PORT" "$TARGET_ADMIN@$TARGET_HOST" \
  "kubectl --context '$TARGET_CONTEXT' -n '$MONITORING_NS' apply --dry-run=server -f -" \
  < "$EVIDENCE_DIR/synthetic-alert.yaml"

# 由目标集群管理员执行实际创建。
ssh -p "$TARGET_SSH_PORT" "$TARGET_ADMIN@$TARGET_HOST" \
  "kubectl --context '$TARGET_CONTEXT' -n '$MONITORING_NS' apply -f -" \
  < "$EVIDENCE_DIR/synthetic-alert.yaml" | tee "$EVIDENCE_DIR/rule-apply.txt"
ssh -p "$TARGET_SSH_PORT" "$TARGET_ADMIN@$TARGET_HOST" \
  "kubectl --context '$TARGET_CONTEXT' -n '$MONITORING_NS' get prometheusrule 'mosaic-smoke-$RUN_ID' -o json" \
  > "$EVIDENCE_DIR/applied-rule.json"
```

验收：创建的是 `monitoring/mosaic-smoke-<run_id>`；表达式 `vector(1)`；`for: 30s`；labels 有 `mosaic_test="true"` 与 `run_id`；annotation `test_from` 保留原文 **test from Jeff Peng**。保留读回对象的 UID、creationTimestamp 与完整 spec。

### 5.3 逐跳看证据

等待规则发现、至少 30 秒 pending 和下一次拉取；这几段间隔叠加，不能要求创建后立刻显示。终端 B 执行以下采样；未 firing 时隔 10 秒重跑，保留每次完整快照：

```bash
export SAMPLE_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export SAMPLE_DIR="$EVIDENCE_DIR/samples/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$SAMPLE_DIR"

curl --fail-with-body -sS -G "$PROM_URL/api/v1/rules" \
  --data-urlencode 'type=alert' > "$SAMPLE_DIR/prometheus-rules.private.json"
jq '[.data.groups[].rules[] | select(.name=="MosaicSyntheticAlert" and .labels.run_id==env.RUN_ID)]' \
  "$SAMPLE_DIR/prometheus-rules.private.json" > "$SAMPLE_DIR/test-rules.json"

curl --fail-with-body -sS -G "$PROM_URL/api/v1/query" \
  --data-urlencode "query=ALERTS{alertname=\"MosaicSyntheticAlert\",run_id=\"$RUN_ID\"}" \
  > "$SAMPLE_DIR/prometheus-alerts.json"
curl --fail-with-body -sS -G "$AM_URL/api/v2/alerts" \
  --data-urlencode 'filter=alertname="MosaicSyntheticAlert"' \
  --data-urlencode "filter=run_id=\"$RUN_ID\"" > "$SAMPLE_DIR/alertmanager.json"

curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" \
  "$MOSAIC_URL/api/alerts" > "$SAMPLE_DIR/mosaic-all.private.json"
jq '[.alerts[] | select(.labels.run_id==env.RUN_ID)]' \
  "$SAMPLE_DIR/mosaic-all.private.json" > "$SAMPLE_DIR/mosaic-test.json"
curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" \
  "$MOSAIC_URL/api/alerts/alertmanager" > "$SAMPLE_DIR/pull.json"

jq -n --arg checkedAt "$SAMPLE_AT" \
  --slurpfile rules "$SAMPLE_DIR/test-rules.json" \
  --slurpfile prometheus "$SAMPLE_DIR/prometheus-alerts.json" \
  --slurpfile alertmanager "$SAMPLE_DIR/alertmanager.json" \
  --slurpfile mosaic "$SAMPLE_DIR/mosaic-test.json" \
  --slurpfile pull "$SAMPLE_DIR/pull.json" \
  '{checkedAt:$checkedAt,rules:$rules[0],prometheus:$prometheus[0],alertmanager:$alertmanager[0],mosaic:$mosaic[0],pull:$pull[0]}' \
  > "$SAMPLE_DIR/snapshot.json"

jq '.rules[] | {name,state,health,lastEvaluation,labels}' "$SAMPLE_DIR/snapshot.json"
jq '.alertmanager[] | {fingerprint,status,labels,annotations}' "$SAMPLE_DIR/snapshot.json"
jq '.mosaic[] | {id,stage,status,fingerprint,labels,annotations}' "$SAMPLE_DIR/snapshot.json"
```

屏幕输出是便于查看的摘要；`snapshot.json` 和各 API 文件保留完整选中对象。两个 `.private.json` 还包含其他规则/告警，只留在本地，不能直接公开或发群。

成功后，保存本轮唯一告警并用 fingerprint 严格比对：

```bash
jq -e 'length == 1' "$SAMPLE_DIR/mosaic-test.json"
jq '.[0]' "$SAMPLE_DIR/mosaic-test.json" > "$EVIDENCE_DIR/alert.json"
jq -e --slurpfile m "$EVIDENCE_DIR/alert.json" \
  'any(.[]; .fingerprint==$m[0].fingerprint and .status.state=="active" and .annotations.test_from=="test from Jeff Peng")' \
  "$SAMPLE_DIR/alertmanager.json"
jq -e '.id == ("alertmanager:" + .fingerprint) and .annotations.test_from=="test from Jeff Peng"' \
  "$EVIDENCE_DIR/alert.json"
export ALERT_ID="$(jq -r '.id' "$EVIDENCE_DIR/alert.json")"
```

同时确认规则 state 为 `firing`。不能用 Alertmanager 总告警数或接收计数器增长证明**这条**告警已送到 MOSAIC；要比对本轮 run ID、fingerprint 和 `test_from`。

## 6. 触发信息收集，并确认真的收集到了什么

### 6.1 推荐先手动调查一条

在 **Alerts** 中定位本轮条目，点击 **Start Investigating ❯**。已有调查的条目点击 **Open Chat**；普通会话列表中也可打开对应 Alert 会话。阶段通常从 Active 变为 Responding；右侧聊天会出现包含原始 payload、labels、annotations 和时间的调查 prompt。

对于 `vector(1)`，模型应识别这是合成测试，没有真实硬件故障。可在同一会话补充：

```text
这是 test from Jeff Peng 的合成告警，run_id=<本轮 RUN_ID>。
请仅做只读核验，目标集群是 <TARGET_CLUSTER>，不要操作运行 MOSAIC 的 Kind 管理集群。
1. 核对告警标签、fingerprint、开始时间；区分 Prometheus firing、Alertmanager active、MOSAIC stage。
2. 查询最近 30 分钟 ALERTS{alertname="MosaicSyntheticAlert",run_id="<本轮 RUN_ID>"}，返回查询、起止时间、步长与全部数据点。
3. 按实际可用的只读工具核查相关规则、监控 Pod 状态、Events 和相关日志；逐项列出成功、Forbidden、无数据或未尝试。
4. 不要查询 Secret，不要注入 GPU 故障，不要删除资源，不要把总量指标当作这条告警送达证据。
5. 输出证据表、判断、限制和管理员清理命令。明确“合成测试，无实际 GPU 故障”；不要宣称已修复。
```

这份清单是要求模型执行的任务，不能当作已经完成的采集。工具结果决定实际完成了哪些项。

### 6.2 再验收 Auto investigate

需要测试自动发起时，保留浏览器打开，开启 **Auto investigate**，再用**新 RUN_ID**创建一条规则。它会对当前列表中尚未处理的 active 告警发起调查，不只处理测试条目；现场有其他告警时优先使用上一节的单条手动方式。

当前版本普通手动会话 key 形如 `agent:default:alert-alertmanager-<fingerprint>`；自动会话形如 `agent:default:mosaic-automation-alert-alertmanager-<fingerprint>`。这是该 UI build 的行为，验收时从 sessions API 读回实际 key，不只拼字符串。自动会话受只读策略约束；人工操作也保持 View，不切换 Edit/Auto。

浏览器开发者工具 **Network** 可观察：`/api/alerts/events` 收到告警，`PATCH /api/alerts` 更新阶段，`POST /api/openclaw/chat/stream` 提交调查。保存本轮相关请求/响应或截图；HAR 可能含认证信息，原始 HAR 留在本地。

### 6.3 导出完整会话，不只复制最后一段回答

在终端 B 列出会话，选择本轮 fingerprint 对应项：

```bash
curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" \
  "$MOSAIC_URL/api/openclaw/sessions" > "$EVIDENCE_DIR/sessions.private.json"
jq --arg fp "$(jq -r '.fingerprint' "$EVIDENCE_DIR/alert.json")" \
  '.sessions[] | select(.sessionKey | contains($fp))' "$EVIDENCE_DIR/sessions.private.json"
export SESSION_KEY='填入上一步实际的 sessionKey'

curl --fail-with-body -sS --netrc-file "$MOSAIC_NETRC" -G \
  "$MOSAIC_URL/api/openclaw/chat" \
  --data-urlencode "sessionKey=$SESSION_KEY" --data-urlencode 'limit=1000' \
  > "$EVIDENCE_DIR/investigation-api.json"
```

当前 UI API 的 `messages` 会合并 assistant 活动；原始 Gateway 响应在 `history.stdout`。本次旧会话就是 UI 4 条、Gateway 19 条，直接只看 UI 数组会漏掉逐个 toolResult。提取全部原始消息并另存最新完整分析：

```bash
python3 - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['EVIDENCE_DIR'])
api = json.loads((p/'investigation-api.json').read_text())
if not api.get('success'):
    raise SystemExit('History request failed; retain full response')
history = api.get('history', {})
raw = json.loads(history['stdout']) if history.get('stdout') else {'messages': api.get('messages', [])}
(p/'investigation-gateway.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2)+'\n')
messages = raw.get('messages', [])
if api.get('rawMessageCount', 0) >= 1000 or any(m.get('truncated') for m in messages):
    raise SystemExit('History may be capped; retrieve the session transcript before calling the export complete')
tools = [m for m in messages if m.get('role') == 'toolResult']
(p/'tool-results.json').write_text(json.dumps(tools, ensure_ascii=False, indent=2)+'\n')
answers = [m for m in messages if m.get('role') == 'assistant']
if not answers:
    raise SystemExit('No assistant response yet')
def text(m):
    c = m.get('content', '')
    return c if isinstance(c, str) else '\n'.join(b.get('text','') for b in c if b.get('type')=='text')
(p/'analysis-latest-unreviewed.md').write_text(text(answers[-1])+'\n')
(p/'analysis-all-unreviewed.md').write_text('\n\n'.join(text(m) for m in answers)+'\n')
print({'rawMessages':len(messages), 'toolResults':len(tools), 'hasActiveRun':api.get('hasActiveRun')})
PY
```

有多轮追问时，“最新一条”可能是简短回顾；审核 `analysis-all-unreviewed.md` 与完整原始 JSON，选用完整调查报告后写入 `analysis-reviewed.md`，不要让回顾替代证据。长会话还可能受服务端 maxChars 限制；若出现截断提示、较早消息缺失或计数不符，需由管理员保存 OpenClaw 对应 session 的原始 transcript。保留 API 的完整错误/截断字段。

界面中打开 **Audit**，选择相同会话和时间范围，查看工具名称、参数、成功/失败状态；工具调用卡片/子 agent 面板可看返回内容。需要 API 导出时，使用浏览器 Network 中该版本实际的 `/api/audit?...` 查询参数，避免猜测过滤参数而误取别的会话。补充运行日志，在 Spark 执行并保存到本地：

```bash
ssh -p "$SPARK_SSH_PORT" "$SPARK_USER@$SPARK_HOST" \
  '$HOME/.local/bin/kubectl --context kind-mosaic-poc -n mosaic logs deploy/openclaw -c gateway --since=30m --timestamps' \
  > "$EVIDENCE_DIR/openclaw.private.log"
```

日志是补充，完整 toolResult 才能说明“查了什么、返回什么”。禁止仅凭日志中出现工具名就说采集成功。

### 6.4 证据应包含哪些信息

| 证据 | 怎么看 | 如何解释 |
| --- | --- | --- |
| 原始告警 | `alert.json`：payload、labels、annotations、fingerprint、startsAt、source | 证明本轮收到的内容，不能证明根因 |
| Prometheus 指标 | range query 的 query、start/end、stepSeconds、每条 metric labels、全部 values、truncated | 确认现场数据及时间窗口；空数组是无匹配序列，不是值为零 |
| Kubernetes | `run_kubectl` 的 cluster、实际命令、exitCode、stdout、stderr、mutating | `Forbidden` 必须保留；没有 `alerts` 这种标准资源类型 |
| 日志/Events | 具体集群、namespace、Pod、时间、命令和原文 | 未调用则写“未采集”，不要从健康摘要推断已读取日志 |
| 模型分析 | 完整 assistant 回答 + 所依据的 toolCallId | 将现场事实、推测、文档建议分开；完成分析不等于修复 |
| 运行关联 | RUN_ID、ALERT_ID、fingerprint、SESSION_KEY、toolCallId、时间 | 把每一步对上同一次测试，防止引用旧会话 |
| 后续 IRAOP | query/depth/collections、工具返回、sources、PDF 页码 | 仅证明查询了文档；仍需与当前现场证据交叉核对 |

当前只读账号不能读取某些 monitoring CRD。不要为演示改成 cluster-admin；由管理员独立导出规则，或评估后给专用只读账号增加确需的 `get/list/watch` 权限。收到 Forbidden 时，本轮可以证明投递/部分指标采集成功，但该项 CRD 采集失败。

<a id="7-将告警与分析发到飞书"></a>

## 7. 将告警与分析发到飞书

### 7.1 先走单向群通知：自定义机器人 Webhook

**本现场已于2026-10-31完成真实投递：** 用户创建MOSAIC Alert Test机器人并提供受保护凭据，签名前5445bytes报告未截断，业务响应code=0/StatusCode=0，用户确认run ID `feishu-continued-validation-20261031T071049Z`一致。完整payload、业务响应和收件确认在[最新记录第5章](spark_research_feishu_followup_20261031.zh-CN.md)。本现场不需要重复创建；其他客户按以下步骤准备自己的群和授权。当前是操作员显式投递，自动报告发布仍待开发。

这条路线不依赖 PR #74，不需要将 Spark 暴露成公网回调。操作在**发送脚本运行的机器**发起 HTTPS 请求；从本机执行时，飞书看到的是本机网络出口，若迁到 Spark，则使用 Spark 的出口。

**还没有测试群时，由客户在飞书电脑端先建群：**

1. 打开飞书客户端的消息页，在头像右侧/消息列表上方找到「＋／创建」。
2. 选择「创建群组」，输入群名`MOSAIC Alert Test`，选择普通聊天类型。
3. 选择实际参与验收的成员，点「创建」。测试消息会发给这个群的成员。
4. 进入刚建好的群，点右上角「…」打开群设置，再找「群机器人／机器人」。它位于群内设置，不是工作台里的应用列表。不同客户端版本可能显示齿轮或设置文字。
5. 点「添加机器人」→「自定义机器人」，名称仍可用`MOSAIC Alert Test`，描述填“接收MOSAIC告警与分析报告”。若缺少入口，由群主或组织管理员核对添加机器人权限；不要把单聊界面当群设置。

参照[飞书官方建群说明](https://www.feishu.cn/hc/zh-CN/articles/360025113754-%E5%88%9B%E5%BB%BA%E7%BE%A4%E7%BB%84)和[群内机器人说明](https://www.feishu.cn/hc/zh-CN/articles/360024984973-%E5%9C%A8%E7%BE%A4%E7%BB%84%E4%B8%AD%E4%BD%BF%E7%94%A8%E6%9C%BA%E5%99%A8%E4%BA%BA)。创建机器人后启用签名校验，保存Webhook和签名密钥；若启用关键词，可使用`test from Jeff Peng`；若启用IP白名单，填实际发送端的出口IP。自定义机器人支持内部群和外部群，具体管理权限取决于群/组织策略。按[飞书官方自定义机器人指南](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)核对当前界面。

这些飞书操作需要**客户/群管理者本人完成**。通过凭据库授权发送者，或在本机权限600的凭据文件中保存`FEISHU_WEBHOOK`和`FEISHU_SIGNING_SECRET`并只交文件路径；不要把值贴到聊天、Git、PR或截图。群与机器人建好后，仍需执行第7.2节的发送脚本，再按第7.3节到群里验收；不会因创建机器人就自动推送所有告警。

自定义机器人服务当前群，不是可私聊的完整应用机器人。Webhook 本身属于凭据，不能写进 Git、PR、截图或群消息。本例脚本用隐藏输入读取 Webhook 和密钥；不把它们写进报告。

### 7.2 审核、预览、发送

将审核后的**完整**分析保存为 `$EVIDENCE_DIR/analysis-reviewed.md`。它至少交代：合成/真实事件、告警时间与对象、实际成功和失败的采集、结论与置信限制、人工下一步、IRAOP 是否使用。完整数据点保留在原始证据文件中，不用一句“约 30 个点”替代。

可以先复制完整原始分析，再逐项核对工具证据并修正不受支持的表述；原始文件继续保留：

```bash
cp "$EVIDENCE_DIR/analysis-all-unreviewed.md" "$EVIDENCE_DIR/analysis-reviewed.md"
vi "$EVIDENCE_DIR/analysis-reviewed.md"
```

在仓库根目录、终端 B 先预览。脚本见 [send_feishu_report.py](examples/alert-feishu/send_feishu_report.py)：

```bash
python3 docs/examples/alert-feishu/send_feishu_report.py \
  --alert "$EVIDENCE_DIR/alert.json" \
  --analysis "$EVIDENCE_DIR/analysis-reviewed.md" \
  --session-key "$SESSION_KEY" --run-id "$RUN_ID" \
  --output "$EVIDENCE_DIR/feishu-payload.json"
python3 -m json.tool "$EVIDENCE_DIR/feishu-payload.json"
```

预览不发送网络请求。确认收件群、报告内容后，显式 `--send`：

```bash
python3 docs/examples/alert-feishu/send_feishu_report.py \
  --alert "$EVIDENCE_DIR/alert.json" \
  --analysis "$EVIDENCE_DIR/analysis-reviewed.md" \
  --session-key "$SESSION_KEY" --run-id "$RUN_ID" \
  --output "$EVIDENCE_DIR/feishu-payload.json" \
  --send --response "$EVIDENCE_DIR/feishu-response.json"
```

签名按照飞书规则计算：以 `timestamp + "\n" + secret` 为 HMAC-SHA256 的 key，对空消息求摘要，再 Base64；请求 body 加 `timestamp` 与 `sign`。脚本检查业务 `code=0`（兼容旧 `StatusCode=0`），不能只凭 HTTP 200 判断成功。传输超时可能处于“已送达但响应丢失”，先看群，再决定是否重发；示例不自动重试。

官方请求体上限 20 KB；示例保守限制为 20,000 UTF-8 字节（含签名字段），超过时明确报错，保留完整 payload，**不截断分析**。长报告/原始数据应先放到客户认可且群成员可访问的证据位置，再用 `--evidence-url 'https://evidence.example.com/...'` 附链接；仅增加链接不会缩短当前消息，若仍超限，应另做有明确摘要标识的通知并通过应用机器人文件上传/获准存储发送完整附件，不能把删节版冒充完整报告。群自定义 Webhook 示例没有实现附件上传。

### 7.3 验证飞书确实收到

同时保留以下证据，才在验收表写“成功”：

1. `feishu-payload.json`：完整告警、审核分析、run ID、sessionKey。
2. `feishu-response.json`：API 成功响应，脚本退出码为 0。
3. 目标群中的实际消息：核对 `test from Jeff Peng`、同一 run ID 和 Alert ID；保存带时间的截图或消息链接。
4. 若有证据链接，用实际收件人账号打开；本机 `127.0.0.1:13000` 链接不能替其他人打开自己的 MOSAIC。

API 接受、群中可见、用户能打开附件是三个检查点。自定义机器人不提供本例所需的已读回执，因此不要声称收件人已阅读。

### 7.4 需要飞书内双向交互时：原生插件

[PR #74](https://github.com/NVIDIA/AI-Factory-Operations-Agent/pull/74) 使用与 OpenClaw `2026.6.10` 匹配的 `@openclaw/feishu`，不是要求升级到任意最新版。应用配置应参照[该版本指南](https://github.com/openclaw/openclaw/blob/v2026.6.10/docs/channels/feishu.md)，当前官网的[飞书概览](https://docs.openclaw.ai/channels/feishu)仅用于理解通道机制。

客户需要：创建飞书企业自建应用、启用机器人、配置接收/发送消息权限、以长连接订阅 `im.message.receive_v1`、发布并允许目标用户使用、取得 App ID/App Secret 和真实 `ou_...` 用户/`oc_...` 群 ID。PR 采用出站 WebSocket，无需公网回调。按该分支部署时的配置如下：

```bash
# 在 Spark，env 文件由 Secret 管理工具生成，位于仓库之外且权限 0600。
# 两个键：FEISHU_APP_ID、FEISHU_APP_SECRET。
kubectl --context kind-mosaic-poc -n mosaic create secret generic mosaic-feishu \
  --from-env-file=/secure/path/feishu.env
```

```yaml
openclaw:
  feishu:
    enabled: true
    domain: feishu
    existingSecret: mosaic-feishu
    allowedUserIds:
      - ou_REPLACE_WITH_ALLOWED_USER
    allowedGroupIds:
      - oc_REPLACE_WITH_ALLOWED_GROUP
```

必须先选择包含该 PR 的 chart，并核对已有 Teams 等现场定制后，按正常 upgrade 流程合入；本轮沿用的现场 chart（revision 8→10）不能只增加这些 values 就认为飞书插件已安装。验收允许用户私聊、允许群中 @、未授权用户/群拒绝、不 @ 不触发、Pod 重启后仍可回复。该 PR 关闭飞书文档/网盘等额外工具；飞书消息接入也不等于 IRAOP 文档入库。

**调查结束后的自动投递仍是下一步开发项。** 需建立持久化的“运行完成事件 → 报告发布器”，记录 fingerprint/sessionKey/run ID、消息目的地、发送响应、幂等键和失败重试状态，并用服务端采集/调度取代依赖浏览器的发起。普通飞书聊天回复不会自动订阅网页 Alert 会话的报告。不要把手动脚本、原生 IM 通道和自动告警报告器写成同一种已完成功能。

## 8. 清理本轮测试并保存复盘证据

先记录本轮 fingerprint/分析/飞书结果，再由目标集群管理员删除**本轮**规则：

```bash
ssh -p "$TARGET_SSH_PORT" "$TARGET_ADMIN@$TARGET_HOST" \
  "kubectl --context '$TARGET_CONTEXT' -n '$MONITORING_NS' delete prometheusrule 'mosaic-smoke-$RUN_ID'" \
  | tee "$EVIDENCE_DIR/rule-delete.txt"
```

等待规则重评估及 Alertmanager 失效/resolve，重新执行第 5.3 节采样。应观察本轮 `ALERTS{...,alertstate="firing"}` 消失，Alertmanager 不再有活动的本轮 fingerprint；如果查询到 resolved 状态，保留该对象与时间。UI 可以保留历史项，单击 **Resolve** 仅移除 MOSAIC 条目，不会修复目标集群，也不会删除 PrometheusRule；先在源头清理，否则后续拉取可能再次导入。

本轮确认后关闭 Auto investigate。若只是短期试验，按第 4 节接口 POST `{"enabled":false}` 或关闭 Auto pull，并保存状态。若需要保留原有轮询，恢复 `pull-before.json` 记录的原设置。不要用 **Resolve all** 清理其他告警。

此前保留的旧测试规则 `monitoring/mosaic-alert-smoke-test` 与本轮 `mosaic-smoke-$RUN_ID` 是不同资源。2026-10-30 旧规则仍在 firing；本手册没有执行删除旧规则或创建新的告警。

建议本地保留的证据清单：

| 文件/目录 | 内容 |
| --- | --- |
| `run-id.txt`、版本记录 | 本轮关联 ID、chart/UI/OpenClaw 版本、操作者时间 |
| `prometheus-selector.json` | Prometheus 规则和 namespace selector |
| `synthetic-alert.yaml`、`rule-apply.txt`、`applied-rule.json` | 完整创建命令产物、UID/spec |
| `samples/*/snapshot.json` 与原始 API 文件 | 每次完整投递采样；保留每个样本，不只留最后一次 |
| `alert.json` | 本轮单条完整 MOSAIC 告警 |
| `investigation-api.json`、`investigation-gateway.json`、`tool-results.json` | API 包装、原始会话与全部工具返回 |
| `analysis-all-unreviewed.md`、`analysis-reviewed.md` | 原始模型输出和审核后的完整报告 |
| `openclaw.private.log`、截图/相关 Network 响应 | 时间关联的辅助证据；原始 HAR/日志不直接公开 |
| `feishu-payload.json`、`feishu-response.json`、群消息链接/截图 | 发送内容、业务响应、群中收件 |
| `rule-delete.txt`、清理后的快照 | 源头清理和恢复确认 |

## 9. 已有实测：完整采样和调查结果

这些是旧测试的证据，供比较操作效果，不替代新一轮验收。[完整 7 个投递快照](examples/alert-feishu/evidence/poll-samples-20261029.jsonl)、[完整 Gateway 会话](examples/alert-feishu/evidence/investigation-gateway-20261029.json)、[2026-10-30 当前状态](examples/alert-feishu/evidence/current-test-alert-20261030.json)保留原始字段与全部指标数据点，仅替换私网地址/集群别名。

### 9.1 轮询链路的全部采样

| 采样时间 UTC | Prometheus 状态 | Alertmanager 测试告警数 | MOSAIC 测试告警数 | MOSAIC stage | Auto pull | 链路校验 |
| --- | --- | ---: | ---: | --- | --- | --- |
| 2026-10-29T09:19:47.850Z | 尚未加载 | 0 | 0 | — | true | false |
| 2026-10-29T09:19:57.899Z | unknown | 0 | 0 | — | true | false |
| 2026-10-29T09:20:07.955Z | pending | 0 | 0 | — | true | false |
| 2026-10-29T09:20:18.011Z | pending | 0 | 0 | — | true | false |
| 2026-10-29T09:20:28.051Z | pending | 0 | 0 | — | true | false |
| 2026-10-29T09:20:38.139Z | firing | 1 | 0 | — | true | false |
| 2026-10-29T09:20:48.178Z | firing | 1 | 1 | active | true | true |

fingerprint 为 `0fa8cbd733f54a5a`，MOSAIC ID 为 `alertmanager:0fa8cbd733f54a5a`。这一组采样本身只证明投递；后面的会话才证明调查发生。

### 9.2 现有调查的全部 11 个工具结果

会话 `agent:default:alert-alertmanager-0fa8cbd733f54a5a`，session ID `1192f07a-611e-4880-b59a-fdd43a41a0a0`。首次用户 prompt 时间 `2026-10-29T10:22:10.043Z`，首轮完整回答 `10:22:27.602Z`；随后 `10:23:45.191Z` 再次提交同一告警，`10:23:45.427Z` 返回回顾。2026-10-30 读回 `hasActiveRun=false`，页面条目仍为 `responding`。

| 序号 | UTC 返回时间 | 工具 | 实际命令/查询 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 10:22:15.901 | run_kubectl | `kubectl get alerts -n monitoring` | exitCode=1；集群不存在 `alerts` 资源类型 |
| 2 | 10:22:15.903 | run_kubectl | `kubectl get prometheusrule mosaic-alert-smoke-test -n monitoring -o yaml` | exitCode=1；只读账号读取 PrometheusRule 被 Forbidden |
| 3 | 10:22:15.904 | run_kubectl | `kubectl get alertmanager -o name` | exitCode=1；默认 mosaic namespace 下 list Alertmanager 被 Forbidden |
| 4 | 10:22:19.229 | observability_range_query | `ALERTS{alertname="MosaicSyntheticAlert"}` | 1 条序列，31 点，全部为 1 |
| 5 | 10:22:19.231 | observability_range_query | `ALERTS{mosaic_test="true"}` | 1 条序列，31 点，全部为 1 |
| 6 | 10:22:19.233 | observability_metric_names | 返回匹配的指标名 | count=12、returned=12，完整列表见下文 |
| 7 | 10:22:22.397 | observability_range_query | `alertmanager_alerts_received_total` | 2 条序列，每条 31 点：firing、resolved |
| 8 | 10:22:22.403 | observability_range_query | `alertmanager_alerts` | 3 条序列，每条 31 点：active、suppressed、unprocessed |
| 9 | 10:22:22.407 | observability_range_query | `grafana_alerting_alerts` | 6 条序列，每条 31 点：alerting、error、nodata、normal、pending、recovering |
| 10 | 10:22:27.597 | observability_range_query | `alertmanager_alerts_subscriber_channel_writes_total{alertmanager_name="monitoring-kube-prometheus-stack-alertmanager"}` | 0 条序列，空数组；不能据此判断投递失败 |
| 11 | 10:22:27.598 | exec | 原始结果没有保存请求的命令，不能补猜 | 被 View 策略拒绝；通用执行未发生 |

7 个工具结果成功，4 个失败/拒绝。前两条 ALERTS 查询窗口均为 Unix `1793267539` 到 `1793269339`、步长 60 秒；第 7–9 项窗口为 `1793267542` 到 `1793269342`、步长 60 秒；第 10 项窗口为 `1793267547` 到 `1793269347`、步长 60 秒。所有完整 series labels、13 条非空序列共 403 个数据点以及各查询 `truncated=false` 都在原始 JSON 中，没有省略中间点或把曲线改成首尾值。

第 6 项的全部 12 个指标名：

```text
ALERTS
ALERTS_FOR_STATE
alertmanager_alerts
alertmanager_alerts_invalid_total
alertmanager_alerts_received_total
alertmanager_alerts_subscriber_channel_writes_total
alertmanager_marked_alerts
grafana_alerting_active_alerts
grafana_alerting_alertmanager_alerts
grafana_alerting_alerts
grafana_alerting_alerts_invalid_total
grafana_alerting_alerts_received_total
```

上述记录没有实际 GPU/NVDebug 采集，没有 IRAOP 调用，没有飞书投递。原始模型答案中将内部 subscriber 指标与“MOSAIC webhook ingestion”联系起来，是未经证实的推断；现场实际使用 Auto pull，[Webhook PR #78](https://github.com/NVIDIA/AI-Factory-Operations-Agent/pull/78) 未部署。Alertmanager 总接收计数也不是单条消息的确认。审核报告时应以同一 fingerprint 的 Alertmanager/MOSAIC 原始对象和工具返回为依据，纠正这些表述，同时保留原始答案作为证据。

## 10. 按故障位置排查

| 看到的现象 | 下一条检查 | 说明 |
| --- | --- | --- |
| 规则创建成功但 Prometheus 没有加载 | `prometheus-selector.json`、规则 namespace/metadata labels、规则 health | Kubernetes 对象存在不代表 Prometheus 已选中 |
| 一直 pending | `for:30s`、评估间隔、规则 lastEvaluation | 等待不等于修改 GPU 或重启监控 |
| Prometheus firing，Alertmanager 没有 | Prometheus alerting 配置、AM 路由和目标连接 | 还没到 MOSAIC 这一跳 |
| AM 有，MOSAIC 没有 | `/api/alerts/alertmanager` 的 baseUrl/lastError/lastSyncAt；点 Refresh | active/silenced/inhibited 条件、轮询进程与已导入去重需分开看 |
| 告警到达但无调查会话 | 浏览器是否打开，Auto investigate 是否开；手动点 Start Investigating | 轮询成功不会自动证明已提交 prompt |
| 页面 Responding 很久 | history `hasActiveRun`、assistant 回答、工具错误 | 当前已观测到阶段停留而模型已完成的情况 |
| 工具 Forbidden | 实际 cluster/namespace、SA 只读权限 | 保留失败；管理员导出证据或精确补只读权限 |
| `result: []` | 工具保存的 PromQL 与实际 labels、时间范围 | 空序列与数值零不同 |
| Feishu HTTP 200 但无消息 | JSON 业务 code、签名时间、关键词/出口 IP/收件群 | 不能只看 HTTP 状态 |
| Feishu payload 超限 | 脚本报告的 UTF-8 字节数、完整附件/证据链接方案 | 不静默删表或裁剪结论 |
| 装了 Research 但分析没有引用 | 工具 catalog、实际 `iraop_query`、collections/PDF 入库 | 启用服务不代表本轮调用或文档支持该判断 |
