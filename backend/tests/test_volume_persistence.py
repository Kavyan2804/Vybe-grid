"""Test: named volume persistence across docker-compose down / up.

This test documents and automates the manual verification step:
  1. Start the DB via docker-compose.dev.yml
  2. Insert a row
  3. docker-compose down (stops + removes container, volume persists)
  4. docker-compose up
  5. Verify the row is still there

It calls docker-compose via subprocess and connects with psycopg2.
Requires Docker to be running.

Mark: this test is slow and requires Docker — it's excluded from the
default test run and invoked explicitly:

    pytest tests/test_volume_persistence.py -v -m docker
"""

import subprocess
import time

import psycopg2
import pytest

from pathlib import Path

import os

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = str(REPO_ROOT / "infra" / "compose" / "docker-compose.dev.yml")
COMPOSE_CMD = ["docker", "compose", "-f", COMPOSE_FILE]
PORT = os.environ.get("POSTGRES_PORT", "5433")
DSN = f"host=localhost port={PORT} dbname=gridpilot user=gridpilot password=gridpilot"


def _compose(*args: str) -> None:
    env = {**os.environ, "POSTGRES_PORT": PORT}
    subprocess.run([*COMPOSE_CMD, *args], check=True, capture_output=True, env=env)


def _wait_for_pg(timeout: int = 30) -> None:
    """Block until Postgres accepts connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(DSN)
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(1)
    raise TimeoutError("Postgres did not become ready within timeout")


@pytest.mark.docker
def test_data_survives_compose_restart() -> None:
    """Data written before ``compose down`` is still present after ``compose up``."""
    try:
        # 1. Bring up DB
        _compose("up", "-d", "--wait")
        _wait_for_pg()

        # 2. Create a test table and insert a canary row
        conn = psycopg2.connect(DSN)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS _volume_test (id serial PRIMARY KEY, value text)"
        )
        cur.execute(
            "INSERT INTO _volume_test (value) VALUES ('canary') ON CONFLICT DO NOTHING"
        )
        cur.close()
        conn.close()

        # 3. Stop + remove containers (volume persists)
        _compose("down")

        # 4. Bring up again
        _compose("up", "-d", "--wait")
        _wait_for_pg()

        # 5. Verify canary row still exists
        conn = psycopg2.connect(DSN)
        cur = conn.cursor()
        cur.execute("SELECT value FROM _volume_test WHERE value = 'canary'")
        row = cur.fetchone()
        cur.close()
        conn.close()

        assert row is not None, "Data did not survive compose down && compose up"
        assert row[0] == "canary"

    finally:
        # Cleanup: remove containers but keep volume for next run
        _compose("down")
