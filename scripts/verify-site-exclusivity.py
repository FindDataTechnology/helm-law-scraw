#!/usr/bin/env python3
"""站点 overlay 互斥闸：同一个 CronJob 不许在两个站点同时点亮。

抓的是什么
----------
本 chart 用「base + 站点 overlay」表达「谁跑这条线」：
`values.yaml` 是 base（APPLY-NOTES 记为与 the master 线上收敛），
`values-<site>.yaml` 只覆写各源的 `suspend`。于是同一个源到底谁在跑，
由**两个文件各说一遍**——而没有任何东西比过这两句话。

2026-11-14 实历：`values-server1.yaml` 把 mfa-treaty / gov-rules /
party-regulation / ccdi 四个爬虫 + 五个 loader + report + flkLawCrawl 全写成
`suspend: false`，而同一时刻 the master 上这四只爬虫**正在跑**（且是当前镜像）。
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
    items: dict[tuple[str, ...], list[str]] = {}
    maps: set[tuple[str, ...]] = set()
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
            # list 不参与 map 比对。合法形态：`command:`/`args:`/`accessModes:`
            # 这类与「谁跑」无关的字段。但 `sources:`/`loaders:` 本身若变成
            # list（`- name: x`），键集比对就整体失效 ⇒ 那时判不出，不许静默跳过。
            here = tuple(k for _, k in stack)
            if not here or here[-1] in MUST_BE_MAP:
                raise Unparseable(
                    f"{path.name}:{lineno} {'.'.join(here) or '<root>'} 是 list；"
                    f"本闸按 map 比较，形态一变就判不出")
            item = line[1:].strip()
            # 记录**纯标量**列表项（`- party-regulation-library`）：R4 要读
            # `activeElsewhere`，只跳过不记录会让那条判据零覆盖却报绿。
            if item and ":" not in item and not item.startswith(("{", "[", "&", "*")):
                items.setdefault(here, []).append(item.strip("\"'"))
            else:
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
            maps.add(here)
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
    parse.items = items                  # type: ignore[attr-defined]
    parse.maps = maps                    # type: ignore[attr-defined]
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
    # parse() 的 items/maps/skipped_lists 是**模块级副作用**（下一次 parse 会覆盖），
    # 所以必须在这里立刻快照 base 的；等循环里 parse 过 overlay 再读就变成读 overlay 的。
    base_items = dict(getattr(parse, "items", {}))
    base_maps = set(getattr(parse, "maps", set()))
    base_skipped = list(getattr(parse, "skipped_lists", []))
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

    # R4 僵尸例外：`legalSources.activeElsewhere` 里的源名必须真的在某份站点
    # overlay 里 suspend=false。它是报告侧的「别把它算 paused」白名单 —— 列了却
    # 没人跑，则该源一旦断流，报告会说「合法暂停」而不是「断流」，把切换之后最该
    # 看见的失败形态长期遮住。所以这一条**计命中**（与「只报事实」相反）。
    #
    # 读的是 parse.items（列表项），不是 scalars：`activeElsewhere` 是 YAML 列表，
    # 只按 map 读会得到空集 —— 那是零覆盖，必须判不出，不许报绿。
    # 快照在 `base = parse(...)` 之后已取（见函数开头），这里只用局部变量。
    else_where = ("legalSources", "activeElsewhere")

    # 源名（报告的适配器名）→ 哪些站点让它真的跑起来了。
    # `lit_crawl_by_site` 只数**爬**（`legalSources.sources`），不数装载器：
    # 平台派发器拥有的是 crawl，loader 仍由 chart 跑（rmfyalk 就是这样：爬在平台、
    # 装在 master）。把 loader 算进来会让 R4b 对合法部署误报双执行者。
    lit_sources: set[str] = set()
    lit_by_site: dict[str, set[str]] = {site: set() for site in sites}
    lit_crawl_by_site: dict[str, set[str]] = {site: set() for site in sites}
    for site, scalars in sites.items():
        for label in enabled_labels(scalars):
            parts = label.split(".")
            if len(parts) != 3 or parts[0] != "legalSources":
                continue
            if parts[1] == "sources":
                lit_sources.add(parts[2])      # 源名就是 map 的键
                lit_by_site[site].add(parts[2])
                lit_crawl_by_site[site].add(parts[2])
            elif parts[1] == "loaders":
                src = scalars.get(("legalSources", "loaders", parts[2], "source"))
                if src:
                    lit_sources.add(src)
                    lit_by_site[site].add(src)

    if any("legalSources.activeElsewhere" in s for s in base_skipped):
        raise Unparseable(
            f"{BASE}: legalSources.activeElsewhere 写成了本脚本不解析的形态"
            f"（flow 序列 `[...]`）→ 判不出。改成逐行 `- 源名` 的 block 序列")
    if else_where in base_maps:
        names = base_items.get(else_where, [])
        if not names:
            raise Unparseable(
                f"{BASE}: legalSources.activeElsewhere 声明了却读不出任何条目 → "
                f"判不出（空清单与「读不到」表现相同，不许当成「没有例外」）")
        for name in sorted(set(names)):
            if name not in lit_sources:
                problems.append(
                    f"R4 僵尸例外 legalSources.activeElsewhere: 列了 {name}，但没有任何"
                    f"站点 overlay 让它 suspend=false → 它现在谁都不跑，留在白名单里"
                    f"会让报告把它判成「合法暂停」而不是「断流」；删掉这一条")

    # R4b `platformDispatched`：由**平台派发器**执行的源。它同样被排除出报告的
    # 暂停名单（理由同 R4：chart 关着 ≠ 没人跑），但校验方向相反 ——
    #   · activeElsewhere 的名字必须**被某份 overlay 点亮**，
    #   · platformDispatched 的名字必须**在每一份 overlay 里都 suspend**，
    #     否则 chart 的 CronJob 与平台派发器会同时跑同一个源 = 两个执行者。
    # 2026-11-14 实历（这条例外存在的理由）：rmfyalk 的 chart CronJob 自建成起
    # 就 suspend（平台派发），于是它一直躺在报告的暂停名单里；源从 11-05 起零产出，
    # 日报在 11-13T20:12 出片后由红转绿，而**那一刻没有任何数据进库**。
    dispatcher = ("legalSources", "platformDispatched")
    if any("legalSources.platformDispatched" in s for s in base_skipped):
        raise Unparseable(
            f"{BASE}: legalSources.platformDispatched 写成了本脚本不解析的形态"
            f"（flow 序列 `[...]`）→ 判不出。改成逐行 `- 源名` 的 block 序列")
    if dispatcher in base_maps:
        names = base_items.get(dispatcher, [])
        if not names:
            raise Unparseable(
                f"{BASE}: legalSources.platformDispatched 声明了却读不出任何条目 → "
                f"判不出（空清单与「读不到」表现相同）")
        overlap = set(names) & set(base_items.get(else_where, []))
        for name in sorted(overlap):
            problems.append(
                f"R4b 同一条例同时出现在 activeElsewhere 与 platformDispatched: {name}"
                f" → 一份源只能有一个「谁在跑」的答案，删掉错的那一处")
        for name in sorted(set(names) - overlap):
            lit_at = sorted(s for s, lit in lit_crawl_by_site.items() if name in lit)
            if lit_at:
                problems.append(
                    f"R4b platformDispatched 的爬被站点点亮: {name} 在 "
                    f"{', '.join(lit_at)} 上 `legalSources.sources` 是 suspend=false → "
                    f"平台派发器与 chart 会同时跑同一个爬（两个执行者、两份 crawl_runs"
                    f"行）；把它从那份 overlay 里关掉，或从 platformDispatched 里摘出来"
                    f"（装载器仍归 chart，不算冲突）")
    return problems
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
    # R4/R4b 的独立基线：全灭 + activeElsewhere 只列 b-lib（b 由别站点跑）。
    r4_base = """legalSources:
  activeElsewhere:
    - b-lib
  sources:
    a-lib:
      name: a-crawl
      suspend: true
    b-lib:
      name: b-crawl
      suspend: true
  loaders:
    a-load:
      suspend: true
flkLawCrawl:
  suspend: true
"""
    # R4b 的基线：全灭 + platformDispatched 只列 a-lib（a 由平台派发）。
    r4b_base = """legalSources:
  platformDispatched:
    - a-lib
  sources:
    a-lib:
      name: a-crawl
      suspend: true
    b-lib:
      name: b-crawl
      suspend: true
  loaders:
    a-load:
      suspend: true
flkLawCrawl:
  suspend: true
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
        (
            # R4 用的独立基线：base 全灭，`activeElsewhere` 只列 b-lib。
            # 不复用上面的 base —— 那份把 a-load/flkLawCrawl 点亮着，任何单站点
            # overlay 都会继承出 R1，用例就证不到 R4。
            "绿：activeElsewhere 的源确实在别的站点点亮",
            {"values.yaml": r4_base,
             "values-s1.yaml": "legalSources:\n  sources:\n    b-lib:\n      suspend: false\n"},
            None,
        ),
        (
            # R4 红：白名单留着，但没人点亮它 ⇒ 报告会把它判成「合法暂停」。
            "R4 红：activeElsewhere 里是僵尸例外（谁都不跑）",
            {"values.yaml": r4_base,
             "values-s1.yaml": "legalSources:\n  sources:\n    a-lib:\n      suspend: false\n"},
            "R4",
        ),
        (
            # R4b 绿：平台派发的源在所有站点都关着（chart 只当手工兜底）。
            "R4b 绿：platformDispatched 的源在所有站点都 suspend",
            {"values.yaml": r4b_base,
             "values-s1.yaml": "legalSources:\n  sources:\n    b-lib:\n      suspend: false\n"},
            None,
        ),
        (
            # R4b 红：某个站点点亮了它 ⇒ chart 与平台派发器同时跑同一个源。
            "R4b 红：platformDispatched 被站点点亮（双执行者）",
            {"values.yaml": r4b_base,
             "values-s1.yaml": "legalSources:\n  sources:\n    a-lib:\n      suspend: false\n"},
            "R4b platformDispatched 的爬被站点点亮",
        ),
        (
            # R4b 红：同一名字两处都声明 ⇒ 「谁在跑」有两个答案。
            "R4b 红：同时进了 activeElsewhere 与 platformDispatched",
            {"values.yaml": r4b_base.replace(
                "  platformDispatched:\n    - a-lib\n",
                "  platformDispatched:\n    - a-lib\n  activeElsewhere:\n    - a-lib\n"),
             "values-s1.yaml": "legalSources:\n  sources:\n    a-lib:\n      suspend: false\n"},
            "R4b 同一条例同时出现在",
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
    # 判不出：activeElsewhere / platformDispatched 写成 flow 序列或声明为空
    # （本脚本不解析 ⇒ 不许静默当成「没有例外」）
    for name, text in (
        ("activeElsewhere 写成 flow 序列",
         r4_base.replace("  activeElsewhere:\n    - b-lib\n", "  activeElsewhere: [b-lib]\n")),
        ("activeElsewhere 声明了但为空",
         r4_base.replace("  activeElsewhere:\n    - b-lib\n", "  activeElsewhere:\n")),
        ("platformDispatched 写成 flow 序列",
         r4b_base.replace("  platformDispatched:\n    - a-lib\n", "  platformDispatched: [a-lib]\n")),
        ("platformDispatched 声明了但为空",
         r4b_base.replace("  platformDispatched:\n    - a-lib\n", "  platformDispatched:\n")),
    ):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "values.yaml").write_text(text, encoding="utf-8")
            (Path(td) / "values-s1.yaml").write_text(
                "legalSources:\n  sources:\n    b-lib:\n      suspend: false\n", encoding="utf-8")
            try:
                check(Path(td), "master")
                print(f"✗ 判不出：{name} 却退 0")
                failures += 1
            except Unparseable:
                print(f"✓ 判不出：{name} → EXIT 2")
    print("SELF-TEST", "PASS" if not failures else f"FAIL({failures})")
    return 0 if not failures else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent),
                    help="chart 目录（默认本脚本的父目录）")
    ap.add_argument("--base-site", default="the master",
                    help="values.yaml 对应的站点名（默认 the master，见 APPLY-NOTES.md）")
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
