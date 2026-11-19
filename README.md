# polynomial_commitment_secrete_sharing

**Polynomial Secret Sharing + Proof Verification + REST API + Authentication + RBAC + Automated Testing**

> 中文简介：本项目源自 2025 年海南大学本科毕业设计《基于多项式承诺的可验证秘密分享》。在保留原有研究算法
> （多项式秘密分享、FRI 风格降幂、多点多多项式代数一致性验证）的前提下，重构为分层的 Python 后端研究原型：
> 框架无关的算法核心 `pcss`、FastAPI REST 服务、JWT 认证与 Dealer / Participant 权限控制、SQLite 演示存储，
> 以及 351 个自动化测试。原实现的分析与问题清单见 [`docs/ANALYSIS.md`](docs/ANALYSIS.md)。

> ⚠️ **Research / teaching prototype — not production cryptography.** Read
> [Security Limitations](#11-security-limitations) before using it for anything real.

---

## 1. Project Overview

| Component | What it does |
| --- | --- |
| `pcss/` (algorithm core) | GF(p) arithmetic with p = 2^255 − 19, polynomials, 31-byte UTF-8 chunking, Shamir sharing with degree k − 1, the thesis' batched evaluation-consistency check, FRI-style folding prototype. Standard library only. |
| `app/` (service) | FastAPI REST API, OAuth2 password flow + JWT, RBAC with resource ownership checks, SQLite persistence, unified error handling. |
| `gui/` | Thin Tkinter front-ends calling `pcss` (no algorithm code). |
| `legacy/` | The original thesis code, unchanged (incl. manual polynomial input for research/debugging). |
| `tests/` | 351 pytest cases: math, encoding, permissions, IDOR, end-to-end API flows, restart persistence, log hygiene, layering rules. |

## 2. Cryptographic Workflow

1. **Encoding** – message → UTF-8 → 31-byte chunks (last one right-padded with `\x00`) →
   `int.from_bytes(chunk, "big")`. Since 2^248 < p, every chunk is a field element.
   Metadata: `original_length` (bytes), `chunk_size`, `chunk_count`, `threshold`. An empty message is one all-zero chunk.
2. **Sharing** – for every chunk `s` the system samples, with Python's `secrets` CSPRNG,

   f(x) = s + a₁x + … + a_{k−1}x^{k−1} (mod p), a_{k−1} ≠ 0

   one independent polynomial per chunk. Participant `j` gets `(x_j, [f_1(x_j), …, f_m(x_j)])`, x_j = 1…n.
   Clients cannot choose coefficients or the degree (manual coefficients exist only in `legacy/` and
   `pcss.sharing.split_secret_with_coefficients` for research).
3. **Proof (evaluation consistency)** – with point sets S_i ⊆ T, r_i = interpolant of f_i on S_i, and a challenge y,
   the dealer returns cm_i = f_i(x) and W = Σ yⁱ·((f_i − r_i)/Z_{S_i})(x).
4. **Verification** – `W·Z_T(x) == Σ (cm_i − r_i(x))·yⁱ·Z_{T\S_i}(x) (mod p)`; rejected inputs: S_i ⊄ T, x ∈ T
   (degenerate: any W would pass), y = 0 (would ignore all but one polynomial), wrong sizes, values ∉ GF(p).
5. **Recovery** – ≥ k shares with distinct non-zero x → Lagrange interpolation at 0 per chunk → strip padding
   with `original_length` → UTF-8 decode. Fewer than k shares are refused; extra shares are checked for consistency.

`chunk_count` (from message length), `n` (number of participants) and `k` (threshold) are independent parameters.

FRI-style folding (`pcss/fri.py`) halves the degree and changes the constant term, so it would break the
threshold; it is kept as a stand-alone research prototype and is **not** applied to sharing polynomials.

## 3. System Architecture

```
HTTP client
   │  JSON / OAuth2 form
   ▼
app/api        routers, Pydantic schemas (app/schemas), auth dependency, error mapping   ← FastAPI only here
   │  Actor + plain Python values
   ▼
app/services   sharing / verification / recovery workflows ── app/security/authorization (RBAC policy)
   │                                                     └── app/security/{passwords,authentication}
   ├──────────► app/storage  SQLAlchemy models + Repository (SQLite)
   ▼
pcss           field · polynomial · encoding · sharing · commitment · fri · vss   ← no FastAPI/HTTP/JWT/DB/Tkinter
   ▲
gui (Tkinter)  calls pcss directly
```

Layering is enforced by `tests/test_architecture.py` (AST import checks).

```
├── pcss/                     algorithm core (stdlib only)
│   ├── config.py             FIELD_MODULUS = 2**255 - 19, CHUNK_SIZE = 31, limits
│   ├── field.py  polynomial.py  encoding.py  sharing.py  commitment.py  fri.py  vss.py  errors.py
├── app/
│   ├── main.py               create_app() factory (uvicorn --factory)
│   ├── config.py             Settings from environment variables
│   ├── cli.py                init-db / create-user / seed-demo
│   ├── errors.py             401/403/404/409/422 application errors
│   ├── api/                  auth.py sharing.py verification.py recovery.py deps.py errors.py
│   ├── schemas/              auth.py sharing.py verification.py recovery.py common.py
│   ├── services/             auth_service.py sharing_service.py verification_service.py recovery_service.py
│   ├── security/             passwords.py (scrypt) authentication.py (JWT) authorization.py (RBAC)
│   └── storage/              database.py models.py repository.py
├── gui/                      dealer_app.py recovery_app.py parsing.py
├── legacy/                   original Tkinter thesis code (unchanged)
├── examples/                 demo.py (core) api_walkthrough.py (API, in-process)
├── tests/                    see §10
└── docs/ANALYSIS.md          analysis of the original code and protocol findings
```

### Data ownership (SQLite)

| Table | Content | Who can read it through the API |
| --- | --- | --- |
| `users` | id, scrypt hash, role, active | own id/role (`/auth/me`) |
| `sharing_tasks` | dealer_id, k, n, chunk metadata, S_i, T, status | task dealer + recipients |
| `shares` | one row per (task, recipient): x, values | **only that recipient** (`/shares/me`) |
| `proofs` | x, y, cm, W for one recipient | returned to the dealer at creation; verifiable by id by the dealer and that recipient |
| `task_secrets` | secret polynomials f_i | **nobody** (used internally for proof generation) |
| `task_verification_keys` | r_i | **nobody** (used internally for verification, see §11) |

The plaintext message is never stored; logs contain only ids, sizes and outcomes.

## 4. User Roles

* **Dealer** – creates sharing tasks, distributes shares, generates proofs, verifies, recovers. Can hold a share
  only if they listed themselves as a recipient; no share is generated for them otherwise.
* **Participant** – reads their own share, verifies proofs, recovers with shares they collected.

Roles are assigned by the administrator with the CLI. There is no self-registration endpoint, the role is
never read from tokens or request bodies, and it is re-loaded from the database on every request.

## 5. Permission Matrix

Defined once in `app/security/authorization.py` (`POLICY`) and enforced in the service layer.

| Operation | Dealer | Participant |
| --- | --- | --- |
| Create sharing | Allow | Deny (403) |
| Distribute shares | Allow – **own tasks only** | Deny (403) |
| View own share | Allow – only if a recipient | Allow – only if a recipient |
| View other users' shares | Deny (no such endpoint) | Deny (no such endpoint) |
| Generate proof | Allow – own tasks only | Deny (403) |
| Verify proof | Allow – own tasks or as recipient | Allow – tasks they belong to |
| Recover secret | Allow – own tasks or as recipient | Allow – tasks they belong to |

Callers unrelated to a task get **404** (existence hidden: dealer B cannot even confirm dealer A's task id);
members lacking a permission get **403** (e.g. a participant calling `/proofs`, or dealer B listed as a
recipient of dealer A's task trying to distribute it).

## 6. Authentication

* OAuth2 password flow: `POST /api/v1/auth/login` with form fields `username`, `password`.
* Passwords: `hashlib.scrypt` (n = 2^14, r = 8, p = 1, 16-byte salt), constant-time comparison, dummy
  hash for unknown users to reduce timing-based user enumeration.
* Access token: JWT HS256 (PyJWT) with `sub`, `iat`, `nbf`, `exp`, `iss`, `type="access"`; default lifetime
  30 min. Signature, expiry, issuer, type and the user's existence/active flag are checked on every request;
  `alg=none` and foreign keys are rejected.
* Configuration via environment: `PCSS_JWT_SECRET` (required, ≥ 32 chars), `PCSS_DATABASE_URL`
  (default `sqlite:///./pcss_demo.db`), `PCSS_ACCESS_TOKEN_EXPIRE_MINUTES`. No secrets are committed.

## 7. API Documentation

Interactive docs: `http://127.0.0.1:8000/docs` (Swagger UI) once the server is running.
Field elements (up to 255 bits) are sent as **decimal strings**; share x-coordinates are JSON integers.

| Method & path | Who | Purpose | Success |
| --- | --- | --- | --- |
| `POST /api/v1/auth/login` | anyone | form login → JWT | 200 |
| `GET /api/v1/auth/me` | authenticated | id + role (from DB) | 200 |
| `POST /api/v1/sharing` | dealer | `{message, threshold, participant_ids}` → task metadata (no shares) | 201 |
| `GET /api/v1/sharing/{id}` | task members | public task metadata | 200 |
| `POST /api/v1/sharing/{id}/distribute` | task dealer | `created → distributed`; repeat → 409, shares never regenerated | 200 |
| `GET /api/v1/sharing/{id}/shares/me` | recipients | caller's own share (409 before distribution) | 200 |
| `POST /api/v1/sharing/{id}/proofs` | task dealer | `{participant_id, challenge?}` → proof at that recipient's x | 201 |
| `POST /api/v1/sharing/{id}/verify` | task members | `{proof_id}` **or** `{proof: {x, challenge, commitments, witness}}` | 200 (`verified` true/false) |
| `POST /api/v1/sharing/{id}/recover` | task members | `{shares: [{x, values}]}` (≥ k, submitted by caller) | 200 |
| `GET /health` | anyone | liveness | 200 |

Verification responses differ by role (same mathematical result):

```json
// task dealer
{"verified": true, "details": {"left_value": "1049…", "right_value": "1049…"}}
// participant
{"verified": true, "message": "Verification successful"}
```

Errors always have the form `{"error": {"code": "...", "message": "...", "details": [...]?}}`:

| Situation | Status | `code` |
| --- | --- | --- |
| missing / invalid / expired token | 401 | `not_authenticated` |
| role or task permission missing | 403 | `permission_denied` |
| task / proof not found, or caller not a member | 404 | `not_found` |
| repeated distribution, share/proof before distribution | 409 | `conflict` |
| schema violation (no input echoed back) | 422 | `validation_error` |
| invalid parameters (k, n, x ∈ T, y = 0, out-of-field value …) | 422 | `invalid_input` / `invalid_request` |
| fewer than k shares | 422 | `insufficient_shares` |
| redundant shares disagree / decoded bytes invalid | 422 | `inconsistent_shares` / `decoding_failed` |
| proof does not satisfy the equation | 200 | `verified: false` |
| unexpected server error (no traceback) | 500 | `internal_error` |

## 8. Quick Start

Python 3.9+ (tested on 3.9 and 3.13).

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

export PCSS_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
# PowerShell: $env:PCSS_JWT_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"

python -m app.cli seed-demo          # dealer_a, dealer_b, user_001..user_005; random passwords printed once
python -m app.cli create-user alice --role participant   # prompts for a password
uvicorn app.main:create_app --factory --reload            # http://127.0.0.1:8000/docs
```

Without a server: `python examples/api_walkthrough.py` runs the whole flow in-process,
`python examples/demo.py` shows the core library, `python -m gui.dealer_app` / `python -m gui.recovery_app`
start the Tkinter GUIs.

## 9. Example Requests

```bash
API=http://127.0.0.1:8000/api/v1
TOKEN=$(curl -s -X POST $API/auth/login -d "username=dealer_a&password=<printed password>" | jq -r .access_token)

# Dealer: create a 3-of-5 sharing and distribute it
SID=$(curl -s -X POST $API/sharing -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"message":"Hello World","threshold":3,"participant_ids":["user_001","user_002","user_003","user_004","user_005"]}' \
      | jq -r .sharing_id)
curl -s -X POST $API/sharing/$SID/distribute -H "Authorization: Bearer $TOKEN"

# Participant: own share
U1=$(curl -s -X POST $API/auth/login -d "username=user_001&password=<...>" | jq -r .access_token)
curl -s $API/sharing/$SID/shares/me -H "Authorization: Bearer $U1"
# -> {"sharing_id":"…","participant_id":"user_001","x":1,"values":["4332…"],"threshold":3,…}

# Dealer: proof for user_001; participant verifies it by id
PID=$(curl -s -X POST $API/sharing/$SID/proofs -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"participant_id":"user_001"}' | jq -r .proof_id)
curl -s -X POST $API/sharing/$SID/verify -H "Authorization: Bearer $U1" -H "Content-Type: application/json" \
     -d "{\"proof_id\":\"$PID\"}"
# -> {"verified":true,"message":"Verification successful"}

# Any task member: recover with >= k shares collected out of band
curl -s -X POST $API/sharing/$SID/recover -H "Authorization: Bearer $U1" -H "Content-Type: application/json" \
     -d '{"shares":[{"x":1,"values":["…"]},{"x":2,"values":["…"]},{"x":3,"values":["…"]}]}'
# -> {"message":"Hello World","shares_used":3,"threshold":3,…}
```

## 10. Testing

```bash
python -m pytest                     # 351 tests, ~45 s (scrypt hashing dominates)
```

| File | Focus |
| --- | --- |
| `test_field.py`, `test_polynomial.py` | 255-bit arithmetic, inverses, division, interpolation, coefficient order |
| `test_encoding.py` | 31-byte chunking, UTF-8 (zh/ja/emoji), NUL bytes, empty / 31 / 32+ byte messages |
| `test_sharing.py`, `test_recovery.py` | k ≤ n < p, degree k − 1, CSPRNG use, all k-subsets of 2-of-3 / 3-of-5 / 5-of-10, every (k−1)-subset refused |
| `test_commitment.py`, `test_verification.py` | valid / invalid proofs, degenerate x and y, verifier independence, **leakage findings** |
| `test_fri.py`, `test_vss.py`, `test_legacy_regressions.py` | FRI prototype, workflow, bugs of and equivalence with the legacy code |
| `test_auth.py` | login, 401 cases (expired / forged / `alg=none`), role re-read from DB, no self-registration |
| `test_permissions.py` | permission matrix, dealer A vs dealer B, own-share isolation, **IDOR** attempts |
| `test_api.py` | validation, error format, idempotent distribution, invalid proofs → `verified:false`, recovery errors, 500 handler |
| `test_integration.py` | full 3-of-5 flow, Chinese multi-chunk message, **restart persistence**, **no secrets in logs** |
| `test_architecture.py`, `test_cli.py`, `test_gui_parsing.py` | layering rules, admin CLI, GUI parsing |

All tests use the real algorithms; nothing in the sharing / proof / verification path is mocked.

## 11. Security Limitations

* **Teaching / research prototype.** No security proof; not audited; not constant-time.
* **Not a standard Polynomial Commitment Scheme.** cm_i = f_i(x) are plain evaluations — neither hiding nor
  binding. Anyone knowing r_i can build a passing (cm′, W′) for arbitrary cm′ (pinned by a test). A successful
  verification shows consistency between (cm, W) and the dealer's r_i; it is **not** a proof that a share is valid,
  and the API cannot detect arbitrary malicious shares.
* **Verification parameters leak information (protocol property, documented in `docs/ANALYSIS.md`).** The
  verifier needs no f_i coefficients, but it needs r_i = f_i restricted to S_i, and the witness reveals r_i(x).
  * With the legacy rule 0 ∈ S_i, r_i(0) *is* the secret, and |S_i| proof holders can rebuild it below the threshold.
  * The API therefore uses S_i = T = {p − 1}, keeps r_i server-side and verifies on the server. Each proof handed
    to a participant still reveals one combination of f_i(p − 1) values, so colluding proof holders can need only
    **k − 1** shares (for k = 2 a single participant with enough proofs). Prefer `{"proof_id": …}` verification,
    which keeps W on the server. Fixing this requires a different (hiding) commitment scheme, which is out of scope.
* **Single-chunk messages:** the only weight is y⁰ = 1, so the challenge y has no effect on W.
* **Trusted server.** Verification and recovery run on the server, which holds the secret polynomials;
  JWT + RBAC protect the API, not the cryptographic protocol.
* **Recovery** checks format, counts, distinct issued x-coordinates and (with > k shares) consistency. A modified
  share among exactly k shares is usually caught only by decoding checks — not cryptographically.
* **Storage:** unencrypted local SQLite (secret polynomials, r_i, shares). Do not store real secrets in it.
* **FRI:** a folding prototype only — not the FRI low-degree test protocol, and not used for sharing.
* No rate limiting, token revocation, refresh tokens, TLS termination or audit logging yet.

## Next step: containerisation (suggestions)

* Multi-stage `Dockerfile` on `python:3.12-slim`, non-root user, `pip install -r requirements.txt`, entrypoint
  `uvicorn app.main:create_app --factory --host 0.0.0.0`.
* Inject `PCSS_JWT_SECRET` via Docker secrets / env-file (never baked into the image); mount the SQLite file on a
  volume or switch `PCSS_DATABASE_URL` to PostgreSQL (SQLAlchemy already abstracts it).
* Add a `HEALTHCHECK` on `/health`, run `python -m app.cli init-db` as an init step, and run `pytest` in a CI stage.

## References

* D. Boneh, J. Drake, B. Fisch, A. Gabizon. *Efficient polynomial commitment schemes for multiple points and
  polynomials.* [ePrint 2020/081](https://eprint.iacr.org/2020/081)
