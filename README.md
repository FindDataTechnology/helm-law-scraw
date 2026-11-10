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

## legal-sources-report 的判据口径

`legalSources.sources` / `legalSources.loaders` 建的是 crawl/load 一对 CronJob；
`legalSources.report` 是那条**日体检**（06:00 Asia/Shanghai）。它跑
`bin/legal-sources-report.mjs`，然后**把自己也记进 `crawl_runs`** —— 记录器就写在
`legalSources.report.command` / `.args` 里（`sh -c` + 一段 `node -e`）。

> 为什么要写在 chart 里：这份记录器的真身过去只存在于
> `fd-law-data/k8s/legal-source-crawl-cronjobs.yaml`（该文件已 SUPERSEDED），
> chart 里只是裸跑脚本。于是**谁 apply chart 谁就把 crawl_runs 里那一行记录弄丢**，
> 而且没有任何门会红。2026-11-10 收编进 chart，并加了
> `make verify-report` 这条断言。

### 两个判据，别混

| 字段 | 含义 | 判据 |
|---|---|---|
| `stale_sources` | **断流**：这条源在绿线（`STALE_AFTER_HOURS = 48`）内没有任何成功证据 | `freshness_at = max(最近完整 manifest, state.json, 库里最新一行)` 晚于 48h 前 |
| `load_stalled_sources` | **装载停滞**：crawl 真有产出、库却不跟着长 | 某次 **`emitted > 0`** 的跑批发生在库中最新一行之后，且间隔 > 48h |

两者都让日报告 `exit 2`（`shouldFail` 认两边的并集）：都是「数据没进库」，
区别只在断在 crawl 还是断在 load。

### `emitted > 0` 是刻意的锚点

装载停滞**只认有产出的跑批**，不敢用 `state_updated_at` 当锚点：

- 零新增的干净跑批**每天都会推进** `state.json` —— 这正是「零新增不是断流」那条设计；
- 拿它当锚点，会把所有安静的上游全报成装载停滞。

实测样本（2026-11-10）：`mfa-treaty` 的 crawl/load 每天 `success`、`rows=0`、
`state` 每天推进，而库里 35 天没有新行 —— 那是**上游确实没有新条约**（条约不是天天签），
不是故障。安静的上游没有 `emitted > 0` 的跑批，`crawlAt` 为 null，自然不报。

### 向后兼容

镜像尚未更新时报告里没有 `load_stalled_sources`，记录器 `join` 得到空串 ——
`status` 与 `error_head` 与旧记录器**逐字节一致**。也就是说收编本身不改变任何既有
观测口径，出片后才开始报装载停滞。回归用例：
`fd-law-data/test/legal-report-recorder.test.mjs`（新旧记录器同输入逐字段对比）。

### 自检

```bash
make verify-report     # helm template 断言（见下）
make lint
```

`make verify-report` 渲染 chart、只取 `legal-sources-report` 那一段，断言：

1. `command` 渲染为块序列 `sh -c`（多行记录器需要）；
2. args 里读 `stale_sources` 与 `load_stalled_sources`；
3. **`!loadStalled` 出现在 status 表达式里、`load_stalled=` 出现在 error_head 里**
   —— 只读字段不够：把 `&& !loadStalled` 删掉，字段还在但判据已死；
4. args 里确有 `INSERT INTO crawl_runs` 与 `FD_CRAWL_DB_URL`。

### 负例（这个门的"不会假绿"证据）

一个只会变绿的门没有价值。下面两条是**必须变红**的路径，改动这个记录器后请各跑一次：

| 负例 | 怎么造 | 期望 |
|---|---|---|
| **helm 缺失** | 见下方一行命令（造一个只含 shell 工具的 PATH） | 输出 `✗ helm template 失败：helm: command not found`，**退出码 1** |
| **只读字段、不参与判定** | 把 values 里的 `!stale && !loadStalled` 改回 `!stale` | **只红一条**「装载停滞参与 status 判定」，退出码 1（精准指认，不连坐） |

第一条的造法（可照抄）：

```bash
d=$(mktemp -d)
for t in bash sh awk grep sed dirname cat printf; do ln -s "$(command -v $t)" "$d/$t"; done
PATH=$d ./scripts/assert-report-recorder.sh; echo "退出码=$?"
```

两条都已实测：前者证明 CI runner 没装 helm 时不会因"什么都没渲染"而放行；
后者证明"字段被读到"和"字段起作用"是两个门，缺一个就会重演 2026-11-10 那次
「记录器丢了、谁都没红」。

还原后再跑 `make verify-report` 应全绿。

### 这个门跑在哪（为什么没有 workflow）

**本仓保持私有**，而该 org 的私有 CI 额度已耗尽（2006/2000，私有 Actions 不调度）；
公开仓才免费用 Actions，但本仓内容不适合公开：`values.yaml` / `APPLY-NOTES.md` 里有
tailnet 内网地址（`100.64.0.5` 的 RustFS/PG、退役前的 `100.64.0.8:30880`）、
法务源清单与身份命名（`acct001`、`rmfyalk` / `wenshu` / `ccdi` / `mfa-treaty` /
`party-regulation` / `gov-rules`）—— 那是这条产品线的运营地图，不是模板。

所以门放在**本地**，opt-in 安装：

```bash
./scripts/install-git-hooks.sh     # 只改本克隆的 core.hooksPath=.githooks
```

装好后：提交时暂存区若含 `values*.yaml` / `templates/` / `scripts/` / `Makefile`，
自动跑 `make verify-report`，不通过就拒绝提交；只改 README 之类不触发。
helm 缺失时**拒绝而不是跳过**（不假绿）。
卸载：`git config --local --unset core.hooksPath`。

**前置**：`charts/` 是 gitignored 的打包依赖（`charts/redis-27.0.15.tgz` 等），
新克隆要先 `helm dependency build .`（需要能访问
`oci://registry-1.docker.io/bitnamicharts`）。缺依赖时门会直接点名这件事并退出 1，
不把网络问题伪装成内容问题。

## Notes

- The application images (`scraw-ops-scrapyd`, `scraw-law-contracts`) must be built
  and pushed to whatever registry you configure. The chart deploys them; it does
  not build or ship them.
- The runner writes **SQLite + JSON Lines** to the PVC (`data/scraw.db`,
  `output/items.jl`). Postgresql is included as stack infrastructure for
  scrapyd-deployed spiders, not as the law-contracts output sink.
- `charts/` and `Chart.lock` are gitignored — run `helm dependency build` after clone.