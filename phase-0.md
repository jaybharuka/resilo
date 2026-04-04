# 🔒 Resilo — Phase 0 (Security & Emergency)

## 🎯 Objective

Eliminate all critical security vulnerabilities from the codebase before any further development.

> ⚠️ Phase 0 is **non-negotiable**. No new features should be built until ALL items are completed and verified.

---

## 🚨 Why This Phase Matters

The repository is publicly accessible. Existing vulnerabilities can be exploited immediately, including:

* Credential leaks
* SQL injection
* Authentication bypass risks
* Misconfigured CORS

This phase ensures:

* No secrets are exposed
* No active attack vectors exist
* Authentication is secure and stable

---

## 📦 Scope (7 Issues)

### 1. Remove Sensitive Files

* Remove `audit.txt` from repo and git history
* This file exposes vulnerabilities and file structure

### 2. Remove Hardcoded Credentials

* Eliminate `admin123` or any hardcoded password
* Move credentials to `.env`
* Add strict startup validation (fail if missing)

### 3. Fix JWT Secret Handling

* Remove dynamic/fallback JWT secret generation
* Load from environment variable only
* App must crash if JWT secret is missing

### 4. Implement Account Lockout

* Add fields:

  * `failed_attempts`
  * `locked_until`
* Lock account after 5 failed attempts
* Lock duration: 15 minutes
* Return HTTP 403 when locked

### 5. Fix SQL Injection

* Remove raw SQL using string interpolation (f-strings)
* Replace with parameterized queries

### 6. Add Input Validation

* Use Pydantic models for request validation
* Prevent malformed or oversized inputs

### 7. Fix CORS Configuration

* Remove wildcard `*`
* Use explicit allowlist from environment variable

---

## 🧱 Implementation Rules

* ❌ No fallback values for secrets
* ❌ No hardcoded credentials anywhere
* ❌ No partial fixes
* ✅ Fail fast on missing configuration
* ✅ All changes must be verifiable via command-line checks

---

## 🛠️ Environment Variables Required

```
ADMIN_PASSWORD=
JWT_SECRET_KEY=
ALLOWED_ORIGINS=
```

---

## ✅ Verification Checklist

Run these commands after implementation:

### 1. No hardcoded passwords

```
grep -rn "admin123" .
```

Expected: no output

### 2. No raw SQL injection patterns

```
grep -rn "execute(f" .
```

Expected: no output

### 3. JWT secret enforcement

* Remove JWT_SECRET_KEY from `.env`
* Start app → must crash

### 4. Account lockout

* Attempt 5 failed logins
* 6th attempt → HTTP 403

### 5. CORS validation

* Ensure no `*` in allowed origins

### 6. audit.txt removal

* File should not exist
* Not present in git history

---

## 🧠 Execution Strategy

Work sequentially:

1. Remove audit.txt
2. Fix credentials
3. Fix JWT secret
4. Add lockout
5. Fix SQL injection
6. Add validation
7. Fix CORS

---

## 🚫 Do NOT Proceed to Phase 1 Until:

* All checklist items pass
* No vulnerabilities remain
* App behaves securely under failure conditions

---

## 💡 Notes

* Treat this like production security, not a college assignment
* Small shortcuts here will cause major failures later
* Stability > speed

---

## ✅ Outcome of Phase 0

* Secure authentication system
* No exposed secrets
* No injection vulnerabilities
* Controlled API access

Once this is complete, the system is safe to build on.
