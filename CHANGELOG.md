# Changelog

## 1.0.4-beta.2 - 2026-09-22

Extends the 1.0.4 beta with timetable fixes and downloadable diagnostics.

- Regenerate the full current Monday-Friday timetable after a Home Assistant restart instead of starting at the current day.
- Add Home Assistant config-entry diagnostics for timetable investigations.
- Include the raw `time_tables_current` structure and generated lesson slots while redacting person-related fields.
- Keep the WÜ/TÜ recognition and debug counters from beta.1 unchanged.

## 1.0.4-beta.1 - 2026-09-22

Beta for investigating missing WÜ/TÜ calendar entries.

- Recognize WÜ, TÜ, WUE, TUE, Wissensüberprüfung and tägliche Übung in journal note types and descriptions.
- Match the new abbreviations as whole words to avoid unrelated text matches.
- Add opt-in debug summaries for all three exam journal sources, including unused sources, missing dates, unrecognized notes and entries outside the requested range.
- Debug summaries contain only counts and fixed recognition labels, without API payloads, identifiers, names or note text.
- Keep existing journal source selection and cancelled-lesson behavior unchanged pending real-world diagnostics.

## 1.0.3 - 2026-08-21

### Fixed

- Limit the HACS catalog entry to Germany with `"country": "DE"`.
- Require Home Assistant 2026.3.0 so the bundled integration brand assets are supported.

## 1.0.2 - 2026-08-17

### Fixed

- Restore timetable-card lesson-number mapping from the new `lessons.times` relation.
- Keep fallback timetable rows grouped by identical start/end times when no lesson number can be resolved.

## 1.0.1 - 2026-08-17

### Fixed

- Restore timetable calendar events after beste.schule moved lesson times behind the `lessons.times` include relation.
- Keep compatibility with the new per-lesson `time` object containing `from` and `to`.

## 1.0.0 - 2026-08-09

First stable release.

### Added

- Reauthentication flow for expired or rejected Personal Access Tokens
- Stable per-student entity, device and local-storage identifiers
- Automatic creation of grade sensors for subjects discovered after setup
- Automated Python tests and code-quality checks

### Improved

- Independent API endpoints load concurrently with a global request limit
- Shared API responses and grade history use bounded, defensive caches
- Timetable generation and timetable-card rows are reused between entities
- One shared timer updates school-time and lesson entities at exact boundaries
- Timetable history is persisted only after changes and survives ID migration
- Homework history is retained for one year instead of growing indefinitely
- Authentication errors reliably trigger Home Assistant reauthentication

### Removed

- Development-only diagnostics from production builds
