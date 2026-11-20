# Watchlist Stock Inline Editing Design

> **历史资料。** 以下内容保留文件名所示日期的方案和假设。当前入口、路径与约束见 [项目文档](../../../README.md) 和 [运行契约](../../reliability-and-data-contracts.md)。

**Date:** 2026-05-20
**Status:** Approved

## Problem

Watchlist stocks can only be added or deleted via the Web UI. Modifying a stock's `name` or `tags` requires deleting and re-adding it, which is error-prone and loses data. Tags are the primary editing target since they classify stocks for strategy execution.

## Decision

Add inline editing for `name` and `tags` columns in the stock table. `code` remains read-only (changing code means replacing the stock entirely).

**Approach: Frontend-only, reuse existing PUT save flow.** No backend API changes needed — the existing `PUT /api/watchlists/{filename}` full-replacement endpoint and "dirty → save" pattern handle persistence.

## Interaction Design

### Name Column

- Click name text → converts to `<input>`, auto-focus, select all
- Enter or blur → save to `state.currentWatchlistData.items[idx]`, mark dirty
- Escape → cancel, revert to original value
- Empty name displays "-"; clicking shows empty input

### Tags Column

- Click tags area → enters edit mode:
  - Existing tags shown as pills, each with an × (remove) button
  - An input field for adding new tags (comma-separated or Enter per tag)
- Enter in input → adds new tag pill
- Click × on pill → removes that tag
- Click outside tags area (blur) → exits edit mode, marks dirty
- Empty tags display "-"; clicking enters edit mode

### Code Column

- Read-only, no edit capability. Code change = different stock → delete + add.

### Actions Column

- Unchanged: existing delete button remains.

## Data Flow

```
User clicks name/tags cell
  → DOM switches to edit mode (input/pills+input)
  → User modifies value (Enter/blur/×)
  → Update state.currentWatchlistData.items[idx]
  → Mark dirty (show "Unsaved changes" + Save button)
  → User clicks Save → PUT /api/watchlists/{filename} (existing flow)
```

No new API endpoints. The `saveWatchlist()` function already sends `{name, description, items: [{code, name, tags}]}` via PUT.

## What Changes

### Frontend (`src/quantflow/web/static/app.ts`)

- `renderStockTable()`: Make name and tags cells clickable with edit affordance (cursor pointer, hover highlight)
- New `startEditName(idx)`: Switch name cell to input mode
- New `confirmEditName(idx, newValue)`: Save name change, mark dirty
- New `startEditTags(idx)`: Switch tags cell to edit mode (pills + input)
- New `addTag(idx, tag)`: Add tag to item, mark dirty
- New `removeTag(idx, tagIdx)`: Remove tag from item, mark dirty
- New `finishEditTags(idx)`: Exit tags edit mode

### No Backend Changes

- `watchlists.py`: No modifications
- Data model: No modifications (WatchlistItemModel already has name and tags)

## Testing Strategy

### Frontend Unit Tests (Vitest)

- Tag helper functions: parse, merge, deduplicate
- Edge cases: empty tags, whitespace trimming, duplicate prevention

### E2E Tests

- Edit name: click → type new value → Enter → verify dirty state → Save → reload → verify persisted
- Edit tags: click → add tag → verify pill appears → remove tag → verify pill gone → Save → reload
- Cancel edit: Escape on name → verify original value restored, no dirty state
- Edge: empty name, empty tags, special characters in tags

## Out of Scope

- Batch editing (multi-select + bulk tag assignment)
- Tag-based filtering in the watchlist UI (despite backend `filter_by_tags()` existing)
- `weight` and `notes` fields (currently dead code, not persisted)
- Any new API endpoints
