# setup_morning_task.ps1
# Right-click this file → "Run with PowerShell" (as Administrator)
# Creates a Windows Task Scheduler entry that runs the BLEE Morning Preview
# every weekday at 10:00 AM ET automatically — no Cowork app needed.

$taskName   = "BLEE Morning Preview"
$batFile    = "C:\Kei\ComposerInvest\run_morning_preview.bat"
$startTime  = "10:00"

# Remove old task if exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Build action: run the batch file hidden (no cmd window flash)
$action  = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batFile`" >> `"C:\Kei\ComposerInvest\morning_preview.log`" 2>&1"

# Trigger: Mon–Fri at 10:00 AM
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At $startTime

# Settings: run even on battery, wake to run, start if missed within 1 hr
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -WakeToRun `
    -MultipleInstances IgnoreNew

# Register under current user (no password needed for interactive session)
Register-ScheduledTask `
    -TaskName   $taskName `
    -Action     $action `
    -Trigger    $trigger `
    -Settings   $settings `
    -RunLevel   Highest `
    -Force

Write-Host ""
Write-Host "✅  Task '$taskName' registered successfully!" -ForegroundColor Green
Write-Host "    Runs: Mon–Fri at $startTime"
Write-Host "    Script: $batFile"
Write-Host "    Log: C:\Kei\ComposerInvest\morning_preview.log"
Write-Host ""
Write-Host "To test it now, run:"
Write-Host "  schtasks /run /tn `"$taskName`""
Write-Host ""
Pause
