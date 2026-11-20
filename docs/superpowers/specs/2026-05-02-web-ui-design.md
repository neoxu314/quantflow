# QuantFlow Web UI Design

> **历史资料。** 以下内容保留文件名所示日期的方案和假设。当前入口、路径与约束见 [项目文档](../../../README.md) 和 [运行契约](../../reliability-and-data-contracts.md)。

**Date:** 2026-05-02
**Author:** Sisyphus
**Scope:** Add optional web-based UI for managing watchlists, tasks, and viewing system config.

---

## 1. Overview

An optional web interface integrated with the existing QuantFlow CLI system. Users launch it via `quantflow web`. The web UI provides visual management for:

- **Watchlists** — CRUD on `watchlists/*.yaml` files
- **Tasks** — CRUD across `config/tasks_*.yaml` files
- **System Config** — read-only view of `quantflow.yaml`

**Key principle:** Zero-intrusion to existing system logic. All existing YAML formats, data structures, and CLI commands remain unchanged.

---

## 2. Architecture

```
quantflow web
├── CLI (cli.py)              — web() command
├── FastAPI Server
│   ├── /api/watchlists/*     — Watchlist CRUD
│   ├── /api/tasks/*          — Task CRUD (multi-file)
│   ├── /api/config           — Config view (read-only)
│   ├── /api/strategies       — Strategy list
│   └── /                     — Static SPA
├── Frontend (TypeScript ES Module)
│   ├── Watchlists tab
│   ├── Tasks tab
│   └── Settings tab
└── Config loading from quantflow.yaml → web: {port, host}
```

All YAML reading/writing uses existing patterns (`yaml.safe_load`, `yaml.dump`) and preserves existing file formats.

---

## 3. New Files

### 3.1 Backend

| File | Purpose |
|------|---------|
| `src/quantflow/web/__init__.py` | Package init |
| `src/quantflow/web/config.py` | Web config loader (port, host from quantflow.yaml) |
| `src/quantflow/web/server.py` | FastAPI app + CLI integration |
| `src/quantflow/web/api/__init__.py` | API package init |
| `src/quantflow/web/api/watchlists.py` | Watchlist CRUD API |
| `src/quantflow/web/api/tasks.py` | Task CRUD API |
| `src/quantflow/web/api/config.py` | Config + strategies API |

### 3.2 Frontend

| File | Purpose |
|------|---------|
| `src/quantflow/web/static/index.html` | SPA with tabbed interface + Tailwind CSS (CDN) |
| `src/quantflow/web/static/app.ts` | TypeScript source (browser-native ES Module) |

### 3.3 Modified Files (additions only)

| File | Change |
|------|--------|
| `src/quantflow/cli.py` | Add `web()` function + cli routing |
| `config/quantflow.yaml` | Add `web:` section |
| `pyproject.toml` | Add `fastapi`, `uvicorn[standard]` deps |

---

## 4. Backend API Spec

### 4.1 Watchlist Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/watchlists` | List all: `[{filename, name, itemCount, path}]` |
| GET | `/api/watchlists/:filename` | Get detail with items |
| PUT | `/api/watchlists/:filename` | Create or replace |
| DELETE | `/api/watchlists/:filename` | Delete file |
| POST | `/api/watchlists/search` | Global stock search |

**Search response:**
```json
{"code": "NVDA.US", "found": true, "inLists": ["nasdaq_100.yaml", "sp_500.yaml"]}
```

### 4.2 Task Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List all tasks across all yaml files |
| POST | `/api/tasks` | Add new task |
| PUT | `/api/tasks/:id` | Update task |
| DELETE | `/api/tasks/:id` | Remove task |

**Task ID format:** `{filename}:{task.name}` (e.g. `tasks_us_mac:nasdaq`)

### 4.3 Config & Strategies

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | System config (read-only) |
| GET | `/api/strategies` | Available strategies from registry |

---

## 5. Frontend Spec

### 5.1 Three-tab layout

**Watchlists tab:**
- Left sidebar: watchlist list (name + item count)
- Right main area: item table (code, name, tags, delete buttons)
- Toolbar: Add stock (autocomplete search), Batch import (textarea), Delete selected
- Global search bar: type code → shows if exists and in which lists
- Modified tracking: `beforeunload` warning if unsaved changes

**Tasks tab:**
- Table: name, watchlist, strategies, output, file, edit/delete buttons
- Add/Edit modal: select watchlist (dropdown), strategies (multi-checkbox), output (text input)
- System config read-only card below

**Settings tab:**
- Read-only display of quantflow.yaml content (JSON/tree view)

### 5.2 TypeScript approach

- Browser-native ES Module (`<script type="module">`)
- Uses ES2020+ syntax with JSDoc type annotations
- No Node.js or build step required
- Git clone → `pip install -e .` → `python -m quantflow web` → works

### 5.3 Tailwind CSS

- Loaded via CDN in HTML
- Zero build step
- Direct `class="..."` usage in HTML

---

## 6. Error Handling

| Scenario | Handling |
|----------|----------|
| File not found | 404 with message |
| YAML parse error | 500 with filename |
| Duplicate watchlist name | 409 Conflict |
| Concurrent modification | Last-write-wins (single user) |
| Invalid strategy name | 400 with valid list |
| Empty watchlist items | 200 accepted (watchlist can be empty) |

---

## 7. Security

- Local-only binding (127.0.0.1 by default)
- No authentication needed (personal use)
- File access restricted to `watchlists/` and `config/*.yaml` patterns

---

## 8. Future Extension Hooks (NOT implemented now)

Code structure reserves for:

- **Stock metadata cache:** API `/api/metadata/:code` → cached name, sector, PE
- **Task execution:** POST `/api/tasks/:id/run` → background execution + progress
- **Execution history:** GET `/api/tasks/:id/history` → past results summary

These are reserved as empty endpoint stubs or clear TODO markers.

---

## 9. Self-Review

**Placeholder check:** Zero TBD/TODO in core spec. Future section is clearly marked as out-of-scope.
**Consistency:** ID format is consistent (`{filename}:{name}`). YAML preservation is stated throughout.
**Scope:** Focused on watchlist/task/config management. Excludes execution, history, metadata, auth.
**Ambiguity check:**
- Task ID format is explicit.
- File locations are explicit.
- TypeScript approach is explicit (no build step).
- Auto-open browser on launch + print URL.
- Delete confirmation on both.

---

## 10. Spec Ready for Review

Please review the spec and let me know if you want to make any changes before we start writing out the implementation plan.
