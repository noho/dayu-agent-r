# WU-HOST-SESSION-EVENT-DELIVERY-01 Aggregate Deepreview — AgentDS

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-07-22
- **Work Unit**: WU-HOST-SESSION-EVENT-DELIVERY-01 Host Session Event Delivery Ownership and Bounded Mailbox
- **Mode**: Full-WU aggregate deepreview (Current Changes Mode, --base main)
- **Base**: `2c02079a82c049b49914be412178006ccd354049` (main)
- **HEAD**: `035d0035ddc7a707344ade7377009261ce753572` (Slice 4 accepted)
- **Review artifact**: `docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-ds.md`
- **Slices**: S1 → S2 → S3 → S4 (8 commits from plan to Slice 4 HEAD)
- **Excluded**: `docs/host/issues-implementation-control.md` (Controller-owned, uncommitted changes)
- **Prior review artifacts**: NOT read (AgentMiMo artifacts excluded per instruction); Controller adjudications read for context only

## Scope

- **Changed files**: 150 (production/test/config/README/review artifacts)
- **Insertions**: +19,213
- **Deletions**: -2,429
- **Production modules**: 21 (api.py, transient_delta.py, open_host.py, terminal_post_commit.py, engine_ingest.py, admission.py, waiting.py, recovery.py, dispatch.py, command.py, run_transition.py, entrypoint_runtime.py, host_assembly.py, config_loader.py, runtime_display.py, session_execution.py, activity.py, run_view.py, __init__.py, host_runtime.json, design.md)
- **Test modules**: 38
- **README modules**: 6
- **Review methods**: Full adversarial code walkthrough + 3 parallel subagent reviews (Host delivery core, terminal post-commit/producers, Service/CLI observation) + automated verification

## Verification Evidence

### Automated Gates

| Gate | Result |
|---|---|
| pyright | **0 errors, 0 warnings** |
| git diff --check | **pass** |
| Host tests (`tests/host -q`) | **2067 passed, 2 skipped, 6 deselected** |
| Service/CLI/runtime tests | **1376 passed, 7 skipped** |
| Stress tests | **6 passed** |
| `transient_delta.py` coverage | **92.00%** (≥80%) |
| `terminal_post_commit.py` coverage | **95.24%** (≥80%) |
| `entrypoint_runtime.py` coverage | **86.46%** (≥80%) |
| `open_host.py` coverage | **84.16%** (≥80%) |
| Old delivery semantics scan | **empty** (pass) |
| Promotion bypass scan | **5 legitimate callers only** (pass) |
| Runtime reverse dependency scan | **clean** (pass) |
| Engine delivery contract leakage scan | **empty** (pass) |

### Adversarial Verification Summary

Each acceptance criterion was independently verified against direct file:line evidence. Below is the per-criterion cross-reference:

| # | Acceptance Criterion | Evidence | Verdict |
|---|---|---|---|
| 1 | async attach + successful-return boundary | `open_host.py:1195-1234` — cursor durable read + attach + iterator construction all complete before return; cancellation/Host close/partial allocation paths all release reservation | PASS |
| 2 | Host唯一delivery owner | `transient_delta.py` Hub owns all fanout/mailbox/admission; Service relay deleted (`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`_WatchAndWaitRuntime.queue`、`_drain_host_events` all absent) | PASS |
| 3 | 每订阅唯一items-only mailbox + counted in-flight, default 512 | `transient_delta.py:486` — `retained_items = len(_mailbox) + (1 if _in_flight is not None else 0)`; `host_runtime.json:22` — `transient_mailbox_max_items: 512`; no batch drain (`test_transient_delta.py:460` asserts `drain_nowait` absent) | PASS |
| 4 | per-Session admission default 4 | `host_runtime.json:23` — `max_subscriptions_per_session: 4`; `transient_delta.py:784-816` — `reserve()` enforces cap before any allocation | PASS |
| 5 | typed admission/overflow错误 + 低基数metrics | `api.py:1378-1379` — `DELIVERY_INTERRUPTED`/`RESOURCE_EXHAUSTED` error codes; `transient_delta.py:180-214` — typed detail errors; `_DeliveryLogEvent`/`_DeliveryLogOutcome`/`_DeliveryLogReason` closed enums with no identity/payload | PASS |
| 6 | 确定性overflow顺序 | `open_host.py:1289-1298` — accepted prefix items delivered first, error only after `pop_next_nowait()` returns None | PASS |
| 7 | delayed cursor/factory cancellation/Host close/partial allocation | `open_host.py:1195-1259` — cursor transaction before attach; cancellation at await boundary releases reservation; Host close rechecked before attach; partial allocation cleans up in reverse order | PASS |
| 8 | durable causal fence + bounded catch-up + mailbox-empty reconciliation + 双opener ordering | `engine_ingest.py` — fence from same-transaction `Attempt.started_event_sequence`; `open_host.py:1342-1372` — head fence check, bounded single-page catch-up, timeout-based single-page reconcile; `test_watch_session_events.py` — dual-opener C-side barrier test | PASS |
| 9 | local-only TerminalPostCommitPort + 全部terminal producer static/runtime barriers | `terminal_post_commit.py:52-66` — Protocol with explicit opener-local docstring; 29 call sites across 5 consumers using `project_terminal_notice_from_exact_run_event`; zero terminal producer calls `wake_queue_promotion()` directly; static manifest completeness verified | PASS |
| 10 | Service relay删除 + sole consumer + exact-five observation/cleanup + callback非阻塞 + CLI私有executor | `entrypoint_runtime.py` — exact-five closed union (`_TargetTerminal`/`_DeliveryInterrupted`/`_IteratorEnded`/`_CallbackFailed`/`_IteratorFailed`), capacity-one slot, sole consumer single `anext()`, cleanup precedence (stop→await→aclose); `runtime_display.py:150-153` — `ThreadPoolExecutor(max_workers=1)` private, not default, async serial gate before submit | PASS |
| 11 | runtime config/assembly/CLI调用点 | `config_loader.py:1921-2031` — `_parse_session_event_delivery_policy` strict exact fields; `host_assembly.py:885-893` — one-to-one mapping to `HostSessionEventDeliveryPolicy`; 101 call-site references to `watch_session_events(` with 79 `await` | PASS |
| 12 | 无byte contract | No `transient_mailbox_max_bytes`/`delivery_size_bytes`/`cumulative_byte`/`byte_full`/`oversized.*mailbox` anywhere in production/test/README | PASS |
| 13 | Engine边界与全部非目标 | `dayu/engine` — zero references to `TerminalPostCommit`/`session_event_delivery`; Engine contract unchanged | PASS |
| 14 | 受影响tests | Full `tests/host` (2067 passed) + `tests/service`/`tests/cli`/`tests/runtime` (1376 passed) | PASS |
| 15 | 单文件coverage >= 80% | `transient_delta.py`: 92%, `terminal_post_commit.py`: 95%, `entrypoint_runtime.py`: 86%, `open_host.py`: 84% | PASS |
| 16 | 完整pyright | 0 errors, 0 warnings | PASS |
| 17 | README trigger audit | 6 READMEs updated per plan trigger matrix (`dayu/host/README.md`, `dayu/service/README.md`, `dayu/config/README.md`, `dayu/README.md`, `tests/README.md`, `docs/host/design.md`); root `README.md` not modified (符合5.5预期) | PASS |

## Findings

### Slices 1-4 Prior Controller-Adjudicated Findings: All Closed

逐项验证所有前期 Controller adjudication 中 accepted 的 finding：

| Finding | 原始 Gate | 最终裁决 | 闭合证据 |
|---|---|---|---|
| DS-F02 (S1): `pop_next_nowait` terminal fence regression | code-review-slice-1 | `closed` (S1 re-review) | `transient_delta.py:499-517` — 无 `_terminal_run_ids`; `test_transient_delta.py:462` — source assertion; iterator loop handles ordering at `open_host.py:1300-1321` |
| DS-F01 (S3): `_fail_recovering_run` 丢失 exact notice | code-review-slice-3 | `closed` | `engine_ingest.py:2620-2623` — `project_terminal_notice_from_exact_run_event(result.run, result.run_event, wake_queue_promotion=True)` |
| DS-F02 (S3): 四份 transition-result-to-notice helper 重复 | code-review-slice-3 | `closed` | 5 consumers all import `project_terminal_notice_from_exact_run_event` from `run_transition.py:926`; zero local copies |
| S3-RR-F01: waiting 仍复制 projection | code-rereview-slice-3 | `closed` | `waiting.py:75` imports shared helper; old local projection deleted |

### Aggregate Findings: 0 Material

经过完整 adversarial 审查（包括 3 个并行 subagent 深度走读所有关键子系统），**未发现 material correctness/stability/maintainability finding**。

三个 subagent 各自报告的 observations 均为非阻塞项：
- `_close_from_hub()` 不 detach from fanout（design intent：caller Hub.close 已清空 fanout dict）
- `_offer()` overflow 路径直接 `_ready.set()` 而非 `_refresh_readiness()`（行为等价）
- 无 `__del__` cleanup（标准 Python async generator 限制，非本 WU 独有）
- state machine 初始态命名差异（plan 写 `DETACHED`，实际直接从 `ATTACHED_UNBOUND` 开始；语义等价）

## Open Questions

无。

## Residual Risk

1. **无 byte/heap bound**：plan 明确冻结的裁决——容量 contract 只按 retained item 数量有界，不承诺 logical bytes、Python resident heap 或 cross-Session 总内存上界。这是 design decision，不是未覆盖风险。
2. **跨进程 terminal broadcast**：design 明确不实现。跨 opener correctness 仅依赖 durable DB causal fence/reconciliation。双 opener 测试已覆盖此场景。
3. **transient delta 无持久化/重放/断线补放**：design 明确不实现。transient delta 丢失后不可恢复，是已接受的 transient nature。
4. **README 覆盖**：6 个 README 已按 plan trigger matrix 更新。根 `README.md` 审计后未修改（packaged default 无需新增用户配置步骤），符合预期。
5. **单文件 coverage 缺口**：`transient_delta.py:92%`、`terminal_post_commit.py:95%`、`entrypoint_runtime.py:86%`、`open_host.py:84%`。未覆盖行集中在 Host close/internal resource cleanup 路径的 operator diagnostic 分支(`_emit_delivery_log`)、standalone command handle 的 no-local-delivery port、以及一些 defensive `TypeError` 校验分支。这些路径在集成测试中已间接覆盖（full Host suite 2067 passed），不影响 correctness acceptance。

## Decision

**PASS** — 0 material finding.

全部 17 项 acceptance criteria 均通过，所有前期 Controller-adjudicated findings 均已闭合，自动化验证（pyright、tests、coverage、scans）全部通过，subagent 深度走读未发现 correctness/stability/maintainability 缺陷。

## Verification Commands Executed

```bash
# Type checking
pyright  # 0 errors, 0 warnings

# Diff check
git diff --check  # pass

# Host tests
pytest tests/host -q  # 2067 passed, 2 skipped, 6 deselected

# Service/CLI/runtime tests
pytest tests/service tests/cli tests/runtime -q  # 1376 passed, 7 skipped

# Stress tests
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py tests/host/test_transient_delta_stress.py -q  # 6 passed

# Single-file coverage (all >= 80%)
pytest tests/host/test_transient_delta.py tests/host/test_watch_session_events.py --cov=dayu.host.transient_delta --cov-fail-under=80 -q  # 92%
pytest tests/host/test_terminal_post_commit.py --cov=dayu.host.terminal_post_commit --cov-fail-under=80 -q  # 95%
pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-fail-under=80 -q  # 86%
pytest tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py --cov=dayu.host.open_host --cov-fail-under=80 -q  # 84%

# Old delivery semantics scan (must be empty)
rg -n '_TRANSIENT_WATCH_BUFFER_CAPACITY|_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY|session_live_stream|reason_code="slow_consumer"|transient_mailbox_max_bytes|delivery_size_bytes|cumulative_byte|byte_full|oversized.*mailbox' dayu/host dayu/service dayu/cli tests/host tests/service tests/cli dayu/README.md dayu/host/README.md dayu/service/README.md dayu/config/README.md tests/README.md  # empty

# Promotion bypass scan
rg -n '\.wake_queue_promotion\(' dayu/host  # 5 legitimate callers only (coordinator, scheduler bridge, admission non-terminal, recovery accepted/queued)

# Runtime reverse dependency
rg -n 'from dayu\.(engine|host|service|ui|fins)|import dayu\.(engine|host|service|ui|fins)' dayu/runtime  # docstring only

# Engine delivery contract leakage
rg -n 'TerminalPostCommit|session_event_delivery' dayu/engine  # empty
```

## Artifact Path

`docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-ds.md`

READY_FOR_CONTROLLER
