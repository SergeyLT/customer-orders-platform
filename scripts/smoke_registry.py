"""Проверить авторизацию Registry с передачей переменных ресурса в контейнер."""

import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def check() -> None:
    temporary_root = ROOT / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="registry-check-", dir=temporary_root) as directory:
        folder = Path(directory)
        password = secrets.token_urlsafe(24)
        result = subprocess.run(
            ["docker", "run", "--rm", "-i", "--entrypoint", "htpasswd", "httpd:2.4-alpine", "-niB", "smoke-user"],
            input=password + "\n", text=True, capture_output=True, check=True,
        )
        auth_file = folder / "htpasswd"
        auth_file.write_text(result.stdout.strip() + "\n", encoding="utf-8")
        auth_file.chmod(0o600)
        http_secret = secrets.token_hex(32)
        environment = dict(os.environ, COP_REGISTRY_AUTH_FILE=str(auth_file), REGISTRY_HTTP_SECRET=http_secret)
        # Эмулируем инъекцию переменной ресурса Coolify внутрь контейнера.
        override = folder / "override.json"
        override.write_text(json.dumps({"services": {"registry": {
            "environment": {"COP_REGISTRY_AUTH_FILE": str(auth_file)},
            "ports": ["127.0.0.1:0:5000"],
        }}}), encoding="utf-8")
        env_file = folder / "empty.env"
        env_file.write_text("", encoding="utf-8")
        command = [
            "docker", "compose", "-p", "orders-registry-smoke-" + secrets.token_hex(4),
            "--env-file", str(env_file), "-f", str(ROOT / "compose.registry.yaml"), "-f", str(override),
        ]

        def compose(*arguments: str) -> str:
            return subprocess.check_output(
                command + list(arguments), env=environment, text=True, stderr=subprocess.PIPE,
            ).strip()

        def status(url: str, supplied_password: str | None = None) -> int:
            headers = {}
            if supplied_password is not None:
                credentials = base64.b64encode(("smoke-user:" + supplied_password).encode()).decode()
                headers["Authorization"] = "Basic " + credentials
            try:
                with urlopen(Request(url, headers=headers), timeout=3) as response:
                    return response.status
            except HTTPError as error:
                return error.code

        try:
            compose("up", "-d")
            address = compose("port", "registry", "5000").splitlines()[0]
            endpoint = "http://" + address + "/v2/"
            deadline = time.monotonic() + 30
            while True:
                try:
                    if (status(endpoint), status(endpoint, password), status(endpoint, "wrong-password")) == (401, 200, 401):
                        break
                except (OSError, URLError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Registry не прошёл проверку авторизации за 30 секунд")
                time.sleep(0.5)
            print("Registry: запуск с переменной пути, анонимный 401, авторизованный 200, неверный пароль 401 — OK.")
        finally:
            compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    check()
