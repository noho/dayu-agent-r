# WU-WAIT-01 Slice 1 Fix Artifact

## Scope

- Work unit: WU-WAIT-01 / issue-89
- Gate: Slice 1 code review fix
- Fix owner: AgentCodex
- Accepted findings:
  - S1-CR-F01: callback digest 与 resolve_wait digest 的 outcome JSON 投影重复。
  - S1-CR-F02: callback stale deadline/expires 解析未复用 Host durable timestamp helper。
  - S1-CR-F03: covered by S1-CR-F02。

## First-principles Judgment

两个 accepted finding 成立，但都是同源性与边界一致性问题，不是当前正常路径行为错误。

- digest 两套投影当前产出一致；真实风险是未来其中一处漂移，破坏 callback replay/idempotency 判断。
- stale timestamp 正常持久化值由 Host durable helper 写入，旧 parser 也能解析；真实风险是异常持久化边界被宽松 parser 接受，和 Host durable timestamp 真源不一致。

## Changes

- 新增 `dayu/host/durable/wait_resolution_digest.py`，集中维护 wait resolution digest material：
  - `wait_resolution_digest(...)`
  - `resolve_wait_outcome_json(...)`
  - completed / failed / cancelled / lost result JSON 投影 helper
  - outcome kind 常量
- `dayu/host/wait_callback.py`
  - `callback_payload_digest` 改为调用 `wait_resolution_digest(...)`。
  - stale boundary 解析改为直接调用 `parse_utc_timestamp(...)`。
  - 删除本地重复 outcome/result JSON 投影与本地 timestamp parser。
- `dayu/host/waiting.py`
  - `_wait_resolution_digest(...)` 改为调用同一个 `wait_resolution_digest(...)`。
  - late rejection diagnostic digest 的 `outcome` 字段改为调用同一个 `resolve_wait_outcome_json(...)`。
  - wait resolution payload plan 复用共享 result JSON helper，保持事件 payload 形状不变。
- `tests/host/test_wait_callback.py`
  - 新增 completed 与 lost outcome 的 callback digest / resolve_wait digest 对齐测试。
  - 新增非法持久化 deadline 边界映射为 `INVALID_WAIT_STATE` 且不调用 resolver 的测试。

## Behavior / Contract Decision

- 未改变 digest material 字段、字段语义或幂等行为。
- 未改变 durable schema。
- 未暴露新的 Host package root public symbol。
- 未实现 Service/Web route、poller、physical cancel 或 issue-90/issue-92 范围。
- README 不更新：本轮是内部 helper 同源化与异常边界解析收敛，没有新增 public behavior 或 documented contract。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
  - Result: `56 passed in 1.57s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Finding Status

- S1-CR-F01: 已修复。callback digest 与 direct resolve digest 现在调用同一 Host durable helper；测试覆盖 completed 与 lost outcome。
- S1-CR-F02: 已修复。stale boundary 解析复用 `parse_utc_timestamp(...)`；非法固定格式边界映射为 `INVALID_WAIT_STATE`。
- S1-CR-F03: 已修复。移除本地 parser 后不再存在 `Z -> +00:00` 规范化路径。

## Residual Risks

- failed / cancelled outcome 的 digest 对齐未新增专项测试；共享 helper 的同一入口覆盖所有 outcome 分支，现有 resolve_wait 测试继续覆盖 failed/cancelled 行为。分类：covered by current slice through shared implementation and existing tests。
- callback stale 并发 race 仍可能由 resolver 收敛为 `INVALID_WAIT_STATE`，本轮未新增并发测试。分类：tracked by accepted Slice 1 design behavior。

## Artifact Path

- `docs/reviews/wu-wait-01-slice1-fix-codex.md`
