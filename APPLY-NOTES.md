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

### 搬走一个源之后，还要把它从「合法暂停」名单里摘出来（2026-11-14）

日报的 `LEGAL_PAUSED_SOURCES` 由模板按**本站点**的 `suspend` 推导
（`helm-law-scraw.legalPausedSources`）。于是源一旦搬到别站点、本站点写成
`suspend: true`，日报就会把它列进暂停名单；而报告侧是
`paused = pausedSet.has(source) && stale`（`fd-law-data` `lib/legal-sources/report.js`：
「证据优先：清单说暂停、但绿线内确有成功运行证据时，按正常判鲜」）。
两者叠起来的后果只有一个：**那个源真的谁也不跑之后，日报说它「合法暂停」而不是
「断流」**——而这恰恰是切换试点最该看见的失败形态。

所以切换要连这一处一起改：把源名加进 `legalSources.activeElsewhere`（`values.yaml`，
写的是**报告的适配器源名**，不是 CronJob 名）：

```yaml
legalSources:
  activeElsewhere:
    - party-regulation-library
```

于是 base 渲染出来的暂停名单回到 `rmfyalk-case-library`（与线上现值逐字相同），
而报告仍会正常判它的鲜。`make verify-sites` 的 R4 守这条白名单：**列了却没有任何
站点 overlay 让它 `suspend: false`** 即命中——僵尸例外的作用方向是「让红灯不亮」，
所以它计命中，而不是只报事实。两种读不出也退 2：写成 flow 序列 `[a, b]`、
或声明了却没有任何条目（零覆盖不许读成「没有例外」）。

#### 同一扇门的第三类：平台派发的源（`platformDispatched`，2026-11-14 当日就撞上了）

上面那处只治了「搬到别的站点」。chart 里还有一族 `suspend: true` 的理由完全不同：
**它的执行者是平台派发器**（`crawl_sources` 里 `enabled=true` + `schedule` 非空），
chart 那个 CronJob 只是手工兜底。base 里唯一一条是 `rmfyalk-case-crawl`
（`10 3 * * *` / `Asia/Shanghai`）——它自建成起就 `suspend: true`，于是**从第一天
就在日报的暂停名单里**，而没有人意识到这意味着「它断了也会被说成合法暂停」。

这正是本轮的实况，时间线可以逐条对上：

| 时刻（UTC） | 事实 | 出处 |
|---|---|---|
| 11-05T20:55 | rmfyalk 最后一次成功 crawl（rows=15） | `crawl_runs` id 4364 |
| 11-05T21:07 | `state.json.updatedAt` 停在此刻，之后再没动过 | RustFS `laws/legal-sources/rmfyalk-case-library/state.json` |
| 11-05T21:30 | `legal_documents` 最后一次装载（库里共 22,487 篇） | law_db |
| 11-07 → 11-10 | 平台每天预拉起登录站，4 次失败 + 1 次 timeout（"human login not completed in time"） | `crawl_login_stations` #65–#71 |
| 11-10T18:28 | 登录站 #72 拉起后**卡在 `waiting_operator`**，19:28 过 deadline 仍无人回收（Job 被 deadline 杀掉，没上报终态） | #72 `finished_at` 为空 |
| 11-08 → 11-13T18:00 | 日报**每轮都红**：`exit=2 / stale=rmfyalk-case-library` | `crawl_runs` id 5018…5755 |
| 11-13T20:12 | 新版镜像上产（带 `pausedSources`），日报**转绿**——**同一刻没有任何数据进库** | id 5779 起全 success |
| 11-10 → 11-14 | `pending_runs` 里 `rmfyalk-case-crawl` **19 次 failed**，预拉起**一次都没再开站** | panel 日志每 5 分钟 `prearm: no station needed this pass` |

最后两行是两处独立缺陷叠在一起：

1. **预拉起被僵尸站永久挡住**（`fd-open-data-mcp` `station_ops.py`）。超时兜底
   `_apply_timeouts` 是「读时生效」（panel 列站 / 打开 VNC 才跑），而那个 5 分钟
   后台循环 `prearm_plan` **从不读站表**，于是 `status in ('launching','waiting_operator')`
   把 #72 永远当成「操作者正看着」。修法两条，缺一不可：
   - `prearm_plan` 的 open-station 判据加 `deadline_at > now`（按**有效窗口**判，
     不按行状态判）——决策不再被僵尸站挡住；
   - `prearm_tick` 先跑 `_apply_timeouts` 再规划——状态真的被收成 `timeout` 并留痕，
     Console 上不会永远挂着一个「等待操作者」。
   自证：两条新用例在旧判据下都红（plan 返回空、tick 不改状态），换新判据即绿。
2. **日报把它算成「合法暂停」**，于是第 1 条从 11-13T20:12 起彻底不可见。

修法（chart 侧）：

```yaml
legalSources:
  activeElsewhere:     [party-regulation-library]   # 别的站点在跑
  platformDispatched:  [rmfyalk-case-library]       # 平台派发器在跑
```

模板把两个列表**并起来**排除出暂停名单（`helm-law-scraw.legalPausedSources`）。
改完 base 渲染出 `LEGAL_PAUSED_SOURCES=""`：master 上四个源都是自己在跑，
**一条合法的暂停都没有**，于是任何一条断流都会红——今晚 22:00Z 的日报就会以
`stale=rmfyalk-case-library` 退出 2，那是**恢复告警**，不是新故障。

`make verify-sites` 新增 **R4b** 守这条白名单，校验方向与 R4 相反：

- `activeElsewhere` 的名字必须**被某份 overlay 点亮**（否则是僵尸例外）；
- `platformDispatched` 的名字必须在**每一份** overlay 里都 `suspend: true`，
  否则平台派发器与 chart 会同时跑同一个爬（两执行者、两份 `crawl_runs` 行）；
- **只数爬，不数装载器**：平台派发拥有的是 crawl，loader 仍归 chart
  （rmfyalk 就是「爬在平台、装在 master」）。第一版把 loader 也算进来，
  在真树上立即误报了一条——判据的量词写错会红在合法部署上。
- 同一名字同时出现在两个列表里 = 「谁在跑」有两个答案，也计命中。

**运维上还剩一件只能人来做的**：rmfyalk 的登录是**人工**的
（`lib/auth-broker/logins/rmfyalk.js`：headed Chromium + noVNC，等人在页面里
完成登录，"human login not completed before the session deadline"）。
#72 已在 13:33Z 用 panel 自己的 `_apply_timeouts` 收成 `timeout`，
之后 `prearm_plan`（模拟 18:30Z）返回了 `rmfyalk` 那条身份的账号别名 ——
今晚 02:25 CST 前那轮预拉起会开出登录站，需要有人在 Console 里完成登录；
登录成功后按 `authenticated-crawling` 规格，平台会立刻为该 profile 入队一次执行。

**改完的当场 A/B（同代码、同数据，只差那个 env）**：用
`create job --from=cronjob/legal-sources-report` 跑当前版本，两次对照——

| crawl_runs | 时刻（UTC） | env | 结果 |
|---|---|---|---|
| 5916 | 11-14T12:21 | `LEGAL_PAUSED_SOURCES=rmfyalk-case-library` | `success`（**假绿**） |
| 5929 | 11-14T14:10 | `LEGAL_PAUSED_SOURCES=""` | `failed`，`exit=2 \| stale=rmfyalk-case-library` |

同一份镜像、同一份数据、相隔两小时 ⇒ 红绿之分完全由这行 env 决定。
这比「等今晚 06:00 看结果」强：它当场证明了告警恢复，而不是证明「今天恰好红」。

**两个 broker 都能用今晚这份登录**（另一处会静默失效的前提）：会话 jar 存在
RustFS 桶（`lib/auth-broker/s3-session-store.js`），不是本地卷；两侧 broker 的
`RUSTFS_ENDPOINT`/`LAWS_BUCKET` 逐字相同，`legal-auth-broker` Secret 的
`jar-key`/`broker-token`/`vnc-password` 三键 sha256 也相同（只打印 sha，不打印值）。
所以「在 server1 那侧登录、由 master 那侧爬」不会解密失败。

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

## 试点源的端到端核查：爬在 server1、装在 master（2026-11-14）

翻完试点后「CronJob 绿 + 库里有一行 success」证明不了任何事——那两样在**爬虫什么都没抓、
loader 什么都没装**的形态下同样成立。所以按「物理前提 → 覆盖 → 新鲜度」三层各要一个数：

**① 两侧是同一份桶（判等打 sha，不打值）**：`RUSTFS_ENDPOINT`（len=22 sha=`4ee0cb66`）／
`LAWS_BUCKET`（len=4 sha=`8954b4ce`）／`RUSTFS_REGION`（len=9 sha=`487d6534`）在
**server1 的 party crawl、master 的 party crawl、master 的 party load、master 的 report**
四处逐字相同；`PG_*` 只出现在 load 与 report（crawl 不碰库，缺它是设计而不是漏配）。
这是「爬在 A 写桶、装在 B 读桶」能成立的全部物理前提，缺一条就是「两侧都 success、数据永远不落地」。

**② 覆盖是完整的**（这一步才回答「有没有数据」）：今天扫 11 个类目页得到 **203 条**唯一文章路径，
库内 `party-regulation-library` **196 条**路径（391 行是因为 `source_id = url@v-<hash>`，
同一文书多个版本各占一行）。站点有而库里没有的 20 条逐条拉下来看标题，**全是评论稿**
（答记者问／解读／综述／纪实／新旧对照）或一份《中央党内法规制定工作规划纲要》——
正是 `COMMENTARY_PATTERN` 与「形式关键词」两条过滤器要排掉的东西；库里有而站点目录没有的 13 条
是 2012–2016 的旧条目（站点改版后下架，数据保留）。目录里最新一条
《公立医院领导人员管理办法》（2026-08-12 发布）库里已有，`fetched_at = 2026-10-08`。

**③ 0 行/天是正确稳态，不是空转**：`party-regulation-library` 最后一次装载 `2026-10-08`，
之后每一轮 crawl/load 都是 `success` + `rows_written=0`；而今天扫目录最新仍是 2026-09-18
⇒ **确实没有新法规可抓**（党内法规一年就几部）。报告侧也不会误报：`loadStalled` 的锚点只认
`emitted > 0` 的跑批（`lib/legal-sources/report.js`），安静的上游天然不报；`freshnessAt` 取
run manifest／`state.json`／`last_fetched_at` 三者最大值，所以 crawl 每天推进 state 就够判鲜。

两条判据纪律（当天都踩过）：

- **比覆盖必须先归一化 `source_id`**：库内是 `url@v-<hash>`，且站点在 `www.` / `news.` / `fuwu.`
  三个宿主上各有一份。直接比原串得到「204 条全缺、391 条全多」——**两边都反**（同族于
  「拿 `pg_get_viewdef` 逐字比必然假红」：比性质，不比字面）。
- **`image_tag` 不是站点身份**：11-12 那轮两个执行者都跑 `sha-30f5179`，库里两行一模一样；
  今天两站已对齐同片，这条限制更硬。判双执行者只能靠「同窗两条 success」。
  顺带一条结构事实：`crawl_sources.site` 对**全部** federated 源都写着 `xinru-server1`，
  但除 `rmfyalk-case-crawl`（平台派发，`schedule 10 3 * * *` / `schedule_tz Asia/Shanghai`）
  之外 `schedule` 都是 null —— 那个 `site` 是**目的地声明**，不是「谁真的跑了」。
  这也是 `crawl_runs` 该补 `site` 列的理由。


## 渲染↔线上漂移（`make verify-live`）—— 声明面绿 ≠ 线上是那样

上面所有门都有一个共同盲区：**它们验的是渲染产物**。`make verify-report` 断言
「日报把 `load_stalled` 写进 `crawl_runs`」，绿了很久——而 2026-11-14 逐字段比下来，
master 线上的 report `args` 少了整段 `loadStalled` recorder，**门断言的性质在生产里
根本不存在**。同一次比对还捞出 12 个对象没有 `resources` limits、两个对象
`FD_RUNNER_IMAGE_TAG` 停在旧片、report `backoffLimit` 是集群缺省 6。

这道闸就是那半边：对每个站点用该站点自己的 values 渲染，**把渲染产物经
`kubectl create --dry-run=client -o json -f -` 转成真正的 JSON**（不自己解 YAML——
本机 homebrew python 没有 PyYAML，而 gate 不该依赖解释器口味），再与集群同名对象
逐字段比 `image / command / args / env（名字+来源）/ resources / suspend / schedule /
backoffLimit / activeDeadlineSeconds`。

```bash
make verify-live                      # 两个站点都查；EXIT 1 有漂移 / 2 判不出
python3 scripts/verify-live-drift.py --site xinru
python3 scripts/verify-live-drift.py --self-test   # 8 条自证（含「args 少一段」）
```

四条判据纪律：

- **比 `resources` 先归一化量**：render 出 `cpu: 1`（整数），API 读回 `'1'`（字符串），
  直接比会造 13 条假红——首版就这么假红过，归一后残差 0。
- **`env` 按「名字+来源」比，不比值**：值来自 Secret 时两侧都只有 key 名，比的是
  引用一致性；真值比对照 `verify-secrets`。
- **R2/R3 只报事实**：chart 有、集群没有（还没 apply）与集群有、chart 不渲染
  （`guide-cases-*` 无主源、`federation-observer`/`gost-egress`/`proxy-control`
  站点级作业）都不是缺陷。
- **判不出退 2**：渲染失败、kubectl 读不到、某一侧 0 个可比对象——「什么都没比」
  不许读成「一致」。

它一上线就抓到一处：server1 线上的 `LEGAL_PAUSED_SOURCES` 仍把
`party-regulation-library` 算进暂停名单（那源在 server1 是亮的），补一次
`make render | kubectl --context xinru-server1 apply -n scraw -f -` 后两侧都逐字段一致。

第二处是**闸自己**的问题，值得单记：把 `LEGAL_PAUSED_SOURCES` 清空时，render 出
`value: ""`，而 API server 读回来是 `{"name": "LEGAL_PAUSED_SOURCES"}` ——
**`value` 字段整个消失**（空串等于不写）。运行期两者等价（env 条目还在，变量就是空串），
但按字面比就会永远报一条假红。所以 `envsig()` 现在把「value 缺失」与「空串」归一成
同一个东西（自证：`{name:P,value:""}` 必须等于 `{name:P}`，而非空值不许被吞）。
同族于「比性质不比字面」——**先问这个差异在运行期是否真实存在**，是才计命中。

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
  线上多带外加的 `FD_RUN_STARTED`（apply 不会删）。

**当日稍晚推翻了上面最后一句**（「这三处都不动线上」）。把它逐字段量化之后，
`render-base` 与 master 线上有 **30 处**字段差异，其中四处**不是惰性的**：

| 差异 | 面 | 为什么不算惰性 |
|---|---|---|
| 12 个对象 `resources: {}` | 全部 crawl/load/report | 线上**没有任何 limits**：一个跑飞的爬虫能把整台 3.7GB 机器吃掉，`NODE_OPTIONS` 只约束 V8 堆，管不住 RSS/CPU |
| `FD_RUNNER_IMAGE_TAG=sha-492925f` | `flk-law-embed`、`flk-law-load` | 停在旧片的自报值；镜像自报虽会压过它，但一旦自报缺失就会把错片写进 `crawl_runs` |
| `backoffLimit` 缺省（6） | `legal-sources-report` | chart 写 0 并配 `restartPolicy: Never`，理由写在模板里：重试三条一簇、间隔 12–102 秒，会把真信号稀释 |
| report `args` 缺 `load_stalled` recorder | `legal-sources-report` | **这是真缺口**：`make verify-report` 只验渲染，于是它一直在绿的断言「报告把 load_stalled 写进 crawl_runs」**线上根本没有** |

所以按 `make render-base | kubectl --context xinru apply -n scraw -f -` 收敛了 master，
并把「只比镜像/suspend」升级成**逐字段比**（`image`/`env`/`resources`/`args`/`command`/
`suspend`/`schedule`/`backoffLimit`）。两条判据纪律：

- **比 `resources` 要把量做归一化**：render 出的是 `cpu: 1`（整数），API 读回是
  `'1'`（字符串），直接比会造出 13 条假红；归一成字符串后残差 0。
- **apply 前后核 `suspend` 没变**（本次 16 个对象全保持：party / rmfyalk-case-crawl /
  flk-law-backfill 真，其余 13 个假）——整份 apply 最容易伤到的就是这一列。

收敛结果：report 现在 `backoffLimit: 0`、args 含 `load_stalled_sources` recorder、
`FD_RUNNER_IMAGE_TAG=sha-c33bf67`（`flk-law-embed`/`flk-law-load` 也一并追平），
归一化后**字段残差 0 处**。窗口选在下一个作业（18:30Z）之前，CronJob 的 patch
不碰已在跑的 Job。

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

### 2026-11-14 server1 曾连续三天 DiskPressure（上线前必须知道的容量事实）

清 `scraw` 的幽灵 pod 时撞出来的：3,115 个 pod 里 **2,846 个**是已归零的
ReplicaSet `legal-auth-broker-5d9ffff556` 的失败 pod，创建日 11-10（782）/
11-11（1,428）/11-12（640）。抽样 pod 写得很直白：

```
phase: Failed   reason: Evicted
message: Pod was rejected: The node had condition: [DiskPressure].
container: ContainerStatusUnknown（The container could not be located when the pod was terminated）
```

所以那三天里 broker 是**被驱逐→RS 补新→再驱逐**的循环，不是「起不来」。
**没有任何通道报过**：那台机没有 mail，`node-health-alerts` 跑在 fd-prod 看不见它，
`check_cronjob_health.py` 只判 Job condition、根本不经过 ReplicaSet 的 pod。

处置与判据：

```bash
# 只删死 RS 的失败 pod：hash 属于一个 DESIRED 0 / CURRENT 0 的旧 RS ⇒ 不可能命中活的
kubectl -n scraw delete pods -l pod-template-hash=5d9ffff556 \
  --field-selector status.phase=Failed --wait=false        # 3115 -> 242
```

剩下的 52 个 `Evicted` 属于爬虫 Job 自己（数量小、留作证据，不清）。
**别用「所有 Failed/Unknown」当选择器**——那会把仍有所有者的运行期证据一起删掉。

**当前容量**（2026-11-14 实测，`/api/v1/nodes/vm-0-15-debian/proxy/stats/summary`）：
根分区 **31.2 / 41.7 GB（75%，剩约 10.5 GB）**，imageFs 6.5 GB，节点
`Ready` 且 DiskPressure/PIDPressure/MemoryPressure 全 `False`。这台机同时承着
`/srv/fd-backup`（异地镜像与备份落点）与唯一的 local-path 卷
（`scraw/legal-auth-<法务账号>-profile`，2 GiB，全名见集群 PVC 列表）。**往上排夜间作业前先核这一项**——
盘满那次的表现不是宕机，是一批 pod 静默消失。

### 2026-11-14 夜：给全站 CronJob 加 `resources` 之后的前置调度核查

同一天晚些时候把 `resources`（`requests 100m/256Mi`、`limits 1/2Gi`）收敛进 12 个
线上对象，而这些作业**此前是 `resources: {}`**。加 `limits` 会带来一个全新的失败形态
（超限 → `OOMKilled`），所以点火前先把「会不会排不上、会不会更容易被驱逐」核清：

```
节点 vm-0-15-debian: allocatable cpu=4 / memory=3818800Ki (=3.64 GiB) / pods=110
  conditions: Ready True, MemoryPressure/DiskPressure/PIDPressure 全 False
全命名空间 Running pod 6 个，requests 合计 cpu 0.30 / mem 0.26 GiB
scraw 命名空间: 无 ResourceQuota（`get resourcequota` → No resources found）
kubelet stats: 根分区 capacity 38.80 GiB / used 31.65 GiB / available 7.13 GiB，
              imageFs used 5.57 GiB（对照上面 31.2/41.7 GB：同一天里 used 涨了约 2.8 GiB，
              与 `sha-b63d0d1 → sha-c33bf67` 那次整机滚片拉新层吻合，不是数据增长）
```

三条结论，都是判据本身而不是「看起来没事」：

- **排得上**：调度只看 `requests`，新值 100m/256Mi 对 3.64 GiB/4 核、剩余 requests
  3.38 GiB 的节点是零压力；`scraw` 没有 ResourceQuota，也就不存在配额准入这一道。
- **`limits 2Gi` 不会 OOM**：V8 老生代被 `NODE_OPTIONS=--max-old-space-size=384`
  （`values.yaml:416`）钉住，实测 RSS 量级远低于 2 GiB——这个 limit 是「防跑飞」的天花板，
  不是贴着真实用量的紧箍。**别把它读成容量规划**。
- **但 2 GiB 的 limit 在这台机上不是无限的余量**：节点总内存 3.64 GiB、已用 2.2 GiB（59%），
  真正富余约 1.4 GiB。某个作业真吃到接近 limit 时，内核会先杀大的，而不是等 k8s 记账——
  这正是 DiskPressure 那三天的同族形态（磁盘版本）。所以**盘/内存两件都要在排新夜间作业前核**，
  且 `189 Succeeded + 52 Failed` 这些残留 pod 是故意留的证据，不是待清垃圾。

顺带记一条当天的状态：`scraw` 里 2 个 `Pending` 是 `ContainerCreating`
（`fd-industry-dispatcher`、`federation-observer`），`PodScheduled True`、
没有 `FailedScheduling` —— 属于正在拉镜像，**不要当调度失败处理**。

**同日补齐的漏洞：`flk-law-crawl` / `flk-law-embed` 此前是全站唯一两个没有
`resources` 的作业**（`legalSources` 那 12 个有，它们没有；`NODE_OPTIONS` 也没有）。
最忙的爬虫无上限 = 跑飞就吃掉整台 3.64 GiB、内核随机杀一个（同族于 09-24 那次）。
已补成与兄弟作业同档（requests 100m/256Mi、limits cpu 1 / mem 2Gi），模板用 `with`
包裹（值为空则不渲染）。**刻意没加 `NODE_OPTIONS`**：兄弟那条 384MB 是 09-24 实测
「堆过 ~800MB 被内核杀」的经验值，flk 没有同类实测——照抄一个堆上限可能把它自己
压死，而 V8 堆耗尽比 cgroup OOM 更难查。要加先量。
量的时候会发现：**安静日量不出峰值**。当天从线上 CronJob 派生一次实跑（跑的是当前
版本），13 秒完成、各分类 `total: 0`——没有新条目就不会走到重内存路径。所以档位取
「远高于 09-24 实测 ~800MB」的 2 GiB，而不是拿 13 秒那次当依据。

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

## `party-regulation` 两段常年 `rows_written=0` 是**正常**，不是空转（2026-11-15 查证）

看板/crawl_runs 上这两个源 30 天全是 `success + 0 行`，容易被读成「绿得比绿还真」那一族
（占位行把失败伪装成成功）。逐层查完，结论是**这条链没有缺陷**，判据如下：

1. **crawl 段的 0 行是设计**：`party-regulation-crawl.mjs` 只把变更写进桶
   （`laws/legal-sources/party-regulation-library/structured/*.jsonl`），不写库，所以
   `crawl_runs.rows_written` 恒 0。`flk-law-crawl` 同理。
2. **load 段的 0 行是「全 unchanged」**：`legal-source-load.mjs` 里
   `if (!records.length) throw new Error('no structured records under …')` —— 桶里真没记录
   会**报错**，而它报 success，故一定读到了记录，只是 `inserted+updated==0`。
3. **语料本身小且没变**：`legal_documents` 按源计数
   （2026-11-15 04:50Z 实测，`law_db`）：
   `rmfyalk 22487 / gov-rules 10603 / mfa-treaty 7453 / ccdi 6420 / party 391`。
   桶里 `party` 的 `state.json` 只有 `hashes: 197` 个、`watermark: null`
   （无日期增量，每轮回看全部 197 条），structured 4 个 part / 7.39MB
   —— 对照 `gov-rules` 是 10,593 个 hashes / 43 parts / 136MB。
4. **391 ≠ 197 的原因**：party 是 **versioned 适配器**，每份文档按修订版存一行
   （`URL@v-<hash>`，见 `lib/legal-sources/state.js` 的 `stateKeyOf` 头注
   「party audit 2026-10-10: 0 of 193 documents ever hit a known key」）⇒
   391 行 ≈ 197 个实体 × 约两版。10-10 那次 `state.json.bak-*` 是 state rebuild。

**所以今晚 19:40Z 试点的正确结果是 `success + rows_written=0`**，不是冷启动成功。
要看「它到底动没动」，只有三个判据（都别拿 rows 判）：

- `scraw/crawl_runs` 有一条新的 `party-regulation-crawl` success（行为已跑）；
- 桶里 `legal-sources/party-regulation-library/state.json` 的 `updatedAt` 前移
  （爬虫真的回看过；2026-11-15 实测 11-14T04:50Z）；
- `law_db.legal_documents` 里 `source='party-regulation-library'` 的计数与 `newest`
  （`fetched_at`）——**只有源站发了新东西才会动**，不动是常态。

`make verify-runs` 不受影响：`verify-single-executor-runs.py` 只判「一个排期窗内一条
success」，不看 `rows_written`，不会把 0 行判红。

## rmfyalk 登录窗口为什么总落空，以及正确的登录时间（2026-11-14 查证）

**现象**：预拉起在每轮爬虫开火前 45 分钟开站（`rmfyalk-case-crawl` 是
`10 3 * * *` Asia/Shanghai ⇒ 开火 03:10 CST，站点 **02:25 CST** 打开、60 分钟后关）。
这个点人基本不在，于是每轮的派发都记 `auth pool dry: no active unleased identity`，
源长期零产出，而站本身每次都是好的。

**两条判据决定「其实不用熬到 3 点」**：

1. **派发器的身份判据只看状态，不看新鲜度** —— `fd_industry_data/auth.py`
   的 `lease_identity()` 选行条件是
   `source=<auth_profile> AND status='active' AND lease_token IS NULL`，
   **没有 `last_probe_at` 时间窗**。所以只要身份是 `active`，几小时前登录的一样能被 03:10 那轮租到。
2. **预拉起只在「身份不新鲜」时才开站** —— `station_ops._fresh_identity()` 要求
   `status='active'` 且 `last_probe_at` 在 `FD_PREARM_FRESH_HOURS`（默认 6）内。
   所以晚上登录过的身份，到次日 02:25 若仍在新窗口内，预拉起**不会重复开站**（这是对的）。

**可操作结论**：在**晚上自己方便的时候**用 Console 开站并完成一次 rmfyalk 登录即可，
不必等到 02:25。约束只剩一条客观事实——**站点侧的会话本身要能撑到 03:10**（不是代码闸，
是 rmfyalk 自己的过期时间）。若怕撑不住，次优选择是在 02:25 站点打开后尽快登。

**另外两条今晚实测的时间量纲**（判「还来得及吗」时别用错）：

- **站窗口 60 分钟**（`FD_STATION_DEADLINE_SECONDS` 默认 3600），但
- **派发窗口只有 15 分钟**（`fd_industry_data/dispatch.py` 的 `enqueue_due(window_minutes=15)`，
  派发 tick 每 5 分钟）⇒ 19:10Z 的开火点只在 19:10/19:15/19:20/19:25 四次尝试，
  **19:25Z 之后登录对当轮无效**（2026-11-13 与 11-14 两天的 pending_runs 都是这四行）。

**站建出来了但 VNC 打不开时，先看 init 容器日志**（2026-11-14 实历）：
`kubectl -n fd-mcp logs <station-pod> -c checkout` —— 当晚是 gitee 令牌在
`tencent/fd-industry` 那份更新了、`xinru/fd-mcp` 这份没更新（克隆报
`Incorrect username or password (access token)`），而站行状态照旧写着
`waiting_operator`、面板日志照旧写 `station #NN launched`。修法与核对配方见
`~/.zcode/.../memory/connectivity-proves-network-not-credential-parity.md`。
