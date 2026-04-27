📘 Resilo — Phase 4 README
Enterprise Readiness · SOC2 · Multi-Tenancy · Launch (Weeks 11–16)
🚨 Purpose of Phase 4

Phase 4 transforms Resilo from:

“working AIOps product” → enterprise-grade SaaS platform

This phase is not feature-heavy, it is:

Compliance
Isolation
Deployment reliability
Monetisation
Go-to-market
🧱 Tech Stack Context (DO NOT CHANGE)
Backend: FastAPI (async)
DB: PostgreSQL + TimescaleDB
Auth: JWT + bcrypt
Infra: Docker → Kubernetes
AI: Gemini API
Frontend: React
⚠️ Non-Negotiable Constraints
Multi-tenancy must be enforced at DB level (RLS)
No feature bypass without plan validation
All enterprise features must be API-enforced (not frontend-only)
Zero downtime deploys required
Every action must be auditable
🧩 Phase 4 Architecture Additions
1. 🔐 Multi-Tenancy with Row-Level Security (RLS)
Goal

Hard isolation between organisations.

DB Changes
Add org_id everywhere:
ALTER TABLE users ADD COLUMN org_id UUID NOT NULL;
ALTER TABLE metrics ADD COLUMN org_id UUID NOT NULL;
ALTER TABLE alerts ADD COLUMN org_id UUID NOT NULL;
ALTER TABLE remediation_jobs ADD COLUMN org_id UUID NOT NULL;
Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE remediation_jobs ENABLE ROW LEVEL SECURITY;
Policy
CREATE POLICY org_isolation_policy
ON metrics
USING (org_id = current_setting('app.current_org')::uuid);
Backend Enforcement (CRITICAL)

Every request MUST set:

async def set_org_context(conn, org_id: str):
    await conn.execute(f"SET app.current_org = '{org_id}'")

Inject via FastAPI dependency:

def get_db_with_org(user=Depends(get_current_user)):
    conn = get_db()
    set_org_context(conn, user.org_id)
    return conn
✅ Done Criteria
Cross-tenant query returns 0 rows
Manual SQL bypass attempt fails
Integration test exists:
pytest tests/test_rls_isolation.py
2. 🏢 SSO + SAML Integration
Goal

Enterprise authentication (Okta, Azure AD)

Library

Use:

python3-saml OR fastapi-saml
Endpoints
GET  /auth/sso/login
POST /auth/sso/acs
GET  /auth/sso/metadata
Flow
User clicks “Login with SSO”
Redirect → IdP (Okta/Azure)
IdP → /acs
Extract:
email
name
org_id (mapped via domain)
User Provisioning
user = get_user_by_email(email)
if not user:
    create_user(
        email=email,
        org_id=resolve_org(email),
        sso_only=True
    )
JWT Issuance

SSO → still returns internal JWT:

{
  "access_token": "...",
  "org_id": "...",
  "role": "admin"
}
✅ Done Criteria
Okta test login works
Azure AD login works
No password required for SSO users
JWT issued after SAML success
3. 📊 Pricing Tier Enforcement (CRITICAL)
Plans
Plan	Limits
Starter	10 services
Growth	100 services
Enterprise	Unlimited + SSO
DB Schema
ALTER TABLE organisations ADD COLUMN plan TEXT DEFAULT 'starter';
ALTER TABLE organisations ADD COLUMN service_limit INT;
Middleware Enforcement
def enforce_plan_limits(org):
    if org.services_count >= org.service_limit:
        raise HTTPException(403, "Plan limit reached")
Feature Gating
if org.plan != "enterprise":
    raise HTTPException(403, "SSO requires Enterprise plan")
NEVER DO THIS

❌ Frontend-only gating
❌ Hidden buttons instead of backend enforcement

✅ Done Criteria
API blocks over-limit usage
Downgrade immediately restricts access
Tests:
pytest tests/test_pricing_limits.py
4. 🚀 Blue/Green Deployment Strategy
Goal

Zero downtime deploy + instant rollback

Strategy

Two environments:

blue (current live)
green (new version)
Flow
Deploy → green
Run health checks
Switch traffic
Keep blue as fallback
Kubernetes Implementation
Two deployments:
resilo-blue
resilo-green
Service selector switch:
selector:
  app: resilo-green
Rollback
kubectl patch service resilo -p '{"spec":{"selector":{"app":"resilo-blue"}}}'
✅ Done Criteria
Rollback < 60 seconds
No dropped connections
WebSocket reconnect works
5. 🧪 Health Probes (Kubernetes)
Endpoints
GET /health/live
GET /health/ready
Logic

Liveness

App running

Readiness

DB reachable
Redis (if used)
Queue healthy
Example
@app.get("/health/ready")
async def ready():
    await db.execute("SELECT 1")
    return {"status": "ready"}
Helm Config
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
6. 📈 Auto Scaling (HPA)
Metrics
CPU > 70%
Queue length > 1000
Config
minReplicas: 2
maxReplicas: 10
targetCPUUtilizationPercentage: 70
Advanced (IMPORTANT)

Add custom metric:

Kafka / queue depth
WebSocket connections
7. 📁 SOC2 Type I Evidence System
Folder Structure
/compliance/
  /soc2/
    access_control.md
    encryption.md
    logging.md
    incident_response.md
    key_rotation.md
Required Evidence
Control	Proof
Access Control	RBAC logs
Encryption	AES/Fernet usage
Logging	Audit trail
Secrets	Rotation logs
Example Audit Log
{
  "event": "user_login",
  "user_id": "...",
  "org_id": "...",
  "ip": "...",
  "timestamp": "..."
}
MUST HAVE
Immutable logs
Timestamped
Org-scoped
8. 📚 Public Documentation Site
Tool
Docusaurus
Required Sections
Installation
Agent setup
API reference
Playbooks
Architecture
API Docs

Auto-generate from FastAPI:

/docs
/redoc
9. 🌍 Community Edition Launch
Versioning
git tag v1.0.0
README MUST INCLUDE
Problem statement
Architecture diagram
Demo GIF
Quickstart
Launch Targets
GitHub
Product Hunt
Hacker News
🧪 Testing Requirements
New Test Suites
tests/
  test_rls_isolation.py
  test_sso_flow.py
  test_pricing_limits.py
  test_deployment_health.py
Coverage Target
pytest --cov=app --fail-under=80
🧠 Copilot Execution Strategy
When implementing ANY feature:
Step 1 — Architect
Understand DB impact
Identify API changes
Define failure modes
Step 2 — Developer
Modify exact files only
No unnecessary refactors
Follow existing patterns
Step 3 — Reviewer
Run:
pytest -v
alembic upgrade head
Validate:
No cross-tenant leak
No downtime deploy issues
✅ Final Definition of DONE (Phase 4)

You are DONE when:

RLS blocks all cross-org access
SSO login works with Okta
Pricing tiers enforced at API level
Blue/green deploy rollback < 5 min
Kubernetes auto-scaling works
SOC2 evidence folder exists (20+ controls)
Public docs live
v1.0.0 launched
⚠️ Final Warning

If ANY of these are missing:

RLS
SSO
Pricing enforcement

👉 The product is NOT enterprise-ready
## Current Pass Summary

This pass focused on stabilizing the lint gate so Claude can review a deterministic, low-risk change set.

### Fixes Completed

1. CI lint was scoped to the api/ package.
   - The workflow now runs the same commands locally and in CI on the same target.
   - Final command order:
     - black --check api --line-length=100
     - isort --check-only api
     - flake8 api --max-line-length=100

2. Lint configuration was simplified.
   - .flake8 now keeps only the essential baseline:
     - max-line-length = 100
     - extend-exclude = .venv,node_modules,migrations,alembic
   - This removes the large ignore surface that previously hid too much of the codebase.

3. API bridge files were cleaned up so scoped lint passes.
   - The following files were normalized and formatted:
     - api/agents.py
     - api/alerts.py
     - api/auth.py
     - api/health.py
     - api/metrics.py
     - api/stream.py
     - api/_legacy_bridge.py
     - api/chat.py
     - api/websocket.py

4. Local verification passed.
   - The exact scoped lint trio passed locally on the current branch.
   - This confirms the workflow and local validation are aligned.

### Why This Matters

- It gives the team a stable lint gate without forcing a repo-wide cleanup.
- It keeps the change set narrow enough for review and safe to merge.
- It separates completed infrastructure work from the broader Phase 4 roadmap.

### What Still Belongs To The Broader Phase 4 Roadmap

- RLS enforcement
- SSO / SAML integration
- Pricing and plan limits
- Blue/green deployments
- Kubernetes health probes and autoscaling
- SOC2 evidence collection
- Public docs site
- v1.0.0 launch work
