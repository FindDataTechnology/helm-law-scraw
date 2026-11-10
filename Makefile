CHART := helm-law-scraw
NAMESPACE ?= scraw
RELEASE ?= law-craw
REGISTRY ?= docker.io

.PHONY: help lint verify-deps verify-report dep-build install upgrade package

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

lint: ## Run helm lint
	helm lint .

verify-deps: ## Assert vendored charts/*.tgz match Chart.yaml (name+version, no stale leftovers)
	./scripts/verify-chart-deps.sh

verify-report: verify-deps ## Assert the report CronJob keeps its crawl_runs recorder (incl. load_stalled)
	./scripts/assert-report-recorder.sh

dep-build: ## Fetch Bitnami subchart dependencies
	helm dependency build .

install: dep-build ## Install the chart with default values
	helm install $(RELEASE) . \
		--namespace $(NAMESPACE) --create-namespace \
		--set registry=$(REGISTRY)

upgrade: dep-build ## Upgrade an existing release
	helm upgrade $(RELEASE) . \
		--namespace $(NAMESPACE) \
		--set registry=$(REGISTRY)

package: ## Package the chart into a .tgz
	helm package . -d ../../