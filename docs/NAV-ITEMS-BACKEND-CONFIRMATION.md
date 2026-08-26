# Sidebar Visibility (`nav-items`) — What the Frontend Needs

Paste this whole file to the frontend session. Same pattern as
`GET /tools` — nothing new to learn if that's already wired.

---

## The ask

Wire the Studio's sidebar to `GET /nav-items` the same way you're already
wiring (or about to wire) tool tiles to `GET /tools`:

1. Fetch `GET /nav-items` once when the Studio shell mounts.
2. Build a `Set` of the `key`s it returns.
3. Hide any sidebar entry whose `key` isn't in that set. Everything else
   about the sidebar (order, icons, badges like "NEW") stays exactly as
   it is today — frontend-owned, unchanged.

---

## `GET /nav-items`

No auth. Returns a **flat JSON array** (not wrapped), one object per
active page:

```json
[
  { "key": "activity", "label": "Activity", "is_active": true },
  { "key": "batch", "label": "Batch", "is_active": true },
  { "key": "brand", "label": "Brand Kit", "is_active": true },
  { "key": "home", "label": "Home", "is_active": true },
  { "key": "library", "label": "Library", "is_active": true },
  { "key": "photoshoot", "label": "Photoshoot", "is_active": true },
  { "key": "prefs", "label": "Preferences", "is_active": true },
  { "key": "refine", "label": "Refine", "is_active": true },
  { "key": "templates", "label": "Templates", "is_active": true },
  { "key": "tools", "label": "Tools", "is_active": true },
  { "key": "upload", "label": "Upload", "is_active": true },
  { "key": "video", "label": "Video", "is_active": true }
]
```

`is_active` will always be `true` for every object in the array —
inactive rows are filtered out server-side, not returned with a `false`
flag. Order is alphabetical by `key`, not display order — keep your own
sidebar ordering, just filter against the set.

`label` is included for convenience/debugging but you almost certainly
don't need it — you already have your own copy per sidebar item.

---

## ⚠️ One thing to confirm — the `key` strings

I seeded these 12 keys from your own screenshots' visible order, guessing
at short slugs (`brand` for "Brand Kit", `prefs` for "Preferences"). I do
**not** know your actual route segments or internal ids for each page.

**Please confirm** these 12 keys match how you'd identify each page
internally (route segment, nav config id, whatever you already key
things by): `home`, `upload`, `photoshoot`, `refine`, `video`, `batch`,
`tools`, `templates`, `library`, `brand`, `activity`, `prefs`.

If any don't match, tell me the correct strings and I'll update the
seeded rows to match — it's a one-line data fix on our side, no schema
change, and better to fix now than have a silent mismatch where a hidden
page never actually hides because the key never matched anything.

---

## Freshness

Same guarantee as `GET /tools`: no caching layer, hits Postgres directly
on every call. Confirmed live — toggled a page off via the actual CMS,
it disappeared from `GET /nav-items` on the very next call, no delay to
plan around.
