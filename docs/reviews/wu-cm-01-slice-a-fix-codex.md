# WU-CM-01 Slice A Fix Gate - AgentCodex

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice A fix |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-a-code-review-controller-adjudication.md` |
| fix scope | accepted findings A1 / A2 / A3 only |

## First-Principles Judgment

裁决中的 A1 / A2 / A3 动机成立。三项都位于 Slice A compact contract closure 同一边界内：A1 是 vNext accept barrier 的模块公共契约完整性；A2 是 parser 与 accept barrier 共享同一 label contract 真源；A3 是 `conversation_compact_input_vnext_from_material_pack` 的直接边界测试缺口。它们不要求切换 production compaction operation，也不要求处理 deferred D1。

## Changes

- A1：在 `dayu/host/context_governance.py` 的 `__all__` 中加入 `check_conversation_compact_output_vnext`。
- A2：将 vNext label section allowlists 与 stale-label 判定集中到 contract owner `dayu/host/compaction.py`：
  - 新增 `CONVERSATION_COMPACT_*_SOURCE_SECTIONS_VNEXT` 系列常量。
  - 新增 `conversation_compact_label_looks_stale_vnext(label: str) -> bool`。
  - `dayu/host/llm_compaction.py` 与 `dayu/host/context_governance.py` 直接 import 上述 contract helper / 常量，删除本地重复定义。
  - 未新增 compatibility wrapper、re-export、lazy import 或 old/new bridge。
- A3：在 `tests/host/test_compact_material.py` 增加直接边界测试，覆盖：
  - user turn -> `trace_material`。
  - assistant turn -> `answer_material`。
  - accepted evidence -> `evidence_material`。
  - previous compacted view 只接收 evidence-backed fact block，不吸收 goal 等非 fact stable block。
  - `current_input_anchor` readable but not citable。

## README Decision

- 已更新 `tests/README.md`：本次新增了 `test_compact_material.py` 的 vNext material mapping 直接边界测试，属于 tests README 的测试事实职责。
- 未更新 `dayu/host/README.md`：本次 fix 只收敛 Slice A 局部 vNext contract helper、accept barrier export 与测试覆盖，未切换 production compaction operation、Host public workflow、状态机、event payload 或用户可见行为；把该局部 contract 写入 Host 开发手册会越过当前稳定生产说明边界。

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py -q
```

Result: `105 passed in 0.33s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`

## Residual Risks

- Deferred D1 未处理：`previous_compacted_view` 的完整 session summary / answer anchor / forward intent / reference continuity materialization 仍需要 Slice B/C 的 operation event payload 与 memory projection 闭环。
- Production operation 未切换到 vNext：这是 Slice A approved boundary，仍由 Slice B 承接。
- Memory durable/projection 与 RunInputBuilder 仍未切换到 vNext：仍由后续 approved slices 承接。

## Completion Status

Slice A accepted findings A1 / A2 / A3 已修复并通过指定验证。未提交、未 push。
