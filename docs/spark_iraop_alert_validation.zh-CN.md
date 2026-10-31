<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# 启用 IRAOP，并观察它在告警调查中的作用

状态更新（2026-10-31）：**已实际部署和入库，原生研究质量未通过。** 本轮 Helm revision9 启用 IRAOP/OpenSearch，使用真实本地 CPU embedding 384d；控制 PDF 为2页/4 chunks/0 errors，下载 SHA256 一致。直接查询命中但行内引用页码错误；独立 OpenClaw 及实际告警会话多次 `iraop_query` 为空 sources。完整配置、原始响应和失败样本见[实测记录第5章](spark_live_validation_20261031.zh-CN.md#5-research-实际部署入库和失败点)。前置流程和变量见[主操作手册](spark_alert_feishu_runbook.zh-CN.md)。

[追加实测](spark_live_validation_20261031_followup.zh-CN.md)已验证 IRAOP Pod 重建后无需重新入库，1 PDF/4 chunks 可读；四种完整 agent 对照仍未通过研究质量验收。当前 revision12 回填无来源 query 的 incomplete 处理：不把未核验答案传给主模型，完整原始 MCP 留在会话 JSONL 的 details；chat.history API 会省略 details。新环境需要 [PR #2](https://github.com/JeffPengCoder/AI-Factory-Operations-Agent/pull/2) 或交付的补丁 chart；这些呈现改进不代表后端检索质量已修复。

以下保留完整的通用部署/验收步骤；第2章描述的是实施前 revision8 基线。不要在当前已部署的环境重复生成 token、覆盖 Secret 或沿用2048维旧配置；本轮使用的实际 overlay、CPU 服务及受控 corpus 见实测记录。后续需先解决模型/工具循环及引用问题，再验收告警中的稳定知识增强。

## 1. 要验证的行为

在同一条告警的同一个调查会话里，保留现场指标/Kubernetes 证据，再显式让 OpenClaw 查询 IRAOP 的指定文档集合，观察 `iraop_query` 的输入、执行状态、完整返回、引用页码和最终答案。最终把完整告警、审核后的分析和文档来源交给飞书投递步骤。

```text
合成告警 → MOSAIC Alert 会话 → OpenClaw
                              ├→ Kubernetes / Prometheus：当前现场证据
                              └→ iraop_query(question, depth, collections)
                                    ↓ MCP/SSE + Bearer
                                  IRAOP
                                    ├→ embedding(query)
                                    ├→ OpenSearch 文本/向量检索
                                    ├→ LLM 组织研究答案
                                    └→ answer + sources(文件/页码/collection/doc_id/url)
                              ↓
                     区分事实、文档建议和待验证假设
                              ↓
                      审核报告 → 飞书 + 可访问证据
```

**开关打开只代表可调用。** 当前 Alert prompt 没有强制调用 IRAOP；模型可能不用研究工具。因此先验证显式调用，再决定是否要修改自动调查编排。PDF 不会因为收到告警自动变成知识库；embedding 入库也不等于训练模型。

## 2. 当前基线和部署前检查

实施前（2026-10-30）现场 `modules.research.enabled=false`，历史 Helm revision 1–8 均关闭 Research。子配置 `researchAgent.iraop.enabled=true`、`researchAgent.opensearch.enabled=true` 是合并后的默认值，父开关关闭时不会部署它们。当时普通调查中没有 IRAOP 工具结果；2026-10-31 revision9 起已改变，结果见上方实测链接。

拟使用版本和现有资源配置如下。它们是配置值，不是已经占用的资源：

| 项目 | 当前配置/拟验证值 |
| --- | --- |
| IRAOP image tag | `f804535b` |
| OpenSearch | `opensearchproject/opensearch:2.17.0` |
| IRAOP requests / limits | CPU `500m` / `2`；内存 `2Gi` / `8Gi` |
| OpenSearch requests / limits | CPU `500m` / `2`；内存 `2Gi` / `4Gi` |
| OpenSearch JVM heap | `-Xms2g -Xmx2g` |
| OpenSearch PVC | `20Gi`，StorageClass 按现场默认值 |
| corpus | `/cm/shared/iraop-corpus` |
| chat base URL | `http://llm-openai-compat:8000/v1` |
| chart 当前研究模型名 | `nemotron-ultra-550b`，**需改成实际提供的模型名** |
| 已有 Alert 会话实际模型 | `nvidia/Qwen3.6-35B-A3B-NVFP4`；部署前再读模型列表核对 |
| embedding base URL 默认值 | `https://integrate.api.nvidia.com/v1` |
| embedding model / dimension | `nvidia/llama-nemotron-embed-vl-1b-v2` / `2048` |
| 服务端默认 depth | `deep` |
| OpenClaw 插件默认 depth / timeout | `quick` / `240000 ms` |

IRAOP chat 和 embedding 是两条独立连接。将 chat 指向 Spark 上的模型，不会让 embedding 同时本地化。若要全本地，需单独部署兼容的 embedding 服务、配置 query/passage 协议、维度和 OpenSearch connector；更换模型/维度时按新集合重新入库，不能沿用旧向量。

### 2.1 在 Spark 保存可回滚基线

登录 Spark，在 Bash 执行；备份目录保持私有，不上传原始 values/Secret/集群凭据：

```bash
export PATH="$HOME/.local/bin:$PATH"
export IRA_RUN="$(date -u +%Y%m%dt%H%M%Sz)"
export IRA_WORK="$HOME/mosaic-iraop-validation/$IRA_RUN"
umask 077
mkdir -p "$IRA_WORK"
helm --kube-context kind-mosaic-poc -n mosaic history mosaic -o json \
  > "$IRA_WORK/helm-history-before.private.json"
helm --kube-context kind-mosaic-poc -n mosaic get values mosaic -o yaml \
  > "$IRA_WORK/values-before.private.yaml"
helm --kube-context kind-mosaic-poc -n mosaic get manifest mosaic \
  > "$IRA_WORK/manifest-before.private.yaml"
kubectl --context kind-mosaic-poc -n mosaic get pods,pvc,svc -o wide \
  > "$IRA_WORK/resources-before.txt"
export BASE_REVISION="$(python3 -c 'import json,sys; print(max(x["revision"] for x in json.load(open(sys.argv[1])) if x["status"]=="deployed"))' "$IRA_WORK/helm-history-before.private.json")"
printf '%s\n' "$BASE_REVISION" > "$IRA_WORK/base-revision.txt"
kubectl --context kind-mosaic-poc get nodes -o wide
kubectl --context kind-mosaic-poc get storageclass
kubectl --context kind-mosaic-poc -n mosaic get pvc
docker stats --no-stream
df -h
kind get nodes --name mosaic-poc
```

评估 Spark 上现有推理的内存/CPU 压力。OpenClaw 和 IRAOP 共用模型时会争抢推理吞吐，先 quick 单次测试，再测 deep。不要用自动轮询把大量生产告警同时送去研究。

### 2.2 先解决 chart / 插件兼容性

`MOSAIC_CHART` 必须指向**保留现有 Teams 定制并准备好真实依赖**的审核版 chart。不能直接用仓库 main 覆盖 revision 8，也不能把文档 CI 的空 `iraop-stack` stub 用来部署。

需要检查四处：

1. `helm/mosaic-stack/files/openclaw-seed/extensions/iraop/index.ts` 对 MCP/SSE 连接、握手和后续请求发送 Bearer；支持 `config.apiKey`。
2. `nemoclaw.json` 的 IRAOP 配置将 `${IRAOP_API_KEY}` 传入插件；不能只是 Secret 中有键而调用端没使用。
3. OpenClaw 和 UI 的 Deployment 都通过 `secretKeyRef` 取得同一 `iraop-secrets/IRAOP_API_KEY`。
4. IRAOP 服务本身启用认证并使用同一 token；未认证的业务接口应返回 401。不要通过关闭 `IRAOP_AUTH_REQUIRED` 规避旧调用端问题。

通用步骤基于 fork main commit `6b823775e8cd90e4c1eaaced7fac19f9340ff725` 的公开 chart/plugin；该源码已有 Bearer 支持。实施前 Spark 的 Research 关闭，未配置 IRAOP apiKey；本轮核对保留 chart 也已具备认证支持，启用后实际验证了无认证401和带凭据查询。若其他现场保留的旧 chart 缺少上述支持，先补齐并做 render/兼容检查。

在源码目录先检查，不输出具体凭据：

```bash
rg -n 'authHeaders|apiKey|Authorization' \
  helm/mosaic-stack/files/openclaw-seed/extensions/iraop/index.ts
rg -n 'IRAOP_API_KEY' \
  helm/mosaic-stack/files/openclaw-seed/nemoclaw.json \
  helm/mosaic-stack/templates/openclaw.yaml \
  helm/mosaic-stack/templates/mosaic-ui.yaml
```

使用已获 NGC 授权的本机/服务身份获取真实 `iraop-stack` chart 和私有 IRAOP 镜像。NGC 组织/仓库访问权限与登录 token 是两件事；`docker login` 成功不能证明有拉取权限。

### 2.3 Kind 的 corpus 路径

当前 Kind 节点没有把 Spark 主机的 `/cm/shared/iraop-corpus` 直接 bind mount 进去。chart 的 `hostPath` 指向 **Kind 节点容器内的路径**。直接在 Spark 主机同名目录拷 PDF，Pod 可能仍然看不到。

PoC 可以先把 PDF 放进 Kind 节点，由该 hostPath 提供给 IRAOP。不要为加 extraMount 临时重建现有 Kind 集群。正式持久方案应由部署方规划 Spark → Kind 节点 extraMount 或合适 PVC，同时保留原始 PDF 和 OpenSearch 数据的备份。

```bash
export KIND_NODE="$(kind get nodes --name mosaic-poc | head -n 1)"
docker inspect "$KIND_NODE" --format '{{json .Mounts}}'
docker exec "$KIND_NODE" cat /proc/sys/vm/max_map_count
```

对照真实 OpenSearch chart 的启动要求检查 `vm.max_map_count` 和存储权限；不足时由管理员按该版本文档处理并记录修改。以下 hostPath staging 只能保证当前 Kind 节点中的文件存在，不承诺 Kind 删除/重建后的持久性。

## 3. 配置 Secret 与启用 Research

### 3.1 客户需要提供的输入

客户/部署方必须提供：可用 embedding API key（或获准的本地 embedding 服务）、实际 chat 模型名、可访问的模型端点/必要认证、允许导入的 PDF、存储位置和资源预算。此次镜像检查没有发现内置 PDF 语料，因此不能把空安装当作已有知识库。

在 Spark 创建 Secret，密码/密钥通过隐藏输入进入临时文件，不在 shell history 中写明文：

```bash
export IRA_AUTH_WORK="$(mktemp -d "${TMPDIR:-/tmp}/iraop-auth.XXXXXX")"
chmod 700 "$IRA_AUTH_WORK"
python3 - <<'PY'
import getpass, os, secrets
from pathlib import Path
embedding = getpass.getpass('Embedding API key (hidden): ')
chat = getpass.getpass('Chat API key (hidden; Enter only if this local endpoint needs no auth): ') or 'EMPTY'
if any('\n' in value or '\r' in value for value in (embedding, chat)):
    raise SystemExit('Keys must not contain newlines')
path = Path(os.environ['IRA_AUTH_WORK'])/'iraop.env'
path.write_text('NVIDIA_API_KEY='+embedding+'\nNVIDIA_CHAT_API_KEY='+chat+'\nIRAOP_API_KEY='+secrets.token_hex(32)+'\n')
path.chmod(0o600)
PY
kubectl --context kind-mosaic-poc -n mosaic create secret generic iraop-secrets \
  --from-env-file="$IRA_AUTH_WORK/iraop.env" --dry-run=client -o yaml \
  | kubectl --context kind-mosaic-poc -n mosaic apply -f -
rm -f "$IRA_AUTH_WORK/iraop.env"
rmdir "$IRA_AUTH_WORK"
unset IRA_AUTH_WORK
```

这是初次启用的 Secret 创建步骤。已有服务时不要随机轮换 token；需协调所有调用方并先保存受控的密钥备份。token 无需传入聊天或 PR。

### 3.2 准备 overlay、检查并升级

以下在 Spark 执行。将路径填为第 2.2 节确认的 chart；`modules.research.managed` 是旧 schema 字段，不在这里沿用。

```bash
export MOSAIC_CHART='/path/to/reviewed/mosaic-stack'
export MOSAIC_CHAT_MODEL='nvidia/Qwen3.6-35B-A3B-NVFP4'
test -r "$MOSAIC_CHART/Chart.yaml"
helm dependency list "$MOSAIC_CHART"
```

先在 UI Settings / 现有模型服务 `/v1/models` 核对实际提供的模型 ID。上面的模型名来自已有调查记录，若服务已更换，应同步修改。

```bash
cat > "$IRA_WORK/research-overlay.yaml" <<EOF
modules:
  research:
    enabled: true
    secrets:
      create: false
researchAgent:
  iraop:
    config:
      NVIDIA_CHAT_BASE_URL: http://llm-openai-compat:8000/v1
      NVIDIA_CHAT_MODEL: "$MOSAIC_CHAT_MODEL"
      NVIDIA_API_BASE_URL: https://integrate.api.nvidia.com/v1
      NVIDIA_EMBEDDING_MODEL: nvidia/llama-nemotron-embed-vl-1b-v2
      EMBEDDING_DIMENSION: "2048"
      CORPUS_DIR: /cm/shared/iraop-corpus
    corpus:
      hostPath: /cm/shared/iraop-corpus
EOF

helm lint "$MOSAIC_CHART" \
  -f "$IRA_WORK/values-before.private.yaml" -f "$IRA_WORK/research-overlay.yaml"
helm template mosaic "$MOSAIC_CHART" -n mosaic \
  -f "$IRA_WORK/values-before.private.yaml" -f "$IRA_WORK/research-overlay.yaml" \
  > "$IRA_WORK/research-render.private.yaml"
```

检查 render：IRAOP/OpenSearch/init Job/Service/PVC 实际存在；Secret 引用一致；原有 UI/OpenClaw/Teams/目标集群设置仍保留；image architecture 支持 Spark；没有展开到终端的凭据。`helm template` 不验证镜像可拉取、外部 API 或运行时认证；chart 内 `lookup` 的结果还可能与真实 upgrade 不同。

如果 chart 版本发生改变，先按两个版本的 schema 迁移旧 values；不能仅凭 `--reuse-values` 假定兼容。完成检查后执行：

```bash
helm upgrade mosaic "$MOSAIC_CHART" \
  --kube-context kind-mosaic-poc -n mosaic \
  -f "$IRA_WORK/values-before.private.yaml" -f "$IRA_WORK/research-overlay.yaml" \
  --atomic --wait --timeout 20m
kubectl --context kind-mosaic-poc -n mosaic get pods,jobs,svc,pvc -o wide \
  | tee "$IRA_WORK/resources-after.txt"
helm --kube-context kind-mosaic-poc -n mosaic history mosaic -o json \
  > "$IRA_WORK/helm-history-after.private.json"
```

不要只看 upgrade 的退出码。确认真实资源名后对 IRAOP/OpenSearch 执行 rollout/wait，检查 OpenSearch init Job 的 completion、日志和事件；按 `get` 输出替换下例资源名：

```bash
kubectl --context kind-mosaic-poc -n mosaic get deploy,statefulset,jobs
export IRAOP_POD='填入实际 IRAOP Pod 名'
export OPENSEARCH_INIT_JOB_POD='填入实际 OpenSearch init Job Pod 名'
kubectl --context kind-mosaic-poc -n mosaic describe pod "$IRAOP_POD"
kubectl --context kind-mosaic-poc -n mosaic logs "$OPENSEARCH_INIT_JOB_POD" --timestamps
kubectl --context kind-mosaic-poc -n mosaic logs "$IRAOP_POD" --timestamps
```

先用实际资源名替换两个变量，再运行 describe/logs。ImagePullBackOff 先检查 NGC 权限；Pending 先查资源/PVC；embedding 初始化失败要查真实 API 兼容性，不能用重启成功充当功能验证。

## 4. 先独立验证服务、PDF 入库和引用

### 4.1 打开只在本机可访问的 IRAOP 测试入口

本机另开终端，保留运行；服务名 `iraop` 和端口 `8000` 以实际 chart 为准：

```bash
ssh -t -p "$SPARK_SSH_PORT" -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18000:127.0.0.1:18000 "$SPARK_USER@$SPARK_HOST" \
  '$HOME/.local/bin/kubectl --context kind-mosaic-poc -n mosaic port-forward --address=127.0.0.1 svc/iraop 18000:8000'
```

在原本机取证终端 B：

```bash
export IRA_URL='http://127.0.0.1:18000'
export IRA_HEADERS="$AUTH_DIR/iraop-headers"
trap 'rm -f "$MOSAIC_NETRC" "$IRA_HEADERS"; rmdir "$AUTH_DIR" 2>/dev/null || true' EXIT
python3 - <<'PY'
import getpass, os
from pathlib import Path
key = getpass.getpass('IRAOP_API_KEY from your secret manager (hidden): ')
if not key or '\n' in key or '\r' in key:
    raise SystemExit('A nonempty single-line key is required')
p = Path(os.environ['IRA_HEADERS'])
p.write_text('Authorization: Bearer '+key+'\n')
p.chmod(0o600)
PY
curl --fail-with-body -sS "$IRA_URL/api/v1/live" > "$EVIDENCE_DIR/iraop-live.json"
curl --fail-with-body -sS "$IRA_URL/api/v1/health" > "$EVIDENCE_DIR/iraop-health.json"
curl -sS -o "$EVIDENCE_DIR/iraop-no-auth.json" -w '%{http_code}\n' \
  "$IRA_URL/api/v1/collections"
curl --fail-with-body -sS --header @"$IRA_HEADERS" \
  "$IRA_URL/api/v1/collections" > "$EVIDENCE_DIR/iraop-collections-before.json"
```

从受控 Secret 管理入口向操作员提供服务 token，或由授权管理员直接写入这个临时 header 文件；不要把 `kubectl get secret` 的结果粘到聊天中。完成后删除 header 文件再退出终端，主手册的认证目录清理才能成功。

验收：`live` 是进程存活；`health` 还会真实探测 embedding（成功探针可能缓存 300 秒）；未认证 collections 返回 401，带有效 Bearer 返回 200。health 正常不代表已导入任何文档，也不证明 chat/研究查询完成。

### 4.2 准备一个可核对页码的控制 PDF

先选一个允许入库、含可选择文字的 PDF，文件名例如 `mosaic-synthetic-alert-runbook.pdf`。为了区分文档检索与模型自带知识，可在第一页写入一条专属控制内容：

```text
Reference: MOSAIC-KB-20261030
MosaicSyntheticAlert with vector(1) is a delivery-path test, not a GPU fault.
Verify Prometheus firing, Alertmanager fingerprint, and the matching MOSAIC alert.
Do not remediate a GPU based on this synthetic alert.
An authorized administrator removes only the test PrometheusRule after verification.
```

记录文件 SHA-256、总页数和控制内容所在页码。专属标记用于证明答案可关联本轮入库文档，不能仅凭模型复述通用常识验收。扫描图片 PDF 的文本提取不足时要先完成受控 OCR；该版默认 pdfplumber 路径不能假设自动读图。

把 PDF 从本机传到 Spark：

```bash
shasum -a 256 /path/to/mosaic-synthetic-alert-runbook.pdf \
  > "$EVIDENCE_DIR/corpus-pdf.sha256"
scp -P "$SPARK_SSH_PORT" /path/to/mosaic-synthetic-alert-runbook.pdf \
  "$SPARK_USER@$SPARK_HOST:~/mosaic-synthetic-alert-runbook.pdf"
```

在 Spark staging 到 Kind 节点；示例权限允许读取，若 UI 还需写 corpus，按实际 Pod UID/GID 配置精确目录权限：

```bash
docker exec "$KIND_NODE" mkdir -p /cm/shared/iraop-corpus
docker cp "$HOME/mosaic-synthetic-alert-runbook.pdf" \
  "$KIND_NODE:/cm/shared/iraop-corpus/mosaic-synthetic-alert-runbook.pdf"
docker exec "$KIND_NODE" chmod 0644 /cm/shared/iraop-corpus/mosaic-synthetic-alert-runbook.pdf
kubectl --context kind-mosaic-poc -n mosaic exec "$IRAOP_POD" -- \
  ls -l /cm/shared/iraop-corpus/mosaic-synthetic-alert-runbook.pdf
```

必须在 Pod 内读到文件，而不是只看到 Spark 主机有同名文件。UI 有 Knowledge 页面时也可以用其上传流程，但仍需核对原文是否实际落盘。该版独立 `/ingest/upload` 临时文件路径不保证保留原 PDF；本次采用 corpus + `/ingest/file`，便于后续打开引用原文。

### 4.3 导入并保留完整响应

在本机终端 B：

```bash
export IRA_COLLECTION="mosaic-smoke-$RUN_ID"
jq -n --arg collection "$IRA_COLLECTION" \
  '{file_path:"/cm/shared/iraop-corpus/mosaic-synthetic-alert-runbook.pdf",collection:$collection}' \
  > "$EVIDENCE_DIR/iraop-ingest-request.json"
curl --fail-with-body -sS --max-time 600 --header @"$IRA_HEADERS" \
  -H 'Content-Type: application/json' \
  --data-binary @"$EVIDENCE_DIR/iraop-ingest-request.json" \
  "$IRA_URL/api/v1/ingest/file" > "$EVIDENCE_DIR/iraop-ingest-response.json"
curl --fail-with-body -sS --header @"$IRA_HEADERS" \
  "$IRA_URL/api/v1/collections" > "$EVIDENCE_DIR/iraop-collections-after.json"
curl --fail-with-body -sS --header @"$IRA_HEADERS" \
  "$IRA_URL/api/v1/collections/$IRA_COLLECTION/documents" \
  > "$EVIDENCE_DIR/iraop-documents.json"
curl --fail-with-body -sS --header @"$IRA_HEADERS" \
  "$IRA_URL/api/v1/documents/mosaic-synthetic-alert-runbook.pdf" \
  > "$EVIDENCE_DIR/iraop-downloaded-original.pdf"
shasum -a 256 "$EVIDENCE_DIR/iraop-downloaded-original.pdf"
```

验收导入响应的页数、成功 chunk 数、errors/status/失败明细，逐项保留；不能只看 HTTP 200。Collection `doc_count` 在这里通常是 chunk 数，不是 PDF 份数。下载原文的 SHA-256 应与本机原 PDF 一致。索引可检索与原文下载成功分别验收。

### 4.4 独立研究查询

```bash
jq -n --arg collection "$IRA_COLLECTION" \
  '{question:"According to the indexed runbook, explain MOSAIC-KB-20261030, how to verify MosaicSyntheticAlert, and who performs cleanup. Cite the source file and page. Do not inspect or change a live cluster.",depth:"quick",collections:[$collection]}' \
  > "$EVIDENCE_DIR/iraop-query-request.json"
curl --fail-with-body -sS --max-time 300 --header @"$IRA_HEADERS" \
  -H 'Content-Type: application/json' \
  --data-binary @"$EVIDENCE_DIR/iraop-query-request.json" \
  "$IRA_URL/api/v1/query" > "$EVIDENCE_DIR/iraop-query-response.json"
python3 -m json.tool "$EVIDENCE_DIR/iraop-query-response.json"
```

保留全部 `answer`、`depth`、`collections_searched` 和每条 `sources` 的 `source_file/page_number/collection/doc_id/url`。核对控制标记、文件名、页码与原文内容。`sources` 是研究期间取得的来源，不保证每句答案都受它支持；逐条检查关键操作建议。一次 HTTP 查询成功也不等于 OpenClaw MCP 调用成功，两条调用路径需要分别验收。

## 5. 在同一告警会话里观察真实调用

回到主手册里已有的、本轮 Alert 会话，不另开没有告警上下文的新聊天。先保留 Research 关闭时的分析与原始工具结果，作为基线 A；Research 启用、语料验证后，在同一会话补充以下 prompt 作为 B：

```text
继续调查当前告警；run_id=<RUN_ID>，Alert ID=<ALERT_ID>。
仍保持 View/只读。先列出已有现场证据及其限制。
请调用 iraop_list_collections，确认集合 <IRA_COLLECTION>；
然后实际调用 iraop_query，depth=quick，collections=["<IRA_COLLECTION>"]，
查询：根据 MOSAIC-KB-20261030 文档，这条 vector(1) 合成告警应如何验证和清理？
返回完整工具结果、source_file、page_number、collection、doc_id、url。
将“现场观测”“文档建议”“尚未验证的假设”分开说明。
若无法调用/无命中/认证失败，明确写出错误，不用模型常识冒充检索结果。
不要实际清理规则或更改集群。
```

### 5.1 UI / Audit 证据

打开工具调用详情和 **Audit**，确认同一 SESSION_KEY 出现 `iraop_list_collections`、`iraop_query`，记录 toolCallId、时间、question/depth/collections、返回结果。支持该版本事件遥测时，可看到 `IRA research` 子 agent 面板的 start/delta/complete/error。

当前插件面板显示连接/请求进度及最终结果摘要，不能把这些 delta 理解为 IRAOP 内部每一步研究思考或每个模型 token 的完整实时流。摘要可能裁剪，完整返回仍以会话中的 toolResult 为准。

### 5.2 日志证据

在 Spark 保存本轮时间范围的完整日志：

```bash
kubectl --context kind-mosaic-poc -n mosaic logs deploy/openclaw -c gateway \
  --since=30m --timestamps > "$IRA_WORK/openclaw-with-iraop.private.log"
kubectl --context kind-mosaic-poc -n mosaic logs "$IRAOP_POD" \
  --since=30m --timestamps > "$IRA_WORK/iraop.private.log"
rg -n 'iraop-plugin|MCP|SSE|401|query|error' "$IRA_WORK/openclaw-with-iraop.private.log"
```

插件日志应出现 MCP/SSE 打开、query 调用与完成/失败；服务日志核对同时间的认证/查询请求。默认日志未必携带 UI 的 sessionKey 或打印全文 question，不能仅凭时间相近就证明严格对应。使用 toolCallId、单条受控测试、请求中的专属控制标记和工具结果联合关联；需要多并发生产追踪时，补充结构化 request ID/会话关联日志是后续工程项。

重新执行主手册第 6.3 节导出完整会话，**另存 A、B 两份**，不要覆盖基线。核对新增 toolResult 确实包含 IRAOP 结果、引用与错误字段。缺少真实调用时，不能填“已使用知识库”。

### 5.3 A/B 验收表

| 检查点 | A：Research 关闭 | B：Research 启用并显式调用 | 可接受的证据 |
| --- | --- | --- | --- |
| 同一告警上下文 | 记录 run ID/fingerprint/sessionKey | 保持同一对象，记录追问时间 | 两次完整会话导出 |
| 现场数据 | 原始 Prometheus/Kubernetes 结果 | 保留并标注是否重新采集 | 时间窗口、查询、所有结果/错误 |
| 文档调用 | 无 IRAOP toolResult | 有实际 `iraop_query` | toolCallId、完整参数与返回 |
| 语料范围 | 无此检索链路 | collections 为指定测试集合 | 集合/文档清单与请求 |
| 引用准确性 | 不应宣称查过 PDF | 控制标记、文件名、页码可核对 | 下载 PDF 的 SHA-256 和原文 |
| 回答变化 | 模型常识 + 工具事实 | 现场事实 + 有出处的文档建议 | 两份完整答案，逐项核对差异 |
| 错误透明 | 保留 Forbidden/空序列 | 另保留 401/超时/无命中等 | 全部失败输出，不删失败行 |
| 飞书投递 | 可发基础报告 | 报告增加准确的来源与限制 | payload、业务成功响应、群中消息 |
| 修复状态 | 合成告警未实际修复 | 文档建议不触发写操作 | 管理员单独清理规则的记录 |

## 6. 回到自动告警流程，还需要哪些开发

先完成以上显式查询验收，再考虑默认自动调查。建议分开做以下可评审变更：

1. 服务端持久队列接收/轮询告警，按 fingerprint + run/session 标识去重；浏览器关闭也能调度。
2. 告警编排明确什么时候做现场采集、什么时候调用 IRAOP、允许哪些 collections、quick/deep 和超时预算；文档仅作为证据补充。
3. 将 alert ID、sessionKey、toolCallId、IRAOP request ID 和飞书发布记录串起来；默认日志不包含这种完整关联时，需要加埋点。
4. 调查完成事件驱动报告发布器，保存完整报告/证据位置；飞书消息有幂等键、发送状态、限流/重试及人工重发入口。
5. 测试无文档、无命中、错误引用、认证失败、embedding 不可用、模型超时、飞书拒收和大报告。失败要可见，不把失败回退成“已研究完成”。

这些是后续计划，不是本 PR 中已经实现的自动化。Webhook 收告警、Research 模块和飞书通道分别解决不同的连接，仍需完成服务端编排与报告发布。

## 7. 回滚与资料保留

若部署或集成影响原有会话，在 Spark 回滚到第 2.1 节保存的 revision：

```bash
helm --kube-context kind-mosaic-poc -n mosaic rollback mosaic "$BASE_REVISION" \
  --wait --timeout 20m
helm --kube-context kind-mosaic-poc -n mosaic status mosaic
kubectl --context kind-mosaic-poc -n mosaic get pods,svc,pvc -o wide
```

验证原有 UI、聊天、目标集群只读工具、Teams 定制和 Auto pull 配置。新增工作负载应不再运行；检查实际残留 Job/Secret/PVC。回滚不保证删除或恢复 OpenSearch 数据、hostPath 中的 PDF，不能作为语料备份方案。

测试集合的删除只在确认不再需要后针对本轮集合执行；保留完整研究结果和 PDF 校验值：

```bash
curl --fail-with-body -sS --header @"$IRA_HEADERS" -X DELETE \
  "$IRA_URL/api/v1/collections/$IRA_COLLECTION" \
  > "$EVIDENCE_DIR/iraop-delete-test-collection.json"
rm -f "$IRA_HEADERS"
```

不要删除共享 OpenSearch PVC、其他 collections 或现有原始 PDF。单独清理合成 PrometheusRule 按主手册第 8 节执行。

完整验收应交付：Helm 前后记录、资源/健康/认证检查、PDF 哈希、入库全部明细、独立 query 全响应、同一 Alert 会话的完整消息和工具结果、IRAOP/OpenClaw 日志、引用逐项核验、飞书群收件证据、资源清理/回滚结果。2026-10-31 已有的部署、入库、直接查询及原生失败结果见[完整实测记录](spark_live_validation_20261031.zh-CN.md)；原生检索/引用质量、飞书收件和回滚仍待完成，不能因为部署成功就把整体验收标为通过。

完成 Research 验证后，再进入 [Edit/Auto 修复草案](spark_edit_auto_repair_validation.zh-CN.md)，验证从只读调查到获授权修复的人工交接、审批、执行、恢复确认和审计。
