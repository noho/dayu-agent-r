# WU-SEMANTIC-OWNERSHIP-01 R04 plan-fix Controller validation

## 1. Scope

- validated plan：`docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`
- validated fix record：`docs/reviews/wu-semantic-ownership-01-r04-plan-fix-codex.md`
- Controller 已完整读取两份文件并核对当前 `host_assembly.py`、`fins_wait_adapter.py` 与 `entrypoint_runtime.py` 调用链。
- 本验证不接受计划、不授权 implementation。

## 2. Closure status of accepted review findings

- `R04-PLAN-F01`：文本 closure 成立；typed mode 与 operation-kind 结构映射已明确分离。
- `R04-PLAN-F03`：owner closure 成立；Fins parser、Service identity routing、disabled validation 与 recognized non-awaiting misuse boundary 已明确。
- `R04-PLAN-F04`：测试迁移分类 closure 成立。
- `R04-PLAN-F02`：原 S2/S3 broken-state 反例已通过合并关闭，但合并后的新 S1/S2 边界仍未达到“每个保留 slice 都是可运行、可测试、语义完整产品状态”的 Controller 要求。

## 3. New direct-evidence finding

### R04-PLAN-CV-F05 — S1 暴露三模式 contract，但 scene-derived poller authority 延迟到 S2 删除

当前计划 S1 同时要求：

1. provider parser 接受 `poll/callback/manual`；
2. `_binding_for_tool_name` 映射三种 `WaitResumePolicy`；
3. poll registry 只包含 `poll` mode；
4. S1 结束时产品可运行且 pyright clean。

但当前 `with_entrypoint_wait_poller_policy -> _scene_selects_fins_awaiting_tools` 仍只依据 Fins awaiting tool name 与 scene selection，并无 typed mode 输入；它在 scene 选中一个配置为 `manual` 的 provider 时仍会构造默认 poller policy。S1 又已把该 provider 从 poll registry 排除，因此可能得到错误的 scene-derived poller 启用或 enabled-policy/missing-registry failure。`callback` 的错误也可能来自错误的 poll registry 缺失路径，而不是计划承诺的 authenticated transport pre-open fail-fast。

这会在 accepted S1 commit 中形成新的过渡产品语义和第二 authority，直接违反：

- 用户禁止过渡设计、局部最小设计和兼容 seam；
- plan §1 的 scene independence；
- Controller `R04-PLAN-F02` 要求每个保留 slice 都是可运行、可测试的产品状态；
- phaseflow slice 必须形成独立行为闭环，不能只有 contract/type 而消费者延后。

### Required fix

把当前 S1 与 S2 合并为一个单一原子 implementation slice。provider mode parser/binding/metadata、完整 runtime policy、Host defaults/fallback 删除、override/scene helper 删除、typed composition、tests/README/scans/smoke 必须在同一 slice 中完成，不建立任何中间 commit/checkpoint、旧 scene bridge 或临时 fallback。

计划中的 per-slice tests、顺序、allowlist、handoff 和“两 slices”措辞必须同步改为一个 slice；umbrella 原 S1/S2/S3 mandatory baseline 仍需逐项保留，不能因合并而弱化。

## 4. Boundary validation

- AgentCodex 只修改了 plan 并新增 fix artifact；control、reviewer artifacts、代码、测试、README、design 未被 Agent 修改。
- `git diff --check` 通过。
- rejected/no-fix dispositions、Host API/open_host no-diff、数值裁决、security/deferred/no-code 边界均保持不变。

## 5. Verdict

`FIX_CONTINUATION_REQUIRED / R04-PLAN-CV-F05`

AgentCodex 必须继续同一 plan-fix task，修正 plan 并更新同一 fix artifact；完成后 Controller 再验证。双路 re-review 与 implementation 尚未授权。

## 6. Re-validation

AgentCodex 已继续同一 plan-fix task，并在原 plan 与同一 fix artifact 中关闭 `R04-PLAN-CV-F05`：

1. 原 S1/S2 已合并为唯一原子 implementation slice；
2. provider mode/parser/binding/typed metadata、runtime policy、Host defaults/fallback 删除、override/scene helper 删除、typed composition、tests、README、scans 与 smoke 必须同一次完成；
3. 明确禁止中间 commit/checkpoint、旧 scene bridge、临时 fallback、compatibility field/wrapper 和 hard-coded bridge；
4. umbrella 原 R04-S1/S2/S3 mandatory baseline 在 §3 分别逐项保留，未因合并弱化；
5. §4.1 统一封闭 production/config/tests/smokes/README allowlist，§7-§10 的验证与 handoff 全部改为唯一 slice；
6. 多-slice 残留措辞 scan 零命中；§3 composition cross-reference 已纠正为实际 matrix 所在 §6.3；
7. `git diff --check` 与两个 untracked target 的独立 whitespace check 均通过；Agent 未修改 control、reviewer/Controller artifacts、代码、测试、README 或 design。

`R04-PLAN-F01..F04` 与 `R04-PLAN-CV-F05` 现全部关闭。Rejected/no-fix dispositions、Host API/open_host no-diff、12 个 packaged values、source-scan strictness、security/deferred/no-code 边界均保持不变。

### Re-validation verdict

`PASS / READY_FOR_DUAL_COMPLETE_PLAN_RE_REVIEW`

计划仍未 accepted，implementation 仍未授权。下一 gate 是 AgentMiMo / AgentDS 对最终 212 行 immutable plan、完整初 review/adjudication/fix/validation 链做双路完整 plan re-review。
