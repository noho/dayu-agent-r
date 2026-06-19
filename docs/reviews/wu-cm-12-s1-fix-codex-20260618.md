# WU-CM-12 S1 Fix Gate - Codex

## Scope

- Work unit: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- Slice: S1 Material Block And Policy Owner Convergence
- Gate: fix
- Accepted finding source: `docs/reviews/code-review-wu-cm-12-s1-adjudication-20260618-143543.md`
- Accepted finding: DS-F1 only
- Deferred finding kept out of scope: DS-F2

## First-Principles Check

DS-F1 成立。`_facts_from_accepted_event` 在同一个 accepted compact event 内先遇到 oversized fact 时会累积 `BUDGET_LIMIT_REACHED` diagnostic；随后遇到 empty evidence labels 时走 early return。如果 early return 只返回 invalid diagnostic，就会丢失同一函数内已经确认发生的预算超限事实，导致 projection diagnostics 与实际处理路径不一致。

DS-F2 不在本次 fix 范围内。empty-label invalid candidate 仍让该 compact event 的 facts 物化结果为空；本次只保留已经累积的 diagnostics，不改变 valid facts 被后续 invalid candidate 清空的既有语义。

## Fix Review

- `dayu/host/memory.py:1824` 的 empty-label early return 已返回 `tuple(diagnostics) + (...)`，保留此前 oversized fact 累积的 `BUDGET_LIMIT_REACHED` diagnostic。
- `dayu/host/memory.py:1826` 仍返回空 facts，符合裁决中 deferred DS-F2 的范围边界。
- `tests/host/test_memory_projection.py:743` 新增 mixed oversized + empty-label regression fixture，断言 diagnostics 顺序为 `BUDGET_LIMIT_REACHED` 后接 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`，并断言 facts 仍为空。

本轮 Codex 未对生产代码或测试代码再做额外微调；现有草案已经符合裁决要求。本 artifact 是本轮新增文件。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q
```

结果：

```text
118 passed in 0.77s
```

已运行：

```bash
source .venv/bin/activate && pyright dayu/host/compact_material.py dayu/host/memory.py dayu/host/run_input.py tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

已运行：

```bash
git diff --check
```

结果：无输出，检查通过。

## README Decision

- `dayu/host/README.md` 已检查其 `Agent更新约束【必须遵守】`。本次 DS-F1 fix 不改变 Host public API、稳定架构边界、主要状态机或开发者稳定契约，不属于该 README 职责范围。
- `tests/README.md` 已检查。新增测试仍位于既有 `tests/host/test_memory_projection.py` 的 Conversation Memory coverage 范围内，没有新增测试层级、运行方式或维护约定，不需要更新。
- 根 README 与 `dayu/README.md` 未命中触发条件；本次不改变用户可见安装、入口、工作流、日志定位、工作区位置或分层关系。

## Residual Risks

- DS-F1: 已修复并由 mixed oversized + empty-label fixture 覆盖。
- DS-F2: deferred-with-owner，保留到 WU-CM-12 后续 S3 provenance guard / compact fact rendering review 中裁决；本次没有改变该语义。
- S2/S3/S4/S5 后续 slice 风险仍按既有 WU-CM-12 控制文档推进，不由本 fix gate 关闭。

## Completion Status

Fix gate pass. 不 commit、不 stage、不 push。
