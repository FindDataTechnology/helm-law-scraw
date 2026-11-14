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
`flk-law-load`, `flk-law-embed`, `federation-observer`, `guide-cases-crawl`,
`gost-egress`, `proxy-control`, and the rmfyalk identity-profile PVC
(`legal-auth-rmfyalk-<账号标识>-profile`；账号标识见带外 `values-private.yaml`).
The chart renders no object with any of these names — verified.

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

现状（2026-11-14）：**master 是活宿主，server1 / chengsi 全灭**。

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
