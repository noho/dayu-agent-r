# WU-TOOL-01 Slice 4 Code Review (MiMo)

**日期**: 2026-06-01
**审查范围**: 未提交 diff（`tests/host/test_toolruntime_duplicate_governance.py`、`dayu/host/README.md`、`tests/README.md`）+ implementation artifact
**未重跑验证**: DS 已验证 123 passed / pyright 0 errors / grep 只剩允许上下文；本次只抽查 diff 与 artifact 一致性。

---

## Findings

### Checklist 1: cross-Attempt test

**PASS**。`test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs`（L759-800）覆盖：

- 同 `run_id=_RUN_ID`，不同 attempt_id（`_ATTEMPT_ID` vs `"attempt-other"`）
- 两个工具均真实执行（`call_count=1` each）
- 两个 candidate 均为 `ToolFactKind.COMPLETED`（非 REUSE）
- 两个 candidate 均为 `DuplicateDecisionKind.ALLOW`
- 两个 candidate 均 `reuse_prior_event_refs == ()`
- 两个 candidate 的 `duplicate_key` 不同（L792-794）
- 两个 candidate 的 `duplicate_scope.attempt_id` 分别匹配各自 attempt（L795-800）

### Checklist 2: fresh ToolRuntime handle same attempt test

**PASS**。`test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior`（L803-837）覆盖：

- 新 `_executor()` 调用构造新的 `ToolRuntime` handle，保持同 `_ATTEMPT_ID` + 同 args
- restarted tool 真实执行（`call_count=1`）
- 两者 `duplicate_scope.attempt_id` 均为 `_ATTEMPT_ID`（L825-829）
- 两者 `duplicate_key` 相同（L830-832，因为 tool/args 相同，attempt 也相同）
- restarted candidate 为 `ToolFactKind.COMPLETED`、`DuplicateDecisionKind.ALLOW`、`reuse_prior_event_refs == ()`
- docstring 明确"该行为不是 correctness 前提"（L804）

### Checklist 3: dayu/host/README.md

**PASS**。

- L231-232: 新增 attempt-local in-memory 治理说明，明确新 Attempt / worker restart / Host restart 不继承旧索引、不从 EventLog 重建
- L233: 新增 `HostToolingOptions.duplicate_governance_policy` 说明，默认动作、按工具覆盖、模型可见治理文案、justification 参数名
- L239: 旧 "run-scoped duplicate governance registry" 改为 "attempt-local duplicate governance state"
- 无残留 run-scoped duplicate registry 旧说法

### Checklist 4: tests/README.md

**PASS**。

- L55: 命令入口补充 `test_tool_trace_projection.py`、`test_dispatch_scheduler.py`、`test_tooling_options.py`
- L130: 旧 "Run-scoped duplicate registry 的同 Run 共享 / 跨 Run 隔离 / scheduler 生命周期清理" 替换为 "attempt-scoped duplicate key / in-flight owner-waiter 串行化 / cross-Attempt fresh request / worker restart in-memory non-durable behavior / trace scope projection"

### Checklist 5: 术语 grep

**PASS**。剩余 `run-scoped` / `run-local` 匹配均属允许上下文：

| 位置 | 内容 | 判定 |
|------|------|------|
| `dayu/host/tool_runtime.py` L7,791,1129,1294,1736,2736,2797 | truncation cursor / manager / remaining ref | 允许：截断语义 |
| `dayu/host/README.md` L236 | truncation cursor | 允许：截断语义 |
| `dayu/host/README.md` L278 | compaction cancellation token | 允许：compaction 语义 |
| `dayu/host/api.py` L734 | truncation manager | 允许：截断语义 |
| `tests/host/test_local_proxy_engine_ingest.py` L290,308,371 | `run_id="run-local"` | 允许：测试数据 id |

duplicate governance 生产、测试和 README 文字未残留 run-scoped / run-local duplicate registry 说法。

### Checklist 6: 一般性问题

**PASS**。未发现：

- README 职责越界：Host README 只写 Host 层契约，tests README 只写测试事实
- 测试假阳性：断言覆盖 outcome kind、decision、refs、scope、key，无空断言或 tautology
- `Any` / `object` / 无类型签名：diff 中未引入
- 兼容路径：无兼容 re-export、wrapper、facade
- schema / public contract 越界：未修改 `dayu.host` 生产代码

---

## Verification

未重跑全量验证。DS 已验证：

- `pytest tests/host/test_toolruntime_duplicate_governance.py ...` 123 passed
- `pyright` 0 errors, 0 warnings
- `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run"` 只剩允许上下文

本次抽查确认 diff 与 implementation artifact 一致，无遗漏或矛盾。

---

## Conclusion

**Remaining blocking findings: 0**

Slice 4 的三处变更（cross-Attempt 断言强化、fresh handle restart 行为测试、README 术语迁移）均正确实现 checklist 要求。术语迁移完整，无残留旧语义。测试覆盖 cross-Attempt fresh request、in-memory non-durable restart、duplicate key scope、reuse refs 和 governance decision。README 职责无越界，无类型安全退化。
