# WU-LAYER-01 Slice 4 Code Review — DS

## 审查范围

当前 workspace 内 WU-LAYER-01 Slice 4 未提交改动：

- `dayu/host/README.md` — Host durable foundation bullet 更新
- `tests/host/test_run_attempt_transitions.py` — 两个 corrupted Run CAS guard 测试同步 Slice 3 row decode 边界
- `docs/host/host-core-followup-implementation-control.md` — 总控状态更新
- `docs/reviews/wu-layer-01-slice4-integration-verification-codex-20260602.md` — Slice 4 实现报告（仅作为上下文参考，不审查其内容）

## 审查方法

1. 逐文件审查 diff，追踪 `HostRowDecodeError` 从 `cancel_queued_run_row` / `cancel_running_run_row` → `_run_mutation_result` → `read_run_by_id` → `run_row_from_host_row` → `validate_terminal_event_refs_shape` 的完整调用链。
2. 与 Slice 3 `test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at` 横向对比 corrupted row CAS guard 测试模式。
3. 验证 Host README 变更范围、术语、职责边界。
4. 验证无 production source 修改、无 WU-LAYER-02 越界、无 public API / layering / 兼容 wrapper 变更。
5. 运行计划指定的 6 文件聚合 pytest 与全量 pyright。

## Findings

### Finding 01 — Control doc modification claim in implementation report [Low]

**Severity**: Low (report accuracy)

实现报告第 12 行声称：

> `docs/host/host-core-followup-implementation-control.md` 在本 slice 开始前已处于修改状态；本次未修改该文件。

但 `git diff HEAD -- docs/host/host-core-followup-implementation-control.md` 明确显示该文件在 Slice 4 中被修改：`implementation status`、`Slice 4 status`、`current slice`、`implementation artifact`、`validation`、`next entry point` 均更新为 Slice 4 对应值。这些是 Slice 4 的正确状态更新，符合总控文档推进规则。

**裁决**：不影响代码正确性，但在后续 gate 进入前应修正实现报告中的事实陈述，或确认该 diff 是否为 Slice 4 开始前的预修改。

### Finding 02 — Host README durable foundation bullet 更新正确 [Info]

**Severity**: Info (validation)

原句：

> 主连接与 secondary durable connections 都会执行完整当前 schema validation。

改为：

> 主连接与 secondary durable connections 都会执行当前 schema validation，校验 schema version、required object 存在性与 required object 定义一致性。

验证结论：
- 变更准确反映 Slice 1 schema definition validation 的稳定能力扩展。
- 未写实现细节（无 `sqlite_master`、`_normalize_schema_sql`、`_validate_required_object_definitions` 等内部实现概念）。
- 属于 Host durable foundation 稳定开发手册信息，不越界到根目录 README / `dayu/README.md` / `tests/README.md`。
- 无 stale 术语、无旧架构表述。
- 符合 AGENTS.md 中 `dayu/host/README.md` 的职责边界：Host 开发手册，只写接口、公共契约、架构、边界、执行路径、状态机、事件流、关键机制、扩展点。

### Finding 03 — Two corrupted Run CAS guard tests correctly sync with Slice 3 row decode boundary [Verified]

**Severity**: Verified (correctness)

#### 3.1 CAS 是否仍拒绝 corrupted row

是。两个测试均通过 `PRAGMA ignore_check_constraints = ON` 构造测试专用 corrupted row（非终态 Run 携带 non-null terminal refs）。CAS `WHERE` 子句包含 `_TERMINAL_REFS_UNSET_WHERE_SQL`（`terminal_event_id IS NULL AND terminal_event_sequence IS NULL AND terminal_at IS NULL`），corrupted row 不满足条件，`UPDATE rowcount = 0`。

#### 3.2 `HostRowDecodeError` 证明 CAS 不覆盖 corrupted row

`_run_mutation_result` 在 `rowcount=0` 后调用 `read_run_by_id` → `run_row_from_host_row` → `validate_terminal_event_refs_shape`。corrupted row 的 `status=QUEUED`（非终态）但 `terminal_event_id` 非空，触发 `HostDurableError("non-terminal Run terminal refs must be unset")`，在 `run_row_from_host_row:998` 被 `_wrap_row_decode_shape_error` 转换为 `HostRowDecodeError` 并向调用方传播。

`HostRowDecodeError` 被抛出而非返回 mutation result，恰恰证明 CAS 成功拒绝了 corrupted row：若 CAS 错误匹配并更新，row 状态将变为 `CANCELLED`（终态）+ 有效 terminal refs，decode 将通过。

#### 3.3 与 Slice 3 WaitRecord corrupted CAS 测试一致性

Slice 3 的 `test_wait_record_terminal_cas_rejects_corrupted_waiting_terminal_at`（`tests/host/test_wait_record_state.py:763`）使用完全相同的模式：

| 维度 | Slice 3 WaitRecord | Slice 4 Run (本次) |
|---|---|---|
| 构造方式 | `PRAGMA ignore_check_constraints=ON` + UPDATE | 同 |
| CAS 函数 | `mark_wait_record_resolved_row` | `cancel_queued_run_row` / `cancel_running_run_row` |
| CAS 拒绝证据 | `pytest.raises(HostRowDecodeError, match=...)` | 同 |
| 错误消息 | `"waiting wait record terminal_at"` | `"non-terminal Run terminal refs"` |

两端完全一致：测试专用 corrupted row → CAS 拒绝 → row decode 边界检测 corruption → `HostRowDecodeError`。

#### 3.4 不掩盖生产回归

- 生产路径中 DDL CHECK 约束已阻止非终态 Run 携带 terminal refs，不会产生此类 corrupted row。
- `HostRowDecodeError` 是 Slice 3 row decode 边界的设计行为，不是本 slice 引入的新错误类型。
- 旧测试通过 `result.row.terminal_event_id` 直接读取 corrupted 数据判断 CAS 结果，本质上是绕过 decode 边界消费 corrupted row。改为 assert `HostRowDecodeError` 反而更早暴露 corruption，不静默传播 corrupted 数据。
- `HostRowDecodeError` 是 `HostDurableError` 子类，已有 broad catch 调用方不受影响。

### Finding 04 — 无生产源码修改 [Verified]

**Severity**: Verified (scope)

`git diff HEAD -- 'dayu/**/*.py'` 无输出。所有 `.py` 生产文件未被修改。

- `dayu/host/__init__.py` 无变更。
- `dayu/host/durable/__init__.py` 无变更。
- 无 public API 变更。
- 无 re-export、wrapper、facade 引入。

### Finding 05 — 无 WU-LAYER-02 越界 [Verified]

**Severity**: Verified (scope boundary)

未观察到 shared helper consolidation、validation/redaction/JSON helper 迁移、runtime import 变更。Host README 更新仅在 durable foundation bullet 范围内，不涉及 WU-LAYER-02 的层中立 helper 收敛。

### Finding 06 — 测试 docstring 与类型合规 [Verified]

**Severity**: Verified (compliance)

两个测试函数及其内部 `operation` 嵌套函数均有完整中文 docstring：

- `:param tmp_path: pytest 临时目录。`
- `:returns: \`\`None\`\`。`
- `:raises AssertionError: ...` 或 `:raises HostRowDecodeError: ...`

类型标注：`tmp_path: Path`、`-> None`、`transaction: HostTransaction`，无 `Any`/`object`/untyped。嵌套函数 `operation` 是 `transaction_runner.run_write()` 的回调参数，属于测试中合理使用，非无意义嵌套。

### Finding 07 — 聚合验证覆盖 [Verified]

**Severity**: Verified (plan coverage)

计划要求的 6 个 Host test files：
```
pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_run_attempt_transitions.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py
```

验证结果：**136 passed in 1.16s**。

pyright：**0 errors, 0 warnings, 0 informations**。

完全满足计划 section 8 "Tests / Validation Commands" 和 section 9 "Minimum expected assertions" 要求。

## Open Questions

无。

## Validation

- [x] 聚合 pytest 6 文件 136 passed
- [x] pyright 0 errors
- [x] 无生产 `.py` 源码修改
- [x] 无 public API 变更
- [x] 无 WU-LAYER-02 越界
- [x] 无兼容 wrapper/re-export
- [x] Host README 职责边界合规
- [x] CAS guard 测试与 Slice 3 WaitRecord 模式一致

## Verdict

**PASS** — 无 blocking/high/medium finding。

Finding 01（实现报告 control doc 修改声明不准确）为低严重报告准确性问题，不影响代码正确性、测试语义或文档准确性。建议在进入 ready-to-open-draft-PR 前修正实现报告中的事实陈述，但不需要 fix/re-review loop。

所有变更均在 Slice 4 "Integration Verification / README Sync" allowed files 范围内，未修改生产源码，测试同步正确对齐 Slice 3 row decode 边界，Host README 更新准确且不越界。
