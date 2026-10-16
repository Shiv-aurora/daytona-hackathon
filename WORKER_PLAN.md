# Active backend execution

The user replaced the manual five-chat/PR checkpoint plan with spawned backend subagents.
`STATUS.md` is the current record of assignments, progress, reviews, tests, and limitations.

- Storage: local SurrealDB, persistence, seed/reset, isolation.
- Recovery: report intake, organization claims, delivery/verification, API integration.
- Calls: opt-in receipt checks, fixed disclosure, emergency escalation, provider adapters.
- Evaluation: synthetic historical/current disaster data, label-separated comparison, Arize export.
- Integration: shared boundaries/dependencies, review, merges, independent HTTP/DB verification.
- UI: the user's separate agent; backend agents must not change it.

Agents work in separate worktrees, commit their scoped changes, and report results to integration.
Integration reviews and merges locally, returning specific defects to the owning agent for repair.
No remote repository, deployments, live calls, or automatic paid-service export are configured.

The demo remains report -> claim -> delivery report -> verified outcome -> reviewed lesson ->
measured reuse. Real agency/emergency-feed integrations and production authentication stay out of scope.
