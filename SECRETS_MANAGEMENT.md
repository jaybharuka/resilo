# Secrets Management Guide

## Overview

This document describes how secrets are managed in the Resilo project. All sensitive credentials must be stored in environment variables and never committed to version control.

## Required Secrets

The following secrets **must** be set in your environment before starting the application:

### JWT_SECRET_KEY
- **Purpose**: Signing and verifying JWT access tokens
- **Length**: Minimum 32 characters
- **Generation**: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- **Rotation**: Change this to invalidate all existing tokens

### ENCRYPTION_KEY
- **Purpose**: Field-level encryption of sensitive data at rest (email, full_name)
- **Length**: Must be a valid Fernet key (base64-encoded 32 bytes)
- **Generation**: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **Rotation**: See Key Rotation section below

### DATABASE_URL
- **Purpose**: PostgreSQL connection string
- **Format**: `postgresql+asyncpg://user:password@host:port/database`
- **Example**: `postgresql+asyncpg://aiops:secure_password@localhost:5432/aiops`
- **Security**: Use strong passwords (12+ chars, mixed case, digits, special chars)

## Optional Secrets with Defaults

These secrets have sensible defaults but can be overridden:

- `ADMIN_DEFAULT_PASSWORD`: Default admin password (default: "Admin@1234")
- `ENVIRONMENT`: "development" or "production" (default: "development")
- `FRONTEND_URL`: Frontend application URL (default: "http://localhost:3000")
- `BACKUP_DIR`: Directory for database backups (default: "./backups")
- `BACKUP_RETENTION_DAYS`: Days to retain backups (default: "30")
- `BACKUP_HEALTH_CHECK_HOURS`: Backup age threshold in hours (default: "24")
- `ALLOWED_ORIGINS`: CORS allowed origins (comma-separated)

## Setup Instructions

### 1. Generate Required Secrets

```bash
# Generate JWT_SECRET_KEY
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"

# Generate ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

### 2. Create .env File

Copy `.env.example` to `.env` and fill in the generated secrets:

```bash
cp .env.example .env
# Edit .env and add the generated secrets
```

### 3. Verify Secrets

The application will validate all required secrets on startup. If any are missing, it will fail with a clear error message.

## Key Rotation

### JWT_SECRET_KEY Rotation

When rotating JWT_SECRET_KEY:

1. Generate a new key
2. Set `JWT_SECRET_KEY_PREVIOUS` to the old key (optional, for grace period)
3. Update `JWT_SECRET_KEY` with the new key
4. All existing tokens become invalid immediately
5. Users must log in again

### ENCRYPTION_KEY Rotation

When rotating ENCRYPTION_KEY (for encrypted fields):

1. Generate a new key
2. Set `ENCRYPTION_KEY_PREVIOUS` to the old key
3. Update `ENCRYPTION_KEY` with the new key
4. Old encrypted data can still be decrypted with `ENCRYPTION_KEY_PREVIOUS`
5. New data is encrypted with the new `ENCRYPTION_KEY`
6. Run migration script to re-encrypt all data with new key (optional)

**Note**: Changing ENCRYPTION_KEY without proper migration will make old encrypted data unreadable.

## Best Practices

### Development

- Use `.env.example` as a template
- Never commit `.env` to version control (protected by .gitignore)
- Use weak secrets for development (e.g., "dev-secret-key-12345")
- Rotate secrets regularly even in development

### Production

- Use strong, randomly generated secrets (32+ characters)
- Store secrets in a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
- Never store secrets in code, config files, or version control
- Rotate secrets every 90 days minimum
- Audit all secret access and rotation events
- Use different secrets for each environment (dev, staging, prod)
- Enable secret versioning for graceful rotation

### Deployment

1. Generate secrets in your secrets manager
2. Inject secrets as environment variables at runtime
3. Never pass secrets as command-line arguments
4. Never log secret values (even in debug mode)
5. Verify all required secrets are present before starting

## Validation

The application validates secrets on startup:

```python
from secrets import validate_secrets

# This is called automatically in @app.on_event("startup")
validate_secrets()  # Raises RuntimeError if any required secret is missing
```

## Troubleshooting

### "Missing required environment variables"

**Cause**: One or more required secrets are not set.

**Solution**:
1. Check `.env` file exists and has all required variables
2. Verify variable names match exactly (case-sensitive)
3. Ensure no trailing whitespace in values
4. Check environment variables are loaded before starting app

### "Invalid ENCRYPTION_KEY format"

**Cause**: ENCRYPTION_KEY is not a valid Fernet key.

**Solution**:
1. Regenerate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Ensure the full key is copied (including any padding)
3. Verify no extra whitespace

### "Decryption failed: invalid token"

**Cause**: Data was encrypted with a different ENCRYPTION_KEY.

**Solution**:
1. Check if you're using the correct ENCRYPTION_KEY
2. If rotating keys, ensure `ENCRYPTION_KEY_PREVIOUS` is set to the old key
3. If data is unrecoverable, restore from backup

## Related Files

- `.env.example`: Template for environment variables
- `.gitignore`: Prevents accidental .env commits
- `app/core/secrets.py`: Secrets validation and rotation helpers
- `app/core/encryption.py`: Field-level encryption implementation

## Security Checklist

- [ ] All required secrets are set in environment
- [ ] `.env` file is in `.gitignore` and never committed
- [ ] Secrets are strong (32+ characters, random)
- [ ] Secrets are rotated every 90 days
- [ ] Secret access is audited and logged
- [ ] Different secrets for each environment
- [ ] Secrets are stored in a secrets manager (production)
- [ ] No secrets in logs, error messages, or code
- [ ] Backup encryption key is stored securely
