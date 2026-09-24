# helm-law-scraw

Helm chart for the **scraw law-crawling stack**: deploys `scrapyd` (shared crawl
service), the `scraw-law-contracts` runner (SAMR contract templates crawler as a
CronJob), the `flk-law-crawl` runner (flk.npc.gov.cn regulation incremental
crawler, from `fd-law-data`), and `redis` + `postgresql` (Bitnami subcharts).

| Component          | Kind      | Image reference                            |
|--------------------|-----------|--------------------------------------------|
| scrapyd            | Deployment+Service `:6800` | `<registry>/scraw-ops-scrapyd:<tag>` |
| scraw-law-contracts| CronJob   | `<registry>/scraw-law-contracts:<tag>`     |
| flk-law-crawl      | CronJob   | `<registry>/fd-law-data:<tag>`             |
| redis              | Bitnami subchart (standalone) | —                                    |
| postgresql         | Bitnami subchart            | —                                       |

## Quickstart

```bash
# 1. Fetch Bitnami subchart dependencies
helm dependency build charts/helm-law-scraw/

# 2. Install (defaults to Docker Hub; override registry for your own)
helm install law-craw charts/helm-law-scraw/ \
  --namespace scraw --create-namespace \
  --set registry=docker.io \
  --set images.scrapyd.repository=scraw-ops-scrapyd \
  --set images.lawContracts.repository=scraw-law-contracts

# 3. Verify
kubectl -n scraw get pods
# scrapyd: 1/1, redis: 1/1, postgresql: 1/1

# 4. Forward scrapyd
kubectl -n scraw port-forward svc/law-craw-helm-law-scraw-scrapyd 6800:6800
curl -s http://localhost:6800/listprojects.json
```

## Prerequisites

### Image registry
The chart image references are built as `<registry>/<repository>:<tag>`.
- **Default**: `registry: docker.io` → images resolve from Docker Hub.
- **Override**: set `registry` to your registry host, with or without a project path:
  ```bash
  --set registry=myregistry.example.com:5000/myproject
  ```
  This produces `myregistry.example.com:5000/myproject/scraw-ops-scrapyd:latest`.

### Insecure (HTTP-only) registry
If your registry serves HTTP, every k8s node must be configured to treat it as
insecure. For **containerd** (`/etc/containerd/config.toml`):
```toml
[plugins."io.containerd.grpc.v1.cri".registry.mirrors."<your-host>"]
  endpoint = ["http://<your-host>"]
[plugins."io.containerd.grpc.v1.cri".registry.configs."<your-host>".tls]
  insecure_skip_verify = true
```
Then `sudo systemctl restart containerd`. For **docker**: add `"<your-host>"` to
`insecure-registries` in `/etc/docker/daemon.json` and restart docker.

### Helm dependencies
```bash
helm dependency build charts/helm-law-scraw/
```
Or with the included Makefile:
```bash
make dep-build
```

## Private registry with credentials

Create an imagePullSecret and pass it to the chart:

```bash
# Option A: let the chart create the secret
helm install law-craw charts/helm-law-scraw/ \
  --set imageCredentials.host=myregistry.example.com \
  --set imageCredentials.username=myuser \
  --set imageCredentials.password=mypassword

# Option B: pre-create the secret and reference it
kubectl -n scraw create secret docker-registry my-pull-secret \
  --docker-server=myregistry.example.com \
  --docker-username=myuser \
  --docker-password=mypassword
helm install law-craw charts/helm-law-scraw/ \
  --set imageCredentials.existingSecret=my-pull-secret
```

## Usage

```bash
# scrapyd projects
kubectl -n scraw port-forward svc/law-craw-helm-law-scraw-scrapyd 6800:6800
curl -s http://localhost:6800/listprojects.json | python3 -m json.tool

# Trigger a runner run immediately (e.g. while suspended):
kubectl -n scraw create job --from=cronjob/law-craw-helm-law-scraw-law-contracts manual-1
```

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `registry` | `docker.io` | Registry prefix prepended to all image repositories |
| `imageCredentials.host` | `""` | Registry hostname for the imagePullSecret auths key |
| `imageCredentials.username` / `imageCredentials.password` | `""` | Credentials for the imagePullSecret |
| `imageCredentials.existingSecret` | `""` | Reuse a pre-created imagePullSecret |
| `images.scrapyd.{repository,tag,pullPolicy}` | `scraw-ops-scrapyd:latest` | scrapyd image |
| `images.lawContracts.{repository,tag,pullPolicy}` | `scraw-law-contracts:latest` | runner image |
| `images.flkLawCrawl.{repository,tag,pullPolicy}` | `fd-law-data:latest` | flk crawler image |
| `flkLawCrawl.{schedule,suspend,concurrencyPolicy,activeDeadlineSeconds}` | `30 2 * * *`, false, Forbid, 14400 | flk CronJob scheduling |
| `flkLawCrawl.secretName` | `flk-law-crawl-credentials` | Secret with `rustfs-access-key` / `rustfs-secret-key` |
| `flkLawCrawl.rustfs.endpoint`, `.region` | `https://file.finddatatech.cloud`, `us-east-1` | RustFS public endpoint |
| `flkLawCrawl.{lawsBucket,rateMs,pageSize,lookbackDays}` | `laws`, 1100, 100, 7 | crawler behaviour |
| `scrapyd.replicas` | `1` | scrapyd Deployment replicas |
| `scrapyd.redisUrl` | `""` | Override redis (empty → in-chart redis) |
| `lawContracts.schedule` | `0 2 * * *` | CronJob schedule |
| `lawContracts.suspend` | `false` | Suspend the CronJob (manual-only) |
| `lawContracts.{sqlitePath,jsonlPath}` | `data/scraw.db`, `output/items.jl` | Runner output paths |
| `lawContracts.persistence.*` | enabled, RWO 5Gi | PVC for runner outputs |
| `redis.auth.enabled` | `false` | Disabled by default (chart URL has no password). Enable if you add a password to the URL. |
| `redis.enabled` / `postgresql.enabled` | `true` | Disable to use external hosts |

## Notes

- The application images (`scraw-ops-scrapyd`, `scraw-law-contracts`) must be built
  and pushed to whatever registry you configure. The chart deploys them; it does
  not build or ship them.
- The runner writes **SQLite + JSON Lines** to the PVC (`data/scraw.db`,
  `output/items.jl`). Postgresql is included as stack infrastructure for
  scrapyd-deployed spiders, not as the law-contracts output sink.
- `charts/` and `Chart.lock` are gitignored — run `helm dependency build` after clone.