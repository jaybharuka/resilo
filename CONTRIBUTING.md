# Contributing to Resilo

Thank you for your interest in contributing to Resilo! This document provides guidelines and instructions for contributing.

## Code of Conduct

We are committed to providing a welcoming and inclusive environment for all contributors. Please:
- Be respectful and professional in all interactions
- Welcome diverse perspectives and backgrounds
- Report harassment or inappropriate behavior to maintainers
- Focus on constructive feedback

## Getting Started

### Prerequisites
- Python 3.9+
- PostgreSQL 12+
- Git
- Virtual environment (venv or conda)

### Development Setup

```bash
# 1. Fork and clone repository
git clone https://github.com/your-username/resilo.git
cd resilo

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies (including dev dependencies)
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Setup pre-commit hooks
pre-commit install

# 5. Create .env file
cp .env.example .env
# Edit .env with your local settings

# 6. Run migrations
alembic upgrade head

# 7. Run tests to verify setup
pytest tests/ -v
```

## Coding Standards

### Code Style

We follow PEP 8 with these tools:

```bash
# Format code
black app/ tests/

# Lint code
ruff check app/ tests/ --fix

# Type checking
mypy app/
```

### Python Guidelines

- Use type hints for all function parameters and return values
- Write docstrings for all public functions and classes
- Keep functions focused and under 50 lines when possible
- Use descriptive variable names
- Avoid magic numbers (use named constants)

### Example

```python
def create_user(email: str, password: str, org_id: str) -> User:
    """
    Create a new user in the organization.
    
    Args:
        email: User email address
        password: User password (will be hashed)
        org_id: Organization ID
    
    Returns:
        Created User object
    
    Raises:
        ValueError: If email is invalid or already exists
    """
    if not is_valid_email(email):
        raise ValueError(f"Invalid email: {email}")
    
    hashed_password = hash_password(password)
    user = User(email=email, hashed_password=hashed_password, org_id=org_id)
    return user
```

## Git Workflow

### Branch Naming

Use descriptive branch names:
- `feature/add-2fa` - New feature
- `fix/login-timeout` - Bug fix
- `docs/update-readme` - Documentation
- `refactor/optimize-queries` - Code refactoring
- `test/add-auth-tests` - Test additions

### Commits

Write clear, descriptive commit messages:

```bash
# Good
git commit -m "Add two-factor authentication support"
git commit -m "Fix database connection pool exhaustion"
git commit -m "Improve login endpoint performance by 30%"

# Bad
git commit -m "fix stuff"
git commit -m "update code"
git commit -m "WIP"
```

### Pull Requests

1. **Create feature branch**:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes and commit**:
   ```bash
   git add .
   git commit -m "Add my feature"
   ```

3. **Push to your fork**:
   ```bash
   git push origin feature/my-feature
   ```

4. **Open Pull Request** on GitHub:
   - Use descriptive title
   - Reference related issues: "Fixes #123"
   - Describe changes and rationale
   - Include testing instructions

5. **PR Template**:
   ```markdown
   ## Description
   Brief description of changes
   
   ## Related Issues
   Fixes #123
   
   ## Testing
   - [ ] Unit tests added/updated
   - [ ] Integration tests passed
   - [ ] Manual testing completed
   
   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] Documentation updated
   - [ ] No breaking changes
   ```

## Testing Requirements

### Unit Tests

All new code must include tests:

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_auth_api.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Test Guidelines

- Write tests for new features and bug fixes
- Aim for > 80% code coverage
- Use descriptive test names: `test_login_with_invalid_email_fails`
- Test both success and failure cases
- Use fixtures for common setup

### Example Test

```python
import pytest
from app.api.auth_api import app
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_with_valid_credentials():
    """Test successful login with valid email and password."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "ValidPassword123!"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_login_with_invalid_email():
    """Test login fails with invalid email."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/auth/login",
            json={"email": "invalid-email", "password": "ValidPassword123!"}
        )
        assert response.status_code == 400
```

## Documentation

### Code Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Include examples for complex functions
- Document exceptions raised

### User Documentation

- Update README.md for new features
- Update CHANGELOG.md with changes
- Add/update relevant docs (DEPLOYMENT.md, RUNBOOKS.md, etc.)
- Keep documentation in sync with code

## PR Review Process

### What Reviewers Look For

- **Code Quality**: Follows style guidelines, no obvious bugs
- **Tests**: Adequate test coverage, tests pass
- **Documentation**: Code and user docs updated
- **Performance**: No performance regressions
- **Security**: No security vulnerabilities introduced
- **Breaking Changes**: Clearly documented if any

### Responding to Feedback

- Address all comments before re-requesting review
- Explain any disagreements respectfully
- Push new commits (don't force-push until approved)
- Mark conversations as resolved after addressing

### Approval and Merge

- Requires 1 approval from maintainer
- All CI checks must pass
- No merge conflicts
- Squash commits before merging (optional)

## Release Process

### Version Numbering

We follow Semantic Versioning (MAJOR.MINOR.PATCH):
- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

### Release Steps

1. **Update version**:
   ```bash
   # Update version in setup.py, __init__.py, etc.
   ```

2. **Update CHANGELOG.md**:
   ```markdown
   ## [2.1.0] - 2026-04-15
   
   ### Added
   - New feature description
   
   ### Fixed
   - Bug fix description
   ```

3. **Create release branch**:
   ```bash
   git checkout -b release/2.1.0
   ```

4. **Tag release**:
   ```bash
   git tag -a v2.1.0 -m "Release version 2.1.0"
   git push origin v2.1.0
   ```

5. **Create GitHub Release**:
   - Use tag as title
   - Copy CHANGELOG section as description
   - Attach release notes

## Common Issues

### Pre-commit Hooks Failing

```bash
# Run pre-commit on all files
pre-commit run --all-files

# Update pre-commit hooks
pre-commit autoupdate
```

### Tests Failing Locally

```bash
# Ensure database is set up
alembic upgrade head

# Clear pytest cache
pytest --cache-clear

# Run with verbose output
pytest tests/ -vv -s
```

### Type Checking Errors

```bash
# Run mypy to see all type errors
mypy app/

# Install type stubs if needed
pip install types-requests
```

## Getting Help

- **Questions**: Open a discussion on GitHub
- **Bugs**: Open an issue with reproduction steps
- **Security Issues**: Email security@resilo.io (do not open public issue)
- **Chat**: Join our Discord community

## Recognition

Contributors will be:
- Added to CONTRIBUTORS.md
- Mentioned in release notes
- Recognized in project README

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to Resilo! 🎉**
