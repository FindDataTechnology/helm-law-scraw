# APPLY-NOTES — helm-law-scraw on xinru (converged 2026-10-06)

This chart is converged to the xinru cluster (`xinru-master`, 134.175.46.69,
namespace `scraw`) live inventory. **Standard apply command (when a wave is
approved):**

```bash
# render exactly what the cluster should look like (object names are
# release-name independent — safe with any release name)
helm template law-craw /Users/chengsishi/finddata/helm-law-scraw --namespace scraw

# lint
helm lint /Users/chengsishi/finddata/helm-law-scraw
```

## ⚠️ Namespace rule (2026-10-06 wave-0 lesson)

`helm template` output carries **NO namespace** (active templates render bare
objects). Applying the render without a namespace flag creates duplicate
objects in `default` (this happened on wave-0 and was cleaned via
`kubectl delete -l app.kubernetes.io/part-of=finddata -n default`).
ALWAYS apply with an explicit namespace:

```bash
helm template law-craw /Users/chengsishi/finddata/helm-law-scraw --namespace scraw \
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
`gost-egress`, `proxy-control`, `legal-auth-rmfyalk-acct001-profile` (PVC).
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
helm template law-craw . --namespace scraw \
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


## 法律线宿主：xinru-server1（2026-10-07 迁移后）

法律线全家驻 xinru-server1 scraw ns（独立 k3s、节点级 ccr 认证、docker.io 轩辕加速已配）。
- 渲染：`helm template law-craw . --namespace scraw -f values-server1.yaml`
- **runner_image 同步义务**：升级 `images.legalSources.tag` 时必须同步 `crawl_sources.runner_image`（dispatcher 触发的 Job 用登记值，不是 chart 值）——drill 4.2 曾因此跑旧镜像。
- xinru 侧 13 个挂起 CronJob 为回退，稳定一周后清理。

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
