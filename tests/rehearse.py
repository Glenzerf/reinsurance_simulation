"""Rehearse the installed oTree application over HTTP and WebSockets in process.
The parent copies source into a new temp folder; only that throwaway database is reset.
Works without TCP sockets. TestClient exercises the routes used by a browser, but does
not run JavaScript or measure layout. See README for the separate browser walkthrough.
"""
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def isolated():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "rehearsal"
        shutil.copytree(
            root,
            folder,
            ignore=shutil.ignore_patterns(
                "*.sqlite3*",
                "*.db",
                ".venv",
                "__pycache__",
                ".env",
                ".classroom-key",
                ".ruff_cache",
                "node_modules",
                "*.zip",
            ),
        )
        env = dict(
            os.environ,
            OTREE_AUTH_LEVEL="STUDY",
            OTREE_PRODUCTION="1",
            OTREE_SECRET_KEY=secrets.token_hex(32),
            OTREE_ADMIN_PASSWORD=secrets.token_urlsafe(24),
            MARKET_DB=str(folder / "market.sqlite3"),
        )
        # Existing deployment environment must never redirect this test to a real database.
        for k in ("DATABASE_URL", "OTREE_IN_MEMORY", "REDIS_URL"):
            env.pop(k, None)
        cli = str(Path(sys.executable).parent / "otree")
        if not Path(cli).is_file():
            cli = shutil.which("otree")
        subprocess.run([cli, "resetdb", "--noinput"], cwd=folder, env=env, check=True)
        subprocess.run(
            [cli, "create_session", "market_six", "5"], cwd=folder, env=env, check=True
        )
        subprocess.run(
            [cli, "create_session", "market_full", "12"],
            cwd=folder,
            env=env,
            check=True,
        )
        for step in ("exercise", "restart"):
            subprocess.run(
                [sys.executable, "tests/rehearse.py", step],
                cwd=folder,
                env=env,
                check=True,
            )


def run(step):
    sys.path.insert(0, str(Path.cwd()))
    import csv
    import io
    from starlette.testclient import TestClient
    from starlette.middleware.wsgi import WSGIMiddleware
    from otree.asgi import app
    from instructor import application
    from exports import COLUMNS
    from reconstruct import reconstruct

    console = TestClient(WSGIMiddleware(application))
    public = TestClient(app)
    assert console.get("/sessions").status_code == 401
    assert "/login" in public.get("/export").url
    console.auth = ("admin", os.environ["OTREE_ADMIN_PASSWORD"])
    sessions = console.get("/sessions").json()
    sid = sessions[-1]
    assert len(sessions) == 2
    assert console.get("/").status_code == 200
    assert console.get("/desk.js").status_code == 200

    def admin(op=None, **fields):
        uri = "/market/" + sid
        msg = console.get(uri).json()
        if op:
            msg = console.post(
                uri,
                json=dict(rev=msg["state"]["rev"], op=op, **fields),
                headers={"X-Market-Action": "instructor"},
            ).json()
        assert not msg["error"], msg
        return msg["state"]

    assert console.post("/market/" + sid, json={}).status_code == 403
    if step == "restart":
        saved = json.loads(Path("checkpoint.json").read_text())
        assert admin()["settlement"] == saved["settlement"]
        assert (
            console.get("/csv/" + sid + "/settlement").content
            == Path("settlement.csv").read_bytes()
        )
        print("Fresh process reopened settled market with identical ID and accounts.")
        return
    # Fetch the same protected link list the instructor opens in a normal session.
    instructor = TestClient(app)
    login = instructor.get("/login")
    token = re.search(r'name="csrftoken" value="([^"]+)', login.text)[1]
    instructor.post(
        "/login",
        data=dict(
            username="admin",
            password=os.environ["OTREE_ADMIN_PASSWORD"],
            csrftoken=token,
        ),
    )
    start = instructor.get("/SessionStartLinks/" + sid)
    links = re.findall(r'href="([^"]+)" class="participant-link"', start.text)
    assert len(links) == 5, (start.status_code, start.url)
    assert (
        len(
            re.findall(
                r'class="participant-link"',
                instructor.get("/SessionStartLinks/" + sessions[0]).text,
            )
        )
        == 12
    )
    sockets = []
    for link in links:
        page = public.get(html.unescape(link))
        assert "Connecting to your team desk" in page.text and page.status_code == 200
        sockets.append(
            html.unescape(
                re.search(r'id="otree-live" data-socket-url="([^"]+)', page.text)[1]
            )
        )
    assert public.get("/static/market/desk.js").status_code == 200

    def team(n, op=None, **fields):
        # New websocket each time deliberately models refresh/reconnect to an existing login.
        with public.websocket_connect(sockets[n - 1]) as ws:
            ws.send_json(dict(op="sync"))
            msg = ws.receive_json()
            if op:
                ws.send_json(dict(rev=msg["state"]["rev"], op=op, **fields))
                msg = ws.receive_json()
            assert not msg["error"], msg
            return msg["state"]

    assert "sheet" not in team(1)
    admin("open", assign={"2": "I3", "3": "B2", "5": "R1"})
    assert (
        "sheet" not in team(1)
        and "consider two possible" in team(2)["sheet"]["mandate"]
    )
    assert "survey" in team(3)["sheet"]["mandate"]
    team(
        3,
        "propose",
        buyer="I3",
        seller="R1",
        line="C",
        kind="QS",
        q=0.4,
        share=1,
        premium=12,
    )
    for n in (2, 5):
        team(n, "approve", id="T1", version=1)
    admin("review")
    for n in (2, 3, 5):
        team(n, "confirm", book=team(n)["book"])
    admin("close")
    for n in (2, 3, 5):
        team(n, "submit", short=0.4, long=0.3, etf=0.3)
    admin("freeze")
    for name, expected in [("investments", 3), ("contracts", 1), ("settlement", 0)]:
        resp = console.get("/csv/" + sid + "/" + name)
        assert len(list(csv.DictReader(io.StringIO(resp.text)))) == expected
    end = admin("settle")
    assert team(3)["result"]["roe"] is None and team(3)["result"]["funds"] == 0.24
    assert team(2)["result"]["assessment"] == "pending"
    assert "I3" not in team(5)["losses"] and team(5)["payments"]["T1"]["buyer"] == "I3"
    for name in COLUMNS:
        response = console.get("/csv/" + sid + "/" + name)
        assert response.status_code == 200
        Path(name + ".csv").write_bytes(response.content)
    # Exercise oTree's native Data → market (custom_export) CSV action as well.
    export_page = instructor.get("/export")
    assert "app-market-custom" in export_page.text
    with instructor.websocket_connect("/export") as ws:
        ws.send_json(
            dict(
                app_name="market",
                is_custom=True,
                for_excel=False,
                link_id="app-market-custom",
            )
        )
        exported = ws.receive_json()
        assert "error" not in exported, exported.get("error")
        native = list(csv.DictReader(io.StringIO(exported["data"])))
        assert set(r["dataset"] for r in native) == set(COLUMNS)
        assert any(
            json.loads(r["row_json"]).get("settlement") == end["settlement"]
            for r in native
        )
    reconstruct(Path.cwd())
    Path("checkpoint.json").write_text(json.dumps(dict(settlement=end["settlement"])))
    print(
        "Passed admin login, both session presets, 5 real participant links, authenticated console, live trading, freeze, settlement and 7 CSV downloads."
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        isolated()
    else:
        run(sys.argv[1])
