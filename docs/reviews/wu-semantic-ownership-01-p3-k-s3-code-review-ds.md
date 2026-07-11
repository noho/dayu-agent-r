# WU-SEMANTIC-OWNERSHIP-01 P3-K S3 Code Review (DeepReview)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `0ebea2c1`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s3-code-review-ds.md`
- Included scope: S3 Protocol-Faithful Test Double Consolidation — all files listed in the implementation artifact
- Excluded scope: unrelated dirty/untracked files (AGENTS.md, CLAUDE.md, docs/cli_ci.md, docs/cli_ci_oracles.json, docs/cli_ci_scenarios.json, prior code-review artifacts)
- Parallel review coverage: 无（单一 reviewer，全部走读）

## Findings

### 未发现实质性问题

经完整的逐文件走读、diff 比对、source scan 和测试验证，S3 实现严格遵循批准计划的所有要求，未发现 correctness、stability、maintainability 或 semantic ownership 方面的实质性问题。

以下逐项确认每个 review focus：

---

#### 1. ControllableCancellationToken 实现 CancellationToken 且构造即为开放状态

**证据**：

- `tests/host/fake_cancellation.py:14`：`class ControllableCancellationToken(CancellationToken):` — 直接继承自 `dayu.contracts.cancellation.CancellationToken` Protocol。
- `tests/host/fake_cancellation.py:21-28`：`__init__` 设置 `self._reason = None`，`self._requested_at = None`。
- `tests/host/fake_cancellation.py:30-36`：`is_cancelled()` 返回 `self._reason is not None`。
- `tests/host/fake_cancellation.py:38-44`：`cancel_reason()` 返回 `self._reason`。
- `tests/host/fake_cancellation.py:46-52`：`requested_at()` 返回 `self._requested_at`。
- 契约测试 `tests/host/test_compaction_contract.py:35-54`：断言 `is_cancelled() is False`，`cancel_reason() is None`，`requested_at() is None`。

**结论**：PASS。构造即为 open token，所有 CancellationToken 协议方法正确实现。

---

#### 2. request_cancel 是唯一外部 mutation 方法，幂等，保留首次原因/时间，requested_at 为 UTC-aware

**证据**：

- `tests/host/fake_cancellation.py:54-63`：`request_cancel(reason: str = "test_cancelled")` — 检查 `self._reason is None` 后才写入 `self._reason` 和 `self._requested_at = datetime.now(UTC)`。
- 无其他 mutation 方法（`is_cancelled`、`cancel_reason`、`requested_at` 均为只读）。
- 契约测试 `tests/host/test_compaction_contract.py:44-54`：第二次 `request_cancel("second_reason")` 后 `cancel_reason()` 仍为 `"first_reason"`，`requested_at()` 仍等于第一次时间戳。
- 契约测试 `tests/host/test_compaction_contract.py:45-49`：`first_requested_at.tzinfo is UTC`。

**结论**：PASS。幂等、保留首次原因/时间、UTC-aware。

---

#### 3. 无 constructor-as-cancelled 语义，无外部 .trigger(...) 调用

**证据**：

- `tests/host/fake_cancellation.py:21`：`def __init__(self) -> None:` — 无参数，不允许构造时传入 reason。
- `rg -n "\.trigger\(" tests/engine tests/host tests/service` 结果：无匹配。
- `rg -n "FakeCancellationToken|StubCancellationToken" tests/engine tests/host tests/service` 结果：无匹配（仅 `tests/host/fake_cancellation.py:14` 的 canonical helper 定义）。

**结论**：PASS。旧语义和旧调用点均已清除。

---

#### 4. OpenAI _fakes.py 不再拥有本地 cancellation fake 或 naive timestamp 语义

**证据**：

- `git diff` 确认 `FakeCancellationToken` dataclass（含 `cancelled`、`reason`、`requested` 字段及 `trigger` 方法）已从 `tests/engine/runners/openai/_fakes.py` 完全移除。
- `from datetime import datetime` 已从 `_fakes.py` 移除（该文件不再使用 `datetime`）。
- `__all__` 中已移除 `"FakeCancellationToken"`。
- `rg -n "FakeCancellationToken" tests/engine` 结果：无匹配。
- `rg -n "datetime\.now\(\)" tests/engine/runners/openai` 结果：无匹配。

**结论**：PASS。

---

#### 5. Engine/Host/Service 已迁移到 canonical helper，无兼容性 re-export/facade

**证据**：

- 所有 OpenAI runner 测试文件的 import 均为 `from tests.host.fake_cancellation import ControllableCancellationToken` — 直接导入 canonical helper。
- Host 压缩测试各级 import 均已从 `StubCancellationToken` 替换为 `ControllableCancellationToken`。
- Engine Agent 测试（`test_agent_phase2.py`、`test_agent_phase3_tool_call.py`）已删除本地 `_Token` 类，改为导入 `ControllableCancellationToken`。
- `rg` 扫描确认无 `FakeCancellationToken` 或 `StubCancellationToken` 残留引用。
- 无兼容性 wrapper/re-export 存在。

**结论**：PASS。

---

#### 6. Service 直接测试不再定义独立的 cancellable fake

**证据**：

- `tests/service/test_fins_direct.py` diff 确认：`_FakeCancellationToken` 类（含三个返回固定 `False`/`None` 的方法）已完全移除。
- 测试 `test_download_stream_builds_request_and_yields_progress_result` 及其他测试点使用 `ControllableCancellationToken()` 替代。
- `ControllableCancellationToken()` 默认 open 状态满足原 Service 测试"never-cancelled"的语义需求。

**结论**：PASS。

---

#### 7. 压缩/内存 helper 所有权未漂移

**证据**：

- `tests/host/fake_compaction.py`：未改动（仅 `FakeContextCompactor` 内部使用的 `StubCancellationToken` → `ControllableCancellationToken` 由调用方完成）。
- `tests/host/memory_snapshot_factories.py`：未改动。
- `rg -n "ConversationMemorySnapshotVNext\(" tests/engine tests/host tests/service` 结果：构造仅出现在 `tests/host/memory_snapshot_factories.py`（两处）和 `tests/host/test_import_boundary.py`（scanner fixture 文本，非业务测试构造）。
- 无生产代码 `dayu/` 变动。
- 无新增 production behavior / schema 变更。

**结论**：PASS。所有权边界保持清晰。

---

#### 8. 聚焦验证和 README 决策

**证据**：

- 契约测试 `tests/host/test_compaction_contract.py::test_controllable_cancellation_token_contract_is_protocol_faithful` 覆盖：open 状态、UTC-aware `requested_at`、reason 持久性、幂等性。
- 实现 artifact 记录了 `tests/README.md` 已读，判定无需更新（helper 职责边界未变）。
- 实现 artifact 记录了 README 触发决策：`tests/README.md: no update needed`。

**结论**：PASS。聚焦验证完备，README 决策合理（helper 位置和责任边界未变，仅类名变更）。

---

#### 9. Scope drift、缺失测试、类型/docstring 问题、残余风险

**Scope drift**：无。S3 严格限制在批准的计划文件集合内，未触及生产代码，未扩展压缩/内存 schema 构造。

**缺失测试**：无关键缺失。契约测试覆盖了计划要求的所有 ControllableCancellationToken 行为：
- Open 状态 ✓
- UTC-aware requested_at ✓
- Reason 持久性 ✓
- 幂等 cancellation ✓
- 隐式覆盖：默认 reason `"test_cancelled"`（由 `test_cancellation_boundaries.py` 中 `token.request_cancel()` 无参调用隐式验证）
- 隐式覆盖：`isinstance(token, CancellationToken)` 通过所有测试的 `cancellation_token=` 参数传递和 `@runtime_checkable` 协议隐式验证

**类型/docstring**：无问题。
- `ControllableCancellationToken` 所有方法均有完整中文 docstring。
- 类型标注完整（`str | None`、`datetime | None`、`-> bool` 等）。
- pyright 0 errors, 0 warnings, 0 informations。

**一个轻微的定位意见**（不构成 finding）：契约测试 `test_controllable_cancellation_token_contract_is_protocol_faithful` 放在 `tests/host/test_compaction_contract.py` 中略显 mislocated（该文件主体为 compaction contract 测试）。但这不影响任何实质行为，且该文件按名称本就承担 "contract" 测试职责。建议后续如有合适时机，可考虑抽取为 `tests/host/test_cancellation_token_contract.py`，但当前不需要为此创建 finding。

**CODEOWNERS**：`dayu.contracts.cancellation.CancellationToken` 为取消观察协议 owner；`tests/host/fake_cancellation.py::ControllableCancellationToken` 为测试侧可控 mutation owner。职责清晰，无重叠或冲突。

---

## Open Questions

无。

## Residual Risk

- **低风险 — 片段测试覆盖**：本 review 运行了全部 OpenAI runner 测试（271 passed）、Engine Agent Phase 2/3 测试、Host 压缩测试矩阵和 Service 直接测试（共 288 passed），以及 pyright 全量检查。未运行 `tests/host/test_public_open_host_multiturn_smoke.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_recovery_multiprocess.py` 或 stress 测试，但这些测试位于 S2 scope（durable diagnostic helper boundary），不在 S3 变更文件范围内。S3 对 Host 压缩测试的修改仅限于 import 名称替换，不影响这些测试的语义。
- **低风险 — 第三方依赖警告**：`tests/service/test_fins_direct.py` 存在 3 个 `edgar` 库 deprecation warning，与 S3 取消 helper 迁移无关。

## Validation Notes

| 验证项 | 结果 |
|--------|------|
| `pytest tests/engine/runners/openai/test_cancellation_boundaries.py ... test_response_cleanup_race.py` | 24 passed |
| `pytest tests/host/test_compaction_operation.py ... test_compact_artifact_store.py` | 174 passed |
| `pytest tests/service/test_fins_direct.py` | 19 passed, 3 warnings (edgar) |
| `pytest tests/engine/test_agent_phase2.py test_agent_phase3_tool_call.py` | 109 passed |
| `pytest tests/engine/runners/openai/` (full) | 271 passed |
| `pytest tests/host/test_compaction_contract.py::test_controllable_cancellation_token_contract_is_protocol_faithful` | 1 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `rg "\.trigger\(" tests/engine tests/host tests/service` | 无匹配 |
| `rg "FakeCancellationToken\|StubCancellationToken" tests/engine tests/host tests/service` | 无匹配（仅 canonical 定义） |
| `rg "ConversationMemorySnapshotVNext\(" tests/engine tests/host tests/service` | 仅 factories + scanner fixture |
| `git diff --check` | pass |

## Verdict

**PASS** — S3 实现严格遵循批准计划，所有 review focus 通过。未发现实质性问题。
