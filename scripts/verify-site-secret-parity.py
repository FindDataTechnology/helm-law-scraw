#!/usr/bin/env python3
"""站点凭据一致性闸：chart 引用的每个 secret 键，两个集群必须同值。

抓的是什么
----------
2026-11-14 切换试点时发现的那一类：**集群之间「能连」不等于「能用同一份凭据」**。
连通性探针证明的是网络与凭据**在探测的那一路**可用（我探的是 crawl 库
`fd_open_data` + `laws` 桶），完全看不出 load/report 走的是另一个库、另一份口令。

实测（同一时刻，两集群逐键 sha256 比对）：

    flk-law-pg-credentials   pg-password  master 3515c8f6… ≠ server1 d40c7c11…
    flk-embed-credentials    server1 上根本没有这个 secret
    flk-law-crawl-credentials  server1 是超集（dashed + UPPERCASE），master 只有 dashed

第一条直接解释了一批失败：server1 的 `*-load` 连续 10 轮
「用户 "postgres" Password 认证失败」——11-13 那次口令轮换只同步了一侧。
第二条意味着 `flk-law-embed` 搬到 server1 必然起不来。而这三条**在连通性探针里全绿**。

判据
----
从 chart 自己的 render 里取出被引用的 `(secret, key)` 对（`secretKeyRef` 与
`envFrom.secretRef` 都算），逐对在两集群上算 sha256：

R1 缺失：某个被引用的键在目标站点不存在 ⇒ FAIL（pod 会 CreateContainerConfigError，
   或更糟：`envFrom` 遇到不合法键名时静默什么都不注入）。
R2 不一致：两侧 sha256 不同 ⇒ FAIL，只打 8 位哈希与长度，**从不打印值**。
R3 判不出：render 失败、某集群取不到 secret 列表 ⇒ EXIT 2。

为什么只比「chart 引用的键」而不是整份 secret：两份 secret 的键集本来就会因为
`envFrom` 与显式 `secretKeyRef` 两种写法而分叉（实测 server1 是超集）；比全量会把
这种设计差异报成红。**只比 pod 真的会读的那几个键。**

用法
----
    python3 scripts/verify-site-secret-parity.py                      # master vs server1
    python3 scripts/verify-site-secret-parity.py --from master --to xinru-server1
    python3 scripts/verify-site-secret-parity.py --self-test

退出码：0 全部同值且两侧都有；1 有缺失/不一致；2 判不出。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

CHART = Path(__file__).resolve().parent.parent
NS = "scraw"


class Unjudgeable(Exception):
    """判不出（渲染失败/集群不可达/零引用）——不是通过。"""


def rendered_refs() -> set[tuple[str, str]]:
    """chart render 里被引用的 (secret, key) 对。envFrom 的 secretRef 只能给名字、
    给不出键，所以它单列成 ('name', '*') 由调用方按「存在」判。"""
    try:
        out = subprocess.run(["make", "-s", "render"], cwd=CHART,
                             capture_output=True, text=True, timeout=180)
    except (FileNotFoundError, subprocess.TimeoutExpired) as err:
        raise Unjudgeable(f"render 起不来: {err}") from err
    if out.returncode != 0:
        raise Unjudgeable(f"make render 失败: {(out.stderr or '').strip()[:300]}")

    refs: set[tuple[str, str]] = set()
    # secretKeyRef 块：name 在前、key 在后（chart 的实际写法）
    for m in re.finditer(r"secretKeyRef:\s*\n\s+name:\s*(\S+)\s*\n\s+key:\s*(\S+)", out.stdout):
        refs.add((m.group(1), m.group(2)))
    for m in re.finditer(r"secretKeyRef:\s*\n\s+key:\s*(\S+)\s*\n\s+name:\s*(\S+)", out.stdout):
        refs.add((m.group(2), m.group(1)))
    for m in re.finditer(r"-\s*secretRef:\s*\n\s+name:\s*(\S+)", out.stdout):
        refs.add((m.group(1), "*"))
    if not refs:
        raise Unjudgeable("render 里一个 secret 引用都没解析到")
    return refs


def secret_hashes(ctx: str) -> dict[str, dict[str, tuple[str, int]]]:
    """{secret: {key: (sha256[:8], bytes)}} —— 只回哈希与长度，不回值。"""
    out = subprocess.run(
        ["kubectl", "--context", ctx, "-n", NS, "get", "secrets", "-o", "json"],
        capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise Unjudgeable(f"{ctx} 取不到 secret: {(out.stderr or '').strip()[:200]}")
    try:
        items = json.loads(out.stdout).get("items", [])
    except ValueError as err:
        raise Unjudgeable(f"{ctx} 的 secret JSON 解析不了: {err}") from err
    table: dict[str, dict[str, tuple[str, int]]] = {}
    for it in items:
        name = it["metadata"]["name"]
        table[name] = {}
        for k, v in (it.get("data") or {}).items():
            raw = base64.b64decode(v)
            table[name][k] = (hashlib.sha256(raw).hexdigest()[:8], len(raw))
    return table


def compare(refs: set[tuple[str, str]], a: dict, b: dict,
            an: str, bn: str) -> tuple[list[str], list[str]]:
    if not refs:
        raise Unjudgeable("零引用——什么都没比，不许读成「都一致」")
    problems: list[str] = []
    notes: list[str] = []
    for secret, key in sorted(refs):
        if key == "*":
            have_a, have_b = secret in a, secret in b
            if not (have_a and have_b):
                miss = bn if have_a else an
                problems.append(f"R1 缺失 {secret}（envFrom 整份）: {miss} 上没有这个 secret")
            continue
        ha = (a.get(secret) or {}).get(key)
        hb = (b.get(secret) or {}).get(key)
        if ha is None and hb is None:
            problems.append(f"R1 缺失 {secret}/{key}: 两个集群都没有")
        elif ha is None:
            problems.append(f"R1 缺失 {secret}/{key}: {an} 没有（{bn} 有）")
        elif hb is None:
            problems.append(f"R1 缺失 {secret}/{key}: {bn} 没有（{an} 有）")
        elif ha[0] != hb[0]:
            problems.append(
                f"R2 不一致 {secret}/{key}: {an}={ha[0]}({ha[1]}B) ≠ {bn}={hb[0]}({hb[1]}B)"
                f" → 搬站点前必须对齐：这类差异不会在连通性探针里现形，只在真跑那一刻")
        else:
            notes.append(f"✓ {secret}/{key} 同值（{ha[0]}）")
    return problems, notes


def self_test() -> int:
    refs = {("s1", "k1"), ("s1", "k2"), ("s2", "*")}
    same = {"s1": {"k1": ("aaa", 8), "k2": ("bbb", 8)}, "s2": {"x": ("z", 1)}}
    cases = [
        ("绿：全部同值", same, same, None),
        ("R2 红：值不同", same,
         {"s1": {"k1": ("aaa", 8), "k2": ("ccc", 8)}, "s2": {"x": ("z", 1)}}, "R2"),
        ("R1 红：目标站点缺键", same,
         {"s1": {"k1": ("aaa", 8)}, "s2": {"x": ("z", 1)}}, "R1"),
        ("R1 红：目标站点缺整份 secret", same,
         {"s1": {"k1": ("aaa", 8), "k2": ("bbb", 8)}}, "R1"),
    ]
    bad = 0
    for name, a, b, expect in cases:
        problems, _ = compare(refs, a, b, "master", "server1")
        hit = [p for p in problems if expect and p.startswith(expect)] if expect else problems
        if expect and not hit:
            print(f"✗ {name}: 期望 {expect}，实际 {problems or '无'}")
            bad += 1
        elif not expect and problems:
            print(f"✗ {name}: 期望全过，实际 {problems}")
            bad += 1
        else:
            print(f"✓ {name}")
    try:
        compare(set(), {}, {}, "master", "server1")
        print("✗ 判不出：零引用却退 0")
        bad += 1
    except Unjudgeable:
        print("✓ 判不出：零引用 → EXIT 2")
    print("SELF-TEST", "PASS" if not bad else f"FAIL({bad})")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", default="xinru")
    ap.add_argument("--to", dest="dst", default="xinru-server1")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    try:
        if not args.self_test:
            pass
        refs = rendered_refs()
        if not refs:
            raise Unjudgeable("零引用")
        a = secret_hashes(args.src)
        b = secret_hashes(args.dst)
    except Unjudgeable as err:
        print(f"✗ 判不出：{err}")
        return 2
    problems, notes = compare(refs, a, b, args.src, args.dst)
    for n in notes:
        print(f"  {n}")
    if not problems:
        print(f"✓ 两站点凭据一致（{len(refs)} 个被引用的键）")
        return 0
    print(f"✗ 凭据不一致 {len(problems)} 条：")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
