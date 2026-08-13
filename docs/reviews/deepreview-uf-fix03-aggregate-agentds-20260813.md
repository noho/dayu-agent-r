# UF-FIX03 Aggregate Final Deepreview（AgentDS）

## Scope

- Mode: aggregate final review（current changes）
- Branch: `codex/upload-filing-oracle`
- Base: `662c9ad4b234894e54c62b56368c7682a09f596e`
- HEAD: `c54a4fd8a08955a91287cc0f74070f5c9211143a`
- Review date/time: 2026-08-14T00:09:23+0800
- Output file: `docs/reviews/deepreview-uf-fix03-aggregate-agentds-20260813.md`
- Included scope: 全部生产/测试 diff（`662c9ad4...c54a4fd8`，42 文件）；accepted plan、goal confirmation、三个 frozen predicates、S1/S2/S3 accepted/implementation/review-fix artifacts
- Excluded scope: 无（生产 diff 8 个文件全部逐行走读；测试 diff 全部新测试走读）
- Parallel review coverage: 无（单 reviewer 全量走读）
- 执行约束遵守：全程只读；未 stash/switch/checkout/reset/clean/commit/改代码或既有 artifact；仅新增本 artifact；运行只读 pytest/pyright/coverage（coverage 数据文件重定向至 `/tmp`，仓库内零写入）

## 结论

**PASS** — 附带 1 个低严重度 maintainability finding（F1，dead defensive catch）。未发现 correctness/stability 级缺陷；全部 frozen predicate、owner contract、原子性、stderr 安全与 direct no-artifact 边界均经代码与运行验证闭环。

## 核对清单与证据

### 1. requested/stored 单一真源（S1）

- requested 真源：`FinsUploadResultSummary.requested_file_count` 只来自 `len(validated request.files)`。四点生产构造：`service_runtime.py:131`（early-cancelled）、`service_runtime.py:305`（`_upload_summary_from_result`）、`ingestion_runtime.py:3968`（direct runner-unavailable）、`ingestion_runtime.py:4449`（job runner-unavailable）——AST audit 测试 `test_production_upload_count_constructors_are_explicit_and_complete`（`test_fins_ingestion_runtime.py:863`）锁定恰为 4 点且无 default。本 review 独立 `rg` 复核一致。
- stored 真源：`docling_upload_service.py` `_store_upload_assets` 只在每次成功 `store_file(...)` 后对 `asset.source == _ASSET_SOURCE_ORIGINAL` 计数（当前文件 `stored_original_count`，diff hunk 行 ~529-534）；derived Docling 资产不计；payload 中 `uploaded_files` 已删除。
- `FinsUploadPipelineResult.__post_init__`（`ingestion_runtime.py:1216-1242`）拥有完整五状态矩阵：`ok>=1`、`skipped/deleted/failed/cancelled==0`，拒绝 bool/负数/非 int；`from_pipeline_json` 只 exact-read 后进 constructor（`_required_upload_result_int` 拒绝缺失/bool/非 int），不复制矩阵。生产 `cls(...)` 构造点恰为 1（AST audit 断言）。
- `FinsUploadResultSummary.__post_init__`（`ingestion_runtime.py:1317-1342`）矩阵与 plan §5.3 逐项一致：`ok: requested>=1 && stored==requested`；`skipped: requested>=1 && stored==0`；`deleted/cancelled/failed: requested>=0 && stored==0`；全部拒绝 bool/负数。
- 状态矩阵测试同时覆盖 direct constructor 与 JSON parser 双入口，`cancelled+0` 接受、`cancelled+positive` 拒绝（`test_fins_ingestion_runtime.py:600-722, 735-835`）——不靠 summary 兜底。

### 2. non-ok zero / original-only / 无 old field

- 非 ok 终态 stored 恒为 0 的构造链：`prepare_upload` skipped（`docling_upload_service.py:330-336`）、`publish_prepared_upload` deleted（:412-420）、`_build_cancelled_result`（:1468-1474）均为 `stored_file_count=0`；workflow failure terminal `_build_sec_filing_failure_event`（`sec_upload_workflow.py:390-395`）与 `_build_cn_filing_failure_event`（`cn_pipeline.py:1837-1841`）显式 0；commit 失败路径经 `test_upload_filing_commit_failure_never_publishes_staged_count`（OSError→`storage/storage_io`、RuntimeError→`runtime/unexpected_runtime`，published tree SHA 不变，`rollback_tokens==[]`）锁定 staged count 不外泄。
- 取消路径：`DoclingConversionCancelledError` 不是 `DoclingConversionError` 子类（`docling_process_converter.py:242`），逐文件 catch 不吞取消；prepare 取消分支与 `_store_upload_assets` 循环内取消均回 `_build_cancelled_result`（stored 0）。CN `test_upload_filing_conversion_cancelled_has_zero_stored_count` 与既有 SEC observably 测试覆盖。
- `rg '\buploaded_files\b' dayu tests --glob '*.py'`：生产零命中；唯一命中为 CLI 测试负向护栏 `assert "uploaded_files" not in rendered`。`to_json_summary` 只输出 `requested_file_count/stored_file_count`。
- progress `_PAYLOAD_FILE_COUNT == "file_count"` 未动（`ingestion_runtime.py:250, 7648`），started/preparing/completed 仍是 requested 单位；未出现双写或 rename。

### 3. typed failure 唯一 owner 与五字段 exact contract（S2）

- `FinsUploadFailureReason` 五字段全部 required、`file_label` 无 default 可 null（`upload_failure.py:67-102`）；`__post_init__` 对非 None label 强制调用唯一 `validate_fins_public_file_label`。parser `_FAILURE_KEYS` frozenset exact-key 检查拒绝旧四字段/缺失/未知 key（:285-286），`_optional_failure_text` 允许 null 值；kind/code 一致性校验含 `EMPTY_INPUT_FILE -> content`（`_CONTENT_FAILURE_CODES` :156-158）。
- 唯一 label owner：`direct_events.py:1070-1156` `canonicalize_fins_public_file_label` / `validate_fins_public_file_label` 共享同一私有判定，复用既有 `_validate_safe_text` 与 `_DISALLOWED_TEXT_FRAGMENTS`；fragment、Unicode `Cc/Cf`、超 240 合法 basename → 固定隐藏标签 `输入文件（文件名已隐藏）`；pathful/空/dot 拒绝；`FinsEventDetail` 通用 guard 未放宽。依赖方向 `upload_failure -> direct_events` 单向，无 lazy import。
- 无字符串重分类/下游 fallback：`_build_pending_assets` 逐文件 catch 用当前 `file_path.name` canonicalize 后经 owner mapper 包装（`docling_upload_service.py` diff ~769-786），`raise ... from exc` 保留 cause；workflow 在 Docling/OSError/generic 前穷尽 `FinsUploadFailureError` 直接投影 `exc.failure`。测试 `test_direct_upload_typed_failure_projection_bypasses_string_classifiers`（禁用 `_classify_direct_error`/`_safe_direct_error_message`）与 SEC/CN mixed 测试（禁用 `fins_upload_failure_from_exception`）证明 typed 路径不穿透字符串分类边界。parser delegation 测试（monkeypatch constructor）证明 parser 不复制 label 规则。
- known/unknown 边界：known（empty/corrupt/mixed/storage/runtime）→ typed terminal；unknown（workflow generic）→ 同 owner mapper `unexpected_runtime` + 固定文案；unknown（CLI transport）→ `run_fins_direct_command` generic catch（`fins.py:220-227`）只写 `_LOGGER.exception` + 固定 stderr `命令执行失败，请使用 --log-file PATH 重试并查看日志`，退出码 `EXIT_FAILURE`；已知分支顺序未变。

### 4. empty/corrupt/mixed 预发布原子失败、SEC/CN 一致（S2）

- empty：`_build_original_assets` 对 FILING 空 bytes 在 converter/batch 前抛 `empty_input_file`（message/retry_hint 与 plan §5.4 字面一致），material 行为不变。SEC `test_upload_filing_empty_fails_before_batch_with_typed_label` 断言 exact 五字段 JSON、converter calls `[]`、begin/commit/rollback/company/source stage 全 0、published tree SHA `{}`。
- corrupt：六个 Docling closed kind 全矩阵映射（`test_corrupt_filing_wraps_each_closed_docling_failure_with_label_and_cause`），reason 不含底层异常文本/路径，`__cause__` 身份保留。
- mixed：SEC/CN 各一条 workflow 测试断言 fail-fast 顺序（`calls == ["valid.pdf", "corrupt.docx"]`）、batch/company/source 零 stage、tree SHA 不变、terminal stored 0；direct mixed 测试同形。CN/HK 与 SEC 实现逐 catch 对称（已逐行比对）。
- 真实 CLI：`test_real_cli_content_failure_has_bounded_stderr_and_zero_fresh_workspace_mutation` 用真实 subprocess `dayu-cli upload_filing` 覆盖 empty/corrupt PDF/corrupt DOCX：exit 1、stderr 含 canonical label + closed kind/code + requested/stored + 有界 reason、无 Traceback/绝对路径、fresh workspace 零 mutation。

### 5. stderr/log 安全与 canonical label（S3）

- 8 项 renderer cap 下 details 排序（`_upload_result_details`，`ingestion_runtime.py:6372-6400`）：`source kind/status/requested files/stored files/failure kind/failure code/file/failure message` 为前 8 项，带 label 的 content failure 的 counts、code、file、message 全部在 cap 内；retry hint/document 为辅助项。owner 顺序测试（`test_upload_direct_details_consume_typed_failure_label_and_retry_hint`）精确断言全序与前 8 项。`dayu/cli/output.py` no-touch（`_FINS_SUMMARY_MAX_ITEMS=8` 无 Fins 特例）。
- operator log 保留 raw cause：`_LOGGER.exception` + `%r` 转义 raw basename（防换行注入），public 投影不含 raw text（SEC/CN mixed 测试断言 `str(cause) in caplog.text` 且 `not in str(result)`）。

### 6. direct 不创建 Host/Engine/runtime/legacy artifacts（S3）

- `_produce_direct_upload` 无 `create_job/start_upload` 调用（grep 复核）；`test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts` 为正控优先：真实 `DefaultFinsRuntime.create` + FS 仓储完成 filing 发布，从仓储读回 source meta/original blob/derived Docling asset/company meta，随后断言 `job_store.root_dir` 无 `*.json/*.jsonl`、`executor.operations == []`、host_dir/host_sqlite/artifact_root/runtime_lanes_db 均不存在（typed `job_store.root_dir`，不硬编码路径）。
- Service production 零改动；`test_service_public_direct_api_does_not_export_job_handle` 扩展断言无 `start_upload/read_job/read_job_events`。

### 7. README / pyright / coverage / no-touch / frozen SHA

- README：根 `README.md`（用户可见 requested/stored、整批失败、`--log-file PATH` 指引）、`dayu/fins/README.md`（owner contract/typed projection）、`tests/README.md`（测试层级与命令）按各自职责更新；Service/Host/Engine/`dayu/README.md` 未动，与 plan §6.3 预定 decision 一致。
- 本 review 独立运行：focused 8 文件 `473 passed, 3 warnings`（与 S3 artifact 声称一致）；broader `tests/fins`（deselect 既有无关 fixture 失败测试）`1409 passed, 1 skipped, 1 deselected`；pyright 全量 `0 errors, 0 warnings, 0 informations`。
- coverage（独立复跑）：8 文件 focused 集 `fins.py 86% / direct_events 88% / ingestion_runtime 91% / cn_pipeline 69% / docling_upload_service 88% / sec_upload_workflow 93% / service_runtime 90% / upload_failure 97%`，aggregate 88%；broader run `cn_pipeline 94%`。与 S1/S2/S3 artifacts 逐项一致；`cn_pipeline` 的 focused 69% 缺口按 S1 裁决归既有未修改分支，broader 94% 满足修改文件目标，未用 pragma/降阈值掩盖。
- no-touch diff：`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/config/**`、`dayu/ui/**`、`dayu/service/**` 生产、`dayu/fins/storage/**`、冻结 JSON/evidence 零改动（`git diff --name-only` 复核）。
- frozen SHA 独立复核：`docs/cli_ci_scenarios.json = a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`、`docs/cli_ci_oracles.json = 88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`，与 plan §1 字面一致。
- 排除项：diff 中无 UF-PF03 artifact/evidence 变更；未执行 UF-PF03。material 仅机械补齐 shared count（material 测试只增 count 断言，generic failure/company-first 行为回归保持）。

### 8. 跨切片排序 / summary schema / known-unknown / fixture 挑战

- details 排序与 8 项 cap：S3 F1 修复后 ordering 已由 owner 级全序测试锁定（见 §5），不存在跨切片漂移。
- summary schema 跨切片一致：S1 定义的两个 count 字段在 S2（failure label 投影）与 S3（details 排序）未被重定义；durable（`to_json_summary`）与 direct（`_upload_result_details`）消费同一 `FinsUploadResultSummary` 字段。
- 测试未只验证 fixture：owner 矩阵测试打 direct constructor 与真实 parser 双入口；direct 集成测试使用真实 FS 仓储与真实 publication 正控；CLI 使用真实 subprocess 与真实 production 投影链（`validate_fins_upload_filing_request -> _direct_upload_terminal_events -> render_fins_direct_event`）；workflow 测试使用真实 pipeline + tracking 仓储 + published tree SHA。fixture 仅作为 typed 输入存在，未固化第二套 counts/status/error 映射。

## Findings

### 1-未修复-低-SEC/CN filing workflow 的 `except DoclingConversionError` 分支当前拓扑不可达且无覆盖
- **入口/函数**: `run_upload_filing_stream`（SEC）/ `CnPipeline.upload_filing_stream`（CN/HK）的 exception 分层
- **文件(行号)**: `dayu/fins/pipelines/sec_upload_workflow.py:298-301`（`except DoclingConversionError` catch 体，coverage missing 299-301）；`dayu/fins/pipelines/cn_pipeline.py:918-921`（coverage missing 919-921）
- **输入场景**: 任何 filing 上传（当前拓扑下无输入可触发）
- **实际分支**: `_build_pending_assets` 已把 filing 全部 `DoclingConversionError` 在逐文件边界包装为 `FinsUploadFailureError`（`docling_upload_service.py` catch 分支，`source_kind is not FILING` 时才原样 re-raise），故 filing 路径上该 workflow catch 不可达；两条 catch 均未被任何测试覆盖（broader coverage missing 行证实）。
- **预期行为**: 按 plan §5.4，`FinsUploadFailureError` 的 typed catch 是 filing 的穷尽边界；若保留防御性 `DoclingConversionError` catch，其投影应携带同一 canonical label 或至少被 owner test 锁定。
- **实际行为**: 若未来任何改动让 `DoclingConversionError` 绕过包装（例如新增转换入口、refactor 时序），该 catch 会以 `file_label=None` 投影 content failure——静默丢失 frozen predicate 要求的 canonical 文件名标签，且没有任何测试会失败报警。
- **直接证据**: 逐文件包装代码（`docling_upload_service.py` `except DoclingConversionError as exc: if source_kind is not SourceKind.FILING: raise`）+ `DoclingConversionCancelledError` 非子类事实（`docling_process_converter.py:242`）+ broader coverage missing `sec_upload_workflow.py:299-301`、`cn_pipeline.py:919-921`。
- **影响**: 当前无行为错误；属于 maintainability/latent degradation——不可达分支 + 退化投影（label 丢失）+ 零回归报警。
- **建议改法和验证点**: 二选一，由 controller 裁决：(a) 与 S1 删除不可达 `DoclingConversionCancelledError` catch 的裁决一致，删除这两个 filing catch（material workflow catch 保留，仍可达）；(b) 保留为防御层，但补充 owner test 注入未包装 `DoclingConversionError` 并断言其投影行为（file_label=None 的有意语义），并在 catch 处注释说明防御理由。
- **修复风险（低）**: 仅删两个不可达 catch 或补注释/测试，不动状态机。
- **严重程度（低）**:

## Open Questions

- `_build_original_assets` 的 empty 检查发生在 skip fingerprint 判定之前：若旧版本（允许空文件）曾成功发布空文件形成 previous meta，重传同一空文件将由 skip 变为 `empty_input_file` 失败。本 review 判断旧版空文件能通过 Docling 转换并成功发布的可能性极低（fail-closed 也符合 frozen predicate），未列为 finding。
- 有 file label 的 content failure 在 8 项 cap 下 `retry hint`（第 9 项）被 renderer 截断。S3 controller 已裁决该优先级（F1），不再复议；用户仍可从 durable/typed reason 取得 retry hint。

## Residual Risk

- 真实 Docling 多平台损坏样本差异未验证（UF-PF03 明确未执行）；public contract 只承诺 closed code/reason，底层文本只在 operator log——风险已按 accepted plan 归 UF-PF03。
- `test_real_cli_content_failure_has_bounded_stderr_and_zero_fresh_workspace_mutation` 依赖真实 Docling 对损坏样本稳定失败；若平台升级改变行为且测试失败，S3 stop condition 已预留裁决路径（保留 deterministic owner tests，不加无条件 xfail/skip）。
- 既有无关测试 `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` fixture 缺 `company_name`（broader run 需 deselect）——已按 S2/S3 裁决归 upload tool contract/test owner，本 WU 未在生产加兼容分支；该测试修复前 broader 全量绿仍依赖 deselect。
- F1 未修复前，SEC/CN filing 各存在一条零覆盖防御分支（详见 Finding 1）。

## 验证命令与结果（本 review 独立执行）

- `pytest -q tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py` → `473 passed, 3 warnings in 15.21s`（warnings 为 edgar 第三方弃用提示）。
- `coverage run -m pytest -q tests/fins -k 'not test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect'`（COVERAGE_FILE 重定向 /tmp）→ `1409 passed, 1 skipped, 1 deselected`；`cn_pipeline.py 94%`。
- 8 文件 coverage report（§7）与 artifacts 逐项一致。
- `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- 静态审计：`rg uploaded_files`（生产零命中）、summary/operation/pipeline constructor inventory（4/4/1）、`_PAYLOAD_FILE_COUNT` 保留、no-touch diff、frozen SHA（§7）全部通过。
