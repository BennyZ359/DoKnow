"""Local launcher: standard library only, no installs or database writes in diagnose."""

import argparse
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from processes import OwnedProcess

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "local"
STATE = CACHE / "state.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


HTTP = build_opener(ProxyHandler({}), NoRedirect())
HINT = "请运行 diagnose，检查端口/依赖/数据库；详见 docs/LOCAL_RUNNING.md。"


class LocalError(Exception):
    pass


def row(name, status, detail, action=""):
    return {"name": name, "status": status, "detail": detail, "action": action}


def emit(value, json_output=False):
    if json_output:
        print(json.dumps(value, ensure_ascii=False))
        return
    if "status" in value:
        print({"running": "服务正在运行", "stopped": "服务已停止", "failed": "操作未完成"}.get(value["status"], value["status"]))
    if value.get("read_only"):
        print("只读诊断 · " + ("独立体验库" if value.get("scope") == "isolated_demo" else "当前环境配置"))
    if value.get("detail"):
        print(value["detail"])
    if value.get("url"):
        print("打开 " + value["url"])
    for item in value.get("checks", []):
        print(f"[{item['status']}] {item['name']}: {item['detail']}")
        if item.get("action") and item["status"] != "ok":
            print("  → " + item["action"])


def read_state():
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("port"), int):
            return None
        if not 0 < state["port"] < 65536 or not isinstance(state.get("token"), str):
            return None
        return state
    except (OSError, ValueError):
        return None


def request(url, *, token=None, stop=False):
    req = Request(url, data=b"" if stop else None,
                  headers={"Authorization": f"Bearer {token}"} if token else {})
    with HTTP.open(req, timeout=1) as response:
        data = response.read(100_001)
        if len(data) > 100_000:
            raise ValueError("Response too large")
        return json.loads(data)


def control(state, stop=False):
    if not state:
        return None
    try:
        result = request(f"http://127.0.0.1:{state['port']}/{'stop' if stop else 'status'}",
                         token=state["token"], stop=stop)
        if result.get("instance") == state["token"]:
            return {k: v for k, v in result.items() if k != "instance"}
    except Exception:
        pass
    return None


@contextmanager
def lock(name):
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / name).open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            if not stream.read(1):
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise LocalError("已有启停操作或托管服务正在运行；请稍后重试或运行 stop。") from None
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise LocalError("已有启停操作或托管服务正在运行；请稍后重试或运行 stop。") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def environment(args):
    env = os.environ.copy()
    if args.demo:
        env.update(AI_PROVIDER="demo", AI_API_KEY="", REDIS_URL="",
                   DATABASE_URL="sqlite:///" + (CACHE / "demo.db").as_posix())
    env["PYTHONIOENCODING"] = "utf-8"
    env["DOKNOW_API_TARGET"] = f"http://127.0.0.1:{args.backend_port}"
    return env


def executables():
    python = ROOT / "backend" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return python, shutil.which("node")


def dependencies(env):
    python, node = executables()
    checks = []
    probe = (
        "import sys,importlib,json; "
        "names=['fastapi','uvicorn','sqlalchemy','alembic','pydantic','httpx','dotenv',"
        "'multipart','pypdf','docx','langgraph','psycopg','redis']; "
        "missing=[n for n in names if importlib.util.find_spec(n) is None]; "
        "print(json.dumps({'ok':sys.version_info>=(3,11) and not missing,'missing':missing}))"
    )
    try:
        result = subprocess.run([str(python), "-c", "import importlib.util; " + probe],
                                env=env, capture_output=True, timeout=15)
        good = result.returncode == 0 and json.loads(result.stdout)["ok"]
    except Exception:
        good = False
    checks.append(row("python", "ok" if good else "error", "Python 3.11+ 与后端依赖已就绪。" if good else "Python 环境或后端依赖缺失。",
                      "在 backend 目录运行 uv sync --frozen --extra dev，或按 README 创建 .venv 并安装 requirements.lock。"))
    try:
        result = subprocess.run([node, "--version"], capture_output=True, timeout=5)
        node_ok = result.returncode == 0 and int(result.stdout.decode().strip().lstrip("v").split(".")[0]) >= 22
        if node_ok:
            result = subprocess.run([node, "--input-type=module", "-e",
                                     "await import('vite'); await import('vue'); await import('@vitejs/plugin-vue')"],
                                    cwd=ROOT / "frontend", capture_output=True, timeout=10)
            node_ok = result.returncode == 0
    except Exception:
        node_ok = False
    checks.append(row("node", "ok" if node_ok else "error", "Node.js 22+ 与前端依赖已就绪。" if node_ok else "Node.js 22+ 或前端依赖缺失。",
                      "安装 Node.js 22+，在 frontend 目录运行 npm ci。"))
    return checks


def free_port(port):
    with socket.socket() as sock:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # Match HTTP servers on POSIX: a closed connection in TIME_WAIT is
            # reusable. SO_REUSEADDR still rejects an active TCP listener;
            # SO_REUSEPORT, which would allow sharing that listener, is not set.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def offline_checks(args):
    env = environment(args)
    checks = dependencies(env)
    if checks[0]["status"] == "ok":
        try:
            result = subprocess.run([str(executables()[0]), "-m", "app.diagnostics"], cwd=ROOT / "backend",
                                    env=env, capture_output=True, timeout=20)
            checks.extend(json.loads(result.stdout)["checks"])
        except Exception:
            checks.append(row("database", "error", "数据库诊断未能完成。", HINT))
    else:
        checks.append(row("database", "pending", "安装后端依赖后才能检查模式与数据库。"))
    return checks


def diagnose(args):
    checks = offline_checks(args)
    owned = control(read_state())
    if owned and any(owned.get(k) != getattr(args, k) for k in ("backend_port", "frontend_port", "demo")):
        checks.append(row("instance", "warning", "当前托管服务与本次诊断参数不同。",
                          "请使用启动时相同的 --demo、--backend-port 和 --frontend-port 参数检查该实例。"))
    for name, port in (("backend", args.backend_port), ("frontend", args.frontend_port)):
        available = free_port(port)
        checks.append(row(name + "_port", "ok" if available else "warning",
                          f"端口 {port} 可用。" if available else f"端口 {port} 已占用。",
                          "如果不是当前服务，请手动核对占用者或用 --backend-port / --frontend-port 选择其他端口。"))
        try:
            body = request(f"http://127.0.0.1:{port}/api/health")
            reachable = body.get("status") == "ok" and body.get("mode") in {"demo", "ai"} and body.get("database") in {"sqlite", "postgresql"}
        except Exception:
            reachable = False
        checks.append(row(name, "ok" if reachable else "warning",
                          (("后端可连通" if name == "backend" else "前端代理可连通后端") + f"（{body['mode']}）。") if reachable else "服务未启动或健康检查失败。",
                          "运行 start；失败时按其他诊断项排查。"))
    return {"read_only": True, "scope": "isolated_demo" if args.demo else "configured", "managed": owned, "checks": checks}


def save_state(state):
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state), encoding="utf-8")
    if os.name != "nt":
        temp.chmod(0o600)
    temp.replace(STATE)


def service_commands(args):
    python, node = executables()
    return [
        ([str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.backend_port), "--no-access-log"], ROOT / "backend", args.backend_port),
        ([node, str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(args.frontend_port), "--strictPort"], ROOT / "frontend", args.frontend_port),
    ]


def supervise(args):
    children = []
    state = {}
    server = None
    try:
        with lock("run.lock"):
            token = secrets.token_hex(32)
            status = {"status": "starting", "backend_port": args.backend_port,
                      "frontend_port": args.frontend_port, "demo": args.demo}
            stopped = False

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def do_GET(self):
                    self.respond(False)

                def do_POST(self):
                    self.respond(True)

                def respond(self, stop):
                    nonlocal stopped
                    if not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}"):
                        self.send_error(403)
                        return
                    if self.path != ("/stop" if stop else "/status"):
                        self.send_error(404)
                        return
                    stopped = stopped or stop
                    payload = json.dumps(status | {"instance": token}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

            server = HTTPServer(("127.0.0.1", 0), Handler)
            server.timeout = 0.1
            state = {"port": server.server_port, "token": token, "launch_id": getattr(args, "launch_id", ""), **status}
            save_state(state)
            commands = service_commands(args)
            try:
                for command, cwd, port in commands:
                    if not free_port(port):
                        raise LocalError("端口冲突；未结束占用者。")
                    children.append(OwnedProcess(command, cwd=cwd, env=environment(args)))
                    deadline = time.monotonic() + args.timeout
                    ready = False
                    while time.monotonic() < deadline and not stopped:
                        server.handle_request()
                        if any(child.poll() is not None for child in children):
                            break
                        try:
                            ready = request(f"http://127.0.0.1:{port}/api/health").get("status") == "ok"
                        except Exception:
                            ready = False
                        if ready:
                            break
                    if not ready or stopped:
                        raise LocalError("后端未就绪。" if port == args.backend_port else "前端或代理未就绪。")
                status["status"] = "running"
                save_state(state | status)
                while not stopped:
                    server.handle_request()
                    if any(child.poll() is not None for child in children):
                        raise LocalError("服务意外退出，已收尾本次启动的全部服务。")
                status["status"] = "stopped"
            except Exception as exc:
                status.update(status="failed", detail=str(exc) if isinstance(exc, LocalError) else "启动失败。")
            finally:
                for child in reversed(children):
                    child.close()
                save_state(state | status)
                # Only curated events; never persist raw child stdout, config or learner data.
                (CACHE / "events.log").write_text(json.dumps(status, ensure_ascii=True) + "\n", encoding="utf-8")
    finally:
        if server:
            server.server_close()


def start(args):
    with lock("command.lock"):
        existing = control(read_state())
        if existing:
            if any(existing.get(k) != getattr(args, k) for k in ("backend_port", "frontend_port", "demo")):
                raise LocalError("已有不同参数的托管服务；先 stop 再启动。")
            return existing | {"detail": "已运行，未重复启动。"}
        checks = offline_checks(args)
        for port in (args.backend_port, args.frontend_port):
            if not free_port(port):
                checks.append(row("port", "error", f"端口 {port} 已占用，未结束占用者。", "选择其他端口，或手动核对并停止原服务。"))
        if any(c["status"] == "error" for c in checks):
            return {"status": "failed", "checks": checks}
        launch_id = secrets.token_hex(16)
        command = [sys.executable, str(Path(__file__).resolve()), "_supervise", "--launch-id", launch_id, "--backend-port", str(args.backend_port),
                   "--frontend-port", str(args.frontend_port), "--timeout", str(args.timeout)] + (["--demo"] if args.demo else [])
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                   start_new_session=os.name != "nt")
        deadline = time.monotonic() + args.timeout * 2 + 10
        own_state = None
        while time.monotonic() < deadline:
            candidate = read_state()
            if candidate and candidate.get("launch_id") == launch_id:
                own_state = candidate
            live = control(own_state)
            if live and live["status"] == "running":
                return live | {"url": f"http://127.0.0.1:{args.frontend_port}"}
            if process.poll() is not None:
                break
            time.sleep(0.15)
        control(own_state, stop=True)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            # Never kill via a saved PID. The supervisor owns worker cleanup.
            raise LocalError("启动等待超时；运行 stop 完成收尾。" + HINT) from None
        state = own_state or {}
        raise LocalError(state.get("detail", "服务启动失败，已收尾本次服务。") + HINT)


def stop():
    with lock("command.lock"):
        state = read_state()
        live = control(state)
        if not live:
            # Stale/malformed state is never a license to terminate a PID or port owner.
            return {"status": "stopped", "detail": "没有可连接的托管服务；未结束其他进程。"}
        control(state, stop=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if control(state) is None:
                try:
                    with lock("run.lock"):
                        return {"status": "stopped", "detail": "本次托管服务已停止，学习数据保留。"}
                except LocalError:
                    pass  # Cleanup owns the lock until every child has been handled.
            time.sleep(0.1)
        raise LocalError("停止尚未完成，请稍后再次 stop；未结束其他进程。")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.version_info < (3, 11):
        print("需要 Python 3.11+；安装后重新运行 diagnose。")
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "diagnose", "_supervise"])
    parser.add_argument("--demo", action="store_true", help="Force demo and use an isolated .cache/local/demo.db")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--json", action="store_true", help="Print a structured report")
    parser.add_argument("--launch-id", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not all(0 < p < 65536 for p in (args.backend_port, args.frontend_port)) or args.backend_port == args.frontend_port or not 1 <= args.timeout <= 120:
        parser.error("Use distinct ports in 1..65535 and timeout in 1..120 seconds.")
    try:
        if args.command == "_supervise":
            supervise(args)
            return 0
        result = start(args) if args.command == "start" else stop() if args.command == "stop" else diagnose(args)
        emit(result, args.json)
        return int(result.get("status") == "failed" or any(c["status"] == "error" for c in result.get("checks", [])))
    except (LocalError, OSError):
        # LocalError text is ours; arbitrary OS errors could disclose configuration.
        exc = sys.exception()
        emit({"status": "failed", "detail": str(exc) if isinstance(exc, LocalError) else "无法访问本地运行目录或启动进程。" + HINT}, args.json)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
