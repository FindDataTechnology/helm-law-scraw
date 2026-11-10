# 自建 runner 接入（也没做，只是前置清单）

> 状态：**尚未注册**。`helm-law-scraw` 的 `.github/workflows/chart-verify.yml` 写的是
> `runs-on: [self-hosted, linux]`，在 runner 注册前它只会**排队**（`status: queued`），
> 不会失败也不会跑。**排队不是绿灯** —— 这期间真正的门是本地
> `./scripts/install-git-hooks.sh`（opt-in pre-commit）+ `make verify-report`。

## 为什么不用 `ubuntu-latest`

本仓保持 **PRIVATE**（裁决 2026-11-10），而 `FindDataTechnology` 的 GitHub 托管分钟
已耗尽（`2006 / 2000`）。托管 runner 上跑 = 把门挂在一个不调度的地方。
**自建 runner 不消耗托管分钟**，这是「走 GitHub Actions 又不依赖私有仓额度」的唯一可行解。

## 前置清单

| # | 前提 | 判据 / 说明 |
|---|---|---|
| 1 | **一台常驻 Linux 主机**（x86_64 或 arm64） | 必须常驻：runner 是长轮询进程，机器关机=任务积压。不要用笔记本/临时容器。 |
| 2 | **出网 `github.com:443`** | runner 需访问 `github.com`、`api.github.com`、`codeload.github.com`、`objects.githubusercontent.com`（下载 runner 与 action 归档）、`ghcr.io`（部分 action 镜像）。**不需要**入站端口——runner 主动外连取任务。 |
| 3 | `git`、`make`、`bash`、`awk`/`sed` | workflow 会跑 `make verify-report`；脚本只用 POSIX 工具。 |
| 4 | `helm` | chart 门必需。workflow 首个 step 会检查，缺了**直接红而不是跳过**。 |
| 5 | 非 root 专用账号 | runner 会 checkout 私有仓代码（含内网地址与源清单），不要与其他服务共用账号。 |
| 6 | **不需要** Docker Hub 访问 | 子依赖已随仓入库（`charts/*.tgz`，见任务 2.4），不再需要 `oci://registry-1.docker.io/bitnamicharts`。 |

本机实测连通性（仅作参考，不能替代目标主机实测）：

```
github.com                       200
api.github.com                   200
codeload.github.com              301
objects.githubusercontent.com    404（根路径无内容，可连通）
runner tarball: final=200 size=195796727
```

## 注册步骤（**未执行**，供有主机后照做）

```bash
# 0) 变量
OWNER=FindDataTechnology
REPO=helm-law-scraw
RUNNER_NAME=$(hostname)-chart-gate

# 1) 取 runner 版本（2026-11-10 实测 latest = v2.338.2）
VER=$(gh api repos/actions/runner/releases/latest --jq .tag_name)   # 形如 v2.338.2
V=${VER#v}

# 2) 下载并解包（arm64 把 x64 换成 arm64）
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -fsSL -o runner.tar.gz \
  "https://github.com/actions/runner/releases/download/${VER}/actions-runner-linux-x64-${V}.tar.gz"
tar xzf runner.tar.gz

# 3) 取注册 token（**需要该仓 admin 权限**；token 1 小时过期，不要写进任何文件/提交）
TOKEN=$(gh api -X POST repos/$OWNER/$REPO/actions/runners/registration-token --jq .token)

# 4) 配置：标签必须含 self-hosted,linux（workflow 的 runs-on 就是这两个）
./config.sh \
  --url "https://github.com/$OWNER/$REPO" \
  --token "$TOKEN" \
  --name "$RUNNER_NAME" \
  --labels self-hosted,linux \
  --work _work \
  --unattended

# 5) 前台试跑（先确认能取到任务再装成服务）
./run.sh

# 6) 装成系统服务（需 sudo）
sudo ./svc.sh install
sudo ./svc.sh start
```

> `--labels self-hosted,linux` 是**必需**：GitHub 会自动加 `self-hosted`，但 `linux`
> 要显式给，否则 `runs-on: [self-hosted, linux]` 匹配不到，任务永远 queued。

## 注册后的验收（三条，缺一条不算成功）

```bash
# ① runner 在线
gh api repos/FindDataTechnology/helm-law-scraw/actions/runners \
  --jq '.runners[] | {name, status, labels: [.labels[].name]}'
# 期望：status=online，labels 含 self-hosted 与 linux

# ② 手动触发一次，且**不是 queued**
gh workflow run chart-verify --repo FindDataTechnology/helm-law-scraw
sleep 20
gh run list --repo FindDataTechnology/helm-law-scraw --workflow chart-verify --limit 3 \
  --json status,conclusion,event

# ③ 负例：真正会红才算门（在分支上把记录器改坏）
#    把 values.yaml 里 `!stale && !loadStalled` 改回 `!stale`，提 PR
#    期望：chart-verify 失败，日志点名「缺少 装载停滞参与 status 判定」
```

注册前（当前基线）：`total_count = 0`，dispatch 出来的 run 是 `queued`。

## 安全边界

- 私有 runner 拿到的是**完整仓代码**（含内网地址与法务源清单）。主机被攻破 ≈ 仓内容泄露。
  故：专用主机、专用低权限账号、不跑无关服务、不打开放入站端口。
- registration token **1 小时过期**，只在 `config.sh` 时用一次；**不要**写进
  `docs/`、脚本、或任何提交（本仓 `.gitignore` 已拦 `.env*` / `secrets*.yaml`）。
- runner 不需要仓库写权限即可跑读类 workflow；本 workflow 已声明
  `permissions: contents: read`。
- 撤销：`gh api -X DELETE repos/$OWNER/$REPO/actions/runners/<id>`，并在主机
  `sudo ./svc.sh stop && sudo ./svc.sh uninstall`。

## 回滚点

- 未注册 runner 前，**删掉 `.github/workflows/chart-verify.yml` 无副作用**（它只会排队）。
- 已注册后要停门：先 `gh workflow disable chart-verify --repo …`（立即生效、不删历史），
  再按需移除 runner；本地 pre-commit 与 `make verify-report` 始终可独立使用。
