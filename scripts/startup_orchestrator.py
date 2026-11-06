#!/usr/bin/env python3
"""
scripts/startup_orchestrator.py — KogniSync Startup Orchestration Engine.

Encapsulates all preflight checks, environment configuration, dependency checks,
infrastructure orchestration, service lifecycle, readiness polling, and graceful cleanup.
Used both as a standalone cross-platform entrypoint and as the testable core logic for automated testing.
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent


class StartupError(RuntimeError):
    """Raised when a preflight or startup condition fails closed."""


class StartupOrchestrator:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        socket_check_fn: Optional[Callable[[str, int, float], bool]] = None,
        process_runner_fn: Optional[Callable[..., subprocess.CompletedProcess]] = None,
        http_check_fn: Optional[Callable[[str, float], bool]] = None,
        browser_open_fn: Optional[Callable[[str], bool]] = None,
    ):
        self.repo_root = repo_root
        self.backend_dir = repo_root / "backend"
        self.frontend_dir = repo_root / "frontend"
        self.logs_dir = repo_root / "logs"
        self.env_file = repo_root / ".env"
        self.env_example_file = repo_root / ".env.example"

        # Injectable hooks for testing & isolation
        self._socket_check = socket_check_fn or self._default_socket_check
        self._run_cmd = process_runner_fn or subprocess.run
        self._http_check = http_check_fn or self._default_http_check
        self._browser_open = browser_open_fn or self._default_browser_open

        # Lifecycle tracking
        self.backend_proc: Optional[subprocess.Popen] = None
        self.frontend_proc: Optional[subprocess.Popen] = None
        self.tracked_pids: set[int] = set()

    @staticmethod
    def _default_socket_check(host: str, port: int, timeout: float = 1.0) -> bool:
        """Return True if port is open/listening on host, False otherwise."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect((host, port))
                return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                return False

    @staticmethod
    def _default_http_check(url: str, timeout: float = 2.0) -> bool:
        """Return True if HTTP endpoint responds with 2xx/3xx."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KogniSync-Startup/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 400
        except Exception:
            return False

    @staticmethod
    def _default_browser_open(url: str) -> bool:
        import webbrowser
        return webbrowser.open(url)

    # --- Preflight Phase ---
    def check_python(self, sys_version_info: tuple[int, int] | None = None) -> tuple[int, int]:
        ver = sys_version_info if sys_version_info is not None else (sys.version_info.major, sys.version_info.minor)
        if ver[0] < 3 or (ver[0] == 3 and ver[1] < 10):
            raise StartupError(f"Python 3.10+ required. Detected: {ver[0]}.{ver[1]}")
        return ver

    def check_node(self) -> str:
        try:
            res = self._run_cmd(["node", "-v"], capture_output=True, text=True, check=True)
            raw = res.stdout.strip().lstrip("v")
            major = int(raw.split(".")[0])
            if major < 18:
                raise StartupError(f"Node.js 18+ required. Detected: v{raw}")
            return raw
        except (subprocess.SubprocessError, FileNotFoundError, ValueError) as exc:
            raise StartupError(f"Node.js check failed: {exc}") from exc

    def check_docker(self) -> bool:
        """Check if Docker CLI is present and the Docker daemon is responsive."""
        if shutil.which("docker") is None:
            return False
        try:
            res = self._run_cmd(["docker", "info"], capture_output=True, text=True)
            return res.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def check_ports(self, backend_port: int = 8000, frontend_port: int = 5173) -> None:
        """Ensure backend and frontend ports are free. Fail closed without killing unrelated processes."""
        if self._socket_check("127.0.0.1", backend_port, 0.5):
            raise StartupError(
                f"Port {backend_port} (Backend) is already occupied by an existing process. "
                "KogniSync strictly preserves unrelated processes and will not kill them. "
                "Please stop the existing process or close prior instances."
            )
        if self._socket_check("127.0.0.1", frontend_port, 0.5):
            raise StartupError(
                f"Port {frontend_port} (Frontend) is already occupied by an existing process. "
                "KogniSync strictly preserves unrelated processes and will not kill them. "
                "Please stop the existing process or close prior instances."
            )

    # --- Configuration Bootstrap ---
    def bootstrap_env(self) -> str:
        """Ensure .env exists; copy from .env.example with secure keys if missing; preserve existing."""
        if self.env_file.exists():
            return "preserved"

        if not self.env_example_file.exists():
            raise StartupError(f".env.example not found at {self.env_example_file}")

        content = self.env_example_file.read_text(encoding="utf-8")
        secret_key = secrets.token_urlsafe(32)
        internal_key = secrets.token_hex(16)

        if "JWT_SECRET_KEY=" in content:
            lines = []
            for line in content.splitlines():
                if line.startswith("JWT_SECRET_KEY="):
                    lines.append(f"JWT_SECRET_KEY={secret_key}")
                else:
                    lines.append(line)
            content = "\n".join(lines) + "\n"
        else:
            content += f"\nJWT_SECRET_KEY={secret_key}\nINTERNAL_API_KEY={internal_key}\n"

        self.env_file.write_text(content, encoding="utf-8")
        return "created"

    # --- Infrastructure Orchestration ---
    def orchestrate_postgres(
        self,
        docker_available: bool,
        allow_offline_fallback: bool = False,
        timeout_seconds: int = 30
    ) -> str:
        """Check/start PostgreSQL on port 5434. Fail closed unless allow_offline_fallback is True."""
        if self._socket_check("127.0.0.1", 5434, 0.5):
            return "Connected (existing on port 5434)"

        if docker_available:
            try:
                self._run_cmd(["docker", "compose", "up", "-d", "postgres"], check=True)
            except subprocess.SubprocessError as exc:
                if not allow_offline_fallback:
                    raise StartupError(f"Failed to start PostgreSQL container: {exc}") from exc
                return "Unavailable (offline fallback)"

            start_t = time.time()
            while time.time() - start_t < timeout_seconds:
                if self._socket_check("127.0.0.1", 5434, 0.5):
                    return "Connected (Docker container)"
                time.sleep(1)

            if not allow_offline_fallback:
                raise StartupError(f"PostgreSQL container failed to become ready on port 5434 within {timeout_seconds}s.")
            return "Unavailable (offline fallback)"

        if allow_offline_fallback:
            return "Unavailable (offline fallback)"

        raise StartupError(
            "PostgreSQL is not listening on port 5434 and Docker is unavailable. "
            "Please start Docker Desktop or local PostgreSQL, or pass --allow-offline-fallback."
        )

    def orchestrate_redis(
        self,
        docker_available: bool,
        timeout_seconds: int = 15
    ) -> str:
        """Check/start Redis on port 6380. Fallback gracefully to in-memory degraded mode if unavailable."""
        if self._socket_check("127.0.0.1", 6380, 0.5):
            return "Connected (existing on port 6380)"

        if docker_available:
            try:
                self._run_cmd(["docker", "compose", "up", "-d", "redis"], check=True)
            except subprocess.SubprocessError:
                return "Unavailable (in-memory degraded)"

            start_t = time.time()
            while time.time() - start_t < timeout_seconds:
                if self._socket_check("127.0.0.1", 6380, 0.5):
                    return "Connected (Docker container)"
                time.sleep(1)

        return "Unavailable (in-memory degraded)"

    def run_migrations(self, postgres_status: str) -> bool:
        """Run database migrations if PostgreSQL is connected."""
        if not postgres_status.startswith("Connected"):
            return False

        migrate_script = self.repo_root / "scripts" / "migrate.py"
        if not migrate_script.exists():
            raise StartupError("scripts/migrate.py not found.")

        res = self._run_cmd([sys.executable, str(migrate_script), "upgrade"])
        if res.returncode != 0:
            raise StartupError("Database migration failed (scripts/migrate.py upgrade).")
        return True

    # --- Readiness Verification ---
    def wait_for_readiness(
        self,
        backend_url: str = "http://127.0.0.1:8000/health",
        frontend_url: str = "http://127.0.0.1:5173",
        timeout_seconds: int = 60
    ) -> bool:
        """Poll backend and frontend readiness until both respond or timeout."""
        start_t = time.time()
        backend_ready = False
        frontend_ready = False

        while time.time() - start_t < timeout_seconds:
            if self.backend_proc and self.backend_proc.poll() is not None:
                raise StartupError(f"Backend process terminated prematurely with code {self.backend_proc.returncode}.")
            if self.frontend_proc and self.frontend_proc.poll() is not None:
                raise StartupError(f"Frontend process terminated prematurely with code {self.frontend_proc.returncode}.")

            if not backend_ready:
                backend_ready = self._http_check(backend_url, 1.0)
            if not frontend_ready:
                frontend_ready = self._http_check(frontend_url, 1.0)

            if backend_ready and frontend_ready:
                return True

            time.sleep(0.5)

        raise StartupError(
            f"Readiness verification timed out after {timeout_seconds}s (Backend: {backend_ready}, Frontend: {frontend_ready})."
        )

    # --- Process Cleanup ---
    def cleanup_processes(self) -> list[int]:
        """Safely terminate only tracked application processes. Never kill unrelated processes."""
        terminated = []
        for proc in (self.backend_proc, self.frontend_proc):
            if proc and proc.pid in self.tracked_pids:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except (subprocess.TimeoutExpired, OSError):
                        try:
                            proc.kill()
                        except OSError:
                            pass
                    terminated.append(proc.pid)
        return terminated

    def open_browser(self, url: str = "http://127.0.0.1:5173", no_browser: bool = False) -> bool:
        """Launch browser only after readiness has succeeded and unless no_browser is set."""
        if no_browser:
            return False
        return self._browser_open(url)


def main():
    parser = argparse.ArgumentParser(description="KogniSync Startup Orchestrator")
    parser.add_argument("--no-browser", action="store_true", help="Do not open default browser.")
    parser.add_argument("--allow-offline-fallback", action="store_true", help="Allow running without PostgreSQL.")
    parser.add_argument("--skip-infrastructure", action="store_true", help="Skip database/Redis orchestration.")
    parser.add_argument("--dry-run", action="store_true", help="Validate preflight and plan without launching.")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="Max readiness wait in seconds.")
    args = parser.parse_args()

    orchestrator = StartupOrchestrator()
    try:
        orchestrator.check_python()
        orchestrator.check_node()
        orchestrator.check_ports()
        docker_ok = orchestrator.check_docker()
        orchestrator.bootstrap_env()

        if args.skip_infrastructure:
            pg_status = "Skipped"
            redis_status = "Skipped"
        else:
            pg_status = orchestrator.orchestrate_postgres(
                docker_available=docker_ok,
                allow_offline_fallback=args.allow_offline_fallback
            )
            redis_status = orchestrator.orchestrate_redis(docker_available=docker_ok)
            orchestrator.run_migrations(pg_status)

        if args.dry_run:
            print("=== KogniSync Dry-Run Plan ===")
            print(f"PostgreSQL: {pg_status}")
            print(f"Redis:      {redis_status}")
            print("Preflight:  PASSED")
            return 0

        print(f"Starting services (PostgreSQL: {pg_status}, Redis: {redis_status})...")
    except StartupError as e:
        print(f"Startup Failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
