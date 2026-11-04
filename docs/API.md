# API заявок

Все пути включают `/api`; Nginx сохраняет префикс, редиректов завершающего слеша нет. Канонические пути без завершающего `/`. Тела запросов — JSON. Суммы — целые рубли.

Машиночитаемый контракт — `docs/openapi.json`. После изменения моделей или маршрутов пересоберите backend и выполните `python scripts/export_openapi.py`; CI проверяет соответствие контракта образу через `--check`.

| Метод и путь | Доступ | Результат |
| --- | --- | --- |
| GET `/api/health` | Публичный | Состояние соединения с БД, версия и сборка backend |
| GET `/api/services` | Публичный | Все активные услуги с диапазонами бюджета |
| POST `/api/applications` | Публичный | Создание заявки и метрик одной транзакцией |
| GET `/api/admin/docs` | JWT cookie | Swagger с ресурсами на собственном сервере |
| GET `/api/admin/openapi.json` | JWT cookie | Машиночитаемый OpenAPI-контракт |
| GET/POST `/api/admin/services` | JWT cookie | Полный каталог / создание услуги |
| GET/PUT/DELETE `/api/admin/services/{id}` | JWT cookie | Чтение / полная замена / деактивация услуги |
| GET `/api/admin/applications` | JWT cookie | Заявки с метриками; limit 1–100, offset ≥ 0 |
| GET/PATCH/DELETE `/api/admin/applications/{uuid}` | JWT cookie | Чтение / смена статуса / удаление вместе с метриками |
| GET `/api/admin/orders` | JWT cookie | Объект items/total/offset/limit; q, status, service_id, priority, sort |
| GET `/api/admin/orders/{uuid}` | JWT cookie | Карточка с автоматической и ручной оценкой |
| PATCH `/api/admin/applications/{uuid}/priority` | JWT cookie + CSRF | priority: high/medium/low/null, comment обязателен при ручной оценке |
| GET `/api/admin/dashboard` | JWT cookie | Число заявок, распределение по статусам и услугам |
| GET/POST `/api/admin/admins`, PATCH `/{uuid}` | JWT cookie + CSRF для записи | Управление аккаунтами без выдачи хешей |
| POST `/api/auth/setup/check`, `/api/auth/setup` | Одноразовый код | Проверка приглашения / первый аккаунт |
| POST `/api/auth/login` | Логин/пароль | Установить HttpOnly cookie и вернуть CSRF |
| GET `/api/auth/me` | JWT cookie | Текущий аккаунт и CSRF-токен |
| POST `/api/auth/logout`, `/api/auth/password` | JWT cookie + CSRF | Выход / смена своего пароля с отзывом сеансов |
| POST `/api/analytics/visits` | consent=true | Посещение и секрет записи |
| POST `/api/analytics/batches` | Секрет посещения | Пакет событий с дедупликацией по UUID |
| GET `/api/admin/analytics` | JWT cookie | Периоды 1/7/30 дней, device, kind и тепловая карта |

Все изменяющие административные запросы требуют X-CSRF-Token, не только строки таблицы с явной пометкой CSRF. Вход и первичная настройка требуют Content-Type: application/json и X-Requested-With: CustomerOrders. Подробности: [ADMIN.md](ADMIN.md), [PRIORITIZATION.md](PRIORITIZATION.md), [ANALYTICS.md](ANALYTICS.md). Старый HTTP Basic отключён. Swagger использует сеанс после входа на /admin.

Публичное создание возвращает только UUID и подтверждение, без контактов. `201` означает новую запись; `200` — повтор уже принятой заявки. Полные данные доступны только администратору. Деактивация услуги сохраняет историю уже созданных заявок.

## Заявка

```json
{
  "service_id": 1,
  "name": "Анна",
  "email": "anna@example.com",
  "phone": null,
  "telegram": null,
  "task_description": "Нужно собирать заявки с сайта в CRM и уведомлять ответственного.",
  "company": null,
  "niche": null,
  "company_size": null,
  "role": null,
  "budget": null,
  "desired_deadline": null,
  "preferred_contact": "email",
  "contact_time": null,
  "comment": null,
  "metrics": {"elapsed_ms": 30000, "submission_attempts": 1, "returning_visitor": false}
}
```

Обязательны услуга, имя, описание от 10 символов, хотя бы один контакт и базовые метрики. Если указан предпочтительный канал, соответствующий контакт обязателен. `budget: null` означает «Нужна оценка». Числовой бюджет должен попадать в текущий диапазон услуги.

Frontend посылает UUID в заголовке `Idempotency-Key`. Повтор с тем же ключом и теми же данными не создаёт вторую заявку, даже если меняется счётчик попыток. Другие данные с уже использованным ключом получают `409`. Без заголовка каждое обращение считается новой заявкой.

Время до отправки ограничено 24 часами, попытки — от 1 до 100. Признак повторного посещения берётся из локального флага браузера; контактные данные не сохраняются в localStorage. Метрики поступают от клиента и не являются доверенным аудитом поведения.

Ошибки `422` содержат только имена полей и сообщения, без исходных значений. `404` — недоступная услуга или запись; `401` — нет административной авторизации; `409` — конфликт slug или повторной отправки; `503` — недоступна БД/backend. Nginx ограничивает размер JSON 32 КиБ и общий поток создания заявок 30 запросами в минуту с burst 10; это общий лимит сайта, не персональная квота.

## Начальные услуги

Каталог изначально пуст. Через Swagger создайте три записи. Значения бюджета — предварительные ориентиры для демонстрационного каталога и могут быть изменены.

| slug | Название | budget_min | budget_max |
| --- | --- | --- | --- |
| lead-processing | Обработка заявок | 30000 | 120000 |
| system-integration | Интеграция систем | 50000 | 200000 |
| telegram-bot | Клиентский Telegram-бот | 40000 | 150000 |

Пример POST `/api/admin/services`:

```json
{
  "slug": "lead-processing",
  "title": "Обработка заявок",
  "description": "Сбор обращений с сайта, распределение и уведомления ответственных.",
  "budget_min": 30000,
  "budget_max": 120000,
  "currency": "RUB",
  "is_active": true
}
```

Для остальных записей: «Обмен данными между CRM, сайтом и другими рабочими сервисами» и «Диалог с клиентами, сбор заявок и уведомления в Telegram». Публичный GET должен возвращать все три услуги.
