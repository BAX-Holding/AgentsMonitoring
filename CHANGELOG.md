# Changelog

## 0.3.0 – review candidate (2026-10-15)

### Core/plugin boundary

- Plugin API v1: declarative agent tables, shared renderer, extra columns, scoped actions,
  model/account display detectors and hidden sessions/services. File manifests plus opt-in
  Python entry points. No private runtime imports or deployment names in core.
- Bounded isolated worker processes, background collection, stale result expiration, visible
  error cards and guarded/namespaced action endpoint. Plugin auth is never implicit.
- Package manifest, `doctor` integrity/plugin diagnostics, clean/modified footer.
- Shared fixed-column tables, safe clipping for long IDs, optional usage-column width,
  English labels, service-card subrows/history. Legacy modules retained.
- Clean-HOME unattended installer mode and real-browser/HTTP/plugin acceptance tests.
- Legacy service modules reject non-boolean health and non-finite/negative metrics, keeping
  malformed output from faking a healthy state or breaking the dashboard's JSON.

### Fixes and community review

- [Issue #4](https://github.com/petrludwig-collab/AgentsMonitoring/issues/4), reported by
  **jenicek001**: close SQLite uptime connections after transactions, including initialization
  failures. Also close Antigravity connections on query errors, reviewed against
  jenicek001's `fix/sqlite-fd-leak` fork (fb7e3883, 95c28661).
- [Issue #6](https://github.com/petrludwig-collab/AgentsMonitoring/issues/6), reported by
  **jenicek001**: Hermes reads its own model configuration regardless of key order and never
  borrows Codex's model on failure. Wizard no longer freezes the discovered model as a manual
  tag. Manual existing overrides remain operator-controlled.
- [PR #3](https://github.com/petrludwig-collab/AgentsMonitoring/pull/3), **tomasvida**:
  adopt actual Claude process `--model` over an ambiguous shared-cwd transcript. Preserve
  exact-session transcript precedence for runtime `/model` changes; ignore helper argv.
- [PR #8](https://github.com/petrludwig-collab/AgentsMonitoring/pull/8), **TomasErnest**:
  account-scoped **opt-in Usage plugin** inspired by the proposal. Adapted to explicit local
  snapshots instead of vendor-global caches and automatic OAuth requests. Missing/expired
  data is visibly unknown; no invented quotas. This is a reviewed adaptation, not a merge of
  the original PR's networking implementation.

See [community review](docs/COMMUNITY-REVIEW.md) for other fork findings and scope decisions.
This candidate has not been published, tagged on GitHub, or deployed automatically.
