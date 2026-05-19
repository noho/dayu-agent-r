# Host-owned Compactor 最终整体 Review

## Scope

- Mode: current changes
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/host-owned-compactor-final-review-mimo-20260519-115936.md`
- Included scope: 从 `main` 到 `HEAD` 的完整变更，聚焦 7 个检查维度
- Excluded scope: `dayu/runtime/`（零变更）、`dayu/ui/`、`dayu/service/`、`dayu/fins/`
- Parallel review coverage: 7 个 subagent 分别覆盖
  1. 设计文档一致性（design.md / plan.md / implementation-control.md）
  2. Host public contract（`__init__.py` / `api.py`）
  3. LLMContextCompactor + compaction_operation + context_events + context_policy
  4. dispatch / admission / open_host
  5. Engine runner / engine_ingest / durable state / runtime
  6. manual smoke + 测试覆盖
  7. README 同步

---

## Findings

### 001-未修复-[高]-`thread.join()` 无超时可致 Host governance 线程永久阻塞

- **入口/函数**: `LLMContextCompactor.compact()` -> `_run_agent_request_sync()`
- **文件(行号)**: `dayu/host/llm_compaction.py:243-244`
- **输入场景**: LLM provider 底层 HTTP 调用永久挂起（超出 AgentPolicy 配置的保护范围时）
- **实际分支**: `thread.start()` 后 `thread.join()` 无 timeout 参数
- **预期行为**: Host governance 层发起的 compaction LLM 调用应有强制超时保护，超时后 raise `LLMCompactionProposalError` 交由 `compaction_operation` 处理
- **实际行为**: 如果 Engine runner 底层 LLM provider 永久挂起，`thread.join()` 永久阻塞，Host dispatch scheduler 的 governance 路径卡死
- **直接证据**: `llm_compaction.py:243` — `thread.join()` 无 timeout；`AgentPolicy.max_iterations=1` 和 `continuation_max_attempts=0` 只限制重试次数，单次 LLM 推理无强制超时
- **影响**: Host compaction 操作永久阻塞 -> 该 Run 的 dispatch 停滞 -> Session 级联不可用
- **建议改法和验证点**: 给 `thread.join(timeout=合理秒数)` 加超时，超时后 `thread` 仍在后台运行需处理（可考虑 daemon thread 或后续 cleanup），raise `LLMCompactionProposalError` 让 `compaction_operation` 的 attempt 循环正常推进
- **修复风险（低/中/高）**: 低
- **严重程度（高）**: 生产环境 LLM provider 不稳定时可直接触发

### 002-未修复-[中]-`_budget_after_compact` 在 `hard_threshold_tokens == 1` 时返回 0

- **入口/函数**: `_budget_after_compact()`
- **文件(行号)**: `dayu/host/llm_compaction.py:490-499`
- **输入场景**: `ContextBudgetPolicy` 配置 `hard_threshold_tokens = 1`
- **实际分支**: `min(half_estimate, 1 - 1)` = `min(half_estimate, 0)` = `0`
- **预期行为**: compact 后预算应 > 0，否则 compact 完全无意义
- **实际行为**: 返回 0，语义上"compact 后零预算"意味着 compact 完全无效
- **直接证据**: `llm_compaction.py:496` — `return min(half_estimate, estimate.hard_threshold_tokens - 1)`；`context_policy.py` 的 `_require_positive_int` 校验 `hard_threshold_tokens >= 1`，允许值为 1
- **影响**: compact 成功但 budget 为 0，后续 Run 无法正常执行
- **建议改法和验证点**: `_require_positive_int` 改为 `_require_int_ge(2)` 或 `_budget_after_compact` 内加 `max(1, ...)` 下限保护
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 需要不常见配置才能触发，但一旦触发影响 Run 可用性

### 003-未修复-[中]-Host orchestration retry loop 无集成测试

- **入口/函数**: `run_compaction_operation()` + dispatch/ingest 调用方
- **文件(行号)**: `dayu/host/compaction_operation.py:71-177`，测试缺口
- **输入场景**: compaction quality rejected -> retry -> 再次 rejected -> 达上限 -> fail
- **实际分支**: 无测试覆盖
- **预期行为**: Host orchestration 层对 "quality rejected -> retry -> 再次 rejected -> 达上限 -> fail" 的完整闭环应有集成测试
- **实际行为**: `test_compaction_contract.py` 只测单次 quality check；`test_llm_compaction.py` 只测 LLMCompactor 层面错误映射；不涉及 retry policy 驱动的多 attempt 循环
- **直接证据**: `test_llm_compaction.py` 和 `test_compaction_contract.py` 中无 `max_attempts > 1` 的测试场景
- **影响**: compaction retry loop 是 compaction 可靠性的核心路径，当前为黑盒
- **建议改法和验证点**: 补充 `max_attempts=3`，mock quality check 前两次 rejected、第三次 accepted 的测试；补充 `max_attempts=3`，三次全部 rejected 最终 fail 的测试
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 功能正确性未被验证

### 004-未修复-[中]-compaction 失败后 Host 行为无测试

- **入口/函数**: `_execute_proactive_compaction()` / `_execute_reactive_compaction()`
- **文件(行号)**: `dayu/host/dispatch.py`，`dayu/host/engine_ingest.py`
- **输入场景**: compactor 最终失败（`fail_compaction`）
- **实际分支**: 无测试
- **预期行为**: 当 compaction 最终失败，Host 如何决定后续 Run 行为（hard threshold block vs 放行）应有测试
- **实际行为**: 无对应测试
- **直接证据**: 测试文件中无 `CompactionOperationResult.failure_reason` 非 None 的集成场景
- **影响**: compaction 失败后 Run 的行为未被验证
- **建议改法和验证点**: 补充 compaction 失败后 Run 是否被 hard threshold block 或正常放行的测试
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: failure path 行为未验证

### 005-未修复-[中]-无 reactive compaction 集成测试

- **入口/函数**: `_execute_reactive_compaction()` via `engine_ingest.py`
- **文件(行号)**: `dayu/host/engine_ingest.py:1325-1473`
- **输入场景**: provider_overflow 触发的 reactive compaction
- **实际分支**: 无端到端测试
- **预期行为**: reactive 路径（带 `attempt_id` / `execution_id`）应有端到端验证
- **实际行为**: 只在 event payload validator 层面有测试（`test_context_compact_events.py`），无 orchestration 层端到端验证
- **直接证据**: 无测试文件覆盖 reactive compaction orchestration
- **影响**: reactive compaction 路径的正确性未被端到端验证
- **建议改法和验证点**: 补充 mock provider_overflow -> reactive compaction trigger -> artifact 产出的集成测试
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: reactive 路径是 compaction 的重要触发源

### 006-未修复-[中]-`test_public_compact_smoke.py` 断言偏弱

- **入口/函数**: `test_public_compact_smoke.py`
- **文件(行号)**: `tests/host/test_public_compact_smoke.py`
- **输入场景**: compaction 成功后的 artifact 验证
- **实际分支**: 只检查 `new_artifacts > 0` 和 `artifact_kind == context_compaction`
- **预期行为**: 应断言 `quality_result.accepted == True`、`budget_after_compact` 为正整数、`episode_summary_candidate.evidence_refs` 非空、`pinned_state_patch_candidate` 结构完整性
- **实际行为**: 仅通过性检查，不能有效捕获 artifact 结构退化
- **直接证据**: 测试中无对 artifact 内容字段的深层断言
- **影响**: artifact 结构退化不会被 smoke 捕获
- **建议改法和验证点**: 增加对 artifact 关键字段的深层断言
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 测试有效性不足

### 007-未修复-[中]-`CONTEXT_COMPACTED` 和 `CONTEXT_COMPACTION_FAILED` 互斥约束无测试

- **入口/函数**: dispatch/ingest compaction result writing
- **文件(行号)**: `dayu/host/dispatch.py`，`dayu/host/engine_ingest.py`
- **输入场景**: compaction 操作完成后 event 写入
- **实际分支**: 无互斥约束断言
- **预期行为**: `CONTEXT_COMPACTED` 和 `CONTEXT_COMPACTION_FAILED` 不应同时出现在同一 Run 上
- **实际行为**: 这个互斥约束没有测试
- **直接证据**: 测试文件中无 event 互斥性断言
- **影响**: 事件一致性约束未被验证
- **建议改法和验证点**: 补充断言同一 Run 上 COMPACTED 和 FAILED 不同时出现
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 事件一致性是审计和恢复的基础

### 008-未修复-[低]-README.md 断链 `docs/host/interface-discussion-notes.md`

- **入口/函数**: README.md 文档导航
- **文件(行号)**: `README.md:19`，`README.md:1169`
- **输入场景**: 用户点击文档链接
- **实际分支**: 链接指向 `docs/host/interface-discussion-notes.md`
- **预期行为**: 链接应指向实际存在的文件
- **实际行为**: 实际文件名是 `docs/host/discussion-note.md`，链接 404
- **直接证据**: `README.md:19` 和 `README.md:1169` 引用 `docs/host/interface-discussion-notes.md`
- **影响**: 用户点击后 404
- **建议改法和验证点**: 修改链接为 `docs/host/discussion-note.md`
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 文档可用性

### 009-未修复-[低]-README.md 断链 `dayu/web/README.md`

- **入口/函数**: README.md 功能说明链接
- **文件(行号)**: `README.md:316`
- **输入场景**: 用户点击文档链接
- **实际分支**: 链接指向 `dayu/web/README.md`
- **预期行为**: 链接应指向实际存在的文件
- **实际行为**: `dayu/web/` 目录不存在，链接 404
- **直接证据**: `README.md:316` 引用 `dayu/web/README.md`
- **影响**: 用户点击后 404
- **建议改法和验证点**: 删除或修正该链接
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 文档可用性

### 010-未修复-[低]-README.md "Host 层正在重写中" 已过时

- **入口/函数**: README.md 项目描述
- **文件(行号)**: `README.md:5`
- **输入场景**: 用户阅读项目概述
- **实际分支**: 描述为"Host 层正在重写中"
- **预期行为**: 应反映 Host 已完成 P10.5 public contract freeze 的当前状态
- **实际行为**: 措辞暗示 Host 仍处于重写进行中
- **直接证据**: `README.md:5` — "Host 层正在重写中"
- **影响**: 误导用户对项目成熟度的判断
- **建议改法和验证点**: 更新为当前 Phase 10.5 状态描述
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 文档准确性

### 011-未修复-[低]-`open_host.__aenter__` exception handler 不关闭 scheduler

- **入口/函数**: `open_host.__aenter__`
- **文件(行号)**: `dayu/host/open_host.py:482-489`
- **输入场景**: `HostDispatchScheduler.open` 成功但后续 `create_host_admission_service` 或 `HostCommandHandle` 构造抛错
- **实际分支**: except handler 只关闭 `durable_store`
- **预期行为**: scheduler 已打开但构造失败时应被关闭
- **实际行为**: scheduler 不会被关闭
- **直接证据**: `open_host.py:482-489` — except handler 中无 `scheduler.close()` 调用
- **影响**: 资源泄漏（scheduler 内部的 lane、task cancel 等）
- **建议改法和验证点**: 在 except handler 中增加 `scheduler.close()` 的 best-effort 调用
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 当前构造器不会抛错，实际风险极低

### 012-未修复-[低]-`dayu/host/__init__.py` docstring 旧 Phase 引用

- **入口/函数**: 模块 docstring
- **文件(行号)**: `dayu/host/__init__.py:1`
- **输入场景**: 阅读模块概述
- **实际分支**: docstring 写 "Phase 4 已实现的 Session / Run public facade"
- **预期行为**: 应反映当前 Phase 10.5 状态
- **实际行为**: Phase 引用过时
- **直接证据**: `__init__.py` 第一行 docstring
- **影响**: 误导开发者对模块成熟度的判断
- **建议改法和验证点**: 更新为当前 Phase
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 文档准确性

### 013-未修复-[低]-`run_compaction_operation` 缺少 `max_attempts >= 1` 入口校验

- **入口/函数**: `run_compaction_operation()`
- **文件(行号)**: `dayu/host/compaction_operation.py:71`
- **输入场景**: 直接调用 `run_compaction_operation(max_attempts=0)`
- **实际分支**: `for` 循环不执行，直接返回 `_FAILURE_MAX_ATTEMPTS_EXHAUSTED`
- **预期行为**: 应在入口校验 `max_attempts >= 1`
- **实际行为**: 返回"耗尽"结果而非错误
- **直接证据**: `compaction_operation.py:71` — 无入口校验；`ContextBudgetPolicy.__post_init__` 校验 `max_compaction_attempts_per_operation >= 1` 保护了正常装配路径
- **影响**: 误用时返回语义错误的结果
- **建议改法和验证点**: 在函数入口加 `_require_positive_int` 校验
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 正常装配路径已受保护

---

## Open Questions

- `USER_INPUT_ACCEPTED` payload 中 `user_prompt` 与 `display_text` 冗余存储是否有意为之（是否会有 `display_text != user_prompt` 的场景）？
- `compactor_policy_ref` 字段在 `HostLocalExecutionOptions` 中的最终去留（当前硬编码 `None`，字段仍保留）？
- design.md 要求"每次外部 LLM call 前后 recheck"，当前实现只在 operation 结束后 recheck，多次 repair attempt 之间无逐次 recheck——是否接受此偏差？

---

## Residual Risk

- **测试缺口（中等）**: Host orchestration retry loop、compaction failure 后 Host 行为、reactive compaction 端到端、event 互斥约束均无集成测试
- **smoke 依赖真实 provider**: `test_public_compact_smoke.py` 只有 1 个测试用例且依赖 DeepSeek API key，CI 上形同虚设
- **`thread.join()` 无超时**: 生产环境 LLM provider 不稳定时可直接触发 Host governance 线程永久阻塞

---

## 7 维检查结论

| 维度 | 结论 | 说明 |
|------|------|------|
| 1. Service-facing public contract 只暴露 CompactorRunnerBaseline | **PASS** | `__init__.py.__all__` 只导出 `CompactorRunnerBaseline`；`ContextCompactor`/prompt/candidate/quality/policy_ref 均未暴露 |
| 2. Host 拥有 compaction timing/prompt/candidate/quality/event/artifact/memory 边界 | **PASS** | `LLMContextCompactor` 只做单次 proposal；循环/策略/EventLog/artifact/memory projection 全在 Host governance 层 |
| 3. Engine 低层 retry 与 Host semantic retry 分层 | **PASS** | Engine runner 零 compaction 语义；`compaction_operation.py` 独立封装 Host semantic retry |
| 4. EventLog/HostEvent 留痕完整性 | **PASS** | 4 个 canonical event 覆盖完整生命周期；steer/retry/replay 路径事件链完整 |
| 5. manual smoke 走 public opener -> Host-owned compactor -> artifact -> 多轮闭环 | **PASS** | smoke 真实走三轮闭环；但 artifact 断言偏弱（Finding 006） |
| 6. README 与当前代码一致 | **PASS（有 minor 问题）** | 主要同步点已完成；存在 2 处断链和过时措辞（Finding 008-010） |
| 7. correctness/stability/security finding | **有需修复项** | `thread.join()` 无超时（Finding 001，高）；budget 边界（Finding 002，中）；测试缺口（Finding 003-007，中） |

---

## 总结

**结论: FAIL**

存在 1 个高严重度 finding（`thread.join()` 无超时可致 Host governance 线程永久阻塞）和 6 个中严重度 finding（budget 边界 + 5 个测试缺口）。高严重度 finding 是 correctness/stability blocker，需在 ship 前修复。中严重度 finding 的测试缺口应在后续迭代中补齐。

**建议优先级:**
1. **必须修复（ship blocker）**: Finding 001 — `thread.join()` 加超时
2. **强烈建议修复**: Finding 002 — budget 下限保护
3. **建议补齐（不 block ship 但应尽快）**: Finding 003-007 — 测试缺口
4. **低优先级清理**: Finding 008-013 — 文档/代码清理
