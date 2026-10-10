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
  value: {{ .rustfs.endpoint | quote }}
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
  value: {{ .postgres.host | quote }}
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
