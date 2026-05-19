# Code Review

## Scope

- Mode: all repository
- Branch: feat/host-p10-5-public-contract-freeze
- Base: main (HEAD = b8089a8)
- Output file: docs/reviews/pr-62-fullrepo-deepreview-all-mimo-20260519.md
- Included scope: dayu/contracts/、dayu/engine/、dayu/runtime/、dayu/host/、tests/、docs/host/、各 README
- Excluded scope: CLI / Web / GUI 入口（out of scope）、dayu/config/（无 Python 源码）、utils/、workspace/、render/
- Parallel review coverage: 6 个 subagent 分别覆盖 Host dispatch+admission、tool_runtime+waiting、compaction+context governance、durable+contracts、engine+runtime、tests+docs

## Verification Commands

```bash
source .venv/bin/activate
python -m pytest tests/ -x -q --timeout=30   # 1 failed, 581 passed
pyright                                       # 0 errors, 0 warnings, 0 informations
```

## Findings

### 001-未修复-严重-soft threshold compaction 测试回归导致 1 个测试失败

- **入口/函数**: `FakeContextCompactor._budget_after_compact()` → `estimate_compacted_context_budget()` → `run_compaction_operation()` → `dispatch._execute_proactive_compaction()`
- **文件(行号)**: `dayu/host/fake_compaction.py:201-212`（b8089a8 修改点）、`dayu/host/compaction_operation.py:140-143`（hard threshold recheck）、`tests/host/test_dispatch_scheduler.py:2134-2174`（失败测试）
- **输入场景**: soft threshold prompt（55 字符 'x'）+ `_soft_compact_policy`（context_window=110, hard_threshold=80）
- **实际分支**: `FakeContextCompactor._budget_after_compact` 返回 `estimate_compacted_context_budget(...)` 估算值 ≈ 82 tokens（summary=19 + system_prompt=26 + preserved_refs=19 + typed_fragments=18），该值 ≥ hard_threshold_tokens(80)，触发 `compaction_operation.py:140` 的 hard threshold recheck 拒绝
- **预期行为**: FakeContextCompactor 应产生低于 hard threshold 的 budget_after_compact，使 proactive compact 成功并创建 Attempt
- **实际行为**: compaction 被 hard threshold recheck 拒弃 → `_execute_proactive_compaction` 返回 None → `compact_accepted=None` → `pending_dispatch=None` → Run 停留在 ACCEPTED，无 Attempt 创建。测试 assert `_attempt_count_for_run == 1` 失败
- **直接证据**: `b8089a8` 将 `_budget_after_compact` 从 `max(0, min(half_estimate, hard_threshold_limit))`（结果 ≈ 9）改为 `estimate_compacted_context_budget(...)`（结果 ≈ 82），未同步调整测试参数或 cap 逻辑
- **影响**: 1 个测试失败（581 passed, 1 failed）；FakeContextCompactor 是测试 / 本地开发专用 compactor，不直接影响生产路径，但测试回归证明该 commit 的 budget 估算变更与现有 hard threshold 机制存在数值冲突
- **建议改法和验证点**:
  1. 在 `FakeContextCompactor._budget_after_compact` 中增加 `min(result, request.budget_before_compact.hard_threshold_tokens - 1)` cap，保证 fake compactor 输出始终低于 hard threshold
  2. 或调整测试参数 `_SOFT_HARD_THRESHOLD_TOKENS` 从 80 提高到足够容纳新估算值
  3. 验证: `python -m pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt -xvs`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 严重 — 测试失败证明 budget 估算变更引入了数值回归

### 002-未修复-高-durable/memory.py 反向依赖上层模块

- **入口/函数**: `ConversationMemoryProjectionConsumer` 及其 helper
- **文件(行号)**: `dayu/host/durable/memory.py:37-74`
- **输入场景**: Host startup 或 projection catch-up 时 durable 层初始化 memory projection consumer
- **实际分支**: `memory.py` 从 `dayu.host.memory`（14 个符号）、`dayu.host.context_events`、`dayu.host.payload_resolution`、`dayu.host.terminal_summary_payload`、`dayu.host.projection`（6 个符号）导入
- **预期行为**: durable 层作为 Host 基础设施，应只依赖 contracts、runtime 和标准库；不应 import 上层业务模块
- **实际行为**: foundation 层反向依赖上层业务模块，包含 memory projection 的 event filter、policy digest、payload resolution 逻辑
- **直接证据**: `dayu/host/durable/memory.py:37-74` 的 import 语句；CLAUDE.md 要求"设计下层组件接口时，必须假设上层组件不存在"
- **影响**: durable 层无法独立测试和演进；替换 memory projection 实现需要穿透修改 durable 层
- **建议改法和验证点**:
  1. 将 `ConversationMemoryProjectionConsumer` 及其 helper 移到 `dayu/host/memory_projection.py` 或同类上层模块
  2. `durable/memory.py` 只保留 snapshot CRUD、item CRUD、diagnostic CRUD 的 row 读写 primitive
  3. 验证: pyright + import boundary tests + memory projection tests
- **修复风险（低/中/高）**: 中（需拆分文件并调整 import）
- **严重程度（低/中/高/严重）**: 高 — 架构边界违反，阻碍 durable 层独立演进

### 003-未修复-中-durable 层多个文件从 dayu.host.api 导入类型

- **入口/函数**: durable/schema.py、state.py、run_transition.py、session_lifecycle.py、read_model.py
- **文件(行号)**: `dayu/host/durable/schema.py:13-22`、`state.py:15-33`、`run_transition.py:18`、`session_lifecycle.py:16-27`、`read_model.py:13`
- **输入场景**: durable 层模块初始化
- **实际分支**: 从 `dayu.host.api` 导入 RunStatus、AttemptStatus、SessionStatus、SourceRunRelation、WaitAdapterKey 等公共类型
- **预期行为**: durable 基础设施层的公共类型应自包含或从独立 types 模块导入
- **实际行为**: foundation 层直接依赖 API 层，增加耦合
- **直接证据**: 各文件头部 import 语句
- **影响**: 架构演化风险，替换 API 层类型定义需要穿透修改 durable 层；不影响当前运行时正确性
- **建议改法和验证点**: 将公共类型下沉到 durable 层自身或独立的 host types 模块；api 层 re-export
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 004-未修复-中-waiting.py iteration_id 语义错误

- **入口/函数**: `_tool_result_resolution_payload()`
- **文件(行号)**: `dayu/host/waiting.py:1380`
- **输入场景**: resolve wait 路径构造 TOOL_RESULT_ACCEPTED payload
- **实际分支**: 将 `wait_record.wait_id` 作为 `iteration_id` 传给 payload 构造函数
- **预期行为**: `iteration_id` 应为 Engine iteration id（来自原始 awaiting accept 时的 `candidate.iteration_id`）
- **实际行为**: `wait_record.wait_id`（Host wait record 标识符）冒充 Engine iteration id；`WaitRecordRow` 未持久化 `iteration_id` 字段
- **直接证据**: `waiting.py:1380` 的赋值 vs `ToolAwaitingAcceptCandidate` docstring 行 189 标注 `iteration_id` 为 "Engine iteration id"
- **影响**: EventLog payload 中 `iteration_id` 语义不正确；可能在未来的工具追踪或审计链中产生静默错误
- **建议改法和验证点**: 在 `WaitRecordRow` 中增加 `iteration_id` 字段并从 candidate 持久化；或在 payload 中使用 `None` 并标注语义差异
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 005-未修复-中-resolve_semantic_digest 始终为 None 导致三个 digest 字段退化

- **入口/函数**: `_tool_result_resolution_payload()`
- **文件(行号)**: `dayu/host/waiting.py:1383-1388`
- **输入场景**: resolve wait 路径构造 payload 的 digest 字段
- **实际分支**: 三个 digest 字段均 fallback 到 `payload_plan.outcome_digest`
- **预期行为**: `tool_schema_digest`、`tool_identity_digest`、`normalized_arguments_digest` 应分别反映 schema 定义、工具身份、参数规范化的语义
- **实际行为**: 三个语义不同的 digest 字段全部退化为同一个 `outcome_digest`
- **直接证据**: `_wait_record_row:2006` 将 `resolve_semantic_digest` 硬编码为 `None`
- **影响**: 工具事实的语义完整性被破坏；基于 digest 的工具追踪、schema 校验或参数匹配逻辑会得到错误信号
- **建议改法和验证点**: 在 `WaitRecordRow` 中持久化原始 digest；或将三个字段设为 `None` 并标注语义差异
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 006-未修复-中-diagnostic_refs 类型不一致

- **入口/函数**: `_accept_with_retry()` vs `_accept_awaiting_with_retry()`
- **文件(行号)**: `dayu/host/tool_runtime.py:2983` vs `dayu/host/tool_runtime.py:2860`
- **输入场景**: tool fact accept timeout 路径
- **实际分支**: `_accept_with_retry` 传 `ToolTraceDiagnosticRef` 对象；`_accept_awaiting_with_retry` 传 `str`（ref_id）
- **预期行为**: 两个对称方法对同一语义字段应使用一致类型
- **实际行为**: 一个传对象，一个传字符串；下游 `_hint_with_diagnostic_refs` 按 `tuple[str, ...]` 拼接
- **直接证据**: 行 2983 `(*diagnostics, timeout_ref)` vs 行 2860 `(*diagnostics, timeout_ref.ref_id)`
- **影响**: 如果传入 `ToolTraceDiagnosticRef` 对象，下游拼接会得到 `str(ToolTraceDiagnosticRef(...))` 而非 `ref_id`
- **建议改法和验证点**: 统一为 `tuple[str, ...]`（传 `ref_id`）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 007-未修复-中-幂等重放时错误类型不一致

- **入口/函数**: `waiting._accepted_ack_from_existing()`
- **文件(行号)**: `dayu/host/waiting.py:2069-2072`
- **输入场景**: idempotency replay 路径发现 EventLog rows 缺失
- **实际分支**: 抛出 `RuntimeError`
- **预期行为**: 应使用 `HostDurableError`（模块已有 import），与 `tool_runtime.py:3682` 的同名函数一致
- **实际行为**: `RuntimeError` 会逃逸上层 `accept_tool_awaiting` 的 `except` 分支（只捕获 `HostIdempotencyConflictError` 和 `_AwaitingAcceptStateConflictError`），破坏 accept barrier 的有界错误语义
- **直接证据**: `waiting.py:2069` 的 `RuntimeError` vs `tool_runtime.py:3682` 的 `HostDurableError`
- **影响**: accept barrier 无法捕获该错误，`RuntimeError` 逃逸到调用方
- **建议改法和验证点**: 将 `RuntimeError` 改为 `HostDurableError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 008-未修复-中-cancel_session_runs 被 RECOVERING Run 阻塞

- **入口/函数**: `_CancelSessionRunsOperation._read_supported_targets_or_raise()`
- **文件(行号)**: `dayu/host/admission.py:1968-1992`
- **输入场景**: Session 中存在 RECOVERING Run 时调用 cancel_session_runs
- **实际分支**: 对不满足条件的 Run 直接抛出 `UNSUPPORTED_OPERATION`，阻塞整个 Session cancel
- **预期行为**: session-scope cancel 应跳过不可取消的 Run，允许取消其他可取消的 Run
- **实际行为**: 一个 RECOVERING Run 阻塞整个 Session 的 cancel 操作
- **直接证据**: `_session_cancel_target_for_run` 对 RECOVERING 返回 `UNSUPPORTED_OPERATION`
- **影响**: 用户无法在 RECOVERING 期间取消同一 Session 的其他 Run
- **建议改法和验证点: 跳过 RECOVERING Run 或在文档中明确说明行为
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 009-未修复-中-context_governance.py 模块名与实际职责不匹配

- **入口/函数**: `context_governance.py` 模块整体
- **文件(行号)**: `dayu/host/context_governance.py:1-461`
- **输入场景**: 维护者查阅架构边界
- **实际分支**: 模块只包含 `check_compaction_candidate` quality checker；proactive/reactive compaction 编排在 dispatch.py / engine_ingest.py
- **预期行为**: 模块名应反映实际职责，或编排逻辑应收敛到该模块
- **实际行为**: 命名造成维护者对架构边界的误判
- **直接证据**: `context_governance.py:3-5` docstring 自承"不 append canonical compact events，不写 memory projection，也不执行 proactive / reactive orchestration"
- **影响**: 维护性
- **建议改法和验证点**: 重命名为 `compact_quality_check.py` 或将编排逻辑整合
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 010-未修复-低-重复 helper 函数（3 类）

- **入口/函数**: `_string_list_json`、`_require_optional_non_empty`、`_budget_after_compact`
- **文件(行号)**: `_string_list_json`: compaction.py:1002、compact_artifact.py:308、context_events.py:452。`_require_optional_non_empty`: compact_artifact.py:321、compaction.py:889、memory.py:3114。`_budget_after_compact`: fake_compaction.py:201、llm_compaction.py:467
- **输入场景**: 各模块内部调用
- **实际分支**: 三处 `_string_list_json` 实现相同；`_require_optional_non_empty` 签名不一致（positional vs keyword-only）；`_budget_after_compact` 逻辑高度相似
- **预期行为**: 重复逻辑必须抽取到公共模块
- **实际行为**: 违反"模块间依赖最小化"和"重复逻辑必须抽取"
- **直接证据**: 各文件同名函数
- **影响**: 维护性
- **建议改法和验证点**: 统一到 `_public_validation` 或公共 helper 模块
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

以下风险有明确 tracking 归属，不阻塞本次 review：

1. **HostDispatchScheduler 职责过重**（约 2100 行、6 项职责）：归 P9.5 ToolRuntime / memory module boundary cleanup 或后续 Host dispatch lifecycle owner。当前事务边界和状态转换正确。
2. **tool_runtime.py 模块过大**（5394 行、10+ 异构职责）：归 P9.5 ToolRuntime module boundary cleanup。当前各函数内聚性尚可。
3. **runtime lane close/acquire 竞态**：归 Phase 11 Multi-process Hardening。implementation-control.md 追踪区已记录。
4. **Host crash recovery E2E 缺失**：归 Phase 11 Recovery。implementation-control.md 追踪区已记录。
5. **durable bootstrap DDL 原子性**：implementation-control.md 追踪区已记录。
6. **watch 轮询性能**：归 Phase 11 public lifecycle hardening。
7. **import boundary helper 重复**：归 P9.5 test hardening。
8. **diagnostic_refs 传播对称缺口**（非 awaiting path）：implementation-control.md 追踪区已记录。
9. **根 README "Host 层正在重写中" 残留旧语义**：应更新为反映当前已实现状态。不阻塞 correctness。
10. **根 README 和 dayu/README.md 断链引用**（`docs/host/interface-discussion-notes.md` 不存在）：应修正为 `docs/host/discussion-note.md`。

## Verdict

**BLOCKED**

必须修复项（1 项）：

| # | 文件 | 行号 | 问题 | 修复方向 | 验证命令 |
|---|------|------|------|---------|---------|
| 001 | `dayu/host/fake_compaction.py` | 201-212 | `_budget_after_compact` 新估算值 (≈82) 超过 hard threshold (80)，导致 proactive compact 被 hard threshold recheck 拒绝，测试失败 | 在 `_budget_after_compact` 中 cap 结果为 `min(result, request.budget_before_compact.hard_threshold_tokens - 1)` 或调整测试参数 | `python -m pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt -xvs` |

修复后必须重新运行完整测试套件和 pyright 确认无回归。
