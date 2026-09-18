#!/usr/bin/env bash
# Read-only collector for a separately authorized capacity test.
set -euo pipefail
ns="${1:-jinshu}"; seconds="${2:-300}"; out="${3:-evidence/v4/hpa}"
mkdir -p "$out"
kubectl config current-context > "$out/context.txt"
kubectl version -o json > "$out/versions.json"
end=$((SECONDS+seconds))
while ((SECONDS < end)); do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  kubectl -n "$ns" get hpa jinshu-service -o json > "$out/$stamp-hpa.json"
  kubectl -n "$ns" get pods -l app=jinshu-service -o json > "$out/$stamp-pods.json"
  kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/$ns/pods/*/jinshu_inflight" > "$out/$stamp-metrics.json" || true
  sleep 10
done
kubectl -n "$ns" get events --sort-by=.metadata.creationTimestamp > "$out/events.txt"
echo "Observed scaling only; maxReplicas=20 is not evidence that 20 Pods ran."
