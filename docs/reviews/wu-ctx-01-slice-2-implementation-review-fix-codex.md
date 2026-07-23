# WU-CTX-01 Slice 2 Implementation Review Fix

## 1. Gate 与范围

- Work Unit：`WU-CTX-01`
- Gate：Slice 2 implementation review fix
- Controller decision：`needs-fix`
- 唯一 accepted finding：`CTRL-S2-IMPL-01`
- artifact path：
  `docs/reviews/wu-ctx-01-slice-2-implementation-review-fix-codex.md`
- base：accepted Slice 1 protected commit `b6f297b4`
- 状态：fix complete，未 commit、未 push、未创建 PR。

本 fix 的语义 owner 是
`tests/host/test_durable_schema.py` 中直接断言 `HOST_SCHEMA_VERSION` 的 contract
test。production schema owner 已正确声明 version 24；缺陷仅是同一测试的函数名与
中文 docstring 仍描述 queue-policy CHECK schema 23。

## 2. 唯一修改

仅修改 `tests/host/test_durable_schema.py`：

- 将
  `test_host_schema_version_is_queue_policy_check_version`
  改名为
  `test_host_schema_version_is_context_budget_canonical_fact_version`；
- 将中文 docstring 改为准确说明当前 committed Host schema version 是 context
  budget canonical fact schema 24；
- 保持既有 `assert HOST_SCHEMA_VERSION == 24` 不变。

没有修改 production、public contract、Controller-owned
`docs/host/issues-implementation-control.md`、原 implementation artifact 或既有 review
artifacts。没有进入 Slice 3，也没有实现 anchored builder。

## 3. Finding 状态

| Finding | Controller 裁决 | 本 fix 状态 |
| --- | --- | --- |
| `CTRL-S2-IMPL-01` | accepted | 已修复 |
| DS-F1 anchored builder | 当前 Slice 2 驳回；accepted Slice 3 计划内必做项 | 不在本 fix scope；未修改 |
| DS-F2 exhaustive branch `AssertionError` | rejected | 不在本 fix scope；未修改 |
| DS-F3 projector 重复 `Mapping` 检查 | rejected | 不在本 fix scope；未修改 |

## 4. 验证

Fresh validation：

- 目标单测：
  `pytest -q tests/host/test_durable_schema.py::test_host_schema_version_is_context_budget_canonical_fact_version`
  → `1 passed in 0.32s`。
- accepted plan §8.3 focused Slice 2 清单：
  → `732 passed, 3 warnings in 9.69s`。
- `python -m pyright dayu/ tests/ utils/`
  → `0 errors, 0 warnings, 0 informations`。
- `git diff --check`
  → 通过。

复用
`docs/reviews/wu-ctx-01-slice-2-implementation-codex.md`
中的 full Host clean gate 证据：
`2228 passed, 2 skipped, 6 deselected`。本 fix 只改变测试函数标识和 docstring，不改变
收集数量、断言或可执行路径，因此未机械重跑 full Host 与 coverage。

## 5. Docs 与 scope drift

- `tests/README.md` 不更新：本 fix 没有改变测试目录结构、运行入口、维护规则或稳定验证
  清单，仅修正单个测试的语义标签。
- 零 production scope drift。
- 零 public contract、schema、Controller control doc、原 implementation artifact、
  DS-F1/F2/F3 scope drift。

## 6. Residual risks 与完成状态

- 本 fix 没有新增 residual risk。
- DS-F1 的 anchored builder roundtrip 继续由 accepted Slice 3 覆盖，不属于本 fix 的
  未修复项。
- Slice 2 既有 residual risks 与 Controller 裁决保持不变。
- `CTRL-S2-IMPL-01` 已修复；下一 gate 是 AgentMiMo 与 AgentDS 双路 implementation
  re-review，随后由 Controller 作最终裁决。
