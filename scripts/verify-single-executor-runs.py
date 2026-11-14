#!/usr/bin/env python3
"""单执行者闸（行为侧）：同一个源在一个排期窗内只许有一条 success。

抓的是什么
----------
`verify-site-exclusivity.py` 判的是**声明**（两份 values 里谁写了 suspend=false）；
这条判的是**行为**（数据库里到底几个执行者真跑完了）。两者不可互相替代：

* 声明侧全绿也可以双跑——只要有一侧的 CronJob 对象是旧的/手工 apply 的，
  或者切换时只翻了一边而清单后来被人改回去。2026-11-14 之前的 server1 正是
  这种情况：`values-server1.yaml` 把四个爬虫都写成活，而 master 上它们也在跑。
* 行为侧的证据只在**两侧 pod 都真起来**时才留下。11-12 之前 server1 侧一律
  `Failed 0/1`（pod 没起来、不写行），所以双跑这件事长期不可见——这不是
  「没发生」，是「没留痕」。

`crawl_runs` 里**没有站点列**（2026-11-14 实测列集：id/source/kind/status/
started_at/finished_at/rows_written/error_head/commit_sha/image_tag/created_at/
cancel_requested/pending_run_id/identity_alias/metrics/outcome/error_class/
parse_error，且 `metrics` 为空）。所以重复执行只能靠两件事认出来：**同源同窗
两条 success**（这条闸），以及**两条的 image_tag 不同**（说明是两代代码 =
两处部署）。一旦两站点对齐到同一 tag，tag 就再也分不出来——所以主判据必须是
「一个窗内只有一条 success」，不能依赖 tag。

判据
----
R1 双成功（FAIL）：同一 source，两条 `success` 的 started_at 相距 ≤ `--window-min`
   （默认 30 分钟）。一个排期窗内两个执行者都跑完 ⇒ 同一份 laws 行被写两遍。
   点名两个 run id、两个时刻、两个 tag。
R2 重复执行者伤亡（只报事实，不计命中）：同一 source，一条 success 与一条 failed
   相距 ≤ 窗且 image_tag 不同 ⇒ 那条失败**不是源坏**，是「另一个执行者已经在
   跑同一件事」的副作用（2026-11-14 解释 rmfyalk-case-load 十条失败用的就是这条）。
   只报事实的理由：同一窗口内换片重试（chart 滚动）也会呈现这个形状，归属要人判。
R3 判不出（EXIT 2）：零行、缺 source/status/started_at、时间戳解析不了、
   `--since` 之后一行不剩。**0 个校验对象不许读成「没有重复」。**

为什么窗口取 30 分钟而不是「按排期算」：本 chart 全部 CronJob 的最小间隔是
小时级（`flk-law-backfill` 是 `0 */4 * * *`，其余日跑），所以 30 分钟的窗**不会**
把两个合法的相邻排期配成一对；而双跑的两条通常在秒级到分钟级内。真要接更密的
排期，先把这个前提改掉（用 `--window-min` 压到间隔的一半以下）。

用法
----
行数据由一次性查询 Pod 产出（本机没有 psql，也不该把 DSN 摊进命令行）：

    kubectl -n scraw create configmap qruns \\
      --from-file=single-executor-runs.mjs=scripts/single-executor-runs.mjs
    kubectl -n scraw apply -f /tmp/runs-pod.yaml       # 见 scripts/single-executor-runs.mjs 头注
    kubectl -n scraw logs runs | tail -1 > /tmp/rows.json
    make verify-runs ROWS=/tmp/rows.json SINCE=2026-11-14T05:00:00Z

    python3 scripts/verify-single-executor-runs.py --rows /tmp/rows.json --self-test
    python3 scripts/verify-single-executor-runs.py --rows … --window-min 10 --since …

`--since` 做的是「切换之后才判」：历史重复（切换前那些轮）不该让闸常年红，
但也不许被静默丢掉——被过滤掉的行会打印计数。

退出码：0 全过（含 R2 事实行）；1 有 R1 命中；2 判不出。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: 一个排期窗内允许的 success 条数上限。
MAX_SUCCESS_PER_WINDOW = 1


class Unjudgeable(Exception):
    """判不出（缺输入、零行、时间戳坏）——不是通过。"""


def _ts(value: str) -> datetime:
    """解析 ISO 8601。无时区按 UTC 处理并**留下痕迹**（不许悄悄本地化）。

    Postgres 返回的是带 Z 或 +00:00 的；测试数据里手写的也走这里。带 `+08:00`
    的会被正确换算——绝不按「本机时区」猜。
    """
    txt = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(txt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize(raw: object, where: str = "<rows>") -> list[dict]:
    """把原始条目规范成 {id, source, status, started_at: datetime, image_tag}。

    self-test 与真实路径**走同一个函数**——否则自证的是另一份逻辑
    （自测绿而线上红、或反之，本仓已经踩过）。
    """
    if not isinstance(raw, list):
        raise Unjudgeable(f"{where} 不是数组")
    path = where
    rows, seen = [], set()
    for r in raw:
        if not isinstance(r, dict):
            raise Unjudgeable(f"{path} 里有非对象条目")
        for k in ("source", "status", "started_at"):
            if not r.get(k):
                raise Unjudgeable(f"{path} 里有条目缺 {k}: {str(r)[:120]}")
        rid = str(r.get("id") or f"{r['source']}@{r['started_at']}")
        if rid in seen:      # 同一份行贴了两遍＝调用方出错，不是两条执行
            continue
        seen.add(rid)
        try:
            started = _ts(r["started_at"])
        except ValueError as err:
            raise Unjudgeable(f"{path} 里 {rid} 的 started_at 解析不了: {err}") from err
        rows.append({
            "id": rid,
            "source": str(r["source"]),
            "status": str(r["status"]).strip().lower(),
            "started_at": started,
            "image_tag": str(r.get("image_tag") or "").strip(),
        })
    return rows


def load_rows(path: str) -> list[dict]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise Unjudgeable(f"读不了 {path}: {err}") from err
    return normalize(raw, path)


def compare(rows: list[dict], window: timedelta) -> tuple[list[str], list[str], list[str]]:
    """返回 (R1 命中, R2 事实, 每源摘要)。"""
    if not rows:
        raise Unjudgeable("0 行——什么都没比，不许读成「没有重复」")
    problems: list[str] = []
    facts: list[str] = []
    summary: list[str] = []
    by_source: dict[str, list[dict]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(r)

    for source in sorted(by_source):
        runs = sorted(by_source[source], key=lambda r: r["started_at"])
        succ = [r for r in runs if r["status"] == "success"]
        summary.append(f"{source}: {len(runs)} 行 / {len(succ)} success")
        # R1：任意两条 success 落在同一个窗内
        for i in range(len(succ)):
            for j in range(i + 1, len(succ)):
                gap = succ[j]["started_at"] - succ[i]["started_at"]
                if gap > window:
                    continue
                a, b = succ[i], succ[j]
                tag_a = a["image_tag"].split(":")[-1] or "<空>"
                tag_b = b["image_tag"].split(":")[-1] or "<空>"
                same = (a["image_tag"] == b["image_tag"])
                problems.append(
                    f"R1 双成功 {source}: run#{a['id']}@{a['started_at']:%m-%dT%H:%M:%SZ}"
                    f"({tag_a}) 与 run#{b['id']}@{b['started_at']:%m-%dT%H:%M:%SZ}({tag_b})"
                    f" 相距 {int(gap.total_seconds())}s ≤ {int(window.total_seconds())}s"
                    + ("——**tag 相同，只能靠行数认出来**（两站点已对齐到同一片）" if same else
                       "——tag 不同 ⇒ 两处部署各跑了一次")
                    + "；改法=确认哪个站点该活，另一侧 suspend:true（两侧同一次改动里翻）")
        # R2：成功+失败、异片、同窗。按「成功的那个 run + 异片 tag」聚合成一行——
        # 逐条打会把一次双跑的重试链（backoffLimit 3 就有 4 条）铺成几十行，噪声会把
        # 唯一那条真信号淹掉（本仓在卷保护闸上踩过同一个形状）。
        for s in succ:
            tally: dict[str, int] = {}
            for f in runs:
                if f["status"] != "failed":
                    continue
                if abs((f["started_at"] - s["started_at"]).total_seconds()) > window.total_seconds():
                    continue
                if not f["image_tag"] or f["image_tag"] == s["image_tag"]:
                    continue    # 同片＝换片/重试链，不是双执行者
                tag = f["image_tag"].split(":")[-1]
                tally[tag] = tally.get(tag, 0) + 1
            if tally:
                detail = "、".join(f"{t}×{n}" for t, n in sorted(tally.items()))
                facts.append(
                    f"R2 重复执行者伤亡 {source}: run#{s['id']}@{s['started_at']:%m-%dT%H:%M:%SZ}"
                    f" 成功（{s['image_tag'].split(':')[-1]}）的同窗内还有异片失败 {detail} ⇒ "
                    f"那些失败不是源坏，是另一个执行者已在跑同一件事")
    return problems, facts, summary


def self_test() -> int:
    def row(rid, status, when, tag="ccr/x/fd-law-data:sha-a"):
        return {"id": rid, "source": "s", "status": status,
                "started_at": when, "image_tag": tag}

    win = timedelta(minutes=30)
    cases = [
        ("绿：每轮一条 success",
         [row(1, "success", "2026-11-13T19:40:00Z"), row(2, "success", "2026-11-14T19:40:00Z")],
         None),
        ("R1 红：两条 success 相距 12s",
         [row(1, "success", "2026-11-13T19:40:00Z"),
          row(2, "success", "2026-11-13T19:40:12Z", "ccr/x/fd-law-data:sha-b")], "R1"),
        ("R1 红：同片两条 success（tag 一样也要红）",
         [row(1, "success", "2026-11-13T19:40:00Z"),
          row(2, "success", "2026-11-13T19:41:00Z")], "R1"),
        ("绿：两条 success 隔 4 小时＝两个排期",
         [row(1, "success", "2026-11-13T19:40:00Z"),
          row(2, "success", "2026-11-13T23:40:00Z")], None),
        ("绿：失败重试链里只有一条 success",
         [row(1, "failed", "2026-11-13T19:40:00Z"),
          row(2, "failed", "2026-11-13T19:43:00Z"),
          row(3, "success", "2026-11-13T19:49:00Z")], None),
        ("R2 事实：成功+异片失败同窗",
         [row(1, "failed", "2026-11-13T19:40:00Z", "ccr/x/fd-law-data:sha-b"),
          row(2, "success", "2026-11-13T19:40:30Z")], None),
    ]
    bad = 0
    for name, rows, expect in cases:
        try:
            problems, facts, _ = compare(normalize(rows), win)
        except Unjudgeable as err:
            print(f"✗ {name}: 判不出（{err}）")
            bad += 1
            continue
        hit = [p for p in problems if p.startswith(expect)] if expect else problems
        if expect and not hit:
            print(f"✗ {name}: 期望 {expect}，实际 {problems or '无'}")
            bad += 1
        elif not expect and problems:
            print(f"✗ {name}: 期望全过，实际 {problems}")
            bad += 1
        else:
            print(f"✓ {name}" + (f"（事实 {len(facts)} 条）" if facts else ""))

    # R2 必须在这个形态下真的报出来（上一个 case 只判「不红」，这里判「有事实」）
    _, facts, _ = compare(normalize([
        row(1, "failed", "2026-11-13T19:40:00Z", "ccr/x/a:sha-b"),
        row(2, "success", "2026-11-13T19:40:30Z")]), win)
    if not any(f.startswith("R2") for f in facts):
        print("✗ R2 事实：期望报出「异片同窗」，实际没报")
        bad += 1
    else:
        print("✓ R2 事实：异片同窗真的报出来")

    # 同片失败不许进 R2（否则每轮重试都变成噪声）
    _, facts2, _ = compare(normalize([
        row(1, "failed", "2026-11-13T19:40:00Z"),
        row(2, "success", "2026-11-13T19:40:30Z")]), win)
    if facts2:
        print(f"✗ R2 边界：同片失败被报成伤亡（{facts2[0][:60]}）")
        bad += 1
    else:
        print("✓ R2 边界：同片失败不报")

    for label, rows in (("零行", []),
                        ("时间戳坏", [{"id": 1, "source": "s", "status": "success",
                                    "started_at": "昨天", "image_tag": ""}])):
        try:
            compare(normalize(rows), win)
            print(f"✗ 判不出：{label} 却退 0")
            bad += 1
        except Unjudgeable:
            print(f"✓ 判不出：{label} → EXIT 2")
    print("SELF-TEST", "PASS" if not bad else f"FAIL({bad})")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", help="[{id,source,status,started_at,image_tag}] JSON（查询 Pod 产出）")
    ap.add_argument("--window-min", type=int, default=30,
                    help="同窗阈值（默认 30；必须小于最小排期间隔的一半）")
    ap.add_argument("--since", help="只看这个时刻之后的行（ISO 8601）；切换后首跑用它")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.rows:
        print("✗ 判不出：没有 --rows（行数据由一次性查询 Pod 产出，见 scripts/single-executor-runs.mjs）")
        return 2
    try:
        rows = load_rows(args.rows)
        if args.since:
            try:
                since = _ts(args.since)
            except ValueError as err:
                raise Unjudgeable(f"--since 解析不了: {err}") from err
            before = len(rows)
            rows = [r for r in rows if r["started_at"] >= since]
            print(f"  · --since {since:%Y-%m-%dT%H:%M:%SZ}：过滤掉 {before - len(rows)} 行历史")
        problems, facts, summary = compare(rows, timedelta(minutes=args.window_min))
    except Unjudgeable as err:
        print(f"✗ 判不出：{err}")
        return 2

    for s in summary:
        print(f"  · {s}")
    for f in facts:
        print(f"  · {f}")
    if not problems:
        print(f"✓ 单执行者（{len(rows)} 行，窗 {args.window_min} 分钟）")
        return 0
    print(f"✗ 一个排期窗内出现 {len(problems)} 组重复执行：")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
