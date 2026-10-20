SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND_IMAGE ?=
FRONTEND_IMAGE ?=
SCORE_K8S ?= score-k8s

.PHONY: help render validate deploy status smoke

help:
	@printf '%s\n' \
		'Targets:' \
		'  render BACKEND_IMAGE=... FRONTEND_IMAGE=...    Generate application manifests from Score' \
		'  validate BACKEND_IMAGE=... FRONTEND_IMAGE=...  Render and validate against the local API' \
		'  deploy BACKEND_IMAGE=... FRONTEND_IMAGE=...    Explicitly deploy both applications to local k3d' \
		'  status                                      Show applications and HTTPRoutes' \
		'  smoke                                       Check UI and API through the shared Gateway'

render:
	@BACKEND_IMAGE='$(BACKEND_IMAGE)' FRONTEND_IMAGE='$(FRONTEND_IMAGE)' SCORE_K8S='$(SCORE_K8S)' bash scripts/render.sh

validate: render
	@kubectl --context k3d-kubedeploy apply --server-side --dry-run=server --field-manager=kubedeploy-score -f kubernetes/namespace.yaml
	@kubectl --context k3d-kubedeploy get namespace kubedeploy-demo >/dev/null
	@kubectl --context k3d-kubedeploy apply --server-side --dry-run=server --field-manager=kubedeploy-score -f build/workloads.yaml

deploy: render
	@BACKEND_IMAGE='$(BACKEND_IMAGE)' FRONTEND_IMAGE='$(FRONTEND_IMAGE)' bash scripts/deploy.sh

status:
	@kubectl --context k3d-kubedeploy --namespace kubedeploy-demo get deployment,service,httproute

smoke:
	@bash scripts/smoke.sh
