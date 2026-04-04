# Phase 1 Implementation Summary

This document records how each Phase 1 issue was implemented, what was fixed during the audit, and how to verify every item is still correct.

Use it as an audit checklist, not just a changelog.

---

## Phase 1 Status

All Phase 1 items are implemented. Three bugs found during the post-implementation audit were also fixed:

| Issue | Title | Status |
|-------|-------|--------|
| #17 | Replace raw CREATE TABLE with Alembic | complete |
| #18 | Unify PostgreSQL-only auth and core storage | complete |
| #23 | Write authentication tests | complete |
| #19 | Fix schema drift | complete |
| #20 | Add DB connection pooling | complete |
| #21 | Add DB health check | complete |
| #11 | Enable TimescaleDB hypertables | complete |
| #24 | Add coverage gate in CI | complete |
| #25 | Fix CI deploy dependency | complete |
| #26 | Add API integration tests | complete |
| #8  | Centralize config in .env | complete |
| #10 | Add secrets rotation tooling | complete |
| —   | **AUDIT FIX**: Duplicate `_require_access_token` removed | complete |
| —   | **AUDIT FIX**: Test suite migrated from SQLite to PostgreSQL | complete |
| —   | **AUDIT FIX**: PostgreSQL service container added to CI | complete |

---

## Issue-by-Issue Detail

---

### #17 — Replace raw CREATE TABLE with Alembic

**Problem:** Tables were created manually on startup, causing schema drift.

**What changed:**
- Replaced the manual bootstrap path with Alembic-managed migrations.
- `alembic/env.py` reads `Base.metadata` from `app.core.database` and runs migrations via psycopg2 (converted from asyncpg URL at runtime).
- Deployment now calls `python -m alembic upgrade head` — never a safe-upgrade wrapper.

**Key files:**
- `alembic/env.py`
- `alembic/versions/001_initial_postgresql_schema.py`

**Verify:**
```bash
python -m alembic upgrade head   # must complete cleanly against a fresh database
grep -rn "create_all" app/       # must return zero results (no manual bootstrap)
grep -rn "alembic_safe_upgrade" . # must return zero results
```

---

### #18 — Unify PostgreSQL-only auth and core storage

**Problem:** Legacy SQLite auth path coexisted with the PostgreSQL core path.

**What changed:**
- Deleted all SQLite-era modules and migration scripts (listed in git status as `D`).
- `app/core/database.py` uses `postgresql+asyncpg` exclusively — no SQLite import, no fallback.
- Admin bootstrap (`create_admin.py`, `fix_admin_password.py`, `scripts/seed_admin.py`) updated to use the PostgreSQL models.

**Key files:**
- `app/core/database.py`
- `create_admin.py`
- `fix_admin_password.py`
- `scripts/seed_admin.py`
- `tests/conftest.py`

**Verify:**
```bash
grep -rn "sqlite" app/       # must return zero results
grep -rn "sqlite" alembic/   # must return zero results
grep -rn "sqlite" scripts/   # must return zero results
```

---

### #23 — Write authentication tests

**Problem:** Test coverage was 8%.

**What changed:**
- `tests/test_auth_api.py` covers the full auth request/response cycle:
  - Login → access token + refresh token returned, session persisted in DB.
  - Invalid credentials → 401.
  - Refresh token rotation → old token revoked, new token issued, replay of old token returns 401.
  - Logout → refresh token revoked, subsequent refresh returns 401.
  - `GET /auth/health` → `{status: ok, service: auth}`.
  - `GET /health/db` → `{status: ok, latency_ms: <int>}`.

**Key files:**
- `tests/test_auth_api.py`
- `tests/conftest.py`

**Verify:**
```bash
pytest tests/ -v
```

---

### #19 — Fix schema drift

**Problem:** A safe-upgrade wrapper silently stamped over bad migrations instead of failing.

**What changed:**
- `deploy.yml` calls `python -m alembic upgrade head` directly.
- No wrapper exists — a bad migration now causes the deploy pipeline to fail visibly.

**Key files:**
- `.github/workflows/deploy.yml` (job: `migrate-schema`)

**Verify:**
```bash
grep -n "alembic upgrade head" .github/workflows/deploy.yml
# must appear in migrate-schema job
grep -rn "alembic_safe_upgrade" .   # must return zero results
```

---

### #20 — Add DB connection pooling

**Problem:** A new database connection was opened per request.

**What changed:**
- `app/core/database.py` passes `pool_size`, `max_overflow`, `pool_timeout`, and `pool_recycle` to `create_async_engine`.
- All four values are read from environment variables with safe defaults.
- `config/env_validator.py` lists them in `OPTIONAL_ENV_VARS_WITH_DEFAULTS`.

**Key files:**
- `app/core/database.py` (lines 32–35, 56–64)
- `config/env_validator.py`
- `.env.example`

**Verify:**
```bash
grep -n "pool_size\|max_overflow\|pool_timeout\|pool_recycle" app/core/database.py
# must show all four pool params in the create_async_engine call
```

---

### #21 — Add DB health check

**Problem:** No health endpoint existed to verify database connectivity.

**What changed:**
- `app/api/runtime.py` registers `GET /health/db` via `build_health_router()`.
- The endpoint runs `SELECT 1`, measures wall-clock latency, and returns:
  ```json
  {"status": "ok", "latency_ms": 12}
  ```
- On failure it returns HTTP 503 with `status: degraded` and the error message.

**Key files:**
- `app/api/runtime.py` (`build_health_router`, lines 778–824)
- `tests/test_auth_api.py` (`test_db_health_endpoint`)

**Verify:**
```bash
curl http://localhost:<port>/health/db
# {"status":"ok","latency_ms":<int>}
```

---

### #11 — Enable TimescaleDB hypertables

**Problem:** The `metric_snapshots` table was a plain PostgreSQL table with no time-series optimisation.

**What changed:**
- `alembic/versions/001_initial_postgresql_schema.py` runs a `DO $$ ... END $$` block immediately after creating `metric_snapshots` that:
  1. Creates the `timescaledb` extension if absent.
  2. Calls `create_hypertable('metric_snapshots', 'timestamp', if_not_exists => TRUE)`.
  3. Enables column-store compression segmented by `org_id, agent_id`.
  4. Adds a 7-day compression policy.
  5. Catches `undefined_function` / `feature_not_supported` so plain PostgreSQL continues to work.
- `app/core/database.py` `init_db()` adds a retention policy via `add_retention_policy` (also gracefully skipped when TimescaleDB is absent).

**Key files:**
- `alembic/versions/001_initial_postgresql_schema.py` (lines 275–304)
- `app/core/database.py` (`init_db`, lines 496–517)
- `migrations/001_timescaledb_hypertables.sql` (standalone SQL reference copy)

**Verify (requires TimescaleDB):**
```sql
SELECT hypertable_name FROM timescaledb_information.hypertables;
-- must return: metric_snapshots
SELECT * FROM timescaledb_information.compression_settings WHERE hypertable_name = 'metric_snapshots';
```

---

### #24 — Add test coverage gate in CI

**Problem:** Coverage could drop to zero without blocking deployment.

**What changed:**
- `deploy.yml` test job runs:
  ```bash
  pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=60 -q
  ```
- CI fails if coverage drops below 60%.

**Key files:**
- `.github/workflows/deploy.yml` (job: `test`, lines 73–79)

**Verify:**
```bash
grep -n "cov-fail-under" .github/workflows/deploy.yml
# must show --cov-fail-under=60
```

---

### #25 — Fix CI deploy dependency

**Problem:** Deploy jobs ran even when tests failed.

**What changed:**
- Every deploy job declares `needs: [security-scan, lint, test, migrate-schema]`.
- Deploy is unreachable if any prior job fails.

**Key files:**
- `.github/workflows/deploy.yml` (all deploy jobs)

**Verify:**
```bash
grep -n "needs:" .github/workflows/deploy.yml
# every deploy job must list test and migrate-schema
```

---

### #26 — Add API integration tests

**Problem:** No tests exercised the full request → FastAPI → DB → response path.

**What changed:**
- `tests/test_auth_api.py` tests exercise the full stack:
  - `test_login_persists_refresh_session` — posts to `/auth/login`, then queries the DB directly to confirm a session row was written.
  - `test_db_health_endpoint` — hits `GET /health/db` through the ASGI stack and validates the response shape.
- `tests/conftest.py` wires `AsyncClient` to the real FastAPI ASGI app (not a stub).

**Key files:**
- `tests/test_auth_api.py`
- `tests/conftest.py`

**Verify:**
```bash
pytest tests/test_auth_api.py -v
```

---

### #8 — Centralize config in .env

**Problem:** Configuration values were scattered across modules with no startup validation.

**What changed:**
- `config/env_validator.py` must be called at the top of every entry point before other imports.
- It loads `.env` via `python-dotenv`, then validates all required vars, and applies safe defaults for optional ones.
- Required vars (startup exits with code 1 if missing):
  - `DATABASE_URL`, `JWT_SECRET_KEY`, `ADMIN_DEFAULT_PASSWORD`, `ALLOWED_ORIGINS`, `BACKUP_DIR`, `DEPLOY_HOST`, `ADMIN_DEFAULT_EMAIL`
- Optional vars with defaults applied silently:
  - `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10`, `DB_POOL_TIMEOUT=30`, `DB_POOL_RECYCLE=1800`, and others.

**Key files:**
- `config/env_validator.py`
- `.env.example`

**Verify:**
```bash
# Remove a required var and confirm fast-fail
unset JWT_SECRET_KEY && python -c "from config.env_validator import validate_environment; validate_environment()"
# must print: ERROR: Missing required environment variables: JWT_SECRET_KEY ...
```

---

### #10 — Add secrets rotation tooling

**Problem:** No tooling existed to rotate secrets safely.

**What changed:**
- `scripts/rotate_secrets.py` rotates three secrets in the `.env` file:
  - `JWT_SECRET_KEY` — new `secrets.token_urlsafe(48)`
  - `GATEWAY_JWT_SECRET` — new `secrets.token_urlsafe(48)`
  - `ENCRYPTION_KEY` — new Fernet key (`base64(secrets.token_bytes(32))`)
- Backs up the original `.env` to `.env.backup.<timestamp>` before writing.
- Prints next steps: restart services, revoke active refresh tokens, redeploy dependent services.

**Key files:**
- `scripts/rotate_secrets.py`

**Verify:**
```bash
cp .env .env.test && python scripts/rotate_secrets.py --env-file .env.test
# must print [OK] lines and show a backup path
# diff .env.test .env.test.backup.* must show JWT_SECRET_KEY changed
```

---

## Audit Fixes (applied after initial implementation)

---

### AUDIT FIX — Duplicate `_require_access_token` removed

**Problem (HIGH):** `app/api/runtime.py` contained two definitions of `_require_access_token`. The second definition (added at line ~369) shadowed the first and only decoded the JWT — it skipped the database lookup that verifies the user still exists and is active. Any deactivated user with an unexpired JWT token could access all protected routes.

**What changed:**
- Removed the second definition entirely.
- The single remaining definition at line 305 calls `_require_valid_access_payload`, which decodes the JWT and then queries the `users` table to confirm `is_active = true`.

**Key file:** `app/api/runtime.py`

**Verify:**
```bash
grep -n "def _require_access_token" app/api/runtime.py
# must return exactly ONE line
grep -n "_require_valid_access_payload" app/api/runtime.py
# must show it is called inside _require_access_token
```

---

### AUDIT FIX — Tests migrated from SQLite to PostgreSQL

**Problem (MEDIUM):** `tests/conftest.py` used a hidden SQLite engine (the URL was split across string literals to defeat grep). The Phase 1 summary incorrectly claimed tests used the PostgreSQL path. SQLite diverges from PostgreSQL on timezone-aware datetimes, JSON column behaviour, and the `locked_until` lockout comparison.

**What changed:**
- Removed the `_TEST_DB_FILE` / `_TEST_DB_URL` SQLite setup.
- `_TEST_DB_URL` now reads `os.environ["DATABASE_URL"]`, which is already set to `postgresql+asyncpg://test:test@localhost:5432/test_auth`.
- Removed the `_TEST_DB_FILE.unlink()` teardown call.
- The `create_async_engine` mock still intercepts the module-level engine creation in `database.py` and injects a NullPool PostgreSQL engine — same technique, correct driver.

**Key file:** `tests/conftest.py`

**Verify:**
```bash
grep -n "sqlite\|aiosqlite\|TEST_DB_FILE" tests/conftest.py
# must return zero results
grep -n "_TEST_DB_URL" tests/conftest.py
# must show: _TEST_DB_URL = os.environ["DATABASE_URL"]
```

---

### AUDIT FIX — PostgreSQL service container added to CI

**Problem (MEDIUM):** The CI test job had no database service, so tests could not connect to PostgreSQL and would fail or fall back to SQLite.

**What changed:**
- Added a `postgres:15` service container to the `test` job in `deploy.yml`.
- Container waits for `pg_isready` before the test step runs.
- `DATABASE_URL` is injected as a job-level env var so `conftest.py` picks it up correctly.

**Key file:** `.github/workflows/deploy.yml` (job: `test`)

**Verify:**
```yaml
# In .github/workflows/deploy.yml, the test job must contain:
services:
  postgres:
    image: postgres:15
env:
  DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test_auth
```

---

## Full Verification Checklist

Run these commands against a clean checkout to confirm everything is correct:

```bash
# 1. Alembic is the only schema path
python -m alembic upgrade head
grep -rn "create_all"          app/       # zero results
grep -rn "alembic_safe_upgrade" .         # zero results

# 2. No SQLite references in application code
grep -rn "sqlite" app/                    # zero results
grep -rn "sqlite" alembic/               # zero results
grep -rn "sqlite" scripts/               # zero results
grep -rn "sqlite\|aiosqlite" tests/conftest.py  # zero results

# 3. Auth tests pass
pytest tests/ -v

# 4. Coverage gate
pytest tests/ --cov=app --cov-fail-under=60

# 5. Single _require_access_token with DB check
grep -n "def _require_access_token" app/api/runtime.py   # exactly 1 line

# 6. DB pool settings present
grep -n "pool_size\|max_overflow\|pool_timeout\|pool_recycle" app/core/database.py

# 7. Health endpoint
curl http://localhost:<port>/health/db
# {"status":"ok","latency_ms":<int>}

# 8. CI blocks deploy on test failure
grep -n "needs:" .github/workflows/deploy.yml
# every deploy job must include: test, migrate-schema

# 9. Coverage gate in CI
grep -n "cov-fail-under" .github/workflows/deploy.yml

# 10. PostgreSQL service in CI test job
grep -A5 "services:" .github/workflows/deploy.yml
# must show postgres:15

# 11. TimescaleDB (requires TimescaleDB instance)
# SELECT hypertable_name FROM timescaledb_information.hypertables;
# → metric_snapshots

# 12. Env validation fails fast
unset JWT_SECRET_KEY
python -c "from config.env_validator import validate_environment; validate_environment()"
# EXIT 1, prints missing var list

# 13. Secrets rotation
cp .env .env.test
python scripts/rotate_secrets.py --env-file .env.test
# prints [OK] with backup path, diff shows keys rotated
```

---

## Notes

- The main implementation risk in Phase 1 was schema drift hidden by a bootstrap helper. That helper is gone.
- The main security bug found in the audit was the shadowed `_require_access_token`. Fixed.
- The main test quality issue was the hidden SQLite engine in conftest. Fixed.
- If a future migration fails, the right fix is to repair the migration — do not restore a safe-upgrade wrapper.
- Phase 2 (real-time loop + AI) is unblocked. This is the stable foundation it depends on.
