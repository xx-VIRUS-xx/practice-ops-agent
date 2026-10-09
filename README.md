# practice-ops-agent

> System design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

A vertical AI back-office assistant for solo/small medical and dental practices:
scheduling help, billing support (plain-language code explanations + denial-risk
flags), and structured intake/triage routing suggestions. Built for practices too
small to justify enterprise practice-management software.

**This is an MVP.** It suggests; staff confirm. Nothing in this system auto-sends
a claim or auto-confirms an appointment without an explicit human action — see
"Human-in-the-loop & audit log" below.

## Stack, and why

- **FastAPI (Python)** — the product is domain-logic-heavy (scheduling conflict
  rules, billing heuristics, triage routing rules) rather than UI-heavy, and
  Python has the best ecosystem overlap with retrieval/embedding tooling we'll
  want to grow into. FastAPI gives us typed request/response models (Pydantic),
  automatic OpenAPI docs (`/docs`), and async support without extra ceremony.
- **SQLAlchemy + Postgres** (SQLite for local/dev/tests) — structured records
  (appointments, billing entries, audit log) are inherently relational: foreign
  keys, uniqueness, and transactional writes matter more here than schema
  flexibility.
- **Qdrant** — two collections (see below) for retrieval-grounded billing
  explanations/triage routing, and for per-patient memory. Chosen over a bolt-on
  vector extension because MVP scope explicitly calls for it, and a standalone
  vector DB keeps the patient-memory isolation/deletion story architecturally
  explicit (its own collection, its own payload-level tenant filter, its own
  delete-by-filter capability) rather than implicit in a shared table.
- **cryptography (Fernet)** for field-level encryption of patient-identifying
  data, both in Postgres and in Qdrant payloads.

## Project layout

```
app/
  core/        settings, field encryption, API-key auth
  db/          SQLAlchemy session/engine
  models/      ORM models (Practice, ApiKey, Patient, Appointment, BillingEntry, AuditLog)
  schemas/     Pydantic request/response models
  services/    domain logic: scheduling, billing, triage, qdrant clients, audit
  routers/     FastAPI routers (practices, patients, appointments, billing, triage, audit)
  static/      minimal demo form UI, served at /ui
scripts/       seed_domain_knowledge.py — seeds the domain_knowledge collection
tests/         pytest suite (scheduling conflicts + delete-on-request are the two
               specifically required test areas; a few extra tests ride along)
```

## Running locally

### Option A: docker-compose (Qdrant + Postgres + API)

```bash
cp .env.example .env
# Generate a real encryption key and put it in .env as FIELD_ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up --build
```

The API will be at `http://localhost:8000` (`/docs` for interactive API, `/ui`
for the minimal demo form). Then seed the domain-knowledge collection:

```bash
docker compose exec api python -m scripts.seed_domain_knowledge
```

### Option B: local Python, Qdrant only in Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste the key into .env as FIELD_ENCRYPTION_KEY
# for a fully local run without Postgres, set DATABASE_URL=sqlite:///./practice_ops.db in .env

docker compose up -d qdrant   # or run your own Qdrant instance
python -m scripts.seed_domain_knowledge
uvicorn app.main:app --reload
```

### Running tests

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

Tests run fully offline (SQLite in-memory DB, Qdrant calls mocked in the
delete-endpoint tests) — no Docker/Qdrant/Postgres required to run the suite.

## Using the API

1. **Bootstrap a practice** (gated by `ADMIN_BOOTSTRAP_KEY` from `.env`):

   ```bash
   curl -X POST http://localhost:8000/practices \
     -H "X-Bootstrap-Key: dev-admin-bootstrap-key-change-me" \
     -H "Content-Type: application/json" \
     -d '{"name": "Riverside Family Practice"}'
   ```

   Response includes a one-time `api_key` — store it; it's shown only once
   (only its hash is persisted).

2. All other endpoints require `X-API-Key: <that key>`. Every request is
   resolved to exactly one `Practice` (tenant), and all data access is
   filtered by that tenant.

3. See `/docs` for the full interactive schema. Key endpoints:
   - `POST /patients`, `DELETE /patients/{id}` (real GDPR deletion)
   - `POST /appointments`, `POST /appointments/check-conflict`,
     `POST /appointments/suggest-slots`, `POST /appointments/{id}/confirm`
   - `POST /billing/check`, `POST /billing/{id}/confirm`
   - `POST /triage/intake`
   - `GET /audit`, `POST /audit/{id}/decision`

## Human-in-the-loop & audit log

The assistant **suggests**; staff **confirm**. Concretely:

- `POST /appointments/suggest-slots` never creates an appointment — it only
  returns candidate slots. `POST /appointments` (staff-initiated) creates one
  immediately as `confirmed` because a human typing it in *is* the
  confirmation.
- `POST /billing/check` never submits anything; it creates a `draft` billing
  entry with an explanation + denial-risk flag, and a separate
  `POST /billing/{id}/confirm` records staff's explicit approve/reject.
- `POST /triage/intake` returns a routing suggestion only, with a mandatory
  disclaimer — it is never used to auto-schedule or auto-triage without
  staff seeing it first.
- Every AI-suggested action (`suggest_slots`, `billing_check`,
  `triage_routing`, and `patient_data_deletion`) is written to the
  append-only `audit_log` table with `actor="ai"`, a `human_status` of
  `pending`, and `who/what/when`. `POST /audit/{id}/decision` is how a human
  records `confirmed`/`rejected` against that entry.

## GDPR & health-data handling — approach and honest limitations

This product handles special-category data under GDPR Art. 9 (health data)
from day one. The MVP's approach, and where it currently falls short of a
production-grade compliance posture:

**What's implemented:**

- **Per-tenant isolation.** Every patient-scoped SQL table has a mandatory
  `practice_id` (tenant) column, and every query filters on it. Every point
  in the Qdrant `patient_memory` collection carries a mandatory `tenant_id`
  payload field, indexed and enforced as a hard filter on every read/write/
  delete — see `app/services/patient_memory.py`. Cross-tenant access is not
  just "unlikely," it's structurally required to be requested correctly
  (there's no code path that reads or deletes without both `tenant_id` and,
  for patient memory, `patient_id`).
- **Encryption at rest.**
  - Field-level: patient-identifying fields (name, DOB, contact info) are
    encrypted with Fernet (AES-128-CBC + HMAC) before being written to
    Postgres (`app/core/crypto.py`, `app/models/orm.py::Patient`), and
    free-text patient-memory payloads are similarly encrypted before being
    stored in Qdrant (`app/services/patient_memory.py`).
  - Volume-level: `docker-compose.yml` notes that the Postgres and Qdrant
    data volumes should sit on an encrypted disk/filesystem in any real
    deployment (LUKS on Linux, encrypted managed-disk/EBS in cloud). The MVP
    does not itself provision or verify disk encryption — that's an
    infrastructure/deployment responsibility, documented but not automated
    here.
  - The encryption key (`FIELD_ENCRYPTION_KEY`) is read from an environment
    variable. **In production this must come from a real secrets manager /
    KMS with rotation**, not a `.env` file — the MVP does not implement key
    rotation, envelope encryption, or an HSM-backed key.
- **Deletion on request (Art. 17).** `DELETE /patients/{id}` performs a real,
  permanent deletion: the SQL `patients` row is deleted (not soft-deleted or
  flagged inactive), and every matching point in the `patient_memory`
  Qdrant collection for that exact `(tenant_id, patient_id)` is permanently
  removed via `client.delete(...)` with a filter selector — see
  `app/services/patient_memory.py::delete_patient_memory` and
  `app/routers/patients.py::delete_patient`. Appointments and billing
  entries referencing the patient are **unlinked** (their `patient_id` is set
  to `NULL`) rather than cascade-deleted, so a practice's own operational
  history (e.g. "a slot was booked at 9am on this date") survives with no
  link back to patient identity. Full cascading deletion of those rows too
  would be a straightforward follow-up if a practice's policy requires it.
  This deletion action is itself recorded in the audit log.
- **Non-autonomous by design.** See "Human-in-the-loop & audit log" above —
  this reduces the blast radius of any single AI mistake involving health
  data, since nothing is submitted/finalized without a human in the loop.
- **No real PHI in the domain-knowledge collection.** `domain_knowledge` is
  seeded only with generic reference material (coding/billing explanations,
  scheduling policy templates, generic non-patient-specific triage routing
  guidance) — see `scripts/seed_domain_knowledge.py`. It contains no patient
  scenarios, real or synthetic-but-realistic.

**What's explicitly NOT covered by this MVP (do not assume compliance):**

- No formal Data Processing Agreement / Records of Processing Activities
  tooling, no DPIA has been performed, and no Art. 9(2) lawful-basis
  workflow (e.g. explicit consent capture/withdrawal UI) is implemented —
  the MVP assumes the practice itself is the data controller and handles
  consent capture outside this system for now.
- No key rotation, no envelope encryption / KMS integration, no HSM. The
  Fernet key is a single long-lived symmetric key from an env var.
  Compromise of that key compromises all encrypted fields ever written
  with it.
- No audit-log tamper-evidence (e.g. hash chaining / WORM storage) — rows
  are application-level append-only (no UPDATE/DELETE code path touches
  existing audit rows), but the database itself doesn't enforce immutability.
- No breach-notification tooling, no automated data-retention *expiry*
  (only on-request deletion is implemented — there's no scheduled purge of
  data older than N days).
- No encryption-in-transit enforcement is configured here (that's a
  deployment concern — put this behind TLS/HTTPS in any real deployment;
  local dev runs over plain HTTP).
- The embedding function used for retrieval (`app/services/embeddings.py`)
  is a lightweight deterministic hashing vectorizer chosen to keep the MVP's
  dependency footprint small and fully offline — it is not a production-
  quality semantic embedding model. Swapping in a real embedding model/API
  is a drop-in change (implement `embed_text`) but was left out of MVP scope.
- Multi-user staff accounts / RBAC within a practice are out of scope — auth
  is one static API key per practice (anyone with the key acts as "the
  practice"). A real deployment handling multiple staff members with
  different roles would need per-user auth.

**Bottom line:** this MVP takes Art. 9 seriously in its *architecture*
(tenant isolation, field encryption, real deletion, non-autonomous actions,
audit trail) but is not, on its own, a complete GDPR compliance program. Key
management, consent workflows, DPIAs, and infra-level controls (TLS, disk
encryption, backups/retention policy) still need to be put in place by
whoever operates this in production.

## Out of scope (by design, for this MVP)

- Multi-practice enterprise features (roles, org hierarchies, SSO)
- Real insurance/EHR integrations — billing support here is explanatory/
  risk-flagging only, grounded in generic reference material, not a live
  clearinghouse integration
- A polished frontend — `/ui` is a minimal static form for manual testing,
  not a production UI
