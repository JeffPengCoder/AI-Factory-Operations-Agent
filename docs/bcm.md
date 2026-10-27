# Base Command Manager Installation Without Kubernetes

This guide installs AI Factory Operations Agent on a Base Command Manager
head node when Base Command Manager does not manage a Kubernetes cluster. It creates a
single-node Kind cluster on the head node and enables read-only Base Command Manager access over
SSH. Kind remains independent of Base Command Manager's `cm-kubernetes-setup` inventory.

For upgrades, UI access, and module configuration, see the
[shared Helm guide](installation.md).

## 1. Prerequisites

Run this procedure as `root` on the Base Command Manager head node. Install Docker, Kind, Helm
3, and `kubectl`, then verify Base Command Manager and each dependency:

```bash
docker version
kind version
helm version
kubectl version --client
cmsh -c 'device; list'
```

Ask your NVIDIA contact to invite the email address you will use with NGC to
the AI Factory Operations Agent `afoa-release` team in the private registry. Accept the invitation while
signed in with that account; use a private browser window if another NGC
account is already signed in. Then create an NGC personal API key from
[NGC Setup > API Keys](https://org.ngc.nvidia.com/setup/api-keys), include the
Private Registry service, and confirm that the account can pull the required
private registry artifacts. Obtain an API key, `/v1/chat/completions` base URL,
and model name from the same OpenAI-compatible LLM provider.

The Base Command Manager adapter also requires an SSH private key that can connect to the head
node as `root`. It uses that identity to create or update the dedicated
`aichatbotuser` CMSH account with the `readonly` profile. Do not create that
account manually.

## 2. Create The Kind Cluster

```bash
kind create cluster --name mosaic --wait 120s
kubectl config use-context kind-mosaic
kubectl cluster-info

KIND_NETWORK_ID=$(docker network inspect kind --format '{{.Id}}')
KIND_BRIDGE="br-${KIND_NETWORK_ID:0:12}"
KIND_GATEWAY=$(docker network inspect kind --format '{{(index .IPAM.Config 0).Gateway}}')
printf 'bridge=%s gateway=%s\n' "$KIND_BRIDGE" "$KIND_GATEWAY"
```

Kind provides the `standard` storage class. The Docker network gateway is the
Base Command Manager head address reachable from the Kind cluster; `127.0.0.1` inside a pod
would refer to that pod.

## 3. Configure Shorewall

Skip this section when Shorewall is not installed or active. On a Base Command Manager head node
where Shorewall is active, Docker and Shorewall both manage iptables. A
Shorewall start, reload, or restart can otherwise delete Docker's forwarding,
NAT, and port-publishing rules. Keep Shorewall enabled when the Base Command Manager head-node
role requires it. This local workflow does not require exposing the Kind API
outside the head node or adding a temporary Base Command Manager firewall role for it.

This procedure follows [Shorewall's Docker integration](https://shorewall.org/Docker.html)
and was validated with Shorewall 5.2.8. Shorewall 5.2.4 or later is required
for `DOCKER_BRIDGE`. Back up the existing Shorewall files before editing them.
If Base Command Manager or another configuration manager owns these files, store the equivalent
entries in that system so they survive configuration regeneration.

Set these values in `/etc/shorewall/shorewall.conf`, replacing the example
bridge name with `$KIND_BRIDGE` from the previous step:

```ini
DOCKER=Yes
DOCKER_BRIDGE=br-0123456789ab
```

Add a Docker zone to `/etc/shorewall/zones`:

```text
dock    ipv4
```

Add the Kind bridge to `/etc/shorewall/interfaces`:

```text
dock    br-0123456789ab    detect    bridge
```

Add these entries before the final catch-all policy in
`/etc/shorewall/policy`:

```text
dock    fw     REJECT    info
dock    all    ACCEPT
```

Permit the Base Command Manager adapter to reach only SSH on the head node by adding this entry
to `/etc/shorewall/rules`:

```text
ACCEPT:info    dock    fw    tcp    22
```

On Debian-derived systems, create
`/etc/systemd/system/shorewall.service.d/docker.conf` so service restarts use
`stop` instead of clearing Docker's rules:

```ini
[Service]
ExecStop=
ExecStop=/usr/sbin/shorewall $OPTIONS stop
```

With Shorewall 5.2.8 and Docker 29, restored Docker rules also required
established return traffic to be accepted before Docker's hooks. Add the
following before the final `return 0` in `/etc/shorewall/start`, replacing the
example bridge name:

```bash
KIND_BRIDGE=br-0123456789ab
/sbin/iptables -w -n -L DOCKER-USER >/dev/null 2>&1 || return 0
/sbin/iptables -w -C DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
  /sbin/iptables -w -I DOCKER-USER 1 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
/sbin/iptables -w -C OUTPUT -o "$KIND_BRIDGE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
  /sbin/iptables -w -I OUTPUT 1 -o "$KIND_BRIDGE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
return 0
```

Check the configuration before changing the running firewall. Restart Docker
once to recreate any rules Shorewall previously removed, then verify that the
Kind node and pod egress survive a Shorewall restart:

```bash
shorewall check
systemctl daemon-reload
systemctl restart docker
systemctl restart shorewall
kubectl wait --for=condition=Ready node/mosaic-control-plane --timeout=120s

kubectl run shorewall-egress-check --rm -i --restart=Never \
  --image=curlimages/curl:8.15.0 -- \
  curl --connect-timeout 5 --max-time 15 -sS -o /dev/null \
  -w 'http=%{http_code} tls=%{ssl_verify_result}\n' \
  https://integrate.api.nvidia.com/v1/models

systemctl restart shorewall
kubectl wait --for=condition=Ready node/mosaic-control-plane --timeout=120s
```

An HTTP response such as `401` with `tls=0` confirms network egress and
successful TLS verification. The bridge name belongs to the current Docker
network. Update the Shorewall configuration if the Kind network is recreated.

## 4. Configure Credentials

Set the provider values and select the head node's Kind-network address. The
SSH preflight must return `0`, confirming root access through the same network
path the Base Command Manager adapter will use:

```bash
export EXTERNAL_LLM_BASE_URL='https://integrate.api.nvidia.com/v1'
export EXTERNAL_LLM_MODEL='nvidia/nemotron-3.5-super-vl-120b-a12b'
export CLUSTER_MANAGER_HEAD_HOST="$KIND_GATEWAY"
export CLUSTER_MANAGER_SSH_KEY_PATH='/root/.ssh/id_ecdsa'
export MOSAIC_CHART='oci://nvcr.io/0948643769302270/afoa-release/mosaic-stack'

read -rsp 'NGC API key: ' NGC_API_KEY; echo
read -rsp 'External LLM API key: ' EXTERNAL_LLM_API_KEY; echo

test -r "$CLUSTER_MANAGER_SSH_KEY_PATH"
ssh -i "$CLUSTER_MANAGER_SSH_KEY_PATH" -o BatchMode=yes \
  -o StrictHostKeyChecking=accept-new "$CLUSTER_MANAGER_HEAD_HOST" 'id -u'

printf '%s' "$NGC_API_KEY" | helm registry login nvcr.io \
  --username '$oauthtoken' \
  --password-stdin

kubectl create namespace mosaic --dry-run=client -o yaml | kubectl apply -f -
kubectl -n mosaic create secret generic mosaic-external-llm \
  --from-literal=apiKey="$EXTERNAL_LLM_API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n mosaic create secret generic bcm-host-ssh-key \
  --from-file=id_ecdsa="$CLUSTER_MANAGER_SSH_KEY_PATH" \
  --dry-run=client -o yaml | kubectl apply -f -
```

The private key is stored in the `bcm-host-ssh-key` Kubernetes Secret and
mounted only into the Base Command Manager adapter pod.

## 5. Install AI Factory Operations Agent

This installation enables the UI, local Kubernetes inspection, and read-only
Base Command Manager inspection. Other cluster integrations remain disabled.

```bash
# Remove --devel for the latest stable release, or replace it with --version 0.0.1 to pin that release.
helm upgrade --install mosaic "$MOSAIC_CHART" \
  --devel \
  -n mosaic \
  --create-namespace \
  --set global.registryCredentials.create=true \
  --set-string global.registryCredentials.password="$NGC_API_KEY" \
  --set llm.mode=external \
  --set-string llm.external.baseUrl="$EXTERNAL_LLM_BASE_URL" \
  --set-string llm.external.model="$EXTERNAL_LLM_MODEL" \
  --set llm.external.existingSecret=mosaic-external-llm \
  --set modules.ui.enabled=true \
  --set modules.execution.enabled=true \
  --set modules.kubernetes.enabled=true \
  --set modules.bcm.enabled=true \
  --set bcmMcp.enabled=true \
  --set bcmMcp.mode=ssh-adapter \
  --set-string bcmMcp.headHost="$CLUSTER_MANAGER_HEAD_HOST" \
  --set bcmMcp.hostSshKeySecretName=bcm-host-ssh-key \
  --set modules.slurm.enabled=false \
  --set modules.observability.enabled=false \
  --set modules.grafana.enabled=false \
  --set modules.research.enabled=false \
  --set modules.diagnostics.enabled=false \
  --set modules.terminal.enabled=false \
  --reset-values \
  --atomic \
  --wait \
  --timeout 12m

unset NGC_API_KEY EXTERNAL_LLM_API_KEY
```

## 6. Validate Base Command Manager Access

Confirm that the Kind node and AI Factory Operations Agent workloads are ready, then issue a real
read-only Base Command Manager request. The first request creates or updates `aichatbotuser`:

```bash
kubectl get nodes
kubectl -n mosaic get pods

MANAGER_TEST_PROMPT='/cluster-management Use Base Command Manager to run "device; list" and summarize the first five devices.'
kubectl -n mosaic exec deploy/mosaic-ui -- \
  mosaic --session bcm-install-validation --timeout-ms 180000 \
  "$MANAGER_TEST_PROMPT"

cmsh -c 'user; use aichatbotuser; get profile'

if systemctl is-active --quiet shorewall; then
  systemctl restart shorewall
  kubectl wait --for=condition=Ready node/mosaic-control-plane --timeout=120s
  kubectl -n mosaic exec deploy/mosaic-ui -- \
    mosaic --session bcm-restart-validation --timeout-ms 180000 \
    "$MANAGER_TEST_PROMPT"
fi
```

The `cmsh` profile command must return `readonly`. Base Command Manager edit and administration
remain disabled.

## 7. Open The UI Remotely

Keep this port-forward running on the Base Command Manager head node:

```bash
kubectl -n mosaic port-forward svc/mosaic-ui 3210:3000
```

From the operator's workstation, keep an SSH tunnel to the head node running:

```bash
ssh -L 3210:127.0.0.1:3210 root@bcm-head.example.com
```

Retrieve the generated UI credentials on the head node:

```bash
kubectl -n mosaic get secret mosaic-ui-auth \
  -o jsonpath='{.data.username}' | base64 --decode; echo
kubectl -n mosaic get secret mosaic-ui-auth \
  -o jsonpath='{.data.password}' | base64 --decode; echo
```

Open `http://127.0.0.1:3210` on the workstation. Both forwarding processes
must remain running.

## 8. Optional: Read-Only Redfish

Redfish lets the agent read a node's BMC when the node is down or unreachable in-band: power state,
hardware health, temperatures, fans, power supplies, BMC event logs, and firmware inventory. The
agent passes only a Base Command Manager hostname. The Base Command Manager adapter looks up the
BMC address and credentials through CMSH, the same lookup the Hardware Agent uses, and never returns
them to the model.

Prerequisites:

- The Base Command Manager adapter runs in `ssh-adapter` mode (section 5).
- The adapter's SSH identity can read `bmcsettings` and BMC interfaces through CMSH on the head node.
- The head node can reach the BMC network over HTTPS and has `curl`. Check one BMC from the head node:

  ```bash
  curl -sk https://<bmc-address>/redfish/v1 | head -c 300; echo
  ```

Enable it:

```bash
helm upgrade mosaic "$MOSAIC_CHART" \
  --devel \
  -n mosaic \
  --reuse-values \
  --set modules.bcm.redfish.enabled=true \
  --wait \
  --timeout 12m
```

By default each request runs `curl` on the head node over the adapter's existing SSH session
(`modules.bcm.redfish.viaHeadNode=true`), because the head node is routed to the BMC network. The
BMC credential reaches `curl` on standard input, so it does not appear in process listings. Set
`viaHeadNode=false` only when the adapter pod itself can reach the BMCs. BMCs usually present
self-signed certificates, so `modules.bcm.redfish.verifyTls` defaults to `false`.
`modules.bcm.redfish.timeoutSeconds` (default `60`) bounds each request; some DGX BMCs take about
30 seconds to return the expanded firmware inventory.

The adapter enforces the following allowlist before it looks up any credential. Only `GET` is
used, and the only query parameters accepted are `$top`, `$skip`, and `$expand=.` limited to one
level, which is refused on the service root:

| Resource | Paths under `/redfish/v1` |
| --- | --- |
| Service root and collections | `/`, `Systems`, `Chassis`, `Managers` |
| Systems | `Systems/{id}` and its `Processors`, `Memory`, `Storage`, `EthernetInterfaces`, and `LogServices/{id}/Entries` |
| Chassis | `Chassis/{id}` and its `Thermal`, `ThermalSubsystem`, `Power`, `PowerSubsystem`, and `Sensors` |
| Managers | `Managers/{id}` and its `EthernetInterfaces` and `LogServices/{id}/Entries` |
| Firmware and tasks | `UpdateService/FirmwareInventory`, `TaskService/Tasks` |

Everything else is refused, including any path containing `Actions`, and `AccountService`,
`SessionService`, `CertificateService`, `EventService`, `SecureBoot`, `Bios/Settings`, and
`VirtualMedia`. Paths with `..`, `//`, `%`, or other query parameters are also refused. The adapter
also checks every resource embedded in a response, such as `$expand` results and continuation pages,
against the same allowlist. It reduces any embedded resource outside it to a bare link, so a BMC that
expands more than requested cannot return denied content. Fields named like passwords, tokens, or
secrets are redacted from responses. Resets and other BMC actions are not
available in any session mode.
