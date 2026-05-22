"""Top-level repository layer.

Each `*_repository.py` module owns the SQL/SQLAlchemy queries for one
domain. Routers and services depend on these repositories instead of
constructing queries inline so that:

  - Queries can be shared across multiple routers (e.g. user lookup is
    needed by auth, booking, notification flows alike).
  - The persistence layer can be swapped (SQLAlchemy -> async ORM,
    Postgres -> Mongo, etc.) without rewriting business logic.

The current routers still construct queries inline — these stubs are
placeholders for the ongoing migration.
"""
