# Changelog

## 0.3.1 (2026-10-18)

- Bootstrap the configured tmux server from the cron launcher's shell before
  starting Python. On macOS this preserves the OS permission attribution of the
  launcher; it does not grant or bypass TCC permissions. Existing sessions survive.
- Optional `services[].row_details` shows escaped probe details in the shared
  service table, preserving row identities and history. Default remains off.
- English source identifiers and examples, fresh-install instructions for macOS
  and Ubuntu, and corrected documentation of authentication and action controls.
- Refresh the package integrity manifest and verify release metadata consistency.
- Browser acceptance waits for the action's delayed refresh before measuring
  table geometry. No production renderer change is needed for that test race.
- Python 3.10–3.14 CI runs the standard-library test suite, lint and package install.

## 0.3.0 (2026-10-15)

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

- Keepalive atomically refreshes an existing cron launcher, including when agent supervision
  is disabled. This repairs the first upgrade executed by older updater code on shared hosts.
- Installer parses its full body before a pull can overwrite its own file. Uninstall removes
  an unmodified local CLI wrapper and suggests manual PATH cleanup without editing shell rc files.
- Initial/expired plugin checks show neutral loading with no stale rows or actions. Actual
  errors/timeouts stay red. Dashboard startup announces its URL only after auth/bind succeeds.
- Uninstall uses PID-aware dashboard shutdown and a current-user, full-command keepalive
  match. Daemon Stop is also scoped to the current user, with patterns separated from options.
- Headless installation without a controlling terminal succeeds and prints `agentsmon setup`.
- Dashboard launcher and stop fallback are scoped to the current user. Updates stop via the
  PID-aware service helper and regenerate an existing launcher instead of broad `pkill`.
- Off-loopback auth errors point to `agentsmon setup`. Service uptime displays the observed
  streak duration, not a count of healthy day buckets; tests reap their child processes.
- Healthy daemon/port agents show `Running`, matching tmux agents. Health-check latency
  remains in the status tooltip; explicit error/down states retain precedence.
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
