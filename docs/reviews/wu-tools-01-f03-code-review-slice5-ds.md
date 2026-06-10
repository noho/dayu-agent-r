# Code Review — WU-TOOLS-01-F03 Slice 5 Closeout (AgentDS)

## Scope

- Mode: current changes (Slice 5 uncommitted workspace changes)
- Branch: wu-tools-01-f03-web-ci-smoke
- Review date: 2026-06-10
- Review file: `docs/reviews/wu-tools-01-f03-code-review-slice5-ds.md`
- Included scope:
  - `docs/host/issues-implementation-control.md` (staged diff)
  - `tests/README.md` (unstaged diff)
  - `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md` (untracked, Codex implementation closeout report)
- Excluded scope:
  - Prior Slice 1-4 committed code and review artifacts
  - `utils/smoke_web_ci.py`, `utils/diagnose_web_access.py` production code (not changed in Slice 5)
  - Unrelated control doc history and other WUs
- Sources of truth:
  - `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md` (Slice 5 section)
  - `docs/host/issues-implementation-control.md` (Residual Risk table rules, Slice 5 closeout conditions)
  - `tests/README.md` (Agent update constraints / document duty)
  - `docs/host/design.md`, `docs/engine/design.md` (architecture alignment)
- Parallel review coverage: none

## Verification Commands Executed

| Command | Result |
|---|---|
| `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q` | 36 passed in 0.36s |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | no output (passed) |
| `bash -n utils/smoke_web_ci.sh` | N/A (file does not exist) |

## Findings

### F1-S5-DS-001 — Severe — WU-TOOLS-01-S5-R2 closed without transferring external instability to concrete owner/issue

- **Entry/function**: `docs/host/issues-implementation-control.md` Residual Risk table and F02/F03 Work Unit rows
- **File (line)**:
  - `docs/host/issues-implementation-control.md:195-202` (Residual Risk table: `WU-TOOLS-01-S5-R2` row deleted, no new entries appear)
  - `docs/host/issues-implementation-control.md:954` (F03 status claims "WU-TOOLS-01-S5-R2 closed")
  - `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md:51-58` (closeout rationale, no concrete transfer owner mentioned)
- **Triggering input**: Slice 5 closeout performs R2 residual reconciliation
- **Actual branch**: Deletes `WU-TOOLS-01-S5-R2` row from active Residual Risk table; adds no new entries for external site / browser / provider instability; Codex report claims "no new un-owned residual" and closes R2
- **Expected behavior**: Per plan `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md:487-488` and `:575-585`, R2 closeout MUST transfer external/browser/provider instability to concrete owner or issue. Plan is explicit: "不得留下无 owner residual。若 closeout 时无法写出具体 GitHub Issue 编号、控制文档条目或明确 owner 角色，不得关闭 `WU-TOOLS-01-S5-R2`，必须停止让用户裁决。" (No orphan residual. If concrete GitHub Issue number, control doc entry, or clear owner role cannot be provided at closeout, R2 must not be closed; stop and let user adjudicate.)
- **Actual behavior**: R2 marked closed and removed from active table, but all three categories requiring transfer — external site anti-bot/DNS/timeout/403 unreliability, real Playwright browser/Chrome channel/storage-state gap, and provider/API availability instability — have NO new entry in Residual Risk table and are NOT associated with any concrete GitHub Issue number or clear owner role
- **Direct evidence**:
  - Residual Risk table (`:195-202`): only `WU-ENG-02-S3-R1`, `WU-TOOLS-01-S1-R1`, `WU-TOOLS-01-S1-R2`, `WU-TOOLS-01-F01-02-R1/R2/R3` remain. Zero entries for Web external site instability, Web browser capability gap, or Web provider availability.
  - Codex report `:58`: "没有新的无 owner residual。后续若需要把 external corpus、real Playwright browser 或 provider availability 升级为硬 gate，需要新的环境契约、owner 和 work unit；这不属于 `WU-TOOLS-01-S5-R2` 的 local Web smoke 关闭条件。" (No new un-owned residual. If external corpus, real Playwright browser, or provider availability need to become hard gates later, that requires new environment contract, owner, and work unit; this is not part of R2's local Web smoke closeout conditions.)
  - Plan `:579-585` explicitly requires all three transfer categories, and "不得留下无 owner residual" (no orphan residual).
  - Plan `:487-488`: "若 external/browser/provider 仍不稳定，必须转移到具体 owner 或 issue，并说明不是 F03 local smoke 阻塞。无 owner 或 issue 时不得关闭 closeout。" (If external/browser/provider remain unstable, must transfer to concrete owner or issue, stating they do not block F03 local smoke. R2 must not be closed without owner or issue.)
- **Impact**: External Web site instability, real browser gap, and provider availability gap disappear from tracking system; subsequent work may miss these known risks citing "R2 already closed"; violates plan's highest residual governance constraint
- **Suggested fix and verification**:
  1. Do not claim R2 closed without concrete transfer entries
  2. Create Residual Risk table entry for external site instability, with owner as operator diagnostic maintenance issue / GitHub Issue
  3. Create entry for Playwright browser/Chrome/storage-state gap, with owner as browser-capability smoke issue
  4. Create entry for provider/API availability, with owner as provider-specific smoke/environment issue
  5. Each entry must have concrete GitHub Issue number or control doc entry; if issues cannot be created now, at minimum write into control doc Residual Risk table with `deferred-with-owner` status and clear owner role
  6. Mark R2 closed only after all transfers are completed
- **Fix risk (medium)**: Requires deciding concrete owner roles and issue numbers; needs user adjudication on whether to create issues now or track as deferred residual in control doc
- **Severity (severe)**: Violates plan's highest hard constraint — residual governance stop condition; known risks lose tracking

### F1-S5-DS-002 — High — Manual opt-in smoke not executed; plan expected assertion not met

- **Entry/function**: `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md:47` (not-run declaration)
- **File (line)**: `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md:32-48`
- **Triggering input**: Slice 5 closeout issues manual smoke command verification
- **Actual branch**: Codex report explicitly states "本轮未运行真实 `DAYU_RUN_WEB_CI_SMOKE=1`" (did not run real live smoke this round), with rationale "F03 deterministic closeout 已由 focused tests 与 pyright 证明" (F03 deterministic closeout already proven by focused tests and pyright)
- **Expected behavior**: Plan `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md:521` lists "manual opt-in smoke outputs `summary.json` / `summary.md` with pass / skip / diagnostic-only classification" as Slice 5 expected assertion. Plan does not list "may skip manual smoke run" as an acceptable completion condition.
- **Actual behavior**: Expected assertion #4 not verified. Deterministic synthetic tests cover classification logic but do not verify end-to-end path: local HTTP server startup, diagnostics subprocess invocation, real JSON artifact loading, summary file writing, exit code propagation
- **Direct evidence**:
  - Plan `:520-525` lists 4 expected assertions; #4 is manual opt-in smoke output
  - Codex report `:47`: "本轮未运行真实 `DAYU_RUN_WEB_CI_SMOKE=1`"
- **Impact**: Server startup logic, subprocess call argument construction, JSON schema validation path, summary file write path, and exit code mapping are not verified in real end-to-end execution; path construction bugs, subprocess argument errors, or schema version validation bugs in `utils/smoke_web_ci.py` would not be caught by current verification
- **Suggested fix and verification**:
  1. Run `source .venv/bin/activate && DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live` before closeout completion
  2. Verify `workspace/output/web_smoke/<run_label>/summary.json` and `summary.md` exist and contain valid content
  3. If Docling not installed, verify PDF case skip + HTML pass path (exit code 0)
  4. If unable to run (e.g., no network/Docling), explicitly record skip reason in closeout and state which paths are covered by synthetic tests vs. which require live environment
- **Fix risk (low)**: Running manual smoke is deterministic; risk limited to local environment possibly lacking dependencies causing PDF skip, which is itself the smoke skip path test
- **Severity (high)**: Plan expected assertion not met; end-to-end verification gap

### F1-S5-DS-003 — Medium — F02 non-goal historical record rewritten with post-F03 facts

- **Entry/function**: `docs/host/issues-implementation-control.md` WU-TOOLS-01-F02 non-goal section
- **File (line)**: `docs/host/issues-implementation-control.md:938`
- **Triggering input**: Slice 5 closeout updates F02 entry non-goal text
- **Actual branch**: Original text "不在 F02 定义 Web smoke 的 pass / fail gate；S5-R2 在 F02 后仍保持 open，交由 WU-TOOLS-01-F03 生成 smoke 后关闭。" changed to "不在 F02 定义 Web smoke 的 pass / fail gate；F02 完成后该缺口交由 WU-TOOLS-01-F03 生成 smoke，并已在 F03 Slice 5 closeout 中关闭。"
- **Expected behavior**: F02 "non-goal" section should remain a historical record of what F02 itself does not do; it should not be rewritten to include conclusions that only became true after F03 completed
- **Actual behavior**: Non-goal record rewritten from "S5-R2 still open" to "already closed in F03 Slice 5 closeout". This makes F02 non-goal section read like a retrospective written after F03, reducing its fidelity as F02's independent historical document
- **Direct evidence**:
  - Git diff shows F02 non-goal line `:938` text changed from "S5-R2...仍保持 open" to "已在 F03 Slice 5 closeout 中关闭"
  - F02 non-goal section should describe what F02 itself does not do, not what downstream work unit has accomplished
- **Impact**: Historical record fidelity reduced; credibility of F02 section as independent work unit documentation damaged
- **Suggested fix and verification**:
  1. Revert F02 non-goal section R2 closeout rewrite
  2. Restore to "S5-R2 在 F02 后仍保持 open，交由 WU-TOOLS-01-F03 生成 smoke 后关闭" or similar forward-looking formulation
  3. R2 final conclusion should only appear in F03 section and Residual Risk table
- **Fix risk (low)**: Text-only revert
- **Severity (medium)**: Non-goal section duty semantics damaged, but scope limited to that paragraph

### F1-S5-DS-004 — Medium — F02 Work Unit entry introduces cross-WU forward reference depending on contested R2 closeout

- **Entry/function**: `docs/host/issues-implementation-control.md` Work Units table WU-TOOLS-01-F02 row
- **File (line)**: `docs/host/issues-implementation-control.md:223` (current status column)
- **Triggering input**: Slice 5 closeout updates F02 row status
- **Actual branch**: F02 row "current status" column gains "`WU-TOOLS-01-S5-R2` 已在 F03 Slice 5 closeout 中关闭。"
- **Expected behavior**: F02 row should only record F02's own facts (PR 132 merged, final closeout artifact, provides prerequisites for F03). R2's final closeout status should be expressed in F03 row and Residual Risk table, not asserted as confirmed fact in F02 row, especially when R2 closeout is contested (see F1-S5-DS-001)
- **Actual behavior**: F02 row claims R2 closed in F03. This forward reference depends on F03 Slice 5 closeout validity (currently challenged by Finding F1-S5-DS-001)
- **Direct evidence**:
  - `docs/host/issues-implementation-control.md:223` diff shows: `F03 前置条件已满足；\`WU-TOOLS-01-S5-R2\` 已在 F03 Slice 5 closeout 中关闭。`
  - If F1-S5-DS-001 is valid, this statement is inaccurate
- **Impact**: If F1-S5-DS-001 requires fix (adding concrete transfers), F02 row must also be corrected
- **Suggested fix and verification**: Revert F02 row to only record F02's own completion facts and prerequisites; leave R2 final adjudication in F03 row and Residual Risk table
- **Fix risk (low)**: Text-only revert
- **Severity (medium)**: Cross-WU forward reference introduces dependency risk; must be corrected together with Finding 001

### F1-S5-DS-005 — Low — git status scope confirmed; no core code changes

- **Entry/function**: git working tree
- **File (line)**: `git status --short` — `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md` is untracked
- **Triggering input**: Slice 5 closeout verification
- **Actual branch**: `git status --short` shows staged `M docs/host/issues-implementation-control.md`, unstaged `M tests/README.md`, untracked `?? docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md`
- **Expected behavior**: Consistent with Slice 5 plan allowed files/modules — only docs and tests/README.md modified, no core code changes
- **Actual behavior**: Consistent with expectation. No core code changes.
- **Direct evidence**: git status shows only 3 changed items, all documentation/validation files
- **Impact**: No negative impact; git status scope confirms Slice 5 did not exceed authority
- **Suggested fix and verification**: `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md` should be staged before commit after content completeness confirmed
- **Fix risk (low)**: Confirmation only, no fix needed
- **Severity (low)**: Confirmatory finding, non-blocking

## Open Questions

1. **R2 transfer owners not specified**: Which GitHub Issues should be created for external site anti-bot/DNS/timeout, real Playwright browser/Chrome/storage-state, and provider/API availability respectively? If issues are not created now, what owner role identifiers should be used in the control doc? Requires user adjudication.
2. **Must manual smoke run before closeout**: Plan lists it as expected assertion, but local Docling/Chrome/network status is unknown. If user confirms deterministic tests + transparent declaration suffices, this finding can be downgraded to deferred; if user requires run-first, environment readiness is needed.
3. **Update strategy for completed WU sections**: Should F02 non-goal section reflect "R2 was closed by downstream WU" fact, or strictly maintain historical record fidelity? Current plan does not explicitly specify update strategy for already-completed WU sections.

## Residual Risk

- **External Web site instability (anti-bot, DNS, timeout, 403/429/5xx)**: No tracking entry in Residual Risk table. Plan requires transfer to concrete owner/issue; not executed.
- **Real Playwright browser / Chrome channel / storage-state cookies gap**: No tracking entry in Residual Risk table. Plan requires transfer to concrete owner/issue; not executed.
- **Provider/API availability gap**: No tracking entry in Residual Risk table. Plan requires transfer to concrete owner/issue; not executed.
- **Manual smoke end-to-end path not verified**: Server startup, subprocess invocation, JSON schema validation, summary file write path only covered by synthetic tests; real execution not verified.
- **F02 section historical fidelity**: Non-goal section and Work Unit row rewrites may impact completed work unit's documentation independence.

## Review Conclusion

**Conclusion: pass-with-fixes**

Must fix before re-closeout:
1. **F1-S5-DS-001 (Severe)**: R2 cannot be closed without concrete transfers. Must create Residual Risk table entries with concrete owner/issue for external site instability, browser gap, and provider availability gap before marking R2 closed.
2. **F1-S5-DS-002 (High)**: Execute manual smoke or explicitly record skip reason with synthetic coverage boundary.
3. **F1-S5-DS-003 (Medium)**: Revert F02 non-goal section R2 closeout retrospective rewrite.
4. **F1-S5-DS-004 (Medium)**: Synchronously correct F02 Work Unit row forward reference.

After fixes, re-verify `git diff --check`, `pytest`, `pyright` pass.
