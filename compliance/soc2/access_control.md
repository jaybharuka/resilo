# SOC2 Type I — Access Control Evidence

**Control Domain:** Logical and Physical Access Controls
**Last Reviewed:** 2026-04-07
**Owner:** Engineering / Security Team
**Status:** Implemented

---

## CC6.1 — Logical Access Security Measures

**Requirement:** The entity implements logical access security software, infrastructure, and architectures over protected information assets.

**Implementation:**
- JWT-based authentication enforced on all protected API routes via `OrgContextMiddleware` (`app/api/middleware/org_context.py`)
- Tokens signed with HS256 using `JWT_SECRET_KEY` stored in environment variable (never hardcoded)
- Token expiry enforced: access tokens 15 minutes, refresh tokens 7 days
- API key authentication available for service-to-service calls (`app/core/apikey.py`)

**Evidence Files:**
- `app/api/middleware/org_context.py` — middleware source
- `app/core/apikey.py` — API key enforcement
- `alembic/versions/001_initial_postgresql_schema.py` — `user_sessions` table with expiry

---

## CC6.2 — User Registration and Deprovisioning

**Requirement:** New internal and external users are registered and deprovisioned using defined procedures.

**Implementation:**
- User registration requires org-scoped invite token (`/auth/invite`, `/auth/redeem-invite`)
- SSO users provisioned automatically on first login via `SSOHandler.provision_or_link_user()`
- Deprovisioned users have `is_active = false`; all protected endpoints reject inactive accounts
- Org admins can disable users via `PATCH /users/{id}` (requires `admin` role)

**Evidence Files:**
- `app/core/sso_handler.py:146` — `provision_or_link_user()`
- `app/core/database.py` — `User.is_active` column
- `api/auth.py` — invite and deprovisioning endpoints

---

## CC6.3 — Role-Based Access Control (RBAC)

**Requirement:** Role-based access control is implemented. Access is restricted based on job responsibility.

**Roles Defined:**

| Role | Permissions |
|---|---|
| `admin` | Full access within org — user management, settings, all data |
| `manager` | Read/write alerts, remediations, analytics; cannot manage users |
| `employee` | Read-only access to dashboards and alerts |
| `service` | Machine-to-machine via API key; scoped to specific resources |

**Implementation:**
- Role stored in JWT claim `role` and enforced per-endpoint via `app/auth/rbac.py`
- RBAC dependency injected via FastAPI `Depends(require_role(...))`
- Cross-role escalation blocked at middleware level

**Evidence Files:**
- `app/auth/rbac.py` — role enforcement
- `app/auth/authz.py` — authorization helpers

---

## CC6.4 — Network Access Controls

**Requirement:** Network access is restricted to authorised users.

**Implementation:**
- All external traffic terminates at Nginx reverse proxy (configured in `helm/aiops-bot/`)
- Internal service-to-service communication within Kubernetes namespace only
- No direct DB port exposed outside cluster
- TLS enforced on all ingress via Kubernetes ingress annotations

**Evidence Files:**
- `helm/aiops-bot/templates/namespace.yaml`
- `helm/aiops-bot/templates/api-gateway-service.yaml` (ClusterIP — no external exposure)

---

## CC6.5 — Authentication Credential Management

**Requirement:** Authenticating credentials are protected.

**Implementation:**
- Passwords hashed with bcrypt (cost factor 12)
- `ENCRYPTION_KEY` used for field-level encryption of sensitive columns (Fernet/AES-128)
- Secrets managed via environment variables; never committed to source control
- `.env.example` documents required variables without values
- `scripts/rotate_secrets.py` automates secret rotation with backup

**Evidence Files:**
- `app/core/encryption.py` — Fernet field encryption
- `scripts/rotate_secrets.py` — rotation automation
- `.env.example` — no secrets in source control

---

## CC6.6 — Logical Access Restrictions

**Requirement:** Logical access restrictions to production systems.

**Implementation:**
- Row-Level Security (RLS) enforced at PostgreSQL level — cross-tenant data access impossible even with valid token from different org
- Every DB session sets `app.current_org` via `get_db()` in `app/core/database.py:548`
- Migration 004 enables RLS on: `users`, `metrics`, `alerts`, `remediation_jobs`

**Evidence Files:**
- `alembic/versions/004_phase4_enterprise_foundation.py:151-158` — RLS policies
- `app/core/database.py:540-555` — org context injection
- `tests/test_rls_isolation.py` — automated isolation tests

---

## CC6.7 — Privileged Access Management

**Requirement:** Privileged access is restricted and monitored.

**Implementation:**
- Admin role required for all destructive operations
- Admin actions emit audit log entries with `action_type = "admin_action"`
- `create_admin.py` script requires direct server access (not API-accessible)
- No shared credentials; each admin has individual account

**Evidence Files:**
- `app/core/audit.py` — audit logging
- `create_admin.py` — admin bootstrap (server-only)

---

## CC6.8 — Prevention of Unauthorized Access

**Requirement:** The entity implements controls to prevent unauthorized access.

**Implementation:**
- 401 returned for missing/invalid tokens
- 403 returned for valid token but insufficient role or wrong org
- 429 rate limiting on auth endpoints to prevent brute-force
- Failed login attempts logged to audit trail with IP address

**Evidence Files:**
- `app/api/middleware/org_context.py` — 401/403 enforcement
- `app/core/audit.py` — failed login logging
- `tests/test_rls_isolation.py` — automated rejection tests

---

*This document is part of the Resilo SOC2 Type I evidence package. Update quarterly or after any access control change.*
