# KubeDeploy Environment

Описание backend для локального кластера `kubedeploy`. Score генерирует
Deployment, Service и HTTPRoute. Namespace `kubedeploy-demo` разрешает
подключение маршрута к общему Gateway из репозитория `platform`.

Требования: Docker Desktop, k3d, kubectl, make, bash, curl, python3 и
`score-k8s` **0.19.0** в PATH. Версия генератора проверяется перед рендером.
Путь к нему можно передать через `SCORE_K8S=/path/to/score-k8s`.

## Подготовка

В `platform` должны быть готовы кластер, Envoy Gateway и Gateway
`kubedeploy` в namespace `kubedeploy-gateway`:

```bash
cd ../platform
make cluster-up
make gateway-status
make gateway-smoke
```

Если конфигурация Gateway ещё не опубликована в `main`, примените локальные
файлы по инструкции `platform/README.md`. Argo CD управляет системным слоем;
Deployment, Service и HTTPRoute приложения применяются явно из `environment`.

Соберите текущий backend:

```bash
cd ../backend
make test
make image
cd ../environment
```

## Рендер и развёртывание

```bash
make render BACKEND_IMAGE=kubedeploy-backend:v0.1.0
make deploy BACKEND_IMAGE=kubedeploy-backend:v0.1.0
make status
make smoke
```

Без `BACKEND_IMAGE` команды render/deploy завершаются до обращения к кластеру.
Образ должен содержать явный тег, отличный от `latest`, или полный
`@sha256:...`. Сейчас используются локальные образы; tag-triggered release
и проверки provenance добавятся отдельным этапом.

`make deploy` проверяет готовность Gateway, импортирует доступный локально
образ в k3d, создаёт namespace, выполняет server dry-run, Server-Side Apply
с field manager `kubedeploy-score`, ждёт rollout и запускает smoke.
Registry-образ, которого нет в локальном Docker, скачивается самим кластером;
для закрытого registry потребуется отдельная настройка доступа.
При изменении содержимого образа используйте новый тег или digest:
`IfNotPresent` и неизменившийся Pod template не обновят старый контейнер.

Для read-only server dry-run после создания namespace:

```bash
make validate BACKEND_IMAGE=kubedeploy-backend:v0.1.0
```

Результат рендера — `build/backend.yaml`. Генерация использует временный
Score state и фиксированные имена; внешних stateful-ресурсов пока нет.
`build/` и `.score-k8s/` не входят в исходники. Повторный рендер с тем же
образом сохраняет имена Deployment, Service и HTTPRoute.
Patch template закрепляет `app.kubernetes.io/instance` и selectors по имени
workload: новое временное состояние Score не меняет immutable selector
существующего Deployment.

## Проверка трафика

HTTPRoute `backend-http` направляет `/api` с Host `kubedeploy.local`
в Service backend. Probes используют `/health` напрямую внутри кластера.
`make smoke` ждёт `Accepted=True` и `ResolvedRefs=True` у маршрута,
открывает port-forward к Service Envoy на свободном localhost-порту,
проверяет JSON `/api/version` и HTTP 404 для чужого hostname.
Port-forward автоматически завершается. Ожидаемый JSON:

```json
{"service":"kubedeploy-backend","version":"0.1.0"}
```

Backend работает от UID/GID `65532:65532`, с read-only filesystem,
запретом повышения привилегий, dropped capabilities, RuntimeDefault seccomp
и без service account token. CPU/memory limits и probes заданы в Score.

Исходные правила генерации: [Score CLI](https://docs.score.dev/docs/score-implementation/score-k8s/cli/),
[patch templates](https://docs.score.dev/docs/score-implementation/score-k8s/patch-templates/).
