# BugPilot AI — PostgreSQL Migration + Phases 1–4 Setup Guide

This document covers everything that changed and exactly how to get it running
locally, assuming you've never touched PostgreSQL or pgAdmin before.

---

## Part A — Install PostgreSQL 18 and pgAdmin

### 1. Install PostgreSQL 18

- Go to https://www.postgresql.org/download/ and pick your OS (Windows/Mac/Linux).
- Windows/Mac: use the **EDB installer** — it bundles PostgreSQL, pgAdmin 4, and
  the command-line tools together in one wizard.
- During install you'll be asked to set a **password for the `postgres` superuser**.
  Pick something you'll remember (e.g. `postgres`) — you'll need it in step 4.
- Keep the default **port 5432** unless something else is already using it.
- When the installer finishes, it usually offers to launch **Stack Builder** —
  you can skip/cancel that, we don't need extra components.

### 2. Confirm the server is running

- Windows: open **Services** (search "Services" in the Start menu) → look for
  `postgresql-x64-18` → status should be "Running".
- Mac (if installed via Postgres.app or brew): the app icon/menu bar shows a
  green "running" indicator, or run `brew services list`.
- Linux: `sudo systemctl status postgresql`

### 3. Open pgAdmin 4

- Launch pgAdmin from your Start menu / Applications folder.
- The first time you open it, it asks you to set a **master password** — this
  only protects pgAdmin itself, it's separate from the postgres password.
- In the left sidebar, expand **Servers → PostgreSQL 18**. It'll prompt for the
  `postgres` superuser password you set during install. Enter it and check
  "Save Password" so you're not asked every time.

### 4. Create a dedicated database + user for this project (step by step)

We never run the app as the `postgres` superuser — we create a dedicated
login role + database, exactly matching what's in `.env`.

**4a. Create the login role (user):**
1. In pgAdmin's left tree: right-click **Login/Group Roles** → **Create** → **Login/Group Role...**
2. **General tab** → Name: `bugpilot_user`
3. **Definition tab** → Password: `bugpilot_pass`
4. **Privileges tab** → toggle ON: "Can login?" ✅ (this one is required).
   You don't need Superuser/Createdb/Createrole for this app.
5. Click **Save**.

**4b. Create the database:**
1. Right-click **Databases** → **Create** → **Database...**
2. Database: `bugpilot_db`
3. Owner: pick `bugpilot_user` from the dropdown (this matters — it means our
   app user actually owns the tables it creates).
4. Click **Save**.

That's it — pgAdmin just ran the SQL equivalent of:
```sql
CREATE ROLE bugpilot_user WITH LOGIN PASSWORD 'bugpilot_pass';
CREATE DATABASE bugpilot_db OWNER bugpilot_user;
```

**4c. Verify it in the Query Tool (optional but reassuring):**
1. Click on `bugpilot_db` in the left tree, then **Tools → Query Tool**.
2. Run: `SELECT current_database(), current_user;`
3. You should see `bugpilot_db` — this confirms the DB exists and is reachable.

You now have a running PostgreSQL 18 server with a database (`bugpilot_db`)
and a login (`bugpilot_user` / `bugpilot_pass`) that matches the `DATABASE_URL`
already set in `backend/.env`:

```
DATABASE_URL=postgresql+psycopg2://bugpilot_user:bugpilot_pass@localhost:5432/bugpilot_db
```

If you used a different name/password, just edit that one line in `.env` to match.

---

## Part B — Backend: install, migrate, run

```bash
cd Backend_PythonFastAPI-main

# 1. Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 2. Install dependencies (now includes psycopg2-binary + alembic)
pip install -r requirements.txt

# 3. .env is already provided, pointing at bugpilot_user/bugpilot_db.
#    Open it and set your real GEMINI_API_KEY (AI Bug Generator won't work
#    without one — everything else works fine either way).
#    Also change SECRET_KEY to your own random string before going anywhere
#    near production.

# 4. Run the migration — this is the step that actually creates the
#    users / roles / permissions / role_permissions tables in Postgres.
alembic upgrade head

# 5. Start the API
uvicorn app.main:app --reload
```

Visit http://localhost:8000/docs — you should see Swagger UI with Authentication,
AI Bug Generator, Admin - User Management, and Roles sections.

### Verifying FastAPI → SQLAlchemy → PostgreSQL are actually connected

Before trusting anything above, confirm the chain works:
1. `alembic upgrade head` succeeding with no errors means SQLAlchemy's engine
   reached Postgres and Alembic's own `alembic_version` bookkeeping table got
   written — that's FastAPI's config → SQLAlchemy → Postgres, verified.
2. Back in pgAdmin, refresh `bugpilot_db → Schemas → public → Tables`. You
   should now see `users`, `roles`, `permissions`, `role_permissions`,
   `alembic_version`.
3. `POST /api/v1/auth/signup` via Swagger UI, then check in pgAdmin
   (Query Tool → `SELECT * FROM users;`) that the row actually landed in
   Postgres, not some leftover SQLite file.

### What happens automatically on first run

- **Table creation** is handled by the Alembic migration you just ran (this is
  the "authoritative" path). `main.py` also calls `Base.metadata.create_all()`
  as a harmless safety net, but Alembic migrations are what you should rely on
  and extend going forward (`alembic revision --autogenerate -m "..."` whenever
  you add a new model).
- **Role/permission seeding** happens automatically every time the app starts
  (see `app/services/role_service.py` + the `@app.on_event("startup")` hook in
  `main.py`). It's idempotent — safe to restart the server as many times as
  you want.
- **Bootstrap Owner**: the very first account you sign up through
  `/api/v1/auth/signup` (or the frontend Signup page) automatically becomes
  **Owner** — the only role with every permission by default, including access
  to the new User Management screen. Every signup after that gets the
  **Developer** role. You (or another Owner) can change anyone's role later
  from User Management → Assign role.

---

## Part C — Frontend: install and run

```bash
cd AI-Bug-Frontend-main
npm install

# .env is already provided:
#   VITE_API_BASE_URL=http://localhost:8000
# Change it only if your backend runs on a different host/port.

npm run dev
```

Visit http://localhost:5173. Signup/login/AI Bug Generator work exactly as
before — nothing about those flows changed.

---

## Part D — What's new to try

1. **Sign up as your first user** (e.g. you, the admin). You'll automatically
   become **Owner**.
2. Log in — the sidebar now shows a **"User Management"** item (only Owners
   and Project Managers see it; sign up a second account and you'll see it's
   hidden for that one, since it defaults to Developer).
3. Open **User Management**:
   - **Invite User** — creates the account immediately and shows you a
     one-time temporary password to hand off manually (no email sending is
     wired up yet, so this is the "share it yourself" flow for now).
   - **Assign role** — change any user's global role (Owner / Project Manager
     / Developer / QA Engineer / Viewer).
   - **Deactivate/Activate** — soft-disables login without deleting the row.
   - **Delete** — permanently removes the account (you can't delete or
     deactivate yourself, by design).
4. Try logging in as a non-admin (Developer) account and confirm:
   - The "User Management" nav item is gone.
   - Hitting `/admin/users` directly bounces you back to the dashboard.
   - Calling the admin API directly (e.g. via `/docs`) with that account's
     token returns `403 Forbidden` — this is the real security boundary; the
     frontend hiding the nav item is just a UX nicety on top of it.

---

## Part E — What changed under the hood (file-by-file)

### Backend

| File | What changed |
|---|---|
| `.env`, `.env.example` | New — PostgreSQL connection string + all existing settings preserved |
| `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` | New — Alembic wired to read the DB URL from `app.config.settings` (your `.env`), and to `app.models` for autogenerate |
| `alembic/versions/0001_initial_schema.py` | New — creates `users`, `roles`, `permissions`, `role_permissions` |
| `requirements.txt` | Added `alembic==1.13.2` (psycopg2-binary was already present) |
| `app/models.py` | Added `Role`, `Permission`, `role_permissions` table; added `role_id`, `invited_by_id`, `must_change_password`, `last_login_at` to `User` |
| `app/schemas/admin_schema.py` | New — request/response schemas for RBAC + admin user management |
| `app/schemas/__init__.py` | `UserOut` now includes a nested `role`; re-exports the new admin schemas |
| `app/services/role_service.py` | New — permission catalog, default roles, idempotent seeding, `user_has_permission()` |
| `app/services/user_service.py` | `create_user()` now assigns Owner to the first-ever signup, Developer to everyone after |
| `app/services/admin_service.py` | New — list/invite/update/deactivate/activate/delete/assign-role logic |
| `app/dependencies.py` | Added `require_permission(code)` dependency factory |
| `app/routers/admin_router.py` | New — `/api/v1/admin/users/*` endpoints |
| `app/routers/roles_router.py` | New — `/api/v1/roles` (list roles, for the assign-role dropdown) |
| `app/main.py` | Registers the two new routers; seeds roles/permissions on startup |

Nothing in `app/routers/auth_router.py`, `app/routers/ai_bug.py`, or any of the
`app/services/bug|evidence|llm/*` files was touched — signup, login, and the
AI Bug Generator behave exactly as before.

### Frontend

| File | What changed |
|---|---|
| `.env`, `.env.example` | Fixed to point at `http://localhost:8000` (was `8002`) |
| `src/services/adminService.js` | New — calls to the admin/roles endpoints |
| `src/utils/rbac.js` | New — `canManageUsers(user)` client-side visibility helper |
| `src/routes/AdminRoute.jsx` | New — route guard for `/admin/users` |
| `src/routes/AppRoutes.jsx` | Adds the `/admin/users` route, nested under `AdminRoute` |
| `src/pages/UserManagement.jsx` | New — the full Phase 4 screen: list, search, invite, edit, assign role, activate/deactivate, delete |
| `src/components/Sidebar.jsx` | Adds a "User Management" nav item, shown only when `canManageUsers(user)` |
| `src/pages/Settings.jsx` | Shows the current user's role badge |

`AuthContext`, `authService`, `axiosInstance`, `ProtectedRoute`, and every
existing page were left untouched — your working signup/login/AI Bug
Generator flows are unaffected.

---

## Part F — Where Phase 5 (Projects) picks up

Nothing here assumes projects exist yet, by design. When you're ready:
- Add a `Project` model + `project_members` table (per-project role,
  reusing the same `Role`/`Permission` tables if you want project-level
  permissions later).
- Add `alembic revision --autogenerate -m "add projects"` and review the
  generated migration before running `alembic upgrade head`.
- Reuse `require_permission(...)` / add a `require_project_permission(...)`
  variant the same way `admin_router.py` does today.
