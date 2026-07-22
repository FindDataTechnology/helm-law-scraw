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