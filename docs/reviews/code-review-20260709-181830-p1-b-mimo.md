# Code Review

## Scope

- Mode: current changes (P1-B implementation for WU-SEMANTIC-OWNERSHIP-01)
- Branch: `phaseflow/host-issues-control`
- Base: HEAD (uncommitted diff)
- Output file: `docs/reviews/code-review-20260709-181830-p1-b-mimo.md`
- Included scope: P1-B implementation files per plan `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Excluded scope: P0-A, P0-B, P1-A, P1-C, P2-* sub WUs; non-P1-B touched files
- Parallel review coverage: 无

## Findings

### P1B-CODE-MIMO-F01-未修复-低-`_validate_terminal_cancel_request_link` 未覆盖所有 terminal mutation 路径

- **入口/函数**: `dayu/host/durable/state.py` — `cancel_cancelling_run_row` (L3471), `cancel_queued_run_row` (L3339), `cancel_running_run_row` (L3405), `cancel_waiting_run_row` (L4131), `cancel_recovering_run_row` (L4067); `dayu/host/durable/run_transition.py` — `lose_recovering_run_in_transaction` (L1472)
- **文件(行号)**: `dayu/host/durable/state.py:3471` (`cancel_cancelling_run_row`), `dayu/host/durable/state.py:5197` (`_validate_terminal_cancel_request_link`)
- **输入场景**: Run 从 CANCELLING 经 RECOVERING 到 LOST 的 transition 路径；或 `cancel_queued_run_row` 等被传入非预期的 `cancel_request_event_id` 值时。
- **实际分支**: `_validate_terminal_cancel_request_link` 只被 `terminal_unstarted_run_row` (L3295) 调用，该校验 enforce 两条规则：(1) CANCELLED 必须有 link；(2) 非 CANCELLED 不可有 link。其余 cancel row mutator（`cancel_queued_run_row` 等）只用 `_require_non_empty_text` 校验 link 非空，不校验"非 cancelled 不可有 link"方向。`cancel_cancelling_run_row` 完全不校验 cancel link。
- **预期行为**: 所有 terminal mutation 路径应一致 enforce `_validate_terminal_cancel_request_link` 的两条规则，保证 `cancel_request_event_id` 的语义 shape 在每个 terminal transition 入口都被校验。
- **实际行为**: `cancel_cancelling_run_row` 不校验 cancel link（依赖 CANCELLING 状态已有的值）；`lose_recovering_run_in_transaction` 不校验 cancel link，若 Run 从 CANCELLING 经 RECOVERING 到 LOST，stale `cancel_request_event_id` 会保留。
- **直接证据**: `state.py:3295` 调用 `_validate_terminal_cancel_request_link`；`state.py:3471` (`cancel_cancelling_run_row`) 不调用；`run_transition.py:1472` (`lose_recovering_run_in_transaction`) 不调用。
- **影响**: 数据卫生问题，非阻断性。production 路径中 CANCELLING + accepted cancel 会被 recovery scan defer 到 watchdog 关闭为 CANCELLED；CANCELLING + 无 accepted cancel 直接到 LOST 时不经过 RECOVERING。stale cancel link 不影响任何 consumer（consumer 只在 CANCELLING/CANCELLED 状态读取该 link）。数据库 CHECK constraint 只 enforce CANCELLING/CANCELLED 必须有 link，不 enforce 非 CANCELLED 不可有 link。
- **建议改法和验证点**: 在 `_validate_terminal_cancel_request_link` 被 `terminal_unstarted_run_row` 调用的基础上，将该校验抽取为所有 terminal row mutator 的公共入口校验，或在 `cancel_cancelling_run_row` 和 `terminal_recovering_run_lost_row` 中显式调用。验证：新增测试覆盖 CANCELLING → LOST 路径中 stale cancel link 被拒绝或清除。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### P1B-CODE-MIMO-F02-未修复-低-数据库 CHECK constraint 不 enforce 非 cancelled terminal 不可携带 cancel link

- **入口/函数**: `dayu/host/durable/schema.py` — `host_runs` DDL CHECK constraint
- **文件(行号)**: `dayu/host/durable/schema.py:536-540`
- **输入场景**: Run 从 CANCELLING 经 RECOVERING 到 LOST 的 transition；或手动 SQL UPDATE 将 CANCELLED Run 改为 LOST 而不清除 `cancel_request_event_id`。
- **实际分支**: CHECK constraint `status NOT IN ('cancelling', 'cancelled') OR cancel_request_event_id IS NOT NULL` 只 enforce CANCELLING/CANCELLED 必须有 link，不 enforce 其它状态不可有 link。
- **预期行为**: 数据库层 enforce 完整的 `cancel_request_event_id` 语义约束：CANCELLED 必须有，非 CANCELLED 必须为 NULL。这与 `_validate_terminal_cancel_request_link` 的 Python 层校验一致。
- **实际行为**: 数据库层只 enforce 半条约束。Python 层有完整校验（`_validate_terminal_cancel_request_link`），但未被所有 terminal mutation 路径调用（见 F01）。
- **直接证据**: `schema.py:536-540` 的 CHECK constraint 只覆盖 CANCELLING/CANCELLED 非空要求。`state.py:5215` 的 Python 校验 `if cancel_request_event_id is not None: raise` 覆盖了非 cancelled 不可有 link，但只在 `terminal_unstarted_run_row` 中调用。
- **影响**: 与 F01 相同——数据卫生问题，非阻断性。数据库层无法阻止 stale cancel link 存在于非 CANCELLED terminal Run。
- **建议改法和验证点**: 可考虑添加更严格的 CHECK constraint（如 `(status IN ('cancelling', 'cancelled') AND cancel_request_event_id IS NOT NULL) OR (status NOT IN ('cancelling', 'cancelled') AND cancel_request_event_id IS NULL)`），但这要求所有 terminal mutation 路径在写入 terminal status 时同步清除或设置该字段。当前实现选择只在 Python 层做完整校验、数据库层做半条约束，这是合理的渐进方案，但需确保 F01 的 Python 层校验覆盖完整。
- **修复风险（低/中/高）**: 中（更严格 CHECK 需要所有 mutation 路径同步清除 cancel link）
- **严重程度（低/中/高/严重）**: 低

### P1B-CODE-MIMO-F03-未修复-低-watchdog event builder docstring 描述过时

- **入口/函数**: `dayu/host/durable/run_transition.py` — `_active_watchdog_attempt_cancelled_event_request`, `_active_watchdog_run_cancelled_event_request`, `_active_watchdog_cancelled_payload`
- **文件(行号)**: `dayu/host/durable/run_transition.py:4373`, `run_transition.py:4424`, `run_transition.py:4474`
- **输入场景**: 无——docstring 准确性问题，不影响运行时行为。
- **实际分支**: `cancel_request_event_id` 参数的 docstring 仍写 "从 RUN_CANCELLING payload 读取的 cancel request id"。
- **预期行为**: docstring 应反映当前实现：该值来自 Run row typed link (`RunRow.cancel_request_event_id`)，经 `read_cancel_requested_event_from_run_link` 校验同 Run `CANCEL_REQUESTED` 后传入。
- **实际行为**: docstring 描述已过时的来源（RUN_CANCELLING payload 解析）。
- **直接证据**: `run_transition.py:4373`: `cancel_request_event_id: 从 RUN_CANCELLING payload 读取的 cancel request id`；实际来源是 `run_transition.py:2351`: `cancel_request_event_id=cancel_requested.event_id`，其中 `cancel_requested` 来自 `read_cancel_requested_event_from_run_link`。
- **影响**: 维护性问题，不影响 correctness。
- **建议改法和验证点**: 更新三处 docstring，将 "从 RUN_CANCELLING payload 读取" 改为 "从 Run row typed cancel link 读取"。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

1. **`tests/host/stress_support.py` 终端 tuple 残留**: 该文件仍有私有 `_TERMINAL_EVENT_TYPES` 和 `_ALL_RUN_TERMINAL_EVENT_TYPES` tuple，未迁移到 `lifecycle_events` helper。按 implementation artifact 分类为 deferred test support，不在 P1-B focused migration 范围内。若后续 WU 扩展 stress test 覆盖面，应同步迁移。

2. **`cancel_cancelling_run_row` 不写 `cancel_request_event_id`**: 该函数从 CANCELLING → CANCELLED 时不显式写入 `cancel_request_event_id`，依赖 CANCELLING 状态已有的值。当前正确（CHECK constraint 保证 CANCELLING 非空），但若未来 schema 允许 CANCELLING → 非 CANCELLED terminal（如 LOST），stale link 会保留。建议在 `cancel_cancelling_run_row` 中显式写入当前值，消除对"值已存在"的隐式依赖。

3. **无 CANCELLING → LOST stale link 测试**: 当前测试覆盖了 CANCELLING → watchdog → CANCELLED 和 CANCELLING → orphan → LOST 路径，但没有覆盖 "CANCELLING Run 带 typed link 经 RECOVERING 到 LOST 时 stale link 保留" 的场景。这是因为 production 路径中 CANCELLING + accepted cancel 不会走到 LOST。若未来状态机扩展，应补充该测试。

4. **Schema 版本从 20 升到 21**: 按全新 schema 起库策略，不实现旧库兼容读取或迁移。旧 workspace 需要重建 Host DB。

## Review Conclusion

**pass-with-risks**

P1-B 实现正确完成了计划中的所有核心目标：
- `lifecycle_events.py` 作为 Host terminal/lifecycle event set 和 public outbox terminal item set 的唯一真源，所有 consumer 已迁移。
- `RUN_LOST` 不会制造 public outbox false lag 或 public terminal item。
- `cancel_request_event_id` 作为 typed durable link 写入所有 cancel lifecycle transition（通过 `mark_run_cancelling_row` 和 direct cancel row mutator）。
- active watchdog、engine ingest cooperative cancel、dispatch linked cancel、recovery accepted-cancel 判断均从 Run row typed link 读取，不再从 `RUN_CANCELLING` payload 解析。
- `_cancel_request_event_id_from_cancelling` 已删除，无 critical path 残留调用。
- 残留 grep 匹配已分类（allowed source-of-truth、allowed derived、deferred test support）。
- focused Host tests 通过（487+ passed），pyright 0 errors，`git diff --check` 通过。
- README/design 更新符合触发规则。

三个低严重性 finding 均为数据卫生或文档准确性问题，不阻断 merge。
