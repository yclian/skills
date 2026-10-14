<#
.SYNOPSIS
  fleet-maintenance.ps1 -- Automated retention pruning and integrity verification.

.DESCRIPTION
  Manages grandfather-father-son snapshot retention policies and runs periodic
  cryptographic pack verification.
  - Mode 'Daily': Runs 'forget' without prune. Fast metadata-only retention cleanup.
  - Mode 'Weekly': Runs 'forget' with '--prune' to reclaim disk space, followed by 'check'.
#>

param(
  [ValidateSet('Daily', 'Weekly', 'BiWeekly')]
  [string]$Mode = 'Daily'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ResticRepo     = 'D:\FleetBackup\.restic-repo'
$ResticPassFile = 'C:\ProgramData\FleetBackup\secrets\restic-password.txt'
$ResticExe      = 'C:\tools\bin\restic.exe'

Write-Host "=== Starting Fleet Backup Maintenance (Mode: $Mode) ==="

# Physical storage health audit for weekly / bi-weekly runs
if ($Mode -in @('Weekly', 'BiWeekly')) {
  Write-Host "Checking physical disk S.M.A.R.T. and volume status..."
  $pDisks = Get-PhysicalDisk -ErrorAction SilentlyContinue
  foreach ($d in $pDisks) {
    if ($d.HealthStatus -ne 'Healthy' -or $d.OperationalStatus -ne 'OK') {
      Write-Warning "Physical disk '$($d.FriendlyName)' health status degraded ($($d.HealthStatus)/$($d.OperationalStatus))."
    }
  }
}

$forgetArgs = @(
  '-r', $ResticRepo,
  '--password-file', $ResticPassFile,
  'forget',
  '--keep-daily', '7',
  '--keep-weekly', '5',
  '--keep-monthly', '12',
  '--keep-yearly', '3'
)

if ($Mode -in @('Weekly', 'BiWeekly')) {
  $forgetArgs += '--prune'
}

Write-Host "Applying snapshot retention policy..."
& $ResticExe @forgetArgs

if ($Mode -in @('Weekly', 'BiWeekly')) {
  Write-Host "Verifying repository data integrity (10% subset)..."
  & $ResticExe -r $ResticRepo --password-file $ResticPassFile check --read-data-subset=10%
}

Write-Host "=== Maintenance Completed Successfully ==="
