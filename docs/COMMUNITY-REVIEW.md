# Community review, 2026-10-15

Public GitHub metadata/commits only, no account credentials. No issues/PRs were modified and no
code pushed. Fork default branches were compared with upstream main; explicitly referenced
feature branches were also examined. This is not a review of every branch or every file in
every fork.

## Included or adapted

- [jenicek001](https://github.com/jenicek001/AgentsMonitoring), issues #4/#6 and SQLite/Hermes
  branches: explicit connection close (also on Antigravity errors), independent Hermes model.
- [tomasvida PR #3](https://github.com/petrludwig-collab/AgentsMonitoring/pull/3): process argv
  model precedence over shared-cwd guesses, preserving exact-session runtime changes.
- [TomasErnest PR #8](https://github.com/petrludwig-collab/AgentsMonitoring/pull/8): quota-column
  idea adapted to the plugin API, explicit per-account local snapshots. The original vendor-wide
  cache and automatic token-based networking are not included.

## Additional findings, deferred deliberately

- `tominoxxx` c21e360e: ephemeral/runtime job visibility; implementable as a plugin, not needed
  for this compatibility upgrade.
- `palascak-radek` 6bfcf1fa: Hermes model detection; overlapping with the included independent
  config detector.
- `twiggy22` 936a8d92, 886b0049, bf3e7e2a, ff245573, 7a881cd9: connection/threading changes,
  configurable repository URL, bounded restart attempts and container health. Connection
  lifetime is covered here. Supervision-policy changes need separate failure/recovery tests.
- `tomasvida` f21700c0, fc8c1bf8, 11499b9a, 244c38da: conservative process-model detection;
  used as review context, not merged wholesale.
- `nostromocz`: themes, timezone, name colors, Hermes Telegram state and action gating.
  Display/state customization fits plugins; unrelated timezone and supervision changes deferred.
- `ochodek` be067979, 4d5b9008, f0ed82e9, 835d08bb: process model precedence, native Claude
  sessions, compaction/checkpoint recovery. Native-session/recovery changes are beyond this
  tmux-compatible plugin release.
- `brozian` 2de544f3: process discovery scoped to the current user. Worth a separate regression
  task on multi-user hosts; this change set does not alter process-supervision scope.
- `bezecny75` 39483778, 2af1fcd6, 817badc7: Security Health card, SQLite close and status labels.
  FD fix is covered; organization-specific security inputs belong in a service/plugin.

## Compared with no commits ahead on the inspected default branch

`xtra-software`, `kratocz`, `32may`, `Bacis55`, `BAX-Holding`, `qaxi`, `dan-tsu`,
`tomasjenicek/petrludwig_AgentsMonitoring`, `renegis-tools`, `DavidKosatka`, `haggycz`,
`harrywebdev`, `Marbh`.

Together with the ten forks discussed above this covers the 23 forks returned by the public
listing at review time. Counts/branches can change; no claim is made about subsequent updates.
