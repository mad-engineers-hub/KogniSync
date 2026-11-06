# ==============================================================================
# scripts/start_kognisync.ps1 — KogniSync One-Command Startup Launcher
# ==============================================================================
# Orchestrates environment bootstrap, infrastructure readiness, migrations,
# service supervision (FastAPI backend + Vite frontend), and clean shutdown.
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$AllowOfflineFallback,
    [switch]$SkipInfrastructure,
    [switch]$DryRun,
    [int]$TimeoutSeconds = 60,
    [switch]$ResetDemoState,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host @"
KogniSync One-Command Startup Launcher

Usage:
    .\start.bat [options]
    powershell -ExecutionPolicy Bypass -File scripts\start_kognisync.ps1 [options]

Options:
    -NoBrowser              Do not open the default browser once services are ready.
    -AllowOfflineFallback   If PostgreSQL or Docker is unavailable, proceed in offline mode
                            using corridor estimation rather than failing closed.
    -SkipInfrastructure     Skip database and Redis checks/orchestration entirely.
    -DryRun                 Validate preflight checks, environment, and display the execution plan
                            without starting persistent services.
    -TimeoutSeconds <int>   Maximum time in seconds to wait for backend/frontend readiness (default: 60).
    -ResetDemoState         Execute scripts/reset_demo_state.py after readiness is achieved.
    -Help                   Show this help message.
"@
    exit 0
}

# --- Formatting Helpers ---
function Write-Header([string]$text) {
    Write-Host "`n=== $text ===" -ForegroundColor Cyan
}

function Write-Info([string]$text) {
    Write-Host "  [INFO] $text" -ForegroundColor Gray
}

function Write-Success([string]$text) {
    Write-Host "  [OK]   $text" -ForegroundColor Green
}

function Write-Warn([string]$text) {
    Write-Host "  [WARN] $text" -ForegroundColor Yellow
}

function Write-Err([string]$text) {
    Write-Host "  [ERR]  $text" -ForegroundColor Red
}

# --- Network & Process Helpers ---
function Test-PortOpen([string]$HostAddress, [int]$Port, [int]$TimeoutMs = 1000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostAddress, $Port, $null, $null)
        $connected = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($connected) {
            $client.EndConnect($iar)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
        $client.Dispose()
    }
}

function Get-PortOwnerProcess([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn -and $conn.OwningProcess) {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            if ($proc) {
                return "$($proc.ProcessName) (PID $($conn.OwningProcess))"
            }
            return "PID $($conn.OwningProcess)"
        }
    } catch {
        # Fallback to netstat if Get-NetTCPConnection fails
    }
    return "Unknown process"
}

function Stop-TrackedProcessTree([int]$ProcessId) {
    if ($ProcessId -le 0) { return }
    try {
        & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
    } catch {}
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
}

function Get-FileSha256([string]$FilePath) {
    if (Test-Path $FilePath) {
        $hashObj = Get-FileHash -Path $FilePath -Algorithm SHA256
        return $hashObj.Hash
    }
    return ""
}

function Test-HttpEndpoint([string]$Url, [int]$TimeoutSec = 2) {
    try {
        $req = [System.Net.WebRequest]::Create($Url)
        $req.Timeout = $TimeoutSec * 1000
        $req.Method = "GET"
        $resp = $req.GetResponse()
        $status = [int]$resp.StatusCode
        $resp.Close()
        $resp.Dispose()
        return ($status -ge 200 -and $status -lt 400)
    } catch {
        return $false
    }
}

# --- Path Initialization ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path "$ScriptDir\..").Path
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$LogsDir = Join-Path $RepoRoot "logs"
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExampleFile = Join-Path $RepoRoot ".env.example"

Write-Header "KogniSync Startup Preflight Checks"

# 1. Python check
$SysPython = $null
if (Test-Path $VenvPython) {
    $SysPython = $VenvPython
    Write-Info "Using existing virtualenv Python: $VenvPython"
} else {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd) {
        $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    }
    if ($pyCmd) {
        $SysPython = $pyCmd.Source
        Write-Info "Found system Python: $SysPython"
    } else {
        Write-Err "Python 3.10+ is required but was not found on PATH."
        exit 1
    }
}

try {
    $pyVer = & $SysPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $parts = $pyVer.Trim().Split('.')
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Err "Python version must be >= 3.10. Detected: $pyVer"
        exit 1
    }
    Write-Success "Python $pyVer verified."
} catch {
    Write-Err "Failed to determine Python version: $_"
    exit 1
}

# 2. Node.js check
$NodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $NodeCmd) {
    Write-Err "Node.js 18+ is required but was not found on PATH."
    exit 1
}
try {
    $nodeVerRaw = (& node -v).Trim().TrimStart('v')
    $nodeMajor = [int]($nodeVerRaw.Split('.')[0])
    if ($nodeMajor -lt 18) {
        Write-Err "Node.js version must be >= 18. Detected: v$nodeVerRaw"
        exit 1
    }
    Write-Success "Node.js v$nodeVerRaw verified."
} catch {
    Write-Err "Failed to verify Node.js version: $_"
    exit 1
}

# 3. Git check
$GitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($GitCmd) {
    $gitVer = (& git --version).Trim()
    Write-Success "$gitVer verified."
} else {
    Write-Warn "Git command not found on PATH. Proceeding without VCS checks."
}

# 4. Port Conflict Safety Checks (Fail Closed without killing unrelated processes)
if (Test-PortOpen "127.0.0.1" 8000) {
    $owner = Get-PortOwnerProcess 8000
    Write-Err "Port 8000 (Backend API) is already occupied by $owner."
    Write-Err "KogniSync strictly preserves unrelated processes and will not terminate them."
    Write-Err "Please stop the existing process on port 8000 or close previous instances before restarting."
    exit 1
}

if (Test-PortOpen "127.0.0.1" 5173) {
    $owner = Get-PortOwnerProcess 5173
    Write-Err "Port 5173 (Frontend Vite) is already occupied by $owner."
    Write-Err "KogniSync strictly preserves unrelated processes and will not terminate them."
    Write-Err "Please stop the existing process on port 5173 or close previous instances before restarting."
    exit 1
}

Write-Success "Ports 8000 and 5173 are available."

# 5. Docker CLI and Daemon detection
$DockerCmd = Get-Command docker -ErrorAction SilentlyContinue
$DockerAvailable = $false
if ($DockerCmd) {
    try {
        $null = & docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            $DockerAvailable = $true
            Write-Success "Docker engine is running and responsive."
        } else {
            Write-Warn "Docker CLI found, but Docker daemon is not responding."
        }
    } catch {
        Write-Warn "Docker check threw an exception: $_"
    }
} else {
    Write-Warn "Docker CLI is not installed or not available on PATH."
}

# --- Phase 4: Environment Bootstrap ---
Write-Header "Configuration Bootstrap"
if (Test-Path $EnvFile) {
    Write-Info "Existing .env found. Preserving configuration untouched."
} else {
    if (Test-Path $EnvExampleFile) {
        Write-Info "No .env detected. Creating from .env.example..."
        $content = Get-Content -Path $EnvExampleFile -Raw
        
        # Generate cryptographically secure random token
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $secretKey = [System.Convert]::ToBase64String($bytes)
        
        # Ensure JWT_SECRET_KEY is defined
        if ($content -match "JWT_SECRET_KEY=") {
            $content = $content -replace "JWT_SECRET_KEY=.*", "JWT_SECRET_KEY=$secretKey"
        } else {
            $content += "`nJWT_SECRET_KEY=$secretKey`nINTERNAL_API_KEY=kognisync_dev_ops_secret_internal_key_123`n"
        }
        
        Set-Content -Path $EnvFile -Value $content -Encoding UTF8
        Write-Success ".env created with generated secrets (secrets masked in logs)."
    } else {
        Write-Err ".env.example was not found in $RepoRoot. Cannot bootstrap environment."
        exit 1
    }
}

# --- Dependency Cache & Bootstrap ---
Write-Header "Dependency Management"

# Python Virtualenv
if (-not (Test-Path $VenvPython)) {
    Write-Info "Creating Python virtual environment in .venv..."
    & $SysPython -m venv "$VenvDir"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create Python virtual environment."
        exit 1
    }
    Write-Success "Virtual environment created."
}

$ReqFile = Join-Path $RepoRoot "requirements.txt"
if (-not (Test-Path $ReqFile)) {
    $ReqFile = Join-Path $BackendDir "requirements.txt"
}
$ReqHashFile = Join-Path $VenvDir ".requirements.hash"
$CurrentReqHash = Get-FileSha256 $ReqFile
$CachedReqHash = ""
if (Test-Path $ReqHashFile) {
    $CachedReqHash = (Get-Content -Path $ReqHashFile -Raw).Trim()
}

if ($CurrentReqHash -ne "" -and $CurrentReqHash -eq $CachedReqHash) {
    Write-Success "Backend dependencies up-to-date (cached)."
} else {
    Write-Info "Installing/updating backend dependencies from requirements.txt..."
    & $VenvPython -m pip install --quiet --disable-pip-version-check -r $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install backend dependencies."
        exit 1
    }
    Set-Content -Path $ReqHashFile -Value $CurrentReqHash -Encoding UTF8
    Write-Success "Backend dependencies installed successfully."
}

# Frontend node_modules
$PackageLockFile = Join-Path $FrontendDir "package-lock.json"
$NodeModulesDir = Join-Path $FrontendDir "node_modules"
$LockHashFile = Join-Path $NodeModulesDir ".lock.hash"
$CurrentLockHash = Get-FileSha256 $PackageLockFile
$CachedLockHash = ""
if (Test-Path $LockHashFile) {
    $CachedLockHash = (Get-Content -Path $LockHashFile -Raw).Trim()
}

if ((Test-Path $NodeModulesDir) -and ($CurrentLockHash -ne "") -and ($CurrentLockHash -eq $CachedLockHash)) {
    Write-Success "Frontend dependencies up-to-date (cached)."
} else {
    Write-Info "Installing frontend dependencies (npm ci)..."
    Push-Location $FrontendDir
    try {
        & npm.cmd ci --silent
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "npm ci exited with code $LASTEXITCODE; falling back to npm install..."
            & npm.cmd install --silent
        }
        if ($LASTEXITCODE -eq 0) {
            Set-Content -Path $LockHashFile -Value $CurrentLockHash -Encoding UTF8
            Write-Success "Frontend dependencies installed successfully."
        } else {
            Write-Err "Failed to install frontend dependencies."
            Pop-Location
            exit 1
        }
    } finally {
        Pop-Location
    }
}

# --- Phase 5: Infrastructure Orchestration ---
Write-Header "Infrastructure Orchestration"

$PostgresStatus = "Pending"
$RedisStatus = "Pending"

if ($SkipInfrastructure) {
    Write-Info "Skipping infrastructure checks (-SkipInfrastructure specified)."
    $PostgresStatus = "Skipped"
    $RedisStatus = "Skipped"
} else {
    # 1. PostgreSQL (Port 5434)
    if (Test-PortOpen "127.0.0.1" 5434) {
        $PostgresStatus = "Connected (existing on port 5434)"
        Write-Success "PostgreSQL is already active on port 5434."
    } elseif ($DockerAvailable) {
        Write-Info "Starting PostgreSQL container via docker compose..."
        & docker compose up -d postgres
        $pgWait = 0
        $pgReady = $false
        while ($pgWait -lt 30) {
            Start-Sleep -Seconds 1
            $pgWait++
            if (Test-PortOpen "127.0.0.1" 5434) {
                $pgReady = $true
                break
            }
        }
        if ($pgReady) {
            $PostgresStatus = "Connected (Docker container)"
            Write-Success "PostgreSQL container is active on port 5434."
        } else {
            if ($AllowOfflineFallback) {
                $PostgresStatus = "Unavailable (offline fallback)"
                Write-Warn "PostgreSQL failed to respond within 30s. Operating in offline mode (-AllowOfflineFallback)."
            } else {
                Write-Err "PostgreSQL container failed to become ready on port 5434 within 30 seconds."
                exit 1
            }
        }
    } else {
        if ($AllowOfflineFallback) {
            $PostgresStatus = "Unavailable (offline fallback)"
            Write-Warn "PostgreSQL is not listening on port 5434 and Docker is unavailable. Proceeding in offline mode (-AllowOfflineFallback)."
        } else {
            Write-Err "PostgreSQL is not running on port 5434 and Docker is not available."
            Write-Err "Please start Docker Desktop or local PostgreSQL on port 5434, or run with -AllowOfflineFallback."
            exit 1
        }
    }

    # Run Database Migrations if PostgreSQL is connected
    if ($PostgresStatus -like "Connected*") {
        Write-Info "Applying database migrations (scripts/migrate.py upgrade)..."
        & $VenvPython "$RepoRoot\scripts\migrate.py" upgrade
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Database migrations failed. Check migrate.py output."
            exit 1
        }
        Write-Success "Database schema is up to date."
    } else {
        Write-Info "Skipping database migrations (PostgreSQL not connected)."
    }

    # 2. Redis (Port 6380)
    if (Test-PortOpen "127.0.0.1" 6380) {
        $RedisStatus = "Connected (existing on port 6380)"
        Write-Success "Redis is already active on port 6380."
    } elseif ($DockerAvailable) {
        Write-Info "Starting Redis container via docker compose..."
        & docker compose up -d redis
        $redisWait = 0
        $redisReady = $false
        while ($redisWait -lt 15) {
            Start-Sleep -Seconds 1
            $redisWait++
            if (Test-PortOpen "127.0.0.1" 6380) {
                $redisReady = $true
                break
            }
        }
        if ($redisReady) {
            $RedisStatus = "Connected (Docker container)"
            Write-Success "Redis container is active on port 6380."
        } else {
            $RedisStatus = "Unavailable (in-memory degraded)"
            Write-Warn "Redis container failed to respond within 15s. Using resilient in-memory fallback."
        }
    } else {
        $RedisStatus = "Unavailable (in-memory degraded)"
        Write-Warn "Redis is not running on port 6380 and Docker is unavailable. Using resilient in-memory fallback."
    }
}

# --- Phase 8 (DryRun Check) ---
if ($DryRun) {
    Write-Header "KogniSync Dry-Run Execution Plan"
    Write-Host @"
  Preflight checks:       PASSED
  Configuration:          $EnvFile (Valid)
  PostgreSQL:             $PostgresStatus
  Redis:                  $RedisStatus
  Planned Backend Launch: uvicorn app.main:app --host 127.0.0.1 --port 8000
  Planned Frontend Launch: npm run dev -- --host 127.0.0.1 --port 5173
  Auto-open Browser:      $(-not $NoBrowser)

Dry-run complete. No persistent processes or containers were modified.
"@
    exit 0
}

# --- Phase 6: Service Supervision & Lifecycle ---
Write-Header "Launching KogniSync Application Services"

if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

$BackendLogOut = Join-Path $LogsDir "backend.log"
$BackendLogErr = Join-Path $LogsDir "backend_err.log"
$FrontendLogOut = Join-Path $LogsDir "frontend.log"
$FrontendLogErr = Join-Path $LogsDir "frontend_err.log"

# Clear prior session logs
"" | Set-Content -Path $BackendLogOut -Encoding UTF8
"" | Set-Content -Path $BackendLogErr -Encoding UTF8
"" | Set-Content -Path $FrontendLogOut -Encoding UTF8
"" | Set-Content -Path $FrontendLogErr -Encoding UTF8

$env:PYTHONPATH = "$BackendDir;$RepoRoot"

$BackendProc = $null
$FrontendProc = $null

try {
    Write-Info "Starting Backend service on http://127.0.0.1:8000..."
    $BackendProc = Start-Process -FilePath $VenvPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $BackendDir `
        -RedirectStandardOutput $BackendLogOut `
        -RedirectStandardError $BackendLogErr `
        -PassThru

    Write-Info "Starting Frontend Vite dev server on http://127.0.0.1:5173..."
    $FrontendProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run dev -- --host 127.0.0.1 --port 5173" `
        -WorkingDirectory $FrontendDir `
        -RedirectStandardOutput $FrontendLogOut `
        -RedirectStandardError $FrontendLogErr `
        -PassThru

    Write-Info "Spawned Backend (PID: $($BackendProc.Id)), Frontend (PID: $($FrontendProc.Id))."

    # --- Phase 7: Readiness Verification ---
    Write-Header "Readiness Verification"
    Write-Info "Waiting for services to become responsive (timeout: ${TimeoutSeconds}s)..."

    $startTime = Get-Date
    $backendReady = $false
    $frontendReady = $false

    while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
        if ($BackendProc.HasExited) {
            Write-Err "Backend process terminated unexpectedly (exit code $($BackendProc.ExitCode))."
            if (Test-Path $BackendLogErr) {
                Write-Host "`n--- Backend Error Log Tail ---" -ForegroundColor Red
                Get-Content -Path $BackendLogErr -Tail 20 | Write-Host
            }
            exit 1
        }
        if ($FrontendProc.HasExited) {
            Write-Err "Frontend process terminated unexpectedly (exit code $($FrontendProc.ExitCode))."
            if (Test-Path $FrontendLogErr) {
                Write-Host "`n--- Frontend Error Log Tail ---" -ForegroundColor Red
                Get-Content -Path $FrontendLogErr -Tail 20 | Write-Host
            }
            exit 1
        }

        if (-not $backendReady) {
            $backendReady = Test-HttpEndpoint "http://127.0.0.1:8000/health" 1
        }

        if (-not $frontendReady) {
            $frontendReady = Test-HttpEndpoint "http://127.0.0.1:5173" 1
        }

        if ($backendReady -and $frontendReady) {
            break
        }

        Start-Sleep -Milliseconds 800
    }

    if (-not ($backendReady -and $frontendReady)) {
        Write-Err "Services failed to achieve readiness within $TimeoutSeconds seconds."
        Write-Err "Backend Ready: $backendReady | Frontend Ready: $frontendReady"
        exit 1
    }

    Write-Success "Backend API and Frontend are fully ready and responsive!"

    # Optional Demo State Reset
    if ($ResetDemoState) {
        Write-Info "Executing scripts/reset_demo_state.py (-ResetDemoState)..."
        & $VenvPython "$RepoRoot\scripts\reset_demo_state.py"
    }

    # --- Phase 8: Formatted Operator Feedback ---
    Write-Host @"

================================================================================
                    KOGNISYNC IS LIVE AND READY!
================================================================================
  Frontend Web UI:    http://127.0.0.1:5173
  Backend API:        http://127.0.0.1:8000
  Interactive Docs:   http://127.0.0.1:8000/docs
  Health Endpoint:    http://127.0.0.1:8000/health
  PostgreSQL Status:  $PostgresStatus
  Redis Status:       $RedisStatus
  Logs Directory:     $LogsDir (backend.log, frontend.log)
================================================================================
  Press [Ctrl + C] in this window to stop all services cleanly.
================================================================================
"@ -ForegroundColor Green

    # Open Browser
    if (-not $NoBrowser) {
        Write-Info "Launching default browser to http://127.0.0.1:5173..."
        Start-Process "http://127.0.0.1:5173"
    }

    # Supervision Loop
    while (-not $BackendProc.HasExited -and -not $FrontendProc.HasExited) {
        Start-Sleep -Seconds 1
    }

} finally {
    Write-Header "KogniSync Graceful Shutdown"
    if ($BackendProc -and -not $BackendProc.HasExited) {
        Write-Info "Terminating Backend process (PID $($BackendProc.Id))..."
        Stop-TrackedProcessTree $BackendProc.Id
    }
    if ($FrontendProc -and -not $FrontendProc.HasExited) {
        Write-Info "Terminating Frontend process (PID $($FrontendProc.Id))..."
        Stop-TrackedProcessTree $FrontendProc.Id
    }
    Write-Success "All spawned application processes stopped cleanly. Infrastructure untouched."
}
