# WU-CLI-DOWNLOAD-01 Aggregate Format Closeout

## 1. Gate 与范围

- 日期：2026-08-10
- 精确基线 HEAD：`f0381f6aa366623590937e5667ddf7f535f7dd01`
- 分支：`codex/download-oracle`
- 工具：Python `3.11.15`，Ruff `0.15.11`（当前仓库 `.venv`）
- 性质：总控在 `f0381f6a` 后对全 WU 执行 `ruff format --check`，发现五个既有 WU 文件不合规，随后用当前 `.venv` Ruff 完成纯机械 format；本 closeout 只验证这些既有 formatter diff，不再修改产品或测试语义。
- 禁止项执行结果：未修改既有 artifact、Oracle、scenario registry 或历史 PR 190；未运行真实 CLI/provider；未 commit、push 或创建 PR。

本轮验证目标固定为：

- `dayu/cli/arg_parsing.py`
- `dayu/fins/pipelines/cn_form_utils.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_fins_direct.py`

验证开始与结束时，这五个文件的 diff 统计均为 `43 insertions / 116 deletions`，没有其它产品或测试文件进入工作树。

## 2. Unified diff 与语义等价裁决

完整读取：

```text
git diff -- dayu/cli/arg_parsing.py dayu/fins/pipelines/cn_form_utils.py dayu/fins/pipelines/sec_rebuild_workflow.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py
exit 0
```

人工逐 hunk 检查结果：变化只包含 Ruff 对相邻字符串、调用参数、tuple、generator expression、conditional expression、`cast` mapping 与 assertion 的括号/换行布局调整；没有 identifier、literal value、operator、调用顺序、参数名、控制流、docstring、注释或测试断言语义变化。

随后对每个文件分别读取 `git show HEAD:<path>` blob 与当前 working-tree bytes，使用：

```text
ast.parse(source, type_comments=True)
ast.dump(tree, include_attributes=False)
```

进行严格相等比较。结果：

```text
dayu/cli/arg_parsing.py: AST_EQUIVALENT=true
dayu/fins/pipelines/cn_form_utils.py: AST_EQUIVALENT=true
dayu/fins/pipelines/sec_rebuild_workflow.py: AST_EQUIVALENT=true
tests/fins/test_fins_ingestion_tools.py: AST_EQUIVALENT=true
tests/service/test_fins_direct.py: AST_EQUIVALENT=true
exit 0
```

裁决：五文件 unified diff 与 `f0381f6a` 的 Python AST 完全相同，属于 formatter-only layout closeout；没有产品或测试语义变更。

## 3. 验证记录

所有命令均在仓库根目录执行。

### 3.1 最小 owner / affected tests

```text
.venv/bin/pytest -q tests/cli/test_arg_parsing.py tests/fins/test_cn_download_workflow.py::test_cn_form_resolution_reuses_domain_alias_owner_for_defaults_and_tuple tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_rolls_back_once_and_reraises_cancellation_identity tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_operation_and_rollback_failure_preserve_primary_exception tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_ordinary_failure_with_successful_rollback_returns_failed_result tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_filter_contract tests/fins/test_sec_pipeline_download.py::test_sec_rebuild_state_preserves_published_fingerprint tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py
exit 0
566 passed, 3 warnings in 5.63s
```

覆盖关系：

- `test_arg_parsing.py` 覆盖 CLI parser owner；
- `test_cn_download_workflow.py` 的 form resolution owner 用例覆盖 `cn_form_utils` 的本 WU typed alias/default contract；
- 五个 SEC rebuild owner tests 覆盖 rebuild rollback identity、双失败 cause/note、普通失败、filter 与 fingerprint；
- 完整 `test_fins_ingestion_tools.py` 与 `test_fins_direct.py` 验证两个被格式化测试模块本身及对应 tools/service contract。

三条 warning 均来自已安装 `edgar` package 的 deprecation warning，不是本次 format 产生。

### 3.2 Changed-path pyright

```text
.venv/bin/pyright dayu/cli/arg_parsing.py dayu/fins/pipelines/cn_form_utils.py dayu/fins/pipelines/sec_rebuild_workflow.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py
exit 0
0 errors, 0 warnings, 0 informations
```

### 3.3 Ruff check

```text
.venv/bin/ruff check dayu/cli/arg_parsing.py dayu/fins/pipelines/cn_form_utils.py dayu/fins/pipelines/sec_rebuild_workflow.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py
exit 0
All checks passed!
```

### 3.4 Ruff format check

```text
.venv/bin/ruff format --check dayu/cli/arg_parsing.py dayu/fins/pipelines/cn_form_utils.py dayu/fins/pipelines/sec_rebuild_workflow.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py
exit 0
5 files already formatted
```

### 3.5 Compileall

```text
.venv/bin/python -m compileall -q dayu/cli/arg_parsing.py dayu/fins/pipelines/cn_form_utils.py dayu/fins/pipelines/sec_rebuild_workflow.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py
exit 0
```

### 3.6 Diff gates

```text
git diff --check
exit 0
```

最终工作树中的产品/测试 diff 仍严格只有上述五文件：

```text
dayu/cli/arg_parsing.py                     | 32 ++++-----------
dayu/fins/pipelines/cn_form_utils.py        | 16 ++------
dayu/fins/pipelines/sec_rebuild_workflow.py | 25 ++++++------
tests/fins/test_fins_ingestion_tools.py     | 60 +++++++----------------------
tests/service/test_fins_direct.py           | 26 +++----------
5 files changed, 43 insertions(+), 116 deletions(-)
```

## 4. Docs 与 residual risk

- README 不更新：formatter-only diff 不改变用户、package 或测试 contract。
- 既有 Gateflow/review artifacts 不更新；本文件是唯一新增 closeout artifact。
- 没有新增或未分类 residual risk。AST 等价检查不单独证明运行时依赖环境，但 owner/affected tests、pyright、Ruff、compileall 与 diff gate 已共同覆盖本次纯格式变更的合理风险。

## 5. Gate 结论

`f0381f6a` 后的五文件 formatter diff 已验证为 AST/语义等价，全部要求的验证通过。当前停止在原 MiMo/DS aggregate rereview 门；不 commit、push 或创建 PR。
