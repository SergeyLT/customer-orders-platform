"""Развернуть конкретный digest через Coolify и проверить версию веб-компонента."""

import argparse
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """Не пересылать токен API и не проверять чужой адрес после редиректа."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect())


def https_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
    ):
        raise ValueError("Нужен HTTPS-адрес без пути, параметров и учётных данных")
    return value.rstrip("/")


def request_json(url: str, *, method: str = "GET", token: str = "", body=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = Request(url, data=data, headers=headers, method=method)
    with OPENER.open(request, timeout=20) as response:
        raw = response.read(1024 * 1024)
    return json.loads(raw) if raw else None


def trigger_deployment(base: str, uuid: str, token: str, image: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", uuid):
        raise ValueError("Некорректный UUID приложения")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.:-]*/[a-z0-9/_.-]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("Нужен полный адрес образа с sha256 digest")
    base = https_origin(base)
    request_json(
        f"{base}/api/v1/applications/{uuid}/envs", method="PATCH", token=token,
        body={"key": "WEB_IMAGE", "value": image, "is_preview": False, "is_literal": True},
    )
    query = urlencode({"uuid": uuid, "force": "false"})
    request_json(f"{base}/api/v1/deploy?{query}", method="POST", token=token)


def wait_for_release(base: str, version: str, release: str, *, timeout: float = 600, interval: float = 10) -> None:
    base = https_origin(base)
    deadline = time.monotonic() + timeout
    while True:
        try:
            query = urlencode({"release": release})
            health = request_json(f"{base}/health?{query}")
            if (
                isinstance(health, dict) and health.get("status") == "ok"
                and health.get("component") == "web" and health.get("version") == version
                and health.get("release") == release
            ):
                print(f"Веб-компонент обновлён: {version}, сборка {release}.")
                return
        except (OSError, ValueError, HTTPError, URLError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Не подтверждена ожидаемая сборка. Проверьте деплой в Coolify; автоматический откат не выполняется.")
        time.sleep(min(interval, remaining))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.version):
            raise ValueError("Версия должна быть SHA коммита из 40 символов")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", args.release):
            raise ValueError("Некорректный идентификатор сборки")
        token = os.environ["COOLIFY_TOKEN"]
        if not token:
            raise ValueError("Не задан COOLIFY_TOKEN")
        public_url = https_origin(os.environ["PUBLIC_BASE_URL"])
        trigger_deployment(os.environ["COOLIFY_URL"], os.environ["COOLIFY_APP_UUID"], token, args.image)
        print("Запуск деплоя принят. Ожидаем нужную сборку веб-компонента.")
        wait_for_release(public_url, args.version, args.release)
    except HTTPError as error:
        # Не выводим ответ API: он может содержать конфигурацию приложения.
        print(f"Ошибка Coolify API: HTTP {error.code}. Проверьте права токена и конфигурацию.", file=sys.stderr)
        raise SystemExit(1) from None
    except (KeyError, OSError, ValueError, TimeoutError):
        print("Деплой не подтверждён. Проверьте параметры окружения, доступность API и состояние приложения в Coolify.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
