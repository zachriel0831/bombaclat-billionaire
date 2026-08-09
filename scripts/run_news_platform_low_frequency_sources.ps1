# Collect low-frequency public category pages for extra Taiwan news sources.
param(
  [string]$EnvFile = ".env",
  [string]$SourceIds = "tvbs,udn,setn",
  [string]$Categories = "society,politics",
  [int]$Limit = 20,
  [int]$AuthorLimit = 30,
  [double]$AuthorSleepSeconds = 1.0,
  [int]$AuthorTimeoutSeconds = 15,
  [switch]$SkipAuthorBackfill,
  [switch]$SkipKeywordsAndTopics,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
$env:NEWSPF_LIMIT_PER_FEED = [string]$Limit
. (Join-Path $PSScriptRoot "codex_observer.ps1")

$sourceArray = $SourceIds.Split(",") |
  ForEach-Object { $_.Trim().ToLowerInvariant() } |
  Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

if (-not $sourceArray) {
  throw "SourceIds must contain at least one source id."
}

Write-Host "Collecting low-frequency news-platform sources..." -ForegroundColor Cyan
Write-Host "Sources: $($sourceArray -join ',')"
Write-Host "Categories: $Categories"

$exitCode = Invoke-CodexObservedCommand `
  -Job "news_platform_low_frequency_sources" `
  -Category "crawler" `
  -Skill "news-ingestion-skill" `
  -Metadata @{
    source_ids = ($sourceArray -join ",")
    categories = $Categories
    limit = $Limit
    author_limit = $AuthorLimit
    log_level = $LogLevel
  } `
  -Command {
    & python -m news_platform.main `
      --env-file $EnvFile `
      --once `
      --categories $Categories `
      --source-ids ($sourceArray -join ",") `
      --log-level $LogLevel
    if ($LASTEXITCODE -ne 0) {
      throw "low-frequency crawl failed with exit code $LASTEXITCODE"
    }

    if (-not $SkipAuthorBackfill) {
      & python .\scripts\backfill_news_author_detail_pages.py `
        --env-file $EnvFile `
        --limit $AuthorLimit `
        --sources @sourceArray `
        --sleep-seconds $AuthorSleepSeconds `
        --timeout $AuthorTimeoutSeconds `
        --quiet
      if ($LASTEXITCODE -ne 0) {
        throw "author backfill failed with exit code $LASTEXITCODE"
      }
    }

    if (-not $SkipKeywordsAndTopics) {
      & python -m news_platform.main `
        --env-file $EnvFile `
        --extract-keywords `
        --classify-topics `
        --log-level $LogLevel
      if ($LASTEXITCODE -ne 0) {
        throw "keyword/topic enrichment failed with exit code $LASTEXITCODE"
      }
    }
  }

exit $exitCode
