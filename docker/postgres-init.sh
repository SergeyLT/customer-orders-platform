#!/bin/sh
# Только для нового локального тома. Рабочую БД подготавливает отдельный скрипт.
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
\getenv app_password APP_DB_PASSWORD
SELECT format('CREATE ROLE orders_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') \gexec
CREATE SCHEMA orders AUTHORIZATION orders_app;
SELECT format('GRANT CONNECT ON DATABASE %I TO orders_app', current_database()) \gexec
SQL
