{{/*
Expand the chart name.
*/}}
{{- define "helm-law-craw.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully-qualified app name.
*/}}
{{- define "helm-law-craw.fullname" -}}
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
{{- define "helm-law-craw.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "helm-law-craw.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels.
*/}}
{{- define "helm-law-craw.selectorLabels" -}}
app.kubernetes.io/name: {{ include "helm-law-craw.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
imagePullSecret name: existingSecret if set, else <fullname>-harbor.
*/}}
{{- define "helm-law-craw.imagePullSecretName" -}}
{{- if .Values.harbor.existingSecret -}}
{{- .Values.harbor.existingSecret -}}
{{- else -}}
{{- include "helm-law-craw.fullname" . -}}-harbor
{{- end -}}
{{- end -}}

{{/*
imagePullSecrets block for a pod spec - only when creds or existingSecret are set.
*/}}
{{- define "helm-law-craw.imagePullSecrets" -}}
{{- if or .Values.harbor.existingSecret (and .Values.harbor.username .Values.harbor.password) -}}
imagePullSecrets:
  - name: {{ include "helm-law-craw.imagePullSecretName" . }}
{{- end -}}
{{- end -}}

{{/*
.dockerconfigjson (base64) for the Harbor registry.
*/}}
{{- define "helm-law-craw.dockerconfigjson" -}}
{{- $host := .Values.harbor.host -}}
{{- $user := .Values.harbor.username -}}
{{- $pass := .Values.harbor.password -}}
{{- $auth := printf "%s:%s" $user $pass | b64enc -}}
{{- printf "{\"auths\":{\"%s\":{\"username\":\"%s\",\"password\":\"%s\",\"auth\":\"%s\"}}}" $host $user $pass $auth | b64enc -}}
{{- end -}}

{{/*
scrapyd REDIS_URL: explicit value or in-chart redis master service.
*/}}
{{- define "helm-law-craw.scrapydRedisUrl" -}}
{{- if .Values.scrapyd.redisUrl -}}
{{- .Values.scrapyd.redisUrl -}}
{{- else -}}
{{- printf "redis://%s-redis-master:6379/0" .Release.Name -}}
{{- end -}}
{{- end -}}

{{/*
runner REDIS_URL: explicit value or in-chart redis master service.
*/}}
{{- define "helm-law-craw.runnerRedisUrl" -}}
{{- if .Values.lawContracts.redisUrl -}}
{{- .Values.lawContracts.redisUrl -}}
{{- else -}}
{{- printf "redis://%s-redis-master:6379/0" .Release.Name -}}
{{- end -}}
{{- end -}}
