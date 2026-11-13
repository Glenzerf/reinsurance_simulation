"""Launch both classroom services on one persistent host. This launcher creates a signing
key on first use, keeps the instructor password out of files, and never resets a database.
Use a TLS reverse proxy for the student-facing service when hosting beyond localhost.
"""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def signing_key():
    """Use the same application key after a restart. The private file is owner-readable."""
    value = os.environ.get("OTREE_SECRET_KEY")
    if value:
        return value
    path = ROOT / ".classroom-key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    value = secrets.token_hex(32)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--listen",
        default="127.0.0.1:8000",
        help="oTree bind address:port; instructor console always stays on localhost:8765",
    )
    args = parser.parse_args()
    binary = Path(sys.executable).parent / "otree"
    if not binary.is_file():
        binary = shutil.which("otree")
    if not binary:
        raise SystemExit(
            "Install requirements.txt in the active Python 3.11 environment."
        )
    password = os.environ.get("OTREE_ADMIN_PASSWORD") or getpass.getpass(
        "Instructor password (use the same password after restart): "
    )
    if not password:
        raise SystemExit("An instructor password is required.")
    env = dict(
        os.environ,
        OTREE_AUTH_LEVEL="STUDY",
        OTREE_PRODUCTION="1",
        OTREE_ADMIN_PASSWORD=password,
        OTREE_SECRET_KEY=signing_key(),
    )
    # The durable ledger and oTree participant IDs must both survive hard restarts.
    env.pop("OTREE_IN_MEMORY", None)
    procs = []
    try:
        for cmd in (
            [sys.executable, "instructor.py"],
            [str(binary), "prodserver", args.listen],
        ):
            procs.append(
                subprocess.Popen(cmd, cwd=ROOT, env=env, start_new_session=True)
            )
        print(
            "oTree session administration: http://"
            + args.listen
            + "\nInstructor market desk: http://127.0.0.1:8765\nKeep this terminal open. Press Ctrl-C to stop.",
            flush=True,
        )
        while all(p.poll() is None for p in procs):
            time.sleep(0.4)
        if any(p.returncode not in (None, 0) for p in procs):
            raise SystemExit(
                "A service could not start or stopped. See the messages above."
            )
    except KeyboardInterrupt:
        pass
    finally:
        # prodserver owns a timeout-worker child; terminate its entire process group.
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for p in procs:
            p.wait()


if __name__ == "__main__":
    main()
