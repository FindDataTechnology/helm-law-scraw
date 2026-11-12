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
#    ⚠ 2026-11-12：还要加 -f values-private.yaml —— 内网端点/PG 主机/账号标识
#    在带外那份里，缺它渲染即报错（见「带外私有值」一节）。
helm install law-craw charts/helm-law-scraw/ \
  --namespace scraw --create-namespace \
  -f values-private.yaml \
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
  -f values-private.yaml \
  --set imageCredentials.host=myregistry.example.com \
  --set imageCredentials.username=myuser \
  --set imageCredentials.password=mypassword

# Option B: pre-create the secret and reference it
kubectl -n scraw create secret docker-registry my-pull-secret \
  --docker-server=myregistry.example.com \
  --docker-username=myuser \
  --docker-password=mypassword
helm install law-craw charts/helm-law-scraw/ \
  -f values-private.yaml \
  --set imageCredentials.existingSecret=my-pull-secret
```

## 带外私有值（`values-private.yaml`）

内网端点、PG 主机、法务身份标识**不在本仓**。`values.yaml` 里这些位置一律留空，
真正的值放在带外 `values-private.yaml`（已 gitignore，同族备份名一并挡掉）。
模板用 `required` 守卫，所以缺了它渲染会**当场报错并点名缺哪个键**：

```
Error: execution error at (helm-law-scraw/templates/legal-source-load-report.yaml:41:20):
缺少 legalSources.rustfs.endpoint：内网端点写在带外 values-private.yaml（已 gitignore），或用 --set 提供
```

这是**故意**的：静默渲染出一个空地址的 Job，比渲染失败更难查——它会在凌晨三点
以「连不上对象存储」的形态出现，而根因在两小时前的渲染参数里。

标准渲染（两个 `-f` 都要，顺序无关——两者没有重叠键）：

```bash
helm template law-craw . --namespace scraw -f values-server1.yaml -f values-private.yaml
# 或
make render
```

需要搬进那份文件的键（`values.yaml` 里同名位置是 `""`）：

| 键 | 说明 |
|---|---|
| `private.accountId` | 法务身份标识；代入图表内的 `__ACCOUNT_ID__` 令牌 |
| `flkLawCrawl.rustfs.endpoint` | 对象存储端点 |
| `legalSources.rustfs.endpoint` / `.postgres.host` | crawler/loader/report 的对象存储与 PG |
| `authBroker.rustfs.endpoint` / `.postgres.host` | 身份代理同上 |
| `wenshuCrawl.rustfs.endpoint` | wenshu 线（默认 `enabled: false`，不渲染） |
| `images.wenshuCrawl.repository` | 内网镜像项目名（含下划线，与 ccr 项目名不同） |

**`__ACCOUNT_ID__` 为什么是个令牌**：账号标识同时出现在三处形态里——pod label 值、
crawler 的 `--account-id` 参数、身份 Secret 名 `legal-identity-rmfyalk-<id>`。三者必须
同源，所以由 `_helpers.tpl` 的 `helm-law-scraw.subst` 在**渲染时**代入（先 `toYaml`
再替换再缩进，因此带私有文件渲染出的结果与写死时逐字一致）。

卫生门（回归防线）：

```bash
make verify-hygiene     # = scripts/assert-no-internal-endpoints.sh
```

它按三个特征判：tailnet 网段、法务账号标识、内网镜像项目名（含下划线的那一个）。
模式串只写在脚本里（一处真源），**不要**在文档里复制——复制过的判据迟早只改一处。
它已接进 `make verify-report`，也就接进了 pre-commit 门：谁把内网地址写回来，提交即红。
CI 里没有 `values-private.yaml`，因此 `make verify-report` / `make lint` 用**占位值**渲染
（门验的是记录器形态，与真实地址无关）——**不是**跳过渲染，跳过就是假绿。

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

### 这个门跑在哪（自建 runner 的 GitHub Actions + 本地 pre-commit）

**本仓保持私有**，而该 org 的私有 CI 额度已耗尽（2006/2000，私有 Actions 不调度）；
公开仓才免费用 Actions，但本仓内容不适合公开：`values.yaml` / `APPLY-NOTES.md` 里有
内网端点（tailnet 内的对象存储与 PG、退役前的 Harbor）、法务源清单与身份命名
（账号标识、`rmfyalk` / `wenshu` / `ccdi` / `mfa-treaty` /
`party-regulation` / `gov-rules` 等来源 slug）—— 那是这条产品线的运营地图，不是模板。
具体地址与标识不写入文档，真源是集群 Secret 与带外的 `values-private.yaml`。

**结论：门走 GitHub Actions，但只跑自建 runner** —— 自建 runner 不消耗托管分钟，
不受私有仓额度影响。`.github/workflows/chart-verify.yml` 已就位，
`runs-on: [self-hosted, linux]`。

⚠ **runner 尚未注册前，该 workflow 会排队而不是跑**。排队期间真正的门是本地
pre-commit。不要把「一直排队」当成绿灯。

runner 就绪条件见 **[`docs/runner-setup.md`](docs/runner-setup.md)**（前置清单、注册命令、
三条验收、安全边界与回滚点）。要点：
1. 一台**常驻** Linux 主机，出网 `github.com:443`（runner 主动外连，不需要入站端口）；
2. 主机上有 `helm` / `git` / `make` / `bash`；标签必须显式给 `self-hosted,linux`；
3. 子依赖已随仓入库（`charts/*.tgz`），**不再需要** Docker Hub 访问。

本地 opt-in 安装（runner 未就绪期间用它兜住）：

```bash
./scripts/install-git-hooks.sh     # 只改本克隆的 core.hooksPath=.githooks
```

装好后：提交时暂存区若含 `values*.yaml` / `templates/` / `scripts/` / `Makefile`，
自动跑 `make verify-report`，不通过就拒绝提交；只改 README 之类不触发。
helm 缺失时**拒绝而不是跳过**（不假绿）。
卸载：`git config --local --unset core.hooksPath`。

### 子依赖为什么入库

`charts/redis-27.0.15.tgz`（104K）与 `charts/postgresql-18.8.0.tgz`（92K）**随仓提交**，
共约 196K。三个理由，缺一条都足以让它入库：

1. 私有仓 Actions 额度耗尽，CI 不能依赖"跑一次 `helm dependency build`"的余量；
2. 内网拉不到 `oci://registry-1.docker.io/bitnamicharts`（实测 `i/o timeout`）；
3. 新克隆没有 `charts/` 就渲染不了 chart —— 任何人第一次跑门都撞红，最后都会
   `--no-verify` 绕过。

**代价**：二进制进 git。`charts/*` 仍然忽略，只反向放行 `*.tgz`（规则顺序在
`.gitignore` 里写了原因：git 以最后匹配为准）。

**漂移防线**：`helm` 只按**文件名里的版本**加载子依赖，**不会**拿 `Chart.yaml` 的
`dependencies.version` 做比对 —— 所以 Chart.yaml 升到 28.x 而 charts/ 还是
27.0.15.tgz 时，`helm template` 照样成功，线上悄悄跑旧依赖。为此加了：

```bash
make verify-deps     # 逐对校验 charts/<name>-<version>.tgz，并揪出未声明的残留
```

它被 `make verify-report` 前置调用（`verify-report: verify-deps`），所以 chart 门的
第一道就是依赖一致性。缺依赖/版本漂移都会点名到具体文件与修法，退出码 1。

## Notes

- The application images (`scraw-ops-scrapyd`, `scraw-law-contracts`) must be built
  and pushed to whatever registry you configure. The chart deploys them; it does
  not build or ship them.
- The runner writes **SQLite + JSON Lines** to the PVC (`data/scraw.db`,
  `output/items.jl`). Postgresql is included as stack infrastructure for
  scrapyd-deployed spiders, not as the law-contracts output sink.
- `charts/` and `Chart.lock` are gitignored — run `helm dependency build` after clone.
## 解冻后执行清单

> 状态：可见性**已裁决为 PRIVATE**（2026-11-10），不再作为可选项。
> 下列动作按顺序执行，每步都给了验证与回滚。

### 0. 动手前先备份（`/tmp` 会随重启消失，别依赖旧备份）

```bash
D=$(date +%Y%m%d-%H%M%S)
mkdir -p ~/law-rollback/$D
for cj in legal-sources-report ccdi-supervisory-load gov-rules-load mfa-treaty-load party-regulation-load rmfyalk-case-load; do
  kubectl -n scraw --context xinru get cronjob "$cj" -o yaml > ~/law-rollback/$D/cj-$cj.yaml
done
kubectl -n scraw --context xinru get secret legal-identity-rmfyalk-<账号标识> -o yaml > ~/law-rollback/$D/secret-identity.yaml
echo "备份目录: ~/law-rollback/$D"
```

> `<账号标识>` 的真实值不进 git，取自带外 `values-private.yaml` 的
> `private.accountId`；不知道是哪个时用
> `kubectl -n scraw --context xinru get secret | grep legal-identity-rmfyalk-` 直接列出来。

### 1. 裁决 A：保持私有（当前默认）

**不需要任何仓库/流水线动作。** 只做第 3 步（出片），因为两笔代码修复要新镜像才生效。

验证与回滚：无。

### 2. 仓库可见性：已裁决为 PRIVATE（不再作为可选项）

2026-11-10 裁决：本仓**保持私有**，理由见上节（内容含 tailnet 内网地址与法务源清单）。
因此**不存在"公开前必须清零"这条路径**；原先的"公开 + 接 CI"分支已删除。
卫生债（26 处内网地址/身份命名）按普通技术债排期，见
`openspec/changes/chart-gate-and-repo-hygiene/tasks.md` 第 1 节。

### 3. 出片（与裁决无关，两笔代码修复等这步生效）

已推送但**尚未进镜像**：`fd-law-data` 的 `213eb3e`（load_stalled 判据）、`c4c670f`（锚点改
`emitted > 0`）、`38ccd50`（记录器回归）；`fd-law-data` 的 auth-broker 状态机修复（`8c65527`，
`cooldown` 出口 + `/failure` 默认 `login_required`）。

1. 出片前判路：`fd-build-channel`（**公开仓线首选、免费无限**；私有池 5 个，余额最多
   `testaction003/build-pool`）。
2. 出片后按顺序换 tag：先 `legalSources.tag`（报告/爬取/装载同一 tag），再 `authBroker.tag`。
   当前分别是 `sha-b63d0d1` 与 `sha-b726e1f`。
3. 应用：`helm template law-craw . --namespace scraw -f values-server1.yaml -f values-private.yaml | kubectl apply -n scraw -f -`
   （只 apply，别删对象；先跑 `make verify-report`。漏掉 `-f values-private.yaml` 会渲染报错，
   不会静默应用空端点 —— 见「带外私有值」一节）。
4. 验证：
   ```bash
   kubectl -n scraw --context xinru rollout status deploy/legal-auth-broker
   # 报告里应开始出现 load_stalled 判据（无停滞时该字段为空，行为与旧版一致）
   DSN=$(kubectl -n scraw --context xinru get secret federation-db -o jsonpath='{.data.url}' | base64 -d)
   psql "$DSN" -c "select id,status,left(coalesce(error_head,''),80) from crawl_runs where source='legal-sources-report' order by id desc limit 3;"
   ```
5. **回滚**：把 `values.yaml` 的两个 tag 改回 `sha-b63d0d1` / `sha-b726e1f`，
   重新 `helm template … | kubectl apply`，再 `kubectl -n scraw --context xinru rollout undo deploy/legal-auth-broker`。
   数据侧不回滚（新镜像只会多报，不会改写既有行）。

### 4. 与该裁决无关、但仍挂着的人工项

- **rmfyalk 重登**：会话停在 2026-09-24，入口在面板 `/panel/partials/auth` 那一行的登录操作。
  重登后按 spec 走探活 + 小批量才会升 `active`；在那之前 `legal-sources-report` 每天 `exit=2`，
  原因同一个，不必逐天看。
- 五个 load CronJob 目前已是 `suspend: false`（按 chart 声明归位）。若需回退：
  ```bash
  for cj in ccdi-supervisory-load gov-rules-load mfa-treaty-load party-regulation-load rmfyalk-case-load; do
    kubectl -n scraw --context xinru patch cronjob "$cj" --type merge -p '{"spec":{"suspend":true}}'
  done
  ```
