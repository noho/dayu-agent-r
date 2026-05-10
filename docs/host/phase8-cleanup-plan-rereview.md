# Plan Re-Review — Host P8 Legacy Cleanup + Code-Review Fix

## Reviewed Target

- Plan artifact (revised): `docs/host/phase8-cleanup-plan.md`
- Original review: `docs/host/phase8-cleanup-plan-review.md`（10 个 accepted findings F01-F10）
- Cross-check 源：
  - `docs/reviews/code-review-20260510-{0825,0830,0831}.md`
  - `dayu/host/_run_harness.py`、`_attempt_supervisor.py`、`_attempt_lease.py`、`_run_state_store.py`、`_conversation_memory_durable.py`、`_tool_runtime.py`、`__init__.py`
  - `tests/host/test_phase8_attempt_recovery.py`、`tests/host/test_phase8_attempt_supervisor.py`、`tests/host/test_phase8_multiprocess_stress.py`、`utils/smoke_host_p8_attempt_lease.py`
  - `CLAUDE.md`、`docs/host/phase8-plan.md`

## F01-F10 Verification 摘要

| ID | 等级 | 状态 | 备注 |
|----|------|------|------|
| F01 | 严重 | **fixed** | S3 Case A/B 显式矩阵、行号 1151-1342、新增 `test_handle_owner_lost_cas_miss_no_stale_terminal` |
| F02 | 高 | **fixed** | D6 显式删除 `InMemoryToolRuntime.fetch_more` 公开入口；S2 列出每个消费方文件与目标 API |
| F03 | 高 | **fixed** | D2 删除 `MARK_RECOVERING_AND_CREATE_ATTEMPT` 枚举值、删字段、加 `source_attempt_id`、改 typed log 字段；S5 列出测试改写行号 |
| F04 | 高 | **fixed** | D7/S1 引入 `is_durable: bool`；invariant 矩阵覆盖 supervisor/event_store/attempt_state_store/storage 四个字段 |
| F05 | 中 | **fixed** | Slice 顺序调整：S1 invariant → S2 API 删除 → S3 owner-lost 原子化（plan §Slice 顺序段）|
| F06 | 中 | **fixed** | D2 已基于 grep 给出确定删除范围（supervisor + 4 个测试/utils 位置） |
| F07 | 中 | **fixed** | D1 显式 CAS hit/miss 双路径、复用现有 `_run_to_store` 退出，禁止新公开 close 入口；规定 stop 条件 |
| F08 | 低 | **fixed** | D7 显式 `is_durable=True` 与 ContextVar 的优先级（is_durable 上限、ContextVar 严格充要） |
| F09 | 低 | **fixed (caveat)** | S10 加入 `dayu/README.md` grep；但仓库当前并无该文件（见下 N02） |
| F10 | 低 | **fixed** | S7 测试矩阵扩展为 `acquire_new_attempt` 路径 + `host_attempts/host_fencing_tokens` 行未插入断言；recovery 路径已被 S5 下线，无需覆盖 |

---

## New / Residual Findings

### N01-未修复-[中]-D7「`is_durable: bool` 默认 `False`，禁止省略」措辞自相矛盾

- **Plan位置**: §D7 第 1 项；§Slice S1 第 1 条「`is_durable: bool` 必填参数」
- **问题类型**: 契约措辞不自洽 / 不可直接实施
- **计划当前写法**:
  - D7：`LocalRunHarness.__init__ 新增 is_durable: bool 显式构造参数（默认 False，禁止省略）`
  - S1：`LocalRunHarness.__init__ 加 is_durable: bool 必填参数`
- **为什么有问题**: 「默认 False」与「禁止省略 / 必填」是互斥语义。Python 层面只有两种实现：
  1. 必填关键字参数（无默认值），所有现有 `LocalRunHarness(...)` 构造点立即编译失败；
  2. 有默认值（`= False`），调用方可省略，与「禁止省略」冲突。
  Plan 必须二选一，否则 implementation agent 会自行裁决，影响 S2 之前的测试可运行性。
- **直接证据**: plan §D7 / §S1 上述行；现状 `dayu/host/_run_harness.py` `LocalRunHarness.__init__` 无 `is_durable` 参数，所有现有构造点（`build_durable_harness` + 测试 fixtures）都不传该参数。
- **影响**: 中。若选「必填」，S1 完成的瞬间所有未迁移测试在 collection 期就会因 `TypeError` 失败，跨 S1→S2 区间无法跑测试；若选「有默认值 False」，与 plan 文字冲突，且无法在编译期强制装配方显式声明意图。
- **建议改法和验证点**:
  - 推荐：keyword-only **必填**（无默认值）；同时把 S1 「测试」段补一条：S1 内同步把 `build_durable_harness` 装配点与 S1 直接引用的 fixture（包括 phase1 公开边界测试）传入显式 `is_durable`。其余测试随 S2 迁移。或
  - 备选：keyword-only 默认 `False`；plan 文字改为「显式构造参数（默认 False；durable 装配必须显式传 True，由 invariant 校验兜底）」。
  - 验证点：`grep -n "LocalRunHarness(" dayu tests utils` 命中处必须显式传 `is_durable=...`；pyright 干净。
- **修复风险（低/中/高）**: 低
- **严重程度**: 中

### N02-未修复-[低]-F09 加入的 `dayu/README.md` grep 目标文件并不存在

- **Plan位置**: §S10 第「F09 防御」与「完成信号」grep 命令
- **问题类型**: 验证误指
- **计划当前写法**: `grep -n "start_run\|stream_run_events\|fetch_more_tool_result\|get_run_result\|get_tool_fetch_more_handle" dayu/README.md`
- **为什么有问题**: 实际仓库 `dayu/README.md` 不存在（`ls dayu/README.md` 报 No such file or directory）。grep 会因路径缺失而 silent / 报错；S10 完成信号若以「grep 输出为空」为通过条件，无法区分「文件不存在」与「文件存在且无残留」。
- **直接证据**: `ls dayu/README.md` → No such file or directory；CLAUDE.md「README 触发更新规则」未把 `dayu/README.md` 列入 Host 包修改的同步范围（仅在「分层关系 / 装配方式 / UI/Service/Host/Agent 边界变化」时同步）。
- **影响**: 低。
- **建议改法和验证点**:
  - 把 F09 防御改为：先 `[ -f dayu/README.md ]` 判定，存在才跑 grep；不存在跳过并在 closeout 注明。
  - 或直接删除 F09 的 `dayu/README.md` 子项；改为统一 grep `docs/host/ dayu/host/README.md`，与 CLAUDE.md 触发规则一致。
- **修复风险（低/中/高）**: 低
- **严重程度**: 低

### N03-未修复-[低]-D2 删除 `AttemptStaleConflictError` 等 helper 的范围未与 `update_state_owner_aware` / `close_attempt_with_diagnostic_state` 残留 `recovery_attempt_id=None` 字面量对齐

- **Plan位置**: §D2 第 4 子点；§Slice S5
- **问题类型**: 删除范围不闭环
- **计划当前写法**: 「在 `dayu/host/_run_state_store.py` 删除 `mark_recovering_and_create_attempt`、对应 docstring 引用、`AttemptStaleConflictError` 等仅服务该方法的 helper（保留 `close_attempt_with_diagnostic_state` 与 `update_state_owner_aware`）。」
- **为什么有问题**: grep 显示 `_run_state_store.py:1133, 1145` 与 `update_state_owner_aware` / `close_attempt_with_diagnostic_state` 内部仍构造 `AttemptRecoveryDecision(recovery_attempt_id=None, recovery_attempt_index=None, ...)`，`_attempt_supervisor.py:905` 同样。这些位置不属于「仅服务 mark_recovering_and_create_attempt」的 helper，而是保留路径里的字段填充。S5 必须连带改这些 dataclass 构造点（删字段或改新字段名 `source_attempt_id=...`），否则 dataclass 字段集与构造调用不一致 → pyright/runtime fail。
- **直接证据**: `dayu/host/_run_state_store.py:1133, 1145`、`dayu/host/_attempt_supervisor.py:905` 均直接构造 `AttemptRecoveryDecision(... recovery_attempt_id=None ...)`。
- **影响**: 低（grep-driven 修复显然），但 plan 没列出；implementation agent 在 S5 内自然会撞上。
- **建议改法和验证点**:
  - S5 「允许改动」补一行：「`AttemptRecoveryDecision` 所有构造点（`_run_state_store.py:1133/1145`、`_attempt_supervisor.py:905`）按新字段集（`source_attempt_id` / `action` / `reason`）重写。」
  - 完成信号补 grep：`grep -RIn "recovery_attempt_id=" dayu` 为空。
- **修复风险（低/中/高）**: 低
- **严重程度**: 低

### N04-未修复-[低]-`AttemptRecoveryAction.MARK_RECOVERING_AND_CREATE_ATTEMPT` 旧值的字符串字面量出现在多处 docstring / log，S5 grep 完成信号已覆盖但 plan 未列出 docstring 段落

- **Plan位置**: §Slice S5 完成信号 grep；`dayu/host/_attempt_supervisor.py:735, 785, 796, 876` docstring
- **问题类型**: 文档同步覆盖范围
- **计划当前写法**: S5 完成信号 grep 字符串 `MARK_RECOVERING_AND_CREATE_ATTEMPT|mark_recovering_and_create_attempt|recovery_attempt_id|recovery_attempt_index`。
- **为什么有问题**: grep 会命中 supervisor / lease 模块多段 docstring（line 735/785/796/876 等）。S5 「允许改动」未明确包含这些 docstring 改写，但完成信号又要求 grep 为空 → implementation agent 必须扩大改动范围才能让 grep 通过。Plan 明确这一点能避免 S5 触发 stop condition。
- **直接证据**: grep 命中行 `_attempt_supervisor.py:735, 785, 796, 876`；`_run_state_store.py:822, 1064`。
- **影响**: 低。
- **建议改法和验证点**:
  - S5 「允许改动」补：「同步删除 supervisor / lease store 中提及该 enum/方法的 docstring 段落与状态机叙述。」
  - 验证点不变。
- **修复风险（低/中/高）**: 低
- **严重程度**: 低

### N05-未修复-[低]-D7 invariant `event_store is DurableRunEventStore` 用 `isinstance` 与 CLAUDE.md「禁止 hasattr/isinstance 当类型逃避」的措辞张力

- **Plan位置**: §D7 第 2 子项「`event_store` 是 `DurableRunEventStore`（用 `isinstance` 检查 invariant，例外允许 —— invariant 校验非类型逃避）」
- **问题类型**: 编码硬约束的边界提示
- **为什么有问题**: plan 已自我说明这是 invariant 校验而非类型逃避（属于合规例外），但缺少把这条裁决落到代码注释/docstring 的指令。后续 review/maintainer 会反复质疑。
- **建议改法和验证点**: D7 / S1 加一条：在 invariant 校验代码处加中文注释「invariant 校验：`isinstance` 用于装配契约校验，非类型分支判断；与 CLAUDE.md 禁止 `isinstance` 当类型逃避不冲突。」
- **修复风险（低/中/高）**: 低
- **严重程度**: 低

---

## Adversarial Spot-Checks（无问题）

- **新增 `is_durable: bool` 是否构成 typing leak / public API 扩散**：构造参数非全局类型；不破坏分层（仅 Host 内部约束 + `build_durable_harness` 装配点显式传值）。`InMemoryToolRuntime` 同名 flag 由装配方同源传入，不引入双源真实。结论：无问题。
- **Slice 顺序 S1→S2→S3 是否破坏其它 invariant**：S1 在 invariant 立住后再删入口，符合「先关边界后清入口」的安全顺序；S3 owner-lost 原子化在 S2 之后实施时，新引入的 `_handle_owner_lost` CAS-miss 路径所依赖的 `is_durable=True` invariant 已就位，可正确 fail-fast。结论：无问题。
- **`AttemptRecoveryDecision` 字段重命名是否破坏 multiprocess stress 序列化协议**：S5 已显式列 `tests/host/test_phase8_multiprocess_stress.py:686-786` worker 协议字段调整。结论：无问题。
- **D1 RunStream 契约是否引入新 typed event**：D1 显式禁止新增 typed close 事件 / 公开入口，并在 implementation 中给出停下问 controller 的 stop 条件。结论：无问题。
- **D8 schema_version 严格校验是否破坏现有测试**：`_SCHEMA_VERSION=1` round-trip 测试与新 mismatch 测试覆盖；按 CLAUDE.md schema 起库政策不留兼容读。结论：无问题。

## Residual Risks

- **R-N01**：N01 的 `is_durable` 默认值/必填语义未在 plan 收敛 → owner: controller 在 plan-fix 选择必填或带默认，S1 落地。
- **R-N03**：`AttemptRecoveryDecision` 字段在 store 内部所有构造点的连带改动 → owner: S5 实施期收敛，完成信号 grep `recovery_attempt_id=` 为空。
- **R-existing R5**：`tests/host/_memory_store_fake` round-trip 等价测试若 S9 不能闭环，需在 closeout 给出 issue id（owner: S9）。
- **R-existing R3**：recovery scan 不再自愈，P9 lifecycle/admission 必须接管重启逻辑 → owner: S10 在 phase8-plan.md 与 review artifact residual risk 指向 P9。

## Plan Re-Review Conclusion

**pass-with-risks**

10 个原始 findings 全部按建议落到 plan 内（F01-F10 fixed）。残留 5 个新发现均为低/中级措辞或覆盖范围细节，不影响 plan handoff-ready 性质，建议 controller 在 plan-fix 阶段或 S1/S5 实施期一并处理 N01 / N03，N02 / N04 / N05 可在 S5 / S10 内顺手覆盖，不再单独 re-review。
