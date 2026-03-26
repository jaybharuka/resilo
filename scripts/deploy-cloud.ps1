# ============================================================
# deploy-cloud.ps1 — Full Cloud Run + Firebase deployment
# Run from repo root: .\scripts\deploy-cloud.ps1
# ============================================================
# Prerequisites:
#   1. gcloud auth login
#   2. gcloud auth configure-docker REGION-docker.pkg.dev
#   3. Set the environment variables listed below before running
# ============================================================

$ErrorActionPreference = "Stop"

# ─── CONFIG — all values pulled from environment ─────────────
$DATABASE_URL  = $env:DATABASE_URL
$JWT_SECRET    = $env:JWT_SECRET_KEY
$PROJECT_ID    = $env:GCLOUD_PROJECT_ID
$REGION        = $env:GCLOUD_REGION
$DASHBOARD_URL = $env:DASHBOARD_URL
$GCLOUD        = if ($env:GCLOUD_CLI_PATH) { $env:GCLOUD_CLI_PATH } else { "gcloud" }
$REPO_ROOT     = Split-Path -Parent $PSScriptRoot
# ────────────────────────────────────────────────────────────

if (-not $DATABASE_URL) {
    Write-Host "ERROR: DATABASE_URL is not set." -ForegroundColor Red
    Write-Host "       Export DATABASE_URL (e.g. from Neon/Supabase) before running." -ForegroundColor Yellow
    exit 1
}

if (-not $JWT_SECRET) {
    Write-Host "ERROR: JWT_SECRET_KEY is not set." -ForegroundColor Red
    Write-Host "       Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"" -ForegroundColor Yellow
    exit 1
}

if (-not $PROJECT_ID) {
    Write-Host "ERROR: GCLOUD_PROJECT_ID is not set." -ForegroundColor Red
    exit 1
}

if (-not $REGION) { $REGION = "us-central1" }
if (-not $DASHBOARD_URL) { $DASHBOARD_URL = "https://your-dashboard.example.com" }

Write-Host "=== Resilo AIOps — Cloud Run Deployment ===" -ForegroundColor Cyan
Write-Host "Project : $PROJECT_ID"
Write-Host "Region  : $REGION"
Write-Host "Frontend: $DASHBOARD_URL"
Write-Host ""

# ─── 1. Enable required APIs ────────────────────────────────
Write-Host "[1/5] Enabling GCP APIs..." -ForegroundColor Yellow
& $GCLOUD services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    containerregistry.googleapis.com `
    --project $PROJECT_ID

# ─── 2. Build React for production ──────────────────────────
Write-Host "[2/5] Building React dashboard..." -ForegroundColor Yellow
Push-Location "$REPO_ROOT\dashboard"
npm run build
Pop-Location

# ─── 3. Deploy auth-api ──────────────────────────────────────
Write-Host "[3/5] Deploying auth-api to Cloud Run..." -ForegroundColor Yellow
& $GCLOUD run deploy auth-api `
    --source $REPO_ROOT `
    --dockerfile Dockerfile.auth `
    --region $REGION `
    --project $PROJECT_ID `
    --allow-unauthenticated `
    --port 5001 `
    --memory 512Mi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 3 `
    --set-env-vars "DATABASE_URL=$DATABASE_URL,JWT_SECRET_KEY=$JWT_SECRET,FRONTEND_URL=$DASHBOARD_URL,ALLOWED_ORIGINS=$DASHBOARD_URL"

$AUTH_URL = (& $GCLOUD run services describe auth-api --region $REGION --project $PROJECT_ID --format "value(status.url)" 2>&1)
Write-Host "auth-api deployed: $AUTH_URL" -ForegroundColor Green

# ─── 4. Deploy core-api ──────────────────────────────────────
Write-Host "[4/5] Deploying core-api to Cloud Run..." -ForegroundColor Yellow
& $GCLOUD run deploy core-api `
    --source $REPO_ROOT `
    --dockerfile Dockerfile.core `
    --region $REGION `
    --project $PROJECT_ID `
    --allow-unauthenticated `
    --port 8000 `
    --memory 512Mi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 3 `
    --set-env-vars "DATABASE_URL=$DATABASE_URL,JWT_SECRET_KEY=$JWT_SECRET,DASHBOARD_URL=$DASHBOARD_URL,ALLOWED_ORIGINS=$DASHBOARD_URL,ANOMALY_AUTONOMOUS=org,ANOMALY_POLL_INTERVAL=30"

$CORE_URL = (& $GCLOUD run services describe core-api --region $REGION --project $PROJECT_ID --format "value(status.url)" 2>&1)
Write-Host "core-api deployed: $CORE_URL" -ForegroundColor Green

# ─── 5. Deploy Firebase (functions + hosting) ────────────────
Write-Host "[5/5] Deploying Firebase functions + hosting..." -ForegroundColor Yellow
Push-Location $REPO_ROOT

if (-not $CORE_URL) {
    Write-Host "WARNING: core-api URL not detected; skipping Firebase env injection." -ForegroundColor Yellow
} else {
    (Get-Content "functions\index.js") `
        -replace "https://core-api-REPLACE_WITH_YOUR_CLOUD_RUN_HASH-uc.a.run.app", $CORE_URL `
        | Set-Content "functions\index.js"
}

firebase deploy --only hosting,functions

Pop-Location

Write-Host ""
Write-Host "=== DEPLOYMENT COMPLETE ===" -ForegroundColor Green
Write-Host ""
Write-Host "Dashboard    : $DASHBOARD_URL"
Write-Host "Auth API     : $AUTH_URL"
Write-Host "Core API     : $CORE_URL"
Write-Host ""
Write-Host "Test the PS1 route:" -ForegroundColor Cyan
Write-Host "  irm '$DASHBOARD_URL/connect.ps1?token=test' | Write-Host"
