# UF-FIX07 Slice 2 Code Review Fix

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Slice：`Slice 2：CLI 与 LLM-facing primary 投影`
- Gate：`fix`
- 日期：2026-08-15
- Base / Slice 1 accepted commit：`9d0a2f8ab2068acc667752cb277e74bbe0a536c1`
- Review inputs：
  - `docs/reviews/code-review-20260815-200314.md`（MiMo：pass）
  - `docs/reviews/code-review-20260815-201037.md`（DS：1 low）
- Artifact path：`docs/gateflow/uf-fix07-slice2-review-fix-20260815.md`
- Completion status：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`
- Blocking open question：无
- Next entry point：`re-review`

## Finding 裁决

| Finding | 主控裁决 | Fix status | 证据 |
| --- | --- | --- | --- |
| DS Finding 1：material-primary failure 是英文且 ValueError hint 未包含 primary | `accepted` | `已修复` | failure 文本已归属 `FinsUploadFormatTextProjection.upload_tool_material_primary_failure`；schema description 与 adapter ValueError 机械复用该字段；hint 已加入 `primary`；ToolFailedOutcome exact message/hint 与零副作用测试通过 |

MiMo review 无 finding，无需 fix。两份 review artifact 均仅读，本 gate 未修改。

## 第一性原理与 owner 修复

Finding 动机成立：`ToolFailedOutcome.result.message` 是 LLM-facing 文本，material 携带 primary 的拒绝规则
已出现在 tool schema description，adapter 再硬编码英文文本会形成两个业务文本真源。正确修复边界不是
`FinsUploadToolCallable` 中做 message mapping，而是在既有上传文本 owner 中产生 typed projection，adapter 只机械消费。

实现后的唯一数据流：

```text
project_fins_upload_format_text()
  -> FinsUploadFormatTextProjection.upload_tool_material_primary_failure
       -> upload_tool_primary schema description 内嵌同一字段
       -> _upload_primary_selectors_from_arguments() 直接 ValueError(同一字段)
            -> FinsUploadToolCallable ValueError outcome.message
```

ValueError recovery hint 属于 tool callable 失败投影责任，已收敛为模块级 `Final[str]`，文案为：
`请检查 ticker、upload_kind、action、files、primary、会计期间和材料字段后重试。`

## Fix scope 与 changed files

本 fix 仅修改 Slice 2 白名单内的 owner、adapter、测试与 artifact：

- `dayu/fins/upload_format_contract.py`
- `dayu/fins/tools/upload_tools.py`
- `tests/fins/test_upload_format_contract.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `docs/gateflow/uf-fix07-slice2-implementation-20260815.md`
- `docs/gateflow/uf-fix07-slice2-review-fix-20260815.md`

未修改 CLI 行为、Slice 1 owner、Host/Engine/runtime/storage/Docling/README/registry/oracle/evidence，也未修改任一
review artifact。

## Tests 与 validation

### Affected tests

```bash
source .venv/bin/activate
python -m pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py tests/fins/test_upload_format_contract.py -q
```

- Exit code：0
- Result：`721 passed, 3 warnings in 16.40s`
- Warning：3 条均为现有 `edgar` 依赖 deprecation warning，与本 finding/fix 无关。

新增/更新的 owner-level assertions：

- `upload_tool_material_primary_failure` 精确等于中文、自解释、可行动的拒绝文本。
- `upload_tool_primary` schema description 逐字包含上述 typed failure 字段。
- adapter 直接抛出的 `ValueError` 文本精确等于同一 projection 字段。
- material-primary `ToolFailedOutcome.result.message` 精确等于同一 projection 字段。
- `ToolFailedOutcome.result.hint` 精确包含 `primary` 且提示检查后重试。
- failure 前后 workspace tree 不变，state repository、executor submit、observation 与 job file 均为零。

### Targeted pyright

```bash
source .venv/bin/activate
python -m pyright dayu/cli/arg_parsing.py dayu/cli/commands/fins.py \
  dayu/fins/tools/upload_tools.py dayu/fins/upload_format_contract.py \
  tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py tests/fins/test_upload_format_contract.py
```

- Exit code：0
- Result：`0 errors, 0 warnings, 0 informations`
- pyright 新版本提示不是类型检查失败。

### 单生产文件 branch coverage

使用同一 affected test 集执行 `coverage run --branch`，结果 `721 passed, 3 warnings in 18.66s`；
然后逐文件执行 `coverage report --include=... --fail-under=80`：

| 文件 | Coverage | Gate |
| --- | ---: | --- |
| `dayu/cli/arg_parsing.py` | 99% | pass |
| `dayu/cli/commands/fins.py` | 81% | pass |
| `dayu/fins/tools/upload_tools.py` | 92% | pass |
| `dayu/fins/upload_format_contract.py` | 89% | pass |

### Diff / scope

- `git diff --check`：exit 0，无输出。
- Slice 2 生产/测试 diff 仍仅位于获准白名单。
- Review artifacts 为主控提供的未跟踪输入，本 fix 未修改。

## Docs decision

本 fix 不修改 README。README 同步仍归 accepted Slice 4，不在 review fix 中扩大范围。

## Residual risks / uncovered areas

- 既有 delete+files adapter 英文消息：`assigned to later work unit`。该路径不是 Slice 2 新增，主控明确要求
  本轮不处理；owner/destination 为后续 LLM-facing 文案收敛或 registry/evidence work unit。
- schema `files.maxItems=100` 与 ingestion 上限的 owner design：`assigned to later work unit`。该设计是 accepted plan
  明确边界，本 fix 不改。
- Slice 3 asset/storage/process 行为：`covered by later approved slice`，owner/destination 为 Slice 3。
- README 与全量 closeout：`covered by later approved slice`，owner/destination 为 Slice 4。
- accepted plan §12 的 UF-FIX08/10/11、registry/evidence 和真实 scenarios：`assigned to later work unit`。
- 未分类 residual risk：无。

## 禁止边界确认

- 未修改 review artifact、README、registry、oracle、evidence、ingestion runtime、Docling 或 storage。
- 未执行 UF-PF07、UF-PF12 或其它真实 evidence。
- 未 commit、push、创建/推进 PR 或对外 comment。
- 未执行 re-review，未进入 Slice 3。

## Gate decision

DS Finding 1 已按主控裁决完整修复，验证通过，没有 blocking open question 或未分类 residual risk。
Completion status：`REVIEW FIX COMPLETE / RE-REVIEW PENDING`。Next entry point：`re-review`。
