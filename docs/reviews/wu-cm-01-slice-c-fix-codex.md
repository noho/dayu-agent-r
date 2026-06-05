# WU-CM-01 Slice C Fix - Codex

## Gate

- Work unit: WU-CM-01
- Gate: Slice C fix
- Scope source: `docs/reviews/wu-cm-01-slice-c-code-review-controller-adjudication.md`
- Design source: `docs/host/design.md`
- Status: fix complete; ready for external re-review

## Scope Boundary

本次只处理 controller adjudication 中的 accepted findings。未处理 rejected / deferred cleanup，包括 compact artifact message reader、`_memory_messages` cleanup、测试 helper 可读性 cleanup、old schema_version explicit rejection message。

Changed files:

- `dayu/service/host_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_memory_projection.py`
- `docs/reviews/wu-cm-01-slice-c-fix-codex.md`

Docs decision:

- 未更新 README。用户明确禁止修改 README；本次也未改变用户可见命令、配置入口或公共文档职责，只修正 assembly 映射并补测试覆盖。

## Accepted Finding Fixes

### F-1: Service assembly 丢弃 effective model context window

Status: 已修复。

修复摘要：

- `dayu/service/host_assembly.py` 中 `_memory_projection_policy_from_config` 现在使用函数参数 `context_window_size` 装配 `MemoryProjectionPolicy.context_window_size`。
- 该参数来自 ordinary effective model 的 `context_window_tokens`，与 `docs/host/design.md` 中 Service / composition root 传入 effective model context window 的要求一致。

测试覆盖：

- `tests/service/test_host_assembly.py` 新增 `test_memory_projection_context_window_uses_effective_model_window`。
- 测试构造 profile policy `context_window_size=262144`，同时使用 effective model `deepseek-v4-flash` 的 `context_window_tokens=1048576`，断言 Host `memory_projection_policy.context_window_size == 1048576`。

### F-2: DuplicateMaterialSectionOwnerError dedicated vNext 覆盖

Status: 已修复。

修复摘要：

- `tests/host/test_compact_material.py` 新增 dedicated vNext duplicate owner test。
- 测试通过 public `build_compact_material_pack` 路径构造 previous compacted view 与 trace material 拥有相同 canonical source refs 和相同 content digest，断言抛出 `DuplicateMaterialSectionOwnerError`。
- 保留 `test_vnext_snapshot_does_not_bridge_old_goal_into_previous_view`，未删除 vNext no-old-goal bridge 覆盖。

### F-3: vNext projection budget limiting focused 覆盖

Status: 已修复。

修复摘要：

- `tests/host/test_memory_projection.py` 新增 facts section budget limiting test。
- 测试把 `evidence_fact_item_cap` 降为 1，输入两个 accepted compact fact candidates，断言只保留最新 fact，并在 snapshot diagnostics 中记录 `MemoryDiagnosticReason.BUDGET_LIMIT_REACHED`。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/host/test_compact_material.py tests/host/test_memory_projection.py -q
```

结果：

```text
58 passed in 0.37s
```

已运行：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## Residual Risks / Uncovered Areas

- fixed in current slice: F-1 effective model context window mapping 已由 production 修复和 service assembly test 覆盖。
- fixed in current slice: F-2 duplicate section owner guard 已由 vNext public builder 路径 dedicated test 覆盖。
- fixed in current slice: F-3 facts budget limiting 已由 focused projection test 覆盖。
- assigned to later work unit: compact artifact message reader vNext-aware cleanup 维持 controller adjudication 的 deferred-with-owner 状态。
- rejected-with-reason: `_memory_messages` cleanup、`_snapshot_with_goal` helper cleanup、old schema_version explicit rejection message 维持 controller adjudication 的 rejected 状态。

## Completion Status

本 fix gate 已完成 accepted findings 修复与要求验证。未 commit、未 push、未创建 PR、未进入 re-review。

Artifact path: `docs/reviews/wu-cm-01-slice-c-fix-codex.md`
