"""Проверить HTTP-контракт образа в контейнере с production-ограничениями."""

import argparse
import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def get(url: str) -> tuple[int, bytes]:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def check(image: str, version: str, release: str) -> None:
    container = docker(
        "run", "--rm", "-d", "--read-only", "--tmpfs", "/tmp:rw,size=32m,mode=1777",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "-p", "127.0.0.1:0:8080", image,
    )
    try:
        address = docker("port", container, "8080/tcp").splitlines()[0]
        base = "http://" + address
        deadline = time.monotonic() + 30
        while True:
            try:
                status, body = get(base + "/health")
                if status == 200:
                    break
            except (OSError, URLError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Контейнер не начал отвечать за 30 секунд")
            time.sleep(0.5)
        health = json.loads(body)
        expected = {"status": "ok", "component": "web", "version": version, "release": release}
        if health != expected:
            raise RuntimeError("Метаданные запущенного образа не соответствуют сборке")
        if get(base + "/")[0] != 200:
            raise RuntimeError("Стартовая страница недоступна")
        for path in ("/api/health", "/api/services"):
            status, body = get(base + path)
            if status != 503 or json.loads(body).get("error") != "backend_not_available":
                raise RuntimeError("API без backend должен явно отвечать 503")
        if get(base + "/missing-page")[0] != 404:
            raise RuntimeError("Неизвестный маршрут должен отвечать 404")
        docker("exec", container, "nginx", "-t")
        print("Образ: HTTP, версия, отсутствие backend и конфигурация Nginx проверены.")
    finally:
        docker("rm", "-f", container)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--version", default="dev")
    parser.add_argument("--release", default="local")
    arguments = parser.parse_args()
    check(arguments.image, arguments.version, arguments.release)
