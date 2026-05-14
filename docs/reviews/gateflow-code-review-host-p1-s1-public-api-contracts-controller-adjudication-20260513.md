# Host Phase 1 Slice 1 Code Review Controller Adjudication

## Work Gate

code review controller adjudication

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Assigned Slice

Slice 1: `dayu.host` public API typed contracts。

## Reviewed Artifacts

- Implementation artifact: `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`
- AgentMiMo code review: `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-mimo-20260513.md`
- AgentDS code review: `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-ds-20260513.md`
- Approved plan: `docs/host/phase1-public-contract-runtime-plan.md`

## Summary

AgentMiMo 与 AgentDS 均确认 Slice 1 实现无 blocking finding、无 scope violation、无 Engine / Fins / runtime 夹带，验证命令通过。

Controller 裁决：代码主体符合 approved plan。两个 low-severity 测试覆盖观察项应在当前 slice fix gate 补齐；其余观察项不要求代码修改。

## Controller Decisions

### M1 / D1: `CreateSessionRequest.bind_slot=False` 时仍拒绝空字符串 scope / slot_key

- Source: AgentMiMo Finding 1, AgentDS Finding 1。
- Decision: rejected-for-fix。
- Rationale: `scope` / `slot_key` 属于 name-like 字段。即使 `bind_slot=False` 时允许 `None`，拒绝空字符串仍符合 plan 中“id / name / reason 字段拒绝空字符串或纯空白”的通用校验。该行为比最低要求更严格，但不引入 contract drift。
- Required fix: none。

### D2: `_require_graceful_cancel` 在当前单值 `CancelMode` 下不可通过正常枚举路径触发

- Source: AgentDS Finding 2。
- Decision: rejected-for-fix。
- Rationale: Phase 1 明确只允许 `CancelMode.GRACEFUL`。守卫函数存在是为了保持 request constructor 的边界检查位置清晰，不需要为后续 enum 扩展提前引入额外生产代码。
- Required fix: none。

### D3: `CancelRunRequest` / `CancelSessionRunsRequest` mode 校验失败路径未显式覆盖

- Source: AgentDS Finding 3。
- Decision: accepted。
- Rationale: approved plan 要求 validation failure paths 覆盖 cancel mode 第一版只能为 graceful。虽然当前 `CancelMode` 只有一个成员，测试仍可用 `typing.cast(CancelMode, "force")` 或等价方式覆盖 runtime 边界，避免未来 enum 扩展时守卫失效。
- Required fix: 在 `tests/host/test_public_contracts.py` 增加 focused test，覆盖 `CancelRunRequest` 与 `CancelSessionRunsRequest` 传入非 graceful runtime 值时抛 `ValueError`。不得修改生产 API。

### D4: frozen / slots 测试只抽样检查一个 dataclass

- Source: AgentDS Finding 4。
- Decision: accepted。
- Rationale: Slice 1 的公共类型稳定性依赖所有 Host public dataclass 都是 frozen + slots。当前只抽样 `SessionSlotRef`，不能防止后续在同一 slice 文件中新增或修改 dataclass 时漏掉 `frozen=True, slots=True`。
- Required fix: 将 `tests/host/test_public_contracts.py` 的 dataclass frozen / slots 检查改为覆盖所有 `dayu.host` public dataclass，排除 `HostApiError` 与 `HostCommandFacet` 等非 dataclass 类型。不得修改生产 API。

### D5: `RunSnapshot.source_run_id` / `source_run_relation` 一致性校验

- Source: AgentDS Finding 5。
- Decision: accepted-as-positive-observation。
- Rationale: 该校验防止 snapshot 进入不一致状态，符合公共类型契约收敛目标，不需要修改。
- Required fix: none。

## Required Fix Scope

Fix agent 只允许修改：

- `tests/host/test_public_contracts.py`
- `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`
- source review artifacts if updating finding status is practical:
  - `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-ds-20260513.md`
  - `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-mimo-20260513.md`
- fix artifact: `docs/reviews/gateflow-fix-host-p1-s1-public-api-contracts-20260513.md`

Fix agent must not modify `dayu/host/api.py`, `dayu/host/__init__.py`, README files, runtime, Engine, Fins, pyproject, or any future-slice files unless a validation failure proves the test-only fix is impossible.

## Required Validation

- `source .venv/bin/activate && pytest tests/host -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

## Next Gate

Proceed to fix gate for accepted findings D3 and D4 only. After fix, run MiMo + DS code re-review on the accepted findings and the focused diff.

## Artifact Path

`docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-controller-adjudication-20260513.md`
