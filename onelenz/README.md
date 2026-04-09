# OneLenz

Multi-tenant SaaS platform — backend (Python/FastAPI) + frontend (React/TypeScript).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, SQLAlchemy (async) |
| Database | PostgreSQL 17.6 |
| Cache | Redis 8.6 |
| Frontend | React, TypeScript |
| Auth | JWT (RS256), Argon2id |
| Infra | Docker, AWS (RDS, EKS, Secrets Manager) |

## Project Structure

```
backend/
  shared/          — Shared utilities (DB adapter, auth, logging, Redis)
  services/        — Microservices (auth-service, ...)
  migrations/      — SQL migration files
ui/
  src/features/    — Feature modules (auth, ...)
  src/shared/      — Reusable components, hooks, utils
```

## Local Setup

**Prerequisites:** Docker

```bash
# Start Postgres + Redis + auth-service
docker-compose up

# Or run auth-service directly (requires local Postgres + Redis)
cd backend/services/auth-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Environment:** Copy `backend/.env.example` to `backend/.env` and fill in values.

**Database:** Run the migration against your local Postgres:
```bash
psql -U postgres -d onelenz -f backend/migrations/001_create_auth_tables.sql
```

## Docs

- [Developer Guide](DEVELOPER_GUIDE.md) — coding standards, project conventions, PR checklist
- [Auth Service Tech Spec](backend/services/auth-service/TECH_SPEC.md) — API specs, JWT design, Redis keys
