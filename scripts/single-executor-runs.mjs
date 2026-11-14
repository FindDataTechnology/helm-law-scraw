// 单执行者闸（行为侧）的行数据产出器 —— 见 scripts/verify-single-executor-runs.py
//
// 为什么用 Pod 而不在脚本里直连库：本机没有 psql（`command -v psql` 为空），
// 而把一个 DSN 摊进命令行会进 `ps`。这个 Pod 从 secret 取 DSN，只把结果打到
// stdout，验证器本身是**纯比对器**。
//
// 用法（在仓根跑，镜像要带 pg 依赖 + 用当前出片段）：
//
//   kubectl -n scraw create configmap qruns \
//     --from-file=single-executor-runs.mjs=scripts/single-executor-runs.mjs \
//     --dry-run=client -o yaml | kubectl -n scraw apply -f -
//
//   cat > /tmp/runs-pod.yaml <<'YAML'
//   apiVersion: v1
//   kind: Pod
//   metadata: {name: runs, namespace: scraw}
//   spec:
//     restartPolicy: Never
//     containers:
//       - name: q
//         image: ccr.ccs.tencentyun.com/lawcraw-business/fd-law-data:sha-c33bf67
//         command: ["node", "/app/q/single-executor-runs.mjs"]
//         env:
//           - {name: FD_CRAWL_DB_URL, valueFrom: {secretKeyRef: {name: federation-db, key: url}}}
//           - {name: FD_LOOKBACK_DAYS, value: "7"}
//         volumeMounts: [{name: s, mountPath: /app/q}]
//     volumes: [{name: s, configMap: {name: qruns}}]
//   YAML
//
//   kubectl -n scraw delete pod runs --ignore-not-found
//   kubectl -n scraw apply -f /tmp/runs-pod.yaml
//   kubectl -n scraw wait --for=jsonpath='{.status.phase}'=Succeeded pod/runs --timeout=120s
//   kubectl -n scraw logs runs | tail -1 > /tmp/rows.json
//   make verify-runs ROWS=/tmp/rows.json SINCE=2026-11-14T05:00:00Z
//
// 只取 kind='federated' 的源：这些是「可能有两个执行者」的那批（chart 渲染的
// CronJob + 站点 dispatcher 派发的 Job）。普通源只有一个执行者，纳进来只会噪声。
import pg from "pg";

const c = new pg.Client({ connectionString: process.env.FD_CRAWL_DB_URL });
await c.connect();

const days = Number(process.env.FD_LOOKBACK_DAYS || 7);
const q = await c.query(
  `select r.id::text as id,
          r.source,
          r.status,
          to_char(r.started_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as started_at,
          coalesce(r.image_tag, '') as image_tag
     from crawl_runs r
    where r.source in (select source from crawl_sources where kind = 'federated')
      and r.started_at > now() - ($1 || ' days')::interval
      and r.status in ('success', 'failed')
    order by r.source, r.started_at`,
  [String(days)],
);

console.log(JSON.stringify(q.rows));
await c.end();
