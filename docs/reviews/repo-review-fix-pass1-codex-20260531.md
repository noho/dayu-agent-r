# PR 99 full-repo review fix pass1 - AgentCodex

## Scope

- Branch: `feat/host-purge-audit-reconciliation`
- Role: implementation/fix only
- 本轮只处理证据直接、无需公共契约或 schema 设计变更的 accepted findings。
- 未处理非目标项：`_AsyncAgent` 大拆分、`LaneClock` 跨进程时钟、`RunnerHTTPError` 新事件、ToolRuntime 大结果 fallback 治理、duplicate governance durable 化、purge tombstone cleanup、`_validation` 与 schema 空白规则选择。

## Finding Status

### 1. RuntimeFileLock.release 失败状态

- Status: `deferred-with-owner`
- 改动文件: 无
- Owner 建议: runtime/filelock owner 或 gate controller 单独开设计切片
- Root-cause assessment:
  - `RuntimeFileLock` 相对第三方 `FileLock` 增加的有效语义是：统一 `RuntimeFileLockError` / `RuntimeFileLockTimeoutError` 异常边界、parent directory 创建策略、timeout 参数校验、lock path 基础校验、release 后 best-effort 恢复 lock marker 文件、同一 wrapper 实例的 `_active_token` 重入防御。
  - 生产调用面只有 `dayu.host.audit` 与 `dayu.host.tool_trace` 通过 `file_lock(...)` 做 JSONL/trace 文件写入互斥，`dayu.host.command` 只捕获 `RuntimeFileLockError`。未发现生产调用方真实依赖 `RuntimeFileLockToken.released` 状态机。
  - 直接使用第三方 `FileLock` 可以消除 wrapper 自己复制生命周期状态机带来的 bug，但会改变当前 runtime 公共异常边界与 import boundary 测试；这不是本轮“低风险局部修复”。
  - 若保留封装，建议收缩为只负责 parent directory、统一异常与审计边界，不再复制 FileLock acquire/release 生命周期状态；删除或隐藏 token `released` 状态。
- 剩余风险: 当前 release 失败后误标记 released 的已知 bug 仍存在，等待单独设计切片处理。

### 2. schema v15 active Run CHECK 测试数据

- Status: `fixed`
- 改动文件:
  - `tests/host/test_wait_record_state.py`
  - `tests/host/test_public_cancel_session_runs.py`
- 修复内容: 测试 helper seed / status update active Run 时补充 `started_event_id` / `started_event_sequence`，不改 schema，不加兼容层。

### 3. WAITING Run 的 wait records 已 RESOLVED 后仍应可 cancel

- Status: `fixed`
- 改动文件:
  - `dayu/host/durable/run_transition.py`
  - `tests/host/test_wait_cancel_late_result.py`
- 修复内容: `cancel_waiting_run_in_transaction` 不再要求 active wait records 非空；active waits 为空时跳过 wait record cancel，只取消 WAITING Run。补充 targeted public cancel test。

### 4. cancel_queued_run_row / cancel_running_run_row terminal guard

- Status: `fixed`
- 改动文件:
  - `dayu/host/durable/state.py`
  - `tests/host/test_run_attempt_transitions.py`
- 修复内容: 两个 Run cancel CAS 的 SQL `WHERE` 增加 `terminal_event_id IS NULL`、`terminal_event_sequence IS NULL`、`terminal_at IS NULL` 防御性守卫。补充 targeted tests。

### 5. Accept barrier payload_ref descriptor digest 校验

- Status: `fixed`
- 改动文件:
  - `dayu/host/tool_runtime.py`
  - `tests/host/test_toolruntime_accept_barrier.py`
- 修复内容: payload descriptor 存在性校验同时要求 descriptor digest 与 candidate `payload_ref.payload_digest` 一致。补充 digest mismatch targeted test。

### 6. ToolExecutor 内部 CancelledError warning

- Status: `fixed`
- 改动文件:
  - `dayu/engine/agent.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
- 修复内容: `_call_tool_executor` 在 executor 抛出 `CancelledError` 且 run-level cancellation token 未取消时写 warning 日志。现有 cancelled executor 路径测试补充日志断言。

### 7. opaque_ref.py 覆盖率低于 80%

- Status: `fixed`
- 改动文件:
  - `tests/host/test_opaque_ref.py`
- 修复内容: 只补边界测试，不改生产语义。覆盖 TypeError、空文本、缺 kind、空 ref id、非法 kind 和公开 kind 集合。
- 覆盖率验证: `dayu/host/opaque_ref.py` 单文件 coverage 为 `100%`。

### 8. config_loader 与 assembly fallback_mode 合法值重复

- Status: `fixed`
- 改动文件:
  - `dayu/runtime/_agent_policy_constants.py`
  - `dayu/runtime/config_loader.py`
  - `dayu/runtime/scene_prepare.py`
  - `dayu/runtime/assembly.py`
- 修复内容: 新增 runtime 层中立私有常量模块作为 fallback mode 闭集真源；`config_loader`、`scene_prepare`、`assembly` 复用该真源，不引入反向依赖。

## README

- 检查了 `tests/README.md`。本轮只是在既有测试分层内新增/更新用例，不改变测试层级、运行方式或维护规则，因此未修改 README。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_wait_record_state.py tests/host/test_public_cancel_session_runs.py tests/host/test_wait_cancel_late_result.py tests/host/test_run_attempt_transitions.py::test_cancel_queued_run_row_requires_empty_terminal_refs tests/host/test_run_attempt_transitions.py::test_cancel_running_run_row_requires_empty_terminal_refs tests/host/test_toolruntime_accept_barrier.py::test_accept_rejects_payload_descriptor_digest_mismatch tests/engine/test_agent_phase3_tool_call.py::test_duplicate_and_executor_exception_paths tests/host/test_opaque_ref.py tests/runtime/test_assembly_helpers.py tests/runtime/test_config_loader.py::test_agent_fallback_mode_is_closed_enum tests/runtime/test_scene_prepare.py::test_agent_policy_fallback_mode_is_closed_enum`
  - Result: `50 passed`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests`
  - Result: `1796 passed, 1 skipped`
- `source .venv/bin/activate && pytest tests/host/test_opaque_ref.py --cov=dayu.host.opaque_ref --cov-report=term-missing`
  - Result: `10 passed`, `dayu/host/opaque_ref.py 100%`

## Residual Risk

- `RuntimeFileLock.release` 的 release 失败状态 bug 未在本轮修复；原因是补充总控指令要求先评估是否应收缩或替换 wrapper，单行状态赋值修复会继续保留问题根源。
- 本轮未处理需要公共契约、schema 或 durable governance 设计的 findings，需由对应控制文档或 owner 后续切片处理。
- `cancel_queued_run_row` / `cancel_running_run_row` 的 terminal guard 属防御性 SQL guard；正常 schema 已阻止 active Run 持有 terminal refs，测试通过 `PRAGMA ignore_check_constraints` 构造异常行验证 CAS 防线。
