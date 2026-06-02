# WU-LAYER-01 Slice 4 Code Review — MiMo

## Review Scope

| Item | Value |
|---|---|
| branch | `refactor/host-layer-followup-wu-layer-01-02` |
| reviewed files | `dayu/host/README.md`, `tests/host/test_run_attempt_transitions.py`, `docs/reviews/wu-layer-01-slice4-integration-verification-codex-20260602.md`, `docs/host/host-core-followup-implementation-control.md` |
| design source | `docs/host/design.md` |
| plan source | `docs/host/wu-layer-01-durable-row-primitive-cleanup-plan.md` |
| control doc | `docs/host/host-core-followup-implementation-control.md` |

## Findings (ordered by severity)

### F-1 [INFO] Host README 更新准确且在范围内

`dayu/host/README.md:297` 将 "完整当前 schema validation" 改为 "当前 schema validation，校验 schema version、required object 存在性与 required object 定义一致性"。

- 方向正确：Slice 1 新增了 required object definition validation，README 描述从模糊的"完整"变为具体三项校验内容。
- 未越界：不写实现细节（如 `_expected_schema_sql_by_name`、`_normalize_schema_sql`），不写内部 helper 名称。
- 未侵入其它 README：根目录 README、`dayu/README.md`、`tests/README.md` 均未修改，符合计划 Slice 4 规定。
- 无旧术语残留。

**结论**：PASS，无需修改。

### F-2 [INFO] corrupted Run CAS guard 测试从 mutation result 分类改为 HostRowDecodeError — 合理但需记录行为变化

两个测试 `test_cancel_queued_run_row_requires_empty_terminal_refs` 和 `test_cancel_running_run_row_requires_empty_terminal_refs` 原来断言：
- queued: `INVALID_STATE` + 保留原 terminal_event_id
- running: `CAS_LOST` + 保留原 terminal_event_id

现在断言 `HostRowDecodeError` with `match="non-terminal Run terminal refs"`。

**根因分析**：

1. Slice 3 在 `run_row_from_host_row` 中加入了 `validate_terminal_event_refs_shape` decode-time 校验。
2. `_run_mutation_result` 在 `rowcount == 0` 时调用 `read_run_by_id` 读取最新 row。
3. corrupted row（非终态 status 但有 terminal refs）被 `run_row_from_host_row` 读取时触发 `validate_terminal_event_refs_shape`，抛出 `HostRowDecodeError`。
4. 该异常在 `_run_mutation_result` 调用 `read_run_by_id` 时传播出来，早于 mutation result 分类。

**是否仍能证明 CAS 不覆盖 corrupted row**：是。CAS WHERE 子句包含 `_TERMINAL_REFS_UNSET_WHERE_SQL`（`terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`），corrupted row 已有 terminal refs，WHERE 不匹配，`rowcount == 0`，CAS 确实未覆盖。测试现在验证的是：corrupted row 在被读取时即被 row decode boundary 拒绝，比原来只检查 mutation result 分类更严格。

**是否和 Slice 3 WaitRecord corrupted CAS 测试一致**：是。Slice 3 的 WaitRecord corrupted CAS 测试同样断言 `HostRowDecodeError`，本次修改使 Run corrupted CAS 测试语义对齐。

**是否掩盖了真实生产回归**：否。`HostRowDecodeError` 是 `HostDurableError` 子类，上层 catch `HostDurableError` 的代码不受影响。且该行为变化是 Slice 3 row decode boundary 加强的自然结果，不是回归。

**结论**：PASS。测试变更合理，语义比原来更严格。

### F-3 [INFO] 控制文档更新仅反映状态推进

`docs/host/host-core-followup-implementation-control.md` 的变更仅更新了：
- implementation status 从 "Slice 3 accepted; Slice 4 pending" 到 "Slice 4 implementation complete; code review pending"
- Slice 4 status 行
- current slice 从 "Slice 4 pending" 到 "Slice 4 code review gate"
- implementation artifact 列表追加 Slice 4 verification report
- validation 从 Slice 3 结果到 Slice 4 聚合结果
- next entry point 更新

无内容性变更，纯状态推进。

**结论**：PASS。

### F-4 [INFO] Slice 4 verification report 覆盖完整

`docs/reviews/wu-layer-01-slice4-integration-verification-codex-20260602.md` 包含：
- Changed Files 清单
- README/doc sync decision 与理由
- 首次聚合验证失败与修正过程
- 最终聚合验证 136 passed
- pyright 0 errors
- Residual Risks

**结论**：PASS。

### F-5 [INFO] 无生产源码修改

`git diff HEAD -- dayu/` 确认仅 `dayu/host/README.md` 有变更，无 `.py` 生产源码修改。符合 Slice 4 "No source changes unless verification exposes a slice regression" 规定。

**结论**：PASS。

### F-6 [INFO] 无 WU-LAYER-02 越界

- 未新增 `_row_rules.py` 或其它 durable-private 模块。
- 未修改 `dayu/runtime`。
- 未引入 public API 变更、layering 变更或兼容 wrapper。
- 未修改 schema version。

**结论**：PASS。

## Open Questions

无。

## Validation

| Check | Result |
|---|---|
| `pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py` | 136 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| 生产源码修改 | 无（仅 README） |
| 中文 docstring 合规 | 修改的测试函数 docstring 含 `:param`、`:returns`、`:raises` |
| README 职责边界 | 仅 `dayu/host/README.md`，未越界 |
| 六个 Host test files 覆盖 | 是（计划要求的六个文件均在聚合验证命令中） |

## Verdict

**PASS**。Slice 4 集成验证与 README 同步改动无阻塞问题。测试变更合理反映了 Slice 3 row decode boundary 的自然行为变化，README 更新准确且在范围内，无生产源码修改，无 WU-LAYER-02 越界。
