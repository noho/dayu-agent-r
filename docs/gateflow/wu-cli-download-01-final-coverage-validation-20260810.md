# WU-CLI-DOWNLOAD-01 Final Coverage Validation

## 1. Gate、基线与最终裁决

- 日期：2026-08-10
- 精确 HEAD：`d2c5f9a2bf28abb4c50bf87641e15bb4f39fa046`
- 分支：`codex/download-oracle`
- 性质：final coverage root-cause validation；不修改 production 或 tests。
- 禁止项：未修改 Oracle/registry、既有 artifact 或 PR 190；未运行真实 CLI/provider；未 commit、push 或创建 PR。

最终 root-cause 裁决：`dayu/cli/output.py=71%` 不是 owner test 缺口，而是 base plan §9 的 21-file coverage matrix遗漏了该共享 renderer 已存在的 prompt、interactive 与 session owner tests。`output.py` 同时拥有 Host terminal、session list/purge 与 Fins direct 的公开展示职责；只执行 Fins/下载 matrix 不能代表整文件 owner coverage。

## 2. 初始证据

精确 HEAD 的既有 21-file affected union：

```text
1389 passed
dayu/cli/output.py: 188 statements, 55 missing, 71%
```

初始 missing lines 同时包含：

- prompt/interactive success、failure、lost 映射；
- session list/purge 及其公开 DTO 投影；
- typed download failure/missing-period 等分支。

因此不能只凭 71% 推断 download/Fins owner tests缺失。coverage collection本身没有执行 `tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py` 与 `tests/cli/test_session_command.py`，这是同源 root cause。

## 3. 本轮测试试改的完整撤销

在总控给出既有 owner matrix 证据后，本轮已完整撤销此前对 `tests/cli/test_output.py` 的全部新增内容，包括：

- bounded rows / missing periods / document reasons 测试；
- closed failure transport `None` / 非 `None` 测试；
- prompt/interactive public-status 测试；
- `_download_result_event`、`_terminal_result` helper及专用 imports。

精确验证：

```text
git diff --exit-code HEAD -- tests/cli/test_output.py
exit 0
```

错误命名且未完成的 `docs/gateflow/wu-cli-download-01-final-coverage-fix-20260810.md` 已在本轮交付前删除，没有作为 artifact 保留。

最终没有任何 product/test diff。没有为了数字复制已有 progress coverage、伪造非法 public DTO、直接调用私有 renderer helper，或把本 WU 之外的历史 renderer contract重新写一遍。

## 4. Canonical 既有 owner test matrix

无 `-k` 排除，运行五个现有 owner test 文件：

```text
.venv/bin/coverage erase
.venv/bin/coverage run -m pytest -q \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py \
  tests/cli/test_session_command.py
```

结果：

```text
239 passed, 3 warnings in 9.45s
exit 0
```

逐文件 gate：

```text
.venv/bin/coverage report -m --fail-under=80 dayu/cli/output.py
exit 0

dayu/cli/output.py
188 statements, 17 missing, 91%
Missing: 89-90, 125-126, 209, 234, 371, 374, 406, 442, 465,
467, 482-483, 506, 521, 563
```

三条 warning 均来自已安装 `edgar` package 的 deprecation warning，不是产品或测试 failure。

结论：现有 owner tests 在零代码/测试变更下已经使 `output.py` 达到 91%，独立 `--fail-under=80` PASS。应修正 coverage matrix，而不是制造新的 WU 外测试。

## 5. 完整全 WU owner coverage matrix

为同时保留 base plan §9 的 download affected union，并正确测量共享 output owner，本轮在原 21-file matrix 上仅加入三个既有测试文件：

- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`

未新增或修改任何测试。expanded matrix 结果：

```text
1574 passed, 3 warnings in 58.51s
exit 0
```

同一 coverage data 中：

```text
dayu/cli/output.py: 188 statements, 17 missing, 91%
--fail-under=80: exit 0
```

首次逐文件枚举发现 CNINFO/HKEX downloader 数值偏低后，总控补充直接证据：expanded matrix 仍遗漏两个既有 downloader owner test 文件。没有新增测试，而是在上述同一 coverage data 上 append：

```text
.venv/bin/coverage run --append -m pytest -q \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_hkexnews_downloader.py

138 passed in 0.31s
exit 0
```

因此最终完整 matrix 由以下既有 tests 组成：

1. base plan §9 的 21-file affected union；
2. prompt / interactive / session 三个共享 output owner 文件；
3. CNINFO / HKEX 两个 downloader owner 文件。

coverage data 共包含 `1574 + 138 = 1712` 个通过的 test executions；两个命令均 exit 0。首次未 append downloader owner tests 时出现的低值只是中间态 matrix omission，不是最终 coverage gap。

## 6. 全 WU changed production files 枚举

production 范围由以下只读命令从 baseline 到当前 HEAD直接枚举：

```text
git diff --name-only bad90963abad48d29b5571d44a1cd9a80e0e2d77..HEAD -- 'dayu/**/*.py' 'dayu/*.py'
```

完整 matrix 的逐文件结果：

| Production file | Statements | Miss | Coverage | 判定 |
| --- | ---: | ---: | ---: | --- |
| `dayu/cli/arg_parsing.py` | 342 | 1 | 99% | PASS |
| `dayu/cli/commands/fins.py` | 448 | 66 | 85% | PASS |
| `dayu/cli/output.py` | 188 | 17 | 91% | PASS |
| `dayu/fins/direct_events.py` | 379 | 46 | 88% | PASS |
| `dayu/fins/domain/filing_semantics.py` | 115 | 12 | 90% | PASS |
| `dayu/fins/download_contract.py` | 317 | 41 | 87% | PASS |
| `dayu/fins/downloaders/cninfo_downloader.py` | 326 | 33 | 90% | PASS |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 457 | 68 | 85% | PASS |
| `dayu/fins/downloaders/sec_downloader.py` | 923 | 78 | 92% | PASS |
| `dayu/fins/ingestion/observation_handle.py` | 127 | 8 | 94% | PASS |
| `dayu/fins/ingestion_runtime.py` | 1760 | 173 | 90% | PASS |
| `dayu/fins/pipelines/cn_docling_process.py` | 125 | 22 | 82% | PASS |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 197 | 28 | 86% | PASS |
| `dayu/fins/pipelines/cn_download_protocols.py` | 40 | 0 | 100% | PASS |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 152 | 26 | 83% | PASS |
| `dayu/fins/pipelines/cn_download_workflow.py` | 240 | 16 | 93% | PASS |
| `dayu/fins/pipelines/cn_form_utils.py` | 114 | 21 | 82% | PASS |
| `dayu/fins/pipelines/cn_pipeline.py` | 381 | 41 | 89% | PASS |
| `dayu/fins/pipelines/download_events.py` | 25 | 0 | 100% | PASS |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 187 | 30 | 84% | PASS |
| `dayu/fins/pipelines/sec_download_persistence.py` | 125 | 23 | 82% | PASS |
| `dayu/fins/pipelines/sec_download_source_upsert.py` | 39 | 1 | 97% | PASS |
| `dayu/fins/pipelines/sec_download_workflow.py` | 234 | 26 | 89% | PASS |
| `dayu/fins/pipelines/sec_pipeline.py` | 455 | 66 | 85% | PASS |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 129 | 13 | 90% | PASS |
| `dayu/fins/pipelines/sec_sc13_filtering.py` | 257 | 45 | 82% | PASS |
| `dayu/fins/storage/__init__.py` | 11 | 0 | 100% | PASS |
| `dayu/fins/storage/_fs_source_document_core.py` | 491 | 81 | 84% | PASS |
| `dayu/fins/storage/_fs_storage_infra.py` | 1041 | 137 | 87% | PASS |
| `dayu/fins/storage/fs_source_document_repository.py` | 86 | 3 | 97% | PASS |
| `dayu/fins/storage/repository_protocols.py` | 102 | 0 | 100% | PASS |
| `dayu/fins/storage/source_integrity.py` | 75 | 9 | 88% | PASS |
| `dayu/fins/tools/download_tools.py` | 50 | 5 | 90% | PASS |
| `dayu/service/fins_direct.py` | 62 | 6 | 90% | PASS |
| `dayu/service/fins_wait_adapter.py` | 195 | 11 | 94% | PASS |

总计：

```text
10195 statements, 1153 missing, 89%
```

随后对35个 production 文件分别执行：

```text
.venv/bin/coverage report --fail-under=80 <exact-production-file>
```

结果：`PER_FILE_GATE_COUNT=35`、`PER_FILE_GATE_FAILURES=0`。35/35 个 changed production files全部达到 `>=80%`，没有用 aggregate 89% 掩盖单文件结果。

## 7. 工作树与静态检查

恢复测试后、写本 artifact 前：

```text
git status --short
<empty>

git diff --exit-code HEAD -- tests/cli/test_output.py
exit 0

git diff --check
exit 0
```

最终工作树只允许本 validation artifact。由于 product/test Python diff 为零，changed-path pyright、Ruff、format 与 compileall没有适用的 changed Python target；本轮不重复运行它们，也不把历史结果冒充本次验证。

README 不更新：没有产品、测试或用户可见 contract 变化。

## 8. Gate 结论

- `output.py` coverage root cause 已验证并更正：21-file matrix遗漏既有 owner tests。
- 零产品/测试改动下，canonical 五文件 owner matrix为 239 passed，`output.py=91%`，逐文件 gate PASS。
- 完整 WU matrix由21-file base union、三个共享 output owner文件与两个 downloader owner文件组成；coverage data累计1712个通过的 test executions。
- `cninfo_downloader.py=90%`、`hkexnews_downloader.py=85%`；二者此前的低值已证明同样来自 matrix omission，不是最终 gap。
- 35/35 个 changed production files独立 `--fail-under=80` gate全部 PASS；完整 matrix总计89%。
- 没有未分类 coverage residual，也没有通过新增测试或产品改动制造 PASS。

当前停止在 MiMo/DS 双路 rereview 入口；不 commit、push 或创建 PR。
