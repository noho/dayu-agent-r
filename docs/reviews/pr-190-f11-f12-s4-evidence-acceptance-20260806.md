# PR 190 F11/F12 S4 real-provider evidence acceptance（2026-08-06）

## Gate decision

**ACCEPTED**。S4 implementation observation、immutable evidence、双路独立 review、总控逐项裁决、文档勘误与双路 re-review 已完成闭环。

- Implementation：`PASS`
- Real-provider observation：`PASS`
- Formal Oracle：`PENDING`
- 生产 finding：0
- 接受的 evidence-artifact finding：1（MiMo-02，已修复）
- 最终双路 re-review：MiMo `PASS`，DS `PASS`

本 gate 的接受不表示 Oracle ready，也不运行或裁决 frozen formal CLI scenarios。

## Accepted truth

- 基线 HEAD：`d9f044f944dd44e0d369f9d93e0533d2b725e413`
- immutable evidence root：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`
- `digest.json` SHA-256：`38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- manifest：159 个 covered files，另有 self-excluded `digest.json`，共 160 个发布文件；逐文件 digest 验证通过。
- secret scan：2 个 credential sources，exact-value 与 Authorization/Bearer/API-key pattern 均 0 findings。
- 4 个含 credential snapshot 的 `dayu_host.sqlite3` 已从发布树移至只读 quarantine；发布树保留的 4 个 `runtime_lanes.sqlite3` 不属于该 private Host DB 集合。

## Review loop

- MiMo initial review：`docs/reviews/pr-190-f11-f12-s4-evidence-mimo-review-20260805.md`
- DS initial review：`docs/reviews/pr-190-f11-f12-s4-evidence-ds-review-20260806.md`
- controller adjudication：`docs/reviews/pr-190-f11-f12-s4-evidence-review-adjudication-20260806.md`
- Codex fix：`docs/reviews/pr-190-f11-f12-s4-evidence-fix-20260806.md`
- MiMo re-review：`docs/reviews/pr-190-f11-f12-s4-evidence-mimo-rereview-20260806.md`，`PASS`
- DS re-review：`docs/reviews/pr-190-f11-f12-s4-evidence-ds-rereview-20260806.md`，`PASS`

### Finding adjudication

1. MiMo-01 rejected：canonical failed-terminal fallback input boundary 是 selected 9 / dropped 2；post-dispatch Memory 的 8 items 是另一投影。
2. MiMo-02 accepted/fixed：repo observation 已用 canonical request operation 与 `frozen_material_list_digest=sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee` 替换不可定位的派生 digest。immutable report 未回写，勘误链完整。
3. DS-01 rejected：assembly `compactor_model_id` 是配置 selector；actual provider/model 由 resolved runner identity、public Tool Trace 与 canonical terminal 拥有。
4. DS-02 rejected：baseline Memory summary 非空，replacement 后为 null，完整证明 clear。
5. DS-03 rejected：Host owner 计量为 title 7 + newline 1 + detail 28 = 36，canonical audit 与 repair feedback 同源。

## Accepted observation coverage

- Mimo `capability=none`：真实 attempts 无 structured-output request/outbound format；first-pass 与 exhaustion/fallback 均有证据。
- DeepSeek `capability=json_object`：真实 outbound 装配、first-pass、cap-constrained replacement、`session_summary:null`、same-boundary bounded repair、rolling correction、reconnect 与 exhaustion/fallback 均有证据。
- F11：successful compact 与 successful-response-then-rejected 两类 public Tool Trace response identity 均与 canonical terminal exact match；所有 equality artifact `finding_count=0`。
- Failed compact：两次 rejected 后恰好一个 failed terminal，0 compact artifact，semantic Memory 不污染，进入 deterministic fallback。
- Prompt/material boundary：system contract 同源，业务 marker/pressure text 只处于明确的不可信 material 边界。

## Residual risks / owner

- Formal Oracle remains pending：owner 为 Oracle controller；S5 只允许登记 replacement scenario 为 `unadjudicated`，不得声明 accepted/ready。
- `02-mimo-boundary` 未触发新的 compaction attempt：Mimo transport 已由 baseline/exhaustion覆盖；该 observation 不承担额外 boundary-compaction 结论。
- screen assembly selector 容易被跳读为 actual model：actual identity 已由正式 public/canonical evidence消歧；若未来要提升 smoke 人类可读性，owner 是 smoke harness 独立 work unit，不是 F11/F12 product contract blocker。
- reconnect 回答可把 18.2% 作为“已失效历史值”提及；活动 Memory/RunInput 未恢复旧结论。后续 Oracle 裁决必须继续区分 raw history 与 active semantic truth。

## Next gate

进入 S5：按已确认 replacement contract 更新 oracle/scenario lifecycle、handbook/readiness artifact 与 PR body；三条 replacement scenarios 只能标记 `unadjudicated`，registry 顶层继续为 `calibration`。
