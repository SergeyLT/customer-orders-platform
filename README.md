# Customer Orders Platform

[![CI/CD](https://github.com/SergeyLT/customer-orders-platform/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SergeyLT/customer-orders-platform/actions/workflows/ci.yml?query=branch%3Amain)

Инфраструктурная основа сервиса приёма и обработки заказов клиентов. Проект включает веб-контейнер Nginx, PostgreSQL, pgAdmin, собственный Docker Registry и доставку релизов через GitHub Actions и Coolify.

Backend и форма заказа находятся в планах. Стартовая страница сообщает о подготовке сервиса; `/api` и `/api/*` отвечают `503`, не принимая заказы. `/health` подтверждает работу и версию веб-контейнера, но не готовность всей системы.

## Состав

| Компонент | Назначение | Доступ |
| --- | --- | --- |
| Nginx | Веб-страница и точка будущего API | `https://orders.example.com` через Traefik |
| PostgreSQL 17 | Хранилище будущих заказов | Внутренняя сеть проекта |
| pgAdmin | Администрирование PostgreSQL | Loopback VPS и SSH-туннель |
| Distribution Registry | Хранение Docker-образов | `https://docker-registry.example.com` через Traefik, с авторизацией |
| GitHub Actions | Проверки, сборка и публикация релиза | GitHub |
| Coolify | Запуск Compose и управление деплоем | Собственная установка Coolify |

`example.com` во всех примерах заменяется вашим доменом. Имена `orders` и `docker-registry` — рекомендуемые поддомены; конфигурация не привязана к конкретному серверу или DNS-провайдеру.

Описание сетей и цепочки доставки: [ARCHITECTURE.md](ARCHITECTURE.md).

## Требования

- Linux-сервер с Docker Engine и актуальным плагином Docker Compose.
- Coolify с работающим Traefik, доступом к Git-репозиторию и API.
- DNS-записи `orders` и `docker-registry`, направленные на сервер; при использовании AAAA IPv6 также должен работать.
- Внешние TCP `80/443` для прокси и выпуска сертификатов, SSH-доступ администратора.
- GitHub-репозиторий с Actions и runner `ubuntu-latest` для Linux amd64. Другую архитектуру следует явно настроить и проверить.
- Python 3.12+ для скриптов. Сторонние Python-пакеты не требуются.

Не публикуйте порты PostgreSQL и Registry на всех интерфейсах. pgAdmin по умолчанию привязан к `127.0.0.1:5050`. Наличие UFW само по себе не гарантирует фильтрацию опубликованных Docker-портов: см. [Docker и межсетевые экраны](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## Файлы проекта

- `compose.registry.yaml` — отдельный инфраструктурный ресурс Registry.
- `compose.coolify.yaml` — приложение: web, PostgreSQL, pgAdmin.
- `Dockerfile`, `nginx/`, `web/` — образ веб-компонента.
- `.github/workflows/ci.yml` — CI/CD.
- `scripts/create_registry_user.py` — создание и ротация bcrypt-паролей Registry.
- `scripts/deploy.py` — установка digest в Coolify, запуск деплоя и проверка сборки.
- `.env.example` — примеры переменных без рабочих доступов. Это не готовая production-конфигурация.

## Первый запуск

Порядок важен: сначала Registry, затем первая публикация, затем приложение. Git-репозиторий создаёт и публикует владелец проекта.

### Подготовка Registry

1. Создайте DNS-запись `docker-registry.example.com`.
2. На машине с Docker из корня проекта создайте пользователей:

   ```sh
   python scripts/create_registry_user.py ci-publisher
   python scripts/create_registry_user.py server-deployer
   ```

   Скрипт запросит пароль дважды, передаст его `htpasswd` через stdin и сохранит bcrypt-хеш в `.secrets/registry.htpasswd`. Используются утилиты из `httpd:2.4-alpine`; пароль не попадает в аргументы процесса. На Windows ограничьте доступ к файлу средствами ACL; `chmod` там не обеспечивает Linux-права.

3. Передайте файл на сервер через SSH/SCP и разместите по абсолютному пути, например `/data/customer-orders-platform/registry/auth/htpasswd`. Если файл загружен в домашний каталог, на сервере можно выполнить:

   ```sh
   sudo install -d -m 700 /data/customer-orders-platform/registry/auth
   sudo install -m 600 ~/registry.htpasswd /data/customer-orders-platform/registry/auth/htpasswd
   ```

   Исходный файл в домашнем каталоге после проверки удалите. Файл на сервере должен существовать до запуска контейнера; пути на компьютере администратора и VPS различаются.

4. В Coolify создайте отдельное приложение из Git с Build Pack **Docker Compose** и файлом `compose.registry.yaml`. Задайте:

   | Переменная | Значение |
   | --- | --- |
   | `COP_REGISTRY_AUTH_FILE` | Абсолютный путь к htpasswd на VPS |
   | `REGISTRY_HTTP_SECRET` | Постоянный случайный секрет, например результат `python -c "import secrets; print(secrets.token_hex(32))"` |

   Это секрет сессий загрузки, а не пароль пользователя Registry. Не меняйте его при каждом деплое.

   Переменная пути названа `COP_REGISTRY_AUTH_FILE`, чтобы не конфликтовать с конфигурационным префиксом Distribution `REGISTRY_`. Coolify может передать переменные ресурса внутрь контейнера. Не создавайте в этом ресурсе старую переменную `REGISTRY_AUTH_FILE`: Registry интерпретирует её как настройку авторизации и завершится с ошибкой разбора конфигурации. Для перехода со старой версии удалите её из настроек Coolify и задайте `COP_REGISTRY_AUTH_FILE` с тем же путём.

5. Назначьте домен сервису `registry`: `https://docker-registry.example.com:5000`. В этом поле Coolify `:5000` обозначает **внутренний** порт; Docker-клиенты используют `docker-registry.example.com` без порта. Отключите **Connect To Predefined Network**, не назначайте домены другим компонентам.
6. Запустите ресурс и проверьте HTTPS. Без авторизации `/v2/` должен отвечать `401` с `WWW-Authenticate`, а после авторизации — `200`:

   ```sh
   curl -i https://docker-registry.example.com/v2/
   curl -i --user ci-publisher https://docker-registry.example.com/v2/
   docker login docker-registry.example.com --username ci-publisher
   ```

   Команды с именем пользователя запросят пароль. Не включайте для этого домена страницу интерактивного входа или внешний auth-портал: Docker ожидает Registry API. Проверяйте сертификат штатно; не используйте `-k` и `insecure-registries` для production.

### Первая публикация из Actions

Создайте GitHub Environment `production`. В **repository variables** настройте флаги, поскольку условия запуска jobs вычисляются до загрузки environment variables:

| Repository variable | Начальное значение |
| --- | --- |
| `PUBLISH_ENABLED` | `true`, когда Registry готов |
| `DEPLOY_ENABLED` | `false`, пока приложение в Coolify не настроено |

В environment `production` добавьте:

| Variable | Значение |
| --- | --- |
| `REGISTRY_HOST` | `docker-registry.example.com`, без схемы и пути |
| `COOLIFY_URL` | `https://coolify.example.com`, без `/api` |
| `COOLIFY_APP_UUID` | UUID будущего приложения, не Registry |
| `PUBLIC_BASE_URL` | `https://orders.example.com`, без внутреннего порта |

| Secret | Назначение |
| --- | --- |
| `REGISTRY_USERNAME` | Например, `ci-publisher` |
| `REGISTRY_PASSWORD` | Его пароль |
| `COOLIFY_TOKEN` | Токен API для изменения переменной приложения и запуска деплоя |

Для первой публикации достаточно настроить Registry и его доступы; параметры Coolify нужны на следующем этапе. Флагов нет — работают только проверки. Environment production и правила его доступа ограничьте доверенной веткой `main`.

После push в `main` или ручного запуска workflow на `main` Actions проверит конфигурацию и скрипты, соберёт образ, запустит его HTTP-проверки и опубликует **тот же проверенный образ** через временный artifact. Повторной сборки в publish-job нет. Тег содержит SHA, run ID и номер попытки. В Summary задания появятся полный digest, SHA и идентификатор сборки — сохраните их для первого запуска и отката.

### Приложение в Coolify

1. Создайте второе приложение из того же Git-репозитория: Docker Compose, файл `compose.coolify.yaml`.
2. Отключите автоматический деплой при push из Git: запуск релиза выполняет Actions после проверок.
3. В настройках реестров сервера Coolify выполните вход в `docker-registry.example.com` как `server-deployer`. При настройке через SSH вход выполняется от пользователя, настроенного для этого сервера в Coolify, не обязательно от пользователя вашей интерактивной SSH-сессии. Проверьте доступ к домену Registry с самого VPS.
4. Задайте `WEB_IMAGE` полным адресом с digest из Summary. Нулевой digest в `.env.example` — не существующий образ. Настройте runtime-переменные `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD`, `PGADMIN_HOST_PORT` по примеру. Используйте разные случайные пароли; значения передаются через Coolify, а не файлом `.env` из Git.
5. Назначьте **только** сервису `web` домен `https://orders.example.com:8080`. Внешний адрес останется `https://orders.example.com`. Не назначайте домены PostgreSQL и pgAdmin; отключите **Connect To Predefined Network**. Перед запуском проверьте сгенерированный Coolify Compose: PostgreSQL должен оставаться только в сети database, pgAdmin — на loopback.
6. Выполните первый Deploy, проверьте страницу и `/health`. В ответе будут `status`, `component`, `version`, `release`.
7. Добавьте UUID этого приложения в GitHub и токен Coolify с правами на **изменение переменных** и **деплой**. Одного deploy-only разрешения недостаточно. Установка Coolify должна поддерживать `PATCH /api/v1/applications/{uuid}/envs` и `POST /api/v1/deploy`.
8. Поставьте repository variable `DEPLOY_ENABLED=true`. Следующий workflow обновит `WEB_IMAGE` digest-адресом, вызовет деплой и дождётся ожидаемой сборки.

Скрипт не следует HTTP-редиректам API и не выводит сырые ответы с конфигурацией. `COOLIFY_URL` должен сразу содержать окончательный HTTPS-origin. Ошибка или таймаут не запускают автоматический откат; проверьте приложение в Coolify.

### Доступ к pgAdmin

Из локального терминала создайте туннель, подставив SSH-пользователя, сервер и при необходимости ключ:

```sh
ssh -N -L 5050:127.0.0.1:5050 user@server
```

Откройте `http://127.0.0.1:5050`, войдите с учётными данными pgAdmin и создайте подключение: host `postgres`, port `5432`, имя базы и пользователь из настроек приложения. Пароль PostgreSQL вводите в pgAdmin, не в Compose репозитория. Если 5050 занят на VPS, измените `PGADMIN_HOST_PORT` и правую часть туннеля; если занят локально — левую.

Инициализационный пользователь PostgreSQL имеет административные права. Для будущего backend создадим отдельного пользователя с ограниченными правами и миграциями. Переменные `POSTGRES_*` и `PGADMIN_DEFAULT_*` задают начальные учётные данные: смена значения в Coolify не заменяет пароль в уже созданной базе или профиле pgAdmin.

## Локальные проверки

Запускайте из корня проекта с работающим Docker:

```sh
python scripts/check_compose.py
python -m unittest discover -s tests -v
docker build -t customer-orders-web:check .
python scripts/smoke_image.py customer-orders-web:check
python scripts/smoke_registry.py
```

Проверки скриптов не обращаются к реальному Coolify. HTTP-проверка запускает временный контейнер с read-only filesystem и без Linux capabilities, проверяет `/health`, страницу, `503` API и `404`, затем удаляет контейнер. Проверка Registry эмулирует передачу переменной пути в контейнер, проверяет анонимный и авторизованный запросы и удаляет временный проект с его томом. Домены, HTTPS и настройки Coolify требуют отдельной проверки в целевом окружении.

## Обновление и откат

Обычный релиз: push в `main` → проверки → сборка и HTTP-проверка → публикация → установка digest → деплой → подтверждение SHA и сборки. Workflow сериализует production-запуски и не прерывает уже запущенный деплой.

Для отката остановите новые автоматические релизы (`DEPLOY_ENABLED=false`), выберите сохранённый digest предыдущего релиза, задайте его в `WEB_IMAGE` в Coolify и выполните Redeploy. Проверьте `/health` и доступность страницы. После устранения проблемы снова включите деплой. Возврат образа не откатывает данные или миграции будущего backend.

Версии сторонних сервисов изменяются отдельно через Compose с проверкой совместимости и резервной копией. PostgreSQL закреплён на major 17 и получает patch-обновления тега `17-alpine`; для побитовой фиксации сторонних образов закрепите также digest. Переход на другой major PostgreSQL требует миграции данных.

## Хранение и восстановление

- Registry: том `registry_data`, htpasswd, секрет `REGISTRY_HTTP_SECRET`, конфигурация и DNS. Регулярно сохраняйте резервную копию вне VPS. Для согласованной файловой копии остановите запись в Registry или сам ресурс на время копирования. Точные имена томов определяются развёртыванием Coolify; не угадывайте их по имени из Compose.
- PostgreSQL: регулярный `pg_dump` в custom-формате и резервирование нужных ролей/настроек. Храните копии вне VPS и проверяйте восстановление в отдельную базу. На Windows не перенаправляйте бинарный dump через старый PowerShell: сохраняйте его внутри контейнера и используйте `docker cp`.
- pgAdmin: том `pgadmin_data` содержит настройки интерфейса, но не заменяет backup PostgreSQL.
- Постоянные тома сохраняются при пересоздании контейнеров; не выполняйте удаление томов при штатном обновлении.

Смена пользователя Registry: `python scripts/create_registry_user.py ci-publisher --replace`, установка обновлённого файла на VPS, затем **пересоздание контейнера Registry** через Coolify (атомарная замена файла может оставить старый inode в существующем bind mount). Обновите соответствующие GitHub Secrets или логин сервера. Простого изменения файла без перезапуска недостаточно.

Базовый htpasswd проверяет пользователей, но не разделяет роли публикации и чтения: оба пользователя могут выполнять push/pull. Для строгого разграничения нужен token-auth сервер или отдельные правила авторизации прокси. Пароли Registry не должны совпадать с паролями PostgreSQL и pgAdmin.

Удаление манифестов Registry по умолчанию выключено. Не включайте автоматическую очистку без политики хранения. Сохраняйте текущий релиз и версии для отката; удаление тега не гарантирует освобождения слоёв. Garbage collection выполняется при остановленных записях/read-only режиме, сначала с `--dry-run`, по [документации Distribution](https://distribution.github.io/distribution/about/garbage-collection/). Не запускайте `--delete-untagged` без проверки OCI indexes и связанных манифестов. Следите за размером тома и свободным местом VPS.

## Альтернативы

### Watchtower

С Watchtower цепочка выглядела бы так: Actions проверяет код и публикует образ под отслеживаемым тегом → Watchtower периодически проверяет Registry → скачивает новый образ и пересоздаёт выбранный контейнер. Понадобятся доступ к Docker socket, credentials Registry и явный выбор контейнеров через enable-метки и scope. Базы и несвязанные приложения не должны входить в область обновления.

В выбранной схеме Actions передаёт Coolify точный digest только после проверок; проверка версии завершает workflow. Не нужно ждать опроса изменяемого тега, а состояние релиза видно в цепочке CI/CD. У контейнера остаётся один механизм управления обновлениями. Для перехода на Watchtower необходимо отключить CD через Coolify для этих контейнеров и спроектировать независимое управление их запуском.

Оригинальный [containrrr/watchtower](https://github.com/containrrr/watchtower) архивирован 17 декабря 2025 года. Для Docker 29 зарегистрирована [проблема старого API](https://github.com/containrrr/watchtower/issues/2122). Если выбирать этот подход, потребуется отдельно оценить поддерживаемую реализацию и её совместимость.

### GitHub Container Registry

GHCR — альтернативное хранилище образов, совместимое с выбранной цепочкой Actions → Coolify. Клиентские данные и PostgreSQL при этом продолжают храниться на VPS.

| Критерий | Собственный Registry, выбранный вариант | GHCR |
| --- | --- | --- |
| Размещение образов | Постоянный том на VPS | Инфраструктура GitHub |
| Публикация Actions | Пользователь Registry и GitHub Secrets | Обычно `GITHUB_TOKEN` с `packages: write` |
| Чтение приватных образов | Логин собственного Registry | Учётные данные с `read:packages` и доступом к пакету |
| HTTPS и обслуживание | Coolify/Traefik и администратор VPS | GitHub |
| Место, очистка, backup | Ответственность владельца VPS | Правила и возможности GitHub Packages |
| Потеря VPS | Нужен backup или повторная сборка | Образы остаются в GHCR |
| Контроль хранилища | Полный контроль, собственная политика | Зависимость от GitHub и его условий |

Для перехода на GHCR нужно изменить домен и namespace образа (обычно `ghcr.io/<owner>/<repository>/web`), разрешить workflow `packages: write`, заменить авторизацию публикации на `github.actor`/`GITHUB_TOKEN`, настроить сервер Coolify на чтение пакета и передавать новый адрес с digest в `WEB_IMAGE`. Проверка `REGISTRY_HOST` уже принимает `ghcr.io`, но фиксированный путь `customer-orders-platform/web` в workflow надо заменить на namespace владельца. Собственный ресурс Registry после переноса необходимых релизов можно вывести из эксплуатации. Одновременная публикация в оба хранилища сейчас не реализована.

Преимущества GHCR: меньше сервисов на VPS, меньше задач обслуживания, интеграция прав с GitHub и сохранение образов при потере сервера. Собственный Registry выбран для независимого размещения и контроля образов. Подробнее: [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Развитие

Backend TBD: API заказов, схема и миграции PostgreSQL, ограниченная роль БД, прикладная валидация, защита от злоупотреблений, форма заказа, readiness и интеграционные проверки. До реализации этих компонентов платформа не принимает реальные заказы.
