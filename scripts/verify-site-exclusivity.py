#!/usr/bin/env python3
"""站点 overlay 互斥闸：同一个 CronJob 不许在两个站点同时点亮。

抓的是什么
----------
本 chart 用「base + 站点 overlay」表达「谁跑这条线」：
`values.yaml` 是 base（APPLY-NOTES 记为与 xinru-master 线上收敛），
`values-<site>.yaml` 只覆写各源的 `suspend`。于是同一个源到底谁在跑，
由**两个文件各说一遍**——而没有任何东西比过这两句话。

2026-11-14 实历：`values-server1.yaml` 把 mfa-treaty / gov-rules /
party-regulation / ccdi 四个爬虫 + 五个 loader + report + flkLawCrawl 全写成
`suspend: false`，而同一时刻 xinru-master 上这四只爬虫**正在跑**（且是当前镜像）。
两侧同时在跑的证据不是清单，是数据：2026-11-13 那一轮 `crawl_runs` 里
四个源各写了两行、`image_tag` 不同（`sha-e584fc5` / `sha-b63d0d1`）——
一行的执行者 = master 的 CronJob，另一行 = server1 的 CronJob。
那种重复只在**两侧 pod 都真起来**时才留下痕迹：11-12 之前 server1 侧一直
Failed 0/1（pod 没起来、不写行），所以这件事长期不可见。

一条纪律
--------
切换宿主不是「把新宿主点亮」，是**同一次改动里两边一起翻**：
新站点 suspend:false 与旧站点 suspend:true 必须同步。只翻一侧 = 双跑，
而双跑写的是同一张 `crawl_runs`、同一批 laws 行，症状要几天后才以别的形态冒。
闸不猜哪边该活（那是人的裁决），只拒绝「两边都活」。

判据
----
R1 同时点亮（FAIL）：同一条 label 在两个站点的生效值里都是 suspend=false。
R2 幽灵键（FAIL）：overlay 写了 base 里不存在的键——Helm 会把它合进去，
   但没有任何模板读它，等于「声明了但没生效」，比报错更贵。
R3 判不出（EXIT 2）：没 base、没有 overlay、文件解析不了、或出现本脚本
   不解析的 YAML 形态（flow map / anchor / list）。判不出**不许退 0**。

用法
----
    python3 scripts/verify-site-exclusivity.py            # 本仓 values*.yaml
    python3 scripts/verify-site-exclusivity.py --self-test
    python3 scripts/verify-site-exclusivity.py --dir <chart>

退出码：0 全过；1 命中（逐条带修法）；2 判不出。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE = "values.yaml"
#: 带外凭据 overlay（gitignore）。它不是站点：里面只有内网端点/主机/账号标识，
#: 不该决定「谁跑」。默认不参与比较——否则同一份仓在「本机有那份文件」与
#: 「CI 没有」两种情形下判出不同结论（判据不许嵌进我这台机器的形状）。
PRIVATE = "values-private.yaml"
FALSY = {"false", "no", "off", "0", ""}
#: 只在这些顶层段落里看 suspend —— 其余段落（images/redis/postgresql）
#: 没有「谁跑」的语义，纳进来只会制造噪声。
SCOPES = ("legalSources", "flkLawCrawl", "flkLawEmbed", "wenshuCrawl")
#: 这几个键必须是 map；一旦写成 list（`- name: x`），按 map 比较的闸就整体失效。
MUST_BE_MAP = {"sources", "loaders"}


class Unparseable(Exception):
    """本脚本不解析这一行（宁可判不出，也不猜）。"""


def parse(path: Path) -> dict[tuple[str, ...], str]:
    """把 `a: b:` 缩进映射拍平成 {路径元组: 标量值}。

    只支持本 chart 的写法（纯 block mapping、2 空格缩进、无 list/anchor/flow）。
    出现别的形态就抛 Unparseable —— 判不出比猜错便宜。
    """
    scalars: dict[tuple[str, ...], str] = {}
    stack: list[tuple[int, str]] = []
    skip_indent: int | None = None
    skipped_lists: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if skip_indent is not None:
            if indent > skip_indent:
                continue
            skip_indent = None
        if line.startswith("-"):
            # list 不解析，整段跳过。合法形态：`command:`/`args:`/`accessModes:`
            # 这类与「谁跑」无关的字段。但 `sources:`/`loaders:` 本身若变成
            # list（`- name: x`），键集比对就整体失效 ⇒ 那时判不出，不许静默跳过。
            here = tuple(k for _, k in stack)
            if not here or here[-1] in MUST_BE_MAP:
                raise Unparseable(
                    f"{path.name}:{lineno} {'.'.join(here) or '<root>'} 是 list；"
                    f"本闸按 map 比较，形态一变就判不出")
            skipped_lists.append(f"{path.name}:{lineno} {'.'.join(here)}")
            skip_indent = stack[-1][0] if stack else -1
            continue
        if ":" not in line:
            raise Unparseable(f"{path.name}:{lineno} 不是 key: value")
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.strip()
        if not key or key.startswith(("&", "*", "<<")):
            raise Unparseable(f"{path.name}:{lineno} anchor/alias")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        here = tuple(k for _, k in stack) + (key,)
        if rest == "" or rest.startswith("#"):
            stack.append((indent, key))
            continue
        value = rest.split(" #", 1)[0].strip()
        if value.startswith("{"):
            # flow map 里可能藏着 suspend（`x-lib: {suspend: false}`），
            # 解析不了就判不出——不许静默当成「这条没有 suspend」。
            raise Unparseable(f"{path.name}:{lineno} flow map 形态")
        if value.startswith("["):
            skipped_lists.append(f"{path.name}:{lineno} {'.'.join(here)}（flow 序列）")
            continue
        scalars[here] = value.strip("\"'")
    parse.skipped_lists = skipped_lists  # type: ignore[attr-defined]
    return scalars


def effective(base: dict, overlay: dict) -> dict:
    """Helm 的 map 合并：overlay 的标量覆盖 base，键集取并集。"""
    out = dict(base)
    out.update(overlay)
    return out


def enabled_labels(scalars: dict) -> dict[str, str]:
    """{label: 值} —— 生效值里 suspend 为真的有哪几条（只看 SCOPES 内）。"""
    out = {}
    for path, value in scalars.items():
        if path[0] not in SCOPES or path[-1] != "suspend":
            continue
        if value.lower() in FALSY:
            out[".".join(path[:-1])] = value
    return out


def keys_under(scalars: dict, prefix: tuple[str, ...]) -> set[tuple[str, ...]]:
    """prefix 下一层的键（含更深层的键路径），用来找 overlay 里的幽灵键。"""
    return {p for p in scalars if p[: len(prefix)] == prefix and len(p) > len(prefix)}


def check(dirpath: Path, base_site: str) -> list[str]:
    base_path = dirpath / BASE
    overlay_paths = sorted(p for p in dirpath.glob("values-*.yaml")
                           if p.name != PRIVATE)
    if not base_path.is_file() or not overlay_paths:
        raise Unparseable(f"{dirpath} 缺 {BASE} 或 values-*.yaml")
    base = parse(base_path)
    problems: list[str] = []

    # 凭据 overlay 若写了 suspend，那条声明没有消费者看得见（它不是站点），
    # 会让人误以为「在 private 里关掉了」—— 直接判红，不许当无事发生。
    private = dirpath / PRIVATE
    if private.is_file():
        for label in enabled_labels(effective(base, parse(private))):
            if label in enabled_labels(parse(private)):
                problems.append(
                    f"凭证文件决定调度 {PRIVATE}: {label} 在这里被写成 suspend=false → "
                    f"站点 overlay 才是「谁跑」的声明面，凭据文件只放内网端点/账号标识")

    sites: dict[str, dict] = {base_site: base}
    for p in overlay_paths:
        site = p.stem.removeprefix("values-")
        sites[site] = effective(base, parse(p))

    # R2 幽灵键：overlay 里写了 base 没有的键 = 渲染出来没人读。
    for p in overlay_paths:
        overlay = parse(p)
        for prefix in (("legalSources", "sources"), ("legalSources", "loaders")):
            known = {k[len(prefix)] for k in keys_under(base, prefix)}
            ghost = {k[len(prefix)] for k in keys_under(overlay, prefix)} - known
            for g in sorted(ghost):
                problems.append(
                    f"R2 幽灵键 {p.name}: {'.'.join(prefix)}.{g} 在 {BASE} 里不存在"
                    f"（渲染出来没有任何模板读它）→ 改对键名，或先把它加进 {BASE}"
                )
        for path in overlay:
            if path[0] in SCOPES and path not in base and len(path) > 1:
                problems.append(
                    f"R2 幽灵键 {p.name}: {'.'.join(path)} 在 {BASE} 里不存在 → "
                    f"改对键名，或先把它加进 {BASE}"
                )

    # R1 同时点亮。
    live: dict[str, list[str]] = {}
    for site, scalars in sites.items():
        for label in enabled_labels(scalars):
            live.setdefault(label, []).append(site)
    for label, where in sorted(live.items()):
        if len(where) > 1:
            problems.append(
                f"R1 同时点亮 {label}: {' + '.join(where)} 都是 suspend=false → "
                f"切换宿主必须**同一次改动**里两边一起翻（新站点 false + 旧站点 true），"
                f"只翻一侧就是两个执行者写同一张 crawl_runs"
            )
    return problems


def self_test() -> int:
    """证明每条规则都能红，且判不出不走绿。"""
    import tempfile

    base = """legalSources:
  sources:
    a-lib:
      name: a-crawl
      suspend: true
    b-lib:
      name: b-crawl
      suspend: false
  loaders:
    a-load:
      suspend: false
flkLawCrawl:
  suspend: false
"""
    cases = [
        (
            "R1 红：两个 overlay 同时点亮 b-lib",
            {"values.yaml": base,
             "values-s1.yaml": "legalSources:\n  sources:\n    b-lib:\n      suspend: false\n",
             "values-s2.yaml": "legalSources:\n  sources:\n    b-lib:\n      suspend: false\n"},
            "R1",
        ),
        (
            "R2 红：overlay 键在 base 里不存在",
            {"values.yaml": base,
             "values-s1.yaml": "legalSources:\n  sources:\n    b-libb:\n      suspend: false\n"},
            "R2",
        ),
        (
            # 继承陷阱：overlay 不提某个源 = 继承 base 的 suspend false。
            # 2026-11-14 的真实形态就是这一条（server1 overlay 只写自己要点亮的，
            # base 里点亮的 5 个 loader / report / flkLawCrawl 全被继承过去）。
            "R1 红：overlay 不写 = 继承 base 的点亮状态",
            {"values.yaml": base,
             "values-s1.yaml": "legalSources:\n  sources:\n    a-lib:\n      suspend: false\n"},
            "R1 同时点亮 legalSources.sources.b-lib",
        ),
        (
            # 合法形态：base 全灭，只有一处 overlay 逐条点亮。
            "绿：base 全灭，只有一个站点逐条点亮",
            {"values.yaml": base.replace("b-lib:\n      name: b-crawl\n      suspend: false",
                                         "b-lib:\n      name: b-crawl\n      suspend: true")
                               .replace("a-load:\n      suspend: false",
                                        "a-load:\n      suspend: true")
                               .replace("flkLawCrawl:\n  suspend: false",
                                        "flkLawCrawl:\n  suspend: true"),
             "values-s1.yaml": "legalSources:\n  sources:\n    b-lib:\n      suspend: false\n",
             "values-s2.yaml": "legalSources:\n  sources:\n    a-lib:\n      suspend: false\n"},
            None,
        ),
    ]
    failures = 0
    for name, files, expect in cases:
        with tempfile.TemporaryDirectory() as td:
            for fn, text in files.items():
                (Path(td) / fn).write_text(text, encoding="utf-8")
            try:
                problems = check(Path(td), "master")
            except Unparseable as err:
                print(f"✗ {name}: 判不出（{err}）")
                failures += 1
                continue
            hit = [p for p in problems if expect and p.startswith(expect)] if expect else problems
            if expect and not hit:
                print(f"✗ {name}: 期望 {expect} 命中，实际 {problems or '无'}")
                failures += 1
            elif not expect and problems:
                print(f"✗ {name}: 期望全过，实际 {problems}")
                failures += 1
            else:
                print(f"✓ {name}")
    # 判不出：缺 base
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "values-s1.yaml").write_text("a: b\n", encoding="utf-8")
        try:
            check(Path(td), "master")
            print("✗ 判不出：缺 values.yaml 却退 0")
            failures += 1
        except Unparseable:
            print("✓ 判不出：缺 values.yaml → EXIT 2")
    print("SELF-TEST", "PASS" if not failures else f"FAIL({failures})")
    return 0 if not failures else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent),
                    help="chart 目录（默认本脚本的父目录）")
    ap.add_argument("--base-site", default="xinru-master",
                    help="values.yaml 对应的站点名（默认 xinru-master，见 APPLY-NOTES.md）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    try:
        problems = check(Path(args.dir), args.base_site)
    except Unparseable as err:
        print(f"✗ 判不出：{err}")
        return 2
    if not problems:
        print(f"✓ 站点互斥闸通过：{args.dir}")
        return 0
    print(f"✗ 站点互斥闸命中 {len(problems)} 条：")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
