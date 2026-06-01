# WU-CTX-02 + WU-CTX-03 Plan Re-Review (DS)

## 1. Re-review 元数据

- **Gate**: WU-CTX-02 + WU-CTX-03 focused plan re-review
- **Review target**: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- **Fix artifact**: `docs/reviews/wu-ctx-02-03-plan-fix-codex-20260601.md`
- **Source reviews**: `docs/reviews/wu-ctx-02-03-plan-review-mimo-20260601.md`、`docs/reviews/wu-ctx-02-03-plan-review-ds-20260601.md`
- **Controller adjudication**: `docs/reviews/wu-ctx-02-03-plan-controller-adjudication-20260601.md`
- **Scope**: 仅复核 DS-1、DS-3、DS-4 修复状态及 DS-2 排除状态

## 2. Finding 逐项复核

### DS-1: Slice C fallback "最新 N 轮" 选择规则

**裁决要求**: N 由 deterministic budget-driven selection 得出，不是 public config，不是任意魔法常量；tests 覆盖 determinism、floor、hard-budget behavior。

**复核结果**: 已修复

**证据**:

| 要求 | Plan 位置 | 内容 |
|---|---|---|
| N 不是 public config | Section 5 (line 129) | "fallback '最新 N 轮'不是 public config，也不是可任意调整的内部魔法常量" |
| N 是 budget-driven selection 输出 | Section 5 (line 129) | "N 是预算驱动选择算法的输出：在 hard budget 约束下，先固定必须保留的 anchor / stable / compact represented context / floor，再按确定性 reverse chronological material block 顺序尽可能追加最近 raw turn blocks" |
| 不定义任意 internal max 常量 | Section 6 (line 171) | "不定义任意 internal max 常量" |
| 算法细节 | Section 6 (line 171) / Slice C exact allowed changes (line 214) | 先保留 anchor + stable/compact context + floor，再 reverse chronological 追加直到超 budget 或 material 耗尽 |
| 必保留集合超 budget 则 fail closed | Section 5 (line 129) / Section 6 (line 171) | "若必保留集合本身已超过 hard budget，则 fallback estimate 结果为 over-budget 并 fail closed，不通过降低 floor 偷偷 dispatch" |
| Tests: determinism | Slice C invariants (line 219) | "selected block ids / digest 对相同 input cursor / material list 确定" |
| Tests: floor | Slice C invariants (line 219) | "selected raw turn 数量不少于 recent_raw_turns_floor，除非可用 material 本身不足" |
| Tests: hard-budget | Slice C invariants (line 219) / tests (line 220) | "selection 不超过 hard budget 可容纳结果" / "不会选择使 estimate 超过 hard budget 的下一 block" |
| Tests: normal/empty stable/over-budget | Slice C tests (line 220) | "fallback estimate 单测覆盖 normal、empty stable input、over-budget" |

### DS-3: Slice D durable/run_transition.py 边界

**裁决要求**: 默认不允许修改 `durable/run_transition.py` 或 `RUN_STARTED` required payload；reactive fallback 优先在 `engine_ingest`/`run_input`/fallback provider 接线；stop condition 明确。

**复核结果**: 已修复

**证据**:

| 要求 | Plan 位置 | 内容 |
|---|---|---|
| 默认不允许修改 run_transition.py | Section 4 (line 98) | "默认不允许修改 `dayu/host/durable/run_transition.py`、SQLite durable transition 结构或 `RUN_STARTED` required payload" |
| run_transition.py 不在 allowed files | Section 4 (line 84-98) | allowed production files 列表中无 `dayu/host/durable/run_transition.py` |
| Slice D 默认不允许 | Slice D allowed files (line 228) | "默认不允许修改 `dayu/host/durable/run_transition.py`" |
| 不得修改 RUN_STARTED required payload | Slice D exact allowed changes (line 229) | "不得新增或修改 `RUN_STARTED` required payload，不得修改 durable table schema" |
| 优先在 engine_ingest/run_input/fallback provider 接线 | Section 4 (line 98) / Slice D exact allowed changes (line 229) | "reactive fallback 接线必须优先在 `engine_ingest.py`、`run_input.py` 与 fallback provider 内完成" / "优先通过 `engine_ingest.py` 内部 recovery flow、`run_input.py` fallback provider 与现有 recovery start transition 创建新 Attempt" |
| Stop condition 明确 | Slice D stop condition (line 238) | "若实现必须修改 `dayu/host/durable/run_transition.py`、SQLite durable transition、`RUN_STARTED` payload validator required field 集合或 public typed payload required 字段，停止并交回 controller" |

### DS-4: Slice C estimator compatibility 前置核对

**裁决要求**: Slice C 增加 estimator compatibility 前置核对；tests 覆盖 normal、empty stable input、over-budget；不新增 provider tokenizer、不新增 public policy field。

**复核结果**: 已修复

**证据**:

| 要求 | Plan 位置 | 内容 |
|---|---|---|
| 前置核对 | Section 6 (line 172) | "Slice C 开始 fallback dispatch 实现前必须先核对现有 conservative estimator 能接受 fallback-selected `message_fragments` 子集" |
| Prerequisite check 子节 | Slice C (line 213) | 独立 "Prerequisite check" 段落，明确"在接线 proactive dispatch 前，先用最小单元测试或现有 estimator 调用点验证" |
| Normal 测试 | Slice C prerequisite check (line 213) / tests (line 220) | "覆盖 normal、empty stable input、over-budget 三类 fallback estimate" |
| Empty stable input 测试 | 同上 | ✓ |
| Over-budget 测试 | 同上 | ✓ |
| 不新增 provider tokenizer | Section 6 (line 172) / Slice C prerequisite check (line 213) | "不新增 provider tokenizer" |
| 不新增 public policy field | 同上 | "不新增 public policy field" |
| 仅允许最小 typed adapter | Section 6 (line 172) / Slice C prerequisite check (line 213) | "只允许增加最小 typed adapter 以转换输入形状，不改变估算算法" |
| RR-CTX-PLAN-02 更新 | Section 11 (line 329) | "Slice C 前置核对 conservative estimator 对 fallback-selected `message_fragments` 子集的兼容性；fallback 后强制重估；normal、empty stable input、over-budget 测试覆盖" |

### DS-2: Scene inheritance defense（rejected）

**裁决要求**: 不纳入必修 scope。

**复核结果**: 未作为必修 scope 引入（已按 rejected-with-reason 处理）

**证据**:

| 检查项 | Plan 位置 | 内容 |
|---|---|---|
| Non-goal 明确排除 | Section 2 (line 39) | "不改变 scene inheritance semantics；当前 WU 只要求 `conversation_compaction` scene default model 与默认 execution profile compactor model 对齐，不新增'不得继承 conversation_compaction'的配置约束或防御性测试" |
| 无 scene inheritance 防御测试 | 所有 slice tests | 各 slice 测试列表中无 scene inheritance 相关测试 |
| 无 scene inheritance 防御断言 | 所有 slice invariants | 各 slice invariants 中无 scene inheritance 约束 |

## 3. 最终状态

| Finding | 状态 |
|---|---|
| DS-1 (fallback N 选择规则) | 已修复 |
| DS-3 (durable transition 边界) | 已修复 |
| DS-4 (estimator compatibility) | 已修复 |
| DS-2 (scene inheritance, rejected) | 证据失效（rejected，未被误引入） |

- **未解决数**: 0
- **Blocking questions**: 0

## 4. 结论

DS-1、DS-3、DS-4 三项已按要求在 plan 中完成修复，DS-2 未被误引入为必修 scope。Plan 当前状态满足 controller adjudication 的全部修复要求，re-review 通过。

---

- **Artifact path**: `docs/reviews/wu-ctx-02-03-plan-rereview-ds-20260601.md`
- **Conclusion**: PASS — 所有 accepted findings 已修复，rejected finding 正确排除
- **Unresolved count**: 0
- **Blocking questions**: 0
