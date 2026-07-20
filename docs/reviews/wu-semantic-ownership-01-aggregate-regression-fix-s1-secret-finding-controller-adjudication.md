# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Secret Finding Controller Adjudication

> **Superseded on 2026-07-19:** 用户已裁决本地 Config 与 Host SQLite/EventLog 属于同一受信任产品域，内部 EventLog 持久化 provider secret/header 不构成当前 code finding；只有 Tool Trace、audit 及其它 public/LLM-facing projections 不得泄露明文。权威 supersession 记录为 `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-user-decision-controller-record.md`。本文以下内容仅保留历史审查过程，不再授权 design correction 或 implementation。

## Gate identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Finding：`S1-SEC-F01`。
- Gate：Slice 1 configured-secret scan 后的 dual design-truth review controller adjudication。
- 历史状态：`SUPERSEDED BY USER DECISION / NO LONGER BLOCKING`。
- 本 artifact 是总控裁决，不是新 WU、不是新 feature/issue，也不授权 implementation。
- 本 artifact 不记录任何 secret value 或具体 secret ref 名称。

## Locked evidence

- Controller redacted evidence：
  `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-evidence.md`
  - SHA-256：`2f3fc19e4cdab8b93fd2e4e8b09008169e95d0ece4f7183431d3bd643b574bea`
- AgentMiMo corrected design-truth review：
  `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-designtruth-review-mimo.md`
  - SHA-256：`fd1897411497b039f05cda6891d547c0d09a2130659e479758d3a3f2581c674f`
  - 初版遗漏的完整 control/Fins/UI reads 与 `docs/host/design.md:3403` 已通过同任务 follow-up 补齐。
- AgentDS design-truth review：
  `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-designtruth-review-ds.md`
  - SHA-256：`0aef51d2a9eef88eb98f650b7a5d87c66d3d3257a78e4da7e11828c528088d84`
- Accepted aggregate fix plan commit：`ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- Finding production origin：umbrella accepted commit `2f2b73f8`。

## Direct production and design-truth evidence

Production chain is closed by direct code evidence:

```text
Service model assembly
  -> resolves configured environment reference into provider header value
  -> constructs RunnerSpec with resolved headers
  -> Host admission accepts the RunnerSpec
  -> Host effective-execution projection writes all RunnerSpec headers
  -> USER_INPUT_ACCEPTED canonical fact persists them in EventLog SQLite
  -> dispatch/replay restores the same headers
  -> Engine runner sends them to the provider
```

The configured-secret scan found three value occurrences in one real-compactor SQLite path. Two logical occurrences are in `USER_INPUT_ACCEPTED` canonical facts at the structural JSON path already recorded in the redacted evidence. `git-diff://HEAD` had zero match, so this is neither a review-artifact leak nor a test fixture string. The real smoke exercises the production chain above.

The behavior directly conflicts with all of the following authoritative rules:

1. `docs/host/design.md:115`：Service / execution environment owns provider secret use, redaction and protection.
2. `docs/host/design.md:944`：Host does not accept API-key plaintext; `RunnerSpec.api_key_ref` is only a secret reference.
3. `docs/host/design.md:944`：Host must freeze each Run's effective runner configuration as an explainable snapshot or source refs for retry/replay/recovery.
4. `docs/host/design.md:3403`：EventLog cannot contain API keys or headers.
5. `docs/ui/design.md:66`：secret may be persisted only in the user-selected system environment location, not workspace JSON, Host durable state, logs or LLM-facing text.

## Reviewer disposition

### Converged accepted conclusions

Both independent reviewers now converge on all material points:

- `S1-SEC-F01` is valid, severe and blocking.
- It is not a test false positive and cannot be waived by deleting the temporary SQLite file, using a synthetic key, narrowing the scan or skipping the real smoke.
- Projection-only redaction is not a complete fix.
- A header-name blacklist is not a semantic owner and is rejected.
- Host dispatch must not resolve an environment reference or otherwise receive plaintext secret.
- EventLog must not persist headers, not merely omit one known authorization header.
- Current design truth excludes the unsafe implementations but does not define a code-generation-ready secret injection/recovery seam.
- A product/design correction is required before plan or implementation can resume.

### AgentMiMo findings

- `S1-SEC-F01`：`ACCEPTED / BLOCKING`。
- MiMo initial proposal to resolve the secret in Host dispatch：`REJECTED`，because it moves the same violation from durable storage into Host runtime memory.
- Corrected MiMo conclusion that design truth is insufficient：`ACCEPTED`。

### AgentDS findings

- DS F-01, plaintext provider secret and headers in EventLog：`ACCEPTED / BLOCKING`，merged into `S1-SEC-F01`。
- DS F-02, one `RunnerSpec` currently carries both a secret reference promise and resolved headers：`ACCEPTED AS ROOT-CAUSE CONTRACT EVIDENCE`，not tracked as a second independent code finding.
- DS F-03, durable header projection/replay owner gap：`ACCEPTED AS DESIGN GAP`。
- DS header-name closed set / Host-side re-render candidate：`REJECTED`，because it conflicts with the literal no-headers EventLog rule and Host no-plaintext rule.

## Controller adjudication of the open questions

The following points are already determined by existing design truth and are not sent back to the user as false choices:

1. EventLog must contain no `headers` field in the frozen runner payload. “Allow non-secret headers after filtering” is rejected because the source says no headers and a blacklist has no unique owner.
2. Host must never look up, receive, reconstruct or forward plaintext provider secrets in Host-owned admission/dispatch/projection code.
3. Current Run, retry, replay and recovery must fail closed if the execution environment cannot resolve the exact accepted runner configuration; silent fallback to current defaults is forbidden.
4. Topic 9 remains no-code: this correction must not introduce a unified tool authorization framework, permission schema, role/capability model, policy DSL or sandbox.
5. Issues 142, 151, 175, 177 and 178 remain deferred and out of scope.

One material product boundary remains genuinely undecided:

> What is the typed, uniquely owned representation and execution seam that preserves the exact secret-free header/template configuration for per-Run override and retry/replay/recovery, while resolving the secret only inside a Service-owned execution environment immediately before Engine provider I/O?

The current public contracts do not answer this:

- `RunnerSpec` is simultaneously used as Service-to-Host durable configuration and Host-to-Engine execution input.
- Omitting headers from EventLog loses exact per-Run custom header/template semantics.
- Re-reading mutable current `models.json` from only provider/model/api-key refs does not reproduce the accepted historical override.
- Letting Host call an environment resolver still makes Host receive plaintext.
- Letting Service directly control dispatch violates Host lifecycle authority.

## Recommended product decision

Controller recommends a type-safe execution-boundary correction:

1. Split the Host-safe, durable runner configuration from the Engine-only resolved runner input. One type must not promise both “secret reference only” and “resolved outbound headers”.
2. EventLog stores no headers. Exact secret-free header templates/non-secret provider request material are frozen outside EventLog as a content-addressed, digest-checked descriptor referenced by the Run snapshot. The descriptor must contain no resolved secret value.
3. Reuse the existing typed `LocalEngineWorkerFactory` / `LocalEngineWorker` execution boundary as the Service-owned execution environment seam. Service composition supplies the secret resolution authority to that execution environment; Host receives only the typed factory/worker port and never the secret value.
4. Immediately before Engine provider I/O, the execution environment validates the descriptor digest, resolves the accepted `api_key_ref`, renders the descriptor into an Engine-only `RunnerSpec`, and fail-closes on missing/mismatched source or secret.
5. Opener baseline, compactor baseline and per-Run override use the same descriptor/ref contract. Retry/replay/recovery reuse the exact frozen descriptor rather than mutable current config.
6. Do not add a generic callback registry, secret manager platform, provider permission framework or compatibility path. This is one narrow provider-execution boundary correction.

This recommendation changes a public/cross-layer typed contract and durable source-ref meaning, so it cannot be inferred as implementation authorization. User confirmation and design-truth writeback must precede the remediation plan gate.

## Required validation after a user decision

The later plan must include at least:

- owner tests proving Service-to-Host inputs and EventLog contain no resolved secret and EventLog contains no headers field;
- descriptor digest/tamper/missing-source fail-closed tests;
- current Run, opener, compactor, per-Run override, retry, replay and restart recovery tests proving the same accepted descriptor is used;
- worker-boundary tests proving Host-owned code never observes resolved headers while Engine provider I/O receives the rendered header only at execution time;
- missing/blank secret resolution fail-closed tests with redacted diagnostics;
- real compactor smoke and configured-secret scan with zero matches;
- existing security matrices, full pyright, affected coverage, `git diff --check`, README triggers and full aggregate regression rerun.

## Gate result and authorization

- `S1-SEC-F01` remains `OPEN / ACCEPTED / BLOCKING`.
- Slice 1 test deltas and implementation artifact remain protected intermediate work.
- AgentCodex implementation, Slice 1 code review/commit, Slice 2, Slice 3, aggregate deepreview, push and PR remain unauthorized.
- Next entry is user product decision on the recommended type-safe execution-boundary correction, followed by design-truth writeback and a corrected remediation plan gate within the same umbrella WU.
