"""Real owned process lifecycles, plus deterministic launch failure injection."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import local  # noqa: E402
from processes import OwnedProcess  # noqa: E402


def ports():
    with socket.socket() as a, socket.socket() as b:
        a.bind(("127.0.0.1", 0))
        b.bind(("127.0.0.1", 0))
        return a.getsockname()[1], b.getsockname()[1]


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "CACHE", tmp_path / "runtime")
    monkeypatch.setattr(local, "STATE", local.CACHE / "state.json")
    a, b = ports()
    # Windows process/venv startup can exceed two seconds under a full regression load.
    # Still below the production default of 30 seconds; failure assertions remain exact.
    return argparse.Namespace(demo=True, backend_port=a, frontend_port=b, timeout=10)


def wait_until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for owned process")


def fake_supervisor(args, tmp_path, *, fail_frontend=False, hang_frontend=False):
    worker = tmp_path / "worker.py"
    worker.write_text('''from http.server import HTTPServer, BaseHTTPRequestHandler
import sys
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/exit': raise SystemExit(1)
        self.send_response(200); self.end_headers()
        self.wfile.write(b'{"status":"ok","mode":"demo","database":"sqlite"}')
    def log_message(self, *args): pass
HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
''')
    second = ([sys.executable, "-c", "import time; time.sleep(120)"] if hang_frontend else
              [sys.executable, "-c", "raise SystemExit(1)"] if fail_frontend else
              [sys.executable, str(worker), str(args.frontend_port)])
    script = tmp_path / "supervisor.py"
    script.write_text(f'''import sys
sys.path.insert(0, {str(SCRIPTS)!r})
import local
from pathlib import Path
from argparse import Namespace
local.CACHE = Path({str(local.CACHE)!r})
local.STATE = local.CACHE / 'state.json'
args = Namespace(**{vars(args)!r})
local.service_commands = lambda args: [
([sys.executable, {str(worker)!r}, str(args.backend_port)], Path({str(tmp_path)!r}), args.backend_port),
({second!r}, Path({str(tmp_path)!r}), args.frontend_port)]
local.supervise(args)
''')
    return subprocess.Popen([sys._base_executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_diagnose_missing_dependencies_creates_nothing(launcher, monkeypatch):
    monkeypatch.setattr(local, "executables", lambda: (local.CACHE / "missing.exe", None))
    result = local.diagnose(launcher)
    assert result["read_only"]
    assert [c["status"] for c in result["checks"][:2]] == ["error", "error"]
    assert not local.CACHE.exists()


def test_port_conflict_leaves_external_listener_alive(launcher, monkeypatch):
    monkeypatch.setattr(local, "offline_checks", lambda _: [])
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", launcher.backend_port))
        listener.listen()
        result = local.start(launcher)
        assert result["status"] == "failed"
        assert "已占用" in result["checks"][0]["detail"]
        assert local.stop()["status"] == "stopped"
        assert not local.free_port(launcher.backend_port)


def test_stale_state_never_terminates_pid(launcher):
    local.CACHE.mkdir()
    local.save_state({"port": launcher.backend_port, "token": "stale", "pid": os.getpid()})
    assert local.stop()["status"] == "stopped"
    assert os.getpid() > 0


def test_lifecycle_duplicate_start_and_only_owned_stop(launcher, tmp_path):
    process = fake_supervisor(launcher, tmp_path)
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        external_port = unrelated.getsockname()[1]
        try:
            wait_until(lambda: (local.control(local.read_state()) or {}).get("status") == "running")
            before = local.read_state()
            result = local.start(launcher)
            assert result["status"] == "running" and "未重复" in result["detail"]
            assert local.read_state() == before
            other = argparse.Namespace(**(vars(launcher) | {"demo": False}))
            with pytest.raises(local.LocalError, match="不同参数"):
                local.start(other)
            wrong = dict(before, token="wrong")
            assert local.control(wrong, stop=True) is None
            assert local.stop()["status"] == "stopped"
            process.wait(timeout=10)
            wait_until(lambda: local.free_port(launcher.backend_port) and local.free_port(launcher.frontend_port))
            assert not local.free_port(external_port)
            assert local.stop()["status"] == "stopped"
        finally:
            local.control(local.read_state(), stop=True)
            process.wait(timeout=15)


@pytest.mark.parametrize("hang", [False, True])
def test_partial_start_failure_cleans_backend(launcher, tmp_path, hang):
    process = fake_supervisor(launcher, tmp_path, fail_frontend=True, hang_frontend=hang)
    process.wait(timeout=35)
    state = local.read_state()
    assert state["status"] == "failed"
    assert "前端" in state["detail"]
    wait_until(lambda: local.free_port(launcher.backend_port))
    assert local.free_port(launcher.frontend_port)


def test_unexpected_service_exit_cleans_sibling(launcher, tmp_path):
    process = fake_supervisor(launcher, tmp_path)
    try:
        wait_until(lambda: (local.control(local.read_state()) or {}).get("status") == "running")
        with pytest.raises(Exception):
            local.request(f"http://127.0.0.1:{launcher.backend_port}/exit")
        process.wait(timeout=15)
        assert local.read_state()["status"] == "failed"
        wait_until(lambda: local.free_port(launcher.backend_port) and local.free_port(launcher.frontend_port))
    finally:
        local.control(local.read_state(), stop=True)
        process.wait(timeout=15)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job lifetime guarantee")
def test_windows_supervisor_crash_closes_owned_jobs(launcher, tmp_path):
    process = fake_supervisor(launcher, tmp_path)
    try:
        wait_until(lambda: (local.control(local.read_state()) or {}).get("status") == "running")
        process.kill()  # This exact Popen handle, never a persisted PID or port owner.
        process.wait(timeout=10)
        wait_until(lambda: local.free_port(launcher.backend_port) and local.free_port(launcher.frontend_port))
        assert local.stop()["status"] == "stopped"
    finally:
        if process.poll() is None:
            local.control(local.read_state(), stop=True)
            process.wait(timeout=15)


def test_owned_process_stops_descendants(tmp_path):
    port, _ = ports()
    script = tmp_path / "parent.py"
    script.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-m','http.server',sys.argv[1],'--bind','127.0.0.1'])\ntime.sleep(120)\n")
    process = OwnedProcess([sys.executable, str(script), str(port)], cwd=tmp_path, env=os.environ.copy())
    try:
        wait_until(lambda: not local.free_port(port))
    finally:
        process.close()
    wait_until(lambda: local.free_port(port))


def test_missing_dependency_prevents_any_spawn(launcher, monkeypatch):
    monkeypatch.setattr(local, "offline_checks", lambda _: [local.row("python", "error", "缺依赖")])
    monkeypatch.setattr(local.subprocess, "Popen", lambda *a, **k: pytest.fail("must not spawn"))
    assert local.start(launcher)["status"] == "failed"


def test_demo_overrides_model_and_database_without_echoing_secrets(launcher, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@host/database")
    monkeypatch.setenv("AI_PROVIDER", "compatible")
    monkeypatch.setenv("AI_API_KEY", "secret")
    env = local.environment(launcher)
    assert env["AI_PROVIDER"] == "demo" and not env["AI_API_KEY"]
    assert env["DATABASE_URL"].endswith("demo.db")
    assert "secret" not in json.dumps({k: env[k] for k in ("DATABASE_URL", "AI_API_KEY")} )
