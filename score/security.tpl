{{ range $i, $m := .Manifests }}
{{ if or (eq $m.kind "Deployment") (eq $m.kind "Service") }}
{{ $name := index $m.metadata.annotations "k8s.score.dev/workload-name" }}
- op: set
  path: {{ $i }}.metadata.labels.app\.kubernetes\.io/instance
  value: {{ $name | quote }}
{{ if eq $m.kind "Service" }}
- op: set
  path: {{ $i }}.spec.selector.app\.kubernetes\.io/instance
  value: {{ $name | quote }}
{{ else }}
- op: set
  path: {{ $i }}.spec.selector.matchLabels.app\.kubernetes\.io/instance
  value: {{ $name | quote }}
- op: set
  path: {{ $i }}.spec.template.metadata.labels.app\.kubernetes\.io/instance
  value: {{ $name | quote }}
{{ end }}
{{ end }}
{{ if eq $m.kind "Deployment" }}
{{ $uid := 65532 }}
{{ if eq $m.metadata.name "frontend" }}{{ $uid = 10001 }}{{ end }}
- op: set
  path: {{ $i }}.spec.template.spec.automountServiceAccountToken
  value: false
- op: set
  path: {{ $i }}.spec.template.spec.securityContext
  value:
    runAsNonRoot: true
    runAsUser: {{ $uid }}
    runAsGroup: {{ $uid }}
    seccompProfile:
      type: RuntimeDefault
{{ if eq $m.metadata.name "frontend" }}
- op: set
  path: {{ $i }}.spec.template.spec.volumes
  value:
    - name: tmp
      emptyDir:
        medium: Memory
        sizeLimit: 16Mi
{{ end }}
{{ range $c, $_ := $m.spec.template.spec.containers }}
{{ if eq $m.metadata.name "frontend" }}
- op: set
  path: {{ $i }}.spec.template.spec.containers.{{ $c }}.volumeMounts
  value:
    - name: tmp
      mountPath: /tmp
{{ end }}
- op: set
  path: {{ $i }}.spec.template.spec.containers.{{ $c }}.imagePullPolicy
  value: IfNotPresent
- op: set
  path: {{ $i }}.spec.template.spec.containers.{{ $c }}.securityContext
  value:
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    capabilities:
      drop: ["ALL"]
{{ end }}
{{ end }}
{{ end }}
