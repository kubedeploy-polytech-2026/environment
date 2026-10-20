# KubeDeploy Environment

Score-описания frontend и backend для локального кластера `kubedeploy`.
Генерируются Deployment, Service и HTTPRoute для каждого приложения.
Namespace `kubedeploy-demo` разрешает маршрутам подключаться к общему Gateway.

Требования: Docker Desktop, k3d, kubectl, make, bash, curl, python3 и
`score-k8s` **0.19.0** в PATH. Путь к генератору можно передать через
`SCORE_K8S=/path/to/score-k8s`. Версия проверяется перед рендером.

## Подготовка

Системный слой должен быть синхронизирован из `main` репозитория `platform`:

```bash
cd ../platform
make cluster-up
make bootstrap
make gateway-smoke
```

Соберите текущие приложения:

```bash
cd ../backend
make test image
cd ../frontend
make test image
cd ../environment
```

## Рендер и развёртывание

```bash
make render BACKEND_IMAGE=kubedeploy-backend:v0.1.0 FRONTEND_IMAGE=kubedeploy-frontend:v0.1.0
make deploy BACKEND_IMAGE=kubedeploy-backend:v0.1.0 FRONTEND_IMAGE=kubedeploy-frontend:v0.1.0
make status
make smoke
```

Оба образа нужно указать явно: тег, отличный от `latest`, или полный
`@sha256:...`. Отсутствующий образ или неправильный тег останавливает команду
до обращения к кластеру. Это ручной способ проверки окружения до появления
deploy-controller. Tag release, provenance verification и deployment request
добавляются следующими этапами. Argo CD управляет системным слоем, а приложения
разворачиваются явно из `environment`; автоматического deploy после мерджа нет.

Deploy проверяет готовность Gateway, импортирует доступные локальные образы
в k3d, создаёт namespace, выполняет server dry-run и Server-Side Apply с field
manager `kubedeploy-score`, ждёт оба rollout и запускает smoke. Registry-образ,
которого нет локально, скачивается кластером; для закрытого registry потребуется
настройка доступа. Для изменённого содержимого используйте новый тег или digest:
`IfNotPresent` и прежний Pod template не заменят уже запущенный контейнер.

Для server dry-run после создания namespace:

```bash
make validate BACKEND_IMAGE=kubedeploy-backend:v0.1.0 FRONTEND_IMAGE=kubedeploy-frontend:v0.1.0
```

Результат — `build/workloads.yaml`. Временный Score state удаляется после
генерации, внешних stateful-ресурсов пока нет. Patch template фиксирует labels
и selectors по имени workload, поэтому повторный рендер не меняет immutable
selector Deployment. `build/` и `.score-k8s/` исключены из Git.

## Трафик и доступ

Для Host `kubedeploy.local` действуют два маршрута:

| HTTPRoute | Путь | Service |
|---|---|---|
| `backend-http` | `/api` | `backend:8080` |
| `frontend-http` | `/` | `frontend:8080` |

Более конкретный `/api` направляет запросы в backend. Frontend отдаёт статику
и SPA fallback. Probes обоих приложений используют `/health` внутри кластера.
Caddy получает `BACKEND_UPSTREAM=backend:8080` для прямого доступа к frontend
Service. Через общий Gateway API обрабатывает маршрут `backend-http`.

`make smoke` проверяет Accepted/ResolvedRefs обоих HTTPRoute, JSON API,
HTML и JS, вложенный SPA-маршрут, HTTP 404 для отсутствующих ресурсов и чужого
hostname. Созданный для проверки port-forward завершается автоматически.

Для доступа в браузере оставьте port-forward работающим в отдельном терминале:

```bash
ENVOY_SERVICE="$(kubectl --context k3d-kubedeploy -n envoy-gateway-system get service \
  -l gateway.envoyproxy.io/owning-gateway-namespace=kubedeploy-gateway,gateway.envoyproxy.io/owning-gateway-name=kubedeploy \
  -o jsonpath='{.items[0].metadata.name}')"
kubectl --context k3d-kubedeploy -n envoy-gateway-system port-forward "service/$ENVOY_SERVICE" 18082:80
```

Откройте `http://kubedeploy.local:18082`, предварительно сопоставив
`kubedeploy.local` с `127.0.0.1` в локальном DNS или `/etc/hosts`.
Для curl изменение hosts не требуется:

```bash
curl --resolve kubedeploy.local:18082:127.0.0.1 http://kubedeploy.local:18082/api/version
```

## Runtime

Backend работает от UID/GID `65532:65532`, frontend — `10001:10001`.
Оба используют read-only root filesystem, dropped capabilities,
`allowPrivilegeEscalation=false`, RuntimeDefault seccomp и не получают
service account token. Frontend получает ограниченный memory-backed
`emptyDir` объёмом 16 MiB в `/tmp` для Caddy. CPU/memory limits и probes
заданы в Score.

Основа генерации: [Score CLI](https://docs.score.dev/docs/score-implementation/score-k8s/cli/)
и [patch templates](https://docs.score.dev/docs/score-implementation/score-k8s/patch-templates/).
