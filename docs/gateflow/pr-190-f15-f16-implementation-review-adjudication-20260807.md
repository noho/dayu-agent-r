# PR 190 F15 / F16 Implementation Review Adjudication

## Gate 与证据

- Gate: implementation review adjudication。
- Branch / base: `codex/interactive-oracle` / `580b1427`。
- 独立审查：
  - `docs/reviews/pr-190-f15-f16-implementation-review-mimo-20260807.md`
  - `docs/reviews/pr-190-f15-f16-implementation-review-ds-20260807.md`
- Controller 直接审计范围：tracked diff、两个 ignored PTY harness、Host lifecycle projector、accepted plan/implementation artifact。
- 本文只裁决 finding；修复、复验和最终状态记录在后续 review-fix artifact。

## 第一性原理裁决

F15 的主修复成立：accepted replacement 到 previous packed/readable pair 的 owner 在 Host，五区文本必须先进入同一 canonical projection，strict validator、F14 cumulative coverage frontier 与 accepted tool evidence exact renderer 均不得被放宽或改写。

F16 的主修复尚未达到 evidence gate。canonical Run terminal 与 PTY process outcome 已分离，但 consumer 在 dependency stop、invalid observation 与 aggregate index 上仍可能丢证据或误报 complete。因此不能在 review 前提交，更不能启动 binding real rerun。

## Reviewer findings 裁决

### MiMo 001 — 接受并提高约束

`_segment_terminal_facts()` 在 `run-terminals.json` 缺失或 invalid shape 时会二次抛错，导致主 harness 无 final index。finding 接受。

修复不得把 invalid 静默降成 `(0, False)`；必须保留原异常/validation diagnostics，标记 harness/evidence `invalid`，阻断依赖链，并继续完成独立 evidence/index 固化。

### MiMo 002 — 接受

`execution-index-f15-f16.json` 只有 accepted 数，缺逐 process outcome、完整 terminal counts、per-run descriptor/digest、compaction observation 与 secret scan。finding 接受。index 必须只投影 observation facts，不新增 scenario verdict。

### MiMo 003 — 拒绝删除

`RunObservationRole.INDEPENDENT` 是可复用的 observation contract，不是需要删除的 dead compatibility surface。保留该 enum；补 pure role mapping / test 证明独立 action 不被 required dependency 链误分类。

### DeepSeek 016 — 有条件拒绝

accepted tool evidence 与普通 normalized material 是两个不同的输入语义边界。不得为了消除构造字段重复，把 raw exact renderer 文本伪装成 canonical-normalized wrapper，也不得加入 boolean/trusted-string seam。

允许使用两个明确 typed prepared-text wrappers/union 复用低层 constructor；若这会引入超过当前风险的抽象，则保留显式分支并记录该重复是 semantic isolation 的代价。本 finding 不得驱动 schema/public contract 改动。

### DeepSeek 017 — 接受测试缺口

现有 strict constructor/parser 已拒绝 whitespace-only required text，但 accepted plan 要求明确 evidence。补 accept/read/projector owner tests，证明不会 skip、default 或 renumber。

### DeepSeek 018 — 接受

`required_success_accepted_ordinal + 1` 是 upstream ordinal 到 dependent Run ordinal 的语义转换，不能只靠临时脚本中的隐式算术。抽成 typed/pure mapping helper并测试，或以等价的显式 contract 消除歧义。

## Controller additional findings

### C01 — P1：dependency stop 后 PTY 可永久等待

`prompt_observe_calibration.py` 在 `dependency_stopped` / `observation_invalid` 时只递增当前 action。下一 action 仍等待一个不会出现的 terminal count，cleanup EOT 也被排在该 trigger 之后，最终可耗尽 1800 秒 deadline。

修复必须：记录剩余 dependent actions 为 `not_run`；不发送任何依赖输入；执行一次明确、安全的 PTY cleanup；让 process 尽快退出；保留 process exit 与 canonical failed/cancelled/lost terminal 的独立事实。

### C02 — P1：valid failure 被误投影为 evidence complete

当前 index 的 `evidence_status` 只查看 `harness_status == invalid`。valid `RUN_FAILED` 会使 dependency stopped，但仍可能得到 `complete`。required non-succeeded 应为 `insufficient`（非 PASS）；canonical observation 破损才是 `invalid`。依赖跳过的后续 segment 必须显式 `not_run`，不能参与 complete 证明。

### C03 — P2：terminal pair identity 与 shared projector 未完全同源

helper 仅按 `run_id` 配对，没有断言 accepted 与 terminal 的 `session_id` 相同；同时手工映射四类 terminal class，并用 `terminal_type is not RUN_LOST` 推导 public outbox membership。修复应验证 session identity，并复用 `dayu.host.lifecycle_events` 已有 status/public-outbox projector，避免第二映射真源。

### C04 — P2：formal adjudication 状态值错误

用户要求 replacement scenarios 保持 `unadjudicated`。临时 index 使用 `pending_user_adjudication`，必须改为精确 `unadjudicated`；不得写 accepted/ready/PASS。

### C05 — P2：implementation artifact 与实际控制流不一致

artifact 声称 dependency stop 后 cleanup/independent evidence 会继续，但 C01 反例证明当前控制流可能卡死。修复后按真实行为更新 artifact，并重新计算 tracked helper 与两个 ignored harness 的 SHA-256。

## 修复 gate 接受条件

1. 所有 P1/P2 correctness/evidence findings 修复；低风险 finding 有明确 fix 或基于 owner boundary 的拒绝理由。
2. invalid、insufficient、complete 三类 evidence 状态可由 deterministic tests 区分。
3. dependency stop 不发送后续依赖输入、不等待不存在的 terminal、仍固化 final index。
4. index 含完整 process/terminal/dependency/compaction/secret-scan facts，且 formal status 仍为 `unadjudicated`。
5. F15 strict pair、accepted evidence exact path、durable reopen、ordinary freeze/dispatch 与 F14 frontier 回归全绿。
6. 修复后由 MiMo / DeepSeek 对相同 diff 独立 re-review；未通过前不进入 commit、real rerun 或 PR gate。
