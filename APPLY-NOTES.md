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
- `images.flkLawCrawl` — 100.64.0.8:30880/lawcraw_business/fd-law-data:sha-e78d96e
  (registry mirror, underscore project) + `harbor-lawcraw-pull` pull secret.
  IN-SERVICE; converged to live, zero behavior change.
- `images.authBroker` — 100.64.0.8:30880/lawcraw_business/legal-auth-broker:sha-b726e1f.
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
  3. `legal-sources-report` gains PG_* env (PG_HOST 100.64.0.5, PG_PORT 5432,
     PG_DATABASE law_db, PG_USER/PG_PASSWORD from flk-law-pg-credentials) —
     required by the new report code; live report predates it.
  Nothing else differs: schedules, suspends (all true), deadlines, envs,
  commands, labels match live; mfa/ccdi crawl deadlines were fixed to live
  (28800); rmfyalk command carries `--account-id acct001 --auth-broker
  http://legal-auth-broker.scraw` plus its 4 auth envs from Secrets.

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
