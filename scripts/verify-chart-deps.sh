#!/usr/bin/env bash
# 校验随仓预置的 chart 子依赖（charts/*.tgz）与 Chart.yaml 声明**逐对一致**。
#
# 为什么需要它：子依赖是二进制，随仓入库后最容易悄悄腐坏 —— Chart.yaml 升到
# redis 28.x，charts/ 里还躺着 27.0.15.tgz，`helm template` 照样渲染成功（helm 只
# 认文件名里的版本，不读 Chart.yaml 的期望值做比对），于是线上跑的是旧依赖而没
# 有任何信号。2026-11-10 起依赖入库（charts/*.tgz），这条门就是它的守护。
#
# 判据三条：
#   1. Chart.yaml 每个 dependency 都要有 charts/<name>-<version>.tgz；
#   2. charts/ 里不得有未声明的 tgz（陈旧残留会让人以为换过依赖）；
#   3. 缺依赖时点名该跑什么，不把网络问题伪装成内容问题。
#
# 只依赖 helm 之外的标准工具（awk/sed/ls），无 yq/python 依赖。
set -uo pipefail

CHART_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CHART_YAML="$CHART_DIR/Chart.yaml"
[ -f "$CHART_YAML" ] || { printf '✗ 找不到 %s\n' "$CHART_YAML" >&2; exit 1; }

# dependencies: 块内抽 (name, version)。块在遇到下一个顶格键时结束。
DECLARED="$(awk '
  /^dependencies:[[:space:]]*$/ { inblock=1; next }
  inblock && /^[^[:space:]#]/ { inblock=0 }
  inblock && /^[[:space:]]*-[[:space:]]*name:/ { sub(/^[[:space:]]*-[[:space:]]*name:[[:space:]]*/, ""); gsub(/["'"'"']/, ""); name=$0 }
  inblock && /^[[:space:]]*version:/ {
    sub(/^[[:space:]]*version:[[:space:]]*/, ""); gsub(/["'"'"']/, "");
    if (name != "") { printf "%s %s\n", name, $0; name="" }
  }
' "$CHART_YAML")"

[ -n "$DECLARED" ] || { printf '✗ Chart.yaml 里没解析出任何 dependencies（格式变了？）\n' >&2; exit 1; }

fail=0
declare -a EXPECTED=()
echo "校验 charts/ 与 Chart.yaml："
while read -r name ver; do
  [ -z "$name" ] && continue
  want="charts/${name}-${ver}.tgz"
  EXPECTED+=("${name}-${ver}.tgz")
  if [ -f "$CHART_DIR/$want" ]; then
    printf '  ✓ %-32s (%s)\n' "$want" "$(du -h "$CHART_DIR/$want" | cut -f1)"
  else
    printf '  ✗ 缺 %s（Chart.yaml 声明 %s %s）\n' "$want" "$name" "$ver"
    found="$(ls "$CHART_DIR"/charts/"$name"-*.tgz 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
    if [ -n "$found" ]; then
      printf '      charts/ 里现有：%s→ 版本与声明不符（陈旧副本），删掉或按声明重出\n' "$found"
    else
      printf '      该依赖一个文件都没有\n'
    fi
    fail=1
  fi
done <<< "$DECLARED"

# 未声明的残留
for f in "$CHART_DIR"/charts/*.tgz; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  hit=0
  for e in "${EXPECTED[@]}"; do [ "$base" = "$e" ] && hit=1; done
  if [ "$hit" -eq 0 ]; then
    printf '  ✗ 未声明却存在：charts/%s（Chart.yaml 里没有对应 name+version）\n' "$base"; fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  cat >&2 <<'EOS'

修复方向（二选一）：
  · 依赖版本就在仓里定：把正确的 charts/<name>-<version>.tgz 放进 charts/ 并提交；
  · 要换版本：先改 Chart.yaml 的 dependencies.version，再重出 tgz。
重出需要能访问 oci://registry-1.docker.io/bitnamicharts（内网实测 i/o timeout）。

注意：helm 只按文件名里的版本加载，**不会**拿 Chart.yaml 的期望值比对 ——
所以版本漂移不会自己报错，必须靠这条校验。
EOS
  exit 1
fi
printf 'ASSERT_CHART_DEPS ok（%d 个依赖，全部与 Chart.yaml 一致）\n' "${#EXPECTED[@]}"
