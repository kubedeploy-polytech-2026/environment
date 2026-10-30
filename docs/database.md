# PostgreSQL

`make database-up` устанавливает локальный Helm chart `database/postgres`.
Это отдельная операция оператора; деплой frontend/backend не пересоздаёт БД.
PostgreSQL 17.11 закреплён по digest, данные находятся на PVC `data-postgres-0`.
PVC сохраняется при удалении или уменьшении StatefulSet.

Пароли создаются один раз в Secret `postgres-credentials` и не попадают в Helm
values или Git. Ключ `url` предназначен для backend. При повторном запуске
пароли сохраняются. Прикладная роль `kubedeploy` не имеет SUPERUSER и владеет
схемой `app`. Состояние: `make database-status`.

`make database-smoke` записывает строку в служебную таблицу, пересоздаёт Pod,
повторяет Helm upgrade и проверяет строку, PVC и неизменность реквизитов.

CI публикует отчёт Trivy для стороннего образа. В `gosu` есть HIGH/CRITICAL
находки; при запуске от UID 70 эта утилита не вызывается. Находки не подавляются,
но этот отчёт не является блокирующим gate для PostgreSQL.
