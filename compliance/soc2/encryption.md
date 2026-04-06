# SOC2 Type I — Encryption Evidence

**Control Domain:** Encryption and Key Management
**Last Reviewed:** 2026-04-07
**Owner:** Engineering / Security Team
**Status:** Implemented

---

## CC9.1 — Data Encryption at Rest

**Requirement:** Sensitive data is encrypted when stored.

**Implementation:**
- Field-level encryption using Fernet (AES-128-CBC + HMAC-SHA256) via `app/core/encryption.py`
- Encrypted columns: `refresh_token`, `password_reset_token`, `invite_token`, `api_key_hash` (hashed), sensitive `detail` fields in audit logs
- Encryption key sourced from `ENCRYPTION_KEY` environment variable (Fernet key = base64-encoded 32 bytes)
- PostgreSQL data directory encrypted at rest using disk-level encryption (cloud provider managed — AWS EBS/Azure Disk with AES-256)

**Key Generation:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Evidence Files:**
- `app/core/encryption.py` — `EncryptedString` TypeDecorator
- `alembic/versions/001_initial_postgresql_schema.py` — encrypted column definitions

---

## CC9.2 — Data Encryption in Transit

**Requirement:** Data in transit is encrypted using TLS.

**Implementation:**
- All HTTP traffic requires HTTPS (TLS 1.2 minimum, TLS 1.3 preferred)
- TLS termination at ingress (Kubernetes ingress controller with cert-manager)
- Internal service-to-service traffic within Kubernetes uses mutual TLS (mTLS) via service mesh
- WebSocket connections use WSS (WebSocket Secure)
- JWT tokens transmitted over HTTPS only; `secure` cookie flag enforced

**Cipher Suites Allowed:**
- TLS_AES_256_GCM_SHA384
- TLS_CHACHA20_POLY1305_SHA256
- TLS_AES_128_GCM_SHA256

**Evidence Files:**
- `helm/aiops-bot/templates/api-gateway-service.yaml` — HTTPS-only ingress config
- Kubernetes ingress annotations enforce `ssl-redirect: "true"`

---

## CC9.3 — Key Management Procedures

**Requirement:** Cryptographic keys are managed according to a formal procedure.

**Key Inventory:**

| Key | Algorithm | Rotation Period | Storage |
|---|---|---|---|
| `JWT_SECRET_KEY` | HMAC-SHA256 (32 bytes) | 90 days | Environment variable / secrets manager |
| `ENCRYPTION_KEY` | Fernet (AES-128) | 180 days | Environment variable / secrets manager |
| TLS certificates | RSA-2048 / ECDSA P-256 | Auto (cert-manager, 90 days) | Kubernetes Secret |
| Database password | N/A (hash stored) | 90 days | PostgreSQL auth |

**Rotation Process:**
1. Generate new key: `python scripts/rotate_secrets.py --key JWT_SECRET_KEY`
2. Script backs up current `.env` with timestamp
3. Overwrites key in `.env`
4. Operator restarts application pods (zero-downtime rolling restart in Kubernetes)
5. Old tokens invalidated after `JWT_EXPIRY` window expires

**Evidence Files:**
- `scripts/rotate_secrets.py` — automated rotation script
- `app/core/encryption.py:get_encryption_key()` — runtime key validation

---

## CC9.4 — Encryption Algorithm Standards

**Requirement:** Industry-standard encryption algorithms are used.

**Algorithms in Use:**

| Purpose | Algorithm | Standard |
|---|---|---|
| Field encryption | AES-128-CBC (Fernet) | NIST SP 800-38A |
| Password hashing | bcrypt (cost 12) | NIST SP 800-63B |
| JWT signing | HMAC-SHA256 (HS256) | RFC 7518 |
| TLS | AES-256-GCM, ChaCha20-Poly1305 | RFC 8446 (TLS 1.3) |
| API key hashing | bcrypt | NIST SP 800-63B |

**Prohibited algorithms:** MD5, SHA-1, DES, 3DES, RC4, RSA < 2048-bit

**Evidence Files:**
- `app/core/encryption.py` — Fernet implementation
- `requirements.txt` — `cryptography>=3.4` (maintains current OpenSSL)

---

## CC9.5 — Secret Detection and Prevention

**Requirement:** Secrets are not exposed in source code or logs.

**Implementation:**
- `.env.example` contains only placeholder values — never actual secrets
- `.gitignore` explicitly excludes `.env`, `*.key`, `*.pem`, `*.p12`
- No hardcoded secrets in any source file (enforced via pre-commit hook scanning)
- Log output sanitizes JWT tokens and passwords before writing
- Error messages do not include raw exception traces in production responses

**Evidence Files:**
- `.env.example` — placeholder-only template
- `.gitignore` — secret file exclusions
- `config/logger.py` — sanitized logging

---

*This document is part of the Resilo SOC2 Type I evidence package. Update after any encryption configuration change.*
