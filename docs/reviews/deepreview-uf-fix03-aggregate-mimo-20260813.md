# UF-FIX03 aggregate deep review — AgentMiMo

## Review metadata

- Review type：aggregate final deep review
- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Slices：S1（publication-owned requested/stored count）、S2（typed failure + canonical label）、S3（CLI boundary + direct no-artifact + docs）
- Base：`662c9ad4`
- HEAD：`c54a4fd8`
- Reviewer：AgentMiMo
- Date：2026-08-13
- Constraint：严格只读；只新增本 artifact 文件

## 结论

**PASS** — 三个 frozen predicates 全部满足，S1–S3 contract 一致且无回归。一个 LOW 观察项不阻塞接受。

## 验证执行摘要

| 检查项 | 结果 |
| --- | --- |
| S1–S3 focused pytest | `473 passed, 3 warnings` ✓ |
| pyright | `0 errors, 0 warnings, 0 informations` ✓ |
| 八文件 coverage aggregate | 88% ✓ |
| frozen SHA-256 scenarios | `a357e5a1…` ✓ |
| frozen SHA-256 oracles | `88b04ca4…` ✓ |
| `git diff --check`（production/test） | 通过 ✓ |
| `uploaded_files` production 残留 | 零命中 ✓ |
| `UploadOperationResult` constructor | 恰 4 处，全在 `docling_upload_service.py` ✓ |
| `FinsUploadResultSummary` constructor | 恰 4 处 ✓ |
| `DoclingConversionCancelledError` in workflows | 零命中 ✓ |
| no-touch（Host/Engine/runtime/config/Service/storage/frozen） | 无改动 ✓ |
| UF-PF03 | 未执行（按约束） ✓ |

## Frozen predicate 核对

### P1：requested/stored 单一真源，non-ok zero，original-only

- `requested_file_count` 真源：`len(request.files)`，由 `_upload_summary_from_result()` 在 `service_runtime.py:308` 取得。
- `stored_file_count` 真源：`DoclingUploadService` 逐次 `store_file()` 对 provenance `original` 计数，由 `commit_prepared_upload_batch()` 成功返回后传入 `UploadOperationResult.stored_file_count`。
- `FinsUploadResultSummary.__post_init__()` 强制：`ok` 要求 `stored == requested >= 1`；`skipped` 要求 `requested >= 1, stored == 0`；其余 `stored == 0`。
- `FinsUploadPipelineResult.__post_init__()` 强制：`ok` 要求 `stored >= 1`；其余 `stored == 0`。
- `commit_batch()` 抛错时 terminal builder 固定 `stored_file_count=0`，不消费 staged count。
- durable summary 与 direct RESULT details 消费同一 `FinsUploadResultSummary`；progress 的 `file_count` 保持 requested 单位不变。

**判定：PASS。**

### P2：typed failure 唯一 owner 与五字段 exact contract

- `FinsUploadFailureReason` 是 frozen dataclass，恰五字段：`kind`、`code`、`message`、`retry_hint`、`file_label`。
- JSON parser `upload_failure_reason_from_json()` 要求 `frozenset(value) == {"kind","code","message","retry_hint","file_label"}`，exact key set。
- `__post_init__()` 调用 `validate_fins_public_file_label(file_label)` 确保 canonical。
- `file_label` 无 default、constructor 要求显式传入。
- Docling/OSError/runtime mapper 只按 typed exception 分类，显式接收 `file_label`，不从异常字符串重建。
- workflow、runtime、direct projection 只消费 typed reason，不重分类或 fallback。
- `canonicalize_fins_public_file_label()` 是唯一 label owner：普通 basename 原样保留；fragment/Cc/Cf/超长 投影固定隐藏标签；pathful/empty/dot 拒绝。
- `_admit_fins_upload_file_basename()` 在 filing static validation（`exists/is_file/suffix`）前调用 canonicalizer 做 shape admission，`ValueError` 转为 `INVALID_FILE_BASENAME` usage fact。

**判定：PASS。**

### P3：empty/corrupt/mixed 原子失败，SEC/CN 一致

- filing 空 bytes 在 converter 前抛 typed `empty_input_file`，`converter calls == 0`。
- corrupt PDF/DOCX 在当前文件边界 fail-fast 包装为 `FinsUploadFailureError`，保留 `__cause__`。
- valid+corrupt mixed：bad-first 不转换后续文件；valid-before-bad 只转换到首个 bad。batch begin/commit/rollback 均为 0，terminal stored 为 0。
- SEC workflow filing catch 在 Docling/OSError/generic 前穷尽 `FinsUploadFailureError`。
- CN/HK filing 与 SEC 同形直接投影 typed failure。
- CLI subprocess 真实 empty PDF、corrupt PDF、corrupt DOCX：stderr 含 canonical basename、closed kind/code、`requested_files="1"`、`stored_files="0"`、bounded reason、无绝对路径/traceback。fresh workspace 零 mutation。

**判定：PASS。**

## Correctness pass

### 跨切片 summary schema 一致性

S1 建立 `FinsUploadResultSummary` 的 requested/stored count contract。S2 只增加 `failure_reason` 字段，不修改 count 矩阵规则。S3 不修改 schema。三切片 schema 演进一致，无冲突。

`FinsUploadPipelineResult` → `FinsUploadResultSummary` 路径通过 `_upload_summary_from_result()` 单一汇合点贯通，`requested_file_count` 始终来自 `len(request.files)`，`stored_file_count` 始终来自 pipeline result。

### typed failure 唯一 owner 边界

`DoclingUploadService` 是 conversion failure 的 typed owner。SEC/CN workflow 只消费 `FinsUploadFailureError`，不重新构造。`_upload_result_details()` 只消费 typed reason 的字段，不做字符串重分类。

`DoclingConversionCancelledError` 在 `docling_upload_service.py:350` 被投影为 typed cancelled `UploadOperationResult`。SEC/CN workflow 中零命中——S1 review-fix 已删除不可达 catch。

### CLI typed terminal 投影

`_upload_result_details()` 固定前四项为 `source kind`、`status`、`requested files`、`stored files`。failure 时随后投影 `failure kind`、`failure code`、`file`（存在时）、`failure message`、`retry hint`、`document`。renderer 的 8 项上限截断 retry hint 和 document，但 canonical file 和 bounded message 在前 8 项内——满足 frozen `upload_filing.malformed-and-empty-input` predicate。

### CLI unknown 边界

- `run_fins_direct_command()` 的 generic `except Exception` 只在 known（`CliFinsUsageError`、`FinsUploadPrevalidationError`）与 typed terminal 之后。
- 固定 stderr：`命令执行失败，请使用 --log-file PATH 重试并查看日志`。
- `_LOGGER.exception(...)` 保持原实现，traceback 只进 operator log。
- 测试同步断言：stderr exact match、无 traceback/异常类型、caplog 含 marker + traceback。

### direct no-artifact 正控

`test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts`：
- 通过 production upload runner 发布 filing。
- 读回 source meta、original blob、derived Docling asset。
- 验证 `ingestion.job_store.root_dir`（typed `FsFinsIngestionJobStore`）下无 `.json`/`.jsonl`。
- 验证 `WorkspacePaths` 的 host_dir、host_sqlite_path、artifact_root、runtime_lanes_db_path 均不存在。

## Stability pass

### 五状态矩阵完整覆盖

Pipeline constructor + parser 接受：`ok/1`、`skipped/0`、`deleted/0`、`failed/0`、`cancelled/0`。
Pipeline constructor + parser 拒绝：`ok/0`、`skipped/1`、`deleted/1`、`failed/1`、`cancelled/1`。

Summary constructor 接受：`ok/2/2`、`skipped/2/0`、`deleted/0/0`、`cancelled/0/0`、`failed/0/0`。
Summary constructor 拒绝：`ok/0/0`、`ok/2/1`、`ok/1/2`、`skipped/0/0`、`skipped/1/1`、`deleted/0/1`、`cancelled/0/1`、`failed/0/1`。

CLI 四状态 renderer 集成：ok（stdout 含 requested/stored）、deleted（stdout）、skipped（stdout）、failed（stderr 含 failure reason）。全部断言 `uploaded_files` 不出现。

### 进度不变量

`_PAYLOAD_FILE_COUNT == "file_count"` 保持不变。progress `started`/`preparing`/`completed` 仍表达 requested progress unit。未新增 progress count 字段。

### fingerprint 不变量

fingerprint fixture digest 保持 `099dc963…`。provenance bytes/schema 未改。

## Maintainability pass

### 语义 ownership 清晰度

| 语义 | owner |
| --- | --- |
| `requested_file_count` | `len(request.files)` via `_upload_summary_from_result()` |
| `stored_file_count` | `DoclingUploadService` original store 计数 |
| summary status 矩阵 | `FinsUploadResultSummary.__post_init__()` |
| pipeline status 矩阵 | `FinsUploadPipelineResult.__post_init__()` |
| typed failure 五字段 | `FinsUploadFailureReason` constructor + `__post_init__()` |
| canonical file label | `canonicalize_fins_public_file_label()` |
| basename shape admission | `_admit_fins_upload_file_basename()` → canonicalizer |
| terminal detail ordering | `_upload_result_details()` |
| unknown stderr 文案 | `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE` |
| direct no-artifact | `test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts` |

无重复 owner、无 fallback、无兼容分支。

### cn_pipeline.py coverage

S3 八文件子集 coverage 为 69%，但该文件不是 S3 production diff。S2 broader changed-file run 已验证 94%（`1404 passed, 1 skipped, 1 deselected`）。修改文件覆盖率目标已满足。remaining missing 为既有未修改的 conversion-error/download/facade/helper 路径，归后续 CN pipeline 测试覆盖工作。

## Adversarial pass

### F1：summary 拒绝 delete/cancelled 时 requested > 0

`FinsUploadResultSummary.__post_init__()` 对 `deleted`/`cancelled`/`failed` 只强制 `stored_file_count == 0`，不强制 `requested_file_count == 0`。测试矩阵接受 `deleted/0/0` 但不测试 `deleted/1/0` 是否被拒绝。

直接代码证据：`service_runtime.py:131-137` 的 early-cancelled summary 构造 `requested_file_count=len(raw_request.files)`，对 delete 请求可能 > 0。pipeline 不返回 requested，所以 summary 的 requested 只能来自 request。

**严重度：LOW**。业务上 delete 请求 `files=()` 是 CLI 强制的，runtime 层不需重复防御。不阻塞接受。

### F2：POSIX 反斜杠 basename 降级

S2 review-fix 已在 `_validate_fins_upload_filing_static()` 的文件循环中，`exists/is_file/suffix` 前调用 `_admit_fins_upload_file_basename(basename)`。POSIX `a\b.pdf` 通过 `Path.name` 保留反斜杠，canonicalizer 的 `ValueError` 被转为 `INVALID_FILE_BASENAME` usage fact，不降级为 generic runtime。

**判定：已修复。**

### F3：测试是否只验证 fixture

- CLI content failure 测试使用真实 subprocess 调用 `dayu-cli upload_filing`，验证完整 stderr 输出。
- CLI renderer 测试通过 production `validate_fins_upload_filing_request()` 构造 typed request，调用 production `_direct_upload_terminal_events()` 和 `render_fins_direct_event()`。
- direct success 正控通过 production upload runner 发布并读回 Fins repositories。
- 不是 fixture-only 测试。

**判定：PASS。**

### F4：stderr/log 安全与 canonical label

- CLI content failure stderr 含 canonical basename（`file="{file_name}"`），无绝对路径、traceback 或异常 repr。
- unknown failure stderr 为固定文案，异常只进 `_LOGGER.exception()`。
- `_validate_safe_text()` 拒绝绝对路径、URL、job_id、内部标识和控制字符。
- `FinsUploadFailureReason.__post_init__()` 调用 `validate_fins_public_file_label()` 确保 label canonical。

**判定：PASS。**

### F5：direct 不创建 Host/Engine/runtime/legacy artifacts

正控测试验证 `jobs_dir` 下无 `.json`/`.jsonl`，`WorkspacePaths` 的 host_dir、sqlite、artifact_root、runtime_lanes 均不存在。executor operations 为空。

**判定：PASS。**

## README / pyright / coverage / no-touch / frozen SHA

全部通过，详见验证执行摘要表。

`git diff --check` 在 production/test 代码中通过；4 个 gateflow docs 有 trailing blank line，非 production 代码，不阻塞。

## 排除项

- UF-PF03 未执行（按用户约束）。
- material generic raw failure / company-first publication 未修改（归后续工作）。
- `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 既有 fixture 缺 `company_name`，归 upload tool contract/test owner。

## 最终判定

**PASS** — 三个 frozen predicates 全部满足，无 NEEDS_FIX finding。一个 LOW 观察项（summary 不强制 delete 的 `requested_file_count == 0`）不阻塞接受，归后续 runtime contract 加固。
