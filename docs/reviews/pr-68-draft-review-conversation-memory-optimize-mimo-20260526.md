# Code Review

## Scope

- Mode: PR
- Branch: feat/phase-12-5-conversation-memory-optimize
- Base: main
- PR: #68
- URL: https://github.com/noho/dayu-agent-r/pull/68
- Author: noho
- Output file: docs/reviews/pr-68-draft-review-conversation-memory-optimize-mimo-20260526.md
- Included scope: PR #68 full diff (280 files, ~45K lines) through commit efcf332. Covers Host conversation memory / compaction redesign (P12.5 + P12.6), conversation memory smoke test, engine SSE parser / tool_call_aggregator fixes, runtime config loader changes, service host_assembly compactor scene wiring.
- Excluded scope: docs/reviews/ artifacts (review metadata, not production code)
- Parallel review coverage: 5 subagents covering compaction/memory core, dispatch/state machine, new modules/smoke test, engine/runtime/layering, test coverage. All subagent findings integrated and deduplicated below.

## Findings

未发现 blocking 实质性问题。

以下为 non-blocking residuals，均不阻塞 draft-PR-pass：

### N1-非阻塞-低-smoke test 死分支

- **入口/函数**: `utils/smoke_host_public_conversation_memory.py:1097-1099` `_compact_pressure_reserve_tokens`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory.py:1097-1099`
- **输入场景**: 任意 `context_window_size`
- **实际分支**: `if context_window_size >= LARGE_WINDOW` 和 `else` 分支返回相同值
- **预期行为**: 大窗口和小窗口应返回不同预留 token 数
- **实际行为**: 两个分支均返回 `_COMPACT_PRESSURE_RESERVE_TOKENS`
- **直接证据**: `return _COMPACT_PRESSURE_RESERVE_TOKENS` 在 if 和 else 中完全相同
- **影响**: 无功能影响；条件判断为死代码
- **建议改法和验证点**: 删除条件判断或为大窗口设置不同值
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### N2-非阻塞-低-PinnedStateView docstring 过期

- **入口/函数**: `dayu/host/memory.py:377` `PinnedStateView.__post_init__`
- **文件(行号)**: `dayu/host/memory.py:375-387`
- **输入场景**: `open_questions` 包含重复项
- **实际分支**: 代码静默去重（`_dedupe_text_tuple_by_normalized_text`）
- **预期行为**: docstring 声称"open questions 内部重复时抛出"
- **实际行为**: 静默去重，不抛出异常
- **直接证据**: `object.__setattr__(self, "open_questions", _dedupe_text_tuple_by_normalized_text(self.open_questions))` 替代了旧的 ValueError 逻辑
- **影响**: 无功能影响；docstring 误导
- **建议改法和验证点**: 更新 docstring 移除"重复时抛出"描述
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### N3-非阻塞-低-cross-module helper 签名分歧

- **入口/函数**: `dayu/host/compact_material.py:1847` vs `dayu/host/evidence.py:449` vs `dayu/host/compaction_evidence.py:508`
- **文件(行号)**: 三个模块各自的 `_require_non_empty_text`
- **输入场景**: 维护者跨模块复制调用
- **实际分支**: `compact_material.py` 版本接受 `str | None`，其余两个版本只接受 `str`
- **预期行为**: 同名私有 helper 应有统一签名
- **实际行为**: 签名不一致
- **直接证据**: `compact_material.py:1847` 参数类型为 `value: str | None`，`evidence.py:449` 为 `value: str`
- **影响**: 维护陷阱；无运行时影响
- **建议改法和验证点**: 统一签名或重命名 `compact_material.py` 版本为 `_require_optional_non_empty_text`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### N4-非阻塞-低-multi-pass attempt 预算共享未文档化

- **入口/函数**: `dayu/host/compaction_operation.py:126` `run_compaction_operation`
- **文件(行号)**: `dayu/host/compaction_operation.py:103-130`
- **输入场景**: `pass_queue` 包含多个 pass request
- **实际分支**: `attempt_number` 跨 pass 递增，不按 pass 重置
- **预期行为**: 若 N 个 pass 各需 max_attempts 次重试，总预算为 N * max_attempts
- **实际行为**: 总预算为 max_attempts，所有 pass 共享
- **直接证据**: `attempt_number = 1` 在循环外初始化，while 条件 `attempt_number <= max_attempts` 跨 pass 检查
- **影响**: 设计意图（共享 proposal attempt 预算）已通过测试验证（`test_compaction_operation.py:627`）；docstring 未说明此行为
- **建议改法和验证点**: 在 docstring 中明确"所有 pass 共享 attempt 预算"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### N5-非阻塞-低-weak_typing_guard 未覆盖 dayu.host

- **入口/函数**: `tests/service/test_weak_typing_guard.py`
- **文件(行号)**: `tests/service/test_weak_typing_guard.py`
- **输入场景**: PR 新增大量 `dayu.host/` 生产代码
- **实际分支**: weak_typing_guard 只扫描 `dayu.service/`
- **预期行为**: 若项目按层做 weak typing guard，`dayu.host/` 也应覆盖
- **实际行为**: 无对应 `tests/host/test_weak_typing_guard.py`
- **直接证据**: `test_weak_typing_guard.py` 中 `HOST_DIR` 指向 `dayu.service`
- **影响**: 若 `dayu.host/` 引入 `Any`/`object`，无自动检测
- **建议改法和验证点**: 考虑为 `dayu.host/` 添加类似 guard（如项目约定需要）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Validation Reviewed

- **架构边界**: `dayu.runtime` 无 import from `dayu.engine/host/service/ui/fins`；`dayu.host` 无 import from `dayu.service/ui`。通过。
- **CancellationToken 接口**: `cancel_reason()` 在 main 的 Protocol 中已存在，本次无接口变更。`LocalWorkerHandle.on_cancel(reason)` 替代旧 `handle.cancel(reason)`，与 `api.py:652` 协议声明一致。通过。
- **Host 状态机**: `_DurableRunCancellationToken` fail-closed 设计正确；`cancel_all` 替代旧循环，同时传播 token 和 hook；lag repair rebuild-then-retry 有两层升级保护。通过。
- **Compaction 多 pass 合并**: `_merge_pass_candidates` 正确去重 evidence/facts/preserve items/ranges，取 `min(budget_after_compact)`。通过。
- **Memory projection**: snapshot lag 检测 → rebuild → retry → outer closeout 升级链路完整。通过。
- **Smoke test**: 只使用 public Host API（`open_host`/`ensure_session`/`submit_followup`/`watch_session_events`/`get_session`/`get_run`），无内部模块 import。4 轮生命周期覆盖 fact 确认 → 压力 → 话题转移 → fact 一致性。通过。
- **Engine 修复**: SSE parser 空 choices 防护、tool_call_aggregator 合成 index 防碰撞、agent.py 敏感值 regex 检测均为正向修复。通过。
- **Service 装配**: compactor scene 装配链（`prepare_scene` → `_compactor_prompts_from_scene_inputs` → `_read_compactor_user_prompt_template`）路径遍历防护（`relative_to` 校验）正确。通过。
- **README 一致性**: `dayu/host/README.md` 已同步更新 compaction、memory projection、ToolRuntime、close 语义。通过。
- **测试覆盖**: cancellation / quality rejection / budget exceeded / multi-pass merge / memory lag repair / E2E smoke 均有覆盖，断言具体到字段值级别。通过。

## Areas Not Covered

- `dayu/host/llm_compaction.py` 内部 LLM 调用逻辑细节（由 subagent 1 覆盖，未发现 blocking 问题）
- `dayu/host/context_governance.py` 完整走读（由 subagent 2 覆盖核心路径）
- `docs/` 目录下的 design docs 和 implementation plan 内容（非生产代码）
- `workspace/` 目录下的讨论文档（非生产代码）
- CI checks（PR 无 checks reported）
