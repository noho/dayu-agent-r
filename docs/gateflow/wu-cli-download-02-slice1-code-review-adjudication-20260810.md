# WU-CLI-DOWNLOAD-02 Slice 1 code review 裁决

## Review inputs

- `docs/reviews/code-review-20260810-171054.md`
- `docs/reviews/code-review-20260810-171152.md`
- Implementation：`docs/gateflow/wu-cli-download-02-slice1-implementation-20260810.md`
- Base：`0fe85869bffe214d6d8bc18d0e69690a493928d1`

两路 review 均判定 production correctness、pre-workspace 时序、standalone mode、help 与 scope boundary 通过；均报告相同的两个低严重度维护 finding。总控逐项裁决如下。

## Findings

### 1. 永久 AST owner test 与实现结构耦合 — 接受，修复

`test_download_mutation_mode_conflict_has_one_production_owner` 验证的是 `BoolOp(And)` 的源码形状，不是 public owner contract；嵌套 `if`、局部变量或等价表达都会误报。它与本项目“测试断言 owner 级 contract 行为”的约束相比收益不足。

修复要求：

- 删除该测试及只为它引入的 `ast`、module/path 依赖。
- 保留并继续运行 request/effective-filter 行为矩阵、精确冲突诊断、非 bool 校验和 CLI 无副作用测试。
- 唯一 conjunction 检查只作为 implementation/review gate 的 `rg`/静态验证记录，不固化为结构耦合的长期测试。

### 2. `test_arg_parsing.py` 无关全文件格式化 — 接受，修复

当前 diff 混入约 20～30 处与 F12 无关的既有函数签名/表达式折叠。虽然不影响 correctness，但降低审查性并增加合并冲突风险，不符合最小 slice。

修复要求：

- 仅还原与 F12 无关的纯格式化 hunks，保留 `--rebuild` help inventory 与互斥 help owner test。
- 不使用 destructive reset/checkout，不覆盖其它文件；用精确 patch 还原。
- 修复后 `ruff format --check` 若因仓库基线本来未格式化而失败，应记录 changed-lines/既有 baseline 事实，不得重新全文件格式化制造相同 churn；`ruff check`、pytest、pyright 仍必须通过。

## Re-review gate

修复范围只允许上述 test cleanup 与相应 implementation/fix artifact 更新；production 实现不得改变。修复后 MiMo/DS 原 reviewer 必须独立 re-review，确认 production diff 不变、两个 finding 关闭、tests/static validation 仍通过，方可形成 accepted Slice 1 commit。

## Re-review 后总控 validation 裁决

两路 re-review 均判定上述 findings 已关闭，但 `ruff format --check` 对仍在 changed-files 集合内的 `tests/cli/test_arg_parsing.py` 返回失败。把它称为“已归因 baseline”不能满足用户冻结的 changed-files format gate，也不能在最终汇报中伪称通过。

最小修复路径：

- 将 `tests/cli/test_arg_parsing.py` 完全还原到 accepted-plan base，使它退出 changed-files 集合。
- 将 download help 的两个 option/互斥文案行为断言迁到同属 Slice 1 allowed files且已格式化的 `tests/cli/test_fins_commands.py`；不得删除该 owner 行为覆盖。
- Production 不变；其它 tests 不变。
- 重跑 affected tests、完整 focused union/coverage、全部实际 changed Python files 的 `ruff check` 与 `ruff format --check`、compileall、pyright、diff/static guards。只有 format check 真正 exit 0 后才可再次 re-review。

## Final re-review 与 accepted Slice 1 裁决

- `docs/reviews/code-review-20260810-173039.md`：`PASS`。
- `docs/reviews/code-review-20260810-173314.md`：`PASS`。

两路均确认：`test_arg_parsing.py` 相对 accepted-plan base 零 diff；help owner test 已等价迁入 `test_fins_commands.py`；production diff 与初审一致；实际 4 个 changed Python files 的 Ruff lint/format 均真实 exit 0；affected tests、完整 focused union、逐文件 coverage、compileall、全量 pyright 与 static guards 通过；无新增 finding。

总控裁决：**accepted Slice 1**。允许形成独立 protected commit；下一入口为 Slice 2 implementation，真实 installed CLI evidence 仍按 accepted plan 留到所有 slice 与 aggregate deepreview 后执行。
