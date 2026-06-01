# Alembic Migrations

This directory contains database migration scripts managed by [Alembic](https://alembic.sqlalchemy.org/).

## Quick reference

```bash
# Generate a new migration after model changes
cd backend
alembic revision --autogenerate -m "add_user_avatar_field"

# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# View migration history
alembic history

# Rollback one step
alembic downgrade -1

# Generate SQL without executing (dry run)
alembic upgrade head --sql
```

## How it works

- `env.py` reads the database URL from `app.core.config.Settings`
- All ORM models in `app.models` are auto-discovered via `Base.metadata`
- On application startup, `init_db()` runs `alembic upgrade head`
- New migrations are auto-detected via `--autogenerate`

## Configuration

- `alembic.ini` — CLI defaults (script location, logging)
- `env.py` — runtime config (async engine, model metadata, URL)

## First run

The initial migration (`d534ad5ae8e0_initial_baseline.py`) creates all tables from the current ORM model state. It serves as the baseline for all future migrations.
