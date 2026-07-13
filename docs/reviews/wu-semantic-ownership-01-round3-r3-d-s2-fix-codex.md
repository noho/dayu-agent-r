# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S2 Fix

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S2 — Virtual Section Consistency, Source Freshness, And Read Failure Contracts`
- Gate: `code review fix`
- Implementer: `AgentCodex`
- Status: `complete`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-controller-adjudication.md`
- Scope: 只修复 controller 接受的 `R3-D-S2-CR-F01`；不进入 re-review、commit、S3 或 R3-E。

## First-Principles And Owner Decision

Finding 成立，严重性维持 `low`。Accepted plan 明确由
`FinsReadRuntime._create_processor()` 拥有 source decode failure 到
`FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED, ...)` 的转换语义；当前实现已经在该 owner boundary 捕获
`FinsSourceDecodeError` 并完成转换。因此调用它的
`FinsReadRuntime._get_or_create_processor()` 无法再观察到该异常类型，外层同义转换分支是不可达死代码。

本 fix 直接删除外层 `try/except FinsSourceDecodeError`，保留 `_create_processor()` 的唯一 owner 转换。未改变错误码、错误文本、hint、cause chain、processor 创建、cache freshness 或 revision race 行为，也未增加 fallback、兼容分支或下游补偿。

## Changed Files

- `dayu/fins/tools/read_runtime.py`
  - 删除 `_get_or_create_processor()` 中不可达的 `except FinsSourceDecodeError` 分支。
  - 改为直接调用 `_create_processor()`；其它代码不变。
- `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-fix-codex.md`
  - 记录本 fix gate 的证据、验证、文档裁决、残余风险与 scope confirmation。

本 fix gate 未修改任何其它文件；工作区中其余既有 S2 未提交改动均保持原样。

## Finding Status

| Finding | Controller decision | Fix status | Evidence |
| --- | --- | --- | --- |
| `R3-D-S2-CR-F01` | `accepted / low` | `已修复` | `_get_or_create_processor()` 只直接调用 `_create_processor()`；`read_runtime.py` 中唯一 `except FinsSourceDecodeError` 保留在 decode mapping owner `_create_processor()`。 |

## Validation Results

所有 Python 命令均在 `source .venv/bin/activate` 后运行。

1. `pytest tests/fins/test_processor_read_consistency.py::test_read_runtime_maps_invalid_utf8_to_source_decode_failure -q`
   - 结果：`1 passed, 3 warnings`。
   - 结论：invalid UTF-8 仍由 owner 映射为既有 source decode typed failure，行为不变。
2. `pytest tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`
   - 结果：`37 passed, 3 warnings`。
3. `python -m pyright dayu/ tests/ utils/`
   - 结果：`0 errors, 0 warnings, 0 informations`。
   - pyright 仅提示存在新版本，不是类型检查失败。
4. `git diff --check`
   - 结果：通过，无输出。

pytest 的 3 条 warning 均来自 edgartools 既有 deprecated import，不是本 fix 引入的失败。

## README Decision

- 已读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`。
- 不修改 README。本 fix 只删除不可达重复异常分支，公开 read contract、架构边界、能力、接口与用户工作流均未变化。
- Accepted plan 仍由 S3 aggregate docs step 统一处理 S2 的 source revision/read failure contract 文档；本 gate 不提前进入 S3。
- 未修改测试，因此不触发 `tests/README.md` 更新；也未触发根 `README.md` 或 `dayu/README.md` 的职责范围。

## Residual Risks / Uncovered Areas

- 本 fix 未引入新的 residual risk。
- downloader-side `errors="ignore"` 仍位于 S2 read owner 路径和本 gate allowed files 之外。分类：`assigned to later work unit / outside current slice`。
- 非 UTF-8 业务 charset 支持仍需独立 encoding-policy owner。分类：`assigned to later work unit`。
- cache revision 读取开销仍待实际 profiling 后裁决。分类：`assigned to later work unit`。
- 完整 `pytest tests/fins -q` 仍由 approved S3 aggregate validation 覆盖。分类：`covered by later approved slice`。

上述风险均继承 controller adjudication，未因本次死代码删除而扩大。

## Scope Confirmation

- 未进入 re-review、commit 或 S3。
- 未修改 R3-E、Host、Engine、upload/download security 或 tool-security 文件。
- 未修改任何工具安全相关文件。
- 除 `dayu/fins/tools/read_runtime.py` 与本 artifact 外，本 fix gate 未触碰其它文件。

## Blocking Questions

无。

## Completion Status

- Accepted findings fixed: `1 / 1`
- Required validation: `pass`
- README: `no change`
- Blocking questions: `0`
- Next gate: 交回 controller；AgentCodex 停在 S2 fix gate，不自行进入 re-review、commit 或 S3。

