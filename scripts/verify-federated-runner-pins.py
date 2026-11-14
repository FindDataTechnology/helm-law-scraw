#!/usr/bin/env python3
"""联邦出片 pin 闸：dispatcher 能 spawn 的镜像必须等于 chart 钉的那一版。

抓的是什么
----------
`crawl_sources.runner_image`（kind='federated'）是 **chart 镜像的手抄副本**：
`dispatch.sync_sources` 只 owns site/schedule/enabled/auth_profile/last_commit，
而且**整段跳过 federated 行**（`continue  # registered federated member:
not manifest-owned`）。于是副本一旦抄下来就没人再对齐——除非有人手工改。

这条副本已经在 2026-10-14 咬过一次：当时 6 个法律爬虫钉在 `sha-3ca3e8b`
（hkccr 有、ccr 已被逐出，而节点只从 ccr 拉），`rmfyalk-case-crawl` 钉在
`sha-9eb5c72`（两个注册表都没有）。alembic `0011_federated_runner_tag` 把它们
收敛到当年那条 anchored tag，并把规则写进 docstring：
**任何 dispatcher 能 spawn 的镜像都必须存在于 ccr 且被 anchor**。

而 2026-11-14 实测：7 行全部钉在 `sha-e9c1c11`，chart / 线上 CronJob 已是
`sha-c33bf67` —— 又一次漂移，且这次是**手工改上去的**（0011 的锚点是 `sha-b63d0d1`，
DB 里却是 e9c1c11，中间没有任何提交记录）。后果不是宕机，是「异常触发跑起来的是
五代前的代码」：镜像自报 image_tag、S3 写预算、报告 coverage 字段都不在那一版里。

判据（三条，都不猜）
--------------------
R1 对齐：chart 渲染出的同名 CronJob 的镜像 MUST 等于 `crawl_sources.runner_image`。
   不一致即 FAIL，点名两侧 tag 与改法（新增 alembic revision，别手工 UPDATE ——
   上一次手工改就没留出处，正是这次漂移的来源）。
R2 无主：chart 不渲染的 federated 源（`guide-cases-crawl`、`wenshu-crawl`）
   **只报事实、不计命中**——没有所有者就没有可比的另一侧，判红会变成常年红的闸。
R3 判不出：没有 `FD_CRAWL_DB_URL`、没有 helm、渲染失败、0 条 federated 行
   ⇒ EXIT 2。**0 个校验对象不许读成「都对齐」**。

用法
----
    python3 scripts/verify-federated-runner-pins.py --rows /tmp/rows.json
    python3 scripts/verify-federated-runner-pins.py --rows … --rendered /tmp/jobs.json
    python3 scripts/verify-federated-runner-pins.py --self-test

退出码：0 全对齐（含 R2 事实行）；1 有分叉；2 判不出。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CHART = Path(__file__).resolve().parent.parent
#: federated 行里 chart 明确不管的那几个——没有所有者就没有另一侧可比。
UNOWNED_NOTE = "chart 不渲染该对象（APPLY-NOTES「Not charted on purpose」/独立镜像）"


class Unjudgeable(Exception):
    """判不出（缺输入、渲染失败、零校验对象）——不是通过。"""


def render_cronjobs(chart: Path) -> dict[str, str]:
    """跑 chart 自己的 render 配方，拿 {CronJob 名: 镜像}。

    用 `make render` 而不是自己拼 helm 参数：Makefile 里有带外私有值的占位兜底
    （缺 values-private.yaml 也能渲染），自己拼就会在两台机器上渲染出不同结果。
    """
    try:
        out = subprocess.run(["make", "-s", "render"], cwd=chart, capture_output=True,
                             text=True, timeout=180)
    except FileNotFoundError as err:
        raise Unjudgeable(f"没有 make: {err}") from err
    except subprocess.TimeoutExpired as err:
        raise Unjudgeable("make render 超时") from err
    if out.returncode != 0:
        raise Unjudgeable(f"make render 失败: {(out.stderr or out.stdout).strip()[:300]}")

    jobs: dict[str, str] = {}
    for block in out.stdout.split("\n---"):
        if "kind: CronJob" not in block:
            continue
        name = re.search(r"^\s*name: (\S+)", block, re.M)
        image = re.search(r"^\s*image: (\S+)", block, re.M)
        if name and image:
            # render 里 image 可能带引号（`image: "ccr/…:sha-x"`），去掉再比
            jobs[name.group(1)] = image.group(1).strip("\"'")
    if not jobs:
        raise Unjudgeable("render 输出里一个 CronJob 都没解析到")
    return jobs


def load_rows(path: str) -> list[dict]:
    """读一份 [{source,runner_image}] JSON。

    为什么不在脚本里直连库：本机没有 psql（实测 `command -v psql` → 空），而
    「把一个 DSN 传进脚本」要么写在命令行（进 ps），要么要求调用方先 export——
    两种都把凭据面摊开。这里改成**纯比对器**，行数据由一次性的查询 Pod 产：

        kubectl -n scraw apply -f /tmp/runs-pod.yaml   # 同族用法见记忆「查询 Pod 模式」
        kubectl -n scraw logs runs | tail -1 > /tmp/rows.json

    Pod 里跑的是：
        select source, coalesce(runner_image,'') img
        from crawl_sources where kind='federated' order by source
    并 `console.log(JSON.stringify(rows))`。
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise Unjudgeable(f"读不了 {path}: {err}") from err
    if not isinstance(raw, list):
        raise Unjudgeable(f"{path} 不是数组")
    rows = []
    for r in raw:
        if not isinstance(r, dict) or not r.get("source"):
            raise Unjudgeable(f"{path} 里有条目缺 source")
        rows.append({"source": str(r["source"]),
                     "runner_image": str(r.get("img") or r.get("runner_image") or "").strip()})
    return rows


def compare(rows: list[dict], rendered: dict[str, str]) -> tuple[list[str], list[str]]:
    """返回 (命中, 事实行)。"""
    if not rows:
        raise Unjudgeable("0 条 federated 行——什么都没比，不许读成「都对齐」")
    problems: list[str] = []
    facts: list[str] = []
    for row in rows:
        src, pin = row["source"], row["runner_image"]
        want = rendered.get(src)
        if want is None:
            facts.append(f"R2 无主 {src}: {UNOWNED_NOTE}（DB pin={pin or '<空>'}）")
            continue
        if not pin:
            problems.append(f"R1 未钉 {src}: chart 渲染 {want.split('/')[-1]}，"
                            f"DB 里 runner_image 为空 → dispatcher 造 Job 时没有镜像可用")
            continue
        if pin != want:
            problems.append(
                f"R1 不对齐 {src}: DB={pin.split('/')[-1]} ≠ chart={want.split('/')[-1]} → "
                f"dispatcher 造出的 Job 会跑与线上不同的一代代码；改法=新增 alembic revision "
                f"按 chart 现值收敛（别手工 UPDATE：上一次手工改没留出处，正是这次漂移的来源）")
    return problems, facts


def self_test() -> int:
    rendered = {"a-crawl": "ccr/x/fd-law-data:sha-new", "b-crawl": "ccr/x/fd-law-data:sha-new"}
    cases = [
        ("R1 红：DB 落后 chart",
         [{"source": "a-crawl", "runner_image": "ccr/x/fd-law-data:sha-old"}], "R1"),
        ("R1 红：DB 未钉",
         [{"source": "a-crawl", "runner_image": ""}], "R1"),
        ("绿：全部对齐",
         [{"source": "a-crawl", "runner_image": "ccr/x/fd-law-data:sha-new"}], None),
        ("绿但报事实：chart 不渲染的源",
         [{"source": "zz-unowned", "runner_image": "ccr/x/y:sha-q"}], None),
    ]
    bad = 0
    for name, rows, expect in cases:
        try:
            problems, facts = compare(rows, rendered)
        except Unjudgeable as err:
            print(f"✗ {name}: 判不出（{err}）")
            bad += 1
            continue
        hit = [p for p in problems if expect and p.startswith(expect)] if expect else problems
        if expect and not hit:
            print(f"✗ {name}: 期望 {expect}，实际 {problems or '无'}")
            bad += 1
        elif not expect and problems:
            print(f"✗ {name}: 期望全过，实际 {problems}")
            bad += 1
        else:
            print(f"✓ {name}" + (f"（事实 {len(facts)} 条）" if facts else ""))
    try:
        compare([], rendered)
        print("✗ 判不出：0 条 federated 行却退 0")
        bad += 1
    except Unjudgeable:
        print("✓ 判不出：0 条 federated 行 → EXIT 2")
    print("SELF-TEST", "PASS" if not bad else f"FAIL({bad})")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rendered", help="离线：读一份 [{name,image}] JSON 而不是跑 make render")
    ap.add_argument("--rows", help="[{source,img}] JSON，来自一次性查询 Pod（见文件头）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    try:
        if args.rendered:
            rendered = {j["name"]: j["image"] for j in json.loads(Path(args.rendered).read_text())}
        else:
            rendered = render_cronjobs(CHART)
        if not args.rows:
            raise Unjudgeable("没有 --rows（行数据由一次性查询 Pod 产出，见文件头）")
        rows = load_rows(args.rows)
        problems, facts = compare(rows, rendered)
    except Unjudgeable as err:
        print(f"✗ 判不出：{err}")
        return 2
    for f in facts:
        print(f"  · {f}")
    if not problems:
        print(f"✓ 联邦 pin 与 chart 对齐（{len(rows)} 行，渲染 {len(rendered)} 个 CronJob）")
        return 0
    print(f"✗ 联邦 pin 命中 {len(problems)} 条：")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
