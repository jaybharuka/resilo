# SOC2 Type I — Evidence Package

**Product:** Resilo AIOps Platform
**Evidence Period:** Phase 4 (2026-Q2)
**Prepared By:** Engineering / Security Team
**Last Updated:** 2026-04-07

---

## Overview

This folder contains the SOC2 Type I control evidence for the Resilo platform. SOC2 Type I asserts that controls are **designed and implemented** as of a specific point in time.

## Evidence Documents

| File | Controls Covered |
|---|---|
| [access_control.md](access_control.md) | CC6.1, CC6.2, CC6.3, CC6.4, CC6.5, CC6.6, CC6.7, CC6.8 |
| [encryption.md](encryption.md) | CC9.1, CC9.2, CC9.3, CC9.4, CC9.5 |
| [logging.md](logging.md) | CC7.1, CC7.2, CC7.3, CC7.4, CC7.5 |
| [incident_response.md](incident_response.md) | CC9.6, CC2.2, CC4.1 |
| [key_rotation.md](key_rotation.md) | CC9.3, CC3.3 |

**Total controls documented: 21**

## Control Summary

| # | Control | Status |
|---|---|---|
| CC6.1 | Logical Access Security Measures | Implemented |
| CC6.2 | User Registration and Deprovisioning | Implemented |
| CC6.3 | Role-Based Access Control | Implemented |
| CC6.4 | Network Access Controls | Implemented |
| CC6.5 | Authentication Credential Management | Implemented |
| CC6.6 | Logical Access Restrictions (RLS) | Implemented |
| CC6.7 | Privileged Access Management | Implemented |
| CC6.8 | Prevention of Unauthorized Access | Implemented |
| CC7.1 | Detection of Security Events | Implemented |
| CC7.2 | Monitoring of System Components | Implemented |
| CC7.3 | Audit Log Integrity | Implemented |
| CC7.4 | Incident Detection and Response Logging | Implemented |
| CC7.5 | Log Protection from Unauthorized Access | Implemented |
| CC9.1 | Data Encryption at Rest | Implemented |
| CC9.2 | Data Encryption in Transit | Implemented |
| CC9.3 | Cryptographic Key Management (×2) | Implemented |
| CC9.4 | Encryption Algorithm Standards | Implemented |
| CC9.5 | Secret Detection and Prevention | Implemented |
| CC9.6 | Incident Response Procedures | Implemented |
| CC2.2 | Communication of Security Incidents | Implemented |
| CC4.1 | Monitoring and Continuous Improvement | Implemented |
| CC3.3 | Risk Assessment for Key Compromise | Implemented |

## Automated Test Evidence

The following test suites provide automated evidence of control effectiveness:

```bash
pytest tests/test_rls_isolation.py -v      # CC6.6 — RLS enforcement
pytest tests/test_sso_flow.py -v           # CC6.2 — SSO user provisioning
pytest tests/test_pricing_limits.py -v     # CC6.3 — Plan-gated access
pytest tests/test_deployment_health.py -v  # CC7.2 — Health monitoring
pytest tests/test_auth.py -v               # CC6.1, CC6.5, CC6.8
```

Run all compliance-related tests:
```bash
pytest tests/test_rls_isolation.py tests/test_sso_flow.py tests/test_pricing_limits.py tests/test_deployment_health.py tests/test_auth.py -v --tb=short
```

## Auditor Notes

- All controls are enforced at the **API / database level** — no frontend-only gating
- RLS policies survive direct DB access (no application-layer bypass possible)
- Audit logs are **append-only** — no UPDATE/DELETE permissions for app user
- Secret rotation is **scripted and documented** — no manual key handling required
