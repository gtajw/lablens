"""Start isolated local dependencies, run checks, and stop only owned processes.

Use --local-db when native PostgreSQL is unavailable. That verifies PostgreSQL
SQL semantics via PGlite, but native concurrency and production load gates still
run in CI against a real PostgreSQL service. All child services share one runtime.
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
parser = argparse.ArgumentParser()
parser.add_argument("--local-db", action="store_true")
parser.add_argument("--browser", action="store_true")
parser.add_argument("--skip-tests", action="store_true")
args = parser.parse_args()
env = dict(
    os.environ,
    LABLENS_ENVIRONMENT="test",
    LABLENS_TEST_DATABASE="1",
    OPENBLAS_NUM_THREADS="1",
    OMP_NUM_THREADS="1",
)
processes = []
logs = []


def start(command, name):
    log = (ROOT / ".local-data" / f"verify-{name}.log").open("w")
    logs.append(log)
    process = subprocess.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
    processes.append(process)
    return process


def wait_port(port, process):
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited: {process.args}; inspect .local-data/verify-*.log")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Port {port} did not become ready")


def run(command):
    subprocess.run(command, env=env, check=True)


(ROOT / ".local-data").mkdir(exist_ok=True)
try:
    if args.local_db:
        # Fresh path avoids touching any user's local notebook.
        directory = tempfile.mkdtemp(prefix="lablens-check-", dir=ROOT / ".local-data")
        env.update(
            LABLENS_PGLITE_PATH=directory,
            LABLENS_POOL_SIZE="1",
            LABLENS_DB_PORT="5544",
            LABLENS_DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5544/postgres",
        )
        db = start(["node", "scripts/local-postgres.mjs"], "database")
        wait_port(5544, db)
    run([sys.executable, "-m", "alembic", "upgrade", "head"])
    if not args.skip_tests:
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--cov=lablens",
                "--cov-report=term-missing",
                "--cov-report=json:docs/coverage.json",
                "--junitxml=docs/test-results.xml",
            ]
        )
    if args.browser:
        api = start(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "lablens.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ],
            "api",
        )
        wait_port(8000, api)
        env["LABLENS_PUBLIC_ORIGIN"] = "http://127.0.0.1:3000"
        web = start(["npm", "run", "start"], "web")
        wait_port(3000, web)
        run(["npm", "run", "test:e2e"])
finally:
    for process in reversed(processes):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
    for log in logs:
        log.close()
