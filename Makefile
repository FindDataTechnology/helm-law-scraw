CHART := helm-law-scraw
NAMESPACE ?= scraw
RELEASE ?= law-craw
REGISTRY ?= docker.io

# 带外私有值（内网端点 / PG 主机 / 法务身份标识）：真源 values-private.yaml，已 gitignore。
# 本地有那份文件就用它；没有（CI、新克隆）就用占位值——门与 lint 验的是**形态**，
# 与真实地址无关，所以不能因为没有私有文件就变红，也不能因此跳过渲染（那是假绿）。
PRIVATE_VALUES := values-private.yaml
ifeq ($(wildcard $(PRIVATE_VALUES)),)
PRIVATE_ARGS := \
	--set flkLawCrawl.rustfs.endpoint=http://rustfs.invalid:9000 \
	--set flkLawEmbed.rustfs.endpoint=http://rustfs.invalid:9000 \
	--set flkLawEmbed.qdrant.url=http://qdrant.invalid:6333 \
	--set legalSources.rustfs.endpoint=http://rustfs.invalid:9000 \
	--set legalSources.postgres.host=pg.invalid \
	--set authBroker.rustfs.endpoint=http://rustfs.invalid:9000 \
	--set authBroker.postgres.host=pg.invalid \
	--set wenshuCrawl.rustfs.endpoint=http://rustfs.invalid:9000 \
	--set images.wenshuCrawl.repository=ci/wenshu \
	--set private.accountId=ci
else
PRIVATE_ARGS := -f $(PRIVATE_VALUES)
endif

.PHONY: help lint render-base verify-deps verify-hygiene verify-report verify-sites verify-pins verify-runs verify-live verify-secrets render dep-build install upgrade package

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

lint: verify-sites ## Run helm lint
	helm lint . $(PRIVATE_ARGS)

verify-sites: ## Assert no CronJob is lit on two sites at once (base + every site overlay)
	./scripts/verify-site-exclusivity.py

verify-secrets: ## Assert every chart-referenced secret key holds the same value on both sites (hash-only)
	./scripts/verify-site-secret-parity.py

verify-pins: ## Assert crawl_sources.runner_image equals the chart's image (needs --rows from a query Pod)
	@test -n "$(ROWS)" || { echo "用法: make verify-pins ROWS=/tmp/rows.json（行数据由一次性查询 Pod 产出，见脚本头注）"; exit 2; }
	./scripts/verify-federated-runner-pins.py --rows $(ROWS)

verify-runs: ## Assert one success per schedule window per source (needs --rows from a query Pod)
	@test -n "$(ROWS)" || { echo "用法: make verify-runs ROWS=/tmp/rows.json [SINCE=2026-11-14T05:00:00Z]（行数据由 scripts/single-executor-runs.mjs 产出，见脚本头注）"; exit 2; }
	./scripts/verify-single-executor-runs.py --rows $(ROWS) $(if $(SINCE),--since $(SINCE))

verify-live: ## Assert every rendered object matches the live cluster field-by-field (both sites)
	./scripts/verify-live-drift.py

verify-deps: ## Assert vendored charts/*.tgz match Chart.yaml (name+version, no stale leftovers)	./scripts/verify-chart-deps.sh

verify-hygiene: ## Assert no internal endpoints / account ids in tracked files
	./scripts/assert-no-internal-endpoints.sh

verify-report: verify-deps verify-hygiene ## Assert the report CronJob keeps its crawl_runs recorder (incl. load_stalled)
	./scripts/assert-report-recorder.sh

render: ## Render the chart for xinru (needs values-private.yaml for the internal endpoints)
	helm template $(RELEASE) . --namespace $(NAMESPACE) -f values-server1.yaml $(PRIVATE_ARGS)

render-base: ## Render the chart for the base site (= xinru-master, values.yaml only)
	helm template $(RELEASE) . --namespace $(NAMESPACE) -f values.yaml $(PRIVATE_ARGS)

dep-build: ## Fetch Bitnami subchart dependencies
	helm dependency build .

install: dep-build ## Install the chart with default values
	helm install $(RELEASE) . \
		--namespace $(NAMESPACE) --create-namespace \
		--set registry=$(REGISTRY) $(PRIVATE_ARGS)

upgrade: dep-build ## Upgrade an existing release
	helm upgrade $(RELEASE) . \
		--namespace $(NAMESPACE) \
		--set registry=$(REGISTRY) $(PRIVATE_ARGS)

package: ## Package the chart into a .tgz
	helm package . -d ../../
