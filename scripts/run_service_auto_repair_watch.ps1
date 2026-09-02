# Monitor local news/finance services and launch a Codex repair agent on warn+.
param(
  [string]$EnvFile = ".env",
  [int]$CooldownMinutes = 60,
  [int]$SourceAccuracyMaxAgeMinutes = 180,
  [switch]$LaunchAgent,
  [switch]$DryRun,
  [switch]$Json,
  [switch]$FailOnWarn
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = "D:\work_space\claude-box\workspace"
$logDir = Join-Path $ProjectRoot "runtime\logs"
$statusDir = Join-Path $ProjectRoot "runtime\status"
$repairDir = Join-Path $ProjectRoot "runtime\service-auto-repair"
$incidentDir = Join-Path $repairDir "incidents"
$stateFile = Join-Path $repairDir "state.json"
$statusFile = Join-Path $statusDir "service-auto-repair-watch-status.json"
$logFile = Join-Path $logDir "service-auto-repair-watch.log"

New-Item -ItemType Directory -Force -Path $logDir, $statusDir, $incidentDir | Out-Null
Set-Location -LiteralPath $ProjectRoot
. (Join-Path $PSScriptRoot "codex_observer.ps1")

function Write-AutoRepairLog {
  param([string]$Message)
  $line = "$(Get-Date -Format o) $Message"
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
  if (-not $Json) {
    Write-Host $line
  }
}

function Get-SeverityRank {
  param([string]$Status)
  switch ($Status) {
    "ok" { return 0 }
    "info" { return 0 }
    "disabled" { return 0 }
    "skipped" { return 0 }
    "warn" { return 1 }
    "stale" { return 2 }
    "missing" { return 2 }
    "error" { return 3 }
    default { return 1 }
  }
}

function New-Probe {
  param(
    [string]$Name,
    [string]$Status,
    [string]$Detail,
    [hashtable]$Extra = @{}
  )

  $probe = [ordered]@{
    name = $Name
    status = $Status
    severity = Get-SeverityRank $Status
    detail = $Detail
    checked_at = (Get-Date).ToString("o")
  }
  foreach ($key in $Extra.Keys) {
    $probe[$key] = $Extra[$key]
  }
  [pscustomobject]$probe
}

function Format-OptionalDateTime {
  param($Value)

  if ($null -eq $Value) {
    return $null
  }
  return $Value.ToString("o")
}

function Resolve-PythonExe {
  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCmd) {
    return $pythonCmd.Source
  }

  $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPython) {
    return $venvPython
  }

  throw "Unable to locate python.exe for JSON normalization fallback."
}

function Read-JsonReport {
  param([string]$Path)

  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  try {
    return $raw | ConvertFrom-Json
  }
  catch {
    # PowerShell's JSON parser can choke on valid UTF-8 title content from source audits.
    $pythonExe = Resolve-PythonExe
    $normalized = & $pythonExe -c "import json, pathlib, sys; obj=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')); print(json.dumps(obj, ensure_ascii=True))" $Path
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($normalized)) {
      throw
    }
    return $normalized | ConvertFrom-Json
  }
}

function Test-ListenPortProbe {
  param(
    [string]$Name,
    [int]$Port
  )

  try {
    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($connections.Count -gt 0) {
      return New-Probe $Name "ok" "listening on $Port" @{ port = $Port; listener_count = $connections.Count }
    }
    return New-Probe $Name "missing" "no listener on $Port" @{ port = $Port }
  }
  catch {
    return New-Probe $Name "error" $_.Exception.Message @{ port = $Port }
  }
}

function Test-HttpProbe {
  param(
    [string]$Name,
    [string]$Url,
    [string]$ExpectedStatus = ""
  )

  try {
    $body = Invoke-RestMethod -Uri $Url -TimeoutSec 5
    if ($ExpectedStatus -and $body.PSObject.Properties.Name -contains "status" -and [string]$body.status -ne $ExpectedStatus) {
      return New-Probe $Name "warn" "HTTP OK but status=$($body.status)" @{ url = $Url }
    }
    return New-Probe $Name "ok" "HTTP OK" @{ url = $Url }
  }
  catch {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        return New-Probe $Name "ok" "HTTP $($response.StatusCode)" @{ url = $Url }
      }
      return New-Probe $Name "warn" "HTTP $($response.StatusCode)" @{ url = $Url }
    }
    catch {
      return New-Probe $Name "missing" $_.Exception.Message @{ url = $Url }
    }
  }
}

function Get-NgrokTunnels {
  foreach ($inspectorPort in 4040, 4041) {
    try {
      $data = Invoke-RestMethod -Uri "http://127.0.0.1:$inspectorPort/api/tunnels" -TimeoutSec 3
      foreach ($tunnel in @($data.tunnels)) {
        [pscustomobject]@{
          inspector_port = $inspectorPort
          public_url = [string]$tunnel.public_url
          addr = [string]$tunnel.config.addr
        }
      }
    }
    catch {
    }
  }
}

function Test-NgrokBindingProbe {
  param(
    [string]$Name,
    [string]$PublicUrl,
    [string]$ExpectedAddr
  )

  $tunnels = @(Get-NgrokTunnels)
  $matches = @($tunnels | Where-Object { $_.public_url -eq $PublicUrl })
  if ($matches.Count -eq 0) {
    return New-Probe $Name "missing" "ngrok tunnel not found for $PublicUrl" @{ public_url = $PublicUrl; expected_addr = $ExpectedAddr }
  }

  $correct = @($matches | Where-Object { $_.addr -eq $ExpectedAddr })
  if ($correct.Count -gt 0) {
    return New-Probe $Name "ok" "ngrok bound to $ExpectedAddr" @{ public_url = $PublicUrl; expected_addr = $ExpectedAddr }
  }

  $actual = ($matches | ForEach-Object { $_.addr }) -join ","
  return New-Probe $Name "error" "ngrok URL is bound to $actual, expected $ExpectedAddr" @{ public_url = $PublicUrl; expected_addr = $ExpectedAddr; actual_addr = $actual }
}

function Read-DataSourceHealthProbes {
  $script = Join-Path $PSScriptRoot "run_data_source_health.ps1"
  if (-not (Test-Path -LiteralPath $script)) {
    return @(New-Probe "data_source_health" "error" "script not found: $script")
  }

  try {
    $raw = & $script -EnvFile $EnvFile -Json
    if ($LASTEXITCODE -ne 0) {
      return @(New-Probe "data_source_health" "error" "health script exit=$LASTEXITCODE")
    }

    $report = $raw | ConvertFrom-Json
    $bad = @($report.probes | Where-Object { (Get-SeverityRank ([string]$_.status)) -ge 1 })
    $items = @(
      New-Probe "data_source_health" ([string]$report.overall_status) "failing_probes=$($bad.Count)" @{
        generated_at_utc = [string]$report.generated_at_utc
      }
    )
    foreach ($probe in $bad) {
      $items += New-Probe "data_source_health/$($probe.name)" ([string]$probe.status) ([string]$probe.detail)
    }
    return $items
  }
  catch {
    return @(New-Probe "data_source_health" "error" $_.Exception.Message)
  }
}

function Read-NewsSourceAccuracyProbes {
  $reportPath = Join-Path $ProjectRoot "runtime\news-source-accuracy\latest.json"
  if (-not (Test-Path -LiteralPath $reportPath)) {
    return @(New-Probe "news_source_accuracy" "warn" "latest report is missing" @{ report = $reportPath })
  }

  try {
    $reportFile = Get-Item -LiteralPath $reportPath
    $ageMinutes = [int][Math]::Round(((Get-Date) - $reportFile.LastWriteTime).TotalMinutes)
    $report = Read-JsonReport -Path $reportPath
    $status = [string]$report.overall_status
    $items = @()
    if ($ageMinutes -gt $SourceAccuracyMaxAgeMinutes) {
      $items += New-Probe "news_source_accuracy_age" "warn" "latest report age ${ageMinutes}m exceeds ${SourceAccuracyMaxAgeMinutes}m" @{
        report = $reportPath
        age_minutes = $ageMinutes
      }
    }

    $bad = @($report.probes | Where-Object { (Get-SeverityRank ([string]$_.status)) -ge 1 })
    $items += New-Probe "news_source_accuracy" $status "failing_probes=$($bad.Count)" @{
      report = $reportPath
      generated_at_utc = [string]$report.generated_at_utc
      age_minutes = $ageMinutes
    }
    foreach ($probe in $bad) {
      $items += New-Probe "news_source_accuracy/$($probe.name)" ([string]$probe.status) ([string]$probe.detail) @{
        coverage_rate = $probe.coverage_rate
        missing_count = $probe.missing_count
      }
    }
    return $items
  }
  catch {
    return @(New-Probe "news_source_accuracy" "error" $_.Exception.Message @{ report = $reportPath })
  }
}

function Read-ScheduledTaskProbes {
  $tasks = @(Get-ScheduledTask -TaskName "NewsCollector-*" -ErrorAction SilentlyContinue)
  if ($tasks.Count -eq 0) {
    return @(New-Probe "scheduled_tasks" "warn" "no NewsCollector scheduled tasks found")
  }

  $ignoredResults = @(0, 267009, 267011, 267014)
  $items = @()
  foreach ($task in $tasks) {
    if ([string]$task.State -eq "Disabled") {
      continue
    }

    try {
      $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath
      $result = [int]$info.LastTaskResult
      if ($ignoredResults -notcontains $result) {
        $items += New-Probe "scheduled_task/$($task.TaskName)" "warn" "last_result=$result last_run=$($info.LastRunTime)" @{
          task_name = $task.TaskName
          state = [string]$task.State
          last_task_result = $result
          last_run_time = Format-OptionalDateTime $info.LastRunTime
          next_run_time = Format-OptionalDateTime $info.NextRunTime
        }
      }
    }
    catch {
      $items += New-Probe "scheduled_task/$($task.TaskName)" "error" $_.Exception.Message @{ task_name = $task.TaskName }
    }
  }

  if ($items.Count -eq 0) {
    return @(New-Probe "scheduled_tasks" "ok" "enabled NewsCollector task results are clean" @{ task_count = $tasks.Count })
  }
  return $items
}

function New-Fingerprint {
  param([array]$FailingProbes)

  $text = ($FailingProbes |
    Sort-Object name |
    Select-Object name, status, detail |
    ConvertTo-Json -Depth 6 -Compress)
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
  $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
  -join ($hash | ForEach-Object { $_.ToString("x2") })
}

function Read-State {
  if (-not (Test-Path -LiteralPath $stateFile)) {
    return [pscustomobject]@{}
  }
  try {
    return Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
  }
  catch {
    return [pscustomobject]@{}
  }
}

function Write-State {
  param([hashtable]$State)
  $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $stateFile -Encoding UTF8
}

function Resolve-CodexExecutable {
  $cmd = Get-Command codex.cmd -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cmd) {
    return $cmd.Source
  }

  $exe = Get-Command codex.exe, codex -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandType -eq "Application" } |
    Select-Object -First 1
  if ($exe) {
    return $exe.Source
  }
  return ""
}

function New-RepairPrompt {
  param(
    [string]$IncidentId,
    [array]$FailingProbes,
    [string]$IncidentJson
  )

  $probeLines = ($FailingProbes | ForEach-Object {
    "- $($_.name): $($_.status) - $($_.detail)"
  }) -join "`n"

  @"
# Auto Repair Request

Incident: $IncidentId
Generated at: $(Get-Date -Format o)
Report JSON: $IncidentJson

You are a Codex repair agent for the local news/finance workspace.

Read the relevant AGENTS.md, README, runbooks, and skills before changing files.
Diagnose the root cause from the incident JSON and local service state, then apply the smallest safe repair that actually works.

Hard boundaries:
- Treat the incident repo as the default working directory. If you need git or file commands, run them from that repo root or use an explicit repo path.
- On Windows, quote or use `-LiteralPath` for any path that may contain spaces, especially under `C:\Users\Zack Ou\...`.
- Do not push to any remote.
- Do not start, stop, or modify order-dispatcher / broker order flows.
- Do not touch liuli-social-ai-service, Ollama, or llama-server unless the user explicitly named them in the current incident.
- Do not send LINE pushes, external messages, production deploys, destructive data repairs, or schema migrations.
- If code changes are required, stage only related files/hunks, run the narrowest meaningful verification, and create a local commit.
- If the issue is an external outage or needs secrets/user action, write that clearly and stop after collecting evidence.

Warn-or-higher probes:
$probeLines
"@
}

function Write-Incident {
  param(
    [string]$Fingerprint,
    [string]$OverallStatus,
    [array]$Probes,
    [array]$FailingProbes
  )

  $incidentId = "service-auto-repair-{0}" -f (Get-Date).ToString("yyyyMMdd-HHmmss")
  $jsonPath = Join-Path $incidentDir "$incidentId.json"
  $promptPath = Join-Path $incidentDir "$incidentId.prompt.md"

  $incident = [ordered]@{
    incident_id = $incidentId
    generated_at = (Get-Date).ToString("o")
    project_root = $ProjectRoot
    workspace_root = $WorkspaceRoot
    overall_status = $OverallStatus
    fingerprint = $Fingerprint
    launch_agent_requested = [bool]$LaunchAgent
    dry_run = [bool]$DryRun
    cooldown_minutes = $CooldownMinutes
    probes = $Probes
    failing_probes = $FailingProbes
    repair_agent = [ordered]@{
      launched = $false
      pid = $null
      detail = ""
      stdout_log = ""
      stderr_log = ""
      last_message = ""
    }
  }
  $incident | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

  $prompt = New-RepairPrompt -IncidentId $incidentId -FailingProbes $FailingProbes -IncidentJson $jsonPath
  $prompt | Set-Content -LiteralPath $promptPath -Encoding UTF8

  [pscustomobject]@{
    incident_id = $incidentId
    json_path = $jsonPath
    prompt_path = $promptPath
    incident = $incident
  }
}

function Start-RepairAgent {
  param(
    [string]$IncidentId,
    [string]$PromptPath
  )

  if ($DryRun) {
    return [pscustomobject]@{ launched = $false; pid = $null; detail = "dry_run"; stdout_log = ""; stderr_log = ""; last_message = "" }
  }
  if (-not $LaunchAgent) {
    return [pscustomobject]@{ launched = $false; pid = $null; detail = "LaunchAgent was not set"; stdout_log = ""; stderr_log = ""; last_message = "" }
  }

  $codex = Resolve-CodexExecutable
  if ([string]::IsNullOrWhiteSpace($codex)) {
    return [pscustomobject]@{ launched = $false; pid = $null; detail = "codex executable not found"; stdout_log = ""; stderr_log = ""; last_message = "" }
  }

  $outLog = Join-Path $incidentDir "$IncidentId.codex.jsonl"
  $errLog = Join-Path $incidentDir "$IncidentId.codex.err.log"
  $lastMessage = Join-Path $incidentDir "$IncidentId.codex.final.txt"
  $agentCwd = $ProjectRoot
  $arguments = @(
    "exec",
    "-C", $agentCwd,
    "--add-dir", $ProjectRoot,
    "--sandbox", "danger-full-access",
    "--dangerously-bypass-approvals-and-sandbox",
    "--json",
    "-o", $lastMessage,
    "-"
  )

  try {
    $process = Start-Process `
      -FilePath $codex `
      -ArgumentList $arguments `
      -WorkingDirectory $agentCwd `
      -WindowStyle Hidden `
      -RedirectStandardInput $PromptPath `
      -RedirectStandardOutput $outLog `
      -RedirectStandardError $errLog `
      -PassThru
    return [pscustomobject]@{
      launched = $true
      pid = $process.Id
      detail = "codex exec started"
      stdout_log = $outLog
      stderr_log = $errLog
      last_message = $lastMessage
    }
  }
  catch {
    return [pscustomobject]@{ launched = $false; pid = $null; detail = $_.Exception.Message; stdout_log = $outLog; stderr_log = $errLog; last_message = $lastMessage }
  }
}

$probes = @()
$probes += Test-HttpProbe "news_display_frontend" "http://127.0.0.1:3000/health" "ok"
$probes += Test-HttpProbe "news_platform_api" "http://127.0.0.1:8081/health" "ok"
$probes += Test-HttpProbe "line_relay_service" "http://127.0.0.1:8080/health" "ok"
$probes += Test-HttpProbe "stock_monitor_service" "http://127.0.0.1:8089/health" "ok"
$probes += Test-HttpProbe "codex_observer" "http://127.0.0.1:8765/health" "ok"
$probes += Test-HttpProbe "event_relay" "http://127.0.0.1:18090/healthz"
$probes += Test-ListenPortProbe "redis" 6379
$probes += Test-NgrokBindingProbe "frontend_ngrok" "https://011b-220-141-219-53.ngrok-free.app" "http://127.0.0.1:3000"
$probes += Read-ScheduledTaskProbes
$probes += Read-DataSourceHealthProbes
$probes += Read-NewsSourceAccuracyProbes

$failing = @($probes | Where-Object { [int]$_.severity -ge 1 })
$maxRank = 0
foreach ($probe in $probes) {
  if ([int]$probe.severity -gt $maxRank) {
    $maxRank = [int]$probe.severity
  }
}
$hasMissing = @($failing | Where-Object { [string]$_.status -eq "missing" }).Count -gt 0
$hasStale = @($failing | Where-Object { [string]$_.status -eq "stale" }).Count -gt 0
$hasWarn = @($failing | Where-Object { [string]$_.status -eq "warn" }).Count -gt 0

$overallStatus = if ($maxRank -ge 3) {
  "error"
}
elseif ($hasMissing) {
  "missing"
}
elseif ($hasStale) {
  "stale"
}
elseif ($hasWarn) {
  "warn"
}
else {
  "ok"
}

$action = "none"
$incidentRef = $null
$agentResult = $null
$fingerprint = if ($failing.Count -gt 0) { New-Fingerprint $failing } else { "" }
$state = Read-State

if ($failing.Count -eq 0) {
  Write-AutoRepairLog "services_ok"
  Write-State @{
    updated_at = (Get-Date).ToString("o")
    last_status = "ok"
    last_fingerprint = if ($state.PSObject.Properties.Name -contains "last_fingerprint") { $state.last_fingerprint } else { "" }
    last_triggered_at = if ($state.PSObject.Properties.Name -contains "last_triggered_at") { $state.last_triggered_at } else { "" }
    last_incident_id = if ($state.PSObject.Properties.Name -contains "last_incident_id") { $state.last_incident_id } else { "" }
  }
}
else {
  $cooldownActive = $false
  $lastActionWasDryRun = ($state.PSObject.Properties.Name -contains "last_action") -and [string]$state.last_action -eq "dry_run"
  if ((-not $lastActionWasDryRun) -and ($state.PSObject.Properties.Name -contains "last_fingerprint") -and $state.last_fingerprint -eq $fingerprint -and ($state.PSObject.Properties.Name -contains "last_triggered_at")) {
    try {
      $lastTriggered = [datetime]$state.last_triggered_at
      $cooldownActive = ((Get-Date) - $lastTriggered).TotalMinutes -lt $CooldownMinutes
    }
    catch {
      $cooldownActive = $false
    }
  }

  if ($cooldownActive) {
    $action = "suppressed_by_cooldown"
    Write-AutoRepairLog "warn_detected cooldown_active fingerprint=$fingerprint failing=$($failing.Count)"
  }
  else {
    $incidentRef = Write-Incident -Fingerprint $fingerprint -OverallStatus $overallStatus -Probes $probes -FailingProbes $failing
    $agentResult = Start-RepairAgent -IncidentId $incidentRef.incident_id -PromptPath $incidentRef.prompt_path
    $action = if ($agentResult.launched) { "agent_launched" } elseif ($DryRun) { "dry_run" } else { "incident_written" }

    $incidentRef.incident.repair_agent.launched = [bool]$agentResult.launched
    $incidentRef.incident.repair_agent.pid = $agentResult.pid
    $incidentRef.incident.repair_agent.detail = [string]$agentResult.detail
    $incidentRef.incident.repair_agent.stdout_log = [string]$agentResult.stdout_log
    $incidentRef.incident.repair_agent.stderr_log = [string]$agentResult.stderr_log
    $incidentRef.incident.repair_agent.last_message = [string]$agentResult.last_message
    $incidentRef.incident | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $incidentRef.json_path -Encoding UTF8

    Send-CodexObserverEvent `
      -EventType "service_auto_repair_triggered" `
      -Job "service_auto_repair_watch" `
      -Category "service" `
      -Status $action `
      -Skill "workspace-service-shutdown" `
      -Metadata @{
        overall_status = $overallStatus
        failing_count = $failing.Count
        incident_id = $incidentRef.incident_id
        fingerprint = $fingerprint
        agent_launched = [bool]$agentResult.launched
      }

    if (-not $DryRun) {
      Write-State @{
        updated_at = (Get-Date).ToString("o")
        last_status = $overallStatus
        last_fingerprint = $fingerprint
        last_triggered_at = (Get-Date).ToString("o")
        last_incident_id = $incidentRef.incident_id
        last_agent_pid = $agentResult.pid
        last_action = $action
      }
    }
    Write-AutoRepairLog "warn_detected action=$action incident=$($incidentRef.incident_id) failing=$($failing.Count)"
  }
}

$status = [ordered]@{
  updated_at = (Get-Date).ToString("o")
  overall_status = $overallStatus
  failing_count = $failing.Count
  action = $action
  fingerprint = $fingerprint
  cooldown_minutes = $CooldownMinutes
  launch_agent = [bool]$LaunchAgent
  dry_run = [bool]$DryRun
  incident_id = if ($incidentRef) { $incidentRef.incident_id } else { "" }
  agent_launched = if ($agentResult) { [bool]$agentResult.launched } else { $false }
  agent_pid = if ($agentResult) { $agentResult.pid } else { $null }
  probes = $probes
  failing_probes = $failing
}
$status | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $statusFile -Encoding UTF8

if ($Json) {
  $status | ConvertTo-Json -Depth 16
}
else {
  Write-AutoRepairLog "status=$overallStatus failing=$($failing.Count) action=$action status_file=$statusFile"
}

if ($FailOnWarn -and $failing.Count -gt 0) {
  exit 1
}
exit 0
