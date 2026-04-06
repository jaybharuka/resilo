# SOC2 Type I — Key Rotation and Secret Management Evidence

**Control Domain:** Cryptographic Key Management
**Last Reviewed:** 2026-04-07
**Owner:** Engineering / Security Team
**Status:** Implemented

---

## CC9.3 — Cryptographic Key Rotation

**Requirement:** Cryptographic keys are rotated on a defined schedule and upon compromise.

---

## Key Inventory and Rotation Schedule

| Key | Location | Algorithm | Rotation Period | Last Rotated | Next Due |
|---|---|---|---|---|---|
| `JWT_SECRET_KEY` | `.env` / Kubernetes Secret | HMAC-SHA256 32B | 90 days | On deployment | 90 days post-deploy |
| `ENCRYPTION_KEY` | `.env` / Kubernetes Secret | Fernet AES-128 | 180 days | On deployment | 180 days post-deploy |
| TLS certificates | Kubernetes Secret (cert-manager) | RSA-2048 / ECDSA | 90 days (auto) | Auto-managed | Auto |
| PostgreSQL password | DB auth + Kubernetes Secret | N/A | 90 days | On deployment | 90 days post-deploy |
| API keys (per user) | DB (bcrypt hash) | SHA-256 | User-initiated or 365 days | Per issuance | Per issuance |

---

## Rotation Procedures

### JWT_SECRET_KEY Rotation

**Impact:** All active sessions invalidated. Users must re-authenticate.
**Recommended timing:** Off-peak hours

```bash
# Step 1: Generate new key
python scripts/rotate_secrets.py --key JWT_SECRET_KEY

# Step 2: Apply to Kubernetes secret
kubectl create secret generic aiops-secrets \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -

# Step 3: Rolling restart (zero-downtime)
kubectl rollout restart deployment/api-gateway -n production

# Step 4: Verify
kubectl rollout status deployment/api-gateway -n production
curl https://api.resilo.io/health/ready
```

**Evidence Script:** `scripts/rotate_secrets.py`

---

### ENCRYPTION_KEY Rotation

**Impact:** Existing encrypted fields must be re-encrypted. Requires migration.
**Warning:** Do NOT delete old key until re-encryption is complete.

```bash
# Step 1: Generate new key
NEW_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Step 2: Set both old and new key in MultiFernet configuration
# In app/core/encryption.py, update to use MultiFernet([new_key, old_key])
# This allows decryption of old data while encrypting new data with new key

# Step 3: Run re-encryption migration
python scripts/rotate_secrets.py --key ENCRYPTION_KEY --new-value "$NEW_KEY"

# Step 4: After all data re-encrypted, remove old key from MultiFernet
# Step 5: Commit config and deploy
```

**Evidence Script:** `scripts/rotate_secrets.py`

---

### TLS Certificate Rotation

Managed automatically by `cert-manager` in Kubernetes.
- Certificates renewed 30 days before expiry
- No manual action required unless cert-manager fails

**Verify cert-manager health:**
```bash
kubectl get certificates -n production
kubectl get certificaterequests -n production
```

---

### PostgreSQL Password Rotation

```bash
# Step 1: Generate new password
NEW_PW=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Step 2: Update PostgreSQL
psql -h $DB_HOST -U postgres -c "ALTER USER app_user PASSWORD '$NEW_PW';"

# Step 3: Update Kubernetes secret
kubectl patch secret aiops-secrets -n production \
  --type='json' \
  -p='[{"op":"replace","path":"/data/DATABASE_URL","value":"'$(echo -n "postgresql+asyncpg://app_user:$NEW_PW@$DB_HOST/aiops" | base64)'"}]'

# Step 4: Rolling restart
kubectl rollout restart deployment/api-gateway deployment/orchestrator -n production
```

---

## API Key Revocation

User API keys can be revoked at any time:
- Self-service: `DELETE /auth/api-keys/{key_id}` (authenticated)
- Admin: `DELETE /admin/api-keys/{key_id}` (admin role required)
- Mass revocation (compromise): `UPDATE api_keys SET is_active = false WHERE org_id = '<id>'`

All revocations logged to `audit_logs` with `action = "apikey_revoke"`.

**Evidence File:** `app/core/apikey.py`

---

## CC3.3 — Risk Assessment for Key Compromise

**Procedure on suspected compromise:**

1. **Immediate:** Rotate the compromised key (see procedures above)
2. **Within 1 hour:** Audit `audit_logs` for any suspicious access using the compromised key
3. **Within 24 hours:** Determine scope of exposure (which data/orgs affected)
4. **Within 72 hours:** Notify affected customers if data was accessed
5. **Within 5 days:** Post-incident report with root cause and prevention measures

---

## Rotation Log

| Date | Key | Reason | Performed By | Verified By |
|---|---|---|---|---|
| 2026-04-07 | All keys | Initial Phase 4 deployment | Engineering | Security Team |

*Update this log every time a key is rotated.*

---

*This document is part of the Resilo SOC2 Type I evidence package. Review quarterly.*
