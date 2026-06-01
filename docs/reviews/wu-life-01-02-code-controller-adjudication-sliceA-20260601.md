# WU-LIFE-01 + WU-LIFE-02 Slice A Code Review Controller Adjudication

日期：2026-06-01
总控：AgentController
当前 gate：code review slice A
Implementation artifact：docs/reviews/wu-life-01-02-implementation-sliceA-codex-20260601.md
Code reviews：
- docs/reviews/wu-life-01-02-code-review-sliceA-mimo-20260601.md
- docs/reviews/wu-life-01-02-code-review-sliceA-ds-20260601.md

## 裁决结论

Slice A 的核心实现方向通过：未修改生产代码，新增 tests-first recovery lifecycle proof matrix 与 focused scanner tests，验证结果显示受影响测试与 pyright 通过。两份 review 均未发现 correctness blocking issue。

但基于项目最佳实践和 plan 的 code-generation-ready 目标，部分维护性 finding 需要修复后再进入 re-review。原因是这些问题虽然不改变 runtime 行为，但会降低后续 review / maintenance 的证据清晰度，尤其是无关格式化 churn 和 coverage classification 不精确会削弱 proof matrix 的长期价值。

## Finding 裁决

| ID | 来源 | 裁决 | 修复要求 |
|---|---|---|---|
| A-MIMO-01 | AgentMiMo | accepted | `_active_run_observation` 是纯读 helper，应使用 `run_read`，避免在测试 helper 中表达写意图。 |
| A-MIMO-02 | AgentMiMo | accepted | 机械格式化 churn 不是 Slice A 语义变更，应回退无关 reflow，只保留必要代码变更。 |
| A-DS-01 | AgentDS | accepted | 回退无关格式化 churn；这不是风格偏好，而是保持 review diff 聚焦的可维护性要求。 |
| A-DS-02 | AgentDS | accepted | WAITING matrix row 需要拆分 low-level existing 与 durable-read new，或等价地精确表达现有覆盖增强和新增 durable-read 覆盖。 |
| A-DS-03 | AgentDS | accepted | `running-missing-current-attempt-or-dispatch` 不能标注 existing 而没有 scanner 级直接测试；应补轻量 deterministic scanner test，或改为 new 并在本 slice 内完成该 new coverage。 |
| A-DS-04 | AgentDS | accepted | durable-read WAITING 测试名不应暗示 public API；改名为明确 durable 语义的名称，或在名称和 docstring 中消除误导。 |

## Fix Scope

fix agent 只允许修改：

- `tests/host/test_recovery_scan.py`
- `docs/reviews/wu-life-01-02-fix-sliceA-codex-20260601.md`

不允许修改生产代码、plan、README、control doc 或其它 tests。修复后必须运行：

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py -q
python -m pyright dayu/ tests/ utils/
```

## Blocking Open Questions

none
