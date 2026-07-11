# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `0ebea2c1`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s3-code-review-mimo.md`
- Included scope:
  - `tests/host/fake_cancellation.py`
  - `tests/engine/runners/openai/_fakes.py`
  - `tests/engine/runners/openai/test_cancellation_boundaries.py`
  - `tests/engine/runners/openai/test_cancellation_no_done_event.py`
  - `tests/engine/runners/openai/test_close_releases_resources.py`
  - `tests/engine/runners/openai/test_http_error_event.py`
  - `tests/engine/runners/openai/test_http_unknown_status_runner.py`
  - `tests/engine/runners/openai/test_protocol_surface.py`
  - `tests/engine/runners/openai/test_request_identity.py`
  - `tests/engine/runners/openai/test_response_cleanup_race.py`
  - `tests/engine/runners/openai/test_retry_backoff.py`
  - `tests/engine/runners/openai/test_runner_b3_extra.py`
  - `tests/engine/runners/openai/test_runner_diagnostics.py`
  - `tests/engine/runners/openai/test_stream_idle.py`
  - `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
  - `tests/engine/test_agent_phase2.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
  - `tests/host/test_compact_artifact_store.py`
  - `tests/host/test_compaction_contract.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_llm_compaction.py`
  - `tests/service/test_fins_direct.py`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s3-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s3-controller-validation.md`
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`
- Parallel review coverage: 无

## Review Focus Verification

### 1. ControllableCancellationToken implements CancellationToken and starts open by construction

**结论: PASS。**

- `tests/host/fake_cancellation.py:14` — `class ControllableCancellationToken(CancellationToken)` 正确声明继承 `CancellationToken` Protocol。
- `dayu/contracts/cancellation.py:21` — `CancellationToken` 是 `@runtime_checkable Protocol`，声明 `is_cancelled()`, `cancel_reason()`, `requested_at()` 三个观察方法。
- `tests/host/fake_cancellation.py:21-28` — `__init__(self)` 无参构造，`_reason = None`, `_requested_at = None`，构造后 `is_cancelled()` 返回 `False`。
- 运行时 `isinstance(token, CancellationToken)` 验证通过。

### 2. request_cancel is the only external mutation, idempotent, preserves first reason/time, UTC-aware

**结论: PASS。**

- `tests/host/fake_cancellation.py:54` — `request_cancel(self, reason: str = "test_cancelled")` 是唯一的外部 mutation 方法。
- `tests/host/fake_cancellation.py:61` — `if self._reason is None:` 守卫确保仅首次调用写入 reason 和 timestamp，重复调用幂等吸收。
- `tests/host/fake_cancellation.py:63` — `datetime.now(UTC)` 产生 UTC-aware timestamp。
- 运行时验证：首次 `request_cancel("first")` 后再次 `request_cancel("second")`，reason 保持 `"first"`，`requested_at()` 不变且 `tzinfo is UTC`。

### 3. No constructor-as-cancelled semantics, no external .trigger() call site

**结论: PASS。**

- `__init__` 签名从 `__init__(self, reason: str | None = None)` 改为 `__init__(self)`，消除了构造时即取消的能力。
- `rg -n "\.trigger\(" tests/engine tests/host tests/service` — 无匹配结果。所有 `.trigger()` 调用已迁移到 `request_cancel()`。

### 4. OpenAI _fakes.py no longer owns a local cancellation fake or naive timestamp

**结论: PASS。**

- `tests/engine/runners/openai/_fakes.py` diff 显示删除了 `FakeCancellationToken` 类定义（原 247-288 行）和 `datetime` import。
- `__all__` 中移除了 `"FakeCancellationToken"`。
- OpenAI runner 测试现在统一 `from tests.host.fake_cancellation import ControllableCancellationToken`。

### 5. Engine/Host/Service migrated to canonical helper without compatibility re-export/facade

**结论: PASS。**

- `tests/host/fake_cancellation.py` 的 `__all__` 只导出 `ControllableCancellationToken`，无 `StubCancellationToken` 兼容性 re-export。
- `rg -n "StubCancellationToken" tests/` — 仅在 `tests/runtime/test_lane.py` 中出现一个同名局部类 `_FakeCancellationToken`（S3 scope 外），S3 范围内无残留。
- 无 wrapper/facade/shim 代码。

### 6. Service direct tests no longer define an independent cancellable fake

**结论: PASS。**

- `tests/service/test_fins_direct.py` diff 删除了 `_FakeCancellationToken` 类定义（原 43-73 行），替换为 `from tests.host.fake_cancellation import ControllableCancellationToken`。
- 测试中使用 `ControllableCancellationToken()` 构造未取消 token，不再需要独立 fake。

### 7. Compaction/memory helper ownership not drifted

**结论: PASS。**

- `tests/host/test_compaction_contract.py` 新增了 `test_controllable_cancellation_token_contract_is_protocol_faithful` 测试，验证 token 协议语义，不涉及 compaction 或 memory schema。
- `ConversationMemorySnapshotVNext(` 构造仅出现在 `tests/host/memory_snapshot_factories.py`（已有 owner）和 `tests/host/test_import_boundary.py`（scanner fixture 文本），无新增业务测试直接构造。
- 无 production 行为/schema 变更。

### 8. Focused validation and README decision

**结论: PASS。**

- 实现 artifact 记录了完整的 focused test matrices 运行结果：24 + 174 + 19 + 109 = 326 passed。
- pyright: 0 errors, 0 warnings, 0 informations。
- `git diff --check`: pass。
- README 决策合理：`tests/README.md` 已记录 helper 位置和职责，S3 仅改类名和删除重复 fake，未引入新 helper 层。

### 9. Scope drift, missing tests, type/docstring issues, residual risk

**结论: PASS with note。**

- 无 scope drift：所有变更文件均在 S3 定义范围内。
- 无 production 代码变更：diff 确认 `dayu/` 目录无修改。
- pyright clean：无类型错误。
- 新增 `test_controllable_cancellation_token_contract_is_protocol_faithful` 覆盖了核心协议语义。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `tests/runtime/test_lane.py:66` 中存在独立的 `_FakeCancellationToken` 类（私有、模块局部），不在 S3 scope 内。若后续 P3-K 计划覆盖 `tests/runtime/`，应一并迁移。
- 实现 artifact 标注的第三方 `edgar` deprecation warnings 与 S3 无关，不构成 blocker。
- S3 focused matrices 覆盖了所有变更文件的直接测试，但未运行完整 `tests/engine/`、`tests/host/`、`tests/service/` 套件。已有 573 个测试通过，覆盖充分。

## Validation Notes

独立验证结果：

- 全 S3 scope 测试：`573 passed, 3 warnings` (warnings 为第三方 edgar deprecation)
- pyright: `0 errors, 0 warnings, 0 informations`
- 运行时协议验证：`isinstance(token, CancellationToken) == True`
- 幂等性验证：重复 `request_cancel()` 保持首次 reason 和 timestamp
- UTC-aware 验证：`requested_at().tzinfo is UTC`

## PASS/FAIL

**PASS。**
