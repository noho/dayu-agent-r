# `WU-CLI-DOWNLOAD-02` Slice 1 code review fix

## 1. Gate 状态

- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Slice：Slice 1 — F12 invocation invariant 与 help
- Gate：code review `fix`
- 日期：2026-08-10
- Accepted-plan base：`0fe85869bffe214d6d8bc18d0e69690a493928d1`
- 裁决输入：`docs/gateflow/wu-cli-download-02-slice1-code-review-adjudication-20260810.md`
- Review inputs：
  - `docs/reviews/code-review-20260810-171054.md`
  - `docs/reviews/code-review-20260810-171152.md`
- Artifact path：`docs/gateflow/wu-cli-download-02-slice1-review-fix-20260810.md`
- Completion status：两个 accepted low findings 均已修复；本轮按用户 stop condition 停在 fix complete，不进入 re-review、accepted slice commit 或 Slice 2。

## 2. 目标、边界与第一性原理判断

两个 finding 的动机均成立：

1. 永久 AST test 断言的是 `BoolOp(And)` 源码形状，不是 public owner contract。合法重构会误报，而 request/effective-filter 行为矩阵、精确冲突诊断、非 bool 校验和 CLI 无副作用测试已经直接覆盖 owner 级契约。因此删除 AST test 比扩展 AST parser 更可维护，也不会降低业务行为覆盖。
2. `tests/cli/test_arg_parsing.py` 中 F12 外的全文件 Ruff 折叠只增加 review 噪声和 merge conflict 面，不提供行为价值。正确边界是逐 hunk 还原这些机械变更，只保留 help inventory 与互斥 help owner test。

语义 owner 仍是 `dayu.fins.download_contract._validate_download_mutation_mode(...)`。本 fix 不改变 owner、public contract、schema、状态机、CLI 行为或任何 production 实现；也不增加 fallback、兼容分支或第二个 validator。

本轮明确不做：Slice 2、Slice 3、production CLI evidence、README、Service/runtime/workflow/provider/storage 修改、commit、push 或 PR。

## 3. Finding 修复与 re-review 状态

### Finding 1：永久 AST owner test 与实现结构耦合

- 裁决：`accepted`
- Fix 状态：`已修复`
- 精确改动：
  - 从 `tests/service/test_fins_direct.py` 删除 `test_download_mutation_mode_conflict_has_one_production_owner`。
  - 删除只为该测试引入的 `ast` 和 `dayu.fins.download_contract as download_contract_module` imports。
  - 保留 request/effective-filter 合法矩阵、双 true 同一精确诊断、非 bool TypeError、两种 CLI 冲突 argv 顺序和副作用为零测试。
- 静态 gate 证据：`rg` 显示 production 中两个 mode 字段的 conjunction 仅剩 `dayu/fins/download_contract.py:79` 一处；该证据不再固化为永久测试。
- Re-review 状态：等待原 reviewer 独立 re-review；本 artifact 不冒充 re-review pass。

### Finding 2：`test_arg_parsing.py` 无关全文件格式化

- 裁决：`accepted`
- Fix 状态：`已修复`
- 精确改动：用 `apply_patch` 逐 hunk 还原 F12 外的函数签名、类型声明、集合推导、调用和 assert 折叠。
- 保留的真实 F12 diff 精确为：
  - `COMMAND_HELP_EXPECTATIONS["download"]` 新增 `--rebuild` inventory。
  - 新增 `test_download_help_explains_mutually_exclusive_mutation_modes`，断言两个 option 和各自的互斥 help 文案。
- `git diff <base> -- tests/cli/test_arg_parsing.py` 不再含其它 hunk。
- Re-review 状态：等待原 reviewer 独立 re-review；本 artifact 不冒充 re-review pass。

## 4. Changed files 与 production 不变性

本 fix 的代码 patch 只修改：

- `tests/service/test_fins_direct.py`
- `tests/cli/test_arg_parsing.py`

本 fix 新建：

- `docs/gateflow/wu-cli-download-02-slice1-review-fix-20260810.md`

未编辑 `dayu/cli/arg_parsing.py`、`dayu/fins/download_contract.py` 或其它 production 文件。相对 accepted-plan base 的 production diff 仍是 Slice 1 implementation/review 已审查的 F12 diff。

## 5. Validation

所有 Python 命令均在仓库根目录先执行 `source .venv/bin/activate`。

### 5.1 Affected tests

```text
pytest tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py
549 passed, 3 warnings in 5.10s
```

3 个 warning 均来自 `edgar` 依赖的既有 deprecation warning。

### 5.2 完整 focused owner union 与逐文件 coverage

```text
coverage erase
coverage run -m pytest \
  tests/service/test_fins_direct.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_output.py \
  tests/service/test_fins_wait_adapter.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_report_selection.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_fins_ingestion_runtime.py

1020 passed, 3 warnings in 13.34s
```

```text
coverage report --include='dayu/cli/arg_parsing.py,dayu/fins/download_contract.py'

dayu/cli/arg_parsing.py            342      2    99%
dayu/fins/download_contract.py     325     39    88%
TOTAL                              667     41    94%
```

两个 changed production files 均超过单文件 80% coverage gate。

### 5.3 Ruff、format、compileall 与 pyright

```text
ruff check <5 changed Python files>
All checks passed!

python -m compileall -q dayu/cli/arg_parsing.py dayu/fins/download_contract.py
PASS

pyright
0 errors, 0 warnings, 0 informations
```

对真实剩余 5 个 changed Python files 执行 `ruff format --check`：4 个文件通过，只有 `tests/cli/test_arg_parsing.py` 报告 `Would reformat`。继续执行 `ruff format --diff tests/cli/test_arg_parsing.py` 后确认：formatter 提议的全部 hunks 都是本 fix 刚按裁决还原的 F12 外既有 baseline 折叠；没有 hunk 触及新增 `--rebuild` inventory 或 `test_download_help_explains_mutually_exclusive_mutation_modes`。因此不重新全文件格式化，不重新引入同一 review finding。

### 5.4 Diff 与 owner guards

创建本 artifact 后执行最终 guard：

```text
git diff --check
PASS

git diff <base> -- tests/cli/test_arg_parsing.py
只含新增 --rebuild inventory 与互斥 help test 两个 hunks

rg "download_contract_module|\\bast\\b|test_download_mutation_mode_conflict_has_one_production_owner" \
  tests/service/test_fins_direct.py
无匹配（rg exit 1，符合预期）

rg "overwrite_existing and rebuild_local_artifacts|rebuild_local_artifacts and overwrite_existing" \
  dayu --glob '*.py'
dayu/fins/download_contract.py:79: if overwrite_existing and rebuild_local_artifacts:

git diff --name-only <base> -- README.md dayu/README.md dayu/cli/README.md \
  dayu/fins/README.md tests/README.md
无输出
```

相对 accepted-plan base 的 Python changed-files 集合仍精确为原 Slice 1 的 5 个 allowed files；没有 Slice 2、README 或其它 scope 文件进入代码 diff。worktree 另含本 work unit 的 implementation、review、adjudication 与本 fix artifacts，均未 commit。

## 6. Docs decision

- README：不更新。`tests/README.md` 的职责边界只要求在新增测试层级、测试运行方式或维护规则变化时同步；本 fix 只删除脆弱结构测试并还原格式噪声，没有改变这些事实。用户也明确禁止 README 修改。
- Gateflow artifact：新建本 fix artifact，记录 gate、finding 状态、validation、docs decision、residual risks 与 next entry point。
- 原 implementation artifact 是 review 前历史快照；其中 `1021 passed` 和 AST guard 描述由本 artifact 的 `1020 passed`、永久 AST test 已删除及静态 `rg` gate 证据取代，不回写历史 artifact。

## 7. Residual risks 与 uncovered areas

| Residual risk / uncovered area | 分类 | Owner / destination |
|---|---|---|
| 两个 accepted findings 尚需原 reviewer 独立确认 production diff 不变、fix 生效和验证证据有效。 | fixed in current slice（待 re-review gate 确认） | Slice 1 re-review；本轮按用户要求在 fix complete 后停止。 |
| detached clean worktree / installed CLI 下的真实 argv 与 help 尚未验证。 | covered by later approved slice | Accepted plan §9.2 的 CLI evidence gate；用户明确禁止本轮运行。 |
| README 尚未投影最终下载语义。 | covered by later approved slice | 后续 approved slice 行为稳定后的 docs decision；用户明确禁止本轮修改。 |
| F13/F14 尚未实现。 | covered by later approved slice | Slice 2 / Slice 3；本轮不得进入 Slice 2。 |

没有 unclassified residual risk，没有 blocking open question。

## 8. Completion signal 与 next entry point

Fix completion signal：两个 accepted low findings 已按裁决精确修复；production 未改变；行为测试、完整 focused union coverage、Ruff lint、compileall、pyright 和 formatter baseline 归因均已完成。

Next entry point：Slice 1 `re-review`，由原 reviewer 独立确认两个 finding 为 `已修复`。按用户明确 stop condition，本轮不进入 re-review、不创建 accepted Slice 1 commit、不进入 Slice 2。
