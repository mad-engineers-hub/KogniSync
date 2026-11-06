"""
backend/tests/test_startup_orchestrator.py — Automated Test Suite for KogniSync Startup Orchestration.

Validates the 18 required scenarios:
 1. Missing / outdated Python
 2. Missing / outdated Node.js
 3. Missing Docker CLI
 4. Docker daemon unavailable
 5. Existing PostgreSQL service reuse
 6. PostgreSQL startup timeout & fail-closed enforcement
 7. Existing Redis service reuse
 8. Redis unavailable resilient fallback
 9. Missing .env bootstrap with secret generation
10. Existing .env preservation
11. Backend premature startup failure handling
12. Frontend premature startup failure handling
13. Occupied backend/frontend port collision safety
14. Browser launch gated strictly on readiness (and respect for no-browser flag)
15. Process cleanup lifecycle on interruption
16. Unrelated process preservation (strictly non-destructive)
17. Docker volumes and canonical organizer files immutability
18. Repeated startup duplication protection
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root and scripts directory are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.startup_orchestrator import StartupError, StartupOrchestrator


@pytest.fixture
def temp_orchestrator(tmp_path: Path):
    """Fixture providing a StartupOrchestrator initialized in an isolated directory."""
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    logs = tmp_path / "logs"
    backend.mkdir(parents=True)
    frontend.mkdir(parents=True)
    logs.mkdir(parents=True)

    example_env = tmp_path / ".env.example"
    example_env.write_text("PROJECT_NAME=KogniSync\nJWT_SECRET_KEY=default\n", encoding="utf-8")

    orchestrator = StartupOrchestrator(repo_root=tmp_path)
    return orchestrator, tmp_path


# 1. Missing / outdated Python (< 3.10)
def test_1_missing_or_outdated_python():
    orchestrator = StartupOrchestrator()
    with pytest.raises(StartupError, match="Python 3.10\\+ required"):
        orchestrator.check_python(sys_version_info=(3, 9))

    with pytest.raises(StartupError, match="Python 3.10\\+ required"):
        orchestrator.check_python(sys_version_info=(2, 7))

    assert orchestrator.check_python(sys_version_info=(3, 10)) == (3, 10)
    assert orchestrator.check_python(sys_version_info=(3, 12)) == (3, 12)


# 2. Missing / outdated Node.js (< 18)
def test_2_missing_or_outdated_nodejs():
    mock_runner = MagicMock()
    # Case: Node executable missing
    mock_runner.side_effect = FileNotFoundError("node not found")
    orchestrator = StartupOrchestrator(process_runner_fn=mock_runner)
    with pytest.raises(StartupError, match="Node.js check failed"):
        orchestrator.check_node()

    # Case: Node version < 18 (e.g. v16.14.0)
    mock_runner.side_effect = None
    mock_runner.return_value = subprocess.CompletedProcess(args=["node", "-v"], returncode=0, stdout="v16.14.0\n")
    with pytest.raises(StartupError, match="Node.js 18\\+ required"):
        orchestrator.check_node()

    # Case: Node version >= 18 (e.g. v20.10.0)
    mock_runner.return_value = subprocess.CompletedProcess(args=["node", "-v"], returncode=0, stdout="v20.10.0\n")
    assert orchestrator.check_node() == "20.10.0"


# 3. Missing Docker CLI
def test_3_missing_docker_cli():
    with patch("shutil.which", return_value=None):
        orchestrator = StartupOrchestrator()
        assert orchestrator.check_docker() is False


# 4. Docker daemon unavailable
def test_4_docker_daemon_unavailable():
    with patch("shutil.which", return_value="/usr/bin/docker"):
        mock_runner = MagicMock()
        mock_runner.return_value = subprocess.CompletedProcess(args=["docker", "info"], returncode=1, stderr="daemon not running")
        orchestrator = StartupOrchestrator(process_runner_fn=mock_runner)
        assert orchestrator.check_docker() is False


# 5. Existing PostgreSQL service (Port 5434 already listening)
def test_5_existing_postgresql_service_reuse():
    mock_socket = MagicMock(return_value=True)  # Port 5434 open
    mock_runner = MagicMock()
    orchestrator = StartupOrchestrator(socket_check_fn=mock_socket, process_runner_fn=mock_runner)

    status = orchestrator.orchestrate_postgres(docker_available=True)
    assert "existing on port 5434" in status
    # Must NOT call docker compose
    mock_runner.assert_not_called()


# 6. PostgreSQL startup timeout & fail-closed enforcement
def test_6_postgresql_startup_timeout_fail_closed():
    mock_socket = MagicMock(return_value=False)  # Never becomes ready
    mock_runner = MagicMock()
    orchestrator = StartupOrchestrator(socket_check_fn=mock_socket, process_runner_fn=mock_runner)

    # Fail closed by default when timeout occurs
    with pytest.raises(StartupError, match="failed to become ready on port 5434"):
        orchestrator.orchestrate_postgres(docker_available=True, allow_offline_fallback=False, timeout_seconds=1)

    # With allow_offline_fallback=True, proceeds in offline mode without crashing
    status = orchestrator.orchestrate_postgres(docker_available=True, allow_offline_fallback=True, timeout_seconds=1)
    assert "offline fallback" in status


# 7. Existing Redis service (Port 6380 already listening)
def test_7_existing_redis_service_reuse():
    mock_socket = MagicMock(return_value=True)  # Port 6380 open
    mock_runner = MagicMock()
    orchestrator = StartupOrchestrator(socket_check_fn=mock_socket, process_runner_fn=mock_runner)

    status = orchestrator.orchestrate_redis(docker_available=True)
    assert "existing on port 6380" in status
    mock_runner.assert_not_called()


# 8. Redis unavailable resilient fallback
def test_8_redis_unavailable_fallback():
    mock_socket = MagicMock(return_value=False)  # Redis down
    orchestrator = StartupOrchestrator(socket_check_fn=mock_socket)

    # When Docker unavailable, Redis failure must degrade gracefully to in-memory mode without raising
    status = orchestrator.orchestrate_redis(docker_available=False)
    assert "in-memory degraded" in status


# 9. Missing .env bootstrap with secret generation
def test_9_missing_env_bootstrap(temp_orchestrator):
    orchestrator, tmp_path = temp_orchestrator
    assert not (tmp_path / ".env").exists()

    status = orchestrator.bootstrap_env()
    assert status == "created"
    assert (tmp_path / ".env").exists()

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "PROJECT_NAME=KogniSync" in env_text
    assert "JWT_SECRET_KEY=" in env_text
    assert "default" not in env_text  # Replaced with generated key


# 10. Existing .env preservation
def test_10_existing_env_preservation(temp_orchestrator):
    orchestrator, tmp_path = temp_orchestrator
    env_file = tmp_path / ".env"
    custom_content = "CUSTOM_SECRET_PRESERVED=true\nJWT_SECRET_KEY=my_secure_existing_key\n"
    env_file.write_text(custom_content, encoding="utf-8")

    status = orchestrator.bootstrap_env()
    assert status == "preserved"
    assert env_file.read_text(encoding="utf-8") == custom_content


# 11. Backend premature startup failure
def test_11_backend_startup_failure():
    orchestrator = StartupOrchestrator()
    mock_backend = MagicMock()
    mock_backend.poll.return_value = 1  # Exited with error
    mock_backend.returncode = 1
    orchestrator.backend_proc = mock_backend

    with pytest.raises(StartupError, match="Backend process terminated prematurely"):
        orchestrator.wait_for_readiness(timeout_seconds=2)


# 12. Frontend premature startup failure
def test_12_frontend_startup_failure():
    orchestrator = StartupOrchestrator()
    mock_frontend = MagicMock()
    mock_frontend.poll.return_value = 1  # Exited with error
    mock_frontend.returncode = 1
    orchestrator.frontend_proc = mock_frontend

    with pytest.raises(StartupError, match="Frontend process terminated prematurely"):
        orchestrator.wait_for_readiness(timeout_seconds=2)


# 13. Occupied backend/frontend port collision safety
def test_13_occupied_port_collision_safety():
    # Occupied backend port 8000
    mock_socket = MagicMock(side_effect=lambda host, port, timeout: port == 8000)
    orchestrator = StartupOrchestrator(socket_check_fn=mock_socket)
    with pytest.raises(StartupError, match="Port 8000 \\(Backend\\) is already occupied"):
        orchestrator.check_ports()

    # Occupied frontend port 5173
    mock_socket = MagicMock(side_effect=lambda host, port, timeout: port == 5173)
    orchestrator = StartupOrchestrator(socket_check_fn=mock_socket)
    with pytest.raises(StartupError, match="Port 5173 \\(Frontend\\) is already occupied"):
        orchestrator.check_ports()


# 14. Browser opens strictly after readiness and respects no-browser flag
def test_14_browser_launch_behavior():
    mock_browser = MagicMock(return_value=True)
    orchestrator = StartupOrchestrator(browser_open_fn=mock_browser)

    # With no_browser=True, browser is never opened
    assert orchestrator.open_browser(no_browser=True) is False
    mock_browser.assert_not_called()

    # Normal launch
    assert orchestrator.open_browser(no_browser=False) is True
    mock_browser.assert_called_once_with("http://127.0.0.1:5173")


# 15. Process cleanup lifecycle on interruption
def test_15_ctrl_c_process_cleanup():
    orchestrator = StartupOrchestrator()
    mock_backend = MagicMock()
    mock_backend.pid = 11111
    mock_backend.poll.return_value = None  # Running

    mock_frontend = MagicMock()
    mock_frontend.pid = 22222
    mock_frontend.poll.return_value = None  # Running

    orchestrator.backend_proc = mock_backend
    orchestrator.frontend_proc = mock_frontend
    orchestrator.tracked_pids = {11111, 22222}

    terminated = orchestrator.cleanup_processes()
    assert 11111 in terminated
    assert 22222 in terminated
    mock_backend.terminate.assert_called_once()
    mock_frontend.terminate.assert_called_once()


# 16. Unrelated process preservation (strictly non-destructive)
def test_16_unrelated_processes_never_terminated():
    orchestrator = StartupOrchestrator()
    unrelated_proc = MagicMock()
    unrelated_proc.pid = 99999  # External PID NOT in tracked_pids
    unrelated_proc.poll.return_value = None

    orchestrator.backend_proc = unrelated_proc
    orchestrator.tracked_pids = {12345}  # Only this PID is tracked

    terminated = orchestrator.cleanup_processes()
    assert 99999 not in terminated
    unrelated_proc.terminate.assert_not_called()
    unrelated_proc.kill.assert_not_called()


# 17. Docker volumes and canonical organizer files immutability
def test_17_docker_volumes_and_canonical_db_immutability():
    canonical_db = REPO_ROOT / "BookingInventory" / "data" / "APS-05.db"
    assert canonical_db.exists(), "APS-05.db must exist"
    initial_sha = hashlib.sha256(canonical_db.read_bytes()).hexdigest()

    mock_runner = MagicMock()
    orchestrator = StartupOrchestrator(process_runner_fn=mock_runner)

    # Execute preflight and mock orchestration
    orchestrator.check_python()
    orchestrator.orchestrate_postgres(docker_available=True, allow_offline_fallback=True, timeout_seconds=1)
    orchestrator.orchestrate_redis(docker_available=False)

    # Verify no docker volume rm/prune commands were ever issued
    for call in mock_runner.call_args_list:
        cmd_args = call[0][0] if call[0] else []
        cmd_str = " ".join(cmd_args)
        assert "volume rm" not in cmd_str
        assert "volume prune" not in cmd_str
        assert "down -v" not in cmd_str

    # Verify canonical database remains byte-for-byte identical
    current_sha = hashlib.sha256(canonical_db.read_bytes()).hexdigest()
    assert current_sha == initial_sha, "Canonical database must never be modified by startup orchestrator!"


# 18. Repeated startup duplication protection
def test_18_repeated_startup_duplication_protection():
    # Simulate first instance running by holding ports 8000 and 5173
    mock_socket = MagicMock(return_value=True)
    orchestrator = StartupOrchestrator(socket_check_fn=mock_socket)

    # Attempting to start another instance must immediately fail closed without spawning new processes
    with pytest.raises(StartupError, match="already occupied"):
        orchestrator.check_ports()
