# UF-FIX03 S2 review-fix

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Slice：`UF-FIX03-S2`
- Gate：`code review -> fix`
- Baseline HEAD：`607bfa4f07f5734553a2c90b13183324caff2ba9`
- Input adjudication：`docs/gateflow/uf-fix03-s2-code-review-adjudication-20260813.md`
- Accepted finding：`F1 — POSIX 反斜杠 basename 导致 known content failure 降级`
- Decision：**PASS — F1 FIX ACCEPTED BY DUAL RE-REVIEW**
- Next entry point：`S2 accepted slice commit`
- Commit：未创建；Gateflow 要求先完成双路 re-review，再进入 accepted slice commit。
- Artifact path：`docs/gateflow/uf-fix03-s2-review-fix-20260813.md`

## Scope and owner decision

F1 root cause 与触发数据同源：filing static request validation 原先只检查 `exists/is_file/suffix`；POSIX `Path.name` 可保留反斜杠，
使 pathful basename 到达 content producer。producer 随后调用唯一 canonicalizer 时抛出 `ValueError`，因此已判定的 empty/corrupt
content failure 未能形成 `FinsUploadFailureError`，最终进入 generic runtime mapper。

修复严格落在裁决指定 owner boundary：`dayu.fins.ingestion_runtime` 的 filing static validation 调用
`canonicalize_fins_public_file_label(...)` 做 basename shape admission，并只把该 owner 的 shape rejection 转成独立 closed usage fact。
canonicalizer 继续唯一拥有 empty/dot/pathful、fragment、Unicode control/format 与长度规则；content producer、content failure mapper 与
failure label projection 均未增加 fallback、catch 或重复规则。

## Changed files

- `dayu/fins/ingestion_runtime.py`
  - 新增 `FinsUploadUsageCode.INVALID_FILE_BASENAME = "invalid_file_basename"`。
  - 新增固定 message `上传文件名无效；请提供单个非空文件名`；不接收或格式化 raw basename，且不加入 `_FILE_USAGE_CODES`。
  - 新增 `_admit_fins_upload_file_basename(...)`，只调用 canonicalizer 并把 `ValueError` 转成上述 typed usage failure。
  - `_validate_fins_upload_filing_static(...)` 在 `exists/is_file/suffix` 前执行 admission。
- `tests/fins/test_fins_ingestion_runtime.py`
  - 扩充 usage code/message closed mapping，并断言新 code 是不接受 `file_name` 的 usage fact。
  - 新增 POSIX 真实反斜杠 basename / Windows 等价 owner fixture，断言 exact typed code/message、无 raw basename、filesystem probe 不可达。
  - 新增普通英文、普通中文、fragment、`Cc`、`Cf`、合法超长 basename admission 与既有 failure label contract 回归。
- `docs/gateflow/uf-fix03-s2-implementation-20260813.md`
  - 回写 F1 root cause、review-fix delta、验证与下一 gate。
- `docs/gateflow/uf-fix03-s2-review-fix-20260813.md`
  - 记录本 fix gate 的 durable evidence。

## Finding status

- F1：实现状态 **已修复**；AgentMiMo 与 AgentDS re-review 均为 **PASS**。
- 其它两份 S2 review 结论：裁决已接受为通过，本轮未扩展或重开 finding。

## Validation

- 新增 owner tests：`8 passed, 221 deselected`。
- S2 focused：`325 passed`，3 个第三方 deprecation warnings。
- S1 regression：`334 passed`，3 个第三方 deprecation warnings。
- changed-file coverage：`1404 passed, 1 skipped, 1 deselected`；
  `direct_events.py 87%`、`ingestion_runtime.py 91%`、`cn_pipeline.py 94%`、`docling_upload_service.py 88%`、
  `sec_upload_workflow.py 93%`、`upload_failure.py 96%`，总计 `91%`。
- 完整 pyright：`python -m pyright dayu/ tests/ utils/` -> `0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- old-field audit：`uploaded_files` 在 `dayu/`、`tests/` Python 文件中零命中。
- production `FinsUploadResultSummary(...)` constructor audit：仍为 accepted S1 的四个构造点。
- HEAD：仍为 `607bfa4f07f5734553a2c90b13183324caff2ba9`，未 commit。

## Documentation and no-touch decision

- README 同步按 accepted plan 归 S3；本 fix 不提前写未来状态。
- 未修改 `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/config/**`、`dayu/ui/**`、Service production、
  `dayu/fins/storage/**`、frozen JSON/evidence 或 UF-PF03 artifact。
- 未修改 `_build_original_assets` / `_build_pending_assets`，未增加 content producer fallback，未改变 material generic failure。
- 未执行 UF-PF03，未进入 S3。
- `docs/cli_ci_scenarios.json` SHA-256：
  `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`。
- `docs/cli_ci_oracles.json` SHA-256：
  `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。

## Residual risks and uncovered areas

- F1 pathful basename 降级：**fixed in current slice**；由 static typed rejection 与 filesystem-probe guard 覆盖。
- 真实 Docling 多平台 subtype/text：**assigned to later work unit**（UF-PF03）；本轮未执行。
- CLI generic catch、真实 CLI stderr 与 direct no-artifact positive control：**covered by later approved slice**（S3）；本轮未进入。
- material generic raw failure/company-first publication：**assigned to later work unit**（Fins material workflow）；本轮 no-touch。
- out-of-scope upload-tool fixture baseline failure：**assigned to later work unit**（upload tool/prevalidation test owner）；coverage 精确 deselect。

没有未分类 residual risk，没有 blocking open question。当前 fix 已通过双路 S2 re-review；下一入口为 accepted slice commit。
