# helm-law-craw

Helm chart for the **scraw law-crawling stack**: deploys `scrapyd` (shared crawl
service), the `scraw-law-contracts` runner (SAMR contract templates crawler as a
CronJob), and `redis` + `postgresql` (Bitnami subcharts) — pulling the application
images from the Harbor registry.

| Component          | Kind      | Image (Harbor)                              |
|--------------------|-----------|---------------------------------------------|
| scrapyd            | Deployment+Service `:6800` | `<host>/scraw/scraw-ops-scrapyd:<tag>` |
| scraw-law-contracts| CronJob   | `<host>/scraw/scraw-law-contracts:<tag>`    |
| redis              | Bitnami subchart (standalone) | —                                    |
| postgresql         | Bitnami subchart            | —                                       |

## Prerequisites

### 1. Harbor is HTTP-only → configure nodes as insecure registry
Harbor (`23.144.68.246:30880`) serves HTTP, not HTTPS. The chart creates an
`imagePullSecret` for **auth**, but it cannot configure node container runtimes.
Every k8s node must treat the registry as insecure. For **containerd**, edit
`/etc/containerd/config.toml`:

```toml
[plugins."io.containerd.grpc.v1.cri".registry.mirrors."23.144.68.246:30880"]
  endpoint = ["http://23.144.68.246:30880"]
[plugins."io.containerd.grpc.v1.cri".registry.configs."23.144.68.246:30880".tls]
  insecure_skip_verify = true
```

Then `sudo systemctl restart containerd` on each node. For **docker** daemons,
add `"23.144.68.246:30880"` to `insecure-registries` in `/etc/docker/daemon.json`
and restart docker.

### 2. Helm + subchart dependencies
```bash
helm dependency update helm-law-craw/   # pulls Bitnami redis + postgresql into charts/
```

## Install

```bash
# Set Harbor robot creds (or pre-create a secret and set harbor.existingSecret)
helm install law-craw helm-law-craw/ \
  --namespace scraw --create-namespace \
  --set harbor.username='robot$scraw+scraw-ci' \
  --set harbor.password='<robot-password>'

# Pin a specific image tag:
helm upgrade law-craw helm-law-craw/ \
  --namespace scraw \
  --set harbor.username='robot$scraw+scraw-ci' \
  --set harbor.password='<robot-password>' \
  --set images.scrapyd.tag=sha-cf73230 \
  --set images.lawContracts.tag=sha-6cb58e8
```

## Usage

```bash
# scrapyd projects
kubectl -n scraw port-forward svc/law-craw-helm-law-craw-scrapyd 6800:6800
curl -s http://localhost:6800/listprojects.json | python3 -m json.tool

# Trigger a runner run immediately (e.g. while suspended):
kubectl -n scraw create job --from=cronjob/law-craw-helm-law-craw-law-contracts manual-1
```

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `harbor.host` | `23.144.68.246:30880` | Harbor registry host:port |
| `harbor.username` / `harbor.password` | `""` | Robot creds for imagePullSecret |
| `harbor.existingSecret` | `""` | Reuse a pre-created imagePullSecret |
| `images.scrapyd.{repository,tag,pullPolicy}` | `…/scraw-ops-scrapyd:latest` | scrapyd image |
| `images.lawContracts.{repository,tag,pullPolicy}` | `…/scraw-law-contracts:latest` | runner image |
| `scrapyd.replicas` | `1` | scrapyd Deployment replicas |
| `scrapyd.redisUrl` | `""` | Override redis (empty → in-chart redis) |
| `lawContracts.schedule` | `0 2 * * *` | CronJob schedule |
| `lawContracts.suspend` | `false` | Suspend the CronJob (manual-only) |
| `lawContracts.{sqlitePath,jsonlPath}` | `data/scraw.db`, `output/items.jl` | Runner output paths (PVC-mounted) |
| `lawContracts.persistence.*` | enabled, RWO 5Gi | PVC for runner outputs |
| `redis.enabled` / `postgresql.enabled` | `true` | Disable to use external hosts |

## Notes

- The runner writes **SQLite + JSON Lines** to the PVC (its existing pipelines);
  postgresql is included as stack infrastructure for scrapyd-deployed spiders, not
  as the law-contracts output sink.
- `charts/` and `Chart.lock` are gitignored — run `helm dependency update` after clone.
