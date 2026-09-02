<#
.SYNOPSIS
    Register / remove the Windows Scheduled Task that watches for the next
    year's Web Room Booking system and books the rooms in targets.json.

.EXAMPLE
    # dry-run watcher, every 15 minutes (safe: never books)
    .\schedule.ps1 -Register

    # the real thing: books as soon as the instance opens
    .\schedule.ps1 -Register -Confirm

    .\schedule.ps1 -Status
    .\schedule.ps1 -Unregister
#>
[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Status,
    [switch]$Confirm,                       # pass --confirm to run.py
    [int]$IntervalMinutes = 15,
    [string]$TaskName = "WarwickRoomBookingWatcher"
)

$ErrorActionPreference = "Stop"
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $here ".venv\Scripts\python.exe"
$script = Join-Path $here "run.py"

if (-not (Test-Path $python)) { throw "venv python not found at $python" }
if (-not (Test-Path $script)) { throw "run.py not found at $script" }

if ($Status) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Write-Host "Task '$TaskName' is not registered."; return }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "Task      : $($t.TaskName)  [$($t.State)]"
    Write-Host "Action    : $($t.Actions[0].Execute) $($t.Actions[0].Arguments)"
    Write-Host "Last run  : $($info.LastRunTime)  result=$($info.LastTaskResult)"
    Write-Host "Next run  : $($info.NextRunTime)"
    return
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

if (-not $Register) {
    Write-Host "Nothing to do. Use -Register, -Unregister or -Status."
    return
}

# run.py does a single pass unless --loop is given, so each scheduled tick
# polls once and exits; the schedule itself provides the repetition, which
# survives reboots and logouts.
$argList = "`"$script`""
if ($Confirm) { $argList += " --confirm" }

$action = New-ScheduledTaskAction -Execute $python -Argument $argList -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Books Warwick rooms when the new WRB instance opens." `
    -Force | Out-Null

$mode = if ($Confirm) { "CONFIRM (will book for real)" } else { "dry run (will not book)" }
Write-Host "Registered '$TaskName': every $IntervalMinutes min, mode = $mode"
Write-Host "Logs: $(Join-Path $here 'watch.log')"
