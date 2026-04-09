# Resilo — data model reference

> **Auto-generate columns from a live DB:**
> ```bash
> python - <<'EOF'
> from app.core.database import engine
> from sqlalchemy import inspect
> inspector = inspect(engine)
> for table in sorted(inspector.get_table_names()):
>     print(f"\n## `{table}`")
>     for col in inspector.get_columns(table):
>         print(f"  {col['name']} ({col['type']}) nullable={col['nullable']}")
> EOF
> ```

---

## `users`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `UUID` | no | Primary key |
| `email` | `VARCHAR(254)` | no | Unique login address; max 254 chars enforced at API layer |
| `username` | `VARCHAR(100)` | yes | Display name |
| `hashed_password` | `TEXT` | no | bcrypt hash; set to `"sso_only"` for SSO-only accounts |
| `role` | `VARCHAR(50)` | no | RBAC role: `admin`, `operator`, `employee`, `viewer` |
| `org_id` | `UUID` | yes | FK → `organizations.id`; NULL until org is assigned |
| `is_active` | `BOOLEAN` | no | Soft-delete flag; inactive users cannot log in |
| `must_change_password` | `BOOLEAN` | no | Forces password change on next login |
| `totp_secret` | `TEXT` | yes | Encrypted TOTP seed; NULL when 2FA not enrolled |
| `created_at` | `TIMESTAMPTZ` | no | Row creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | no | Last modification timestamp |

**Primary key:** `id`
**Foreign key:** `org_id` → `organizations.id`

---

## `organizations`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `UUID` | no | Primary key |
| `name` | `VARCHAR(200)` | no | Display name for the org |
| `slug` | `VARCHAR(100)` | no | URL-safe unique identifier |
| `plan` | `VARCHAR(50)` | no | Subscription tier: `free`, `pro`, `enterprise` |
| `is_active` | `BOOLEAN` | no | Org suspension flag |
| `created_at` | `TIMESTAMPTZ` | no | Row creation timestamp |

**Primary key:** `id`

---

## `sessions`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `UUID` | no | Primary key |
| `user_id` | `UUID` | no | FK → `users.id` |
| `refresh_token_hash` | `TEXT` | no | SHA-256 hash of the opaque refresh token |
| `created_at` | `TIMESTAMPTZ` | no | Session start time |
| `expires_at` | `TIMESTAMPTZ` | no | Hard expiry; rows past this are invalid |
| `revoked_at` | `TIMESTAMPTZ` | yes | Set on logout; NULL means session is live |
| `user_agent` | `TEXT` | yes | Browser / client UA string |
| `ip_address` | `INET` | yes | Client IP at login time |

**Primary key:** `id`
**Foreign key:** `user_id` → `users.id`

---

## `audit_logs`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `BIGSERIAL` | no | Auto-increment primary key |
| `actor_id` | `UUID` | yes | FK → `users.id`; NULL for unauthenticated events |
| `org_id` | `UUID` | yes | FK → `organizations.id`; NULL for system events |
| `event_type` | `VARCHAR(100)` | no | e.g. `auth.login`, `user.role_changed`, `api_key.created` |
| `resource_type` | `VARCHAR(100)` | yes | Entity affected, e.g. `user`, `api_key` |
| `resource_id` | `TEXT` | yes | ID of the affected resource |
| `metadata` | `JSONB` | yes | Arbitrary key/value context (IP, old/new values, etc.) |
| `created_at` | `TIMESTAMPTZ` | no | Event timestamp |

**Primary key:** `id`
**Foreign key:** `actor_id` → `users.id`
**Foreign key:** `org_id` → `organizations.id`

---

## `api_keys`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `UUID` | no | Primary key |
| `org_id` | `UUID` | no | FK → `organizations.id` |
| `created_by` | `UUID` | no | FK → `users.id` |
| `name` | `VARCHAR(200)` | no | Human-readable label |
| `key_hash` | `TEXT` | no | SHA-256 hash of the raw key (raw key shown once at creation) |
| `prefix` | `VARCHAR(12)` | no | First 12 chars of raw key for display/lookup |
| `scopes` | `TEXT[]` | no | Array of permitted scopes, e.g. `{read:metrics, write:alerts}` |
| `expires_at` | `TIMESTAMPTZ` | yes | NULL means no expiry |
| `last_used_at` | `TIMESTAMPTZ` | yes | Updated on each successful request |
| `revoked_at` | `TIMESTAMPTZ` | yes | Set on revocation |
| `created_at` | `TIMESTAMPTZ` | no | Row creation timestamp |

**Primary key:** `id`
**Foreign key:** `org_id` → `organizations.id`
**Foreign key:** `created_by` → `users.id`

---

## `alembic_version`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `version_num` | `VARCHAR(32)` | no | Current Alembic migration head revision |

**Primary key:** `version_num`

---

_Fill in any `_TODO_` description cells by running the generation script above against a live database._
