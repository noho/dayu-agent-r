# WU-CTX-02 + WU-CTX-03 Plan Fix Artifact

## 1. Gate / Scope

- Gate: WU-CTX-02 + WU-CTX-03 plan fix
- Fix agent: Codex
- Plan target: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- Scope: 只修复 controller accepted plan review findings；不进入 implementation、review、commit、push 或 PR。

## 2. Source Review Artifacts

- `docs/reviews/wu-ctx-02-03-plan-review-ds-20260601.md`
- `docs/reviews/wu-ctx-02-03-plan-review-mimo-20260601.md`
- Controller adjudication: `docs/reviews/wu-ctx-02-03-plan-controller-adjudication-20260601.md`

## 3. Accepted Finding IDs

- DS-1: Slice C fallback “最新 N 轮”选择规则不应是 public config 或任意魔法常量。
- DS-3: Slice D durable/run_transition.py 与 `RUN_STARTED` required payload 边界需要收紧。
- DS-4: Slice C 需要增加 conservative estimator compatibility 前置核对。

Rejected finding:

- DS-2: scene inheritance defense rejected。plan 未把 scene inheritance 防御测试加入必修 scope，仅补充“当前 WU 不改变 scene inheritance semantics”为 non-goal。

## 4. Per-finding Fix Status

### DS-1-已修复-fallback 最新 N 轮改为预算驱动选择结果

- Fix status: 已修复。
- Plan changes:
  - 在 Public interface 中明确 fallback “最新 N 轮”不是 public config，也不是任意内部魔法常量。
  - 在 Implementation Decisions 中规定 selection 先保留 current input anchor、required stable / compact represented context 和 `recent_raw_turns_floor` 下限，再按 deterministic reverse chronological material block order 追加最近 raw turn blocks，直到下一 block 会超过 hard budget 或 material 耗尽。
  - 在 Slice C exact allowed changes / invariants / tests 中增加稳定性、floor 下限和 hard budget 容纳结果断言。
- Validation expectation: implementation tests 必须断言同一 input cursor / material list 输出稳定、selected raw turn 数量不少于 floor 且不会选择超过预算的下一 block。

### DS-3-已修复-Slice D durable transition 默认禁止修改

- Fix status: 已修复。
- Plan changes:
  - 从 allowed production files 与 Slice D allowed files 中移除 `dayu/host/durable/run_transition.py`。
  - 明确默认不允许修改 durable transition、SQLite durable transition 结构或 `RUN_STARTED` required payload。
  - 明确 reactive fallback 优先在 `engine_ingest.py`、`run_input.py` 与 fallback provider 内接线。
  - 增加 stop condition：若必须修改 durable transition、`RUN_STARTED` payload validator required field 集合或 public typed payload required 字段，停止并交回 controller。
- Validation expectation: Slice D implementation 不应触碰 durable transition；如发现必须触碰，应停止而不是自行扩 scope。

### DS-4-已修复-Slice C 增加 estimator compatibility 前置核对

- Fix status: 已修复。
- Plan changes:
  - 在 Implementation Decisions 中要求 Slice C 开始 fallback dispatch 接线前，先核对现有 conservative estimator 能接受 fallback-selected `message_fragments` 子集。
  - 在 Slice C 增加 prerequisite check，要求 normal、empty stable input、over-budget 三类 fallback estimate 测试。
  - 明确若 estimator 不兼容，只允许最小 typed adapter，不改变估算算法、不新增 provider tokenizer、不新增 public policy field。
  - 更新 residual risk RR-CTX-PLAN-02，把 estimator compatibility 前置核对列为 Slice C/D 的覆盖方式。
- Validation expectation: implementation tests 覆盖 normal、empty stable input、over-budget 三类估算路径。

### DS-2-已按裁决处理-scene inheritance 防御未纳入必修 scope

- Fix status: 已按 rejected-with-reason 处理。
- Plan changes:
  - 仅在 Non-goals 增加“当前 WU 不改变 scene inheritance semantics”。
  - 未增加 scene inheritance 防御断言或必修测试。

## 5. Changed Files

- `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- `docs/reviews/wu-ctx-02-03-plan-fix-codex-20260601.md`

## 6. Validation

- Tests: n/a，plan-only fix，未修改生产代码或测试代码。
- Pyright: n/a，plan-only fix，未修改 Python 代码。
- README sync: n/a，plan gate 不触发 README 修改；implementation gate 按 plan 与 AGENTS.md 触发规则检查。

## 7. New Risks / Open Questions

- New risks: none。
- Blocking open questions: none。

## 8. Residual Risk Classification

| Risk | Classification | Owner / Destination |
|---|---|---|
| fallback selection 实现细节偏离预算驱动规则 | covered-by-slice | WU-CTX-02 Slice C implementation + code review |
| estimator selected subset shape 不兼容 | covered-by-slice | WU-CTX-02 Slice C prerequisite check |
| reactive fallback durable transition 越界 | stop-condition-protected | WU-CTX-02 Slice D implementation；若触发则 controller decision |
| scene inheritance future drift | non-goal | 不属于当前 WU；未来如改变 scene inheritance semantics，另行设计/测试 |

## 9. Artifact Path

`docs/reviews/wu-ctx-02-03-plan-fix-codex-20260601.md`
