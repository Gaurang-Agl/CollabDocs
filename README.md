# CollabDocs — Collaborative Document Platform

A backend REST API for **CollabDocs**, a multi-tenant collaborative document platform built with **Django REST Framework (DRF)** and **PostgreSQL**. CollabDocs allows users to create workspaces, manage role-based members (Admin, Editor, Viewer), write version-controlled documents, leave threaded comments, categorize documents with tags, and track actions via automatic audit logging.

---

## 📽️ Demo Video
- **Video Walkthrough Link:** [Add your Loom or Google Drive link here]
- **Duration:** 5–10 minutes
- **Key demonstrations shown:**
  1. Atomic transaction rollback on failure (409 Conflict duplicate member handling)
  2. Custom request logging middleware output in terminal in real-time
  3. Aggregation endpoints (Workspace summary & Document stats)
  4. Signal-driven `AuditLog` generation on Document creation and update

---

## 🚀 Key Features & Architectural Highlights

1. **8 UUID-Based Data Models:** Custom `User`, `Workspace`, `WorkspaceMember`, `Document`, `DocumentVersion`, `Comment`, `Tag`, and `AuditLog`.
2. **17 REST Endpoints:** Clean ViewSets with custom `@action` decorators and URL routing via `DefaultRouter`.
3. **Strict Data Integrity:** `transaction.atomic()` ensuring atomic workspace setup and per-document version history snapshots.
4. **Optimized QuerySets:** Extensive use of `select_related`, `prefetch_related`, `distinct()`, `values_list()`, and `Q` objects for search filtering.
5. **Real-time Aggregations:** Document statistics and workspace summary endpoints using `Count` and `annotate()` / `aggregate()`.
6. **Custom Middleware:** Measures request execution duration and logs method, endpoint, status code, and milliseconds.
7. **Signal Architecture:** `post_save` signal on `Document` checking `instance._state.adding` to automatically log audit trails.

---

## 🛠️ Tech Stack & Dependencies

- **Framework:** Django 5.2.6 & Django REST Framework 3.16.1
- **Database:** PostgreSQL (with `psycopg 3.3.6` / `psycopg-binary 3.3.6`)
- **Configuration:** `python-decouple 3.8` (Environment variable isolation)
- **API Client:** Postman

---

## ⚙️ Installation & Setup Guide

### 1. Prerequisites
- Python 3.10+
- PostgreSQL server running locally

### 2. Clone the Repository
```bash
git clone https://github.com/Gaurang-Agl/CollabDocs.git
cd CollabDocs
```

### 3. Create & Activate Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Copy `.env.example` to `.env` in the root directory:
```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Update `.env` with your PostgreSQL database credentials:
```env
DB_NAME=collabdocs_db
DB_USER=your_postgres_user
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
SECRET_KEY=your_django_secret_key
DEBUG=True
```

### 6. Create PostgreSQL Database
Using `psql` or pgAdmin:
```sql
CREATE DATABASE collabdocs_db;
```

### 7. Run Migrations
```bash
python manage.py makemigrations collaboration
python manage.py migrate
```

### 8. Run Automated Test Suite
```bash
python manage.py test collaboration
```
The test suite includes 31 comprehensive automated tests covering:
- Atomic workspace creation and automatic owner ADMIN role assignment
- Rollback verification upon integrity conflicts (409 Conflict)
- Sequential document versioning (version 1, 2, ... N)
- Signal-driven and transactional audit logging on Documents, Workspaces, and Members
- Role-based permissions (Admin, Editor, Viewer, Non-member access controls)
- Custom field validations (case-insensitive duplicate email/phone 409 handling, format validations, non-blank strings, inactive workspace guards)
- Document immutability across workspaces (preventing cross-workspace document moving on update)
- Advanced queries: `Q` object search (title/content), status filtering, and tag filtering
- Aggregations (`documents_by_status`, workspace summary, document stats)


### 9. Start Development Server
```bash
python manage.py runserver
```
The API will be live at `http://127.0.0.1:8000/api/`.

---

## 📡 API Endpoints Overview (17 Endpoints)

### 👤 Users
- `POST /api/users/` — Create user
- `GET /api/users/{id}/` — Retrieve user details

### 🏢 Workspaces
- `POST /api/workspaces/` — Create workspace (owner automatically added as Admin in single transaction)
- `GET /api/workspaces/{id}/` — Get workspace details (annotated with member & document counts)
- `POST /api/workspaces/{id}/members/` — Add member with role (`admin`, `editor`, `viewer`)
- `GET /api/workspaces/{id}/members/` — List members (supports filters: `roles`, `joined_after`, `joined_before`, `email`)
- `GET /api/workspaces/{id}/summary/` — Aggregated workspace summary (total members, total documents, status breakdown)

### 📄 Documents
- `POST /api/documents/` — Create document (+ auto-generates version 1 and triggers audit log)
- `PUT /api/documents/{id}/` — Update document (+ auto-generates version N+1 and triggers audit log)
- `GET /api/documents/` — List documents (supports filtering: `workspace`, `status`, `tags`, `updated_after`, `updated_before`, and `search` via `Q` OR logic)
- `GET /api/documents/{id}/versions/` — List document version history
- `GET /api/documents/{id}/stats/` — Aggregated document stats (version count, comment count, unique contributors)
- `POST /api/documents/{id}/tags/` — Attach tags to document

### 💬 Comments
- `POST /api/comments/` — Add comment or nested reply (supports threaded replies)
- `GET /api/comments/?document={id}` — List threaded comments for a document

### 🏷️ Tags & 📜 Audit Logs
- `POST /api/tags/` — Create new tag
- `GET /api/audit-logs/` — List audit history (supports filters: `actions`, `model_name`, `timestamp_after`, `timestamp_before`)

---

## 🧪 Postman Collection

The complete Postman collection is committed at the repository root:
- [`postman_collection.json`](./postman_collection.json)

**Authentication & Authorization Model:**
In strict compliance with the assignment specification, user context and role-based permissions (ADMIN, EDITOR, VIEWER) are simulated using the request header:
```http
X-User-ID: <User-UUID>
```
This architecture intentionally avoids superfluous external JWT/session overhead while ensuring rigorous role enforcement:
- Workspace owners automatically become `admin`.
- Only `admin` members can add workspace members.
- Only `admin` and `editor` members can create or update documents.
- `viewer` members have read-only access to documents, versions, comments, and stats.
- Non-members are rejected with `403 Forbidden`.

The Postman collection is preconfigured with collection and environment variables (`{{base_url}}`, `{{user_id}}`, `{{workspace_id}}`, etc.) and automated test scripts to extract and propagate dynamic UUIDs seamlessly through the execution flow.

