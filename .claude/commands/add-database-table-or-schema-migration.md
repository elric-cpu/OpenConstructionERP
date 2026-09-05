---
name: add-database-table-or-schema-migration
description: Workflow command scaffold for add-database-table-or-schema-migration in OpenConstructionERP.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-database-table-or-schema-migration

Use this workflow when working on **add-database-table-or-schema-migration** in `OpenConstructionERP`.

## Goal

Introduces a new database table or alters schema, including migration scripts, backend models, schemas, services, and API routes.

## Common Files

- `backend/alembic/versions/*.py`
- `backend/app/modules/*/models.py`
- `backend/app/modules/*/schemas.py`
- `backend/app/modules/*/service.py`
- `backend/app/modules/*/router.py`
- `backend/app/modules/*/validators.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Create or update alembic migration script in backend/alembic/versions/
- Update backend models (e.g., models.py)
- Update backend schemas (schemas.py)
- Update backend services (service.py)
- Update backend routers (router.py)

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.