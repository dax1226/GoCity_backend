# Alembic migrations

Placeholder. Initialise with:

```bash
alembic init alembic
```

then point `sqlalchemy.url` in `alembic.ini` at the same `DATABASE_URL`
used by `app/core/database.py`, and import `app.models` in `env.py` so
autogenerate sees every table. The current app calls
`Base.metadata.create_all(engine)` at startup; switch that off once
Alembic is the source of truth for schema.
