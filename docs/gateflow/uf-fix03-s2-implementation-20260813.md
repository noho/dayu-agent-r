# UF-FIX03 S2 Implementation

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Slice：`UF-FIX03-S2`
- Gate：`implementation -> code review -> review-fix`
- Baseline HEAD：`607bfa4f07f5734553a2c90b13183324caff2ba9`
- Decision：**PASS — S2 ACCEPTED AFTER DUAL RE-REVIEW**
- Next entry point：`S2 accepted slice commit`
- Commit：未创建；Gateflow 要求先完成 code review/re-review，再进入 accepted slice commit。
- Artifact path：`docs/gateflow/uf-fix03-s2-implementation-20260813.md`

## Scope and first-principles decision

直接代码证据确认问题成立：`DoclingUploadService._build_original_assets(...)` 原先接受空 bytes；逐文件
`_build_pending_assets(...)` 持有当前唯一 `file_path.name`；SEC 与 CN/HK filing workflow 均在
`prepare_upload(...)` 完成后才调用 `begin_batch(...)`。因此修复放在内容读取/转换 owner 与 typed failure owner，复用既有
prepare-before-publication 顺序，不新增事务、补偿、目录扫描或下游字符串分类。

本 slice 只实现 filing 的 pre-publication content admission、closed typed failure、canonical public display label 与 direct typed
projection。material generic failure/company-first publication、CLI generic catch、direct no-artifact、README 与 UF-PF03 均未进入。

S2 code review 裁决确认 F1 成立：POSIX 可存在 `a\\b.pdf` 单文件名，原 static validation 未调用 basename shape owner，导致后续
canonicalizer 的 `ValueError` 绕过 `FinsUploadFailureError` 并降级为 generic runtime。review-fix 只在 filing static request boundary
复用 canonicalizer 做 shape admission；不修改 content producer、failure mapper 或 canonicalizer 规则。

## Changed files

### Production

- `dayu/fins/direct_events.py`
  - 新增唯一 `canonicalize_fins_public_file_label(...)` / `validate_fins_public_file_label(...)` owner。
  - 普通 basename 原样保留；命中既有 fragment/public guard、Unicode `Cc/Cf` 或长度超过 240 时投影固定标签
    `输入文件（文件名已隐藏）`；pathful、空与 dot-segment 输入拒绝。
  - 未修改 `FinsEventDetail` 通用 safe-text 接受集。
- `dayu/fins/upload_failure.py`
  - `FinsUploadFailureReason` 改为 exact five-field contract，新增 required nullable `file_label`，`__post_init__()` 调用唯一 label
    validator。
  - 新增 `empty_input_file` content code、固定 message/retry hint、empty factory 与只携带已校验 reason 的
    `FinsUploadFailureError`。
  - Docling/OSError/runtime mapper 只按 typed exception 分类并显式接收 canonical label 或 `None`；parser 只 exact-read 五字段并调用
    constructor。
- `dayu/fins/pipelines/docling_upload_service.py`
  - `prepare_upload(...)` 显式把 `source_kind` 传到 original read 与逐文件 conversion owner。
  - filing 空 bytes 在 converter 前抛 typed `empty_input_file`；material 行为保持不变。
  - filing `DoclingConversionError` 在当前文件边界 fail-fast 包装，保留 `__cause__`；raw basename 用 `%r` 只写 operator log。
- `dayu/fins/pipelines/sec_upload_workflow.py`
  - filing 在 Docling/OSError/generic catch 前穷尽 `FinsUploadFailureError`，直接投影 `exc.failure`。
- `dayu/fins/pipelines/cn_pipeline.py`
  - CN/HK filing 与 SEC 同形直接投影 typed failure；material catch 未修改。
- `dayu/fins/ingestion_runtime.py`
  - filing static validation 在 `exists/is_file/suffix` 前调用 `canonicalize_fins_public_file_label(...)` 的唯一 shape contract；只把其
    `ValueError` 转成 closed `invalid_file_basename` usage fact。
  - `invalid_file_basename` 使用固定、有界、不含 raw basename 的文案，且不属于需要 `file_name` 的 `_FILE_USAGE_CODES`。
  - existing owner factory 调用显式传 `file_label=None`。
  - direct RESULT details 从 typed reason 机械投影 retry hint 与 canonical file label；未增加 fragment/control/长度分支或 fallback。

### Tests

- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_fins_ingestion_runtime.py`

review-fix 新增 cross-platform owner tests：POSIX 使用真实 `a\\b.pdf` 文件；Windows 使用等价 `Path.name` owner fixture，不 skip；两者都
断言 exact typed code/message 且 filesystem probe 不可达。普通英文、普通中文、fragment、Unicode `Cc`、Unicode `Cf` 与合法超长
basename 均通过 static admission，并保持既有 failure label projection。

测试先行红灯证据：首次运行 owner-focused tests 在 collection 阶段因
`canonicalize_fins_public_file_label` 尚不存在而失败；完成 owner 实现后转绿。

## Behavioral evidence

- empty PDF/DOCX：typed `content/empty_input_file`、exact message/retry hint、canonical label；converter calls 为 0。
- fragment、`财报正文`、换行、U+202E 与合法超长 basename：统一固定隐藏标签；普通 `report.pdf` 原样保留；pathful 输入拒绝。
- reason constructor：`None`、普通 canonical label、固定隐藏标签接受；raw fragment、Unicode `Cc/Cf`、pathful、超长未 canonicalize
  label 拒绝。
- parser：旧四字段与非 exact shape 拒绝；delegation test 证明五字段原样进入 constructor，parser 不复制 label 规则。
- corrupt PDF/DOCX deterministic matrix：全部 Docling closed failure kind 映射稳定，reason 不含原始异常文本、绝对路径或 repr，
  `__cause__` identity 保留。
- fail-fast：bad-first 不转换后续文件；valid-before-bad 只转换到首个 bad。
- SEC/CN valid+corrupt mixed：batch begin/commit/rollback 均为 0，company/source stage 为 0，published tree 为空，terminal stored 为 0。
- workflow tests 禁用 generic failure mapper后仍通过；direct test禁用 `_classify_direct_error(...)` 与
  `_safe_direct_error_message(...)` 后仍从 typed reason 产生同一 message/retry/file details。
- material failure catch、publication顺序与 public behavior未修改。
- pathful basename 在 workspace read/publication 与 `exists/is_file/suffix` 前产生
  `invalid_file_basename / 上传文件名无效；请提供单个非空文件名`；message 不含 raw basename，code 不接受 `file_name`。
- 普通 `report.pdf`、普通中文 `审计报告.pdf`、fragment、`Cc/Cf` 与 241 字符 basename 均不被 static admission 拒绝；后四类仍由
  canonicalizer 投影为固定隐藏标签，未复制 slash/backslash/fragment/control/length 规则。

## Validation

- S2 focused：
  - `pytest -q tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py`
  - review-fix 结果：`325 passed`，3 个第三方 deprecation warnings。
- S1 focused regression：
  - `pytest -q tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py`
  - review-fix 结果：`334 passed`，3 个第三方 deprecation warnings。
- Broader coverage run：
  - `coverage run -m pytest -q tests/fins -k 'not test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect'`
  - review-fix 结果：`1404 passed, 1 skipped, 1 deselected`。
  - 修改生产文件覆盖率：`direct_events.py 87%`、`ingestion_runtime.py 91%`、`cn_pipeline.py 94%`、
    `docling_upload_service.py 88%`、`sec_upload_workflow.py 93%`、`upload_failure.py 96%`。
- Pyright：`python -m pyright dayu/ tests/ utils/` -> `0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- old-field audit：`rg -n '\buploaded_files\b' dayu/fins tests/fins --glob '*.py'` 零命中。
- progress audit：`_PAYLOAD_FILE_COUNT = "file_count"` 与 request/progress regression仍存在。
- production summary constructor audit：仍恰好为 accepted S1 的四个构造点。

一次未排除的全 `tests/fins` coverage 运行结果为 `1397 passed, 1 skipped, 1 failed`；唯一失败
`test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 的 fixture 未提供当前 production prevalidation 要求的
`company_name`，实际得到 `invalid_argument`。该测试及其工具入口不在 S2 allowed files/call path，本 slice 未修改或掩盖它；coverage pass
只为取得本 slice 单文件覆盖率而精确 deselect 该无关测试。

## Documentation decision

- 已读取根 `README.md`、`dayu/fins/README.md` 与 `tests/README.md` 的更新边界。
- 本实现确有用户/开发者可见 contract 文档触发，但 accepted plan 将 README 明确放在 S3；因此本 gate
  不修改 README。S3 owner 后续按已落地代码同步，不在 S2 预写未来状态。
- Host/Engine/Service/runtime 分层与 contract 均未改变，不更新对应设计或 README。

## No-touch and SHA audit

- 未修改 `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/config/**`、`dayu/ui/**`、
  `dayu/service/fins_direct.py` 或其它 Service production、`dayu/fins/storage/**`。
- 未修改 material generic failure、CLI generic catch、direct no-artifact、日期/年份、alias、format capability、primary/collision、repair、
  concurrency、company warning 相关实现。
- 未执行 UF-PF03；未修改冻结 evidence 或 UF-PF03 artifact。
- `docs/cli_ci_scenarios.json` SHA-256：
  `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`。
- `docs/cli_ci_oracles.json` SHA-256：
  `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`。

## Residual risks and uncovered areas

- 真实 Docling 对损坏样本的底层异常跨平台差异：**assigned to later work unit**（UF-PF03）；本 slice 只承诺并已验证 closed public
  code/reason，不承诺第三方 subtype/text。
- CLI unknown generic catch、真实 CLI corrupt/empty/mixed stderr 与 direct no-artifact positive control：**covered by later approved slice**
 （UF-FIX03-S3）；本 slice 未进入。
- material generic raw failure/company-first publication：**assigned to later work unit**（Fins material workflow）；本 slice保持现状。
- 上述 out-of-scope upload-tool fixture failure：**assigned to later work unit**（upload tool/prevalidation test owner）；不影响 S2 focused、S1
  regression、pyright或本 slice覆盖率结论。

没有未分类 residual risk，没有 blocking open question。双路 S2 re-review 均已 PASS，下一入口为
`S2 accepted slice commit`；本 slice 未进入 S3 或 UF-PF03。
