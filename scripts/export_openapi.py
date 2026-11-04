"""Экспортировать OpenAPI из backend-образа или проверить отсутствие дрейфа контракта."""

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="customer-orders-backend:check")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = subprocess.check_output([
        "docker", "run", "--rm", "--network", "none",
        "-e", "APP_DB_PASSWORD=contract-placeholder-password",
        "-e", "JWT_SECRET=contract-placeholder-jwt-secret-at-least-32",
        "--entrypoint", "python", args.image, "-c",
        "import json; from customer_orders.main import app; print(json.dumps(app.openapi()))",
    ], text=True)
    contract = json.loads(raw)
    output = ROOT / "docs" / "openapi.json"
    if args.check:
        if not output.exists() or json.loads(output.read_text(encoding="utf-8")) != contract:
            raise SystemExit("OpenAPI изменился. Выполните python scripts/export_openapi.py и проверьте diff.")
        print("OpenAPI: сохранённый контракт соответствует backend.")
    else:
        output.write_text(json.dumps(contract, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print("OpenAPI сохранён в docs/openapi.json.")


if __name__ == "__main__":
    main()
