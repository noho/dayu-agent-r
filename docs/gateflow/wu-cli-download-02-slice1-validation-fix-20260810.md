# `WU-CLI-DOWNLOAD-02` Slice 1 post-re-review validation fix

## 1. Gate 状态

- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Slice：Slice 1 — F12 invocation invariant 与 help
- Gate：code review re-review 后总控 validation `fix`
- 日期：2026-08-10
- Accepted-plan base：`0fe85869bffe214d6d8bc18d0e69690a493928d1`
- 裁决输入：`docs/gateflow/wu-cli-download-02-slice1-code-review-adjudication-20260810.md` 的“Re-review 后总控 validation 裁决”
- 前序 fix：`docs/gateflow/wu-cli-download-02-slice1-review-fix-20260810.md`
- Re-review inputs：`docs/reviews/code-review-20260810-172003.md`、`docs/reviews/code-review-20260810-172154.md`、`docs/reviews/code-review-20260810-172307.md`
- Artifact path：`docs/gateflow/wu-cli-download-02-slice1-validation-fix-20260810.md`
- Completion status：validation finding 已修复；全部指定 validation 真实通过；按用户 stop condition 停在再次 re-review 前。

## 2. 第一性原理判断与语义 owner

本 fix 动机成立且严重性评估准确。用户冻结的是“全部实际 changed Python files 的 `ruff format --check` 必须真实 exit 0”，因此只把 `tests/cli/test_arg_parsing.py` 的失败归因为既有 baseline，不能关闭该 gate，也不能在完成报告中宣称通过。

正确最小路径是让不需要承担 F12 help owner coverage 的通用 parser inventory 文件完全回到 accepted-plan base，并把同一公开 help 行为断言放入已经属于 Slice 1 allowed files 的 Fins command 测试。这样 formatter gate 检查真实 changed-files 集合，行为覆盖不丢失，也不通过重新格式化整个 baseline 文件制造 review churn。

F12 mutation-mode invariant 的唯一生产语义 owner 仍是 `dayu.fins.download_contract._validate_download_mutation_mode(...)`。CLI help 只是该 contract 的用户可见投影；本 fix 不改变 production owner、public contract、schema、状态机、错误文本或副作用时序。

## 3. 精确变更与边界

本轮只用 `apply_patch` 修改两个测试文件：

1. `tests/cli/test_arg_parsing.py`
   - 删除 `COMMAND_HELP_EXPECTATIONS["download"]` 中 Slice 1 新增的 `--rebuild` inventory。
   - 删除 `test_download_help_explains_mutually_exclusive_mutation_modes`。
   - 相对 accepted-plan base 现为完全零 diff，并退出 changed-files 集合。
2. `tests/cli/test_fins_commands.py`
   - 新增同名 owner 行为测试，通过真实 `cli_main.main(("download", "--help"))` 断言 exit 0、两个 option、两条互斥说明和空 stderr。

本轮未修改 `dayu/cli/arg_parsing.py`、`dayu/fins/download_contract.py`、其它 tests、README 或既有 review artifacts。未运行 CLI evidence，未进入 Slice 2，未 commit、push 或创建 PR。

## 4. Validation

所有 Python 命令均在仓库根目录先执行 `source .venv/bin/activate`。

### 4.1 Affected tests

```text
pytest tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py
549 passed, 3 warnings in 5.18s
exit 0
```

3 个 warning 均来自 `edgar` 依赖的既有 deprecation warning。

### 4.2 完整 focused union 与 coverage

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
1020 passed, 3 warnings in 13.20s
exit 0
```

```text
coverage report --include='dayu/cli/arg_parsing.py,dayu/fins/download_contract.py'

dayu/cli/arg_parsing.py            342      2    99%
dayu/fins/download_contract.py     325     39    88%
TOTAL                              667     41    94%
exit 0
```

两个 changed production 文件的单文件 line coverage 均超过 80%。

### 4.3 Ruff、format、compileall 与 pyright

相对 accepted-plan base 的实际 changed Python files 精确为：

```text
dayu/cli/arg_parsing.py
dayu/fins/download_contract.py
tests/cli/test_fins_commands.py
tests/service/test_fins_direct.py
```

对上述 4 个文件执行：

```text
ruff check <4 files>
All checks passed!
exit 0

ruff format --check <4 files>
4 files already formatted
exit 0

python -m compileall -q <4 files>
exit 0

pyright
0 errors, 0 warnings, 0 informations
exit 0
```

Pyright 另输出可升级到新版本的工具提示，不是类型错误或 validation failure。

## 5. Diff 与静态 guards

最终 guard 结果：

- `git diff --check`：exit 0。
- `git diff --exit-code <base> -- tests/cli/test_arg_parsing.py`：exit 0、无输出，证明该文件完全回到 accepted-plan base。
- `git diff --name-only <base> -- '*.py'`：只列出上述 4 个 Slice 1 allowed files。
- help test 名和两条互斥文案只在 `tests/cli/test_fins_commands.py` 命中；`tests/cli/test_arg_parsing.py` 无命中。
- production mode conjunction 只命中 `dayu/fins/download_contract.py:79` 的唯一 owner helper。
- 已删除的 `download_contract_module` / `test_download_mutation_mode_conflict_has_one_production_owner` 在 `tests/service/test_fins_direct.py` 无命中；`rg` 预期 exit 1。
- `git diff --exit-code <base> -- README.md dayu/README.md dayu/cli/README.md dayu/fins/README.md tests/README.md`：exit 0。

## 6. Docs decision

- README：不更新。`tests/README.md` 只记录测试分层、运行方式与维护约定，并要求新增测试层级时同步；本轮仅迁移同一 help owner 断言，没有改变这些事实。用户也明确禁止 README 修改。
- Gateflow：新建本 artifact，持久记录 re-review 后总控 validation fix、真实 validation 结果、scope 与 residual risk。
- 既有 adjudication/review/fix artifacts 是各 gate 的历史快照，不回写。

## 7. Finding 与 residual risks

| Finding / residual risk | 状态 / 分类 | Owner / destination |
|---|---|---|
| `test_arg_parsing.py` 留在 changed-files 集合导致 formatter gate 失败 | `已修复`；fixed in current slice | 本 artifact 的零 diff、changed-files、Ruff format exit 0 证据 |
| 两路原 reviewer 尚未对本次 validation fix 再次独立确认 | fixed in current slice（待 re-review gate 确认） | Slice 1 再次 re-review；本轮按用户要求在其前停止 |
| detached clean worktree / installed CLI evidence 未执行 | covered by later approved slice | Accepted plan §9.2 CLI evidence gate；用户明确禁止本轮运行 |
| F13/F14 尚未实现 | covered by later approved slice | Slice 2 / Slice 3；本轮不得进入 Slice 2 |
| README 最终用户语义投影尚未处理 | covered by later approved slice | 后续 approved docs gate；用户明确禁止本轮修改 |

没有 unclassified residual risk，没有 blocking open question。

## 8. Completion signal 与 next entry point

Completion signal 已满足：`test_arg_parsing.py` 完全回到 accepted-plan base并退出 diff；download help 的两个 option 和互斥文案覆盖已迁移；production 与其它 tests 未变；affected tests、完整 focused union coverage、全部实际 changed Python files 的 Ruff lint/format、compileall、全量 pyright、diff/rg guards 均真实通过。

Next entry point：Slice 1 再次 `re-review`，由原 reviewer确认 validation finding 为 `已修复`。按用户明确 stop condition，本轮不进入 re-review、不创建 accepted Slice 1 commit、不进入 Slice 2。
