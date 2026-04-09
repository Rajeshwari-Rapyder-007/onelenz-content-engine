# OneLenz — Claude Code Instructions

## Project Overview
OneLenz is a multi-tenant SaaS platform. Backend is Python/FastAPI, frontend is React/TypeScript. Monorepo structure with independent microservices sharing common utilities.

## Architecture
```
Route (api/routes/) → Service (services/) → Repository (repositories/) → DB/Redis
```
Never skip a layer. Routes are thin. Business logic in services. DB queries only in repositories.

## Key Paths
- Shared DB layer: `backend/shared/db/` (adapter.py, base_model.py, base_repository.py)
- Shared logging: `backend/shared/logging/` (get_logger, setup_logging, RequestLoggingMiddleware)
- Auth service: `backend/services/auth-service/app/`
- Auth tech spec: `backend/services/auth-service/TECH_SPEC.md`
- SQL migrations: `backend/migrations/` (numbered, run in order)
- Frontend features: `ui/src/features/`
- Env config: `backend/.env.example`
- Developer guide: `DEVELOPER_GUIDE.md`

## Database Rules
- PostgreSQL 17.6+ with async SQLAlchemy + asyncpg
- Always use TIMESTAMPTZ, never TIMESTAMP
- UUID for entity primary keys
- Readable strings (ADMIN, VIEWER) for lookup/reference table IDs
- Lowercase table and column names
- Column names prefixed with table abbreviation (e.g. usm_user_id for user_master)
- All entity tables include audit columns via AuditMixin (created_by, created_on, modified_by, modified_on)
- New tables require: SQL migration file + SQLAlchemy model + export in __init__.py
- Never modify an existing migration — create a new numbered one

## Backend Code Rules
- Use `from shared.db import get_session` for DB sessions — never create your own engine
- Use `from shared.logging import get_logger` for logging — never use print()
- Use Pydantic models for request/response validation
- Use async/await for all I/O (DB, Redis, HTTP)
- Use Argon2id for password hashing
- JWT signing: RS256 (asymmetric)
- Error response format: `{"error": {"code": "ERROR_CODE", "message": "..."}}`
- Type hints on all function signatures
- Imports order: stdlib → third-party → local (blank line between each)
- Max line length: 100 chars
- One class per file for models and schemas

## Frontend Code Rules
- React with TypeScript strict mode
- Feature-based structure: `ui/src/features/{name}/` with components/, hooks/, services/, types/
- Shared reusable code in `ui/src/shared/`
- Auth tokens stored in memory (React context), NEVER in localStorage
- API calls in service files, never directly in components
- Axios interceptor handles token refresh globally
- Functional components only, no class components
- PascalCase for components/files, camelCase for hooks/services

## Services and Middleware
Every FastAPI service main.py must include (in this order):
1. CORSMiddleware
2. GZipMiddleware
3. RequestLoggingMiddleware (from shared/logging)

## Redis Key Pattern
`{env}:onelenz:{service}:{key_name}` — env is dev/staging/prod

## Git
- Branch from `dev`, PR back to `dev`. Never push directly to main or dev.
- Branch naming: `feature/{service}/{description}` or `fix/{service}/{description}`
- Commit format: `{type}: {description}` (feat, fix, refactor, docs, test, chore)

## What NOT to Do
- Don't import models across services
- Don't put shared logic in a service folder — use backend/shared/
- Don't hardcode config values — use env vars
- Don't log passwords, tokens, or PII
- Don't skip the service layer even for simple CRUD
- Don't use TIMESTAMP — always TIMESTAMPTZ
- Don't create documentation files unless explicitly asked
