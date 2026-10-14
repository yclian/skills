<#
.SYNOPSIS
  fleet-backup.ps1 -- Automated Hub-and-Spoke fleet backup orchestrator.

.DESCRIPTION
  Orchestrates scheduled multi-node encrypted backups into a local restic repository.
  1. Runs local SQLite atomic .backup pre-hooks.
  2. Executes remote SSH pre-hooks on 24/7 server nodes (Layer 1).
  3. Pulls staged directories via rclone SFTP into local NVMe staging with link-skipping.
  4. Probes and opportunistically pulls workstation/laptop nodes (Layer 2).
  5. Commits each staged remote node into the local restic repository.
  6. Takes a live Windows Volume Shadow Copy (VSS) snapshot of the Hub's local data.
  7. Invokes retention maintenance.
#>

param(
  [switch]$SkipRemote,
  [switch]$SkipMaintenance
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Configuration (Adjust for your environment) ---
$BackupDriveLetter = 'D'
$ExpectedLabel     = 'FLEET_BACKUP'
$BackupRoot        = 'D:\FleetBackup'
$ResticRepo        = 'D:\FleetBackup\.restic-repo'
$CanaryFile        = 'D:\FleetBackup\.Repository-Canary'

$ProgramDataRoot   = 'C:\ProgramData\FleetBackup'
$StagingRoot       = Join-Path $ProgramDataRoot 'staging'
$SecretsRoot       = Join-Path $ProgramDataRoot 'secrets'
$RcloneConfig      = Join-Path $SecretsRoot     'rclone.conf'
$ResticPassFile    = Join-Path $SecretsRoot     'restic-password.txt'
$SshKeyPath        = Join-Path $SecretsRoot     'id_rsa'
$KnownHostsPath    = Join-Path $SecretsRoot     'known_hosts'
$LockFile          = Join-Path $ProgramDataRoot 'backup.lock'

$RcloneExe         = 'C:\tools\bin\rclone.exe'
$ResticExe         = 'C:\tools\bin\restic.exe'
$PythonExe         = 'python.exe'
$SshExe            = 'C:\Windows\System32\OpenSSH\ssh.exe'

$DateStamp         = Get-Date -Format 'yyyyMMdd'
$LogDir            = Join-Path $BackupRoot 'logs'
if (-not (Test-Path -LiteralPath $LogDir)) {
  $LogDir = Join-Path $ProgramDataRoot 'logs'
}
if (-not (Test-Path -LiteralPath $LogDir)) {
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$Script:ActiveLogFile = Join-Path $LogDir "backup-$DateStamp.log"

function Write-BackupLog {
  param([string]$Message, [string]$Level = 'INFO')
  $line = '{0}  [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
  Add-Content -LiteralPath $Script:ActiveLogFile -Value $line -Encoding UTF8
  Write-Host $line
}

function Acquire-Lock {
  if (Test-Path -LiteralPath $LockFile) {
    $existingPid = 0
    try {
      $existingPid = [int]((Get-Content -LiteralPath $LockFile -Raw).Trim())
    } catch {}
    if ($existingPid -gt 0) {
      $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
      if ($proc) {
        throw "Another backup process (PID $existingPid) is currently running."
      }
      Write-BackupLog "Removing stale lockfile from dead PID $existingPid" 'WARN'
    }
  }
  Set-Content -LiteralPath $LockFile -Value $PID -Encoding ASCII -Force
}

function Release-Lock {
  if (Test-Path -LiteralPath $LockFile) {
    Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
  }
}

function Assert-TargetVolume {
  $vol = Get-Volume -DriveLetter $BackupDriveLetter -ErrorAction Stop
  if ($vol.FileSystemLabel -ne $ExpectedLabel) {
    throw "Backup volume label is '$($vol.FileSystemLabel)', expected '$ExpectedLabel'."
  }
  if (-not (Test-Path -LiteralPath $CanaryFile)) {
    throw "Canary sentinel file missing at '$CanaryFile'."
  }
}

function Invoke-RcloneSync {
  param(
    [Parameter(Mandatory = $true)][string]$SourceSpec,
    [Parameter(Mandatory = $true)][string]$DestPath,
    [string]$ExcludeFile = ''
  )
  if (-not (Test-Path -LiteralPath $DestPath)) {
    New-Item -ItemType Directory -Path $DestPath -Force | Out-Null
  }
  Write-BackupLog "rclone sync $SourceSpec -> $DestPath"
  $rcloneArgs = @(
    'sync', $SourceSpec, $DestPath,
    '--config', $RcloneConfig,
    '--transfers', '4',
    '--checkers', '8',
    '--sftp-skip-links',
    '--skip-links',
    '--retries', '3'
  )
  if ($ExcludeFile -and (Test-Path -LiteralPath $ExcludeFile)) {
    $rcloneArgs += @('--exclude-from', $ExcludeFile)
  }

  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & $RcloneExe @rcloneArgs 2>&1 | ForEach-Object { Write-BackupLog "  [rclone] $_" }
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $prevEAP
  }

  if ($exitCode -eq 0) {
    Write-BackupLog "rclone sync succeeded for $SourceSpec"
  } elseif ($exitCode -eq 1) {
    Write-BackupLog "rclone sync completed with non-fatal file/symlink warnings (exit 1) for $SourceSpec" 'WARN'
  } elseif ($exitCode -eq 3) {
    Write-BackupLog "Source directory not found for $SourceSpec (exit 3) -- skipping optional path" 'WARN'
  } else {
    throw "rclone sync failed for $SourceSpec (exit code $exitCode)"
  }
}

function Invoke-ResticBackup {
  param(
    [Parameter(Mandatory = $true)][string]$HostName,
    [Parameter(Mandatory = $true)][string[]]$Paths,
    [string]$ExcludeFile = '',
    [switch]$UseVss
  )
  $resticArgs = @(
    '-r', $ResticRepo,
    '--password-file', $ResticPassFile,
    'backup',
    '--host', $HostName,
    '--tag', 'scheduled'
  )
  if ($UseVss) { $resticArgs += '--use-fs-snapshot' }
  if ($ExcludeFile -and (Test-Path -LiteralPath $ExcludeFile)) {
    $resticArgs += @('--exclude-file', $ExcludeFile)
  }
  $resticArgs += $Paths

  Write-BackupLog "restic backup --host $HostName ($($Paths -join ', '))"
  $prevEAP = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & $ResticExe @resticArgs 2>&1 | ForEach-Object { Write-BackupLog "  [restic:$HostName] $_" }
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $prevEAP
  }

  if ($exitCode -eq 0) {
    Write-BackupLog "restic backup succeeded for host '$HostName'"
  } elseif ($exitCode -eq 3) {
    Write-BackupLog "restic backup completed with non-fatal partial read warnings (exit 3) for '$HostName'" 'WARN'
  } else {
    throw "restic backup failed for host '$HostName' with exit code $exitCode"
  }
}

try {
  Acquire-Lock
  Assert-TargetVolume
  Write-BackupLog "=== Starting Fleet Backup Run (PID $PID) ==="

  # 1. Local SQLite Pre-Hook
  $pyScript = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'backup_sqlite.py'
  if (Test-Path -LiteralPath $pyScript) {
    Write-BackupLog "Running local SQLite pre-hooks..."
    & $PythonExe $pyScript "C:\tools\data" "C:\Users\service\state" 2>&1 | ForEach-Object { Write-BackupLog "  [sqlite] $_" }
  }

  # 2. Remote Node Backup (Example Server)
  if (-not $SkipRemote) {
    try {
      Write-BackupLog "Executing remote pre-hook on primary server..."
      & $SshExe -i $SshKeyPath -o BatchMode=yes operator@primary-server "sudo /usr/local/sbin/prepare-node.sh"

      $serverStage = Join-Path $StagingRoot 'primary-server'
      Invoke-RcloneSync -SourceSpec 'primary-server:/srv/backup-export' -DestPath $serverStage
      Invoke-ResticBackup -HostName 'primary-server' -Paths @($serverStage)
    } catch {
      Write-BackupLog "Primary server backup failed: $($_.Exception.Message)" 'ERROR'
    }
  }

  # 3. Local Storage Hub Snapshot (with VSS)
  try {
    Invoke-ResticBackup -HostName 'storage-hub' -Paths @(
      'C:\Users\service\data',
      'C:\tools\config'
    ) -UseVss
  } catch {
    Write-BackupLog "Local storage hub backup failed: $($_.Exception.Message)" 'ERROR'
  }

  # 4. Scheduled Maintenance Trigger
  if (-not $SkipMaintenance) {
    Write-BackupLog "Triggering maintenance pass..."
    $maintScript = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'fleet-maintenance.ps1'
    if (Test-Path -LiteralPath $maintScript) {
      & powershell.exe -File $maintScript -Mode Daily
    }
  }

  Write-BackupLog "=== Fleet Backup Run Completed Successfully ==="
} catch {
  Write-BackupLog "Fatal backup error: $($_.Exception.Message)" 'ERROR'
  exit 1
} finally {
  Release-Lock
}
