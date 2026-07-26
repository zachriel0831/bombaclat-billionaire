# Lightweight Codex Observer telemetry for scheduled data-collecting jobs.

function Get-CodexObserverSessionId {
  if (-not [string]::IsNullOrWhiteSpace($env:CODEX_OBSERVER_SESSION_ID)) {
    return $env:CODEX_OBSERVER_SESSION_ID
  }
  return "data-collecting"
}

function Get-CodexObserverUrl {
  if (-not [string]::IsNullOrWhiteSpace($env:CODEX_OBSERVER_URL)) {
    return $env:CODEX_OBSERVER_URL.TrimEnd("/")
  }
  return "http://127.0.0.1:8765"
}

function Add-SafeObserverMetadata {
  param(
    [hashtable]$Target,
    [hashtable]$Source
  )

  foreach ($key in $Source.Keys) {
    $name = [string]$key
    if ($name -match "(?i)(secret|token|password|authorization|api.?key)") {
      continue
    }
    $Target[$name] = $Source[$key]
  }
}

function Send-CodexObserverEvent {
  param(
    [string]$EventType,
    [string]$Job,
    [string]$Category,
    [string]$Status,
    [string]$Skill = "",
    [string]$Rag = "",
    [string]$Model = "",
    [string]$RunId = "",
    [double]$DurationSeconds = -1,
    [int]$ExitCode = -9999,
    [hashtable]$Metadata = @{}
  )

  if ($env:CODEX_OBSERVER_DISABLED -match "^(1|true|yes)$") {
    return
  }

  $caller = Get-PSCallStack |
    Where-Object { $_.ScriptName -and (Split-Path -Leaf $_.ScriptName) -ne "codex_observer.ps1" } |
    Select-Object -First 1
  $callerScript = if ($caller) { Split-Path -Leaf $caller.ScriptName } else { Split-Path -Leaf $PSCommandPath }
  $meta = @{
    repo = "data-collecting"
    job = $Job
    category = $Category
    status = $Status
    script = $callerScript
    cwd = (Get-Location).Path
  }
  if ($RunId) {
    $meta["run_id"] = $RunId
  }
  if ($DurationSeconds -ge 0) {
    $meta["duration_seconds"] = [Math]::Round($DurationSeconds, 3)
  }
  if ($ExitCode -ne -9999) {
    $meta["exit_code"] = $ExitCode
  }
  Add-SafeObserverMetadata -Target $meta -Source $Metadata

  $payload = @{
    session_id = Get-CodexObserverSessionId
    event_type = $EventType
    agent_name = "data-collecting"
    agent_role = $Category
    metadata = $meta
  }
  if ($Skill) {
    $payload["skill"] = $Skill
  }
  if ($Rag) {
    $payload["rag"] = $Rag
  }
  if ($Model) {
    $payload["model"] = $Model
  }

  try {
    $url = (Get-CodexObserverUrl) + "/events"
    $json = $payload | ConvertTo-Json -Depth 8 -Compress
    Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body $json -TimeoutSec 2 | Out-Null
  }
  catch {
    return
  }
}

function Start-CodexObservedRun {
  param(
    [string]$Job,
    [string]$Category,
    [string]$Skill = "",
    [string]$Rag = "",
    [string]$Model = "",
    [hashtable]$Metadata = @{}
  )

  $run = [pscustomobject]@{
    Job = $Job
    Category = $Category
    Skill = $Skill
    Rag = $Rag
    Model = $Model
    RunId = [guid]::NewGuid().ToString("N")
    StartedAt = Get-Date
  }

  Send-CodexObserverEvent `
    -EventType "$($Category)_started" `
    -Job $Job `
    -Category $Category `
    -Status "started" `
    -Skill $Skill `
    -Rag $Rag `
    -Model $Model `
    -RunId $run.RunId `
    -Metadata $Metadata

  return $run
}

function Complete-CodexObservedRun {
  param(
    [pscustomobject]$Run,
    [int]$ExitCode,
    [hashtable]$Metadata = @{}
  )

  if (-not $Run) {
    return
  }

  $status = if ($ExitCode -eq 0) { "succeeded" } else { "failed" }
  $duration = ((Get-Date) - $Run.StartedAt).TotalSeconds
  Send-CodexObserverEvent `
    -EventType "$($Run.Category)_$status" `
    -Job $Run.Job `
    -Category $Run.Category `
    -Status $status `
    -Skill $Run.Skill `
    -Rag $Run.Rag `
    -Model $Run.Model `
    -RunId $Run.RunId `
    -DurationSeconds $duration `
    -ExitCode $ExitCode `
    -Metadata $Metadata
}

function Invoke-CodexObservedCommand {
  param(
    [string]$Job,
    [string]$Category,
    [string]$Skill = "",
    [string]$Rag = "",
    [string]$Model = "",
    [hashtable]$Metadata = @{},
    [scriptblock]$Command
  )

  $run = Start-CodexObservedRun -Job $Job -Category $Category -Skill $Skill -Rag $Rag -Model $Model -Metadata $Metadata
  try {
    & $Command
    $exitCode = if ($null -ne $global:LASTEXITCODE) { [int]$global:LASTEXITCODE } else { 0 }
    Complete-CodexObservedRun -Run $run -ExitCode $exitCode
    return $exitCode
  }
  catch {
    Complete-CodexObservedRun -Run $run -ExitCode 1 -Metadata @{ error_type = $_.Exception.GetType().Name }
    throw
  }
}
