# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Stop Condition Controller Adjudication

## Scope

- Gate: `implementation-slice-3`
- Base: accepted Slice 2 commit `5ac328f0`
- AgentCodex stop artifact: `docs/reviews/wu-host-session-event-delivery-01-slice3-stop-scope-codex.md`
- Accepted plan: `docs/host/wu-host-session-event-delivery-01-plan.md` S3

Controller只裁决 scope/gate，不接手实现或 plan 修改。当前 partial S3 workspace changes 全部保留，不覆盖、不提交，也不派发 code review。

## Direct evidence

S3 将 terminal post-commit port 改为 production constructors 的 required 显式依赖；这是 accepted plan item 9/10 的核心 fail-fast contract。完整 pyright 当前报告 `9 errors`：

- `tests/host/test_admission_multiprocess.py` 4 个旧字段断言错误，文件已在 S3 allowlist。
- `tests/host/test_phase7_waiting_integration.py` 1 个 required factory 参数错误，文件已在 S3 allowlist。
- `tests/host/test_projection_read_model.py` 2 个 required port 参数错误，文件不在 S3 allowlist。
- `tests/host/test_public_host_admin.py` 2 个 required port 参数错误，文件不在 S3 allowlist。

全测试 constructor callsite scan 未发现第三个必须新增的未授权 caller。两份漏列文件都直接构造 `HostCommandHandle` 与 `create_host_admission_service`，没有经过已负责 standalone private endpoint 装配的 `create_host_command_handle`，因此必须在各自 test composition root 显式提供同一个 no-local-delivery final endpoint。

## Motivation and owner adjudication

Decision: `stop-confirmed; return-to-plan-amendment`。

动机成立且由完整 pyright 与 qualified callsite 直接证据证明。正确 owner 仍是 composition root：

- 不得把 port 改回 optional/default/fallback；这会隐藏遗漏装配并违反 item 9/10。
- 不得在 `HostCommandHandle`、admission producer或下游 watcher加入兼容分支。
- 不得让 Controller 或 AgentCodex未经 plan review直接修改漏列测试。
- partial S3 implementation保留在工作树；plan amendment通过后只做机械 caller propagation并恢复同一 implementation slice。

## Minimal plan amendment

只允许给 S3 Allowed tests 增加：

- `tests/host/test_projection_read_model.py`
- `tests/host/test_public_host_admin.py`

授权内容只限：在现有 direct test composition root 创建 test-private、显式 no-local-delivery terminal endpoint，并把同一实例传给 `create_host_admission_service` 与 `HostCommandHandle`。不得改变 production constructor、terminal flags/dataflow、测试业务场景或断言语义，不得引入 optional/default/fallback port。

补充验证必须包括：

1. 两个新增 allowlist 文件各自通过。
2. `tests/host/test_command_handle.py` 的 standalone exact-notice runtime fake通过。
3. 完整 pyright 与全测试 constructor callsite scan归零且无第三个漏列 caller。
4. 原 S3 allowlist内其余5个类型错误完成 owner-contract迁移后，恢复全部 S3 validation。

## Gate decision

Decision: `return-to-plan-amendment`。

- Blocking open question: `None`；缺失 scope与最小修改均已由直接证据确定。
- Next owner: AgentCodex，只修改 accepted plan与 plan-fix artifact，不修改 production/tests/control doc。
- Next review gate: AgentMiMo 与 AgentDS 独立并行使用 `$planreview` 审查该最小 amendment；任一路 material finding均由 Controller逐项裁决。
- 未通过双路 plan re-review与 Controller accepted commit前，不恢复 Slice 3 implementation。
