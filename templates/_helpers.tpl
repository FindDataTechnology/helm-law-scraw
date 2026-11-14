{{/*
Expand the chart name.
*/}}
{{- define "helm-law-scraw.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully-qualified app name.
*/}}
{{- define "helm-law-scraw.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "helm-law-scraw.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "helm-law-scraw.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels.
*/}}
{{- define "helm-law-scraw.selectorLabels" -}}
app.kubernetes.io/name: {{ include "helm-law-scraw.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Full image reference with optional registry prefix.
Usage: {{ include "helm-law-scraw.image" (dict "repository" .Values.images.scrapyd.repository "tag" .Values.images.scrapyd.tag "registry" .Values.registry) }}
*/}}
{{- define "helm-law-scraw.image" -}}
{{- $registry := .registry -}}
{{- $repository := .repository -}}
{{- $tag := .tag -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry $repository $tag -}}
{{- else -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end -}}

{{/*
imagePullSecret name: existingSecret if set, else <fullname>-image-pull.
*/}}
{{- define "helm-law-scraw.imagePullSecretName" -}}
{{- if .Values.imageCredentials.existingSecret -}}
{{- .Values.imageCredentials.existingSecret -}}
{{- else -}}
{{- include "helm-law-scraw.fullname" . -}}-image-pull
{{- end -}}
{{- end -}}

{{/*
imagePullSecrets block for a pod spec - only when creds or existingSecret are set.
*/}}
{{- define "helm-law-scraw.imagePullSecrets" -}}
{{- if or .Values.imageCredentials.existingSecret (and .Values.imageCredentials.username .Values.imageCredentials.password) -}}
imagePullSecrets:
  - name: {{ include "helm-law-scraw.imagePullSecretName" . }}
{{- end -}}
{{- end -}}

{{/*
.dockerconfigjson (base64) for the registry credentials.
*/}}
{{- define "helm-law-scraw.dockerconfigjson" -}}
{{- $host := .Values.imageCredentials.host -}}
{{- $user := .Values.imageCredentials.username -}}
{{- $pass := .Values.imageCredentials.password -}}
{{- $auth := printf "%s:%s" $user $pass | b64enc -}}
{{- printf "{\"auths\":{\"%s\":{\"username\":\"%s\",\"password\":\"%s\",\"auth\":\"%s\"}}}" $host $user $pass $auth | b64enc -}}
{{- end -}}

{{/*
scrapyd REDIS_URL: explicit value or in-chart redis master service.
*/}}
{{- define "helm-law-scraw.scrapydRedisUrl" -}}
{{- if .Values.scrapyd.redisUrl -}}
{{- .Values.scrapyd.redisUrl -}}
{{- else -}}
{{- printf "redis://%s-redis-master:6379/0" .Release.Name -}}
{{- end -}}
{{- end -}}

{{/*
runner REDIS_URL: explicit value or in-chart redis master service.
*/}}
{{- define "helm-law-scraw.runnerRedisUrl" -}}
{{- if .Values.lawContracts.redisUrl -}}
{{- .Values.lawContracts.redisUrl -}}
{{- else -}}
{{- printf "redis://%s-redis-master:6379/0" .Release.Name -}}
{{- end -}}
{{- end -}}

{{/*
RustFS + bucket env block shared by legal-sources crawls/loaders/report.
Context: .Values.legalSources
*/}}
{{- define "helm-law-scraw.legalRustfsEnv" -}}
- name: RUSTFS_ENDPOINT
  value: {{ required "缺少 legalSources.rustfs.endpoint：内网端点写在带外 values-private.yaml（已 gitignore），或用 --set 提供" .rustfs.endpoint | quote }}
- name: RUSTFS_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .secretName }}
      key: rustfs-access-key
- name: RUSTFS_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .secretName }}
      key: rustfs-secret-key
- name: RUSTFS_REGION
  value: {{ .rustfs.region | quote }}
- name: LAWS_BUCKET
  value: {{ .lawsBucket | quote }}
{{- end -}}

{{/*
PG env block shared by legal-sources loaders + report.
Context: .Values.legalSources
*/}}
{{- define "helm-law-scraw.legalPgEnv" -}}
- name: PG_HOST
  value: {{ required "缺少 legalSources.postgres.host：内网主机写在带外 values-private.yaml（已 gitignore），或用 --set 提供" .postgres.host | quote }}
- name: PG_PORT
  value: {{ .postgres.port | quote }}
- name: PG_DATABASE
  value: {{ .postgres.database | quote }}
- name: PG_USER
  valueFrom:
    secretKeyRef:
      name: {{ .postgres.secretName }}
      key: {{ .postgres.userKey }}
- name: PG_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .postgres.secretName }}
      key: {{ .postgres.passwordKey }}
{{- end -}}
{{/*
Telemetry env block shared by legal-sources crawls + loaders (crawl_runs direct report).
Context: dict with telemetry + imageTag
*/}}
{{- define "helm-law-scraw.legalTelemetryEnv" -}}
- name: FD_CRAWL_DB_URL
  valueFrom:
    secretKeyRef:
      name: {{ .telemetry.secretName }}
      key: {{ .telemetry.urlKey }}
- name: FD_RUNNER_IMAGE_TAG
  value: {{ .imageTag | quote }}
# The telemetry writer's schema bootstrap (lib/telemetry.mjs ensureSchemaOnce)
# runs DDL unless this flag is set. Chart-managed Jobs authenticate as
# fd_platform, which owns no schema CREATE right, so without the flag every
# start_run failed "permission denied for schema public" and was swallowed
# after 3 retries — the crawls ran but Console never saw them (found
# 2026-10-10 while verifying rmfyalk-incremental-identity). The platform
# dispatcher already injects the same flag into its Jobs.
- name: FD_SCHEMA_MANAGED
  value: "1"
{{- end -}}

{{/*
V8 堆上限 env（legalSources.nodeOptions）。
为什么单独一条：09-24 `96b6892` 实测这台 3.7GB 的节点会把 V8 堆过 ~800MB 的
爬虫 OOM-kill（list 阶段的分配抖动就够，不是泄漏），此前这个 env 只存在于
`fd-law-data/k8s/` 那份「仅作参考、不要 apply」的清单里，线上靠手工带——
chart 缺它 ⇒ 换命名空间/新集群就丢，回来是节点级 OOM。空值时整段不渲染。
Context: .Values.legalSources
*/}}
{{- define "helm-law-scraw.legalNodeEnv" -}}
{{- with .nodeOptions }}
- name: NODE_OPTIONS
  value: {{ . | quote }}
{{- end }}
{{- end -}}

{{/*
Resource limits hard gate for legal-line federation members (change legal-line-federation).
Context: .Values.legalSources
*/}}
{{- define "helm-law-scraw.legalResources" -}}
resources:
  requests:
    cpu: {{ .resources.requests.cpu }}
    memory: {{ .resources.requests.memory }}
  limits:
    cpu: {{ .resources.limits.cpu }}
    memory: {{ .resources.limits.memory }}
{{- end -}}

{{/*
私有令牌替换：把图表内写死的 `__ACCOUNT_ID__` 换成 .Values.private.accountId。

为什么要有：法务身份标识同时出现在三处形态里——pod label 值、crawler 命令行参数、
身份 Secret 名。三者必须同源，但真实值不进 git。做法是**先在文本层替换再缩进**，
结构不变，因此带 values-private.yaml 渲染的结果与写死时逐字一致。

Context: dict "Values" $ "text" <toYaml 后的文本>
*/}}
{{- define "helm-law-scraw.subst" -}}
{{- $acct := required "缺少 private.accountId：法务身份标识写在带外 values-private.yaml（已 gitignore），或用 --set private.accountId=… 提供" .Values.private.accountId -}}
{{- .text | replace "__ACCOUNT_ID__" $acct -}}
{{- end -}}
{{/*
未点亮（suspend: true）的源清单，供 legal-sources-report 的 LEGAL_PAUSED_SOURCES 使用。

为什么要有：报告侧「无成功证据 → stale → 任务 exit 2」这条口径，遇到「按点亮门
合法停着」的源会永远为真（挂起的 CronJob 从不运行，永远没有证据）。把 suspend
这个部署事实渲染进去，报告才有办法把 negotiated 的暂停与真断流分开。

同一个值同时出现在 sources 与 loaders 两侧：crawl 停了但 load 停，同样不该判断流。
两边都以 `source` 归属为源名，去重后逗号分隔。
*/}}
{{- define "helm-law-scraw.legalPausedSources" -}}
{{- $paused := list -}}
{{- /* activeElsewhere：本站点挂起、但**别的站点**在跑的源。它们不算 paused ——
      「这里不跑」不等于「没人跑」。报告侧 paused 还要 stale 才成立，所以这条只在
      该源真的谁都不跑时才改变判定，而那正是切换后要立刻看见的失败形态。 */ -}}
{{- $elsewhere := (.activeElsewhere | default list) -}}
{{- range $key, $src := (.sources | default dict) -}}
{{- /* 只认真正对应一个源的五条（sourceLabel: true）。flk-law-backfill 也挂在
       sources 下，但它是回填作业、没有源标签，名字也不在报告的适配器表里
       （源名 = rmfyalk-case-library / mfa-treaty-library / gov-rules-library /
       party-regulation-library / ccdi-supervisory-regulations）——把它写进暂停
       清单只会让报告打一行「未知源名」，徒增噪声。 */ -}}
{{- if and $src.suspend $src.sourceLabel (not (has $key $elsewhere)) -}}{{- $paused = append $paused $key -}}{{- end -}}
{{- end -}}
{{- range $key, $ld := (.loaders | default dict) -}}
{{- if and $ld.suspend (not (has $ld.source $elsewhere)) -}}{{- $paused = append $paused $ld.source -}}{{- end -}}
{{- end -}}
{{- $paused | uniq | join "," -}}
{{- end -}}
