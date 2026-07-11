# WU-SEMANTIC-OWNERSHIP-01 / Round2 Batch D2b1 Code Review — AgentDS

## 范围

本 review 仅覆盖 D2b1 workspace changes，对应 finding `144159-05`：cancelled accepted tool outcome 在普通 ToolRuntime 与 wait resolution 路径的 canonical atom/codec 分叉修复。

Baseline commit: `4f4d23db`（D2a accepted）。

### 变更文件

| 文件 | 角色 |
|------|------|
| `dayu/host/accepted_tool_outcome.py` | **新增**：Host accepted tool outcome canonical atom owner |
| `dayu/host/tool_runtime.py` | 普通 ToolRuntime 路径复用 canonical codec |
| `dayu/host/durable/wait_resolution_digest.py` | wait resolution digest 改用 canonical `tool_outcome` atom |
| `dayu/host/waiting.py` | `_wait_resolution_payload_plan` 复用 canonical codec |
| `dayu/host/run_input.py` | resume 消费 `raw_tool_outcome` canonical atom |
| `tests/host/test_accepted_tool_outcome_codec.py` | **新增**：codec owner parity 测试 |
| `tests/host/test_toolruntime_executor.py` | 进口 `accepted_tool_outcome` 符号 |
| `tests/host/test_resolve_wait_command.py` | 新增 cancelled canonical atom 断言 |
| `tests/host/test_run_input_builder.py` | 新增 cancelled resume 消费 canonical atom 测试 |

## Review Emphasis 逐项分析

### 1. `dayu.host.accepted_tool_outcome` 是否为正确的 Host owner boundary？

**结论：是。**

- `accepted_tool_outcome.py` 定义了 `AcceptedToolOutcome` 封闭联合（`ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome`），并提供了三个 projection helper：
  - `accepted_tool_outcome_json()` — canonical JSON atom
  - `accepted_tool_outcome_digest()` — canonical sha256 digest
  - `accepted_tool_outcome_inline_size_bytes()` — inline size 估算
- 该模块位于 `dayu.host` 层，只依赖 `dayu.contracts.tool_outcome`（公共契约）和 `dayu.host.durable.codec`（Host 层基础设施），无上层依赖。这是正确的分层位置。
- ToolRuntime（`_tool_outcome_json` / `_tool_outcome_digest` / `_tool_outcome_inline_size_bytes`）和 wait resolution（`_wait_resolution_payload_plan` / `resolve_wait_outcome_json`）均作为消费者从该 owner 读取 canonical atom，符合单一直源原则。
- `_tool_result_meta_json` 作为模块级私有 helper，统一了 completed / failed / cancelled 的 meta 投影，避免了三个 outcome 类型各自重复 meta 序列化逻辑。

### 2. 普通 ToolRuntime 与 wait resolution 是否对同一 cancelled outcome 使用相同的 canonical atom/digest？

**结论：是，且测试已验证。**

- `_tool_outcome_json(ToolCancelledOutcome(...))` 在 `tool_runtime.py:7281-7284` 委托给 `accepted_tool_outcome_json()`。
- `_wait_resolution_payload_plan` 在 `waiting.py:1348-1360` 对 cancelled 直接调用 `accepted_tool_outcome_json(outcome.result)`，其中 `outcome.result` 是 `ToolCancelledOutcome`。
- `_tool_outcome_digest` 在 `tool_runtime.py:7017-7020` 委托给 `accepted_tool_outcome_digest()`。
- `payload_plan.outcome_digest` 在 `waiting.py:1353` 同样调用 `accepted_tool_outcome_digest(outcome.result)`。
- 测试 `test_completed_failed_cancelled_share_single_accepted_outcome_atom` 显式验证了三条路径（completed / failed / cancelled）的 `_tool_outcome_json`、`_tool_outcome_digest`、`payload_plan.result_json`、`payload_plan.outcome_digest` 全部一致。

**唯一值得注意的结构不对称**：`_wait_resolution_payload_plan` 对 completed 和 failed 需要构造包装对象（`ToolCompletedOutcome(outcome.result)`、`ToolFailedOutcome(outcome.result)`），而对 cancelled 直接使用 `outcome.result`。这是因为 `ResolveWaitCompletedOutcome.result` 的类型是 `ToolResultSuccess`（非 outcome wrapper），而 `ResolveWaitCancelledOutcome.result` 已经是 `ToolCancelledOutcome`。这是 API contract 层的类型差异，不是 codec bug。codec 层对此无感知——它只接受 `AcceptedToolOutcome` 封闭联合。

### 3. wait resolution 是否把 wait-specific payload/provider refs 留在 atom 外部？

**结论：是。**

- `resolve_wait_outcome_json`（`wait_resolution_digest.py:55-90`）对 completed / failed / cancelled 的 envelope 结构是：
  ```json
  {
    "kind": "completed|failed|cancelled",
    "tool_outcome": <canonical accepted_tool_outcome_json atom>,
    "payload_ref": <HostPayloadRef JSON | null>
  }
  ```
- `tool_outcome` 字段内是纯 canonical atom，不含任何 `payload_ref`、`provider_status_ref`、`wait_id` 等 wait 治理字段。
- `_wait_resolution_payload_plan`（`waiting.py:1311-1374`）同样把 wait-specific 的 `payload_ref`、`payload_digest`、`resolution_kind` 放在 `_WaitResolutionPayloadPlan` 的独立字段中，不混入 `result_json`（即 canonical atom）。

### 4. `resolve_wait_outcome_json` 的 digest material 变更是否 coherent？

**结论：是，无冲突。**

- 旧 digest envelope 使用字段名 `result` 承载 outcome JSON；新 envelope 使用 `tool_outcome`。
- `wait_resolution_digest()`（`wait_resolution_digest.py:34-52`）对 `sha256_digest_json({"wait_id": ..., "idempotency_key": ..., "outcome": resolve_wait_outcome_json(...)})` 计算 digest。`resolve_wait_outcome_json` 返回的 `tool_outcome` 字段内容是 `accepted_tool_outcome_json()` 的产物——与普通 ToolRuntime 的 digest 输入完全相同。
- 这意味着：同一个 `ToolCancelledOutcome`，无论是通过普通 ToolRuntime accept 路径还是 wait resolution 路径，其 canonical digest 均一致。
- `_wait_late_rejection_digest`（`waiting.py:1226-1255`）也调用了 `resolve_wait_outcome_json(request.outcome)`，复用同一 digest 结构，没有分叉。
- lost outcome 独立处理（`resolve_wait_lost_result_json`），不经过 `accepted_tool_outcome_json`——这是正确的，因为 lost 是 wait 生命周期概念，不是工具 outcome。

### 5. RunInput resume 是否消费 canonical `raw_tool_outcome` 且无兼容 fallback？

**结论：是，无兼容 fallback。**

- `_resume_wait_tool_message_content`（`run_input.py:3556-3580`）从 `raw_tool_outcome` 字段读取 canonical atom：
  - `kind == "completed"` → 从 `result.value` 提取内容
  - `kind == "failed"` → 从 `result.error` / `result.message` / `result.hint` 提取内容
  - `kind == "cancelled"` → 从 `reason` / `message` / `hint` 直接提取（canonical cancelled atom 的顶层字段）
- 搜索验证：全仓无 `result.result`、`resolve_wait_completed_result_json`、`resolve_wait_failed_result_json`、`resolve_wait_cancelled_result_json`、`_tool_cancelled_json` 等旧 shape 残留。
- 测试 `test_resume_wait_cancelled_tool_content_consumes_canonical_raw_outcome` 直接验证 cancelled resume 消费 canonical atom。
- 测试 `test_resolve_wait_tool_cancelled_resumes_as_resolved_wait` 验证了完整的 end-to-end cancelled wait → resolve → resume → LLM tool message 链路。

### 6. completed / failed / cancelled 三条路径在共享 codec 后是否全部 coherent？

**结论：是。**

- 三条路径的 canonical atom 结构：
  - **completed**：`{"kind": "completed", "result": {"ok": ..., "value": ..., "meta": ...}}`
  - **failed**：`{"kind": "failed", "result": {"ok": ..., "error": ..., "message": ..., "hint": ..., "meta": ...}}`
  - **cancelled**：`{"kind": "cancelled", "reason": ..., "message": ..., "hint": ..., "meta": ...}`
- 三者共享：
  - 同一 `meta` 投影 helper（`_tool_result_meta_json`）
  - 同一 digest 计算（`sha256_digest_json(accepted_tool_outcome_json(...))`）
  - 同一 inline size 估算（`canonical_json_dumps(accepted_tool_outcome_json(...))`）
- ToolRuntime accept barrier（`ToolFactAcceptCandidate` 的 `__post_init__`）对 completed / failed / cancelled 都要求 `raw_tool_outcome` 非 None（`_require_raw_tool_outcome`），validation gate 一致。
- wait resolution 的 `_WaitResolutionPayloadPlan` 对 completed / failed / cancelled 均使用 `accepted_tool_outcome_json` / `accepted_tool_outcome_digest`，不区分对待。

### 7. 测试是否断言 owner 级 contract 行为？

**结论：是。**

- `test_accepted_tool_outcome_codec.py` 断言的是 **producer 一致性**（ordinary vs wait 路径产出相同 atom/digest），而非测试私有 helper 的内部实现细节。这是 owner 级 contract 测试。
- `test_cancelled_wait_payload_ref_does_not_reshape_accepted_atom` 验证了 payload_ref 只影响 wait envelope，不改变 canonical atom——这是 owner boundary 的关键 contracts。
- `test_resolve_wait_command.py:590-595` 断言 `raw_tool_outcome`、`result`、`outcome_digest` 三个字段均等于 canonical 值——验证了 durable write 的 contract。
- `test_run_input_builder.py:835-854` 验证 resume consumer 只依赖 canonical `raw_tool_outcome` 字段——验证了 consumer contract。
- 测试 fixture `_append_resume_wait_projection_events`（`test_run_input_builder.py:5717`）按新 schema 构造 `raw_tool_outcome = result`（均为 canonical shape），未保留旧 shape 兼容读取。符合项目指令要求。

### 8. README no-update 决策是否合规？

**结论：合规。**

- 本轮改动未改变 Host public API、开发手册中的稳定架构边界、测试目录层级、测试运行方式或测试维护规则。实现 artifact 声明已阅读 `dayu/host/README.md` 和 `tests/README.md` 的更新约束并确认无需更新。未发现违反触发规则的情况。

## Adversarial Failure Pass

以下 adversarial 场景均已检查，未发现实质性问题：

### A1. cancelled meta 为 None 的边界
- `_tool_result_meta_json(None)` 返回 `None`（JSON `null`），`accepted_tool_outcome_json` 正确处理该情况。已验证：测试中的 cancelled outcome 使用 `meta=None`，canonical atom 正确输出 `"meta": None`。

### A2. completed value 为非 object 类型
- `_resume_wait_completed_tool_content` 通过 `isinstance(value, Mapping)` 判断：object 类型直接返回 dict，非 object 包装为 `{"content": value}`。该逻辑与 D2a 保持一致，本轮未修改。

### A3. `ToolAwaitingOutcome` 不被错误路由到 accepted codec
- `_tool_outcome_json` 对 `ToolAwaitingOutcome` 使用独立分支，不委托给 `accepted_tool_outcome_json`。
- `accepted_tool_outcome_json` 对非 `AcceptedToolOutcome` 类型抛出 `TypeError`。
- 两条防线确保 awaiting outcome 不会错误产生 accepted canonical atom。

### A4. `resolve_wait_outcome_json` 对 lost 的独立处理
- lost 不经过 `accepted_tool_outcome_json`，使用自己的 `resolve_wait_lost_result_json`。这是正确的——lost 不是工具 outcome，是 wait 生命周期终态。
- `_wait_resolution_payload_plan` 对 lost 的 `result_json` 使用 `{"kind": "lost", "result": _tool_lost_json(...)}` 的嵌套结构，与 completed/failed/cancelled 的 canonical atom 形状不同。这不会造成混淆，因为 lost 路径走 terminal（不 resume），且 digest 计算使用独立的 `sha256_digest_json({"kind": "lost", "result": ...})`。

### A5. duplicate accepted outcome 的幂等重放
- `_wait_resolution_payload_plan` 仅在首次 resolve 时构造，幂等重放路径（`_replay_terminal_resolution_or_none`）不重新计算 payload plan。这部分逻辑本轮未修改，无回归风险。

### A6. `_tool_outcome_json` 对非 accepted 类型的 fallback
- `_tool_outcome_json` 仅处理 `AcceptedToolOutcome` 和 `ToolAwaitingOutcome`，其他类型抛出 `TypeError`。这与 `accepted_tool_outcome_json` 的行为一致（对非 `AcceptedToolOutcome` 抛出 `TypeError`）。

## 综合评价

**未发现实质性问题。**

本轮 D2b1 实现正确、完整地解决了 `144159-05` 的语义所有权分叉：

1. **Owner boundary 正确**：`dayu.host.accepted_tool_outcome` 作为 Host 层 accepted tool outcome 的 canonical atom owner，位置和职责边界清晰。
2. **单一直源达成**：普通 ToolRuntime 和 wait resolution 两条 producer 路径通过 `accepted_tool_outcome_json` / `accepted_tool_outcome_digest` / `accepted_tool_outcome_inline_size_bytes` 共享同一 canonical atom，消除了旧的 completed/failed/cancelled shape 分叉。
3. **wait envelope 不污染 atom**：`resolve_wait_outcome_json` 将 canonical `tool_outcome` atom 与 wait-specific `payload_ref` 保持分离，digest 计算 coherent。
4. **resume consumer 清洁**：`_resume_wait_tool_message_content` 直接从 canonical `raw_tool_outcome` 字段读取，无兼容 fallback、无旧 shape 解析。
5. **测试覆盖充分**：owner parity 测试（ordinary vs wait producer 一致性）、cancelled resume consumer 测试、cancelled end-to-end 测试均到位，断言 owner 级 contract 行为。
6. **类型安全**：pyright 0 errors，所有 codec helper 均有完整类型标注，`AcceptedToolOutcome` 封闭联合确保类型穷尽。

### 残留风险

- 未跑全量 pytest；覆盖范围为受影响 Host tests + owner codec parity + direct resolve wait resume continuity + RunInput canonical consumer + 全量 pyright + diff whitespace。
- `resolve_wait_outcome_json` 的 digest envelope 字段从 `result` 改为 `tool_outcome` 后，任何外部系统若消费了旧 digest 形状将不兼容。本轮按"全新 schema 起库"处理，未提供兼容迁移。该风险已在实现 artifact 中声明。
