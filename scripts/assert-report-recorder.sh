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

# 子依赖（charts/）是 gitignored 的，新克隆里必然缺席。
# 这里**只做前置检查**、不自动补：`helm dependency build` 要从 Docker Hub 拉
# bitnami 的 OCI chart，内网/离线环境下会卡满超时（实测 60s 后 i/o timeout），
# 把网络问题混进内容门里最容易被 --no-verify 绕过。缺了就直接说清楚怎么补。
# 注意形态：依赖是**打包好的 .tgz**（charts/redis-27.0.15.tgz），不是解包目录。
# 判据按真实文件名匹配，不按我以为的目录名（这条已经栽过一次）。
have_dep() { ls "$CHART_DIR"/charts/"$1"-*.tgz >/dev/null 2>&1; }
if ! have_dep redis || ! have_dep postgresql; then
  cat >&2 <<'EOS'
✗ 子依赖缺失（charts/ 被 gitignore），无法渲染。
  先跑一次：helm dependency build .
  （需要能访问 oci://registry-1.docker.io/bitnamicharts；离线时这一步会超时）
  这是环境前置，不是 chart 内容问题。
EOS
  exit 1
fi

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
# 只「读」不够：有人把 `&& !loadStalled` 从 status 表达式里删掉，字段还在、判据已死。
require '!loadStalled'                     '装载停滞参与 status 判定'
require 'load_stalled='                    '装载停滞落进 error_head'
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
