# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Goal Confirmation / Rescope

## Work Unit

- Umbrella WU: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `Round3 R3-E - Web And Document Tool Egress, Resource Caps, Diagnostics, And Oracles`
- Type: production-high semantic ownership / correctness / resource-boundary fix
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`

## Motivation

The motivation is valid.

Round3 controller adjudication accepted R3-E because current Web/Documents tool paths contain bounded, directly evidenced semantic-owner failures:

- Web egress policy is local to URL string checks and does not fully own redirect/subrequest peer safety.
- Web resource caps are enforced after large materialization in key paths, so cap semantics are not owned before allocation.
- Diagnostic paths can persist full page/login/secret-like material instead of a redacted diagnostic contract.
- Document read/search/list paths can materialize full files or trees before business caps.
- Smoke/diagnostic pass states can be self-certified by the path under test rather than an independent oracle.
- Challenge detection and fallback behavior have contradictory owner signals.
- DuckDuckGo fallback parsing can silently collapse provider shape drift into empty success.

These are not style findings. They affect externally reachable tool behavior, resource use, diagnostics, and LLM-facing tool outcomes.

## Correct Owners

- Web egress policy owner: production Web tool boundary shared by HTTP, redirect, Playwright, diagnostic, and warmup paths.
- Web resource budget owner: Web fetch/orchestration boundary before body, decoded content, DOM, or diagnostic materialization.
- Web diagnostic owner: diagnostic projection/redaction boundary, not individual caller error branches.
- Web challenge/search owner: challenge detection and web search provider parsers, not final tool projection.
- Document resource budget owner: document source/list/read/search processors before full materialization.
- Smoke/oracle owner: test/diagnostic oracle layer that observes independent failure/success signals, not the same path being certified.

## Scope

R3-E should plan and implement only evidence-backed current Round3 R3-E findings:

- Shared Web production/diagnostic egress policy for URL, redirect, and browser fallback paths.
- Wire/decoded/DOM/warmup resource caps before unbounded allocation.
- Diagnostic redaction/avoidance of raw secret/login-state persistence by default.
- Document read/search/list pre-budgeting before full file/tree materialization.
- Independent smoke/diagnostic oracles, including negative controls.
- Redirect response close/cancel correctness.
- Challenge fallback consistency and false-positive tuning.
- DuckDuckGo provider shape-drift failure signaling.

## Non-Goals

- Do not implement unrelated Fins upload allowlists, CN/HK downloader provenance, symlink upload policy, or LLM-facing upload/download security schema from earlier R3-C residuals.
- Do not introduce a broad repository-wide security framework or generic capability system unless the plan proves it is the minimal owner boundary for R3-E Web/Documents paths.
- Do not modify Host/Engine governance semantics unless needed only for existing diagnostic projection contracts.
- Do not use downstream fallback to mask unsafe or over-budget inputs.
- Do not make UI/Web app product changes outside the tool boundary.

## Success Signals

- Web production and diagnostic fetch paths consume the same owner contract for egress and resource limits.
- Redirect, cancellation, and rejection paths close response resources deterministically.
- Oversized compressed, decoded, warmup, DOM, file, and directory inputs fail or truncate at the owner boundary before full materialization.
- Diagnostics contain bounded, redacted, non-reversible material by default.
- Smoke/diagnostic pass/fail/skipped states are backed by independent assertions and negative-control tests.
- Challenge detection/fallback behavior is consistent and does not turn normal pages into blocked results without owner evidence.
- Provider parser shape drift produces typed diagnostic/degraded failure rather than silent empty success.
- Validation includes Web SSRF/resource/challenge tests, document cap tests, diagnostic redaction tests, oracle negative-control tests, pyright, and `git diff --check`.

## Risk Level And Slice Guidance

Risk level: High.

R3-E touches external I/O, resource limits, diagnostics, and tool outputs. The plan should split by semantic owner rather than by file:

- Web egress and redirect/cancel response ownership.
- Web resource budgets, challenge fallback, diagnostics, and search-provider parser outcomes.
- Document resource caps and smoke/oracle correctness.

The plan may merge slices only if it proves file ownership and validation blast radius stay bounded.

## Tool-Security Boundary

R3-E contains security-sensitive Web/Documents egress findings. This goal confirmation authorizes planning for those accepted current-scope R3-E findings only.

It does not authorize unrelated tool-security work outside R3-E. Any broader tool-security framework, upload/file-authority policy, Fins downloader provenance policy, or LLM-facing security schema must be rejected or deferred unless direct R3-E evidence proves it is required by the owner boundary.

## Blocking Questions

None. Proceed to plan gate.
