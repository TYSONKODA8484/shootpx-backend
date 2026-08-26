# Nav Items (Sidebar Visibility) — Design Spec

Small, additive feature: give the CMS a show/hide toggle for each of the
Studio's 12 sidebar entries, matching how `Tool.is_active` already
controls individual tool tiles. Confirmed with the user against the
actual Studio UI (screenshots of the sidebar and the Tools page grid).

## Scope

**In scope:** the 12 sidebar nav entries (Home, Upload, Photoshoot,
Refine, Video, Batch, Tools, Templates, Library, Brand Kit, Activity,
Preferences) get a per-item `is_active` toggle, CMS-editable, exposed via
a new public read endpoint the frontend polls once per session — same
shape and spirit as `GET /tools`.

**Already done, not rebuilt:** individual tool-tile visibility
(`Tool.is_active`, proven live earlier this session) and template
visibility (`Template.is_active`). The Tools page's "Scale" group tiles
(Batch Studio / Brand Kit / Library) aren't tools — they're plain nav
links, so they're covered by this feature's `batch`/`brand`/`library`
rows, not by the `tools` table.

**Explicitly out of scope** (per the two decisions already made this
session): reordering, relabeling, icon/badge control. This is show/hide
only — same granularity as `Tool.is_active`.

## Data model

```python
class NavItem(Base):
    __tablename__ = "nav_items"
    key = Column(String, primary_key=True)   # stable identifier, matches
    # the Studio's own route segment (/app/<key>) — the frontend's contract
    label = Column(String, nullable=False)    # display-only, for the CMS's
    # own list view — the frontend keeps its own hardcoded label, this is
    # not fed back to it
    is_active = Column(Boolean, nullable=False, default=True)
    created_at, updated_at
```

Seeded via a one-time data migration with the 12 known keys — same
pattern as the Category-A tool-cost migration and the templates-catalog
seed migration. No code registry needed (unlike `Tool`, these aren't
backed by a Python file per item — the set of pages is fixed by the
frontend's own routing, not discovered from this repo).

## Endpoint

```
GET /nav-items   — no auth, same reasoning as GET /tools (app-shell
                   config, not per-team data)
Returns: [ { "key": "brand", "label": "Brand Kit", "is_active": true }, ... ]
```

Flat array, not wrapped — matches `GET /tools`'s shape exactly, so the
frontend's integration code looks the same for both.

## CMS

New entity `nav-items`, same pattern as `tools`: `allow_create=False`,
`allow_delete=False` (the 12 pages are fixed — an admin toggles, doesn't
add or remove rows), `key`/`label` locked (`editable=False`), `is_active`
gets the same `help_text` treatment as `Tool.is_active`.

## Explicitly out of scope

- Reordering, relabeling, badges/icons (all frontend-owned, unchanged).
- A generic "feature flags" table for arbitrary future toggles — YAGNI;
  revisit only if a real need for non-page, non-tool toggles shows up.
