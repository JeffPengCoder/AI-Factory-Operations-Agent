<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Research 之后：Edit / Auto 修复操作与实测

状态更新（2026-10-31）：**已完成 SSH-only 隔离服务的真实 View / Edit / Auto 验证**，顺序在 [IRAOP 验证](spark_iraop_alert_validation.zh-CN.md)之后。revision10 启用的 `modules.edit.enabled=true`、`hitl=true` 在当前 revision12 保留，Kubernetes/Base Command Manager 写后端关闭。View 拒绝修复，Edit 的 Deny 和新的 Approve once 生效；Auto 确认后执行相同 wrapper，范围外 touch 被 SSH identity 拒绝（126），测试后恢复 View。主机状态与完整审计见[实测记录第6章](spark_live_validation_20261031.zh-CN.md#6-view--edit--auto-的实际隔离修复)。**审批过期已追加实测通过**：不批准/不拒绝，等待120000 ms 后未执行，主机仍failed，完整 SSH 审计未变，见[追加记录第4章](spark_live_validation_20261031_followup.zh-CN.md#4-edit-审批过期实际怎么验证)。

**本轮采用 Spark 用户服务 `mosaic-repair-validation.service` + restrict/forced-command SSH key，没有使用 sudo/root。** 真实 exact argv、设置/重置方法和代码见实测记录。以下保留的是另一种管理员预置的 system-level fixture 完整方案，不是本轮已经执行过的 root/sudo 操作；审批过期和回滚也仍待独立验收。不要混用两套服务名、路径或身份。

本章给接手人一个可观察的“机器上服务故障 → MOSAIC 发出修复命令 → 服务恢复”实验。先用专用测试主机上的独立 systemd 服务，不操作 GPU、驱动或业务服务。它验证权限、审批、执行和审计链路，不代表已经验证所有生产故障都能自动修复。

## 1. 三种模式分别允许什么

以本仓库[安全模型](security_model.md)及实际 chart/plugin 为准。切换模式发生在**每个交互会话**内；启用模块后，新会话仍默认 View。

| 设置 | 含义 | 本实验应观察到什么 |
| --- | --- | --- |
| View | 只读观察，阻止修复类操作 | 诊断可返回，修复工具调用被拒绝，主机状态不变 |
| Edit，`hitl=true` | 需要人批准具体写操作 | 审批卡展示主机、工具和 exact argv；拒绝/过期不执行；批准后才执行 |
| Auto | 操作者确认警示后，该会话允许的写操作不逐次审批 | 相同修复命令直接执行；工具验证、主机权限、审计仍生效 |
| Auto investigate | 浏览器收到告警后自动发起调查 | 这不是 Auto 修复；自动告警/巡检会话仍为只读 |

不能把告警自动调查会话切成 Edit/Auto 来修复。做法是保留只读调查证据，再由有权限的操作者新建交互式修复会话，引用 Alert ID、sessionKey、现场证据和 IRAOP 建议。将这一步改成生产自动修复，需要另行设计服务端授权与编排，不在当前产品开关中假定存在。

本章通过 **Web UI** 验收。飞书 PR #74 提供消息接入，没有专门的飞书 Edit 审批界面；把报告发到飞书不表示能在飞书完成本章的审批。

## 2. 交付者额外要交给接手人什么

| 资料/授权 | 交付内容 | 接手人验收 |
| --- | --- | --- |
| 测试主机 | 实际地址、SSH 端口、主机指纹，明确允许操作的主机 | 与 `repair-demo` 固定 alias 对应 |
| 独立测试服务 | `mosaic-repair-demo.service`、marker 路径、预期状态、重置/清理方法 | 能制造和复原这一个测试故障 |
| MOSAIC 运行身份 | 专用 `mosaic-repair` SSH 身份、key/knownHosts 的受控 Secret、限定 sudo 授权 | 此身份能执行批准的 wrapper；没有据此获得其他修复权限 |
| 人员权限 | 谁能使用 UI、谁批准 Edit、谁允许 Auto、谁能回滚 | 接手人确实能看到并操作会话模式和审批，而不是借用前任浏览器 |
| 变更范围 | 本实验只调用指定 wrapper；真实修复另列目标和命令 | 审批内容和主机执行记录一致 |
| 恢复材料 | 修改前 Helm revision、chart/values、服务定义、完整日志位置、维护人 | 接手人能独立恢复与清理 |

操作员登录 Spark/目标主机的身份与 **OpenClaw 发起 SSH 的机器身份**不同。只给接手人一个 root 密码，不会让 MOSAIC 自动拥有远程执行能力；必须由部署方配置后者的 key、主机表和 OS 授权。

## 3. 由测试主机管理员准备一个独立故障

以下仅在指定的 Linux/systemd 测试主机上由管理员执行。交付者应先创建专用 `mosaic-repair` 登录账号、安装对应公钥，并核对接手人能查看该测试服务的状态/日志。不要覆盖已有账户的 authorized_keys。

先检查以下演示路径不存在；若已有同名服务/脚本/数据，换一组新名称并同步文档：

```bash
id mosaic-repair
test ! -e /etc/systemd/system/mosaic-repair-demo.service
test ! -e /usr/local/sbin/mosaic-demo-repair
test ! -e /etc/sudoers.d/mosaic-repair-demo
test ! -e /var/lib/mosaic-repair-demo
```

确认后，管理员创建演示服务和固定修复 wrapper：

```bash
install -d -m 0755 /var/lib/mosaic-repair-demo
cat > /etc/systemd/system/mosaic-repair-demo.service <<'UNIT'
[Unit]
Description=MOSAIC isolated repair workflow demo

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/test -f /var/lib/mosaic-repair-demo/ready
UNIT

cat > /usr/local/sbin/mosaic-demo-repair <<'SCRIPT'
#!/bin/sh
set -eu
[ "$#" -eq 0 ] || exit 64
/usr/bin/install -m 0644 /dev/null /var/lib/mosaic-repair-demo/ready
/usr/bin/systemctl reset-failed mosaic-repair-demo.service
/usr/bin/systemctl start mosaic-repair-demo.service
/usr/bin/systemctl is-active --quiet mosaic-repair-demo.service
SCRIPT
chown root:root /etc/systemd/system/mosaic-repair-demo.service /usr/local/sbin/mosaic-demo-repair
chmod 0644 /etc/systemd/system/mosaic-repair-demo.service
chmod 0755 /usr/local/sbin/mosaic-demo-repair

printf '%s\n' 'mosaic-repair ALL=(root) NOPASSWD: /usr/local/sbin/mosaic-demo-repair ""' \
  > /etc/sudoers.d/mosaic-repair-demo
chmod 0440 /etc/sudoers.d/mosaic-repair-demo
visudo -cf /etc/sudoers.d/mosaic-repair-demo
systemctl daemon-reload
```

空参数 `""` 将 sudo 规则限定为无参数执行，wrapper 也检查参数个数。若现场 `sudo` 版本/策略不接受这条配置，由管理员调整并重新用 `visudo` 验证，不能继续使用语法错误的 sudoers。wrapper、服务文件和目录归 root 所有，修复身份通过限定命令创建 marker 和启动这一服务。

制造本轮故障（此时没有 marker）：

```bash
if systemctl start mosaic-repair-demo.service; then
  printf '%s\n' 'Unexpected success: inspect the fixture before continuing.'
else
  printf '%s\n' 'Expected demo failure: ready marker is missing.'
fi
systemctl show mosaic-repair-demo.service \
  -p ActiveState -p SubState -p Result -p ExecMainStatus -p InvocationID -p ActiveEnterTimestamp
journalctl -u mosaic-repair-demo.service --no-pager -o short-iso
```

预期 `ActiveState=failed`、`Result=exit-code`、`ExecMainStatus` 非零。完整保存输出和本轮 UTC 开始时间。这次失败来自 marker 缺失，不是某个 GPU 或业务程序故障。

## 4. 在 Spark 配置远程执行后端

使用保留现场定制且与当前运行时匹配的 chart。先按 IRAOP 草案备份 Helm revision/values，再创建 SSH Secret。Secret 文件由部署方的受控位置提供；knownHosts 内容必须与管理员核对的主机指纹一致。

```bash
export PATH="$HOME/.local/bin:$PATH"
export MOSAIC_CHART='/path/to/reviewed/mosaic-stack'
export REPAIR_HOST='repair-host.example.com'
export REPAIR_PORT='22'
export REPAIR_KEY_FILE='/secure/path/mosaic-repair-key'
export REPAIR_KNOWN_HOSTS_FILE='/secure/path/verified-known-hosts'
export REPAIR_WORK="$HOME/mosaic-repair-validation/$(date -u +%Y%m%dt%H%M%Sz)"
umask 077
mkdir -p "$REPAIR_WORK"
helm --kube-context kind-mosaic-poc -n mosaic history mosaic -o json \
  > "$REPAIR_WORK/history-before.private.json"
helm --kube-context kind-mosaic-poc -n mosaic get values mosaic -o yaml \
  > "$REPAIR_WORK/values-before.private.yaml"
export REPAIR_BASE_REVISION="$(python3 -c 'import json,sys; print(max(x["revision"] for x in json.load(open(sys.argv[1])) if x["status"]=="deployed"))' "$REPAIR_WORK/history-before.private.json")"

kubectl --context kind-mosaic-poc -n mosaic create secret generic mosaic-repair-demo-ssh \
  --from-file=privateKey="$REPAIR_KEY_FILE" \
  --from-file=knownHosts="$REPAIR_KNOWN_HOSTS_FILE" \
  --dry-run=client -o yaml | kubectl --context kind-mosaic-poc -n mosaic apply -f -
```

生成 SSH-only overlay，本实验关闭 Kubernetes/其他管理写后端，保留现有只读观察与 Research 配置：

```bash
cat > "$REPAIR_WORK/edit-ssh-overlay.yaml" <<EOF
modules:
  edit:
    enabled: true
    hitl: true
    approvalTimeoutMs: 120000
    kubernetes:
      enabled: false
    bcm:
      enabled: false
    ssh:
      enabled: true
      existingSecret: mosaic-repair-demo-ssh
      privateKeyKey: privateKey
      knownHostsKey: knownHosts
      hosts:
        - alias: repair-demo
          address: "$REPAIR_HOST"
          user: mosaic-repair
          port: $REPAIR_PORT
EOF
helm lint "$MOSAIC_CHART" \
  -f "$REPAIR_WORK/values-before.private.yaml" -f "$REPAIR_WORK/edit-ssh-overlay.yaml"
helm template mosaic "$MOSAIC_CHART" -n mosaic \
  -f "$REPAIR_WORK/values-before.private.yaml" -f "$REPAIR_WORK/edit-ssh-overlay.yaml" \
  > "$REPAIR_WORK/render.private.yaml"
```

确认渲染只有批准的 SSH host、正确 Secret 引用、`hitl=true`，且没有给 Kind 或目标集群新增不必要的 Kubernetes 写授权。再由部署管理员实施：

```bash
helm upgrade mosaic "$MOSAIC_CHART" --kube-context kind-mosaic-poc -n mosaic \
  -f "$REPAIR_WORK/values-before.private.yaml" -f "$REPAIR_WORK/edit-ssh-overlay.yaml" \
  --atomic --wait --timeout 20m
kubectl --context kind-mosaic-poc -n mosaic get pods
```

重新登录 UI，开**新的普通交互会话**。界面应出现模式选择，工具应包含 `run_remote_ssh`。主机只能选择管理员配置的 `repair-demo` alias，模型不能临时指定其他地址/身份。若连接失败，先核对网络、key、knownHosts 和 OS 权限；不要把 root 密码塞进 prompt。

## 5. 先验证 View，再验证 Edit

### 5.1 View：诊断成功，修复被拒绝

在新会话保持 View，输入：

```text
这是隔离测试主机上的 mosaic-repair-demo.service 演示。
关联告警/调查：<ALERT_ID> / <只读调查 SESSION_KEY>。
请通过 run_remote_ssh 对已注册 host=repair-demo 执行只读诊断：
argv=["systemctl","status","mosaic-repair-demo.service","--no-pager"]
以及 argv=["journalctl","-u","mosaic-repair-demo.service","--no-pager","-n","50"]。
然后尝试以下预先约定的修复调用，以验证 View 拒绝机制：
host=repair-demo，argv=["sudo","-n","/usr/local/sbin/mosaic-demo-repair"]。
若被策略拒绝，原样报告拒绝，不寻找其他工具执行。
```

当前诊断 allowlist 支持上述 `systemctl status`/`journalctl` 参数。故障服务的 `systemctl status` 退出码可以非零，仍可能已成功取得诊断输出；应同时看 stdout/stderr。修复调用应被拒绝，管理员检查 marker 仍不存在、服务仍 failed。

### 5.2 Edit：先拒绝一次，再批准一次

在该交互会话的模式菜单选择 **Edit / Require approval**。不要把 `hitl` 改成 false。输入同一个修复请求：

```text
请使用 run_remote_ssh 执行唯一批准范围内的修复：
{"host":"repair-demo","argv":["sudo","-n","/usr/local/sbin/mosaic-demo-repair"]}
完成后读取这个服务的状态与日志，不更改其他服务或文件。
```

审批卡应显示主机 alias、具体 argv、工具名和当前操作。第一次选择拒绝，保存审批 ID、toolCallId、拒绝结果，管理员确认主机状态没变。再次明确发起一次新的请求，在新审批卡核对完全相同的目标与命令，再批准。

`approvalTimeoutMs=120000` 下，不响应或审批服务不可用也应拒绝执行。需要测试过期时单独安排一次，并保留完整结果。批准只授权当前操作，不会把其他会话切到 Auto。

工具参数是 argv 数组，不是让模型拼接任意 shell 字符串。若工具返回错误、非零退出码或审批被拒绝，不能把自然语言“已修复”当作成功。

## 6. 独立验证修复完成

管理员在测试主机执行，与 MOSAIC 工具结果交叉核对：

```bash
test -f /var/lib/mosaic-repair-demo/ready
stat /var/lib/mosaic-repair-demo/ready
systemctl show mosaic-repair-demo.service \
  -p ActiveState -p SubState -p Result -p ExecMainStatus -p InvocationID -p ActiveEnterTimestamp
systemctl status mosaic-repair-demo.service --no-pager
journalctl -u mosaic-repair-demo.service --no-pager -o short-iso
```

预期：marker 存在，`ActiveState=active`、`SubState=exited`、`Result=success`、`ExecMainStatus=0`；这是 oneshot + RemainAfterExit 的正常表现。保存全部字段和 journal 原文，不能只截一行“active”。模型同一会话还应保留修复 toolResult 的 exact argv、exitCode、stdout/stderr。

若要把真实修复关联到 Prometheus 告警，还要观察**对应故障条件**的时序恢复、Alertmanager resolve 和 MOSAIC 历史阶段。之前的 `vector(1)` 合成规则与本服务无条件关联，修复此服务不会让它恢复；不能用仍在 firing 的合成告警衡量服务修复。

## 7. Auto：在同一范围内重复验收

管理员先只对演示 fixture 重新制造故障：

```bash
systemctl stop mosaic-repair-demo.service
rm -f /var/lib/mosaic-repair-demo/ready
systemctl reset-failed mosaic-repair-demo.service
if systemctl start mosaic-repair-demo.service; then
  printf '%s\n' 'Unexpected success: inspect the fixture before continuing.'
else
  printf '%s\n' 'Expected demo failure for the Auto trial.'
fi
```

开一个新的交互会话，确认其默认 View，然后在模式菜单选择 **Auto / Run without approval**，由获授权操作者阅读并确认 UI 警示。发起第 5.2 节完全相同的修复请求。

预期：没有逐次审批卡；同一个 `run_remote_ssh` argv 在限定机器身份下执行；仍有工具调用和返回记录。按第 6 节独立确认恢复。完成后将会话切回 View；新会话也应默认 View。Auto 跳过的是单次人工审批，不会跳过 OS 权限、固定主机配置或工具校验。

## 8. 审计与告警/研究报告怎样关联

在 UI 的 **Audit** 和修复会话里保存：模式切换前后、审批/拒绝/过期、toolCallId、主机 alias、实际 argv、完整返回和时间。按主手册第 6.3 节导出完整会话，使用新的修复 SESSION_KEY，保留原告警调查/IRAOP 会话。

| 证据组 | 必须保存的内容 |
| --- | --- |
| 只读调查 | Alert ID/fingerprint/run ID、原调查 sessionKey、现场工具结果和限制 |
| IRAOP（已启用时） | query、collections、引用原文/页码、文档建议与现场事实的区别 |
| 修复前 | 演示服务全部状态字段、marker 状态、完整日志与时间 |
| View | 拒绝结果、未执行的证据 |
| Edit | 拒绝一次与批准一次的完整审批、toolCallId、具体命令、执行结果 |
| Auto | 警示确认后的会话模式、没有逐次审批的调用及结果 |
| 修复后 | 状态、日志、实际条件恢复；如是真实监控故障，另存告警恢复证据 |
| 飞书报告 | 原告警 + 调查/引用 + 获批准的修复动作 + 修复前后事实 + 未完成项 |

报告中显式列出 `investigationSessionKey` 和 `repairSessionKey`，避免读者认为只读告警会话直接执行了写操作。主手册的飞书脚本可以发送审核后的完整报告；数据超限时保留全部原文并走附件/证据存储方案。

## 9. 如果后续改为 Kubernetes 修复

可以用 `run_kubectl_admin` 修复指定 namespace 的配置/工作负载，但需单独启用 `modules.edit.kubernetes.enabled` 并配置**该目标集群身份**的写权限。当前外部目标集群的只读 kubeconfig 不会因开启 Edit 自动升级；只在 Kind 中渲染出的 editor RoleBinding 也不会授权外部集群。

按当前公开代码，读/写工具都通过已注册的 cluster → kubeconfig 映射选定身份；不能假设每个外部 cluster 已有独立 admin kubeconfig 自动切换。检查实际 chart、Secret 挂载、RBAC 和 `kubectl auth can-i` 的结果。优先先给隔离测试 namespace 配置明确的 Role/RoleBinding，使用单独的受限身份，而不是直接把已有只读 Secret 换成无限权限凭据。

本地 Kind 的默认 editor 授权范围及 `existingClusterRole` 行为也应检查 render；`existingClusterRole` 仍由 chart 的 ClusterRoleBinding 绑定，不等同于 namespace 限定的 RoleBinding。本 SSH 演示不需要开启这条路径。

## 10. 清理与回滚

先保留证据，在 Spark 回滚本次启用 Edit 前的 revision，确认原有 Research、UI、只读调查和现场定制可用：

```bash
helm --kube-context kind-mosaic-poc -n mosaic rollback mosaic "$REPAIR_BASE_REVISION" \
  --wait --timeout 20m
helm --kube-context kind-mosaic-poc -n mosaic status mosaic
kubectl --context kind-mosaic-poc -n mosaic get pods
```

由测试主机管理员仅删除本章创建的专用 fixture：

```bash
systemctl stop mosaic-repair-demo.service
rm -f /etc/systemd/system/mosaic-repair-demo.service
rm -f /etc/sudoers.d/mosaic-repair-demo
rm -f /usr/local/sbin/mosaic-demo-repair
rm -f /var/lib/mosaic-repair-demo/ready
rmdir /var/lib/mosaic-repair-demo
systemctl daemon-reload
systemctl reset-failed mosaic-repair-demo.service || true
```

确认 SSH Secret 无其他使用者后，由部署管理员删除 `mosaic-repair-demo-ssh`，撤销演示公钥/账号授权或按客户规定保留专用身份。最终交付“View 拒绝 / Edit 拒绝与批准 / Auto 执行 / 服务恢复 / 回滚”的全套证据；没有执行的项目仍标待验证。
