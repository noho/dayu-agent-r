# PR 190 F18 Goal Confirmation Amendment

## Authority and supersession

- Work unit：F18。
- Authority：用户在同一 F18 中追加的 Controller follow-up。
- 本 amendment 只覆盖
  `docs/gateflow/pr-190-f18-goal-confirmation-20260808.md` 中“旧 Trial2 sequence 327 具体 root cause 必须先闭合，
  才能运行 B2 formal observation”的 sequencing 条款；原 artifact 的 B1 目标、scope control、真实运行约束、B2 用户裁决边界、
  Git/PR 边界与 non-goals 继续有效。
- 两路专项复核：
  - `docs/reviews/plan-review-20260808-150155.md`：`pass-with-risks`；
  - `docs/reviews/plan-review-20260808-150209.md`：`pass-with-risks`。

## Amended goal

旧 Trial2 sequence `325 -> 326 -> 327` 的具体 exception cause 保持：

`unresolved; original owner exception was not durably captured; no causal inference`

该旧失败是独立 residual diagnostic finding：不得删除、覆盖、重标 PASS，fixed-profile 新 observation 也不能反向解释它；但它不再
是 `interactive.interactive.g06.cap-constrained-memory-replacement@1` formal observation / readiness 的前置条件。

B2 formal observation 的新合法 entry path 是：

1. 每条 chain 使用完全 fresh workspace 与 durable state；在第一次 opener 前通过 production config loader / Service assembly
   安装完整 constrained execution profile。
2. 同一 chain 的所有 ordinary/compactor invocations 与 fresh reconnect 使用相同 profile/config identity；不得 chain 内编辑、
   hot-switch 或旁路改写 caps/policy。
3. replacement chain 先在同一 constrained policy 下形成一个带 canonical provenance 的 accepted FY2024 EvidenceFact，使其成为
   下一 compact input 的 `previous_evidence_fact`；再用真实 AAPL/Fins tool evidence形成新的 FY2025 material。
4. FY2025 evidence turn 必须自然离开 frozen selected-recent turn-group floor，并由 initial compactor input直接证明：真实 caps、
   previous FY2024 atom、新 FY2025 evidence material 与 unsupported `21.7%` / `18.2%` material 同处 immutable source
   boundary，且 relevant material 对同源 caps 构成真实竞争。不得从 Memory、回答文本或 sequence 猜测。
5. replacement + reconnect、same-boundary bounded repair、budget-exhausted fallback 可由独立 fresh real MiMo chains聚合覆盖。
   每条 chain 的最大 ordinary Run、compact operation、ordinary/compactor provider call、reconnect与 wall-time budget必须在首次
   provider 调用前冻结；自然未触发目标分支时按预算停止并标 `needs-more-evidence`，不得追加临场尝试或 output injection。
6. public evidence 必须由 Host public resolver/analysis 与脱敏 typed projection独立证明 mandatory truth；raw PTY/log/SQLite 与
   绝对私有路径只留 private。public tree 的最后 writer 是 secret/path scan与 digest manifest。

## Contract basis

- 目标 scenario 的 precondition 是 `relevant-material-over-initial-output-caps`，input class 是
  `initial-request-with-real-caps`；required evidence只要求 real caps、Host cap/usage audit、accepted provenance/omitted
  complement、same-boundary repair/exhausted fallback与 artifact/Memory/RunInput/reconnect 同源。
- Oracle predicates 29/30 不要求 wide profile baseline、profile hot-switch或旧 sequence 327 root-cause closure。
- `docs/cli_ci.md` 只要求最终 HEAD 上的 fresh real-provider run与用户裁决；允许经 production config loader / Service
  assembly 生效的 CI-owned constrained profile。
- `docs/host/design.md` 把 caps定义为 opener construction-time policy projection；从第一个 opener起固定完整 constrained
  profile 不需要新的 per-Run override或产品兼容分支。

## Stop and verdict rules

- 若任何合法 fixed-profile fresh chain 再出现 `runner_candidate_invalid`，立即 seal 当前失败并停止后续 provider 消耗，重新开启
  owner root-cause investigation；不得用另一条成功 chain掩盖。
- formal observation 完成后只生成逐项 observed behavior report。B2 继续 `unadjudicated`，overall readiness继续非 ready，
  直到用户另行裁决。
- final closeout 必须分别报告：旧 Trial2 diagnostic verdict、fresh fixed-profile real observation verdict、B1/B2 Oracle status。
