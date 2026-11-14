# APPLY-NOTES — helm-law-scraw on xinru (converged 2026-10-06)

This chart is converged to the xinru cluster (`xinru-master`, 134.175.46.69,
namespace `scraw`) live inventory. **Standard apply command (when a wave is
approved):**

```bash
# render exactly what the cluster should look like (object names are
# release-name independent — safe with any release name)
# ⚠ 2026-11-12 起必须带 -f values-private.yaml：内网端点 / PG 主机 / 账号标识都在
# 那份带外文件里（已 gitignore）。缺它 → 渲染当场报错并点名缺哪个键，这是**故意**的。
helm template law-craw /Users/chengsishi/finddata/helm-law-scraw --namespace scraw \
  -f /Users/chengsishi/finddata/helm-law-scraw/values-private.yaml

# lint
cd /Users/chengsishi/finddata/helm-law-scraw && make lint   # 自动带上私有值（缺失时用占位）
```

## ⚠️ Namespace rule (2026-10-06 wave-0 lesson)

`helm template` output carries **NO namespace** (active templates render bare
objects). Applying the render without a namespace flag creates duplicate
objects in `default` (this happened on wave-0 and was cleaned via
`kubectl delete -l app.kubernetes.io/part-of=finddata -n default`).
ALWAYS apply with an explicit namespace:

```bash
helm template law-craw /Users/chengsishi/finddata/helm-law-scraw --namespace scraw \
  -f /Users/chengsishi/finddata/helm-law-scraw/values-private.yaml \
  | sudo k3s kubectl apply -n scraw -f -       # --dry-run=server first on any new shape
```

Rendered object set (15 objects) == chart-owned live inventory:

| kind      | name |
|-----------|------|
| CronJob   | flk-law-crawl (IN-SERVICE, suspend=false) |
| CronJob   | rmfyalk-case-crawl, mfa-treaty-crawl, gov-rules-crawl, party-regulation-crawl, ccdi-supervisory-crawl |
| CronJob   | flk-law-backfill |
| CronJob   | rmfyalk-case-load, mfa-treaty-load, gov-rules-load, party-regulation-load, ccdi-supervisory-load |
| CronJob   | legal-sources-report |
| Deployment + Service | legal-auth-broker |

**Not charted on purpose** (live, external, must never be touched by an apply):
`federation-observer`, `guide-cases-crawl`, `gost-egress`, `proxy-control`, and the
rmfyalk identity-profile PVC (`legal-auth-rmfyalk-<账号标识>-profile`；账号标识见带外
`values-private.yaml`). The chart renders no object with any of these names —
re-verified 2026-11-14 against `make render` (17 objects).

**订正（2026-11-14）**：这份清单原先还写着 `flk-law-load` 与 `flk-law-embed`
「not charted / must never be touched by an apply」——**错的**。两者都有各自的模板与
values 段（`flkLaw`-侧与 `flkLawEmbed`），`make render` 明确渲染它们（各带
`suspend`）。按旧清单办事的人会以为「这两个对象不归 chart 管」，于是手工改线上、
或以为改 values 没用。判据：以 `make render` 的对象名为准，别信这段文字。

**Disabled by default** (nothing live on xinru, verified cluster-wide
2026-10-06): `scrapyd.enabled`, `lawContracts.enabled`, `wenshuCrawl.enabled`,
`redis.enabled`, `postgresql.enabled`. An apply with default values cannot
create them. Do not flip these on xinru.

## Naming rule

Live objects carry NO release prefix. All active templates therefore render
bare names (`rmfyalk-case-crawl`, `legal-auth-broker`, ...) instead of
`<fullname>-...`; `helm template` output is byte-identical for any release
name. `values.yaml nameOverride/fullnameOverride` are irrelevant now.

## 站点互斥（apply 前必跑 `make verify-sites`，`make lint` 已依赖它）

同一个 CronJob 不许在两个站点同时点亮。这条闸是 2026-11-14 用数据换来的：
`values-server1.yaml` 曾把四个爬虫 + 五个 loader + report + flkLawCrawl 写成
`suspend: false`，而 `values.yaml`（xinru-master，活宿主）上同样这几条**正在跑**。
两侧同时在跑的证据不在清单里，在 `crawl_runs`：2026-11-13 那一轮
mfa-treaty / gov-rules / party-regulation / ccdi 各写了两行、`image_tag` 不同
（master 自报 `sha-e584fc5`，server1 的 CronJob 跑 `sha-b63d0d1`）。
那种重复只在**两侧 pod 都真起来**时才留痕——11-12 之前 server1 侧一直
`Failed 0/1`（pod 没起来、不写行），所以这件事长期看不见。

两个必须记住的点：

1. **overlay 不写 = 继承 base 的 `suspend`**。「切换前全部 suspend」这句话如果
   只写在注释里，渲染产物上是假的：`flk-law-load` / `flk-law-embed` 在 base 里是
   `false`，两份 overlay 都没写它 ⇒ 它们其实一直是亮的。现在两份 overlay 都显式关掉了。
2. **切换宿主 = 同一次改动里两边一起翻**（新站点 `false` + 旧站点 `true`）。
   闸不猜哪边该活（那是人的裁决），只拒绝「两边都活」。

## 宿主切换：已裁定，未执行（2026-11-14 查明）

**裁定（2026-10-07，用户五机分布）**：法律线宿主 = **xinru-server1**，全家（CronJob +
dispatcher + observer + auth-broker）驻扎于此。记录在
`openspec/changes/archive/2026-10-12-legal-line-federation/`：proposal「法律线宿主=
xinru-server1」、tasks 3.3「站点 dispatcher 部署于 xinru-server1」已勾。

**实际（2026-11-14 实测）**：**xinru-master 仍在跑整条线**（16 个 CronJob、13 个
`suspend=false`、镜像 `sha-c33bf67`），server1 侧 17 个法律 CronJob **全部 suspend**
（镜像停在 `sha-b63d0d1`）。也就是说：**归档时没有人把 master 侧的 CronJob 关掉**，
那份 change 的任务表里也没有这一条——迁移名义上完成，负载原地未动。

所以现在的状态不是「该选哪边」，而是「裁定的目的地还没到，中转站还在供数」。
`make verify-sites` 保证的只是「此刻只有一个执行者」，它不替人做切换。

### 目标站点已预验（2026-11-14，三面实测）

切换前先证明「目的地能跑这条线」，免得切换当天才发现拉不到镜像或连不上库：

| 面 | 探针 | 结果 |
|---|---|---|
| 镜像 | `kubectl --context xinru-server1 -n scraw run pullprobe --rm -i --image=…:sha-c33bf67 -- node -e …` | 拉起并执行成功（server1 节点自带 ccr 认证，无需 pull secret） |
| PG | 同镜像 Pod，`FD_CRAWL_DB_URL ← secret federation-db/url`，跑一次 `select current_database()` | `fd_open_data` 通，`crawl_runs` 可读（party-regulation 48 行） |
| 对象存储 | `createS3({endpoint: <rustfs 内网端点，见 values-private.yaml>, …secret flk-law-crawl-credentials})` + `listObjects('laws', {prefix:'legal-sources/report/'})` | 通，列到 40 个报告对象 |

三面都过，且探针已删（不留对象）。所以配方第 2 步的「能不能跑」已经有答案，
真正剩下的未知只有**吞吐与资源**（server1 是较小的 VM，限额在 chart 里已有）。

**再加一条真爬实测（同日晚些，比三个探针更硬）**：把 chart 渲染出的
`party-regulation-crawl` 原样 apply 到 server1（**`suspend: true` 保持不变**，
所以没有动排期），再 `kubectl create job --from=cronjob/party-regulation-crawl
party-crawl-pilot` 手工跑一轮：

- Job `Complete 1/1`，17s（`04:49:51Z → 04:50:08Z`）；
- `crawl_runs` 新增一行 id 5882 `success`、**`image_tag = sha-c33bf67` 自带正确**
  （对照 11-13 那两行的 `b63d0d1` / `e584fc5`，正是徽谎与新片的差别）；
- 日志是结构化 JSON（含 `parts`/`failures`/`aborted`/`emitted`）⇒ 那条
  「log 形参没人注入＝生产日志一行都没有」的坑在新片上确实修好了，凌晨轮次的
  可观测性可以指望它。

**踩到的坑（写在这里免得再踩）**：`helm template` 的产物**不带 namespace**，
`kubectl apply -f` 会把这批对象建到 context 的 `default` 里——我第一次就建出了
`default/party-regulation-crawl`，读回 `-n scraw` 才发现镜像没变（那是另一份对象）。
配方里必须写 `apply -n scraw -f -`，误建后按精确名删掉（`kubectl -n default
delete cronjob party-regulation-crawl`），别去 grep 宽匹配。

### 切换前提：站点上「会跑的对象」引用的凭据必须齐备（`make verify-secrets`）

**「能连」不等于「能用同一份凭据」。** 2026-11-14 的连通性探针走的是 crawl 库
`fd_open_data` + `laws` 桶，全绿；可 load / report 走的是另一个库、另一份口令，
探针完全看不到。逐键 sha256 比下来（脚本只打 8 位哈希与长度，从不打印值）：

| secret / key | 两站点 | 判定 |
|---|---|---|
| `flk-law-pg-credentials` / `pg-password` | `3515c8f6` 两侧同值（2026-11-14 对齐） | 曾是 load/report 的硬阻塞；对齐后 server1 上 `create job --from=cronjob/rmfyalk-case-load` 实测 **Complete 1/1、62s**、日志回 `laws: 32355 / law_chunks: 362476 / unchanged: true` |
| `flk-embed-credentials` / `embed-api-key` | 只有 xinru 有 | **不是缺陷**：server1 侧 `flk-law-embed` 挂起、不在必需集里。谁要在 server1 点亮 embed，必需集立刻包含它、闸立刻红 |
| `legal-identity-<法务账号>`（全名见集群 Secret）/ `crawl_proxy_url`、`login_proxy_url` | 两侧不同（54B vs 49B，**proxy id 相同**） | 已裁决（R3，带解除条件）：同一身份的两个活着的站点本地出口，见下文 |
| `federation-db`/`url`、`flk-law-crawl-credentials` 两个 dashed 键、`legal-auth-broker` 三键 | 两侧同值 | crawl/load/report 都可搬 |

**判据在 2026-11-14 重写过一次，别按旧口径读它**：旧版要求「chart 引用的每个键在两站点
都同值」，于是 embed 被报成红——那是在要求一份**永远不会被读**的凭据。现在必需集按站点
求，取两路并集：**线上在跑的对象**（`suspend=false` 的 CronJob ＋ 副本 >0 的 Deployment）
∪ **该站点渲染里点亮的对象**。前者回答「现在会不会起不来」（11-13 那 10 轮 load 失败就是
它抓的：当时 server1 的 load 对象是活的，overlay 写没写都不算），后者回答「下次 apply 之后
会不会起不来」。R2 只在**两站点都必需**时才要求同值。

**proxy 那条为什么判成「已裁决」而不是对齐**：同一个 proxy id（两站点 id 值逐字节相同），
两个 URL 实测都活着、出口 IP 不同——xinru 出 `134.175.46.69`，server1 出
`111.230.147.208`（异地备份机）。所以不是「一份拷贝过期」，而是两个站点各自的本地方案。
按 `legal-line-federation` 的裁定（宿主 = server1）迁移完成后，另一站点 broker 应置 0 副本、
两侧收敛到留用站点的值——**这就是该条在脚本里的解除条件**。

**2026-11-14 处置**：`pg-password` 已按「先快照 server1 原值 → 用 master 的 data 整份
覆盖（secret 的 patch 会整体替换 data，不能只补一个键）→ 逐键哈希复核 → 真跑一轮 load
验证」四步对齐，server1 侧的 load 从「连着 10 轮 Password 认证失败」变成
`Complete 1/1`。

**为什么只比「被引用的键」而不是整份 secret**：两份 secret 的键集本就会因为 `envFrom` 与
显式 `secretKeyRef` 两种写法分叉（实测 server1 的 `flk-law-crawl-credentials` 是超集，
多了 `RUSTFS_*` 大写键）；比全量会把这种设计差异报成红。

### 切换进度（逐源翻，别一次全翻）

| 源 | 生效站点 | 依据 |
|---|---|---|
| `party-regulation-crawl` | **xinru-server1**（2026-11-14 试点） | master 侧 `suspend: true`、server1 侧 `false`；真爬已在 server1 实测（Job Complete 17s、`crawl_runs` 自报 `sha-c33bf67`、日志可见）。观察一个 03:40 轮次 |
| 其余 6 crawl + 5 load + embed + report + flkLawCrawl | **xinru-master**（唯一执行者） | 2026-11-14 实测两集群 `suspend` 全表：master 亮 13 个、server1 只亮 `party-regulation-crawl`（另有 `fd-industry-dispatcher` 与 `federation-observer` 两条站点级作业）|

**2026-11-14 之前，其中 4 个爬虫 + 若干 loader 在两侧同时是活的**——这也是
`crawl_runs` 里 11-10/11-11/11-13 三轮各出现同窗两行的原因（11-13 那轮
`ccdi`/`gov-rules`/`mfa-treaty`/`party` 四只在**同一秒**两侧各写一行）。
今天把 `values-server1.yaml` 应用到 server1 后，overlay 把 party 以外的条目一律
`suspend: true`，**双跑就此结束**；master 侧对象一直是 `values.yaml` 的收敛态
（那 13 个亮着的就是它）。这条不许靠清单声明就算数——次日用 `make verify-runs` 核。

回滚这一源＝两处翻回去并重推：`values.yaml` 的 `party-regulation-library.suspend`
改回 `false`、`values-server1.yaml` 的同项改回 `true`，然后
`kubectl --context xinru -n scraw patch cronjob party-regulation-crawl --type=merge
-p '{"spec":{"suspend":false}}'` 与 server1 侧对称 patch。**load 不动**：它读的是
同一个 `laws` 桶、写同一个库，与 crawl 在哪台机无关。

### 切换配方（一次改动，两边同时翻）

```bash
# 1) git 侧（同一个 commit 里两件事，缺一不可）
#    values-server1.yaml: 目标清单改成 suspend: false
#    values.yaml:         对应条目改成 suspend: true（master 关灯）
make verify-sites          # 必须绿：两个站点不能同时点亮
git commit && git push

# 2) 目标站点先应用（server1），核一次真跑
helm template law-craw . -n scraw -f values-server1.yaml -f values-private.yaml \
  | sudo k3s kubectl apply -n scraw -f -         # 在 server1 上执行
kubectl --context xinru-server1 -n scraw create job --from=cronjob/mfa-treaty-crawl \
  mfa-treaty-crawl-cutover && kubectl --context xinru-server1 -n scraw logs -f job/mfa-treaty-crawl-cutover
#   验收：镜像 tag 与 make render 一致、crawl_runs 新行 image_tag 正确、laws 有新对象

# 3) 再关旧站点（master），核它真的不再写
kubectl --context xinru -n scraw patch cronjob mfa-treaty-crawl --type=merge -p '{"spec":{"suspend":true}}'
#   验收：次日该源只有 server1 那一行（crawl_runs 里 source+minute 唯一）

# 回滚：把 1) 的两处翻回去并重推；两个站点都回到「只有 master 亮」
```

**第 2 步与第 3 步之间必然有一段两侧都亮**（目标已起、旧宿主未关）。那一段的代价是
同一源两行——所以顺序不能反：先起目标、核通，再关旧宿主，且要在同一小时内完成。
`verify-sites` 拦的是**提交**层面的两侧同亮；运行层面的这段窗口靠人守，事后用下面的
`make verify-runs` 核（它读数据，不读清单）。

## 单执行者：数据里只许一条 success（`make verify-runs ROWS=…`）

`verify-sites` 判**声明**（两份 values 谁写了 `suspend: false`），`verify-runs` 判
**行为**（库里到底几个执行者跑完了）。两者不能互替：清单两侧同亮能被拦，而「清单只有
一侧亮、另一侧的 CronJob 对象是旧的/手工 apply 的」拦不住；反过来，行为侧的证据只在
**两侧 pod 都真起来**时才留痕——2026-11-12 之前 server1 侧一律 `Failed 0/1`（pod 没起来、
不写行），所以双跑长期不可见，不是没发生。

```bash
# 行数据由一次性查询 Pod 产出（scripts/single-executor-runs.mjs 头注有完整配方）
kubectl --context xinru -n scraw logs runs | tail -1 > /tmp/rows.json
make verify-runs ROWS=/tmp/rows.json SINCE=2026-11-14T05:00:00Z   # EXIT 1 双跑 / 2 判不出
```

`--since` 是「只看切换之后」：历史双跑不该让闸常年红，但被过滤掉的行会打印计数
（今天 105 行全在切换前 ⇒ 报「判不出」，不是绿——**还没有一个轮次可判**）。

**2026-11-14 的真红证**（7 天真实数据，不是自测造数）：6 组同窗双成功，其中 11-13 那轮
三个源在**同一秒**两侧各写一行——

| 源 | 时刻（UTC） | 两侧 tag |
|---|---|---|
| `party-regulation-crawl` | 11-13T19:40:01 / +1s | `sha-e584fc5` / `sha-b63d0d1` |
| `ccdi-supervisory-crawl` | 11-13T19:50:01 / +1s | `sha-e584fc5` / `sha-b63d0d1` |
| `gov-rules-crawl` | 11-13T19:30:01 / +0s | `sha-e584fc5` / `sha-b63d0d1` |
| `mfa-treaty-crawl` | 11-13T19:20:01 / +0s | `sha-e584fc5` / `sha-b63d0d1` |
| `party-regulation-crawl` | 11-11T19:40:01 / +301s | `sha-30f5179` / `sha-b63d0d1` |
| `party-regulation-crawl` | 11-10T19:40:01 / +70s | `sha-b63d0d1` / `sha-30f5179` |

而 `crawl_runs` **没有站点列**（列集已实测：`id/source/kind/status/started_at/
finished_at/rows_written/error_head/commit_sha/image_tag/created_at/cancel_requested/
pending_run_id/identity_alias/metrics/outcome/error_class/parse_error`，`metrics` 为空）。
所以「哪一行是哪台机」只能靠 `image_tag` 反推——**两站点对齐到同一片之后连这也分不出来**，
主判据因此必须是「一个窗内只有一条 success」，不能依赖 tag。

## 联邦 pin 必须等于 chart 的镜像（`make verify-pins ROWS=…`）

`crawl_sources.runner_image`（`kind='federated'`）是 **chart 镜像的手抄副本**：
`dispatch.sync_sources` 整段跳过 federated 行，副本一旦抄下来就没有任何东西再对齐它。
dispatcher 造 Job 时直接拿这一列当镜像 —— 所以它漂了，症状是「异常触发跑起来的是
N 代前的代码」，而不是宕机。

已经在 2026-10-14 咬过一次（`sha-3ca3e8b` 被 ccr 逐出 ⇒ 批量 ImagePullBackOff，
维护成 alembic `0011_federated_runner_tag`）。**2026-11-14 实测又漂了**：7 行全钉
`sha-e9c1c11`，chart 与线上 CronJob 已是 `sha-c33bf67`——而且是手工改上去的
（0011 的锚点是 `sha-b63d0d1`，DB 里却是 e9c1c11，中间无任何提交记录）。

```bash
# 1) 行数据由一次性查询 Pod 产出（本机没有 psql，也不该把 DSN 摊在命令行）
#    同族用法见记忆「查询 Pod 模式」；脚本只要 [{source,img}]
kubectl --context xinru -n scraw logs runs | tail -1 > /tmp/rows.json
# 2) 比对
make verify-pins ROWS=/tmp/rows.json      # EXIT 1 = 分叉，2 = 判不出
```

三条刻意的边界：**R2 无主只报事实**（`guide-cases-crawl` / `wenshu-crawl` 不在这张
chart 里，没有所有者就没有可比的另一侧，判红会变成常年红的闸）；**判不出退 2**
（没有行数据、渲染失败、0 条 federated 行都不许读成「都对齐」）；**改法只写「新增
alembic revision」**，不写手工 UPDATE —— 上一次手工改没留出处，正是这次漂移的来源。

## Images

- `images.legalSources` — ccr.ccs.tencentyun.com/lawcraw-business/fd-law-data,
  tag `sha-d3e3e55`. Used by the 11 in-change objects (5 crawls + backfill +
  5 loads + report). NO imagePullSecrets on these pods (nodes hold ccr creds).
  `rmfyalk-case-crawl` overrides repository/tag to
  `lawcraw-business/legal-auth-broker:sha-4b79ec5` (same registry).
- `images.flkLawCrawl` — 退役前的 Harbor 镜像（`fd-law-data:sha-e78d96e`，仓库址与项目名
  见 `values-private.yaml` / 集群 Secret，不写进文档）+ `harbor-lawcraw-pull` pull secret。
  IN-SERVICE; converged to live, zero behavior change.
- `images.authBroker` — 同一退役 Harbor 的 `legal-auth-broker:sha-b726e1f`。
  Live Deployment runs exactly this (lease-api container, no pull secrets).

## Render-vs-live diff (2026-10-06, after convergence)

Compared with `python3 /tmp/chart_diff.py` (live snapshots: /tmp/wave-crawls.json,
/tmp/wave-load-report.yaml, /tmp/wave-authbroker.json; normalized for
API-server-defaulted probe/protocol fields):

- EQUAL (zero diff): `CronJob/flk-law-crawl`, `Deployment/legal-auth-broker`,
  `Service/legal-auth-broker`.
- The 11 in-change objects + flk-law-backfill differ from live ONLY in:
  1. image → ccr registry + pinned sha (the declared target state; live still
     runs harbor sha-e78d96e / sha-f9432d2 / sha-4b79ec5),
  2. imagePullSecrets `harbor-lawcraw-pull` dropped (ccr needs none),
  3. `legal-sources-report` gains PG_* env (PG_HOST = tailnet 内 PG 主机，**地址见集群
     Secret** `flk-law-pg-credentials`；PG_PORT 5432, PG_DATABASE law_db,
     PG_USER/PG_PASSWORD 同源) —
     required by the new report code; live report predates it.
  Nothing else differs: schedules, suspends (all true), deadlines, envs,
  commands, labels match live; mfa/ccdi crawl deadlines were fixed to live
  (28800); rmfyalk command carries `--account-id <账号标识，见 Secret
  legal-identity-rmfyalk-…> --auth-broker http://legal-auth-broker.scraw`
  plus its 4 auth envs from Secrets.

## Wave flip manual (suspend / image rolls)

All values live in `values.yaml` → `legalSources`. One key per flip, one wave
at a time; never flip more than one source's crawl+load pair unsuspended
without a validated dry run.

| Wave | Flip | Notes |
|------|------|-------|
| W1 crawl rollout | `legalSources.sources.<id>.suspend: true → false` for each approved source | image already at `images.legalSources` sha; bump `images.legalSources.tag` first if a newer sha is required |
| W1 load rollout | `legalSources.loaders.<id>.suspend: true → false` | loaders read the crawl output written by the same wave |
| report cutover | `legalSources.report.suspend: true → false` | ONLY after the new report code (PG reader) is in the image pinned at `images.legalSources.tag`; old image + PG env is harmless, but the report without PG code would not read law_db |
| flk chain | DO NOT TOUCH from this change | `flkLawCrawl.suspend` stays false; image stays sha-e78d96e; `flk-law-load`/`flk-law-embed` are not charted |

Per-source keys: `rmfyalk-case-library`, `mfa-treaty-library`,
`gov-rules-library`, `party-regulation-library`,
`ccdi-supervisory-regulations` under `sources`; `rmfyalk-case-load`,
`mfa-treaty-load`, `gov-rules-load`, `party-regulation-load`,
`ccdi-supervisory-load` under `loaders`.

Example — wave-2 pins a new crawler sha and enables gov-rules:

```bash
helm template law-craw . --namespace scraw -f values-private.yaml \
  --set-string images.legalSources.tag=sha-<new> \
  --set legalSources.sources.gov-rules-library.suspend=false
```

## Blast-radius rules

- Any chart-owned object must render == live or == the declared target state.
  Re-run a render-vs-live diff before every apply.
- The in-service flk chain (`flk-law-crawl` suspend=false) must never inherit
  `images.legalSources`; its image is pinned separately and verified equal to
  live.
- Applying the chart does NOT create: scrapyd/law-contracts/wenshu/redis/
  postgresql objects (disabled), nor any external object (names verified).


## 法律线宿主：xinru（2026-11-14 更正；此前写的是 xinru-server1）

**现状**：法务线唯一在跑的宿主是 **`xinru` 集群 `scraw` ns**（14 个点亮作业，镜像
`sha-492925f`）。`xinru-server1` 上的同名作业已全部 `suspend=true`，只保留
`fd-industry-dispatcher`（该集群独有）与 `federation-observer`（按**本集群** scraw 的
Job 回填 `crawl_runs`，`FED_NAMESPACE=scraw`，两边看的是不同 Job 集合，不是重复）。

**为什么要更正**：本节原来写「宿主 xinru-server1（2026-10-07 迁移后）」，但 2026-10-06
之后所有出片与修复都落在 xinru，server1 那套一路停在 `sha-b63d0d1`——于是**两边同时
按 CST 窗口点火**：同一 source 同一分钟在 `crawl_runs` 留两行、爬取请求翻倍，
而 server1 那侧还缺 2026-11-13 修的 `lib/http.js` 半开响应体超时（就是那批「进程睡死
8 小时、零日志零重试」的成因）。2026-11-14 实测两边 lastScheduleTime 全部对得上当日窗口，
确认是双份而非「一边备份」。

**回滚**（若决定改回 server1）：先在 server1 把 11 个作业 `suspend` 改回 false——
`ccdi-supervisory-{crawl,load}`、`flk-law-crawl`、`gov-rules-{crawl,load}`、
`legal-sources-report`、`mfa-treaty-{crawl,load}`、`party-regulation-{crawl,load}`、
`rmfyalk-case-load`——再去 xinru 对应挂起，**任何时刻只留一侧点亮**。

**渲染**：`helm template law-craw . --namespace scraw -f values-server1.yaml -f values-private.yaml`
（或 `make render`；**两个 -f 都要** —— 内网端点与账号标识在带外那份里）
- **runner_image 同步义务**：升级 `images.legalSources.tag` 时必须同步 `crawl_sources.runner_image`（dispatcher 触发的 Job 用登记值，不是 chart 值）——drill 4.2 曾因此跑旧镜像。

### 两个不在本 chart 里的 scraw 作业（各有其真源，别重复发布）

- **`flk-law-embed`**（05:30，读 `laws-export` 分片写 Qdrant）——**2026-11-14 已收进本
  chart**（`templates/flk-law-embed-cronjob.yaml`，值在 `flkLawEmbed`）。此前它只有
  `fd-law-data/k8s/flk-embed-cronjob.yaml` 那份手工清单 ⇒ chart 重建不出来、换集群
  静默消失，症状是「检索里没有新法条」而没有任何告警。
- **`federation-observer`**（*/15，按**本集群** scraw 的 Job 历史回填 `crawl_runs`，
  `FED_NAMESPACE=scraw`）——真源在 **`fd-industry-data/k8s/federation-observer.yaml`**
  （另有 `k8s/release.yaml` 引用），**不属于本 chart**；搬进这里会变成两份真源。
  两个集群各跑一个，各自看自己的 Job 集合，不是重复。

### 2026-11-14 收敛的 chart↔线上漂移

- `legalSources.nodeOptions: "--max-old-space-size=384"` → 新增 `legalNodeEnv` helper，
  供给 12 个 crawl/load/report。原来只在「仅作参考」的 `k8s/` 清单里，线上靠手工带；
  chart 缺它，换集群就丢回节点级 OOM（3.7GB 机器，V8 堆过 ~800MB 即被 OOM-kill）。
- `gov-rules-library` / `party-regulation-library` 的 `activeDeadlineSeconds`
  14400 → **28800**（对齐线上）。09-24 `96b6892` 已把四个 catalog 爬虫的墙抬到 8h
  （CCDI 撞过 4h 墙），但那笔只改了清单、没回写 chart——整份 apply 会把墙砍回 4h。
- 仍存的**惰性**差异：chart 多一个 `FD_RUNNER_IMAGE_TAG`（被镜像自报的
  `/app/IMAGE_TAG` 压过，无行为影响）；`legal-sources-report` 上 chart 多
  `FD_SCHEMA_MANAGED`（线上没它也已稳定跑出 `rows=47309`，加不加都只是「跳过 DDL」）、
  线上多带外加的 `FD_RUN_STARTED`（apply 不会删）。这三处都**不动线上**——
  为对齐而改一个正在正常出数的作业，风险大于收益。

### 2026-11-14 server1 侧整机收敛（备站从「三代前」追到当前片）

把 `values-server1.yaml` 应用到 server1 之前，那边的法律线是**手工维护的陈旧副本**：
15 个 CronJob 全钉 `fd-law-data:sha-b63d0d1`（chart 已是 `sha-c33bf67`），
`legal-auth-broker` 停在 `legal-auth-broker:sha-b726e1f`，另有两个 chart 里根本没有的
`guide-cases-crawl` / `guide-cases-load`（10-06 建、一直挂起、零 Job 历史、`guide-cases-*`
是 chart 不渲染的无主源，留着不动）。

处置：`make render | kubectl --context xinru-server1 apply -n scraw -f -`（渲染产物
**不带 namespace**，漏 `-n scraw` 会建出 `default/…`）。复核方式不是看 apply 的
`configured` 字样，而是**逐对象比 render 与 live 的镜像和 suspend**：

```
-> 不一致 0 处          # 17 个对象（1 Service + 1 Deployment + 15 CronJob）
broker rollout: successfully rolled out; 1/1 legal-auth-broker:sha-c33bf67
```

apply 前先确认 broker 是空闲的（日志只有 `GET /health`），否则这次滚版会打断登录。
两个 `guide-cases-*` 不在 chart 里，apply 不会碰它们（没有 prune）——它们是
`verify-pins` 里的「R2 无主」那一档，别顺手删，也别当成缺项。

## 出片记录 2026-11-11：统一到 `sha-30f5179`

出片通道：公开镜像仓 `scs001/fd-law-data`（免费线），run `42885942197` 全绿
（test 19s / fd-law-data 43s / wenshu 1m23s / auth-broker 1m0s），三镜像各铸
`sha-30f5179`。真源 `FindDataTechnology/fd-law-data` @ `1ace71a`。

带上产的两笔修复：
- `lib/legal-sources/report.js` — `load_stalled_sources`（锚点只认 `emitted>0` 的跑批，
  不用 `state_updated_at`；否则零新增的干净跑批会让安静上游集体误报）
- `lib/auth-broker/{identity,service}.js` — `cooldown` 有界出口 + `/failure` 默认 `login_required`

**拉取不是即时的**：构建推 hkccr，集群拉 ccr，靠 `tcr-relay` 首见携带。
首次直接拉 → `ImagePullBackOff / code = NotFound`；等 relay 轮次（≤5min）后两 tag 均
`phase=Succeeded`。**上产前务必先验可拉**（`kubectl run` 一个短命 pod 即可）。

Chart 变更（`5954a54` + `fdba628`）：
- `images.legalSources.tag` / `images.authBroker.tag` → `sha-30f5179`（4 处；`lawContracts` 未动）
- `legal-sources-report`：`backoffLimit: 0` + `restartPolicy: Never`
  **只改 restartPolicy 不够** —— Job 层仍按默认 `backoffLimit=6` 重试 7 次，
  实测一个日任务写出 7 条重复失败行。改动后实测：新增恰好 1 行、只有 1 个 pod。

生产验证：
- `deploy/legal-auth-broker` 滚动成功，`ready=1`
- 报告 JSON 已含 `last_crawl_at` / `load_stalled` / `load_stalled_sources`；
  5 源全部 `false`、`load_stalled_sources=[]`（mfa 35d、party 33d 无新行但 crawl 每日
  `emitted=0`，属安静上游 —— 判据按设计不报，这正是 `emitted>0` 锚点要的行为）

回滚点：`~/law-rollback/20261111-033446/`（6 个 CronJob + auth-broker Deployment）、
`/tmp/values-before-bump.yaml`；tag 回退到 `sha-b63d0d1` / `sha-b726e1f` 后重新 apply。

### runner_image 已同步（2026-11-11）

`crawl_sources.runner_image` 里 7 个源此前仍钉 `sha-b63d0d1`（dispatcher 触发的
Job 用登记值、不用 chart 值，所以只改 chart 不够 —— drill 4.2 就栽在这）：

```
ccdi-supervisory-crawl, flk-law-crawl, gov-rules-crawl, guide-cases-crawl,
mfa-treaty-crawl, party-regulation-crawl, rmfyalk-case-crawl
→ ccr.ccs.tencentyun.com/lawcraw-business/fd-law-data:sha-30f5179
```

回滚点：`~/law-rollback/runner-image-20261111-044356.sql`（逐源还原为 `sha-b63d0d1`）。
复核：`select source, split_part(runner_image,':',2) from crawl_sources where runner_image is not null;`
应全部为当前 tag。

### 生产验证：cooldown 出口（2026-11-11 04:48）

这是本轮最需要实证的一条 —— 它曾让 rmfyalk 静默停摆六周。做法是可逆的实机探测：

1. 把身份置为 `cooldown` 且 `updated_at = now()-31min`（模拟冷却已过）；
2. `POST /lease/acquire` → **HTTP 200，identity.status = active**，并发出 lease；
3. `POST /lease/release`（`failure:false`）释放；
4. 复原为 `login_required`（会话其实早已过期，`active` 是探测产物）。

事件表留下完整痕迹：
```
04:48:16  identity_updated/ok   cooldown expired after 30m   ← 出口触发
04:48:16  lease_acquired/ok
04:48:34  lease_released/probe_ok
```

**副作用与复原**：第 3 步把 `last_success_at` 改写成了 2026-11-11（`!failure` 分支）。
已复原为 `2026-09-24 16:35+00`（原始秒不可考，取 `:00`），并在事件表补一条
`identity_updated` 说明这次 lease 是探测、非真实抓取 —— **不做无痕修改**。

顺带给 rmfyalk 重登留个判据：重登成功后该行应从 `login_required` 变 `active`，
且 `last_success_at` 前移到当天。
