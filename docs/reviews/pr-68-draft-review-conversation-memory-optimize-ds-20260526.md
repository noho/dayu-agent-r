# Code Review — PR 68 Draft PR Gate

## Scope

- Mode: PR
- PR: https://github.com/noho/dayu-agent-r/pull/68
- Title: P12.5 conversation memory evidence-backed facts
- Head: `feat/phase-12-5-conversation-memory-optimize`
- Base: `main`
- Output file: `docs/reviews/pr-68-draft-review-conversation-memory-optimize-ds-20260526.md`
- Included scope: PR 68 full diff (280 files, 45390 insertions, 2143 deletions), covering conversation memory evidence-backed facts redesign, ToolRuntime payload cold/hot split, proactive/reactive compaction material/segment selection, `_DurableRunCancellationToken`, compactor scene assembly, and public conversation memory smoke.
- Excluded scope: Prior review artifacts in `docs/reviews/` (informational only).
- Parallel review coverage: 无（主 reviewer 单线完成全部 review）。

## Verdict: PASS

未发现应阻塞 draft-PR-pass 的 blocking finding。

## Blocking Findings

未发现实质性问题。

## Non-blocking Findings / Residuals

### 1. 非阻塞 — `CompactorRunnerBaseline` 公开 LLM prompt 字段

- **入口/函数**: `CompactorRunnerBaseline` (`dayu/host/api.py:949-959`)
- **文件(行号)**: `dayu/host/api.py:949-959`
- **输入场景**: `OpenHostOptions` 构造时 caller 直接传入 `compactor_agent_policy`、`compactor_system_prompt`、`compactor_user_prompt_template`
- **实际分支**: 这些字段作为 `CompactorRunnerBaseline` 的公开字段暴露给 Service 装配层
- **直接证据**: `dayu/host/api.py:925-928` 的 `CompactorRunnerBaseline` 文档和 `__post_init__` 校验
- **影响**: 这些 LLM-facing prompt 字段已在 Host public API 中暴露。当前设计是合理的 — Service 装配层从 scene assets 中读取并填入，Host 不解释 prompt 内容。但未来若 prompt 结构变更可能影响 Host public API。
- **建议**: 当前设计可接受。不需要修改。
- **严重程度**: 低

### 2. 非阻塞 — `_DurableRunCancellationToken` 无 `requested_at()` 时间戳

- **入口/函数**: `_DurableRunCancellationToken.requested_at()` (`dayu/host/dispatch.py:643-652`)
- **文件(行号)**: `dayu/host/dispatch.py:643-652`
- **输入场景**: Engine runner 检查 proactive compaction 取消 token 的 `requested_at()`
- **实际行为**: 始终返回 `None`
- **直接证据**: `dayu/host/dispatch.py:643-652` 的 docstring 明确说明 "始终返回 None"
- **影响**: Engine 无法获取 proactive compaction 取消请求时间。当前 Engine 不依赖此值，但若未来 Engine 需要此信息做 timeout/deadline 判断，需要补充。
- **建议**: 当前可接受。如果 Engine 未来需要时间戳，可以在 `cancel_reason()` 返回非 None 时从 durable state 合成。
- **严重程度**: 低

### 3. 非阻塞 — smoke 脚本使用 `dayu.host.*` wildcard import

- **入口/函数**: `utils/smoke_host_public_conversation_memory.py` imports
- **文件(行号)**: `utils/smoke_host_public_conversation_memory.py:64-79`
- **输入场景**: 脚本导入 `from dayu.host import (EnsureSessionRequest, FollowupBehavior, Host, ...)`
- **实际分支**: 通过 `dayu.host` public module 导入（`dayu/host/__init__.py` 的 `__all__`）
- **直接证据**: smoke 脚本只使用 `dayu/host/__init__.py` `__all__` 中声明的公开符号
- **影响**: 不违反架构约束。smoke 脚本作为 `utils/` 下的验证脚本，通过 public API 使用 Host 是正确的。
- **建议**: 无需修改。
- **严重程度**: 低

## Validation Reviewed

| 验证项 | 状态 | 证据 |
|---|---|---|
| `dayu.runtime` 层中立 | 通过 | 只 import `dayu.contracts` 和 `dayu.runtime._digest`，无上层依赖 |
| Host public API 变更 | 通过 | `ToolBundleSourceKind`/`ToolBundleSourceRef` 正确从 `__init__.py` 移除；`CompactorRunnerBaseline` 新增字段合理 |
| `_DurableRunCancellationToken` | 通过 | proactive compaction 在 worker 启动前执行，直接读 durable Run 状态是正确的设计选择 |
| `ActiveWorkerRegistry.cancel_all()` | 通过 | cancellation token 为主通道，`handle.on_cancel()` 为补充 best-effort hook |
| `HostDispatchScheduler.close()` | 通过 | 使用 `cancel_all()` 替代逐个 `_safe_cancel_worker_handle()` |
| ToolRuntime payload cold/hot split | 通过 | `_tool_result_payload_plan()` 正确实现 inline/SQLite 分离 |
| Compact material/segment selection | 通过 | 确定性 selection、prompt-local labels、canonical provenance 映射正确 |
| Reactive multi-pass compaction | 通过 | `_reactive_compaction_pass_queue()` 单 block per pass，合并逻辑在 `_merge_pass_candidates()` |
| CompactionRequest 字段变更 | 通过 | `context_events.py` 显式拒绝旧字段名，向前不兼容保护 |
| Evidence-backed fact 替换 verified fact | 通过 | `EvidenceBackedFactView` 正确要求 `HOST_PROJECTION` provenance 和 evidence refs |
| Conversation memory smoke | 通过 | 只使用 public Host API (`open_host`, `ensure_session`, `submit_followup`, `watch_session_events`, `get_session`, `get_run`)，无 durable store 内部读取 |
| 引擎 SSE tool_call_aggregator 修复 | 通过 | 合成 index 使用负数 keyspace，`_sorted_partial_indices()` 分区排序，`_index_by_position` 提供位置回退 |
| 引擎 agent sensitive exception 脱敏 | 通过 | 从子串匹配改为 regex 模式匹配，更精确避免误判 |
| README/docs 一致性 | 通过 | `max_verified_facts` → `max_evidence_backed_facts` 在 config loader、execution profiles、README 中一致 |

## Areas Not Covered

- 真实 LLM provider 调用（smoke 脚本需要真实 API key，不在本 review 范围内执行）
- Service assembly 的 `prepare_scene` 与 compactor scene asset 的端到端集成测试
- `dayu/host/compact_material.py` 1904 行的完整逐行走读（已覆盖核心 `build_compact_material_pack`、`select_compact_segment`、`run_input_material_block`、`prompt_local_evidence_map`）
- `dayu/host/compaction_evidence.py` 528 行的完整逐行走读（已覆盖 evidence block extraction core path）
- `dayu/host/evidence.py` 的 SQLite payload corruption recovery path
