SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND_IMAGE ?=
FRONTEND_IMAGE ?=
SCORE_K8S ?= score-k8s
ROLLOUT_TIMEOUT_SECONDS ?= 600

.PHONY: help render validate deploy apply wait execution-contract status smoke database-up database-status database-smoke

help:
	@printf '%s\n' \
		'Targets:' \
		'  render BACKEND_IMAGE=... FRONTEND_IMAGE=...    Generate application manifests from Score' \
		'  validate BACKEND_IMAGE=... FRONTEND_IMAGE=...  Render and validate against the local API' \
		'  deploy BACKEND_IMAGE=... FRONTEND_IMAGE=...    Explicitly deploy both applications to local k3d' \
		'  apply BACKEND_IMAGE=... FRONTEND_IMAGE=...     Render and apply without waiting' \
		'  wait ROLLOUT_TIMEOUT_SECONDS=600              Wait for both application rollouts' \
		'  status                                      Show applications and HTTPRoutes' \
		'  smoke                                       Check UI and API through the shared Gateway'

render:
	@BACKEND_IMAGE='$(BACKEND_IMAGE)' FRONTEND_IMAGE='$(FRONTEND_IMAGE)' SCORE_K8S='$(SCORE_K8S)' bash scripts/render.sh

validate: render
	@kubectl --context k3d-kubedeploy apply --server-side --dry-run=server --field-manager=kubedeploy-score -f kubernetes/namespace.yaml
	@kubectl --context k3d-kubedeploy get namespace kubedeploy-demo >/dev/null
	@kubectl --context k3d-kubedeploy apply --server-side --dry-run=server --field-manager=kubedeploy-score -f build/workloads.yaml

deploy: render
	@BACKEND_IMAGE='$(BACKEND_IMAGE)' FRONTEND_IMAGE='$(FRONTEND_IMAGE)' ROLLOUT_TIMEOUT_SECONDS='$(ROLLOUT_TIMEOUT_SECONDS)' bash scripts/deploy.sh

apply: render
	@BACKEND_IMAGE='$(BACKEND_IMAGE)' FRONTEND_IMAGE='$(FRONTEND_IMAGE)' DEPLOY_PHASE=apply bash scripts/deploy.sh

wait:
	@ROLLOUT_TIMEOUT_SECONDS='$(ROLLOUT_TIMEOUT_SECONDS)' bash scripts/wait.sh

execution-contract:
	@printf '%s\n' 1

status:
	@kubectl --context k3d-kubedeploy --namespace kubedeploy-demo get deployment,service,httproute

smoke:
	@bash scripts/smoke.sh

database-up:
	@bash scripts/database-up.sh

database-status:
	@kubectl --context k3d-kubedeploy --namespace kubedeploy-demo get statefulset/postgres,service/postgres,persistentvolumeclaim

database-smoke:
	@python3 scripts/database-smoke.py
