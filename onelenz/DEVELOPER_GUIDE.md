# OneLenz Developer Guide

## Project Structure

```
onelenz/
├── backend/
│   ├── shared/              ← Shared utilities used by ALL services
│   │   ├── db/              ← Database layer (adapter, base model, base repository)
│   │   ├── auth/            ← Auth middleware (get_current_user, JWT, hashing)
│   │   ├── encryption/      ← AES-256-GCM token encryption
│   │   ├── s3/              ← Upload/download for email body + attachments
│   │   ├── email/           ← send_otp_email (mock for dev, SES for prod)
│   │   ├── errors/          ← AppError + centralized error codes
│   │   ├── logging/         ← Structured logging with request context
│   │   └── redis/           ← Redis client for sessions, locks, state
│   ├── services/
│   │   ├── auth-service/    ← Authentication microservice
│   │   │   └── app/
│   │   │       ├── api/routes/     ← FastAPI route handlers
│   │   │       ├── models/         ← SQLAlchemy ORM models
│   │   │       ├── schemas/        ← Pydantic request/response schemas
│   │   │       ├── services/       ← Business logic
│   │   │       └── repositories/   ← Database queries
│   │   ├── email-connector/ ← MS365 email ingestion microservice
│   │   │   └── app/
│   │   │       ├── api/routes/     ← FastAPI route handlers
│   │   │       ├── models/         ← SQLAlchemy ORM models
│   │   │       ├── providers/      ← OAuth + Graph API provider classes
│   │   │       ├── services/       ← Business logic (sync, OAuth, storage)
│   │   │       ├── repositories/   ← Database queries
│   │   │       └── workers/        ← Celery tasks + beat scheduler
│   │   └── content-engine/  ← Knowledge Hub content processing
│   │       └── app/
│   └── migrations/          ← SQL migration files (run in order)
├── ui/
│   └── src/
│       ├── app/             ← App-level setup (router, providers)
│       ├── features/        ← Feature modules (auth, dashboard, etc.)
│       └── shared/          ← Reusable UI components, hooks, utils
└── backend/.env.example     ← Single env config for all services
```

---

## Backend Guidelines

### Layer Responsibilities

Every API request flows through 4 layers. **Never skip a layer.**

```
Route → Service → Repository → DB/Redis
```

| Layer | Location | Responsibility | Does NOT do |
|-------|----------|---------------|-------------|
| **Route** | `api/routes/` | Parse request, call service, return response | Business logic, DB queries |
| **Service** | `services/` | Business logic, validation, orchestration | Direct DB queries, HTTP response formatting |
| **Repository** | `repositories/` | DB queries only, return data | Business logic, validation |
| **Shared DB** | `backend/shared/db/` | Connection pool, base classes | Service-specific logic |

### Using Shared DB Layer

#### Base Model (`shared/db/base_model.py`)

All models inherit from `Base` (DeclarativeBase).

Every entity table must define four audit columns with the table's column prefix:

```
{prefix}_created_by   (VARCHAR 100)
{prefix}_created_on   (TIMESTAMPTZ, default=now)
{prefix}_modified_by  (VARCHAR 100)
{prefix}_modified_on  (TIMESTAMPTZ)
```

Example for `user_master` (prefix `usm`):
```python
usm_created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
usm_created_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=...)
usm_modified_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
usm_modified_on: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

Tables without audit needs (like `user_authentication_history`) inherit `Base` only, no audit columns.

#### DB Adapter (`shared/db/adapter.py`)

- Provides `get_session()` — use this as a FastAPI dependency to get an async DB session
- Session auto-commits on success, auto-rollbacks on exception
- Connection pool is configured via env vars (see Configuration section)
- **Do NOT create your own engine or session factory**

#### Base Repository (`shared/db/base_repository.py`)

- Will provide generic CRUD: `get_by_id`, `create`, `update`, `delete`, `list`
- Service-specific repositories extend this with custom queries
- **All DB queries go through repositories — never write raw queries in services or routes**

### Using Shared Encryption (`shared/encryption/`)

AES-256-GCM encryption for sensitive tokens (e.g., OAuth access/refresh tokens stored in DB). Key is sourced from `TOKEN_ENCRYPTION_KEY` env var.

- `encrypt_token(plaintext)` → returns encrypted string
- `decrypt_token(ciphertext)` → returns plaintext
- Tokens are encrypted before writing to JSONB columns and decrypted only when making external API calls
- **Never log decrypted tokens**

### Using Shared S3 (`shared/s3/`)

Upload/download utilities for email body JSON and binary attachments.

- `store_email_body(entity_id, message_id, body_data, date)` → uploads JSON to S3, returns S3 key
- `store_attachment(entity_id, message_id, att_id, filename, content, content_type, date)` → uploads binary to S3, returns S3 key
- Bucket configured via `S3_BUCKET_EMAILS` env var
- IAM role on EKS pods for access — no hardcoded credentials

### Using Shared Email (`shared/email/`)

Email sending utility for OTP and notification emails.

- `send_otp_email(to_address, otp_code)` → sends OTP email
- **dev**: mock provider (logs email content instead of sending)
- **prod**: AWS SES
- Provider selected via `EMAIL_PROVIDER` env var

### Using Shared Logger (`shared/logging/`)

Central structured logging with automatic request context. **Do NOT use `print()` or configure `logging` yourself.**

#### Setup (once per service, in `main.py`):
```
from shared.logging import setup_logging, RequestLoggingMiddleware

setup_logging("auth-service")
app.add_middleware(RequestLoggingMiddleware, service_name="auth-service")
```

#### Usage (in any file):
```
from shared.logging import get_logger

logger = get_logger(__name__)

# Basic logging
logger.info("User logged in")
logger.warning("OTP expired")
logger.error("Failed to connect to Redis", exc_info=True)

# Extra fields — prefix with x_ to attach custom data
logger.info("Deal updated", extra={"x_deal_id": "123", "x_stage": "closed"})
```

#### What gets attached automatically:
Every log line includes these fields without you passing them:
- `timestamp` — ISO 8601 UTC
- `level` — DEBUG/INFO/WARNING/ERROR
- `service` — service name (auth-service, crm-service, etc.)
- `request_id` — unique per request, also returned in `X-Request-ID` response header
- `user_id` — set after auth middleware validates the token
- `endpoint` — e.g. `POST /auth/login`

#### Setting user context after auth:
After the auth middleware validates a token, update the context so all subsequent logs include user_id:
```
from shared.logging import request_context

ctx = request_context()
ctx.user_id = user.user_id
ctx.session_id = user.session_id
```

#### Log output:
- **dev** — colored human-readable format for terminal
- **staging/prod** — structured JSON, ready for CloudWatch/ELK/Datadog

#### Rules:
- Never log passwords, tokens, PII, or full request bodies
- Use `exc_info=True` when logging errors to include the stack trace
- Use `x_` prefix for extra fields to avoid collisions with standard log fields
- Log at the **service layer**, not in routes or repositories

---

### Do's and Don'ts — Backend

#### Do

- Keep route handlers thin — parse request, call service, return response
- Put all business logic in the service layer
- Put all DB queries in the repository layer
- Use `get_session()` dependency for DB access
- Use TIMESTAMPTZ for all timestamp columns
- Use UUID for primary keys on entity tables
- Use readable strings (ADMIN, VIEWER) for lookup/reference table IDs
- Hash passwords with Argon2id — never store plaintext
- Return consistent error responses (see Error Schema below)
- Use environment variables for all configuration — never hardcode
- Write async code — all DB and Redis calls must be awaited

#### Don't

- Don't write DB queries in route handlers or services
- Don't create new DB engine/session instances — use the shared adapter
- Don't import models from one service into another — services are independent
- Don't store secrets in code or commit `.env` files
- Don't use TIMESTAMP — always use TIMESTAMPTZ
- Don't call one microservice's internal methods from another — use HTTP APIs
- Don't put shared logic in a service folder — if two services need it, it goes in `backend/shared/`
- Don't skip the service layer even for simple CRUD — routes call services, services call repositories

---

### Standard Middleware (required in every service's `main.py`)

Every FastAPI service must include these middleware in `main.py`:

| Middleware | Purpose |
|-----------|---------|
| **GZipMiddleware** | Compresses responses > 500 bytes — reduces payload size |
| **CORSMiddleware** | Allows frontend to call backend APIs cross-origin |
| **RequestID** | Adds a unique request ID to every request for tracing across logs |

#### Registration order matters — add them in this order:
1. CORS (outermost — must run first to handle preflight)
2. GZip (compresses the final response)
3. RequestID (innermost — generates ID before any logic runs)

#### CORS allowed origins:
- `dev`: `http://localhost:3000`
- `staging`: staging domain
- `prod`: production domain

Configured via `CORS_ORIGINS` env var (comma-separated).

---

### Adding a New Service

1. Create `backend/services/{service-name}/app/` with the standard structure:
   ```
   app/
   ├── api/routes/
   ├── models/
   ├── schemas/
   ├── services/
   ├── repositories/
   ├── config.py
   └── main.py
   ```
2. Models import from `shared.db.base_model` (Base). Define audit columns explicitly on the model with the table's column prefix (e.g., `inc_created_by`, `inc_created_on` for integration_config).
3. DB sessions use `shared.db.adapter.get_session`
4. Add service-specific env vars to `backend/.env.example` under a new section
5. Add a new SQL migration file: `backend/migrations/002_{description}.sql`
6. Create a Dockerfile that copies `backend/shared/` + service code
7. If the service has background tasks, set up a Celery worker with `celery_app.py` (broker config, beat schedule) and task modules. Use prefork pool. See `email-connector/app/workers/` for reference.

---

### Adding a New DB Table

1. Add the SQL to a new migration file: `backend/migrations/NNN_{description}.sql`
   - Use lowercase table and column names
   - Use TIMESTAMPTZ for timestamps
   - Use UUID for entity primary keys, readable strings for lookup table IDs
   - Include indexes on FKs and frequently filtered columns
   - Include audit columns (created_by, created_on, modified_by, modified_on)
2. Create the SQLAlchemy model in the relevant service's `models/` folder
3. Export the model in `models/__init__.py`
4. Migration files are numbered sequentially and run in order

---

### Error Response Format

All APIs return errors in this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description"
  }
}
```

All error codes are centralized in `backend/shared/errors/codes.py`. Use `AppError` from `shared/errors` to raise errors:

```
from shared.errors import AppError
from shared.errors.codes import EMAIL_ALREADY_EXISTS

raise AppError(EMAIL_ALREADY_EXISTS)

# With custom detail message:
raise AppError(ACCOUNT_LOCKED, detail="Account locked. Try again after 2026-03-18T10:30:00Z")
```

Don't invent inline error codes — add new ones to `codes.py` first.

---

### Configuration

All env vars live in `backend/.env.example`. One file for all services.

| Section | Variables |
|---------|-----------|
| Database | DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE, DB_ECHO |
| Redis | REDIS_URL, ENVIRONMENT |
| JWT | JWT_PRIVATE_KEY_PATH, JWT_PUBLIC_KEY_PATH, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_MINUTES |
| Auth Service | LOCKOUT_THRESHOLD, LOCKOUT_DURATION_MINUTES |
| Auth Email/OTP | EMAIL_PROVIDER, OTP_EXPIRY_MINUTES |
| Email Connector | MS_OAUTH_CLIENT_ID, MS_OAUTH_CLIENT_SECRET, MS_OAUTH_REDIRECT_URI, TOKEN_ENCRYPTION_KEY, S3_BUCKET_EMAILS, CELERY_BROKER_URL, SYNC_FREQUENCY_MINUTES, INITIAL_FETCH_DAYS, BEAT_ENABLED |

When adding a new service, add its config vars under a new commented section.

---

## Frontend Guidelines

### Feature-Based Structure

Every feature gets its own folder under `ui/src/features/`:

```
features/{feature-name}/
├── components/    ← UI components specific to this feature
├── hooks/         ← Custom hooks for this feature
├── services/      ← API calls for this feature
└── types/         ← TypeScript interfaces
```

Shared/reusable code goes in `ui/src/shared/`:

```
shared/
├── components/    ← Buttons, inputs, modals — used across features
├── hooks/         ← useAuth, useFetch — used across features
└── utils/         ← Formatters, validators — used across features
```

### Do's and Don'ts — Frontend

#### Do

- Keep API calls in `features/{name}/services/` — components don't call APIs directly
- Store auth tokens in memory (React context) — never in localStorage
- Use the Axios interceptor for auto token refresh — don't handle 401 in every component
- Use TypeScript interfaces for all API request/response types
- Use the `AuthGuard` component for protected routes
- Keep components small — if a component is doing too much, split it

#### Don't

- Don't store tokens in localStorage or sessionStorage (XSS vulnerability)
- Don't write API calls directly in components — always go through a service file
- Don't put feature-specific components in `shared/` — only truly reusable components belong there
- Don't handle auth token refresh in individual components — the Axios interceptor handles this globally
- Don't duplicate types — if the backend schema changes, update `types/` in one place

### Auth Flow (for frontend devs)

1. **Login/Signup** → call auth API → store tokens in AuthContext
2. **Every API call** → Axios interceptor attaches `Authorization: Bearer {token}` header
3. **401 response** → interceptor calls `/auth/refresh` silently → retries original request
4. **Refresh fails** → clear context → redirect to `/login`
5. **Logout** → call `/auth/logout` → clear context → redirect to `/login`

The developer does NOT need to think about tokens when building features. The interceptor and AuthContext handle everything. Just use `useAuth()` hook to check if user is authenticated and get user info.

### Adding a New Feature

1. Create `ui/src/features/{feature-name}/` with the standard structure
2. Define TypeScript types in `types/`
3. Create API service functions in `services/`
4. Build components in `components/`
5. Add route to the app router
6. Wrap with `AuthGuard` if the feature requires login

---

## Git Conventions

### Branch Naming
```
feature/{service}/{short-description}    — e.g. feature/auth/login-api
fix/{service}/{short-description}        — e.g. fix/auth/lockout-reset
```

### Migration File Naming
```
NNN_{description}.sql
001_create_auth_tables.sql
002_create_shared_tables.sql
003_add_permission_tables.sql
```

Always increment the number. Never modify a migration that's been applied to any environment — create a new one instead.

---

## Coding Standards — Backend (Python)

### Error Handling

- **Global exception handlers** in `main.py` catch all errors — routes do NOT have try/except
- Services raise `AppError(ERROR_CODE)` from `shared/errors` — global handler formats the JSON response
- Repositories let DB exceptions bubble up — never catch in repositories
- Never use bare `except:` — always catch specific exceptions
- All error codes are defined in `shared/errors/codes.py` — never use inline error strings

```
Pattern:
  Route      → calls service, returns result (no try/except)
  Service    → raises AppError(ERROR_CODE) on business errors
  Repository → no try/except, lets DB errors bubble up
  main.py    → global handlers catch AppError → JSON, ValidationError → 400, Exception → 500
```

Three global handlers in every service's `main.py`:
1. `@app.exception_handler(AppError)` — business errors (401, 409, 423, etc.)
2. `@app.exception_handler(RequestValidationError)` — missing/invalid fields → 400
3. `@app.exception_handler(Exception)` — unexpected errors → 500, logged with stack trace

### Logging

- Use Python's `logging` module — never use `print()`
- Log at appropriate levels:
  - `ERROR` — something failed, needs attention
  - `WARNING` — something unexpected but recoverable
  - `INFO` — significant business events (user logged in, session expired)
  - `DEBUG` — detailed flow for debugging (query params, intermediate values)
- Always include context: user_id, session_id, endpoint name
- Never log sensitive data: passwords, tokens, PII

### Comments

- Don't comment obvious code — the code should be self-explanatory
- Do comment **why**, not **what** — explain business rules, edge cases, non-obvious decisions
- Add docstrings to service methods explaining the business logic
- No commented-out code — delete it, git has history

### Naming Conventions

| What | Convention | Example |
|------|-----------|---------|
| Files | snake_case | `auth_service.py` |
| Classes | PascalCase | `UserMaster` |
| Functions/methods | snake_case | `find_by_email()` |
| Variables | snake_case | `user_id` |
| Constants | UPPER_SNAKE | `LOCKOUT_THRESHOLD` |
| DB tables | snake_case | `user_master` |
| DB columns | snake_case with table prefix | `usm_user_id` |
| API endpoints | lowercase with hyphens | `/auth/request-otp` |

### Code Style

- Max line length: 100 characters
- Use type hints on all function signatures
- Use Pydantic models for request/response validation — not manual checks
- Use async/await for all I/O operations (DB, Redis, HTTP calls)
- One class per file for models and schemas
- Imports order: stdlib → third-party → local (separated by blank lines)

---

## Coding Standards — Frontend (TypeScript/React)

### Error Handling

- API errors are handled globally by the Axios interceptor (401, 423)
- Feature-specific errors (400, 409) are caught in the service layer and passed to components
- Use error boundaries for unexpected React rendering errors
- Always show user-friendly messages — never expose raw error codes or stack traces

### Comments

- Same as backend: comment **why**, not **what**
- Add JSDoc to shared hooks and utility functions
- No commented-out JSX — delete it

### Naming Conventions

| What | Convention | Example |
|------|-----------|---------|
| Files (components) | PascalCase.tsx | `LoginForm.tsx` |
| Files (hooks) | camelCase.ts | `useAuth.ts` |
| Files (services) | camelCase.ts | `authApi.ts` |
| Files (types) | camelCase.ts | `auth.types.ts` |
| Components | PascalCase | `LoginForm` |
| Hooks | camelCase with `use` prefix | `useAuth` |
| Functions | camelCase | `handleSubmit` |
| Constants | UPPER_SNAKE | `API_BASE_URL` |
| Interfaces/Types | PascalCase | `LoginRequest` |

### Code Style

- Use functional components only — no class components
- Use TypeScript strict mode
- Define prop types with interfaces, not inline
- Keep components under 150 lines — split if larger
- Colocate styles with components

---

## Git Workflow

### Branch Strategy

```
main          ← production-ready, protected
  └── dev     ← integration branch, protected
       └── feature/auth/login-api    ← your working branch
       └── fix/auth/lockout-reset    ← your working branch
```

- **Never push directly to `main` or `dev`**
- Always create a feature/fix branch from `dev`
- Raise a PR to merge into `dev`
- `dev` → `main` merges are done during releases by maintainers

### Commit Messages

```
{type}: {short description}

Types:
  feat     — new feature
  fix      — bug fix
  refactor — code restructuring, no behavior change
  docs     — documentation only
  test     — adding or updating tests
  chore    — config, dependencies, tooling

Examples:
  feat: add login API with lockout logic
  fix: reset failed login count after lockout expires
  docs: add Redis key design to tech spec
```

- Keep the subject line under 70 characters
- Use imperative mood: "add" not "added", "fix" not "fixes"

### Pre-PR Sanity Checklist

Before raising a PR, verify **all** of the following:

#### Code Quality
- [ ] Code runs locally without errors
- [ ] No `print()` statements — use logging
- [ ] No hardcoded values — use env vars or constants
- [ ] No commented-out code
- [ ] Type hints on all new functions (backend)
- [ ] TypeScript strict mode passes (frontend)

#### Testing
- [ ] Manually tested the happy path
- [ ] Manually tested error scenarios (invalid input, unauthorized, etc.)
- [ ] Existing tests still pass (if test suite exists)

#### API Changes
- [ ] Request/response schema matches TECH_SPEC
- [ ] Error codes and HTTP status codes match TECH_SPEC
- [ ] No breaking changes to existing endpoints without discussion

#### Database
- [ ] New tables/columns have a migration file (not modifying existing migrations)
- [ ] SQLAlchemy model matches the migration SQL
- [ ] Indexes added for FKs and frequently queried columns

#### Security
- [ ] No secrets in code or logs
- [ ] Passwords are hashed, never stored or logged in plaintext
- [ ] Tokens are not logged
- [ ] SQL queries use parameterized inputs (via SQLAlchemy ORM)

#### PR Hygiene
- [ ] Branch is up to date with `dev` (rebase or merge latest dev)
- [ ] PR title follows commit message convention
- [ ] PR description explains **what** and **why**
- [ ] Relevant files only — no unrelated changes
- [ ] Self-reviewed the diff before requesting review
