# 全仓库深度 Code Review

## Scope

- **Mode**: All Repository（全仓库）
- **Branch**: `feat/phase-12-5-conversation-memory-optimize` @ `53a6d13`
- **PR**: https://github.com/noho/dayu-agent-r/pull/68
- **Review date**: 2026-05-25 02:04 UTC
- **Output file**: `docs/reviews/pr-68-post-draft-fullrepo-review-ds-20260524.md`
- **Verification timestamp**: `20260525-020407`

### Included scope

- `dayu/` — 全部 114 个生产 Python 文件
- `tests/` — 全部 90 个测试文件（1638 测试用例）
- `docs/host/design.md` — Host 设计真源
- `docs/host/implementation-control.md` — 实施总控
- `AGENTS.md` / `CLAUDE.md` — 项目指令

### Excluded scope

- `.venv/` — 虚拟环境
- `workspace/` — 临时工作区
- `docs/reviews/` — 既有 review artifacts
- `dayu/render/`、`utils/` — 非测试覆盖要求的辅助脚本
- `node_modules/`、`.pytest_cache/` 等构建/缓存产物

### Parallel review coverage

| Subagent | Scope | Coverage |
|---|---|---|
| Durable layer | `dayu/host/durable/*.py` + tests | Full |
| Memory/compaction | `dayu/host/memory.py`, `compaction.py`, `context_*.py`, `compact_*.py`, `llm_compaction.py` + tests | Full |
| Admission/dispatch/cancel | `dayu/host/admission.py`, `dispatch.py`, `recovery*.py`, `open_host.py`, `engine_ingest.py` + tests | Full |
| ToolRuntime/tooling | `dayu/host/tool_runtime.py`, `tooling.py`, `waiting.py`, `wait_adapter.py` + tests | Full |
| Architecture boundaries | All import dependencies, file sizes, re-exports, protocol coupling, test coupling | Full |
| Engine runner | `dayu/engine/`, `dayu/engine/runners/openai/` + tests | Full |

**Not covered**: `dayu/fins/`（Fins 财报仓储层未纳入本次 Host review scope）; `dayu/config/` prompts/assets 内容审查。

## 验证结果

```text
pyright:        0 errors, 0 warnings, 0 informations
import boundary: 31/31 tests passed（contracts/engine/host/runtime/service 五层全覆盖）
full test suite: 1637 passed, 1 skipped（85.36s）
memory/compaction: 132/132 tests passed
tool runtime: 44 passed, 1 skipped
lifecycle/cancel/compact smoke: 全 pass
event log: 13 pass + multiprocess pass
recovery scan: 6 pass
retry/replay/steer: 12 pass
integration (P5/P6/P7/public multiturn): 19 pass
```

## Findings

### 1-未修复-高-测试文件耦合生产私有符号，破坏封装隔离

- **入口/函数**: 7 个测试文件直接 import 生产代码的 `_private` 符号
- **文件(行号)**: `tests/engine/test_agent_phase3_tool_call.py:35`、`tests/host/fake_compaction.py:26`、`tests/host/test_durable_connection.py:7`、`tests/host/test_host_instance_liveness.py:10`、`tests/host/test_context_compact_events.py:50`、`tests/host/test_logging.py:37`、`tests/host/test_public_event_stream.py:43`
- **输入场景**: 测试运行时加载这些私有符号。
- **实际分支**: 测试绕过公共 API，直接测试内部实现细节。
- **预期行为**: 测试应通过公共接口验证行为，不应依赖内部私有符号。
- **实际行为**: 测试与具体实现绑定，重构时容易断裂且不会警告调用方。
- **直接证据**: `test_agent_phase3_tool_call.py` import `_AsyncAgent`、`_project_tool_outcome_for_llm`；`fake_compaction.py` import `_candidate_from_final_answer`；`test_durable_connection.py` import `_close_connection_best_effort` 等。
- **影响**: 维护成本升高；私有符号变更可能静默破坏测试；无法验证公共 API 实际可达性。
- **建议改法和验证点**: 每个 case 单独评估：若测试的真实目标是私有 helper 的正确性，应将该 helper 提升为模块级公共辅助函数或独立测试替身；若目标是端到端行为，应改为通过公共入口间接覆盖。
- **修复风险（中）**: 需要重新设计部分测试结构。
- **严重程度（高）**:

### 2-未修复-高-兼容性 re-export 违反 AGENTS.md 编码约束

- **入口/函数**: `dayu/host/tooling.py:15` re-export `ToolBundleSourceKind` / `ToolBundleSourceRef`
- **文件(行号)**: `dayu/host/tooling.py:15-16` → `dayu/host/__init__.py:170-171`
- **输入场景**: 上层调用 `from dayu.host import ToolBundleSourceKind`。
- **实际分支**: 符号真源在 `dayu.contracts.tool_source`，但通过 `dayu.host.tooling` → `dayu.host.__init__` 双重 re-export。
- **预期行为**: AGENTS.md 明确"禁止兼容性 re-export：仅为保持旧导入路径而转发符号"。调用方应直接从 `dayu.contracts` 获取工具来源相关类型。
- **实际行为**: `dayu.host` 公共命名空间转发不属于 Host 语义 ownership 的 contracts 类型，诱导调用方绕过 contracts 真源。
- **直接证据**: `tooling.py:15` `from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef`；`__init__.py:170-171` 加入 `__all__`。
- **影响**: 契约漂移风险；contracts 变更时 `dayu.host` 被迫跟进 re-export 或产生 import broken window。
- **建议改法和验证点**: 从 `dayu/host/__init__.py` 和 `dayu/host/tooling.py` 移除这两个符号的 re-export；调用方改为直接从 `dayu.contracts` 导入；检查并消除所有此类 re-export。
- **修复风险（低）**: 仅需改动 import 路径，不涉及行为变更。
- **严重程度（高）**:

### 3-未修复-中-God object 风险：11 文件超 500 行，4 文件超 3000 行

- **入口/函数**: 多文件
- **文件(行号)**: `run_transition.py`(5865)、`state.py`(5700)、`tool_runtime.py`(5519)、`admission.py`(4954)、`engine_ingest.py`(4120)、`memory.py`(4054)、`dispatch.py`(3614)、`run_input.py`(3090)、`api.py`(2965)、`compaction.py`(2386)、`waiting.py`(2213)
- **输入场景**: 任一模块的新功能开发、bug fix 或 review 都需要理解大量正交职责。
- **实际分支**: 代码本身正确，但结构违反 AGENTS.md "禁止 God object、God function、God dataclass"。
- **预期行为**: 按语义 owner 拆分模块。例如 `run_transition.py` 包含 session lifecycle、cancel、terminal closeout、recovery dispatch 等多种不同 owner 的 transition，应沿状态机边界拆分。
- **实际行为**: 单文件承载过多正交职责，使 review、测试、独立演进变得困难。
- **直接证据**: `run_transition.py` 含 137 个函数/类；`state.py` 含 attempt、dispatch record、wait record、session slot、liveness 等多种 row 定义与 mutation helper。
- **影响**: 维护成本升高；单模块变更风险面扩大； reviewer 认知负载过高。
- **建议改法和验证点**: 按语义 owner 与状态机边界分拆为独立模块。`run_transition.py` 可按取消、终态、恢复、dispatch 拆分；`state.py` 可按 Run/Attempt/WaitRecord/Session 拆分。分拆后运行全量测试和 pyright 通过。
- **修复风险（中）**: 重构量大但行为不变；需确保 import 路径更新全面。
- **严重程度（中）**:

### 4-未修复-中-session_lifecycle.py 从 public API 层引入 HostApiError 向下穿透到 durable 层

- **入口/函数**: `_CloseSessionOperation.__call__` / `_require_session` / `_idempotent_session_result` 等
- **文件(行号)**: `dayu/host/durable/session_lifecycle.py:21-22, 383-384, 389-390, 729-730, 775-776, 794-795, 831-832, 852-853, 857-858`
- **输入场景**: Session 缺失、状态非法、幂等冲突等 durable 错误场景。
- **实际分支**: 直接 `raise HostApiError(code=HostApiErrorCode.NOT_FOUND, ...)` — `HostApiError` 定义在 `dayu.host.api`，属于 Host public API 层的错误类型。
- **预期行为**: 按照分层设计，`dayu/host/durable/` 应作为基础设施层使用自己的错误类型（已有 `HostDurableError`、`HostIdempotencyConflictError` 等），由调用方在 public API 层翻译为 `HostApiError`。
- **实际行为**: 基础设施层反向依赖 public API 层的错误类型。虽然同属 Host 层（非跨层），但模糊了 durable foundation 与 public facade 的边界。
- **直接证据**: `session_lifecycle.py:21` `from dayu.host.api import HostApiError, HostApiErrorCode`；其他 durable 模块（`event_log.py`、`idempotency.py`、`memory.py`、`state.py` 等）均不 import `HostApiError`。
- **影响**: `session_lifecycle.py` 与 public API 类型耦合；若 `HostApiErrorCode` enum 重命名或迁移，durable 层被迫跟进。
- **建议改法和验证点**: 在 `session_lifecycle.py` 内部改用 `HostDurableError` 子类表达 durable 错误；upper layer（`command.py`/`api.py`）负责将 durable error 映射为 `HostApiError`。
- **修复风险（中）**: 需要为每种 durable 错误场景定义对应的 `HostDurableError` 子类；上层需要补映射逻辑。
- **严重程度（中）**:

### 5-未修复-中-ToolRuntime 内存在取消失败的资源泄漏和不必要的 accept pipeline

- **入口/函数**: `_dispatch_tool_call_with_bounds` / `_execute_one`
- **文件(行号)**: `dayu/host/tool_runtime.py:2652-2668`、`dayu/host/tool_runtime.py:2509-2577`
- **输入场景**: 
  - (a) 工具执行中 Host cancel 到达，`await_or_cancel` 抛出 CancelledError，被丢弃的协程可能持有外部资源
  - (b) 工具执行超时或被取消后，其结果仍走完整 accept barrier pipeline（`_normalize_runtime_outcome` → 截断 → `_observe_llm_inline_tool_result` → accept candidate → accept retry）
- **实际分支**: (a) 取消路径直接返回 governed failure，不 await 原始协程；(b) `_execute_one:2509-2577` 中即使 `policy_decision` 已判定为 governed error，仍穿过完整 pipeline。
- **预期行为**: (a) 应在可控超时内尝试清理已启动的工具协程；(b) cancelled/timeout 的工具结果应直接返回，不经过截断、observation 和 accept barrier。
- **实际行为**: (a) 若工具持有 DB 连接、文件句柄等外部资源，泄漏持续到 GC；(b) 无意义的 pipeline 处理增加延迟且可能在 accept store 争用下引入额外阻塞。
- **直接证据**: `tool_runtime.py:2652-2668` 的 `_dispatch_tool_call_with_bounds` 取消路径只调用 `await_or_cancel` 返回 governed failure，不对原始协程做清理；`tool_runtime.py:2509-2577` 的 `_execute_one` 对所有结果无分支统一进入 pipeline。
- **影响**: 资源泄漏（长期运行进程）；取消延迟增大。
- **建议改法和验证点**: (a) 取消路径增加带超时的 best-effort await 清理；(b) 在 `_execute_one` 中增加取消/超时 fast path，直接返回 governed failure。
- **修复风险（低）**: fast path 跳过 pipeline 不改变最终结果形状；协程清理需注意不引入死等。
- **严重程度（中）**:

### 6-未修复-中-ToolRuntime 内存态在跨 Attempt 重建时丢失重复治理和历史 cursor

- **入口/函数**: `InMemoryRunLocalDuplicateGovernance` / `TruncationManager`
- **文件(行号)**: `dayu/host/tool_runtime.py:1664-1761`（duplicate）、`dayu/host/tool_runtime.py:1326-1535`（truncation cursor）
- **输入场景**: 同一 Run 经历 `WAITING → resolve_wait → resume` 或 `recovery → new Attempt` 后，Host 创建新的 ToolRuntime 实例。
- **实际分支**: 
  - (a) `InMemoryRunLocalDuplicateGovernance` 新建空 `_index: dict`，丢失旧 Attempt 期间的 duplicate 记录，`REUSE` 决策不会跨 Attempt 延续；
  - (b) `TruncationManager._cursors: dict` 被丢弃，旧 cursor 不再可 fetch_more；
  - (c) 如果进程长期运行且多次产生 cursor 但不触发 `fetch_more`，cursor 可能无限累积。
- **预期行为**: 设计文档明确"同进程且未丢失 Host 运行期状态时，同一个 Run 因 resume、steer 或 recovery 创建的新 Attempt 必须继续复用该 Run 的 duplicate index"。
- **实际行为**: (a)(b) 当前实现不符合设计预期；(c) cursor 清理仅在 `store_cursor`、`fetch_more` 和 cursor lookup miss 时触发，无周期性清理。
- **直接证据**: `tool_runtime.py:1763-1781` 的 `__init__` 创建空 `_index`；`tool_runtime.py:1510` cursor 使用 `single_use=True` 但无全局清理 loop。
- **影响**: 跨 Attempt 重复工具调用可能被错误重新执行（浪费 tokens 和外部调用）；cursor 内存泄漏。
- **建议改法和验证点**: 在 ToolRuntime factory 层面注入 Run 级共享的 duplicate index（如 `RunLocalDuplicateIndex` 作为独立对象在 attempted runs 间传递）；周期性 cursor 清理按 TTL 扫描全量 cursor。
- **修复风险（中）**: 需要设计 Run 级共享对象的生命周期管理。
- **严重程度（中）**:

### 7-未修复-中-Compaction quality checker 拒绝合法的 CLEAR 操作导致失败重试

- **入口/函数**: `_open_questions_retained`（context_governance 内部函数）
- **文件(行号)**: `dayu/host/context_governance.py:616-628`
- **输入场景**: LLM compactor 判定所有 open questions 已解决，输出 `open_questions` patch `operation=CLEAR`，并附带 valid evidence refs。
- **实际分支**: `_open_questions_retained` 仅接受 `REPLACE` 且值非空；`CLEAR` 落到 `return False`，触发 `OPEN_QUESTIONS_MISSING` quality issue。
- **预期行为**: `CLEAR` 表示有意识地清空开放问题（所有问题已解决），应被视为合法结果。
- **实际行为**: 一个语义正确的 compaction 结果被 quality checker 错误拒绝，可能触发不必要的 repair attempt 消耗额外 LLM 调用。
- **直接证据**: `context_governance.py:625-628`：
  ```python
  if patch.operation is PinnedPatchOperation.REPLACE:
      return patch.value is not None and len(patch.value) > 0
  return False  # CLEAR always rejected
  ```
- **影响**: 不必要的 LLM compaction repair 调用；compaction 可能无意义失败。
- **建议改法和验证点**: `CLEAR` 操作应在有 valid evidence refs 支持时视为合法；修改 `_open_questions_retained` 接受 `CLEAR` + evidence_refs。
- **修复风险（低）**: 局部逻辑变更。
- **严重程度（中）**:

### 8-未修复-中-多 pass compaction 合并候选时无条件保留全部 refs

- **入口/函数**: `_merge_pass_candidates`
- **文件(行号)**: `dayu/host/compaction_operation.py:343-345`
- **输入场景**: 多 pass compaction 中，单个 pass 选择保留不同的 evidence refs 子集。
- **实际分支**: `_merge_pass_candidates` 对 `preserved_canonical_evidence_refs` 和 `preserved_evidence_backed_fact_refs` 硬编码为 `request.canonical_evidence_refs` 和 `request.evidence_backed_fact_refs`——即请求中的全量 refs。
- **预期行为**: 应计算各 pass 实际保留的 refs 并集（至少）或交集（严格），尊重各 pass 的独立决策。
- **实际行为**: 所有 refs 被标记为"已保留"，可能超出单个 pass 的保留意图。
- **直接证据**: `compaction_operation.py:343-345`：
  ```python
  preserved_canonical_evidence_refs=request.canonical_evidence_refs,
  preserved_evidence_backed_fact_refs=request.evidence_backed_fact_refs,
  ```
- **影响**: 保守但错误——可能向下游传递夸大的保留范围，影响后续 budget 判断的准确性。
- **建议改法和验证点**: 改为 `pass_candidate.preserved_canonical_evidence_refs` 的实际保留值，取各 pass 并集。
- **修复风险（低）**:
- **严重程度（中）**:

### 9-未修复-中-取消信号与 Engine 运行中事件存在竞态

- **入口/函数**: `_consume_worker_events` / `_DefaultLocalWorkerHandle.cancel`
- **文件(行号)**: `dayu/host/dispatch.py:2878-2941`、`dayu/host/local_proxy.py:136-146`
- **输入场景**: 
  - (a) 用户在 Engine 流式返回 `FINAL_ANSWER` 事件期间调用 `cancel_run`
  - (b) 调用 `_DefaultLocalWorkerHandle.cancel(reason)` 期望中断 Worker
- **实际分支**: 
  - (a) `_consume_worker_events` 的 `while True` event loop（L2878-2941）在每次 event ingest 之间不检查 `cancellation_token.is_cancelled()`；仅当 stream 正常结束（`StopAsyncIteration`）或异常时才检查
  - (b) `cancel()` 是纯 no-op（`del reason`），取消只通过 `_HostCancellationToken.request_cancel()` 传播
- **预期行为**: (a) 取消后应尽快停止 ingest 并终止 Attempt；(b) WorkerHandle 协议声称"best-effort 取消"但无任何实现。
- **实际行为**: (a) 若 Engine 正在返回 final answer，Host ingest 将完整接受该 answer 后再检测到取消，用户拿到一个"已被取消的 Run 的完整结果"；(b) WorkerHandle cancel 是个误导性空壳。
- **直接证据**: `dispatch.py:2878-2941` while 循环体内无 `is_cancelled` 检查；`local_proxy.py:141-143` `del reason # noqa: F841`。
- **影响**: 取消延迟增大；UX 不一致（用户点取消后仍看到旧回答）。
- **建议改法和验证点**: (a) 在 while 循环内每次 event 前检查 `is_cancelled()`；(b) 补文档说明 cancel 只通过 token 传播，或补传输层 cancel RPC。
- **修复风险（低）**: 仅加检查和文档。
- **严重程度（中）**:

### 10-未修复-低-其他未修复低风险项

以下 findings 经主 reviewer 核实为真实但影响有限，按子条目记录：

- **10a. 非流式解析丢弃多 choices**：`engine/runners/openai/non_stream_parser.py:253` 仅处理 `choices[0]`，`len(choices) > 1` 时静默丢弃。建议加 diagnostic log。 -- 低
- **10b. `_FINISH_REASON_MAP` 重复**：`sse_parser.py:69-74` 与 `non_stream_parser.py:53-58` 维护相同映射表。建议提取到共享常量。 -- 低
- **10c. Service 层 assembly 一致性诊断**：`runtime/assembly.py:142` 的兼容性诊断注释表述模糊，未区分"不适配"与"保守但合法"。 -- 低
- **10d. 恢复 dispatch 缺少 owner_host_instance_id**：`engine_ingest.py:436` reactive recovery 创建的 Attempt 没有 owner，crash 后 orphan 为 inconclusive。 -- 低
- **10e. Compactor token 估算 floor 不一致**：`llm_compaction.py:1366` 使用 `max(1, ...)` 而 `context_budget.py:519` 使用 `ceil(...)`。 -- 低
- **10f. `ensure_session` 的 `SessionLifecycleResult.closed` 字段语义**：`closed` 表示"本操作是否关闭了 Session"而非"Session 是否已关闭"，文档清晰但调用方可能误解。 -- 低
- **10g. 多 pass compaction 操作中取消丢失**：`compaction_operation.py:129-130` max_attempts 耗尽后 `while` 退出，取消事件被掩盖。 -- 低
- **10h. `memory.py` 作为 durable projection 直接依赖 Host domain types**：`dayu/host/durable/memory.py:37-59` import `ConversationMemorySnapshot` 等 domain type，松散耦合。 -- 低
- **10i. `close_session` 不对已有 active Run 做 guard**：`session_lifecycle.py:381-392` 允许关闭有 active Run 的 Session。设计文档明确为 intentional（close ≠ cancel），但调用方 Service 需知此约束。 -- 低
- **10j. `getattr(error, "sqlite_errorcode", None)`**：`transaction.py:459` 用 getattr 绕过类型桩缺失，有文档化的合理理由。 -- 低

## Open Questions

- **OQ1**: God object 拆分优先级：`run_transition.py`、`state.py`、`tool_runtime.py` 中哪些应在下一 phase 优先拆分？
- **OQ2**: ToolRuntime 跨 Attempt 状态保持（duplicate index、cursor）是应在 Phase 12 内补丁还是作为独立 phase 处理？
- **OQ3**: 多 pass compaction 目前是否在真实场景中触发（或仅防御性代码路径）？若从未触发，finding 8 的优先级可降低。

## Residual Risk

1. **全量 EventLog replay 鲁棒性**：当前测试覆盖正常 lifecycle 和 recovery 路径，但未覆盖极端场景（EventLog 10000+ events 后追平性能、snapshot 损坏后全量重建）。
2. **跨进程 crash 恢复竞态**：`admission.py` 的 CAS 依赖 SQLite WAL + `BEGIN IMMEDIATE`，虽经 multiprocess 测试验证，但在极端短事务冲突下的重试耗尽行为未覆盖。
3. **取消与 compaction 并发**：`cancel_run` + 同期 `CONTEXT_COMPACTION_REQUESTED` reactive path 的竞态由 ingest 事务排序保证正确，但无专门并发测试。
4. **远程 Engine 路径**：代码有 LocalProxy/RemoteProxy 架构预留，但远程 Engine dispatch、remote cancel 传播、remote execution_id 验证均尚未实现，不在当前 scope。
5. **`dayu/fins/`**：财报仓储层未纳入本次 review，为后续独立 review scope。

## Verdict

**PASS_WITH_FINDINGS**

全仓库代码正确性良好：1637/1638 测试通过、pyright 零错误、五层 import boundary 全覆盖、Engine SSE/tool-call/cancellation/retry 核心路径验证完备、Host durable CAS 状态迁移经 multiprocess 测试验证、记忆/压缩质量检查逻辑完整、ToolRuntime accept barrier 正确执行。

存在 2 个高严重度 finding（测试私有耦合 + 兼容性 re-export）、7 个中严重度 finding（God object 风险、durable 层 HostApiError 穿透、ToolRuntime 资源泄漏和不必要的 pipeline、内存态 cross-Attempt 丢失、compaction quality checker 误拒绝 CLEAR 与合并夸大保留、取消竞态）。无 block-ship 的正确性缺陷。

建议在继续推进后续 phase 前至少处理 2 个高严重度 finding，并对中严重度 finding 中影响生产行为的 5、6、7、9 条制定修复计划。
