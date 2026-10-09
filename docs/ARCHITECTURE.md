# Architecture

A multi-tenant FastAPI back-office assistant for small medical and dental practices: conflict-free scheduling, billing-code explanation with a denial-risk flag, and non-clinical intake triage. Every AI suggestion is logged and waits for a human decision.

## System context

```
 Practice staff
      |  X-API-Key  (one key per practice = one tenant)
      v
 +----------------------------- FastAPI -----------------------------+
 | practices | patients | appointments | billing | triage | audit      |
 +-------------------------------+------------------------------------+
                                 |
     +---------------------------+---------------------------+
     v                           v                           v
 services/scheduling      services/billing, triage     services/audit
 (interval conflicts,     (heuristic flags +           (every AI action,
  slot suggestion)         retrieval grounding)         human_status=pending)
     |                           |
     v                           v
 SQL (SQLite | Postgres)     Qdrant
 practices, api_keys,        - domain_knowledge  (billing/triage reference, no PHI)
 patients (encrypted),       - patient_memory    (per tenant + patient, encrypted payload)
 appointments, billing,
 audit_log
```

## Components

| Module | Responsibility |
|---|---|
| `app/core/security.py` | `X-API-Key` -> SHA-256 hash lookup -> exactly one `Practice`; revoked keys rejected. Every handler depends on `get_current_practice` |
| `app/core/crypto.py` | Fernet field encryption for patient identifiers and memory text; key from config, never stored with data |
| `app/services/scheduling.py` | `find_conflicts` (same practice + provider, half-open intervals, cancelled ignored) and `suggest_available_slots` (walks a window in fixed steps, skipping conflicts) |
| `app/services/billing.py` | Billing-code explanation grounded in `domain_knowledge`; transparent signal lists produce a high/medium/low denial-risk flag |
| `app/services/triage.py` | Structured flags -> `emergency` / `urgent` / `routine_soon` / `routine` routing, with a mandatory non-clinical disclaimer on every response |
| `app/services/patient_memory.py` | Qdrant memory scoped by `tenant_id` + `patient_id`; `delete_patient_memory` hard-deletes by filter |
| `app/services/domain_knowledge.py` | Retrieval over the shared reference collection |
| `app/services/audit.py` | `log_ai_action` writes an entry with `actor="ai"` and `human_status="pending"` |
| `app/routers/patients.py` | Create patient (encrypted fields) and the GDPR Art. 17 delete endpoint |

## Request flow (example: suggest slots)

1. Auth dependency resolves the API key to a `Practice`.
2. Router calls `suggest_available_slots` for the practice and provider.
3. Result is returned as a suggestion; **no appointment is created**.
4. The action is written to `audit_log` as `pending`; only an explicit confirm or reject call changes its status.

## Key design decisions

- **Tenant boundary from day one.** Auth resolves to one practice and all queries filter on it, in SQL and in Qdrant payload filters.
- **Human in the loop by construction.** Slot suggestions, billing checks and triage return suggestions and log them as pending. Nothing in the system marks an AI action confirmed on its own. An appointment staff enter directly is created as `confirmed` (typing it in is the confirmation), after a conflict check.
- **Field-level encryption.** Patient name, date of birth, contact info, and memory text are encrypted before they reach storage.
- **Real erasure.** `DELETE /patients/{id}` deletes the SQL row, hard-deletes all vector points for that tenant and patient, and unlinks (nulls `patient_id` on) appointments and billing entries so operational history survives without identity.
- **Transparent heuristics over opaque models.** Triage and denial-risk rules are small, readable lists that staff can inspect and extend. Output vocabulary is routing language, never diagnosis.
- **Two Qdrant collections with different sensitivity.** `domain_knowledge` holds no PHI; `patient_memory` is filtered by tenant and patient on every read and delete.
- **SQLite for tests and local dev, Postgres for deployment**, behind the same SQLAlchemy models. Datetimes are normalised to UTC because SQLite drops tzinfo.

## Scaling and operational notes

- API tier is stateless; scale it behind a load balancer with Postgres and Qdrant as shared state.
- `find_conflicts` loads the provider's non-cancelled appointments and compares in Python. That is fine for small practices; a SQL overlap predicate or exclusion constraint would be the next step at larger volumes.
- Conflict checking and booking are not wrapped in a lock or constraint, so two simultaneous bookings for the same slot could both pass the check.

## Known limitations (from the README and code)

- No key rotation, KMS/HSM, or envelope encryption.
- No audit-log tamper evidence.
- No TLS enforcement, DPIA tooling, breach tooling, or automated retention expiry.
- Single API key per practice; no staff accounts or RBAC.
- The embedding function used for retrieval is a stand-in (see README).
- Do not use with real patient data before these gaps are closed.
