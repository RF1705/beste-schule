# Changelog

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
