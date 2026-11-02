#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
work="$HOME/.local/share/mosaic-validation-20261031"
helm="$HOME/.local/bin/helm"
kubectl="$HOME/.local/bin/kubectl"
status_file="$work/research-upgrade-exit.txt"
trap 'printf "%s\n" "$?" > "$status_file"' EXIT
revision="$($helm --kube-context kind-mosaic-poc -n mosaic history mosaic -o json | python3 -c 'import json,sys; print(max(x["revision"] for x in json.load(sys.stdin) if x["status"]=="deployed"))')"
test "$revision" = 8
test -s "$work/baseline/values.yaml"
test -s "$work/baseline/chart.tgz"
$kubectl --context kind-mosaic-poc -n mosaic get secret iraop-secrets -o name
docker exec mosaic-poc-control-plane mkdir -p /var/local/mosaic-validation-20261031/corpus
docker cp "$work/mosaic-validation-control.pdf" mosaic-poc-control-plane:/var/local/mosaic-validation-20261031/corpus/mosaic-validation-control.pdf
docker exec mosaic-poc-control-plane chmod 0755 /var/local/mosaic-validation-20261031/corpus
docker exec mosaic-poc-control-plane chmod 0644 /var/local/mosaic-validation-20261031/corpus/mosaic-validation-control.pdf
$helm lint "$work/baseline/chart.tgz" -f "$work/baseline/values.yaml" -f "$work/research-overlay.yaml"
$helm template mosaic "$work/baseline/chart.tgz" -n mosaic -f "$work/baseline/values.yaml" -f "$work/research-overlay.yaml" > "$work/research-render.private.yaml"
$helm upgrade mosaic "$work/baseline/chart.tgz" --kube-context kind-mosaic-poc -n mosaic \
  -f "$work/baseline/values.yaml" -f "$work/research-overlay.yaml" \
  --atomic --wait --timeout 20m
$helm --kube-context kind-mosaic-poc -n mosaic history mosaic -o json > "$work/research-history-after.json"
$kubectl --context kind-mosaic-poc -n mosaic get deploy,sts,pods,jobs,pvc,svc -o json > "$work/research-resources-after.json"
