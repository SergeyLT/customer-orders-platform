"""Проверки отказов и выбора конкретного релиза без обращения к Coolify."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import deploy


class DeploymentTests(unittest.TestCase):
    def test_update_digest_before_deployment(self):
        image = "docker-registry.example.com/customer-orders-platform/web@sha256:" + "a" * 64
        with patch.object(deploy, "request_json", return_value={}) as request:
            deploy.trigger_deployment("https://coolify.example.com", "app123", "test-token", image)
        calls = request.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["method"], "PATCH")
        self.assertEqual(calls[0].kwargs["body"]["value"], image)
        self.assertEqual(calls[1].kwargs["method"], "POST")
        self.assertIn("/deploy?uuid=app123&force=false", calls[1].args[0])

    def test_update_failure_does_not_trigger_deploy(self):
        with patch.object(deploy, "request_json", side_effect=OSError("API unavailable")) as request:
            with self.assertRaises(OSError):
                deploy.trigger_deployment("https://coolify.example.com", "app123", "test-token", "registry.example.com/web@sha256:" + "a" * 64)
        self.assertEqual(request.call_count, 1)

    def test_mutable_tag_rejected_before_api_call(self):
        with patch.object(deploy, "request_json") as request:
            with self.assertRaises(ValueError):
                deploy.trigger_deployment("https://coolify.example.com", "app123", "test-token", "registry.example.com/web:latest")
        request.assert_not_called()

    def test_old_build_with_same_commit_is_not_success(self):
        health = {"status": "ok", "component": "web", "version": "a" * 40, "release": "previous-build"}
        with patch.object(deploy, "request_json", return_value=health):
            with self.assertRaises(TimeoutError):
                deploy.wait_for_release("https://orders.example.com", "a" * 40, "new-build", timeout=0)

    def test_expected_release_is_success(self):
        health = {"status": "ok", "component": "web", "version": "a" * 40, "release": "new-build"}
        with patch.object(deploy, "request_json", return_value=health):
            deploy.wait_for_release("https://orders.example.com", "a" * 40, "new-build", timeout=0)

    def test_origin_rejects_http_credentials_and_paths(self):
        for value in ("http://coolify.example.com", "https://user:password@example.com", "https://example.com/api", "https://example.com?token=x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                deploy.https_origin(value)

    def test_api_redirect_is_not_followed(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/unexpected-target")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError):
                deploy.request_json(f"http://127.0.0.1:{server.server_port}/api", token="test-token")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(received, ["/api"])


if __name__ == "__main__":
    unittest.main()
