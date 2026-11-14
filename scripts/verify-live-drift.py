#!/usr/bin/env python3
"""渲染↔线上漂移闸：chart 渲染出来的对象，必须与集群里的同名对象逐字段相同。

抓的是什么
----------
2026-11-14 实历：`make verify-report` 一直在绿，因为它**只验渲染产物**，断言
「日报把 load_stalled 写进 crawl_runs」；而同一时刻 master 线上的 report `args`
少了整整一段 `loadStalled` recorder —— **门断言的性质在生产里根本不存在**。
同一次逐字段比对还捞出另外三处非惰性差异：

  · 12 个对象线上 `resources: {}`（没有 limits：跑飞的爬虫能吃掉整台 3.7GB 机器，
    `NODE_OPTIONS` 只约束 V8 堆，管不住 RSS/CPU）
  · `flk-law-embed` / `flk-law-load` 的 `FD_RUNNER_IMAGE_TAG` 停在旧片
  · report `backoffLimit` 是集群缺省 6，chart 写 0（重试三条一簇会把真信号稀释）

共同点：**render 是对的、集群是错的、所有门都是绿的**。同一形态在 server1 上更极端
（整条线停在 `sha-b63d0d1`，比 chart 落后三代）。这道闸补的就是「声明面绿 ≠ 线上是
那样」这半边。

判据
----
对每个站点用该站点自己的 values 渲染（`xinru` → `make render-base`，
`xinru-server1` → `make render`），**把渲染产物经
`kubectl create --dry-run=client -o json -f -` 转成真正的 JSON**（不靠自己解 YAML：
本机 homebrew python 没有 PyYAML，而 `/usr/bin/python3` 有——gate 不能依赖解释器
口味），再与集群同名对象逐字段比：

    image / command / args / env（名字+来源）/ resources / suspend / schedule /
    backoffLimit / activeDeadlineSeconds

R1 不一致（FAIL）：任一字段不同，点名对象与字段，两侧各打一段值。
R2 只在渲染里（报事实）：chart 有、集群没有 —— 「先合入、后上线」是常态。
R3 只在集群里（报事实）：集群有而 chart 不渲染 —— 本仓已知两类（`guide-cases-*`
   无主源；`federation-observer`/`gost-egress`/`proxy-control` 站点级作业）。
R4 判不出（EXIT 2）：渲染失败、kubectl 读不到、某一侧 0 个可比对象。

三处刻意的判据细节（都是当天踩出来的）：
- **比 `resources` 先归一化量**：render 出 `cpu: 1`（整数），API 读回 `'1'`（字符串），
  直接比会造 13 条假红。
- **`env` 按「名字+来源」比，不比值**：值来自 Secret 时两侧都只有 key 名，
  比的是引用一致性；真值比对照 `verify-secrets`。
- **渲染侧走 dry-run 转 JSON，不自己解 YAML**：手写 YAML 解析在缩进/多文档上必然
  出错，而出错的解析器只会给出「都一致」。

用法
----
    python3 scripts/verify-live-drift.py                  # 两个站点都查
    python3 scripts/verify-live-drift.py --site xinru
    python3 scripts/verify-live-drift.py --self-test

退出码：0 无 R1 命中（含 R2/R3 事实行）；1 有漂移；2 判不出。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CHART = Path(__file__).resolve().parent.parent
NS = "scraw"
SITES = {"xinru": "render-base", "xinru-server1": "render"}
FIELDS = ("image", "command", "args", "env", "resources", "suspend", "schedule",
          "backoffLimit", "activeDeadlineSeconds")
KINDS = ("CronJob", "Deployment", "StatefulSet")


class Unjudgeable(Exception):
    """判不出（渲染失败/集群不可达/零可比对象）——不是通过。"""


def norm_res(res) -> dict:
    """把 resource 量归一成字符串：render 出 1（int），API 读回 '1'（str）。"""
    if not res:
        return {}
    return {k: {kk: str(vv) for kk, vv in (v or {}).items()} for k, v in res.items()}


def envsig(container) -> list:
    """[(name, 来源)] —— 区分 secretKeyRef / configMapKeyRef / 字面值。

    字面值里 `value: ""` 与「这个键不存在」必须视为同一个东西：API server 会把
    空串值**整个丢掉**（2026-11-14 实测：apply 声明 `LEGAL_PAUSED_SOURCES: ""`，
    读回是 `{"name": "LEGAL_PAUSED_SOURCES"}` 没有 value 字段），而运行期两者等价
    ——env 条目还在，变量就是空串。不归一化的话，每一个「清空某个 env」的改动都会
    永远报一条假红（正是本闸第一次改 `LEGAL_PAUSED_SOURCES` 时踩到的）。
    """
    out = []
    for e in container.get("env") or []:
        fr = e.get("valueFrom") or {}
        if "secretKeyRef" in fr:
            v = "secret:" + fr["secretKeyRef"]["name"] + "/" + fr["secretKeyRef"]["key"]
        elif "configMapKeyRef" in fr:
            v = "cm:" + fr["configMapKeyRef"]["name"] + "/" + fr["configMapKeyRef"]["key"]
        else:
            val = e.get("value")
            v = "val:" + ("" if val is None else str(val))
        out.append((e["name"], v))
    return sorted(out)


def shape(kind: str, spec: dict) -> dict:
    """从 CronJob / Deployment / StatefulSet 的 spec 里取出要比的字段。"""
    if kind == "CronJob":
        job = spec["jobTemplate"]["spec"]
        c = job["template"]["spec"]["containers"][0]
        return {"image": c["image"], "command": c.get("command"), "args": c.get("args"),
                "env": envsig(c), "resources": norm_res(c.get("resources")),
                "suspend": spec.get("suspend"), "schedule": spec.get("schedule"),
                "backoffLimit": job.get("backoffLimit"),
                "activeDeadlineSeconds": job.get("activeDeadlineSeconds")}
    c = spec["template"]["spec"]["containers"][0]
    return {"image": c["image"], "command": c.get("command"), "args": c.get("args"),
            "env": envsig(c), "resources": norm_res(c.get("resources"))}


def _parse_multi_json(text: str) -> list[dict]:
    """kubectl 对多文档输入会**连续打印多个 JSON 对象**（不是 List），
    所以不能 json.loads，要 raw_decode 逐个吃。"""
    dec = json.JSONDecoder()
    out, idx = [], 0
    while idx < len(text):
        while idx < len(text) and text[idx] in " \t\r\n":
            idx += 1
        if idx >= len(text):
            break
        obj, idx = dec.raw_decode(text, idx)
        out.append(obj)
    return out


def rendered(site: str) -> dict:
    """渲染该站点并转成 JSON。走 kubectl dry-run 而不是自己解 YAML。"""
    target = SITES[site]
    try:
        r = subprocess.run(["make", "-s", target], cwd=CHART,
                           capture_output=True, text=True, timeout=300)
    except (FileNotFoundError, subprocess.TimeoutExpired) as err:
        raise Unjudgeable(f"{target} 起不来: {err}") from err
    if r.returncode != 0:
        raise Unjudgeable(f"make {target} 失败: {(r.stderr or '').strip()[:300]}")
    c = subprocess.run(["kubectl", "create", "--dry-run=client", "--validate=false",
                        "-o", "json", "-f", "-"],
                       input=r.stdout, capture_output=True, text=True, timeout=180)
    if c.returncode != 0:
        raise Unjudgeable(f"渲染产物转 JSON 失败: {(c.stderr or '').strip()[:300]}")
    try:
        docs = _parse_multi_json(c.stdout)
    except ValueError as err:
        raise Unjudgeable(f"dry-run 输出不是 JSON: {err}") from err
    objs = {}
    for doc in docs:
        for i in (doc.get("items") or [doc]):
            k = i.get("kind")
            if k in KINDS:
                objs[(k, i["metadata"]["name"])] = shape(k, i["spec"])
    if not objs:
        raise Unjudgeable("渲染输出里一个可比对象都没有")
    return objs


def live(site: str) -> dict:
    objs = {}
    for res, kind in (("cronjob", "CronJob"), ("deploy", "Deployment"),
                      ("statefulset", "StatefulSet")):
        p = subprocess.run(["kubectl", "--context", site, "-n", NS, "get", res, "-o", "json"],
                           capture_output=True, text=True, timeout=180)
        if p.returncode != 0:
            raise Unjudgeable(f"{site} 读不到 {res}: {(p.stderr or '').strip()[:200]}")
        try:
            for i in json.loads(p.stdout)["items"]:
                objs[(kind, i["metadata"]["name"])] = shape(kind, i["spec"])
        except (ValueError, KeyError) as err:
            raise Unjudgeable(f"{site} 的 {res} JSON 解析不了: {err}") from err
    return objs


def compare(want: dict, got: dict) -> tuple[list[str], list[str]]:
    """返回 (R1 命中, 事实行)。"""
    if not want or not got:
        raise Unjudgeable("某一侧 0 个可比对象——什么都没比，不许读成「一致」")
    problems, facts = [], []
    for key in sorted(set(want) | set(got)):
        label = f"{key[0]}/{key[1]}"
        if key not in got:
            facts.append(f"R2 只在渲染里 {label}: chart 有、集群没有（还没 apply？）")
            continue
        if key not in want:
            facts.append(f"R3 只在集群里 {label}: chart 不渲染（无主源或站点级作业）")
            continue
        for f in FIELDS:
            w, g = want[key].get(f), got[key].get(f)
            if w == g:
                continue
            problems.append(f"R1 不一致 {label}.{f}: render={str(w)[:160]} ≠ live={str(g)[:160]}")
    return problems, facts


def self_test() -> int:
    a = {"image": "x:1", "env": [("A", "val:1")], "resources": {"limits": {"cpu": "1"}}}
    cases = [
        ("绿：完全一致", {("CronJob", "a"): a}, {("CronJob", "a"): a}, None),
        ("R1 红：镜像不同", {("CronJob", "a"): a},
         {("CronJob", "a"): dict(a, image="x:2")}, "R1"),
        ("R1 红：env 多一个", {("CronJob", "a"): a},
         {("CronJob", "a"): dict(a, env=[("A", "val:1"), ("B", "val:2")])}, "R1"),
        ("R1 红：resources 缺失", {("CronJob", "a"): a},
         {("CronJob", "a"): dict(a, resources={})}, "R1"),
        ("R1 红：args 少一段 recorder",
         {("CronJob", "a"): dict(a, args=["x\nload_stalled_sources\ny"])},
         {("CronJob", "a"): dict(a, args=["x\ny"])}, "R1"),
        ("绿：只在渲染里（R2 事实）", {("CronJob", "a"): a, ("CronJob", "z"): a},
         {("CronJob", "a"): a}, None),
    ]
    bad = 0
    for name, want, got, expect in cases:
        problems, facts = compare(want, got)
        hit = [p for p in problems if p.startswith(expect)] if expect else problems
        if expect and not hit:
            print(f"✗ {name}: 期望 {expect}，实际 {problems or '无'}")
            bad += 1
        elif not expect and problems:
            print(f"✗ {name}: 期望全过，实际 {problems}")
            bad += 1
        else:
            print(f"✓ {name}" + (f"（事实 {len(facts)}）" if facts else ""))
    if norm_res({"limits": {"cpu": 1}}) != norm_res({"limits": {"cpu": "1"}}):
        print("✗ 归一化：cpu 1 与 '1' 被判成不同")
        bad += 1
    else:
        print("✓ 归一化：cpu 1 == '1'")
    # 空串 env：render 出 `value: ""`，API 读回来连 value 字段都没有
    c_render = {"env": [{"name": "P", "value": ""}]}
    c_live = {"env": [{"name": "P"}]}
    if envsig(c_render) != envsig(c_live):
        print(f"✗ 归一化：空串 env 被判成不同 {envsig(c_render)} vs {envsig(c_live)}")
        bad += 1
    else:
        print("✓ 归一化：空串 env == 无 value 字段")
    if envsig({"env": [{"name": "P", "value": "x"}]}) == envsig(c_live):
        print("✗ 归一化：非空值被吞掉了")
        bad += 1
    try:
        compare({}, {})
        print("✗ 判不出：零对象却退 0")
        bad += 1
    except Unjudgeable:
        print("✓ 判不出：零对象 → EXIT 2")
    print("SELF-TEST", "PASS" if not bad else f"FAIL({bad})")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", choices=sorted(SITES), action="append")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    rc = 0
    for site in (args.site or sorted(SITES)):
        try:
            want, got = rendered(site), live(site)
        except Unjudgeable as err:
            print(f"✗ 判不出 {site}: {err}")
            return 2
        problems, facts = compare(want, got)
        for f in facts:
            print(f"  · {site} {f}")
        for p in problems:
            print(f"  ✗ {site} {p}")
        if problems:
            rc = 1
        else:
            print(f"✓ {site}: {len(want)} 个渲染对象与线上逐字段一致"
                  f"（另有 {len(facts)} 条事实行）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
