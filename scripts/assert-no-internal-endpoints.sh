#!/usr/bin/env bash
# 卫生门：内网地址与法务身份标识不得出现在被跟踪的文件里。
#
# 为什么要有这条门（2026-11-12）：values.yaml 曾经直接写着内网端点、PG 主机与
# 身份标识。仓是私有的，所以不是"泄露"事故，但它是**运维地图**：任何人 clone
# 就拿到内网拓扑。搬进带外 values-private.yaml 之后，剩下的风险是有人图省事又把
# 真地址写回来 —— 那时没有任何门会红。这条门就是那扇门。
#
# 判据（与 openspec change repo-hygiene-debt-and-runner-rollout 1.1 同一句）：
#   git grep -nIE "100\.64\.|acct[0-9]{3}|lawcraw_business" -- . ':!charts'
# 命中即失败，并把命中行原样打出来（点名到文件:行）。
#
# 注意：查的是**工作树**（git grep 的默认），不是暂存区。两者在正常提交流程里
# 一致；若你想核暂存区，用 `git grep --cached`。
#
# ⚠ 本脚本自身被排除（:!scripts/assert-no-internal-endpoints.sh）：它必须写出模式串
# 才能扫，否则提交后第一件事就是自己触发自己。排除范围**只到这一个文件**，
# 不要扩成 `:!scripts`——那会把整个脚本目录从卫生面里挖掉。
set -uo pipefail

CHART_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SELF="scripts/assert-no-internal-endpoints.sh"
PATTERN='100\.64\.|acct[0-9]{3}|lawcraw_business'

if ! git -C "$CHART_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  # 不是 git 工作树（例如从 tarball 解出来的目录）：如实说"没查"，不假装通过。
  printf 'SKIP verify-hygiene：不在 git 工作树里，无法核对历史/被跟踪文件\n'
  exit 0
fi

HITS="$(git -C "$CHART_DIR" grep -nIE "$PATTERN" -- . ':!charts' ":!$SELF" 2>/dev/null)"
if [ -n "$HITS" ]; then
  printf '✗ 卫生门未通过：内网地址 / 身份标识出现在被跟踪的文件里\n\n'
  printf '%s\n' "$HITS" | sed 's/^/    /'
  cat <<'EOF'

修法：把真实值搬到带外 values-private.yaml（已 gitignore），
values.yaml 里留空并让模板的 required 守卫兜住；文档里改成指向该文件/集群 Secret。
判据命令（改完必须 0 命中）：
    git grep -nIE "100\.64\.|acct[0-9]{3}|lawcraw_business" -- . ':!charts'
EOF
  exit 1
fi

printf 'ASSERT_NO_INTERNAL_ENDPOINTS ok（0 命中）\n'
