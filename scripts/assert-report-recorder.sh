#!/usr/bin/env bash
# 断言 legal-sources-report 的容器 args 里带着 crawl_runs 记录器，
# 且该记录器认识 load_stalled_sources。
#
# 为什么要在 chart 仓里断言这件事：这个记录器的真身过去只存在于一份已废弃的
# 独立清单（fd-law-data/k8s/legal-source-crawl-cronjobs.yaml），chart 里只是裸跑
# 脚本 —— 谁 apply chart 谁就把 crawl_runs 里那一行记录弄丢，而且没有任何门会红。
# 2026-11-10 收编进 chart 后，这条断言就是那扇门。
#
# 只依赖 helm + POSIX 工具，不引 yq/python，CI 直接可跑。
set -uo pipefail

CHART_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE="${RELEASE:-law-craw}"
NAMESPACE="${NAMESPACE:-scraw}"
NAME="${NAME:-legal-sources-report}"

RENDERED="$(helm template "$RELEASE" "$CHART_DIR" --namespace "$NAMESPACE" 2>&1)" || {
  printf '✗ helm template 失败：\n%s\n' "$RENDERED"; exit 1; }

# 只取目标 CronJob 那一段，避免别的文档里恰好出现同名字符串导致假通过。
BLOCK="$(printf '%s\n' "$RENDERED" | awk -v name="$NAME" '
  /^---$/ { if (hit) exit; buf=""; hit=0; next }
  { buf = buf $0 "\n"; if ($0 ~ ("name: " name "$")) hit=1 }
  END { if (hit) printf "%s", buf }
')"

[ -n "$BLOCK" ] || { printf '✗ 渲染结果里找不到 CronJob/%s\n' "$NAME"; exit 1; }

printf '%s\n' "$BLOCK" | grep -q 'kind: CronJob' \
  || { printf '✗ %s 不是 CronJob\n' "$NAME"; exit 1; }

fail=0
require() { # 模式 说明
  if printf '%s\n' "$BLOCK" | grep -qF -- "$1"; then
    printf '  ✓ %s\n' "$2"
  else
    printf '  ✗ 缺少 %s\n' "$2"; fail=1
  fi
}

echo "断言 $NAME 的 args："
# helm 渲染出来是块序列（`- sh` / `- -c`），不是流式 ["sh","-c"] ——
# 断言必须对着**渲染后的形态**，否则门在真形态上永远红、在人以为的形态上永远绿。
# 用 POSIX 字符类：BSD 的 awk/grep 不保证支持 \s。
if printf '%s\n' "$BLOCK" | awk '
     /^[[:space:]]+command:[[:space:]]*$/ { seen=1; next }
     seen && /^[[:space:]]+-[[:space:]]+sh[[:space:]]*$/ { sh=1; next }
     seen && /^[[:space:]]+-[[:space:]]+-c[[:space:]]*$/ { c=1; exit }
     END { exit !(sh && c) }
   '; then
  printf '  ✓ %s\n' 'command 渲染为块序列 sh -c（多行记录器需要）'
else
  printf '  ✗ 缺少 command: sh -c（块序列形态）\n'; fail=1
fi
require 'stale_sources'                    '记录器读取 stale_sources'
require 'load_stalled_sources'             '记录器读取 load_stalled_sources'
require 'INSERT INTO crawl_runs'           '记录器把自己写进 crawl_runs'
require 'FD_CRAWL_DB_URL'                  '记录器有落库连接来源'

if [ "$fail" -ne 0 ]; then
  cat <<'EOF'

修复方向：values.yaml 的 legalSources.report.command/args 必须是
「跑 bin/legal-sources-report.mjs → 解析 report.json → INSERT INTO crawl_runs」的
记录器形态，且 status 与 error_head 都要认 load_stalled_sources。
见 README「legal-sources-report 的判据口径」。
EOF
  exit 1
fi
printf 'ASSERT_REPORT_RECORDER ok\n'
