```markdown
# OpenConstructionERP Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill provides a comprehensive guide to contributing to the OpenConstructionERP codebase. It covers coding conventions, commit patterns, and the main development workflows for backend and frontend features, database migrations, API endpoints, i18n, testing, releases, and more. The repository is primarily Python-based (no major framework detected), with a TypeScript/React frontend, and follows clear modular and conventional commit practices.

## Coding Conventions

- **File Naming:**  
  Use `snake_case` for Python files and folders.  
  Example:  
  ```
  backend/app/modules/user_management/models.py
  ```

- **Import Style:**  
  Use aliases for imports to clarify usage and avoid name clashes.  
  Example:  
  ```python
  import sqlalchemy as sa
  import openconstructionerp.utils as utils
  ```

- **Export Style:**  
  Use named exports in TypeScript/JavaScript.  
  Example:  
  ```typescript
  export function fetchProjects() { ... }
  export const PROJECT_STATUSES = [...]
  ```

- **Commit Messages:**  
  Follow [Conventional Commits](https://www.conventionalcommits.org/).  
  Prefixes: `feat`, `fix`, `test`, `docs`, `chore`, `i18n`  
  Example:  
  ```
  feat(api): add endpoint for project summary statistics
  fix(user): resolve login redirect bug
  ```

## Workflows

### Release Version Bump
**Trigger:** When releasing a new version of the application.  
**Command:** `/release`

1. Update `CHANGELOG.md` with release notes.
2. Bump version numbers in:
   - `backend/pyproject.toml`
   - `frontend/package.json`
   - `desktop/src-tauri/tauri.conf.json`
3. Update `frontend/src/features/about/Changelog.tsx`.
4. Optionally update `ACKNOWLEDGMENTS.md` for credits.

---

### Add Database Table or Schema Migration
**Trigger:** When adding a new backend feature requiring persistent data.  
**Command:** `/new-table`

1. Create or update Alembic migration script in `backend/alembic/versions/`.
2. Update backend models (e.g., `models.py`).
3. Update backend schemas (`schemas.py`).
4. Update backend services (`service.py`).
5. Update backend routers (`router.py`).
6. Add or update validators, permissions, or events as needed.
7. Add or update backend unit tests.

**Example Alembic Migration:**
```python
def upgrade():
    op.create_table(
        'project',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(128), nullable=False),
    )
```

---

### Add API Endpoint
**Trigger:** When exposing new backend functionality to the frontend or external consumers.  
**Command:** `/new-endpoint`

1. Update or add backend router (`router.py`).
2. Implement logic in backend service (`service.py`).
3. Update or add backend schemas (`schemas.py`).
4. Add or update backend unit tests.
5. Add or update frontend API module (`api.ts`).
6. Add or update frontend feature code and tests.

**Example (Python FastAPI route):**
```python
@router.get("/projects")
def list_projects():
    return service.get_projects()
```

**Example (TypeScript API call):**
```typescript
export async function fetchProjects() {
  return axios.get('/api/projects');
}
```

---

### Feature Development End-to-End
**Trigger:** When building a new user-facing feature or module.  
**Command:** `/feature`

1. Implement backend logic (models, service, router, schemas, migrations if needed).
2. Implement frontend UI and logic (`.tsx` files, stores, hooks).
3. Add or update frontend and backend unit tests.
4. Update or add i18n/locales files for new UI strings.
5. Update documentation or help/catalog files if needed.

---

### Add or Update i18n Strings
**Trigger:** When introducing new UI strings or features that require localization.  
**Command:** `/i18n-update`

1. Add or update keys in `frontend/src/app/locales/en.ts`.
2. Propagate new keys to all other locale files (e.g., `ar.ts`, `de.ts`, `es-MX.ts`).
3. Preserve interpolation placeholders and terminology.
4. Optionally update i18n fallback or `i18n.ts` files.

**Example:**
```typescript
// en.ts
export default {
  "project.create": "Create Project",
  "project.delete": "Delete Project"
};
```

---

### Add or Update Tests
**Trigger:** When implementing new features, fixing bugs, or improving test coverage.  
**Command:** `/add-test`

1. Add or update backend unit tests (`backend/tests/unit/test_*.py`).
2. Add or update frontend unit tests (`frontend/src/features/*/__tests__/*.test.tsx` or `.test.ts`).
3. Add regression or edge-case tests as needed.

---

### Fix Bug or Regression
**Trigger:** When a bug or regression is reported or discovered.  
**Command:** `/fix`

1. Identify and fix the bug in the relevant backend or frontend file(s).
2. Add or update a regression test to cover the issue.
3. Describe the fix and reference the issue or reporter if applicable.

---

### Add or Update Demo or Pack
**Trigger:** When supporting a new region/market or updating demo content.  
**Command:** `/new-pack`

1. Add or update `backend/app/modules/<pack>/*` and `packs/<country-code>/*`.
2. Add demo projects or templates in `backend/app/core/demo_packs/` or `backend/app/core/demo_projects.py`.
3. Update `manifest.py` and `onboarding.yaml` as needed.
4. Add or update unit tests for the pack.

---

## Testing Patterns

- **Backend:**  
  Python unit tests in `backend/tests/unit/test_*.py`.  
  Example:
  ```python
  def test_create_project(client):
      response = client.post("/api/projects", json={"name": "Test"})
      assert response.status_code == 201
  ```

- **Frontend:**  
  Uses `vitest` with test files matching `*.test.ts` or `*.test.tsx` in `frontend/src/features/*/__tests__/`.  
  Example:
  ```typescript
  import { render, screen } from '@testing-library/react';
  import ProjectList from '../ProjectList';

  test('renders project list', () => {
    render(<ProjectList />);
    expect(screen.getByText('Projects')).toBeInTheDocument();
  });
  ```

## Commands

| Command      | Purpose                                                   |
|--------------|-----------------------------------------------------------|
| /release     | Prepare and document a new release version                |
| /new-table   | Add a new database table or schema migration              |
| /new-endpoint| Implement a new backend API endpoint                      |
| /feature     | Develop a new feature end-to-end                          |
| /i18n-update | Add or update i18n/locale strings                         |
| /add-test    | Add or update backend or frontend unit tests              |
| /fix         | Fix a bug or regression                                   |
| /new-pack    | Add or update a regional pack or demo project             |
```
