"""Loopback-only instructor HTTP service. Basic authentication on every route, including
downloads, plus a custom header on writes (no CORS). Run on the same host as oTree.
The participant app has no route into the administrator command dispatcher."""
import base64
import hmac
import json
import os
from contextlib import closing
from pathlib import Path
from wsgiref.simple_server import make_server
from ledger import connect, view, command
from exports import COLUMNS, csv_bytes

ROOT = Path(__file__).resolve().parent


def application(env, start_response):
    """Closed route list; sessions and table names never become file-system paths."""

    def reply(status, data, mime="application/json", headers=()):
        start_response(
            status,
            [
                ("Content-Type", mime),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "DENY"),
                *headers,
            ],
        )
        return [data if isinstance(data, bytes) else json.dumps(data).encode()]

    pw = os.environ.get("OTREE_ADMIN_PASSWORD")
    expected = "Basic " + base64.b64encode(("admin:" + str(pw)).encode()).decode()
    if not pw or not hmac.compare_digest(
        expected.encode(), env.get("HTTP_AUTHORIZATION", "").encode()
    ):
        return reply(
            "401 Unauthorized",
            {"error": "Instructor login required"},
            headers=[("WWW-Authenticate", 'Basic realm="Reinsurance instructor"')],
        )
    path = env["PATH_INFO"].strip("/").split("/")
    method = env["REQUEST_METHOD"]
    if method == "GET" and path == [""]:
        return reply(
            "200 OK",
            (ROOT / "instructor.html").read_bytes(),
            "text/html; charset=utf-8",
        )
    if method == "GET" and path == ["desk.css"]:
        return reply(
            "200 OK", (ROOT / "_static/market/desk.css").read_bytes(), "text/css"
        )
    if method == "GET" and path == ["desk.js"]:
        return reply(
            "200 OK",
            (ROOT / "_static/market/desk.js").read_bytes(),
            "application/javascript",
        )
    if method == "GET" and path == ["sessions"]:
        with closing(connect()) as db:
            ids = [
                row[0]
                for row in db.execute("SELECT session FROM market ORDER BY rowid DESC")
            ]
        return reply("200 OK", ids)
    try:
        if len(path) == 2 and path[0] == "market":
            sid = path[1]
            error = ""
            if method == "POST":
                if env.get("HTTP_X_MARKET_ACTION") != "instructor":
                    return reply("403 Forbidden", {})
                n = int(env.get("CONTENT_LENGTH") or 0)
                if not 0 < n <= 32768:
                    return reply("400 Bad Request", {})
                payload = json.loads(env["wsgi.input"].read(n))
                if not isinstance(payload, dict):
                    return reply("400 Bad Request", {})
                error = command(sid, None, payload)
            elif method != "GET":
                return reply("405 Method Not Allowed", {})
            return reply("200 OK", dict(state=view(sid, None), error=error))
        if (
            method == "GET"
            and len(path) == 3
            and path[0] == "csv"
            and path[2] in COLUMNS
        ):
            return reply(
                "200 OK",
                csv_bytes(path[1], path[2]),
                "text/csv; charset=utf-8",
                [("Content-Disposition", f'attachment; filename="{path[2]}.csv"')],
            )
    except (ValueError, KeyError):
        return reply("400 Bad Request", {"error": "Invalid session or request"})
    return reply("404 Not Found", {})


if __name__ == "__main__":
    if not os.environ.get("OTREE_ADMIN_PASSWORD"):
        raise SystemExit("Set OTREE_ADMIN_PASSWORD first")
    with make_server("127.0.0.1", 8765, application) as server:
        server.serve_forever()
