# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 4 — AgentMiMo Code Review

- Reviewer: AgentMiMo
- Date: 2026-07-22T03:01:39
- Base: `24efe9bd` (accepted Slice 3)
- Branch: `phaseflow/wu-host-session-event-delivery-01`
- Auto artifact: `docs/reviews/code-review-20260722-030139.md`

## Verdict

**PASS (with 1 low-severity finding)**

## Material Finding Count

1

## Finding Paths

| # | Severity | File | Summary |
|---|---|---|---|
| 1 | 低 | `dayu/cli/session_execution.py` | 单文件覆盖率 79.53%，低于 80% 目标 |

## Detailed Findings

### 1-未修复-低-session_execution.py 单文件覆盖率未达 80% 目标

- **入口/函数**: `dayu/cli/session_execution.py` 全模块
- **文件(行号)**: `dayu/cli/session_execution.py` (79.53% coverage, target ≥ 80%)
- **输入场景**: `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py --cov=dayu.cli.session_execution --cov-fail-under=80`
- **实际分支**: 覆盖率报告 79.53%，未通过 80% gate
- **预期行为**: 单文件覆盖率 ≥ 80%
- **实际行为**: 79.53%，差 0.47%。未覆盖行包括 interactive REPL 边界路径 (628-629, 658-661, 664, 670-671, 674-675, 679-680, 684-686)、display controller lifecycle 错误路径 (714-745, 760-763, 778-786) 和部分 interactive turn 处理路径 (1112-1119, 1259-1263, 1296-1306)
- **直接证据**: `pytest --cov=dayu.cli.session_execution --cov-fail-under=80` 输出 `FAIL Required test coverage of 80% not reached. Total coverage: 79.53%`
- **影响**: 未覆盖行主要为 interactive REPL 边界路径和 error-handling 分支，不直接威胁核心 submit/cancel 终态正确性，但降低对 CLI lifecycle cleanup 路径的信心
- **建议改法和验证点**: 补充 1-2 个 interactive turn error path 测试（如 display controller close failure、interactive turn lifecycle cleanup 异常路径），提升覆盖率至 ≥ 80%
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Validation Summary

| 检查项 | 结果 |
|---|---|
| pyright (full) | 0 errors, 0 warnings |
| git diff --check | clean |
| stale pattern scan | 空 |
| S4 focused tests (70) | 全部通过 |
| CLI integration tests (91) | 全部通过 |
| service+CLI affected suite (794 passed, 7 skipped) | 全部通过 |
| host suite regression (2067 passed, 2 skipped, 6 deselected) | 全部通过 |
| entrypoint_runtime coverage | 86% ✓ |
| runtime_display coverage | 93% ✓ |
| session_execution coverage | 79.53% ✗ |

## S4 Contract Verification Checklist

- [x] Service relay 彻底删除 (`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`, `_WatcherFailure`, queue/drain_task, `_drain_host_events`)
- [x] Exact-five sole consumer + capacity-one generation slot
- [x] `EntrypointCallbackExecutionPort` Protocol 定义与 `RuntimeDisplayController` 实现
- [x] attach/submit/cancel/startup 时序 — submit 先 attach → bind → submit → wait；cancel 先 snapshot → attach → bind → cancel → wait；startup 按 generation 逐个 bind → wait → ack
- [x] typed overflow-only durable recovery (`DELIVERY_INTERRUPTED` + `TRANSIENT_MAILBOX_OVERFLOW` → `_wait_for_durable_terminal`)
- [x] terminal identity dedupe — `seen_event_ids` 已删除，改用 `seen_terminal_event_ids` + `seen_dedupe_keys`
- [x] callback shield (`_await_shielded_callback_job` 使用 `asyncio.shield` + re-shield loop)
- [x] callback failure → `_CallbackFailed` member
- [x] CLI 私有单线程 execution domain (`ThreadPoolExecutor(max_workers=1)` + async serial gate)
- [x] close/cause ordering — primary identity preserved, cleanup as cause chain
- [x] 真实跨层 interruption — `_FakeHostEventIterator` 支持 `_RaiseSignal` + typed `HostApiError` injection
- [x] README 更新 (`dayu/README.md`, `dayu/service/README.md`, `tests/README.md`)
- [x] S1-S3 回归 — host suite 2067 tests 全部通过
- [x] `tests/cli/test_transient_slow_consumer_path.py` 已删除，`tests/cli/test_transient_delivery_interruption_path.py` 已新增

## Open Questions

无

## Residual Risk

- `session_execution.py` 覆盖率 79.53%，接近但未达 80% 目标。未覆盖行主要是 interactive REPL 边界和 error-handling 分支，对核心终态观察路径无直接影响。
