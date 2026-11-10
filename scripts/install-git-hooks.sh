#!/usr/bin/env bash
# 显式安装本地 git hooks（opt-in）。不装 = 零干预。
#
# 只改本克隆的 core.hooksPath（本地 git 配置，不是 GitHub 上的仓库设置），
# 因此对同机的其他克隆、其他会话没有任何影响。
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

[ -d .githooks ] || { echo "✗ 缺少 .githooks/"; exit 1; }
chmod +x .githooks/* 2>/dev/null || true

current="$(git config --local --get core.hooksPath || true)"
git config --local core.hooksPath .githooks

echo "✓ 已安装：core.hooksPath=.githooks（本克隆生效）"
[ -n "$current" ] && echo "  原值：$current"
cat <<'TXT'

行为：提交时若暂存区含 values*.yaml / templates/ / scripts/ / Makefile，
自动跑 `make verify-report`；不通过则拒绝提交。helm 缺失时拒绝而不是跳过。

卸载：git config --local --unset core.hooksPath
TXT
