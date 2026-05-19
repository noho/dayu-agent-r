# Code Review

## Scope

- Mode: PR
- PR: #62 — Host P10.5 ordinary local multi-turn public contract freeze
- Author: noho
- Branch: `feat/host-p10-5-public-contract-freeze` → `main`
- URL: https://github.com/noho/dayu-agent-r/pull/62
- Review date: 2026-05-19
- Included scope: 全部 PR diff（~34k 行），覆盖 host public contract surface、compactor async 执行、dispatch/engine_ingest async boundary、runtime lane refresh cancellation、AGENTS/CLAUDE.md 约束更新、README/docs、测试
- Excluded scope: 无
- Parallel review coverage: 5 个 subagent 分别覆盖 host public contract surface、compactor subsystem、dispatch/engine_ingest async boundary、runtime lane + test coverage、security/docs/constraints
- CI/checks: 无 checks reported（branch 未配置 CI）

## Findings

### 1-未修复-中-HostHandle 兼容别名违反项目禁止规则

- **入口/函数**: `dayu/host/api.py:2798` — `HostHandle: TypeAlias = Host`
- **文件(行号)**: `dayu/host/api.py:2798`；`dayu/host/__init__.py:43,138`
- **输入场景**: 任何 `from dayu.host import HostHandle` 或 `from dayu.host.api import HostHandle`
- **实际分支**: `HostHandle` 被定义为 `Host` 的 TypeAlias，并导出到 `api.py.__all__` 和 `__init__.py.__all__`
- **预期行为**: 按 CLAUDE.md 编码硬约束："禁止兼容性 re-export：仅为保持旧导入路径而转发符号"。contract freeze 不应携带兼容别名。
- **实际行为**: `HostHandle` 仅指向 `Host`，不增加任何语义，是纯粹的兼容转发。
- **直接证据**: `api.py:2798` — `HostHandle: TypeAlias = Host`；`__init__.py:138` — `"HostHandle"` in `__all__`
- **影响**: contract freeze 后调用方可继续依赖旧名 `HostHandle`，导致新旧名称并存，违反"禁止新旧术语并存"约束。
- **建议改法和验证点**: 删除 `HostHandle` TypeAlias 及其 `__all__` 条目；将所有 `HostHandle` 引用改为 `Host`；运行 `test_package_exports.py` 验证。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-中-api.py.\_\_all\_\_ 仍导出 6 个内部类型

- **入口/函数**: `dayu/host/api.py:2801-2876` — `__all__` 列表
- **文件(行号)**: `dayu/host/api.py:2830-2831,2836-2837,2869` — `HostCommandFacet`, `HostCommandHandleOptions`, `HostEventStream`, `HostEventView`, `HostLocalExecutionOptions`, `StartRunRequest`
- **输入场景**: `from dayu.host.api import HostCommandFacet` 等——任何模块可绕过 `__init__.py` 收口直接从 `api.py` 导入内部类型
- **实际分支**: 这 6 个类型已从 `__init__.py.__all__` 正确移除，但仍在 `api.py.__all__` 中
- **预期行为**: 模块 docstring 声明"低层测试如需 legacy command / stream 类型，应显式导入内部模块路径"。若这些类型不属于公共契约，不应出现在 `api.py.__all__`。
- **实际行为**: `api.py.__all__` 仍公开声明这些内部类型，等效于公共契约的一部分。
- **直接证据**: `api.py:2830` — `"HostCommandFacet"`；`api.py:2831` — `"HostCommandHandleOptions"`；`api.py:2836` — `"HostEventStream"`；`api.py:2837` — `"HostEventView"`；`api.py:2833` — `"HostLocalExecutionOptions"`；`api.py:2869` — `"StartRunRequest"`
- **影响**: contract freeze 后，内部类型仍可通过 `api.py` 的 `__all__` 被外部依赖，造成 contract drift。
- **建议改法和验证点**: 从 `api.py.__all__` 移除这 6 个条目；保留类型定义和内部模块路径导入；运行 `test_package_exports.py` 和 `test_import_boundary.py` 验证。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-中-HostInput 死导出

- **入口/函数**: `dayu/host/__init__.py:44,139` — `HostInput` 在包级 `__all__` 中
- **文件(行号)**: `dayu/host/__init__.py:44,139`；`dayu/host/api.py:1342`（类定义）；`dayu/host/api.py:2840`（`api.py.__all__`）
- **输入场景**: `from dayu.host import HostInput`
- **实际分支**: `SubmitFollowupRequest` 已改用显式 `system_prompt`/`user_prompt`/`tool_names` 字段，不再使用 `HostInput`。`StartRunRequest`（仍用 `HostInput`）已从 `__init__.py.__all__` 移除。`HostInput` 仅在 `admission.py`/`command.py` 内部使用。
- **预期行为**: public contract 中不应导出无公共消费者的内部类型。
- **实际行为**: `HostInput` 仍在 `__init__.py.__all__` 和 `api.py.__all__` 中导出。
- **直接证据**: `__init__.py:139` — `"HostInput"` in `__all__`；`api.py:2840` — `"HostInput"` in `__all__`
- **影响**: 调用方可依赖一个无公共语义的内部 envelope 类型，增加 contract 表面负担。
- **建议改法和验证点**: 从 `__init__.py.__all__` 和 `api.py.__all__` 移除 `HostInput`；保留类定义供内部使用；运行 `test_package_exports.py` 验证。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 4-未修复-低-read_api.\_\_all\_\_ 残留 stream_run_events

- **入口/函数**: `dayu/host/read_api.py:722` — `__all__ = ["get_run", "get_session", "stream_run_events"]`
- **文件(行号)**: `dayu/host/read_api.py:722`
- **输入场景**: `from dayu.host.read_api import stream_run_events`
- **实际分支**: `stream_run_events` 已从 `__init__.py` 移除，新 contract 使用 `Host.watch_session_events`
- **预期行为**: 旧 API 在 contract freeze 后应从模块 `__all__` 移除。
- **实际行为**: `stream_run_events` 仍在 `read_api.__all__` 中。
- **直接证据**: `read_api.py:722` — `"stream_run_events"` in `__all__`
- **影响**: 低——内部模块路径已可直接导入，`__all__` 不影响功能，但违反 contract freeze 精神。
- **建议改法和验证点**: 从 `read_api.__all__` 移除 `stream_run_events`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 5-未修复-低-\_\_init__.py docstring 残留 "Phase 4" 引用

- **入口/函数**: `dayu/host/__init__.py:5`
- **文件(行号)**: `dayu/host/__init__.py:5`
- **输入场景**: 阅读模块文档
- **实际分支**: docstring 包含 "Phase 4 已实现的 Session / Run public facade"
- **预期行为**: contract freeze 后 docstring 应描述当前状态，不引用过程性阶段标记。
- **实际行为**: "Phase 4" 是过程产物，不应出现在稳定文档中。
- **直接证据**: `__init__.py:5` — `"Phase 4 已实现的 Session / Run public facade"`
- **影响**: 低——仅影响文档准确性。
- **建议改法和验证点**: 将 "Phase 4 已实现的" 删除，改为描述性文字。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 6-未设计-中-_NeverCancelledToken 禁用 compactor 协作取消

- **入口/函数**: `dayu/host/llm_compaction.py:74-99` — `_NeverCancelledToken` 类；`llm_compaction.py:205` — 传入 `AgentRunRequest`
- **文件(行号)**: `dayu/host/llm_compaction.py:74-99,205`
- **输入场景**: Host 发起 compaction LLM 调用
- **实际分支**: compactor 向 Engine 传递 `_NeverCancelledToken()`，Engine 的 `is_cancelled()` 检查永远返回 `False`
- **预期行为**: Host 可通过 token 协作取消正在运行的 compaction（例如 provider 挂起时）。
- **实际行为**: 协作取消路径被禁用，Host 只能通过 asyncio task cancel（`CancelledError`）取消，依赖 Engine 在 `await` 边界正确传播。
- **直接证据**: `llm_compaction.py:77-78` — `def is_cancelled(self) -> bool: return False`；`llm_compaction.py:205` — `cancellation_token=_NeverCancelledToken()`
- **影响**: 若 Engine `run_agent_and_wait` 在长时间 provider 调用期间不 `await`，取消将被延迟。当前实现依赖 asyncio task cancel 而非协作取消。
- **建议改法和验证点**: 将 Host 自身的 `CancellationToken` 传递给 Engine request 而非 `_NeverCancelledToken`；或在 docstring 中明确记录此设计决策的理由和边界条件。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 7-未修复-低-drain_loop 异常无 backoff

- **入口/函数**: `dayu/host/dispatch.py:1570-1577` — `_drain_loop` 的 `except Exception`
- **文件(行号)**: `dayu/host/dispatch.py:1570-1577`
- **输入场景**: `drain_once` 抛出持续性异常（如 durable store 配置错误）
- **实际分支**: `except Exception` 记录 warning 后立即重入 `while not self._closed` 循环
- **预期行为**: 持续性失败应有 backoff，防止 log/CPU 饱和。
- **实际行为**: 无 sleep，持续性失败形成紧循环。
- **直接证据**: `dispatch.py:1570-1577` — `except Exception as exc: _LOGGER.warning(...)` 后无 `asyncio.sleep`
- **影响**: 若 durable store 持续不可用，循环将以 CPU 密集方式持续重试并产生大量日志。
- **建议改法和验证点**: 在 `except Exception` 分支添加 `await asyncio.sleep(1.0)` 或指数 backoff。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 8-未修复-低-lane.py bare raise 应显式指定异常

- **入口/函数**: `dayu/runtime/lane.py:679` — bare `raise`
- **文件(行号)**: `dayu/runtime/lane.py:679`
- **输入场景**: outer scope 取消后 refresh task 成功完成
- **实际分支**: `token.expires_at = expires_at` 后 bare `raise` 重新抛出捕获的 `CancelledError`
- **预期行为**: 显式 `raise cancelled` 更安全、更清晰，与同函数内 line 668/677 一致。
- **实际行为**: bare `raise` 依赖嵌套 `try/except` 的异常上下文保持活跃。
- **直接证据**: `lane.py:679` — `raise`（对比 line 668 `raise cancelled`）
- **影响**: 若未来在 line 678-679 之间添加代码，异常上下文可能偏移。
- **建议改法和验证点**: 将 bare `raise` 改为 `raise cancelled`，与 line 668/677 保持一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 9-未修复-中-smoke 测试缺 API key 时静默 skip

- **入口/函数**: `tests/host/test_public_compact_smoke.py`、`tests/host/test_public_real_runner_matrix_smoke.py`
- **文件(行号)**: 共 5 个测试方法
- **输入场景**: CI 环境无 LLM provider API key
- **实际分支**: `pytest.skip("missing API key")` — 测试静默跳过
- **预期行为**: CI 无 key 时应有确定性 smoke 测试覆盖核心路径，provider-dependent 测试用独立 marker 管理。
- **实际行为**: 15 个新增测试中 5 个在无 key 时完全 skip，CI 零信号。
- **直接证据**: `test_public_compact_smoke.py` 和 `test_public_real_runner_matrix_smoke.py` 中的 `@pytest.mark.skipif` 或 `pytest.skip()` 调用
- **影响**: CI 无 API key 配置时，compaction 和 real runner 的核心路径无测试覆盖。
- **建议改法和验证点**: 将确定性 smoke（mock worker）与 provider-dependent smoke 分离；确定性部分始终运行。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 10-未修复-低-test_public_lifecycle_smoke 固定轮询可能 flaky

- **入口/函数**: `tests/host/test_public_lifecycle_smoke.py:226` — `_wait_for_run_status`
- **文件(行号)**: `tests/host/test_public_lifecycle_smoke.py:226`
- **输入场景**: CI 高负载时
- **实际分支**: 100 次迭代 × 10ms = 1 秒超时
- **预期行为**: 使用 `asyncio.wait_for` 或指数 backoff。
- **实际行为**: 固定轮询可能在 CI 高负载时超时 flaky。
- **直接证据**: `_wait_for_run_status` 函数中硬编码 100 次循环
- **影响**: CI 偶发 flake。
- **建议改法和验证点**: 改用 `asyncio.wait_for` 配合适当 timeout。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- `_NeverCancelledToken` 是有意设计（避免 compaction 被意外取消干扰 Engine 状态机），还是遗漏了 Host token 的传递？需要与 PR author 确认设计意图。

## Residual Risk

- `api.py.__all__` 与 `__init__.py.__all__` 的不一致意味着 contract freeze 不完整——内部类型仍可通过 `api.py` 路径被外部依赖。
- smoke 测试在无 API key 的 CI 环境中覆盖不足。
- `_drain_loop` 无 backoff 在 durable store 持续故障时可能导致日志风暴。
- `_NeverCancelledToken` 在 provider 挂起场景下的取消延迟风险。

## 结论

**FAIL**

Blocker findings（按项目编码硬约束必须修复后方可 merge）：

1. **Finding #1 — `HostHandle` 兼容别名**：违反"禁止兼容性 re-export"硬约束。必须删除 `HostHandle: TypeAlias = Host` 及其 `__all__` 条目。
2. **Finding #2 — `api.py.__all__` 导出内部类型**：contract freeze 不完整。6 个内部类型仍在 `api.py.__all__` 中，可被外部绕过 `__init__.py` 收口直接导入。
3. **Finding #3 — `HostInput` 死导出**：无公共消费者的内部类型仍在包级 `__all__` 中，增加 contract 表面负担。

其余 findings（#4-#10）为建议性改进，不阻塞 merge 但应在 freeze 前清理。
