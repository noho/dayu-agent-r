# UF-FIX03 S3 code-review fix

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Gate：`code review -> fix`
- Baseline：`a65cec936876260fd10f47f9156e8d6a33da494e`
- Branch：`codex/upload-filing-oracle`
- Input artifacts：
  - `docs/reviews/deepreview-uf-fix03-s3-20260813.md`
  - `docs/reviews/deepreview-uf-fix03-s3-agentds-20260813.md`
- Artifact path：`docs/gateflow/uf-fix03-s3-review-fix-20260813.md`
- Completion status：controller 裁决的三项 `NEEDS_FIX` 已实现并验证；AgentMiMo/AgentDS 双路 re-review 均为 `PASS`。
- Next Gateflow entry：`accepted slice commit`。

## Scope and controller adjudication

Controller 对两份 review 的结论裁决为三项均 `accepted / NEEDS_FIX`：

| ID | Controller finding | Owner adjudication | Fix status |
| --- | --- | --- | --- |
| F1 | empty/corrupt 普通 stderr 缺 canonical 文件名 | `dayu/fins/ingestion_runtime.py::_upload_result_details(...)` 是 typed terminal projection owner；通用 renderer no-touch | 已修复 |
| F2 | unknown 固定文案在默认匿名日志下不可行动 | `dayu/cli/commands/fins.py::run_fins_direct_command(...)` generic public boundary | 已修复 |
| F3 | 缺 success/delete/skip/failure requested/stored CLI owner/integration 测试 | production `FinsUploadResultSummary -> typed terminal projection -> existing renderer` 是唯一测试链 | 已修复 |

第一份 review 将 F1 降为 LOW residual，但 frozen oracle 与真实 CLI 路径证明该项违反当前 work unit 的公开 predicate，因此不接受 deferral。第二份 review 的三项 findings 与 controller 裁决一致。

## Fixes

### F1 — canonical file 与 bounded reason 必须进入 renderer 前 8 项

- `_upload_result_details(...)` 现在按以下优先级产生 details：
  1. `source kind`
  2. `status`
  3. `requested files`
  4. `stored files`
  5. `failure kind`
  6. `failure code`
  7. `file`（存在时）
  8. `failure message`
  9. `retry hint`（存在时）
  10. `document`（存在时）
- reason/code/count/file 均直接消费同一个 typed summary/reason；没有在 CLI renderer 重分类、拼接 reason 或保留 Fins 特例。
- owner test 同时断言完整顺序与 cap=8 前缀。
- 真实 CLI subprocess test 覆盖 `empty.pdf`、`corrupt.pdf`、`corrupt.docx`，逐项断言 exact canonical basename、closed kind/code、requested/stored 和有界原因。

### F2 — unknown 文案自足可行动

- 固定 stderr 更新为 `dayu-cli <command>: 命令执行失败，请使用 --log-file PATH 重试并查看日志`。
- `_LOGGER.exception(...)` 保持原实现，private marker、异常类型和 traceback 仍只进入 operator log。
- stream unknown 与直接注入 unknown 的 exact stderr tests 同步；root README 说明 `PATH` 应为可写文件并需重新执行命令。

### F3 — upload_filing 四状态真实 typed projection

- 参数化覆盖 `ok/delete/skipped/failed` 对应的 success/delete/skip/failure CLI 展示。
- 每个 fixture 先构造 `FinsUploadResultSummary`，再使用 `FinsUploadFilingRequest` / `SourceKind.FILING` 和 public `validate_fins_upload_filing_request(...)` 取得 typed request。
- 测试调用 `ingestion_runtime` 同模块唯一 `_direct_upload_terminal_events(...)` owner，将 production summary 投影为真实 `FinsResultSummary.details`，再调用既有 `render_fins_direct_event(...)`。
- 私有 terminal helper 要求 execution context，因此测试只构造最小同模块 context，并以实现 `FinsJobCancellationChecker` 的 never-cancelled protocol double 填入无关取消字段；没有复制 validation、company-meta、status、error 或 count 逻辑。
- delete request 使用 `files=()` 且 requested summary=`0`；其它状态只在 `tmp_path` 写 validator 所需的安全输入，不产生 workspace/业务 publication 副作用。
- 每个状态断言正确 stdout/stderr、`requested_files`、`stored_files`，并断言 `uploaded_files` 不出现。

### Controller 补充检查

- S3 direct success no-artifact test 不再硬编码 job directory；先把 `ingestion.job_store` 收窄为 typed `FsFinsIngestionJobStore`，再使用其 `root_dir`。
- 误触的较早 direct download 既有测试已恢复原样；只有 `test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts` 使用 typed `root_dir`。
- material fixture 已完全移除，不能替代 frozen `upload_filing` predicate。

## Changed files in this fix

- `dayu/fins/ingestion_runtime.py`
- `dayu/cli/commands/fins.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/cli/test_fins_commands.py`
- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/gateflow/uf-fix03-s3-implementation-20260813.md`
- `docs/gateflow/uf-fix03-s3-review-fix-20260813.md`

`tests/service/test_fins_direct.py` 是 S3 原 implementation 改动，本 fix 未进一步修改其语义。两份 input review artifacts 保持只读。

## Validation

- Tests-first：旧 production 下新增 owner/unknown assertions 为 `3 failed, 4 passed`，失败与 F1/F2 根因完全同源。
- S3 focused：`368 passed, 3 warnings`。
- S1–S3 focused：`473 passed, 3 warnings`。
- coverage：同一八文件 `473 passed, 3 warnings`；total `88%`；`commands/fins.py 86%`、`ingestion_runtime.py 91%`。
- final fixture simplification targeted：四状态 test `4 passed, 3 warnings`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：pass。
- frozen SHA：
  - scenarios：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - oracles：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`
- no-touch：Host/Engine/runtime/config/Service production/storage/frozen JSON/evidence 无相对基线改动。
- 明确未执行 UF-PF03、未启动内部 agents、未 commit、未 push；re-review 仅由 controller 指派的 AgentMiMo/AgentDS 执行。

## Finding status

| ID | Final fix status | Evidence |
| --- | --- | --- |
| F1 | 已修复 | owner detail prefix/order test + real CLI empty/PDF/DOCX canonical file/reason tests |
| F2 | 已修复 | exact fixed stderr + caplog traceback + root README |
| F3 | 已修复 | filing typed summary -> terminal owner -> renderer 四状态 test |

## Residual risks and uncovered areas

- `cn_pipeline.py` 在 S3 八文件子集 coverage 中为 `69%`，但其修改切片 S2 的 broader changed-file coverage 已为 `94%`；修改文件覆盖率目标已满足，不构成 residual risk。
- upload tool 既有 fixture 缺 fresh create `company_name`：`assigned to later work unit`，owner 为 upload tool contract/test；本 fix 不增加兼容分支。
- 真实 Docling 多平台 variance：`assigned to later work unit` UF-PF03；本轮按要求未执行。
- 当前没有未分类 residual risk。

## Gate decision

Fix gate 完成，三项 accepted findings 均标记为`已修复`。AgentMiMo 与 AgentDS 定向 re-review 均为 `PASS`，artifact 分别为 `docs/reviews/deepreview-uf-fix03-s3-rereview-mimo-20260813.md` 与 `docs/reviews/deepreview-uf-fix03-s3-rereview-agentds-20260813.md`。下一入口为 accepted slice commit。
