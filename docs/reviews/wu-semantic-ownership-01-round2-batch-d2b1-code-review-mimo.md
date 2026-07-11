# D2b1 Code Review — AgentMiMo

## 审查范围

- Finding: `144159-05` — cancelled `raw_tool_outcome` 在普通 ToolRuntime 与 wait resolution 路径的 canonical atom/codec 分叉。
- Baseline: D2a accepted commit `4f4d23db`。
- Changed files: 9 files（1 新增 + 8 修改）。

## 审查结论

**未发现实质性问题。**

## 逐项审查

### 1. `dayu.host.accepted_tool_outcome` 是否为正确的 Host owner boundary

**通过。**

`accepted_tool_outcome.py` 定义了 `AcceptedToolOutcome` 封闭联合（`ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome`），并提供三个公共函数：
- `accepted_tool_outcome_json` — canonical JSON atom 投影
- `accepted_tool_outcome_digest` — sha256 digest
- `accepted_tool_outcome_inline_size_bytes` — UTF-8 字节数估算

该模块位于 `dayu.host` 包内，只依赖 `dayu.contracts` 类型与 `dayu.host.durable.codec`，不反向依赖 ToolRuntime、waiting 或 run_input。`_tool_result_meta_json` 作为模块级私有函数内聚于此，不再分散在 `tool_runtime.py` 和 `wait_resolution_digest.py` 中。

Owner boundary 划分正确。

### 2. 普通 ToolRuntime 与 wait resolution 是否使用 identical canonical atom/digest

**通过。**

- `tool_runtime.py` 的 `_tool_outcome_json` / `_tool_outcome_digest` / `_tool_outcome_inline_size_bytes` 对 accepted outcomes 委托给 `accepted_tool_outcome_json` / `accepted_tool_outcome_digest` / `accepted_tool_outcome_inline_size_bytes`。
- `waiting.py` 的 `_wait_resolution_payload_plan` 对 completed/failed 构造 `ToolCompletedOutcome`/`ToolFailedOutcome` 后调用同一 `accepted_tool_outcome_json`；cancelled 直接使用 `outcome.result`（已是 `ToolCancelledOutcome`）。
- `test_accepted_tool_outcome_codec.py::test_completed_failed_cancelled_share_single_accepted_outcome_atom` 断言两条 producer 路径输出 identical atom 和 digest。

### 3. wait resolution 是否将 wait-specific payload/provider refs 留在 atom 外

**通过。**

`_wait_resolution_payload_plan` 返回的 `_WaitResolutionPayloadPlan` 中：
- `result_json` = accepted tool outcome atom（不含 payload_ref）
- `payload_ref` / `payload_digest` / `provider_status_ref` 作为独立字段

`test_cancelled_wait_payload_ref_does_not_reshape_accepted_atom` 明确断言 `payload_ref` 存在但不改变 `result_json` atom 形状。

### 4. `resolve_wait_outcome_json` digest material 是否 coherent

**通过。**

旧结构：`{"kind": "cancelled", "result": {…cancelled body…}, "payload_ref": …}`
新结构：`{"kind": "cancelled", "tool_outcome": {…canonical atom…}, "payload_ref": …}`

字段从 `result` 改为 `tool_outcome`，payload_ref 保持在外层 envelope。`wait_resolution_digest` 使用 `resolve_wait_outcome_json` 输出作为 digest material 的 `outcome` 字段，整体 coherent。

按"全新 schema 起库"处理，无需兼容旧 digest shape。

### 5. RunInput resume 是否消费 canonical `raw_tool_outcome` 无兼容 fallback

**通过。**

`run_input.py::_resume_wait_tool_message_content` 改为：
- 从 `tool_result_payload.get("raw_tool_outcome")` 读取 canonical atom
- completed/failed 通过 `_required_resume_tool_result_body` 读取 `result` 子字段
- cancelled 直接消费整个 atom（`kind`, `reason`, `message`, `hint`, `meta`）

不再读取旧 `result.result` 嵌套 shape。无 `hasattr`/`getattr`/loose parsing 兼容分支。

`test_resume_wait_cancelled_tool_content_consumes_canonical_raw_outcome` 断言 resume 从 canonical atom 正确提取 cancelled 字段。

### 6. completed/failed/cancelled 路径是否全部 coherent

**通过。**

三条路径共享同一 codec：
- **普通 ToolRuntime**: `_tool_outcome_json` → `accepted_tool_outcome_json`
- **wait resolution payload plan**: `accepted_tool_outcome_json`（completed/failed 构造 wrapper，cancelled 直接传入）
- **wait resolution digest**: `resolve_wait_outcome_json` → `accepted_tool_outcome_json`
- **RunInput resume**: 消费 `raw_tool_outcome` canonical atom

`test_accepted_tool_outcome_codec.py` 对 completed/failed/cancelled 三种 outcome 都断言了 parity。

### 7. 测试是否断言 owner-level 行为

**通过（附说明）。**

- `test_accepted_tool_outcome_codec.py` 导入 `_tool_outcome_json`、`_tool_outcome_digest`（`tool_runtime.py` 私有）和 `_wait_resolution_payload_plan`（`waiting.py` 私有）。
- 这些导入的目的是验证 refactoring 后私有 producer 与公共 codec 的 parity，属于 refactoring 验证测试，不是复制生产逻辑。
- 测试断言的是公共 codec 的输出（`accepted_tool_outcome_json` / `accepted_tool_outcome_digest`），私有函数只是被调用来验证委托关系。
- 此模式在 refactoring 阶段可接受；长期可考虑通过公共 API 边界替代。

### 8. README no-update 决策

**通过。**

已确认 `dayu/host/README.md` 的 `Agent更新约束` 与 `tests/README.md` 的 `README 更新边界`。本轮改动：
- 未改变 Host public API
- 未改变架构边界
- 未改变测试目录层级或运行方式

决策正确。

## 观察（非 finding）

1. **codec 测试 meta=None only**: `test_accepted_tool_outcome_codec.py` 所有 fixture 使用 `meta=None`。`_tool_result_meta_json` 对 non-None meta 的投影（`tool_name`, `isoformat` 时间戳）未被测试覆盖。建议后续补充 `ToolResultMeta` 有值的 case。

2. **测试导入私有 producer**: `test_accepted_tool_outcome_codec.py` 导入 `_tool_outcome_json`、`_wait_resolution_payload_plan` 等私有函数。这是 refactoring parity 验证的 pragmatic 选择，不是结构性缺陷。

## 最终结论

D2b1 实现正确闭合了 `144159-05`。`dayu.host.accepted_tool_outcome` 作为 canonical atom owner 边界划分合理，普通 ToolRuntime 与 wait resolution 路径通过同一 codec 产生 identical atom/digest，wait-specific 元数据留在 atom 外，RunInput resume 无兼容 fallback。completed/failed/cancelled 三条路径全部 coherent。测试覆盖充分。

**未发现实质性问题。**

---

Artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b1-code-review-mimo.md`
