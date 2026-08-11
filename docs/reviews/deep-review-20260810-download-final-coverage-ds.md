# Deep Review Final Coverage — `dayu-cli download` Aggregate (WU-CLI-DOWNLOAD-01)

## Gate 状态

- **Reviewer**: AgentDS（独立 final coverage validation rereview）。
- **基线**: `bad90963abad48d29b5571d44a1cd9a80e0e2d77`（github/main）。
- **HEAD**: `d2c5f9a2bf28abb4c50bf87641e15bb4f39fa046`（codex/download-oracle）。
- **参照**: final coverage validation artifact（`docs/gateflow/wu-cli-download-01-final-coverage-validation-20260810.md`）。
- **Coverage 隔离**: 使用独立 `COVERAGE_FILE=/tmp/wu-download-ds.coverage`，避免与并发 MiMo 或其他 session 的默认 `.coverage` 数据覆盖。
- **日期**: 2026-08-10。
- **结论**: **PASS** — 0 findings。

---

## 1. Coverage 数据采集方法

```bash
export COVERAGE_FILE=/tmp/wu-download-ds.coverage
coverage erase

# base 21 + prompt/interactive/session — 共 24 个既有 test 文件
coverage run -m pytest -q \
  tests/cli/test_arg_parsing.py \
  tests/runtime/test_interruptible_process.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_output.py \
  tests/service/test_fins_direct.py \
  tests/service/test_fins_wait_adapter.py \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_sec_downloader.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_docling_process.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_docling_upload_service.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py \
  tests/cli/test_session_command.py
# → 1574 passed

# append CNINFO/HKEX downloader owner tests
coverage run --append -m pytest -q \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_hkexnews_downloader.py
# → 138 passed
```

**总 test executions: 1574 + 138 = 1712**，与验证 artifact §5 一致。

---

## 2. 工作树验证

```
git status --short → 仅 untracked artifacts，零 modified/staged 文件
git diff --stat HEAD -- '*.py' 'dayu/**/*.py' 'tests/**/*.py' → 空输出
git diff --exit-code HEAD -- tests/cli/test_output.py → exit 0
```

零产品/测试 diff。之前被撤销的 `test_output.py` 新增内容已完全移除。

---

## 3. Changed production files 枚举与 matrix 交叉验证

```text
git diff --name-only bad90963..HEAD -- 'dayu/**/*.py' 'dayu/*.py' → 35 files
```

独立 Python set comparison：coverage matrix 的 35 文件与 git diff 枚举的 35 文件**完美匹配**。无遗漏、无多余。

---

## 4. `output.py` coverage root cause 独立验证

**验证 artifact 陈述**: 21-file base matrix 遗漏了 `test_prompt_command.py`、`test_interactive_command.py`、`test_session_command.py`，导致 `output.py` 报告 71% 是因为这三个既有 owner test 文件未被执行，而非 download 覆盖率不足。

**独立验证**（isolated `COVERAGE_FILE`）:

```
dayu/cli/output.py  188 stmts, 17 miss, 91%
Missing: 89-90, 125-126, 209, 234, 371, 374, 406, 442, 465, 467, 482-483, 506, 521, 563
```

Missing lines 定位：
- `89-90` → prompt terminal renderer
- `125-126` → interactive terminal renderer
- `209, 371, 374, 406` → session list/purge/Host terminal renderer

确认 missing lines 分布在 prompt/interactive/session/Host 渲染函数中，不仅限于 Fins/download。三个共享 output owner 文件恰好覆盖这些分支。root cause 成立。

---

## 5. 独立逐文件 `--fail-under=80` gate

以下数据来自独立 `COVERAGE_FILE=/tmp/wu-download-ds.coverage`，对每个文件执行 `coverage report -m --fail-under=80 <file>`：

| File | Stmts | Miss | Cover | Gate |
|---|---:|---:|---:|---|
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

**TOTAL: 10195 stmts, 1153 miss, 89%**

**PER_FILE_GATE_COUNT=35, PER_FILE_GATE_FAILURES=0**

---

## 6. 与验证 artifact 的交叉核对

| 文件 | Artifact (stmts/miss/%) | 独立 (stmts/miss/%) | 匹配 |
|---|---|---|---|
| `filing_semantics.py` | 115/12/90% | 115/12/90% | ✓ |
| `direct_events.py` | 379/46/88% | 379/46/88% | ✓ |
| `download_contract.py` | 317/41/87% | 317/41/87% | ✓ |
| `cninfo_downloader.py` | 326/33/90% | 326/33/90% | ✓ |
| `hkexnews_downloader.py` | 457/68/85% | 457/68/85% | ✓ |
| `cn_docling_process.py` | 125/22/82% | 125/22/82% | ✓ |
| `source_integrity.py` | 75/9/88% | 75/9/88% | ✓ |
| `output.py` | 188/17/91% | 188/17/91% | ✓ |
| Aggregate | 10195/1153/89% | 10195/1153/89% | ✓ |

**所有 35 个文件 stmts/miss/cover 三重数值与验证 artifact 精确匹配，aggregate 完全一致。**

---

## 7. 无新增测试冒充闭环

```
git diff --exit-code HEAD -- tests/cli/test_output.py → exit 0
git diff --stat HEAD -- 'tests/**/*.py' → 空输出
```

零测试新增。全部 1712 个通过的 test executions 均来自既有 owner test 文件。没有新的测试函数、fixture 或 helper 被创建来人为提升覆盖率。

---

## 8. 结论

**PASS** — 0 findings。

| 检查项 | 独立结果 |
|---|---|
| 产品/测试 diff 为零 | CONFIRMED |
| 35 changed production files 完整枚举 | CONFIRMED — matrix 与 git diff 完美匹配 |
| `output.py` root cause | CONFIRMED — missing lines 包含 prompt/interactive/session，非 download 缺口 |
| 1712 test executions | CONFIRMED（1574 + 138） |
| 35/35 per-file `--fail-under=80` | CONFIRMED — 独立 `COVERAGE_FILE`，0 failures |
| 覆盖数值与 artifact 一致 | CONFIRMED — 35/35 stmts/miss/cover 精确匹配 |
| 无新增测试冒充闭环 | CONFIRMED — 零测试 diff |
| 无遗漏 changed production file | CONFIRMED — 35/35 完美匹配 |

所有数据基于独立 `COVERAGE_FILE=/tmp/wu-download-ds.coverage`，未与并发 session 共享默认 `.coverage`。
