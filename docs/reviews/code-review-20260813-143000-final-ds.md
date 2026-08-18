# Code Review — UF-FIX01 Final Gate 独立复核（DS 路）

## Scope

- Mode: current changes（strict bounded final gate review，禁止子 agent、禁止扩散检索、禁止运行大测试、禁止修改实现）
- Branch: `codex/upload-filing-oracle`
- Base: `69bc9d2af91788303c839d01ad937cf9b802eb1d`
- Range: `69bc9d2a..b1064bd9`
- Output file: `docs/reviews/code-review-20260813-143000-final-ds.md`
- Included scope: 完整 diff 57 文件（production + tests + READMEs + gateflow artifacts + prior review artifacts）；关键生产符号最终状态走读（`dayu/fins/ingestion_runtime.py`、`dayu/cli/commands/fins.py`、`dayu/fins/service_runtime.py`、`dayu/fins/storage/` 新增仓储、`dayu/fins/upload_failure.py`、SEC/CN workflow、`docling_process_converter.py` 隔离上下文管理器）；evidence root `/Users/leo/workspace/.dayu-cli-ci/uf-pf01-focused-real-20260813-Cxy3YR/final-r3` 的 `result.json`、`report.md` 与 `UF-ATOMIC-FRESH` / `UF-ATOMIC-EXISTING` 的 `durable-artifacts.json`
- Excluded scope: 未修改的 Host/Engine；frozen evidence/registry 本体；MiMo 路 artifact（本路独立裁决，未以其内容为依据）；`final-r3/manifest.json`、`digest.json`、逐 case `sha256sums.txt`（按 Controller 最新限界只读指定三份事实文件）
- Parallel review coverage: 无
- Evidence HEAD 一致性：evidence artifact 记录 `184c0819`，位于本 review range 内；range 内其后仅有 evidence 记录 commit，生产代码无后续 delta

## Findings

未发现实质性问题。七项 gate 核销项全部有直接代码/测试/真实证据支撑，无阻塞 finding。

## 七项核销

### 1. validation 真源 / bootstrap 前 exit 2 零 mutation — PASS

- 单一真源成立：`FinsUploadUsageCode` 闭集（23 成员）与唯一文案表 `_USAGE_MESSAGES` 集中在 `dayu/fins/ingestion_runtime.py`；静态校验 `_validate_fins_upload_filing_static` 与 state-aware `validate_fins_upload_filing_request` 是所有入口（CLI prevalidate、runtime `_validate_runtime_upload_request`、workflow authoritative recheck）复用的同一 validator。CLI 不再自行解析 ticker/校验文件（`_upload_filing_stream` 旧散参校验已删除）。
- bootstrap 前：`_run_fins_direct_command_async` 中 `_prevalidate_upload_filing_request` 位于 `FINS_DIRECT_SERVICE_FACTORY(workspace_root)` 之前；`run_fins_direct_command` 的 `except FinsUploadUsageError` 位于 `FinsDirectStreamProtocolError` / generic 之前并精确映射 `EXIT_USAGE_ERROR`。
- 零 mutation：`FsFilingUploadStateRepository(create_directories=False)`、`build_fs_repository_set(create_directories=False)`（SecPipeline/CnPipeline/DefaultFinsRuntime 三处 fallback 与 create 全部改为惰性）；job store `__post_init__` 零副作用、`create_job` 首写才 `_ensure_root_for_write`，missing read/save 不建目录；`read_filing_upload_state` 在 ticker directory absent 时于 guard/lock/mkdir 前短路返回 absent。
- 测试证据：`test_upload_filing_usage_matrix_precedes_service_factory_and_workspace_mutation` 参数化 25 个 frozen case 穿过真实 `cli_main.main`，逐 case 断言 exit 2、stdout 空、stderr exact 单行、`factory_calls == []`、service 零调用、`not workspace_root.exists()`；`test_default_runtime_create_and_ingestion_assembly_are_lazy`、`test_job_store_first_write_creates_root_but_missing_read_and_save_do_not`、`test_filing_upload_state_fresh_absent_is_pure_and_lock_free`（monkeypatch 拒绝 guard 证明 fresh absent 不触锁）。
- 真实证据：`final-r3/report.md` 中 UF-003–UF-038 共 25 个 usage case exit 精确为 2，filesystem diff 全部 `{"created": [], "deleted": [], "modified": []}`。

### 2. runtime exit 1 typed — PASS

- `upload()` / `start_upload()` / `start_observed_upload()` / `prepare_observed_upload()` 均在 producer/observation/job 创建前调 `_validate_runtime_upload_request`；raw filing 走 `_filing_upload_request_identity` + `read_filing_upload_state` + 同一 validator，validated request 原样放行。
- prevalidation 期 operational failure：repository 构造与 state read 同处一个 typed `try`（R1 修复落地），`(OSError, RuntimeFileLockError)` → `fins_upload_prevalidation_io_failure()`、`ValueError` → `fins_upload_prevalidation_corruption_failure()`，均 `from exc` 保留 operator cause；CLI `except FinsUploadPrevalidationError` 先 `_LOGGER.exception` 再输出固定 path-free 文案并 exit 1。测试固定 exact stderr、无 tmp_path/Traceback/PermissionError、operator log 含两层 cause、fresh workspace 零 mutation。
- 运行期 failure：`FinsUploadResultSummary.__post_init__` 强制 failed↔failure_reason 互斥，`to_json_summary` 与 pipeline result、direct RESULT details/error_message、durable failure summary 从同一 `FinsUploadFailureReason.to_json()` 投影；workflow 显式 typed catch 顺序 cancelled → `DoclingConversionError` → `OSError` → generic，public 只投影 closed reason，`_LOGGER.exception` 保留原始 cause（SEC/CN marker tests 断言 `str(error) not in public result` 且 `str(error) in caplog`）。
- 真实证据：UF-I11/I12/I13 exit 精确为 1，stderr bounded 且含 typed content reason，workspace diff 全零。

### 3. storage batch fresh/existing 原子 — PASS

- filing 先 `prepare_upload`（无 batch）；terminal skip/cancel 不开 batch；非 terminal 路径以同一 caller-owned `BatchToken` stage company 与 source/blob，成功一次 commit；stage 失败经 `rollback_prepared_upload_batch` 恰好一次回滚且保留主异常证据，无补偿删除、无第二 batch、commit 开始后无二次 rollback。`stage_upload_company_meta_decision` 对非 stage disposition 不写。
- 测试证据：SEC/CN 各一组 `test_upload_filing_stage_failure_rolls_back_one_batch_and_preserves_published_tree`（`begin_tokens` 长度 1、`commit_tokens == []`、`rollback_tokens == begin_tokens`、published tree SHA-256 前后一致）；success case 断言 `begin=1/commit=1/rollback=0` 且 company/source `stage_tokens == begin_tokens`；SEC 额外覆盖 rollback failure 的 primary/recovery evidence。
- 真实证据：`UF-ATOMIC-FRESH/durable-artifacts.json` 的 `before/after/business_before/business_after` 全部为空（零 durable state）；`UF-ATOMIC-EXISTING/durable-artifacts.json` 的 `before == after == business_before == business_after`，逐文件 SHA-256 完全一致（corrupt update 失败后既有 company/source durable facts 无任何部分刷新）。

### 4. authoritative revalidation — PASS

- SEC/CN workflow 在 prepare 前通过注入的同一个 `FilingUploadStateRepositoryProtocol` 实例读 fresh snapshot，对 `preflight.request` 调同一 validator，`_assert_authoritative_filing_identity` 逐项比对 canonical ticker/document_id/internal_document_id，不一致 `RuntimeError` fail closed；只有 authoritative `resolved_action`、`published_state.source_meta`、`company_meta_decision` 驱动 prepare/stage/commit。
- `DoclingUploadService.prepare_upload` 新增 `previous_meta` 参数且不再自行读取 state；filing 链以 `stage_upload_company_meta_decision` 取代 `upsert_company_meta_for_upload`（后者生产调用方仅剩 material 路径）；Service/runtime/runner/SEC/CN/HK facade 全链路 typed request 原样透传，不还原散参。
- 测试证据：SEC/CN 各一组 `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision`（stale preflight 的 create→stage 决策被丢弃，final 为 fresh update+skip，company name 保持已发布值、无新 batch）、`test_upload_filing_authoritative_identity_mismatch_fails_closed`（mismatch 在 prepare/mutation 前失败且 tree 为空）；HK facade typed handoff 与 fresh snapshot 断言；`test_default_runtime_composition_shares_upload_state_and_docling_converter` 断言同一 state repository 实例注入两个 pipeline。

### 5. UF-FIX09 不回退 — PASS

- `docling_process_converter.py` 的 F1 修复只新增 `_isolated_inherited_stderr` 上下文管理器并包住第三方 conversion 调用；`__call__` 既有双 except 的 exact failure descriptor 投影不变；父进程轮询、cancellation、terminate/kill/close、attempt chain、format allow-list、storage/publication transaction 均无其它 diff。
- 退出语义：`sys.exception()` 区分主体异常与 flush-only 异常，flush 次生异常不遮蔽主异常（主体异常在途时抑制，无主体异常时仍传播）；FD2 恢复（`dup2`）先于复制 FD 关闭（`close`），嵌套 finally 保证无描述符泄漏；owner test 断言 descriptor 保持 `converter_construction`、`flush_calls == 2`、dup/close 各一次且 `EBADF`、恢复后 FD2 可写。
- 组合测试断言 SEC upload、CN upload、CN/HK download 共享同一 `ProcessDoclingConverter` 实例，UF-FIX09 共享可中断转换器契约保持。

### 6. tests/pyright/docs — PASS

- 测试：frozen usage matrix（真实 CLI boundary）、prevalidation io/corruption/构造期 resolve failure（exit 1、path-free、operator cause、零 mutation）、真实 subprocess `dayu-cli` + 自建 `b"not a PDF"` corrupt PDF（exit 1、typed content reason、stderr ≤1024、无 Traceback/仓库根/输入路径、fresh workspace 零 mutation，且消除本机绝对路径依赖）、storage fresh absent 纯读、SEC/CN 原子性与 typed catch 顺序、material non-goal 回归（`str(exc)` 语义与无 `failure` key 断言）。
- pyright：各 implementation/fix artifact 记录 `0 errors, 0 warnings, 0 informations`；本 gate 按约束未运行，通过性依据 artifact 记录与已读测试断言主体。
- docs：根 `README.md`（usage exit 2 / operational exit 1 / 不发布半成品）、`dayu/fins/README.md`（validation 真源、fresh recheck、单 batch publication、typed failure、stderr 隔离）、`dayu/service/README.md`（validated request identity handoff）、`tests/README.md`（owner coverage 描述）均按各自触发规则更新，且只描述当前已实现行为。

### 7. UF-PF01 integrity/scope — PASS

- `final-r3/result.json`：`overall_passed: true`、`passed_count: 30`、`case_count: 30`、`integrity_failures: []`。
- `final-r3/report.md`：25 个 usage case exit 2 + 零 diff；3 个 content case 与 fresh/existing atomic exit 1 + 零 diff；声明无 mock/fake/monkeypatch/fault injection，未运行 UF-PF12。
- durable facts（见第 3 项）直接证明 fresh 零新增与 existing 零部分刷新。
- Scope statement：未运行或登记 UF-PF12、未修改 frozen evidence/accepted oracle/`docs/cli_ci_scenarios.json`；bundle digest `5e311272…` 与 gateflow evidence artifact 记录一致。

## Open Questions

- 无阻碍裁决的问题。一处窄项待 Controller 备忘：`_save_failed_from_exception`（`dayu/fins/ingestion_runtime.py`，本 range 内未修改的既有 helper）构造 failed summary 时是否已携带 `failure_reason`。`FinsUploadResultSummary.__post_init__` 新增了 failed 必须带 reason 的硬约束；若该 helper 未附带，job 失败终态持久化会抛 `ValueError`。本 gate 按 Controller 限界指令未再逐行核验其函数体，且该路径有既有 runtime 测试覆盖（若缺失应会红），因此仅作备忘，不构成有直接证据的 finding。

## Residual Risk

- 本 gate 按约束未运行任何测试与 pyright；测试/静态检查通过性依据各 artifact 的红绿记录与已读测试断言主体。
- `final-r3` 的 `manifest.json` 与逐 case SHA 清单未逐份复算（按 Controller 最新限界只读指定事实文件）；bundle digest 已与 gateflow evidence artifact 记录交叉一致。
- Windows 下 `os.devnull`/`dup`/`dup2` descriptor 语义未在本机实跑，归类现有跨平台 CI owner 职责。
- 未执行仓库全量 pytest；已依据 range 内 artifact 记录（受影响 suite、逐文件覆盖率 ≥80%）与代码走读评估。

## 结论

**PASS。** 七项 gate 核销项全部 CLOSED：validation 真源统一且 CLI 在 Service factory 前 exit 2 零 mutation；runtime 入口 typed exit 1；storage batch 对 fresh/existing 均为原子发布；workflow authoritative revalidation 落地且旧派生值被丢弃；UF-FIX09 共享可中断 converter 无回退；tests/pyright/docs 齐备；UF-PF01 final-r3 真实证据 30/30 通过、integrity 零失败、scope 无越界。未发现阻塞 finding。
