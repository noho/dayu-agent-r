# WU-CTX-04 Slice 2 allowlist amendment（Controller）

## Gate metadata

- work unit：`WU-CTX-04`
- gate：implementation Slice 2/3
- baseline：accepted Slice 1 commit `eda1d70eb2c2252570807e1fcdb1cd234a5aae7a`
- blocked artifact：`docs/reviews/wu-ctx-04-slice-2-implementation-codex.md`
- decision：`resume-with-two-narrow-amendments`
- architecture / public contract change：None
- blocking open questions after adjudication：None

## Direct evidence

AgentCodex 在 production edit 前完成 caller/allowlist 审计并正确停止，确认 accepted plan
漏列两个必需机械迁移测试：

1. `tests/host/test_public_host_admin.py:41,339,350` 直接 import、type annotate 并
   monkeypatch `StartupRecoveryScanner`。Slice 2 Exact change 6 要求 production recovery
   改为 target-session 语义并删除 `StartupRecovery*` production symbol；不改测试会产生
   import/pyright/pytest failure，保留 alias 则违反无兼容代码约束。
2. `tests/host/test_active_cancel_dispatch.py:1472,1655` 直接构造
   `HostDispatchScheduler` 并调用 pre-start governance。Slice 2 Exact change 4 要求 access
   port 为 mandatory 且 pre-start 持真实 work lease；不改测试会破坏 required full pyright/
   pytest，增加 allow-all/default 则把错误语义写进 production。

Controller 继续沿同一 rename 数据路径审计，另确认：

3. `tests/host/test_terminal_post_commit.py:89-99,128-132` 的静态 producer oracle 直接断言
   `StartupRecoveryScanner.*` qualified names。production 类型重命名后必须同步 oracle；否则
   测试要么失败，要么倒逼 production 保留 stale 名称。

三项都只是被 production owner contract 强制触发的测试迁移，不新增行为、不修改业务断言，
也不提前实现 Slice 3 cancel owner。

## Narrow amendment

在 accepted plan Slice 2 Allowed test/support files 基础上，仅追加：

- `tests/host/test_public_host_admin.py`：只允许把 recovery import/type/monkeypatch 迁移到
  target-session recovery owner；HostAdmin “不得启动 execution/recovery”断言必须保持。
- `tests/host/test_active_cancel_dispatch.py`：只允许 scheduler construction 与直接 pre-start
  helper 注入 explicit fake access port / work lease；不得修改 cancel state machine、expected
  cancel behavior 或实现 Slice 3 production semantics。
- `tests/host/test_terminal_post_commit.py`：只允许同步 recovery owner/method qualified-name
  oracle；不得修改 terminal transition/promotion ownership assertions。

其余 production/config/test/utils allowlist、non-goals、completion signal、validation、README
defer 与禁止项全部保持 accepted plan 不变。若再次发现必需文件不在 allowlist，Agent 仍须停止并
提供同路径直接证据；不得把本 amendment 泛化为任意测试修改授权。

## Why plan/goal is not reopened

本 amendment 不改变目标、语义 owner、public contract、state machine、schema、implementation
strategy 或 slice boundary；它只修正 accepted plan 对既有直接消费者枚举不完整的问题。重新引入
兼容 alias/default 会违反已确认目标，反而不是可接受替代。后续 Slice 2 双路 code review 必须
逐文件核对这三个文件只发生授权的机械迁移。

## Next entry point

恢复 AgentCodex 的 Slice 2 implementation；更新同一 implementation artifact，保留本次 blocked
证据与 scope resolution，完成联合 checkpoint 后再进入 code review。

## Second narrow amendment：proactive tier request owner

恢复实现后的逐阶段验证又发现 accepted plan 漏列一个必需 production owner 与其直接测试：

1. accepted Slice 1 baseline `eda1d70e:dayu/host/compact_pipeline.py` 中
   `build_tier_recovery_request_plans(...)` 为 tier 2 使用
   `root_request_plan.selected_segment`；但设计真源要求 tier 2 同时使用 fallback selected recent
   window 与 section-aware previous-view degrade。默认 frozen semantic budget 为 5 时，新的
   global attempt schedule 首次让 `root -> root repair -> tier 1 -> tier 2 -> tier 3` 在同一
   operation 内真实可达，因此该既有 owner 偏差不再能被旧的 per-tier budget reset 掩盖。
2. `tests/host/test_compact_pipeline.py` 是 `build_tier_recovery_request_plans(...)` 的直接 owner
   contract 测试；现有断言只覆盖 tier 2 previous-view degrade，没有断言它复用 fallback bounded
   selection。只在 `test_dispatch_scheduler.py` 做集成断言会把 pipeline owner contract 留空。

Controller 在 accepted plan Slice 2 allowlist 中仅追加：

- `dayu/host/compact_pipeline.py`：只允许把 tier 2 的 `selected_segment` 改为同一 helper 已构造的
  `bounded_selection`；不得改 normal selection、tier 1/3、reactive pass queue、material schema
  或其它 pipeline 语义。
- `tests/host/test_compact_pipeline.py`：只允许补 tier 2 与 tier 1 共用 fallback bounded selection、
  且不同于 root selection 的直接 owner 断言；不得扩写其它 pipeline 行为。

该 amendment 不新增目标或方案，只把已接受 design 中“tier 2 = fallback recent window +
section-aware degrade”的实现 owner 纳入封闭范围。AgentCodex 必须保留
`test_dispatch_scheduler.py` 的默认预算全阶段集成证据，并在 implementation artifact 记录本次
allowlist blocker、Controller 裁决与 direct-owner 验证。其余 allowlist、non-goals、README defer
和 completion signal 不变。

## Third narrow amendment：post-coverage mechanical oracles

完整受影响测试面首次覆盖率运行（`3517 passed / 3 failed`）暴露两个未进入 Slice 2 精确矩阵、
但被本 Slice public contract / owner extraction 必然推翻的旧测试 oracle：

1. `tests/host/test_session_attachment_registry.py::test_slice_one_does_not_export_attachment_contract_from_package_root`
   冻结的是 accepted Slice 1 的临时 handoff：attachment value types/registry 当时不得从
   `dayu.host` 包根公开。Slice 2 Exact change 1 明确要求完成 public types/export，继续保留该断言
   会直接否定当前 slice 的唯一稳定 handoff；production compatibility 隐藏同样不允许。
2. `tests/host/test_terminal_post_commit.py::_EXPECTED_TERMINAL_PRODUCERS` 仍把 active-cancel closeout
   owner 写成 `HostDispatchScheduler.tick_active_cancel_watchdog._operation`。Slice 2 为 RW target
   attachment 增加 target-session watchdog 后，全局与 target 入口共同委托
   `HostDispatchScheduler._tick_active_cancel_watchdog._operation`；静态 AST oracle 必须跟随真实唯一
   terminal transition owner。现有第一次 amendment 只授权 recovery qualified-name 迁移，未覆盖
   这一同源 helper extraction。

Controller 在 accepted plan Slice 2 allowlist 中仅追加/扩充：

- `tests/host/test_session_attachment_registry.py`：只允许把 Slice 1 “package root 不公开”临时断言
  迁移为 Slice 2 public export contract；registry 的冲突、lease、close 与 Slice 1 primitive 断言不得改。
- `tests/host/test_terminal_post_commit.py`：在第一次 amendment 的 recovery rename 之外，只允许把
  active-cancel terminal producer qualified name 从 public wrapper 更新为共享 private owner；terminal
  transition 闭集、promotion owner 与其它业务断言不得改。

两项都是 production owner/public contract 已由 accepted plan 明确要求后触发的机械测试迁移，
不改变目标、设计、schema、state machine、slice boundary 或 README defer。AgentCodex 仍须复现并
解决同次覆盖率运行中的 proactive crash-resume 次序稳定性失败；该失败不因本 amendment 被豁免。
其余 allowlist、non-goals、completion signal 与验证要求保持不变。
