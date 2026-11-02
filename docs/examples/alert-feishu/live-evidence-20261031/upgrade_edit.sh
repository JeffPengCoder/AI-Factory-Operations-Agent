#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
work="$HOME/.local/share/mosaic-validation-20261031"
helm="$HOME/.local/bin/helm"
kubectl="$HOME/.local/bin/kubectl"
trap 'printf "%s\n" "$?" > "$work/edit-upgrade-exit.txt"' EXIT
revision="$($helm --kube-context kind-mosaic-poc -n mosaic history mosaic -o json | python3 -c 'import json,sys; print(max(x["revision"] for x in json.load(sys.stdin) if x["status"]=="deployed"))')"
test "$revision" = 9
$helm --kube-context kind-mosaic-poc -n mosaic get values mosaic -o yaml > "$work/before-edit-values.private.yaml"
$kubectl --context kind-mosaic-poc -n mosaic get secret mosaic-validation-ssh -o name
$helm lint "$work/baseline/chart.tgz" -f "$work/before-edit-values.private.yaml" -f "$work/edit-overlay.yaml"
$helm template mosaic "$work/baseline/chart.tgz" -n mosaic -f "$work/before-edit-values.private.yaml" -f "$work/edit-overlay.yaml" > "$work/edit-render.private.yaml"
python3 - "$work/edit-render.private.yaml" <<'PY'
import sys,yaml
for item in yaml.safe_load_all(open(sys.argv[1])):
    if item and item.get('kind')=='ClusterRoleBinding':
        assert not item['metadata']['name'].endswith('-oc-editor'), 'Unexpected Kubernetes editor binding'
PY
$helm upgrade mosaic "$work/baseline/chart.tgz" --kube-context kind-mosaic-poc -n mosaic \
  -f "$work/before-edit-values.private.yaml" -f "$work/edit-overlay.yaml" \
  --atomic --wait --timeout 20m
$helm --kube-context kind-mosaic-poc -n mosaic history mosaic -o json > "$work/edit-history-after.json"
$kubectl --context kind-mosaic-poc -n mosaic get deploy,sts,pods,jobs,pvc,svc -o json > "$work/edit-resources-after.json"
