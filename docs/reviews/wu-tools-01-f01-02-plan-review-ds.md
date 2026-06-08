# WU-TOOLS-01-F01-02 Plan Review — AgentDS

## 1. Review Context

- **Work unit**: WU-TOOLS-01-F01-02 (cancellation propagation / token bridge)
- **Gate**: plan review
- **Artifact under review**: `docs/host/wu-tools-01-f01-02-cancellation-plan.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Reviewer**: AgentDS (第二路独立 review)
- **Date**: 2026-06-08

## 2. Evidence Verification Summary

对 Plan Section 4 "Direct Code Evidence" 的每项主张做了独立验证：

| # | 主张 | 证据路径 | 验证结果 |
|---|------|---------|---------|
| 1 | `FinsDownloadToolCallable.__call__` 中 `del context` | `dayu/fins/tools/download_tools.py:66` | **确认**：`del context` 在 line 66，随后直接 `self.runtime.start_download(request)` |
| 2 | `FinsPreprocessToolCallable.__call__` 中 `del context` | `dayu/fins/tools/preprocess_tools.py:65` | **确认**：同模式 |
| 3 | `start_download` / `start_preprocess` 无 token 参数 | `dayu/fins/ingestion_runtime.py:1008-1051`, `1053-1095` | **确认**：方法签名无 token 参数；`_create_queued_job` 后直接 `executor.submit`，无中间 checkpoint |
| 4 | Runtime 已有 `request_cancel` 与 cancel 检查 | `dayu/fins/ingestion_runtime.py:1114-1128` | **确认**：`request_cancel` 返回更新 record，"终态 job 原样返回"。状态机含 `QUEUED/RUNNING/CANCELLING/CANCELLED` (line 97-106) |
| 5 | Host abandon wait 调用 `runtime.request_cancel` | `dayu/fins/ingestion/wait_adapter.py:127-141` | **确认**：`abandon_wait` 调用 `self.runtime.request_cancel(job_id)` |
| 6 | CANCELLED 投影为 `ResolveWaitCancelledOutcome` | `dayu/fins/ingestion/wait_adapter.py:282-300` | **确认**：`_cancelled_outcome` 用 `TOOL_CANCELLED_REASON_HOST_CANCELLED` 构造 |
| 7 | Legacy adapter 已支持 `execution_context_param_name` | `dayu/tools/_legacy_adapter/definition_adapter.py:90-114` | **确认**：line 113-114 注入 context 到 keyword arguments |
| 8 | `fetch_web_page` 已有 token 传递 | `dayu/tools/web/web_tools.py:1149-1189` | **确认**：`execution_context_param_name="execution_context"`, line 1188-1189 resolve + checkpoint |
| 9 | `fetch_web_page` 在各阶段间 checkpoint | `dayu/tools/web/web_tools.py:1224-1285` | **确认**：warmup 前、probe 前、fetch convert 前、Playwright fallback 传递 token |
| 10 | `search_web` 无 execution context | `dayu/tools/web/web_tools.py:1070-1106` | **确认**：装饰器无 `execution_context_param_name`，函数签名无 context 参数 |
| 11 | `search_public_web` 无 token 参数 | `dayu/tools/web/web_search_providers.py:134-149` | **确认**：签名只有业务参数，无 token |
| 12 | `search_files` (Doc) 无 context/token | `dayu/tools/doc_tools.py:630-698` | **确认**：装饰器无 `execution_context_param_name`；`rglob` 循环内无 cancel 检查 |
| 13 | 5 个 Doc 工具均无 `execution_context_param_name` | `dayu/tools/doc_tools.py` (全局搜索) | **确认**：全文零命中 |
| 14 | Fins read 工具声明无 `execution_context_param_name` | `dayu/fins/tools/fins_tools.py` (全局搜索) | **确认**：全文零命中；9 个 `_create_*_tool` 工厂函数均未注入 |

**结论：Plan 的 root cause 判断基于直接代码证据，每条主张均可独立复现。**

## 3. Findings

### Finding 1 [BLOCKING] — Slice 1 Fins download/preprocess 的 callable 返回类型契约冲突

**严重性**: 阻塞（修复后可解除）

**证据**:
- `dayu/fins/tools/download_tools.py:47-51`: `FinsDownloadToolCallable.__call__` 返回类型声明为 `ToolExecutionOutcome`
- `dayu/fins/tools/download_tools.py:95`: 正常路径返回 `_awaiting_outcome_from_job_start(start)`
- `dayu/fins/tools/preprocess_tools.py:46-50`: 同模式

Plan Section 7 提出："direct Fins awaiting callable 可以直接返回 `ToolCancelledOutcome`，因为它不经过 legacy exception projection"。

**问题**: 当前 callable 直接实现 `ToolCallable` 协议（`(ToolCallRequest, BatchToolExecutionContext) -> ToolExecutionOutcome`），返回 `ToolCancelledOutcome` 在类型上完全合法。但 Plan Section 8 (Slice 1) 的 "Exact changes" 说 "返回 `ToolCancelledOutcome`"——这与当前 `FinsDownloadToolCallable` / `FinsPreprocessToolCallable` 的现有错误处理路径一致（它们已经返回 `ToolFailedOutcome` 和 `ToolAwaitingOutcome`），所以**不涉及契约变更**。

**裁决**: **Accepted** — 类型上无冲突。但 plan 应在 Section 6 明示 direct callable 返回 `ToolCancelledOutcome` 不需要修改 callable 协议签名，避免 implementation agent 误解。

**要求**: implementation gate 时在 Slice 1 的 Exact changes 中补充一句："callable 返回类型 `ToolExecutionOutcome` 已包含 `ToolCancelledOutcome`，无需修改协议"。

---

### Finding 2 [BLOCKING] — Slice 1 的 `request_cancel` 与 `executor.submit` 之间缺乏锁保护

**严重性**: 阻塞（修复后可解除）

**证据**:
- `dayu/fins/ingestion_runtime.py:1131-1173`: `_create_queued_job` 在 `self._start_lock` 内执行
- `dayu/fins/ingestion_runtime.py:1043-1050`: `executor.submit(...)` 在 `_start_lock` 外执行
- `dayu/fins/ingestion_runtime.py:1005`: `_start_lock = Lock()` 是 threading.Lock

Plan Section 8 (Slice 1) 提出：在 `_create_queued_job` 与 `executor.submit` 之间加入 token checkpoint；若取消则调用 `request_cancel` 且不 submit。

**问题**: 在 `_start_lock` 释放后、`executor.submit` 前的窗口内，token 可能从"未取消"变为"已取消"。此时 checkpoint 已过，job 被 submit 到 executor，但 token 实际已取消。这违反 Slice 1 Invariant："token cancelled between create and submit must leave job durable cancelling/cancelled and must not submit background operation."

当前正确的做法是：checkpoint 必须在锁持有期间完成，或使用更细粒度的"check-then-submit"原子区。

**要求**: 实现时必须将 token checkpoint 放在 `_start_lock` 持有区间内（即把 `_start_lock` 的范围扩展到覆盖 checkpoint + submit 决策），或者在锁释放后、submit 前做二次 checkpoint（若发现 cancel 则 `request_cancel` 且不 submit）。后者更简单且足够覆盖实际竞争窗口（时间极短）。Plan 应在 Slice 1 "Error handling" 或 "Invariants" 中明确此时序约束。

---

### Finding 3 [MEDIUM] — Doc tools 的 `list_files` checkpoint "inside file iteration" 对非递归模式而言粒度可能过重

**严重性**: 中等

**证据**:
- `dayu/tools/doc_tools.py:248-254`: `list_files` 在非递归模式用 `dir_path.glob(...)`，文件迭代为生成器遍历
- Plan Section 8 (Slice 3) 要求 `list_files` 加三个 checkpoint："before glob, inside file iteration, before return"

**问题**: `list_files` 的最大文件数受 `actual_limit = min(limit, max_files)` 和 `break` 约束，实际迭代次数有限。非递归 `glob` 通常只遍历单层目录，在绝大多数场景下不可感知。在文件迭代循环内加 cancel 检查带来的开销（每个 file_path 一次 `is_cancelled()` 调用）虽小但恒存在。Plan 应明确区分：只在 `recursive=True` 且目录深度大时，iteration checkpoint 才有实际收益；非递归模式只需 before glob + before return。

**建议**: 保持三个 checkpoint 作为防御性编程（`is_cancelled()` 是 O(1) 内存读取），但在 implementation report 中记录非递归模式的 checkpoint 是防御性的，不作为性能关键路径。**不阻塞**。

---

### Finding 4 [MEDIUM] — Fins read tools 的 `list_documents` / `get_document_sections` checkpoint 必要性质疑

**严重性**: 中等

**证据**:
- `dayu/fins/tools/fins_tools.py:184-210`: `list_documents` 直接调用 `read_runtime.list_documents(...)`，无循环、无 I/O（仓储层是本地/内存操作）
- Plan Section 8 (Slice 4) 要求所有 9 个 Fins read tools 注入 execution context 并加 checkpoint

**问题**: `list_documents` 和 `get_document_sections` 在实现上是单次仓储查询，背后无阻塞 I/O（当前仓储为本地文件系统）。在方法入口加 `is_cancelled()` 检查可以接受（防御性），但要求"repository list / meta / blob reads"等深层 checkpoint 对这些工具而言可能找不到有意义的插入点。Plan 说"按风险补 checkpoint"，但未给出具体到每个方法的判定标准。

**建议**: 在 Slice 4 "Exact changes" 中补充一段：对瞬时完成的方法（如 `list_documents`, `get_document_sections`, `get_page_content`），只需入口 checkpoint；对含搜索/迭代/大结果集的方法（如 `search_document`, `query_xbrl_facts`, `get_financial_statement`），在搜索循环/结果组装循环中补入循环内 checkpoint。这不改变 allowed files 集合，只是 checkpoint 密度的细化。

**裁决**: **Deferred-with-owner** → implementation agent 在 implement 时按上述原则裁决并记录在 implementation report 中。

---

### Finding 5 [LOW] — `web_search_providers.py` 中 `search_public_web` 的 provider fallback 循环取消语义需细化

**严重性**: 低

**证据**:
- `dayu/tools/web/web_search_providers.py:183-204`: provider fallback 循环
- Plan Section 8 (Slice 2) 要求："before each candidate provider attempt" checkpoint，且 "Cancelled search must not try later fallback providers"

**问题**: Plan 正确要求取消时停止 provider fallback。但 `search_public_web` 当前通过闭包传入 `timeout_budget` / `deadline_monotonic` 等预算参数。新增的 `cancellation_token` 参数也将通过闭包传入。实现时需注意：若 token 在第一个 provider 返回后、第二个 provider 前取消，应直接返回 `tool_cancelled` 而非尝试下一个 provider。Plan 的 invariant 已覆盖这点，但 Slice 2 "Exact changes" 在 "pass token into provider-specific helper" 处的描述略显模糊——应明确写"`search_public_web` 的 provider fallback 循环内在每次迭代开头做 checkpoint"。

**裁决**: **Accepted** — 当前表述可接受，但 implementation agent 必须在 `search_public_web` 的 `for candidate_provider in _candidate_providers(...)` 循环体内、`try:` 之前加入 cancel 检查。建议在 implementation report 中显式 audit 此位置。

---

### Finding 6 [LOW] — R3 (legacy adapter 投影为 failed outcome) 的 LLM 可见性差异未在 plan 中充分讨论

**严重性**: 低

**证据**:
- Plan Section 7: "legacy Web / Doc / Fins read tools 因 adapter 当前会把异常投影为 `ToolFailedOutcome`"
- Engine 设计: `ToolCancelledOutcome` → `tool_result_accepted` (EngineEvent), `ToolFailedOutcome` → `tool_result_accepted` (EngineEvent)
- AGENTS.md Agent 语义约束：LLM-facing 内容必须自足说明

**问题**: `ToolCancelledOutcome` 和 `ToolFailedOutcome(error="tool_cancelled")` 在 Engine 层都进入 `tool_result_accepted`，都会被注入为 LLM-facing tool message。但 adapter 当前投影的 failed outcome 可能在 LLM 视角显示为"工具执行失败"而非"工具已取消"。当前 `ToolBusinessError` 已有 `code="tool_cancelled"` 模式和对应的 hint，LLM 可以通过 hint 判断。这已在现有 Web fetch 取消路径（`_raise_fetch_cancelled`）中工作，所以**当前风险可控**。

**裁决**: **Accepted** — 无需在 plan 中展开。但 implementation gate 时需确认 Doc/Fins read tools 使用的取消异常（`ToolBusinessError(code="tool_cancelled")`）产生的 `ToolFailedOutcome` 在 LLM-facing tool result 中的文本是可理解的。若发现 hint 不清晰，implementation agent 可优化取消异常的 message/hint。

---

### Finding 7 [INFO] — Slice 5 的 audit matrix 测试范围可能缩水

**严重性**: 信息

**证据**:
- Plan Section 8 (Slice 5): "Add an audit matrix test or explicit assertions in provider tests"
- Plan Section 8 (Slice 3-4): Doc 5 tools + Fins read 9 tools = 14 tools 需注入 execution context
- 当前 `tests/tools/test_doc_tools_provider.py` 715 行, `tests/fins/test_fins_ingestion_tools.py` 1067 行

**问题**: Plan 说"至少一个 per risk class"的测试覆盖。但 14 个 tools 分散在 4 个风险等级中，实际可能只有 4-5 个新测试。Implementation agent 可能将此解释为最低限度，导致某些工具（如 `get_table`, `get_page_content`）的 context 注入只在 audit matrix 的声明级断言中被验证，而非行为级测试。这是合理的取舍，但应在 plan 中承认此为已知覆盖缺口。

**裁决**: **Accepted** — 当前覆盖策略可接受。Plan 已说"prefer behavior tests"且"provider declaration tests assert all Fins read declarations have execution context injection metadata"。Implementation report 应记录哪些工具仅被 audit matrix 覆盖、哪些有独立行为测试。

---

## 4. Plan Quality Assessment

### 4.1 设计真源对齐

| 检查项 | 状态 | 证据 |
|--------|------|------|
| Host cancel 真源不变 | **通过** | Plan Section 2, Section 3, Section 6 反复声明；不修改 Host durable schema/状态机 |
| Engine cancel 观察语义不变 | **通过** | Plan Section 3 对齐 `docs/engine/design.md:391-421` 的取消观察契约 |
| 工具不引入私有 cancel 状态 | **通过** | Plan Section 2 "不用工具私有 cancel 状态替代 Host durable cancel" |
| Fins storage 约束 | **通过** | Plan Section 3 "本 WU 不绕过仓储"；Slice 4 invariant "Financial document access remains through dayu.fins.storage protocols" |
| 分层边界 | **通过** | 不改 `dayu.runtime`，不改反向依赖 |

### 4.2 过度设计检查

| 检查项 | 状态 |
|--------|------|
| 不新增 Host/Engine public contract | **通过** |
| 不新增 durable schema / 状态机 | **通过** |
| 不复用已有 infrastructure（token, adapter, job store） | **通过**（全部复用） |
| 两阶段启动是否合理 deferred | **通过**（Section 6 详细评估代价，正确识别为跨 Host wait adapter + Fins runtime 的大契约变更） |

### 4.3 Scope 边界

**通过**。Non-goals (Section 2) 清晰列举了 6 项不做的事，每项都有 why + owner/destination。

### 4.4 Slice 可实现性

| Slice | 可实现 | 风险 |
|-------|--------|------|
| Slice 1: Fins Awaiting | **是**，需修复 Finding 2 | 竞争窗口处理 |
| Slice 2: Web Search | **是** | 无 |
| Slice 3: Doc Tools | **是**，需细化 Finding 4 | checkpoint 粒度 |
| Slice 4: Fins Read | **是**，需细化 Finding 4 | checkpoint 粒度 |
| Slice 5: Audit + Validation | **是** | 覆盖可能缩水 (Finding 7) |

### 4.5 AGENTS.md / CLAUDE.md 合规检查

| 规则 | Plan 中的处理 | 状态 |
|------|-------------|------|
| 中文 docstring | Section 8 Slice 1 "docstring 中文完整"，工具新增 helper 示意遵循 | **通过**（implementation agent 必须执行） |
| 类型 `CancellationToken \| None` | Section 7 显式禁止 `object`/`Any`/extra payload | **通过** |
| 禁止兼容性代码 | Section 7 多处表示不为旧测试保留兼容逻辑 | **通过** |
| pyright | Section 9 要求 pyright pass | **通过** |
| 测试覆盖 >= 80% | Section 8 每个 Slice 含 Tests 子节；Section 9 含验证命令 | **通过** |
| README 触发 | Section 10 + Section 2 non-goal: "不修改 README... implementation gate 再按 AGENTS.md 检查并更新" | **通过**（责任明确交给实现 gate） |
| 禁止 god helper | Section 7 "不新增 god helper"，每个工具族模块级私有 helper | **通过** |
| Fins storage 约束 | Slice 4 invariant 显式声明 | **通过** |

### 4.6 状态机 / Contract 漏洞检查

| 检查项 | 状态 |
|--------|------|
| Host Run/Attempt 状态机不变 | **通过** |
| Engine EventLog 不变 | **通过** |
| Fins job 状态机不新增状态 | **通过** (Section 6 "只复用 QUEUED/RUNNING/CANCELLING/CANCELLED") |
| BatchToolExecutionContext contract 不变 | **通过** |
| ToolCallable 协议签名不变 | **通过** (Finding 1 确认) |

## 5. Residual Risks / Uncovered Areas

| ID | 风险 | Plan 中状态 | 评审补充 |
|----|------|-----------|---------|
| R1 | 两阶段启动 orphan job 窗口 | Deferred → WU-WAIT-03 | Plan 评估充分，mitigation 合理 |
| R2 | Synchronous 调用不可抢占 | Accepted | 正确识别为物理限制 |
| R3 | Legacy adapter 投影为 failed 而非 cancelled | Accepted | Finding 6 补充了 LLM 可见性关注点 |
| R4 | Fins read runtime 深层 checkpoint 待裁决 | Deferred → implementation agent | Finding 4 提供了裁决标准 |
| **R5 (新增)** | `start_download/start_preprocess` 的锁/checkpoint 时序竞争 | Plan 未显式提及 | Finding 2 提供了修复方案 |
| **R6 (新增)** | Doc `list_files` 非递归模式的过度 checkpoint | Plan 未区分 | Finding 3 提供了区分建议 |
| **R7 (新增)** | 14-tool audit matrix 可能出现声明级覆盖 vs 行为级覆盖的不平衡 | Plan 未详述 | Finding 7 要求 implementation report 记录 |

## 6. Verdict

**Plan 可进入 fix（修改 Finding 1 和 Finding 2 的标注后即可进入 implementation gate）。**

两个 blocking finding 都是 plan 文本层面的补充性修改，不要求重新设计或重新获取证据。修复方式：

- **Finding 1**: 在 Slice 1 "Exact changes" 中加一句说明 direct callable 返回 `ToolCancelledOutcome` 类型上已合法
- **Finding 2**: 在 Slice 1 "Invariants" 或 "Error handling" 中补充 token checkpoint 与 `_start_lock` 的时序约束

修复后 plan 达到 code-generation-ready 标准。

## 7. Artifact Metadata

- **输出路径**: `docs/reviews/wu-tools-01-f01-02-plan-review-ds.md`
- **Reviewer**: AgentDS
- **Review 类型**: plan review gate
- **Blocking**: 是（2 blocking findings，均为文本级修复）
- **审查文件**: 仅本 artifact；未修改任何生产代码、测试、README 或控制文档
