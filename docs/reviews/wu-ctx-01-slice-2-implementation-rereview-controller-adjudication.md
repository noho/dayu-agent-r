# WU-CTX-01 Slice 2 Implementation Re-Review Controller Adjudication

## 1. Scope

- Work Unit：`WU-CTX-01`
- Gate：Slice 2 implementation re-review
- Base：accepted Slice 1 protected commit `b6f297b4`
- Initial reviews：
  - AgentMiMo：`docs/reviews/code-review-20260724-055928.md`
  - AgentDS：`docs/reviews/code-review-20260724-055648.md`
- Initial Controller adjudication：
  `docs/reviews/wu-ctx-01-slice-2-implementation-review-controller-adjudication.md`
- Fix artifact：
  `docs/reviews/wu-ctx-01-slice-2-implementation-review-fix-codex.md`
- Re-reviews：
  - AgentMiMo：`docs/reviews/code-review-20260724-060844.md`
  - AgentDS：`docs/reviews/code-review-20260724-060842.md`

## 2. Re-Review Results

- AgentMiMo：`pass`
- AgentDS：`pass`
- 两路共同确认：
  - `CTRL-S2-IMPL-01` 已关闭；
  - 本 fix 只有 `tests/host/test_durable_schema.py` 的测试名/docstring 修正；
  - production、public contract、durable schema 行为均无 fix scope drift；
  - DS-F1 未提前进入 Slice 2，仍属于 accepted Slice 3；
  - DS-F2/F3 保持 Controller 驳回边界；
  - canonical fact、producer ordering/rollback、startup strict replay 与 public
    secrecy 的初审结论仍成立；
  - 0 个新增 actionable finding。

AgentMiMo artifact 中把“相对 base 的 assertion 23→24”误写为本次 fix 也修改了
assertion；Controller 已以当前 diff 和 fix artifact 复核：assertion 是 Slice 2 initial
implementation 已有修改，本次 fix 只改变函数名与 docstring。该 artifact 归因误差不
影响当前代码、验证或 re-review verdict。

## 3. Accepted Finding Closure

### CTRL-S2-IMPL-01

状态：**closed**

当前 owner-level contract：

```python
def test_host_schema_version_is_context_budget_canonical_fact_version() -> None:
    """当前 committed Host schema version 是 context budget canonical fact schema 24。"""

    assert HOST_SCHEMA_VERSION == 24
```

测试名、中文 docstring、assertion 与 production owner
`dayu/host/durable/schema.py::HOST_SCHEMA_VERSION` 已同源。

Fresh fix validation：

- 目标单测：`1 passed`
- accepted plan §8.3 focused Slice 2：`732 passed`
- full pyright：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：通过

Initial implementation 的 clean full Host
`2228 passed, 2 skipped, 6 deselected` 与 13 个 changed production files
branch coverage `>=80%` 继续有效；本 fix 没有改变可执行路径。

## 4. Residual Risk Adjudication

- DS-F1 不是 Slice 2 residual：anchored `ContextSizingResult`、builder null
  serialization、anchor diagnostic 与 roundtrip 已在 accepted Slice 3 计划中，是下一
  slice 的显式验收项。
- DS-F2/F3 已在初审 Controller adjudication 中以唯一 owner / typed exhaustive
  boundary 驳回，不保留为 residual。
- local durable import 有直接循环依赖证据；当前是已证明的最小边界，不创建无 owner
  的新 work unit。
- schema 按 fresh schema 起库，version 24 不要求旧库迁移。
- 没有 Slice 2 blocking open question。

## 5. Decision

**`pass`**

WU-CTX-01 Slice 2 implementation、review、fix 与双路 re-review 全部闭环。允许创建
accepted Slice 2 protected commit，并进入 Slice 3 usage-anchor implementation。

Slice 3 必须继续遵守用户确认的独立性：

1. `CONTEXT_BUDGET_EVALUATED` canonical fact 已由 Slice 2 独立成立；
2. Slice 3 只实现 usage anchor / conservative-estimated delta 与完整 conservative
   fallback；
3. provider 不返回 usage、usage 非法或 pairing 不可信时，必须回退到当前完整输入的
   Slice 2 conservative sizing，行为不得比当前实现差。
