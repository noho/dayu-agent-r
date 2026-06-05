# WU-DUR / WU-OBS / WU-CM Closeout — Slice 1 Code Review

## Scope

- Mode: current changes (workspace diff) — phaseflow Slice 1 code review gate
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main` (83cf38d8)
- Review artifact path: `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-ds.md`
- Design source: `docs/host/design.md`, Slice 0 accepted commit `83cf38d8`
- Plan artifact: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- Implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice1-implementation-codex.md`
- Included scope: all workspace-changed production and test files in `dayu/host/` + `tests/host/`
- Excluded scope: Slice 2-7 implementation, `docs/` control doc changes, README modifications beyond review verification
- Parallel review coverage: 无

## Findings

### F1-未修复-中-`ToolAcceptCall.accepted_arguments` optional default 创造测试与生产间语义鸿沟

- **入口/函数**: `ToolAcceptCall.__post_init__` → `_validate_tool_accept_call`
- **文件(行号)**: `dayu/host/tool_runtime.py:448-449`, `dayu/host/tool_runtime.py:4311-4321`
- **输入场景**: 构造 `ToolAcceptCall` 时不显式传入 `accepted_arguments`
- **实际分支**: `__post_init__` 走到 `_validate_tool_accept_call`，第 4311 行 `if call.accepted_arguments is not None:` 为 `False`，跳过 digest 一致性校验
- **预期行为**: 应确保所有构造路径（含测试 helper）都不会漏掉 `accepted_arguments`
- **实际行为**: 当 `accepted_arguments` 使用默认值 `None` 时，`__post_init__` 静默跳过校验。写入 accepted fact 时才由 `_required_accepted_arguments` (`tool_runtime.py:5227-5229`) 抛出 `HostPayloadReferenceError`。双防线设计成立，但默认值 `None` 使得测试 helper 可以不显式传参而通过构造阶段，只在实际行动（写 EventLog）时才暴露
- **直接证据**: 
  - `tool_runtime.py:448`: `accepted_arguments: Mapping[str, JsonValue] | None = None`
  - `tool_runtime.py:4311`: `if call.accepted_arguments is not None:` — 条件判断使得 `None` 值静默通过
  - `tool_runtime.py:5227-5229`: `_required_accepted_arguments` raise when `None`
  - 测试中现有 helper 已正确更新（`_candidate_call` 在 `test_toolruntime_accept_barrier.py:1375-1378`，`_fact_kind_candidate` 在 `test_toolruntime_accept_barrier.py:1312-1316`），但未来测试 helper 可能遗漏
- **影响**: 测试构造 `ToolAcceptCall` 但忘记设置 `accepted_arguments` 时，构造阶段不报错；如果该 helper 只在低层测试使用且不经过 accept barrier 写入路径，`accepted_arguments=None` 将静默保留，测试失去对 durable truth 的验证能力
- **建议改法和验证点**: 将 `accepted_arguments` 改为必填字段（移除 `| None` 默认值），同步更新所有测试 fake ack helper。或至少在 `__post_init__` 中将 `None` 视为错误（去掉条件保护），只在显式传入 `Mapping` 时才构造。更新后需运行全部受影响测试确认
- **修复风险（中）**: 需要更新所有构造 `ToolAcceptCall` 的测试 helper，包括非本 slice 相关的测试；可能超出当前 slice 的 allowed files 范围。实现 agent 已在 implementation report 中注明此风险
- **严重程度（中）**: 不阻塞 merge，但如果后续测试新增 helper 未跟随此约束，可能引入难以发现的 durable truth 缺口

### F2-未修复-低-`_payload_size_bytes` 在 `payload_resolution.py` 与 `tool_runtime.py` 中重复定义

- **入口/函数**: `_payload_size_bytes` (两处)
- **文件(行号)**: `dayu/host/payload_resolution.py:388-395`, `dayu/host/tool_runtime.py:3808-3815`
- **输入场景**: 任一模块修改了 `canonical_json_dumps` 的调用方式或 size 计算逻辑
- **实际分支**: 两个独立函数，各自被本模块内的路径调用
- **预期行为**: 相同语义的函数应只有一处定义，调用方从唯一真源导入
- **实际行为**: 两个完全相同的私有函数分别定义在两个模块中，`payload_resolution.py` 用于读取路径的 size 校验，`tool_runtime.py` 用于写入路径的 size 计算与 threshold 判定。若 size 计算逻辑变更（如切换编码或换用不同 canonical 序列化），必须同步修改两处
- **直接证据**:
  - `payload_resolution.py:388-395`: `def _payload_size_bytes(payload: ...) -> int: return len(canonical_json_dumps(payload).encode("utf-8"))`
  - `tool_runtime.py:3808-3815`: 完全相同的实现
- **影响**: 维护风险，非运行时缺陷
- **建议改法和验证点**: 将 `_payload_size_bytes` 提取到 `dayu/host/durable/codec.py`（与 `canonical_json_dumps` 同模块）或新建 `dayu/host/_size_utils.py`，两个调用方改为导入。或至少让 `tool_runtime.py` 从 `payload_resolution` 导入（当前已有导入关系 `from dayu.host.payload_resolution import event_payload_object`）。验证：pyright 0 errors，受影响测试通过
- **修复风险（低）**
- **严重程度（低）**: 不影响正确性，纯维护性优化

### F3-未修复-低-`_read_arguments_json` inline 路径未强制执行 `arguments_payload_ref` 必须为 None

- **入口/函数**: `_read_arguments_json` / `_read_semantic_query`
- **文件(行号)**: `dayu/host/payload_resolution.py:237-241`, `dayu/host/payload_resolution.py:289-290`
- **输入场景**: 一个畸形（或未来 buggy writer 产生）的 `TOOL_CALL_REQUESTED` hot payload 同时携带 `arguments_storage_kind=inline_json` 和非 None 的 `arguments_payload_ref`
- **实际分支**: `_read_arguments_json` 第 237 行走 `inline_json` 分支，读取 `arguments_inline_json` 并返回，完全忽略非法的 `arguments_payload_ref`
- **预期行为**: 当 storage_kind 为 `inline_json` 时，`arguments_payload_ref` 必须为 None；不为 None 时应 fail-closed 抛 `HostDurableError`
- **实际行为**: 静默忽略不一致的 `payload_ref`，使用 inline 值
- **直接证据**:
  - `payload_resolution.py:237-241`: inline 分支不检查 `arguments_payload_ref is None`
  - `payload_resolution.py:289-290`: semantic query `inline_text` 分支同样不检查 `semantic_query_payload_ref is None`
  - 对比 `_read_semantic_query` 的 `absent` 分支 (`payload_resolution.py:212-217`) 正确检查了所有相关字段必须为 None — 说明项目编码规范已意识到这种防御需求
- **影响**: 当前 writer（`_tool_call_request_payload_plan`）正确地将二选一字段设为 None，因此当前生产路径不受影响。但若未来新增 writer 路径或外部工具写入畸形数据，reader 会静默接受不一致状态。防御深度不足
- **建议改法和验证点**: 在 `_read_arguments_json` inline 分支增加 `if payload.get("arguments_payload_ref") is not None: raise HostDurableError(...)`；`_read_semantic_query` inline 分支同理增加 `semantic_query_payload_ref` 的 None 检查。新增 focused 测试：构造同时有 inline 和 payload_ref 的畸形 payload，断言抛 HostDurableError
- **修复风险（低）**: 纯增量防御性检查，不影响现有路径
- **严重程度（低）**: 防御深度问题，当前无触发场景

## Verification Items (Passed)

以下 review 检查点均通过验证，不构成 finding：

1. **TOOL_CALL_REQUESTED accepted arguments atom 同源于 normalized_arguments_digest**: 
   - `_accepted_arguments_digest()` (tool_runtime.py:5207-5214) 使用 `{"arguments": dict(arguments)}` 作为 canonical preimage，与 `_normalized_arguments_digest` (tool_runtime.py:5185-5192) 完全同源
   - `_tool_call_request_payload_plan` 写入前校验 `arguments_payload_digest != candidate.call.normalized_arguments_digest` (tool_runtime.py:3341-3344)，fail-closed
   - 读取路径 `tool_call_request_atoms` 校验 `arguments_payload_digest != normalized_digest` (payload_resolution.py:136-137) 和 `sha256_digest_json(arguments_json) != arguments_payload_digest` (payload_resolution.py:143-144)，双重 fail-closed

2. **inline_json vs payload_descriptor 按 payload_inline_threshold_bytes 判定**:
   - `_tool_call_request_payload_plan` 使用 `arguments_size_bytes <= transaction.payload_inline_threshold_bytes` (tool_runtime.py:3349)，与 plan contract 的 `<=` 一致
   - descriptor kind `tool_call_arguments_json` 在 metadata 中写入并被 `_validate_descriptor_kind` fail-closed 校验 (payload_resolution.py:337-338)

3. **semantic query absent / inline / descriptor 独立于 semantic_input_digest**:
   - `semantic_input_digest` 来自 `candidate.idempotency.semantic_input_digest` (tool_runtime.py:3403)，独立于 `candidate.call.semantic_query_text` (tool_runtime.py:3450)
   - `_read_semantic_query` 对 absent 路径做完整性检查（三字段均不能携带值），fail-closed
   - digest 校验：`sha256_digest_json({"semantic_query_text": query_text}) != semantic_query_digest` 时抛出 (payload_resolution.py:308-309)

4. **PayloadStore 写入同事务**:
   - `PayloadStore().write_sqlite_payload()` 接收调用方传入的 `HostTransaction` (tool_runtime.py:3352-3354)，不创建新事务
   - SQLite payload 和 descriptor 的写入在同一个 `transaction` 内完成 (durable/payload.py:211-244)
   - Idempotency 保护：`accept_tool_fact` 在写入前通过 idempotency check (tool_runtime.py:1786-1796)，重复请求返回 existing ack

5. **REUSE 路径安全**:
   - `_tool_fact_reuse_accept_candidate` 设置 `accepted_arguments=call.arguments` (tool_runtime.py:5549)
   - 若 REUSE 为首个写入（无 prior idempotency record），走完整写入路径，`_required_accepted_arguments` 可正确取值
   - 若 REUSE 命中已有 idempotency record，直接返回 existing ack，不进入写入路径

6. **payload_resolution.tool_call_request_atoms() 类型严格**:
   - 返回 `ToolCallRequestAtoms`，所有字段有具体类型（`str | None`, `Mapping[str, JsonValue]`），无 `Any`/`object`
   - 错误时均抛 `HostDurableError`，fail-closed
   - 所有 `cast()` 调用有 `isinstance` guard，不会越界

7. **Engine preview normalized_arguments_digest 仅为 diagnostic**:
   - `_preview_payload` 使用 `sha256_digest_json({"arguments": data.arguments})` (engine_ingest.py:4247)
   - 写入 `EventClass.PREVIEW` 事件 (engine_ingest.py 调用路径)，不是 canonical fact
   - 测试 `test_tool_call_requested_and_result_accepted_are_preview` 断言该字段出现在 PREVIEW 事件中 (test_engine_ingest_mapping.py:1661-1663)

8. **Tool Trace 测试验证不展开大参数**:
   - `test_tool_trace_does_not_inline_large_tool_call_arguments` 构造大参数（1024 "x"），写入 SQLite payload descriptor，验证 `arguments_digest in line_text` 且 `"x" * 128 not in line_text`

9. **未越界实现 Slice 2-7**:
   - 未修改 `dayu/host/tool_trace.py`、`dayu/host/run_input.py`、`dayu/host/compaction_evidence.py`、`dayu/host/llm_compaction.py`
   - 未修改 `dayu/engine/` 下任何文件
   - 未修改 `dayu/config/prompts/`
   - 新增测试仅限于 Slice 1 allowed test files

10. **README 更新准确**:
    - `dayu/host/README.md`: 新增了 `TOOL_CALL_REQUESTED` request atom 说明，准确描述了 inline/descriptor 冷热分离、descriptor kind、semantic query 可选性
    - `tests/README.md`: 新增了 Engine preview normalized arguments digest、ToolRuntime accepted tool-call request atoms、Tool Trace 大参数 descriptor 边界等覆盖事实描述
    - 未写未来计划、未写实现细节

## Open Questions

- 无

## Residual Risk

1. **Tests 未覆盖并发冲突路径**: 当前 focused 测试均为单线程，未验证两个并发 accept 对同一 tool call 写入 payload descriptor + EventLog 时的 transaction isolation。现有 idempotency guard 应处理此场景，但无显式测试覆盖
2. **旧 EventLog TOOL_CALL_REQUESTED 事件不可读**: `tool_call_request_atoms()` 读取旧版（Slice 1 前）的 `TOOL_CALL_REQUESTED` 事件会因缺少 `arguments_storage_kind` 等字段而失败。这是按 fresh schema 设计的预期行为，但任何尝试读取旧事件的代码路径需要显式处理
3. **`ToolAcceptCall.accepted_arguments` 默认 None 的长期风险**: F1 已详细记录。实现 agent 已在 implementation report 的 "remaining risks" 中注明，建议在未来合适的 slice（如 Slice 7 测试 closeout）中一并消除
4. **semantic query 生产路径当前始终为 absent**: `_tool_fact_accept_candidate` 和 `_tool_fact_reuse_accept_candidate` 均未设置 `semantic_query_text`，整套 semantic query 基础设施（写入、存储、读取、校验）在 Slice 1 中仅通过测试驱动，实际生产路径无消费。这不影响正确性，但意味着 semantic query 的完整端到端行为尚未在生产中验证

## Completion Report

- **Artifact path**: `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-ds.md`
- **Verdict**: **pass-with-findings**
- **Blocking findings**: 0
- **Non-blocking findings**: 3 (F1: 中; F2: 低; F3: 低)
- **Tests considered**: 
  - `tests/host/test_toolruntime_accept_barrier.py` (43 passed, 含 4 新增)
  - `tests/host/test_engine_ingest_mapping.py` (32 passed, 含 1 updated)
  - `tests/host/test_tool_trace_projection.py` (9 passed, 含 1 新增)
  - `tests/host/test_durable_schema.py` (33 passed, 含 1 新增)
  - `tests/host/test_toolruntime_executor.py` (23 passed, regression)
  - **Total: 117 passed, 0 failed**
- **pyright**: 0 errors, 0 warnings, 0 informations
- **Residual risks**: 见上方 Residual Risk 节

F1 是唯一中严重度 finding，本质是 `ToolAcceptCall.accepted_arguments` 的 optional default 设计与 strict production requirement 之间的设计张力。当前双防线（构造时条件校验 + 写入时强制校验）正确保护了生产路径，但为未来测试 helper 遗漏 durable truth 留了可能性。建议在后续 slice（如 Slice 7 public smoke closeout）中评估是否将 `accepted_arguments` 改为必填。
