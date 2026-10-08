#!/usr/bin/env bash
# Reproduce against a new disposable local cluster; never touches a default kube context.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/work/tools:$PATH"
export KUBECONFIG="$PWD/work/kubernetes/kubeconfig"
export BUILDX_CONFIG="$PWD/work/buildx"
mkdir -p work/kubernetes docs/evidence
CLUSTER=recheck-ops
if kind get clusters | grep -qx "$CLUSTER"; then
  echo "Cluster $CLUSTER already exists. Delete it explicitly with kind delete cluster --name $CLUSTER before a fresh run." >&2
  exit 1
fi
# Some nested Linux runtimes have no IPv6 iptables support. IPv4 suffices for this lab.
docker network inspect kind >/dev/null 2>&1 || docker network create --driver bridge kind
build_args=()
if [[ -n "${CODEX_PROXY_CERT:-}" ]]; then
  build_args+=(--secret "id=proxy_ca,src=$CODEX_PROXY_CERT")
fi
if [[ "${RECHECK_K8S_SKIP_BUILD:-0}" != 1 ]]; then
docker build "${build_args[@]}" -t recheck:kubernetes-build .
# Native snapshotting copies each layer. Flatten only the disposable lab image
# to reduce disk amplification; a shared 32GB runner can still run out of space.
export_container=$(docker create recheck:kubernetes-build)
trap 'docker rm "$export_container" >/dev/null 2>&1 || true' EXIT
docker export "$export_container" | docker import \
  --change 'USER runner' --change 'WORKDIR /app' \
  --change 'ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1' \
  --change 'CMD ["python", "scripts/serve_demo.py"]' - recheck:kubernetes
docker rm "$export_container"
trap - EXIT
fi
docker pull postgres:16-alpine
postgres_container=$(docker create postgres:16-alpine)
trap 'docker rm -v "$postgres_container" >/dev/null 2>&1 || true' EXIT
docker export "$postgres_container" | docker import \
  --change 'ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LANG=en_US.utf8 PG_MAJOR=16 PGDATA=/var/lib/postgresql/data' \
  --change 'ENTRYPOINT ["docker-entrypoint.sh"]' --change 'CMD ["postgres"]' - recheck:postgres-lab
docker rm -v "$postgres_container"
trap - EXIT
kind create cluster --name "$CLUSTER" --config infra/k8s/kind.yaml --image kindest/node:v1.32.2 --kubeconfig "$KUBECONFIG" --wait 180s
kind load docker-image recheck:kubernetes recheck:postgres-lab --name "$CLUSTER"
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/postgres.yaml
kubectl rollout status statefulset/postgres -n recheck --timeout=180s
kubectl apply -f infra/k8s/migrate.yaml
kubectl wait -n recheck --for=condition=complete job/schema-init --timeout=120s
kubectl apply -f infra/k8s/services.yaml -f infra/k8s/deployments.yaml
kubectl rollout status deployment/model -n recheck --timeout=180s
kubectl rollout status deployment/api -n recheck --timeout=180s
python3 scripts/k8s_verify.py --base http://127.0.0.1:18080
