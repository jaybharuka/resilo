# Resilo Auth API

Enterprise-grade authentication and authorization service for multi-tenant SaaS applications.

## Overview

Resilo Auth API provides secure, scalable authentication with:
- **JWT-based access tokens** with configurable expiration
- **Two-factor authentication (TOTP)** for enhanced security
- **Multi-tenancy support** with org-scoped authorization
- **Audit logging** for compliance and security monitoring
- **Field-level encryption** for sensitive data at rest
- **API key authentication** for service-to-service calls
- **Comprehensive monitoring** with Prometheus metrics and distributed tracing

## Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL 12+
- 2GB RAM minimum

### 5-Minute Setup

```bash
# 1. Clone repository
git clone https://github.com/resilo/resilo.git
cd resilo

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 5. Create .env file
cp .env.example .env
# Edit .env and add:
# - JWT_SECRET_KEY (generate: python -c "import secrets; print(secrets.token_urlsafe(32))")
# - ENCRYPTION_KEY (from step 4)
# - DATABASE_URL (postgresql://user:password@localhost/aiops)

# 6. Run migrations
alembic upgrade head

# 7. Start server
python -m uvicorn app.api.auth_api:app --reload
```

Server runs at `http://localhost:5001`

## Architecture

```
Resilo Auth API
├── app/
│   ├── api/
│   │   └── auth_api.py           # FastAPI application
│   ├── core/
│   │   ├── database.py           # SQLAlchemy models
│   │   ├── logging_config.py     # Structured logging
│   │   ├── audit.py              # Audit logging
│   │   ├── authz.py              # Authorization checks
│   │   ├── apikey.py             # API key management
│   │   ├── encryption.py         # Field-level encryption
│   │   ├── secrets.py            # Secrets management
│   │   ├── retention.py          # Data retention policies
│   │   ├── backup.py             # Database backups
│   │   ├── metrics.py            # Prometheus metrics
│   │   ├── trace_context.py      # Distributed tracing
│   │   └── http_client.py        # HTTP client helpers
│   └── models/
│       └── (Pydantic request/response models)
├── tests/
│   └── test_auth_api.py          # Pytest async tests
├── alembic/                       # Database migrations
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
└── README.md                      # This file
```

## Key Features

### Authentication
- **JWT Tokens**: Configurable expiration (default 24h)
- **Password Hashing**: bcrypt with salt
- **2FA Support**: TOTP-based two-factor authentication
- **Session Management**: Persistent user sessions with timeout

### Authorization
- **Role-Based Access Control**: admin, devops, viewer, manager, employee, guest
- **Org-Scoped Access**: Users can only access their organization's data
- **API Key Authentication**: Service-to-service calls with API keys

### Security
- **Field-Level Encryption**: Email and full_name encrypted at rest
- **Audit Logging**: All sensitive operations logged for compliance
- **Secrets Management**: Environment-based secrets with validation
- **HTTPS Enforcement**: Enforced in production mode
- **Rate Limiting**: Login (5/min), registration (3/hour)

### Operations
- **Automated Backups**: Daily database backups with retention policy
- **Data Retention**: Automatic cleanup of expired sessions, tokens, and logs
- **Health Checks**: Endpoints for monitoring backup and system health
- **Prometheus Metrics**: Request latency, error rates, database queries
- **Distributed Tracing**: W3C Trace Context propagation

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_auth_api.py::test_login -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Code Quality

```bash
# Format code
black app/ tests/

# Lint
ruff check app/ tests/

# Type checking
mypy app/
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add new column"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## API Endpoints

### Authentication
- `POST /auth/login` - Login with email/password
- `POST /auth/logout` - Logout and invalidate session
- `POST /auth/register` - Register new organization
- `POST /auth/change-password` - Change user password
- `POST /auth/forgot-password` - Request password reset
- `POST /auth/reset-password` - Reset password with token

### Two-Factor Authentication
- `POST /auth/2fa/setup` - Setup TOTP
- `POST /auth/2fa/enable` - Enable 2FA
- `POST /auth/2fa/disable` - Disable 2FA

### User Management
- `GET /users` - List users (admin only)
- `GET /users/{user_id}` - Get user details
- `POST /users` - Create new user (admin only)
- `PUT /users/{user_id}` - Update user (admin only)
- `DELETE /users/{user_id}` - Deactivate user (admin only)

### Invites
- `POST /auth/invites` - Create invite (admin only)
- `GET /auth/invites` - List invites (admin only)
- `DELETE /auth/invites/{token}` - Revoke invite (admin only)
- `POST /auth/accept-invite` - Accept invite

### API Keys
- `POST /auth/api-keys` - Create API key (admin only)
- `GET /auth/api-keys` - List API keys (admin only)
- `DELETE /auth/api-keys/{key_id}` - Revoke API key (admin only)

### Health & Monitoring
- `GET /auth/health` - Service health check
- `GET /auth/health/backups` - Backup health status
- `GET /metrics` - Prometheus metrics

## Configuration

### Environment Variables

Required:
- `JWT_SECRET_KEY` - Secret for signing JWT tokens (min 32 chars)
- `ENCRYPTION_KEY` - Fernet key for field-level encryption
- `DATABASE_URL` - PostgreSQL connection string

Optional:
- `ENVIRONMENT` - "development" or "production" (default: development)
- `ADMIN_DEFAULT_PASSWORD` - Default admin password (default: Admin@1234)
- `BACKUP_DIR` - Backup directory (default: ./backups)
- `BACKUP_RETENTION_COUNT` - Backups to keep (default: 7)

See `.env.example` for all options.

## Deployment

### Production Checklist

```bash
# 1. Verify secrets
echo $JWT_SECRET_KEY $ENCRYPTION_KEY $DATABASE_URL

# 2. Run migrations
alembic upgrade head

# 3. Run tests
pytest tests/ -v

# 4. Create backup
python -c "from app.core.backup import create_backup; create_backup()"

# 5. Start service
python -m uvicorn app.api.auth_api:app --host 0.0.0.0 --port 5001
```

See `DEPLOYMENT.md` for detailed deployment procedures.

## Documentation

- `DEPLOYMENT.md` - Deployment guide with pre/post-deployment checklists
- `INCIDENT_RESPONSE.md` - Incident response procedures and runbooks
- `RUNBOOKS.md` - Operational runbooks for maintenance tasks
- `SECRETS_MANAGEMENT.md` - Secrets management and rotation
- `DATA_RETENTION.md` - Data retention policies and cleanup
- `CHANGELOG.md` - Version history and release notes

## Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and commit: `git commit -m "Add my feature"`
3. Push to branch: `git push origin feature/my-feature`
4. Open Pull Request

### Code Style
- Follow PEP 8
- Use type hints
- Write docstrings for functions
- Add tests for new features

## Support

- **Issues**: [GitHub Issues](https://github.com/resilo/resilo/issues)
- **Documentation**: See docs/ directory
- **Email**: support@resilo.io

## License

MIT License - see LICENSE file for details

## Version

Current: 2.0.0 (see CHANGELOG.md for version history)