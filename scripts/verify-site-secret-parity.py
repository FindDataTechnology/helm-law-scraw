#!/usr/bin/env python3
"""站点凭据闸：**该站点上会跑的对象**引用的每个键，都必须在该站点存在且能用。

抓的是什么
----------
2026-11-14 切换试点时发现的那一类：**集群之间「能连」不等于「能用同一份凭据」**。
连通性探针证明的是网络与凭据**在探测的那一路**可用（我探的是 crawl 库
`fd_open_data` + `laws` 桶），完全看不出 load/report 走的是另一个库、另一份口令。
实测：`flk-law-pg-credentials/pg-password` 两站点不同 ⇒ server1 的 `*-load`
连续 10 轮「用户 postgres Password 认证失败」（11-13 那次口令轮换只同步了一侧）。

判据（2026-11-14 重写：从「全量逐键比」改成「按必需集比」）
--------------------------------------------------------
必需集按**站点**求，取两路的并集：

1. **线上在跑的对象** —— 该集群 `scraw` 里 `suspend=false` 的 CronJob，加上
   副本数 >0 的 Deployment/StatefulSet（Deployment 没有 suspend，只能看副本）。
   不把 Job 算进来：一次性 Job 是瞬时形态，它引用过的 secret 不构成长期义务。
   这一路回答「**现在就会起不来的**」——它抓到了 11-13 那 10 轮失败，因为当时
   server1 的 load 对象是活的（overlay 写 suspend 也没用，线上才是事实）。
2. **该站点渲染里点亮的对象** —— `values.yaml`（base=xinru-master）与
   `values-server1.yaml`（overlay）各自渲染后 `suspend=false` 的那批。
   这一路回答「**下一次 apply 之后会起不来的**」，也就是切换前置检查。

R1 缺失（FAIL）：某键在站点 S 的必需集里，而 S 上没有这个 secret/键。
   旧版把「两站点都必须有」当判据，于是 `flk-embed-credentials`（只有 xinru 的
   `flk-law-embed` 在用、server1 侧 embed 挂起）被报成红 —— 那是在要求一份
   **永远不会被读**的凭据。现在它在 server1 不在必需集里，自然不判；而一旦有人把
   embed 在 server1 点亮，必需集立刻包含它、闸立刻红 —— 这正是切换前必须知道的事。
R2 不一致（FAIL）：同一键在**两个站点的必需集里都有**且取值不同。
   只对「两边都真的要用」的键要同值：一边根本不用时，两边取值不同不构成风险。
R3 已裁决（只报事实）：R2 的例外，逐条登记在 `KNOWN_DIVERGENCE`，**必须带解除条件**，
   仍逐条打印、不计 EXIT。别为了让闸变绿往里加。
R4 只一侧必需（只报事实）：两侧都有该键但只有一边有对象用它，且取值不同。
R5 判不出（EXIT 2）：集群读不到、渲染失败、某站点必需集为空。
   「什么都没比」不许读成「都一致」。

只打 8 位哈希与长度，**从不打印值**。

为什么只比「被引用的键」而不是整份 secret：两份 secret 的键集本来就会因为
`envFrom` 与显式 `secretKeyRef` 两种写法而分叉（实测 server1 是超集）；比全量会把
这种设计差异报成红。

用法
----
    python3 scripts/verify-site-secret-parity.py                      # master vs server1
    python3 scripts/verify-site-secret-parity.py --from xinru --to xinru-server1
    python3 scripts/verify-site-secret-parity.py --live-only          # 不渲染，只看线上
    python3 scripts/verify-site-secret-parity.py --self-test

退出码：0 全部满足；1 有缺失/不一致；2 判不出。
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

#: 站点 → (渲染用的 values 文件, make 目标)。base 是 xinru-master 的收敛态，
#: overlay 只覆写 suspend。目标名固定，因为闸要用**同一套** helm 参数（Makefile
#: 里有带外私有值的占位兜底），自己拼参数会在两台机器上渲出不同结果。
SITE_VALUES = {
    "xinru": ("values.yaml", "render-base"),
    "xinru-server1": ("values-server1.yaml", "render"),
}

#: R2 的例外：同一键两站点都必需、取值不同，但已查明差异本身不是缺陷。
#: 每条**必须带解除条件**；仍逐条打印、不计 EXIT。别为了让闸变绿往里加。
#:
#: 键是 `(<secret 名前缀>, <键名>)`，**故意不写全名**：secret 名里带法务账号标识，
#: 而 `make verify-hygiene` 禁止把 `acctNNN` 这类标识写进仓（2026-11-14 我自己
#: 先踩了一次——硬编码全名当场让 hygiene 红）。前缀匹配比全名更耐改名，也不会把
#: 仓库变成标识清单。
KNOWN_DIVERGENCE = {
    ("legal-identity-", "crawl_proxy_url"): (
        "同一 proxy id（两站点 id 值相同）的两个不同出口：xinru 出 134.175.46.69、"
        "server1 出 111.230.147.208，两侧实测 200 / 各约 0.4s ⇒ 不是「一份拷贝过期」，"
        "是两个都活着的站点本地出口。该源当前两站点都挂起、broker 只回 /health。"
        "**解除条件**：当它所属的源在某一站点成为唯一执行者（另一站点 broker 置 0 副本，"
        "或该 secret 不再被任何在跑对象引用）时，把两侧收敛到该站点的值并删掉本条。"
    ),
    ("legal-identity-", "login_proxy_url"): (
        "同 crawl_proxy_url（两键实测同值、同 id）。**解除条件**同上。"
    ),
}


def _known_reason(secret: str, key: str) -> str | None:
    for (prefix, k), reason in KNOWN_DIVERGENCE.items():
        if key == k and secret.startswith(prefix):
            return reason
    return None


class Unjudgeable(Exception):
    """判不出（渲染失败/集群不可达/零必需项）——不是通过。"""


# ---------------------------------------------------------------- 渲染侧
def _harvest(block: str, refs: set[tuple[str, str]]) -> None:
    """从一个 YAML 文档块里收被引用的 (secret, key)。envFrom/volume 记 ('name','*')。"""
    if "kind:" not in block:
        return
    # 只收「点亮」的对象：CronJob 看 suspend；其余对象默认活（渲染里没有
    # replicas: 0 的写法就不必判）。
    if re.search(r"^kind:\s*CronJob\s*$", block, re.M):
        if re.search(r"^\s*suspend:\s*true\s*$", block, re.M):
            return
    if re.search(r"^\s*replicas:\s*0\s*$", block, re.M):
        return
    for m in re.finditer(r"secretKeyRef:\s*\n\s+name:\s*(\S+)\s*\n\s+key:\s*(\S+)", block):
        refs.add((m.group(1), m.group(2)))
    for m in re.finditer(r"secretKeyRef:\s*\n\s+key:\s*(\S+)\s*\n\s+name:\s*(\S+)", block):
        refs.add((m.group(2), m.group(1)))
    for m in re.finditer(r"-\s*secretRef:\s*\n\s+name:\s*(\S+)", block):
        refs.add((m.group(1), "*"))


def _render_lit(target: str) -> set[tuple[str, str]]:
    """渲染某个站点，取**点亮对象**引用的 (secret, key)。"""
    try:
        out = subprocess.run(["make", "-s", target], cwd=CHART,
                             capture_output=True, text=True, timeout=240)
    except (FileNotFoundError, subprocess.TimeoutExpired) as err:
        raise Unjudgeable(f"{target} 起不来: {err}") from err
    if out.returncode != 0:
        raise Unjudgeable(f"make {target} 失败: {(out.stderr or '').strip()[:300]}")
    refs: set[tuple[str, str]] = set()
    chunk = ""
    for line in out.stdout.splitlines(keepends=True):
        if line.startswith("---"):
            _harvest(chunk, refs)
            chunk = ""
        else:
            chunk += line
    _harvest(chunk, refs)
    return refs


# ---------------------------------------------------------------- 线上侧
def _live_lit(ctx: str) -> tuple[set[tuple[str, str]], list[str]]:
    """取线上**在跑**对象引用的 (secret, key)，以及每个引用来自哪个对象。"""
    refs: set[tuple[str, str]] = set()
    why: list[str] = []
    for kind, res in (("cronjob", "CronJob"), ("deploy", "Deployment"),
                      ("statefulset", "StatefulSet")):
        p = subprocess.run(["kubectl", "--context", ctx, "-n", NS, "get", kind, "-o", "json"],
                           capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise Unjudgeable(f"{ctx} 读不到 {kind}: {(p.stderr or '').strip()[:200]}")
        try:
            items = json.loads(p.stdout).get("items", [])
        except ValueError as err:
            raise Unjudgeable(f"{ctx} 的 {kind} JSON 解析不了: {err}") from err
        for it in items:
            name = it["metadata"]["name"]
            if res == "CronJob":
                if it["spec"].get("suspend"):
                    continue
                pod = it["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            else:
                if (it["spec"].get("replicas") or 0) == 0:
                    continue
                pod = it["spec"]["template"]["spec"]
            found: list[str] = []
            containers = list(pod.get("containers") or []) + list(pod.get("initContainers") or [])
            for c in containers:
                for e in c.get("env") or []:
                    sk = (e.get("valueFrom") or {}).get("secretKeyRef")
                    if sk:
                        refs.add((sk["name"], sk["key"]))
                        found.append(f"{sk['name']}/{sk['key']}")
                for ef in c.get("envFrom") or []:
                    sr = ef.get("secretRef")
                    if sr:
                        refs.add((sr["name"], "*"))
                        found.append(f"{sr['name']}/*")
            for v in pod.get("volumes") or []:
                sec = (v.get("secret") or {}).get("secretName")
                if sec:
                    refs.add((sec, "*"))
                    found.append(f"{sec}/*(volume)")
            if found:
                why.append(f"{res}/{name}: {', '.join(sorted(set(found)))}")
    return refs, why


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


# ---------------------------------------------------------------- 判据
def compare(required: dict[str, set], secrets: dict[str, dict],
            an: str, bn: str) -> tuple[list[str], list[str], list[str]]:
    """返回 (命中, 事实, 通过项)。"""
    if not any(required.values()):
        raise Unjudgeable("两站点必需集都为空——什么都没比，不许读成「都一致」")
    problems: list[str] = []
    facts: list[str] = []
    notes: list[str] = []
    for secret, key in sorted(set(required[an]) | set(required[bn])):
        need_a, need_b = (secret, key) in required[an], (secret, key) in required[bn]
        if key == "*":                      # envFrom / volume：只判整份 secret 在不在
            have_a, have_b = secret in secrets[an], secret in secrets[bn]
            if need_a and not have_a:
                problems.append(f"R1 缺失 {secret}（整份）: {an} 上有在跑的对象要它")
            if need_b and not have_b:
                problems.append(f"R1 缺失 {secret}（整份）: {bn} 上有在跑的对象要它")
            elif have_a and have_b:
                notes.append(f"✓ {secret}（整份）两侧都在")
            continue
        ha = (secrets[an].get(secret) or {}).get(key)
        hb = (secrets[bn].get(secret) or {}).get(key)
        if need_a and ha is None:
            problems.append(f"R1 缺失 {secret}/{key}: {an} 上有在跑的对象要它，但 secret 里没有")
        if need_b and hb is None:
            problems.append(f"R1 缺失 {secret}/{key}: {bn} 上有在跑的对象要它，但 secret 里没有")
        if ha is None or hb is None:
            continue
        ident = f"{secret}/{key}"
        if ha[0] == hb[0]:
            notes.append(f"✓ {ident} 同值（{ha[0]}）")
        elif need_a and need_b:
            known = _known_reason(secret, key)
            if known:
                facts.append(f"R3 已裁决 {ident}: {an}={ha[0]}({ha[1]}B) ≠ {bn}={hb[0]}({hb[1]}B)"
                             f" —— {known}")
            else:
                problems.append(
                    f"R2 不一致 {ident}: {an}={ha[0]}({ha[1]}B) ≠ {bn}={hb[0]}({hb[1]}B)"
                    f" → 两个站点都有对象要用它，搬站点/轮换凭据前必须对齐："
                    f"这类差异不会在连通性探针里现形，只在真跑那一刻")
        else:
            side = an if need_a else bn
            facts.append(f"R4 只一侧必需 {ident}: 只有 {side} 有对象用它，两侧取值不同"
                         f"（{ha[0]} vs {hb[0]}）—— 不构成风险，但别把它当「两边一致」")
    return problems, facts, notes


def self_test() -> int:
    refs = {("s1", "k1"), ("s1", "k2"), ("s2", "*")}
    same = {"s1": {"k1": ("aaa", 8), "k2": ("bbb", 8)}, "s2": {"x": ("z", 1)}}
    both = {"xinru": set(refs), "xinru-server1": set(refs)}
    only_a = {"xinru": set(refs), "xinru-server1": {("s1", "k1")}}
    cases = [
        ("绿：全部同值", both, {"xinru": same, "xinru-server1": same}, None),
        ("R2 红：两边都必需且不同",
         both, {"xinru": same,
                "xinru-server1": {"s1": {"k1": ("aaa", 8), "k2": ("ccc", 8)},
                                  "s2": {"x": ("z", 1)}}}, "R2"),
        ("绿：只在一边必需、取值不同不判红（embed 形态）",
         only_a, {"xinru": same,
                  "xinru-server1": {"s1": {"k1": ("aaa", 8)}, "s2": {"x": ("z", 1)}}}, None),
        ("R1 红：目标站点缺必需键",
         both, {"xinru": same, "xinru-server1": {"s2": {"x": ("z", 1)}}}, "R1"),
        ("R1 红：目标站点缺整份 secret（envFrom）",
         both, {"xinru": same,
                "xinru-server1": {"s1": {"k1": ("aaa", 8), "k2": ("bbb", 8)}}}, "R1"),
    ]
    bad = 0
    for name, req, sec, expect in cases:
        problems, _, _ = compare(req, sec, "xinru", "xinru-server1")
        hit = [p for p in problems if p.startswith(expect)] if expect else problems
        if expect and not hit:
            print(f"✗ {name}: 期望 {expect}，实际 {problems or '无'}")
            bad += 1
        elif not expect and problems:
            print(f"✗ {name}: 期望全过，实际 {problems}")
            bad += 1
        else:
            print(f"✓ {name}")
    try:
        compare({"xinru": set(), "xinru-server1": set()}, {}, "xinru", "xinru-server1")
        print("✗ 判不出：必需集为空却退 0")
        bad += 1
    except Unjudgeable:
        print("✓ 判不出：必需集为空 → EXIT 2")
    print("SELF-TEST", "PASS" if not bad else f"FAIL({bad})")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", default="xinru")
    ap.add_argument("--to", dest="dst", default="xinru-server1")
    ap.add_argument("--live-only", action="store_true", help="不渲染，只看线上在跑的对象")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    try:
        required: dict[str, set] = {}
        secrets: dict[str, dict] = {}
        for site in (args.src, args.dst):
            live, why = _live_lit(site)
            req = set(live)
            if not args.live_only:
                target = SITE_VALUES.get(site, (None, None))[1]
                if target:
                    req |= _render_lit(target)
            if not req:
                raise Unjudgeable(f"{site} 的必需集为空——读不到或扫错了树，不许读成「都一致」")
            required[site] = req
            secrets[site] = secret_hashes(site)
            print(f"  · {site}: {len(req)} 个必需键，{len(why)} 个在跑对象引用 secret")
            for w in why:
                print(f"      {w}")
    except Unjudgeable as err:
        print(f"✗ 判不出：{err}")
        return 2
    problems, facts, notes = compare(required, secrets, args.src, args.dst)
    for n in notes:
        print(f"  {n}")
    for f in facts:
        print(f"  · {f}")
    if not problems:
        print(f"✓ 两站点必需凭据齐备（{args.src} {len(required[args.src])} 键 / "
              f"{args.dst} {len(required[args.dst])} 键）")
        return 0
    print(f"✗ 凭据命中 {len(problems)} 条：")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
