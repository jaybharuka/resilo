# Changelog

All notable changes to the Resilo Auth API are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Audit logging for sensitive operations (user creation, password changes, org registration, invite acceptance)
- Org-scoped authorization to prevent cross-org data access
- API key authentication for service-to-service calls
- Field-level encryption at rest for sensitive data (email, full_name)
- Secrets management with validation and rotation support
- Data retention policies with automatic cleanup (sessions, tokens, audit logs)
- Automated database backups with retention policy
- Comprehensive deployment guide with pre/post-deployment checklists
- Incident response plan with severity levels and runbooks
- Operational runbooks for maintenance tasks
- Prometheus metrics collection (request latency, error rates, database queries)
- Distributed request tracing with W3C Trace Context propagation
- Structured JSON logging with correlation IDs

### Changed
- Enhanced API documentation with detailed docstrings and response models
- Improved error handling with correlation IDs for debugging
- Strengthened password validation requirements
- Updated rate limiting for login (5/min) and registration (3/hour)

### Fixed
- Hardcoded JWT secret fallback vulnerability
- Missing permission checks on user management endpoints
- Unprotected service-to-service API calls
- Data stored in plaintext without encryption
- Missing data retention policies
- No backup strategy for disaster recovery
- Undocumented deployment procedures
- No incident response procedures

### Security
- Added field-level encryption for sensitive data
- Implemented org-scoped authorization checks
- Added API key authentication for service calls
- Enforced HTTPS in production mode
- Added secrets validation at startup
- Implemented audit logging for compliance

## [2.0.0] - 2026-03-31

### Added
- Complete rewrite of authentication system with FastAPI
- JWT-based access tokens with configurable expiration
- Two-factor authentication (TOTP) support
- Password reset flow with email verification
- Organization management with multi-tenancy
- User invitation system with email notifications
- Role-based access control (admin, devops, viewer, manager, employee, guest)
- Comprehensive API documentation with OpenAPI/Swagger
- Health check endpoints for monitoring
- Metrics endpoint for Prometheus integration
- Structured logging with correlation IDs
- Database migrations with Alembic
- Async database operations with SQLAlchemy 2.0
- Rate limiting on authentication endpoints
- CORS support for frontend integration

### Changed
- Migrated from Flask to FastAPI for better async support
- Switched to PostgreSQL for production use
- Implemented async/await throughout codebase
- Updated database schema for multi-tenancy

### Fixed
- Security vulnerabilities in legacy Flask implementation
- Database connection pooling issues
- Race conditions in session management

### Removed
- Legacy Flask API server
- SQLite database support (production)
- Synchronous database operations

### Breaking Changes
- API endpoints changed from `/api/v1/` to `/auth/`
- Database schema incompatible with v1.x
- JWT token format changed
- Configuration file format changed from INI to environment variables

### Upgrade Instructions

#### From 1.x to 2.0.0

1. **Backup database**: `pg_dump aiops > backup_v1.sql`
2. **Create new database**: `createdb aiops_v2`
3. **Run migrations**: `alembic upgrade head`
4. **Migrate user data**: Use migration script (see MIGRATION.md)
5. **Update configuration**: Use .env.example as template
6. **Test thoroughly**: Run full test suite
7. **Deploy**: Follow DEPLOYMENT.md
8. **Verify**: Check health endpoints and smoke tests

## [1.5.0] - 2026-01-15

### Added
- Basic audit logging for user actions
- User deactivation feature
- Session timeout configuration
- Password expiration policies

### Fixed
- SQL injection vulnerabilities in user search
- Cross-site scripting (XSS) in error messages
- Session fixation vulnerability

### Security
- Added input validation on all endpoints
- Implemented CSRF protection
- Added security headers (X-Frame-Options, X-Content-Type-Options)

## [1.4.0] - 2025-11-20

### Added
- Email notification system
- User profile management
- Organization settings page

### Changed
- Improved login form UX
- Updated password requirements

### Fixed
- Email delivery failures
- Session persistence issues

## [1.3.0] - 2025-09-10

### Added
- Two-factor authentication (SMS)
- User activity logging
- Admin dashboard

### Changed
- Redesigned authentication flow
- Improved error messages

### Fixed
- Database connection leaks
- Memory leaks in session manager

## [1.2.0] - 2025-07-05

### Added
- Password reset functionality
- User role management
- Basic audit logging

### Fixed
- Login timeout issues
- Password validation bugs

## [1.1.0] - 2025-05-20

### Added
- User invitation system
- Organization creation
- Basic role-based access control

### Fixed
- Authentication bypass vulnerability
- Session management issues

## [1.0.0] - 2025-03-31

### Added
- Initial release
- User registration and login
- Password hashing with bcrypt
- Session management
- Basic API endpoints

## Version Support

| Version | Status | Release Date | End of Life |
|---------|--------|--------------|-------------|
| 2.0.0 | Current | 2026-03-31 | 2027-03-31 |
| 1.5.0 | Deprecated | 2026-01-15 | 2026-07-15 |
| 1.4.0 | Unsupported | 2025-11-20 | 2026-01-15 |
| 1.3.0 | Unsupported | 2025-09-10 | 2025-11-20 |
| < 1.3.0 | Unsupported | - | - |

## How to Upgrade

### Minor Version Upgrades (e.g., 2.0.0 → 2.1.0)

1. Review changelog for breaking changes
2. Follow DEPLOYMENT.md procedures
3. No database migration required
4. Run smoke tests after deployment

### Major Version Upgrades (e.g., 1.x → 2.0.0)

1. **Plan**: Schedule maintenance window
2. **Backup**: Create full database backup
3. **Review**: Read upgrade instructions in changelog
4. **Test**: Test upgrade in staging environment
5. **Deploy**: Follow DEPLOYMENT.md
6. **Verify**: Run comprehensive test suite
7. **Monitor**: Watch for errors in logs

## Reporting Issues

Found a bug or security issue?

- **Bug Report**: Create issue on GitHub with reproduction steps
- **Security Issue**: Email security@example.com (do not create public issue)
- **Feature Request**: Create discussion on GitHub

## Contributing

See CONTRIBUTING.md for guidelines on submitting changes.

## Related Documentation

- `DEPLOYMENT.md`: How to deploy new versions
- `INCIDENT_RESPONSE.md`: How to handle issues
- `RUNBOOKS.md`: Operational procedures
- `MIGRATION.md`: Data migration guides
