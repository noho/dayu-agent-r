# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `8515364a`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-aggregate-deepreview-mimo.md`
- Included scope: P3-K aggregate changes across S1 (`f0d4c76a`), S2 (`6e8b786e`), S3 (`2f69a5d1`), plus untracked aggregate validation artifact (`docs/reviews/wu-semantic-ownership-01-p3-k-aggregate-validation.md`)
- Excluded scope: `AGENTS.md`, `CLAUDE.md`, `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
- Parallel review coverage: 无；三片 slice 由独立 subagent 并行走读后由主 reviewer 整合复核

## Findings

未发现实质性问题。

## Validation Notes

### S1 — Owner-Level Contract Assertions

三处精确字段集断言改为子集断言（`<=`），与计划完成信号一致（"no exact ordered field tuple remains"）：

| 文件 | 变更方向 |
|---|---|
| `tests/contracts/test_tool_result_envelope.py` | `==` → `<=`；`isdisjoint(forbidden)` 保留不变 |
| `tests/host/test_memory_projection.py` (policy) | `tuple ==` → `frozenset <=`；新增 JSON 投影 + digest 灵敏度断言 |
| `tests/host/test_memory_projection.py` (snapshot) | `tuple ==` → `frozenset <=`；新增空快照字段值 + JSON round-trip 断言 |
| `tests/host/test_run_input_builder.py` | 内联断言抽取为 `_assert_resume_guidance_semantics` helper；第 2/3 个测试从弱断言升级为完整语义断言 |

子集断言不再阻止生产 dataclass 意外增加额外字段，但禁止字段集断言（`isdisjoint(forbidden)` 阻止 `await_spec`/`await`/`awaiting` 泄漏）仍完整覆盖计划识别的特定失败模式。新增的行为断言（JSON round-trip、digest 灵敏度、resume 指导内部泄漏否定）对真实回归的保护强度高于精确字段集固定。

### S2 — Durable Diagnostic Helper Boundary

`recovery_support.py` 中 `projection_checkpoint_sequence()` 从 raw SQL 迁移至生产 owner helper `read_projection_checkpoint()`。保留的 5 个 raw SQL helper 均为 fault-injection-only（`force_owner_pid_missing_and_heartbeat_stale`、`force_memory_projection_lag`）或 diagnostic-only（`event_type_count`、`attempt_count_for_run`、`current_attempt_id_for_run`），全部有显式 docstring 标注。未引入仅服务于测试的新生产 helper。

### S3 — Protocol-Faithful Test Double Consolidation

迁移完整性确认：

| 检查项 | 结果 |
|---|---|
| 旧 `FakeCancellationToken` 从 `_fakes.py` 删除 | 干净 |
| 旧 `_Token` 从 `test_agent_phase2.py` 删除 | 干净 |
| 旧 `_Token` 从 `test_agent_phase3_tool_call.py` 删除 | 干净 |
| 旧 `_FakeCancellationToken` 从 `test_fins_direct.py` 删除 | 干净 |
| 残留 `StubCancellationToken` 引用 | 无 |
| 残留 `.trigger()` 调用 | 无 |
| `ControllableCancellationToken` 唯一 canonical test double | 是 |
| 合约测试验证协议保真度 | 是（`test_compaction_contract.py:45`） |

`ControllableCancellationToken` 设计：默认 open、`request_cancel(reason)` 幂等、UTC-aware `datetime.now(UTC)`、只暴露 `CancellationToken` 观察协议。

### 聚合验证状态

- 测试：S1 166 passed；smoke/recovery/admission 27 passed + 1 skipped；OpenAI runner/Engine Agent 380 passed；compaction/ingest/service 193 passed + 3 warnings（已知 `edgar` 弃用警告）
- pyright：0 errors, 0 warnings, 0 informations
- `git diff --check`：pass
- 当前 HEAD 验证：180 passed（contract + memory projection + run input builder + compaction contract），pyright 0 errors

### 残差风险分类确认

| 残差 | 分类 | 理由 |
|---|---|---|
| S2 stress 失败（scheduler cleanup / runner-call manifest payload） | 非阻塞 | 路径在 S2 helper 语义之外 |
| `tests/runtime/test_lane.py` 私有 `_FakeCancellationToken` | 非阻塞 | 在 P3-K S3 已批准文件范围之外；方法名为 `cancel()` 而非 `request_cancel()`，不继承 `CancellationToken`，与 canonical helper 无冲突 |
| `tests/host/test_toolruntime_duplicate_governance.py` 本地 `datetime.now()` | 非阻塞 | 在 P3-K S3 已批准迁移范围之外 |
| 全量 `tests/` 未在聚合验证中重跑 | 非阻塞 | 聚合验证覆盖了所有受影响子集 |

### 控制文档一致性

`issues-implementation-control.md` 第 193-196 行记录了 P3-K 三个 slice 的接受状态、commit hash 和 gate 状态，与实际 commit 历史一致。所有 slice 级 code review findings 已关闭。聚合验证 artifact 与控制文档状态一致。

## Open Questions

无。

## Residual Risk

- `tests/runtime/test_lane.py` 的 `_FakeCancellationToken` 使用 `cancel()` 方法名（非 `request_cancel()`），未来若 `CancellationToken` 协议增加 `cancel()` 别名可能产生语义冲突。当前不在 P3-K 范围内，可在后续治理轮次中处理。
- `tests/host/test_toolruntime_duplicate_governance.py:133` 的 naive `datetime.now()` 不影响 P3-K 目标，但若该文件后续扩展取消相关测试应迁移至 `datetime.now(UTC)`。
- 全量 `tests/` 未在聚合验证中重跑。已覆盖子集 766+ passed，未覆盖区域为不涉及 P3-K 变更的独立测试模块。

## PASS/FAIL

**PASS**。P3-K 三个 slice 的聚合变更符合计划意图，无实质性缺陷。所有 slice 级 findings 已关闭，聚合验证通过，控制文档一致。
