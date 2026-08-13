# UF-FIX01 validation-atomic-boundary — Plan Re-Review (MiMo)

## Review Metadata

- **Reviewed target**: `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`（修订后）
- **Review scope**: 复核 MiMo F01–F04 与 AgentDS DS-01–DS-08 是否在修订后 plan 中关闭
- **Review inputs**:
  - `docs/reviews/plan-review-20260813-093247.md`（MiMo 初审）
  - `docs/reviews/plan-review-20260813-094750-agentds.md`（AgentDS 初审）
  - `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-fix-20260813.md`（Controller 裁决）
  - `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`（修订后 plan）
- **Reviewer**: AgentMiMo（adversarial re-review）
- **Review date**: 2026-08-13

## MiMo F01–F04 复核

### F01 — publication guard bypass 机制 — **closed**

- **修订后 plan 证据**: §6.3 明确固定实现顺序："先规范 external ticker，再调用 storage owner 已有 canonical ticker-root read helper `_ticker_dir_for_read(external_ticker)` 判定 published root。只有该 helper 抛出的 exact `FileNotFoundError` 可短路为 `(None, None)`；此分支不得调用 `_acquire_publication_guard`，不得创建 `.dayu`、`portfolio`、lock"
- **补充证据**: §12.1 "fresh canonical-root absent 必须在 guard 前短路且零 lock"
- **测试覆盖**: S1 增加 "fresh absent 后路径级断言 `.dayu`、`portfolio`、batch lock root/publication lock 全部不存在" 与 "canonical ticker root symlink、broken symlink、identity descriptor 缺失/错配、company/source corrupt meta 均 fail closed"
- **判定**: 初审要求的 bypass 策略已显式写死（`_ticker_dir_for_read` 前置 → exact `FileNotFoundError` 短路 → 不进入 guard），路径级断言覆盖了 lock artifact 检测。**closed**。

### F02 — FinsUploadUsageCode 闭集枚举 — **closed**

- **修订后 plan 证据**: §6.1 删除"至少覆盖"措辞，改为"穷尽闭集，不得在实现时添加 ad-hoc 成员"，并列出 23 个精确 member 名称
- **补充证据**: §6.1 新增完整 mapping 表，列出每个 frozen scenario (UF-003–038) → exact code → exact message，含判定优先级
- **测试覆盖**: S2 "UF-003–006、015–019、021–024、026–038 参数逐项返回 exact `FinsUploadUsageCode` 和 bounded message"
- **判定**: 初审要求的显式枚举与 scenario→code 映射表已提供。**closed**。

### F03 — lazy bootstrap 回归验证 — **closed**

- **修订后 plan 证据**: §6.4 明确 "`dayu/fins/storage/_fs_repository_factory.py::build_fs_repository_set` 已有并已透传 `create_directories: bool = True`；本 WU 只在 `DefaultFinsRuntime.create` 传 `False`，**不修改** factory 文件"
- **补充证据**: §7 "明确不修改" 节列出 `_fs_repository_factory.py`，Q2 rejected/resolved
- **测试覆盖**: S1 明列四类路径回归："direct download"、"runtime/durable download"、"direct preprocess"、"legacy preprocess/upload job"，每类有具体断言
- **判定**: 初审要求的 download/preprocess 路径显式覆盖已提供。**closed**。

### F04 — CLI stderr 格式模板 — **closed**

- **修订后 plan 证据**: §6.1 固定唯一渲染路径："`render_cli_error(f"dayu-cli upload_filing: {usage_failure.message}")`"，说明 "`render_cli_error` 负责追加唯一换行"，exact stderr 为 `f"dayu-cli upload_filing: {usage_failure.message}\n"`
- **补充证据**: §6.1 明确 "这里消费的是 `FinsUploadUsageFailure`，绝不能与 runtime 的 `FinsUploadFailureReason` 混用"
- **测试覆盖**: S2 "每个 CLI case 的 stderr 必须来自 `render_cli_error(f"dayu-cli upload_filing: {usage_failure.message}")`"
- **判定**: 初审要求的 stderr 格式模板已通过代码路径固定。**closed**。

## AgentDS DS-01–DS-08 交叉复核

### DS-01 — `validate_fins_upload_filing_request_for_workspace` 模块归属 — **closed**

- **修订后 plan 证据**: §6.1 明确 "`dayu/fins/ingestion_runtime.py` 是 pure types/validator 的唯一归属"，§7 service_runtime.py 条目改为 "`prevalidate_fins_upload_filing_request_for_workspace` concrete assembly wrapper"
- **补充**: §6.1 给出 `service_runtime.py` wrapper 的精确签名，说明"wrapper 只装配 `FsFilingUploadStateRepository(create_directories=False)`……不构造 `DefaultFinsRuntime`，不定义 code/message，不把 concrete storage type 泄漏到 validator 或 CLI。不得再定义第二个 workspace validator 名字或兼容 alias"
- **判定**: 归属矛盾已修复：ingestion_runtime 定义 pure types/validator，service_runtime 只拥有 concrete assembly wrapper。**closed**。

### DS-02 — SEC 侧 state repository 装配路径 — **closed**

- **修订后 plan 证据**: §7 新增 `sec_pipeline.py` 条目："`SecPipeline.__init__(..., filing_upload_state_repository: FilingUploadStateRepositoryProtocol, ...)`"
- **补充**: §7 service_runtime.py 条目 "`get_ingestion_runtime` 把同一实例注入 runtime、SEC、CN"
- **判定**: SEC 侧装配链已完整：service_runtime → SecPipeline.__init__ 注入 → workflow。**closed**。

### DS-03 — validated 契约传导链 — **closed**

- **修订后 plan 证据**: §6.2.1 固定完整签名链：CLI `_prevalidate_upload_filing_request` → `_open_direct_stream` → Service `upload_filing(ValidatedFinsUploadFilingRequest)` → Runtime `upload(ValidatedFinsUploadFilingRequest)` → Runner `run_upload(ValidatedFinsUploadFilingRequest)` → SEC/CN facade `upload_filing(ValidatedFinsUploadFilingRequest)` / `upload_filing_stream(ValidatedFinsUploadFilingRequest)`
- **补充**: §6.2.1 固定 authoritative recheck 流程（fresh snapshot → 同一 validator → 丢弃旧派生值），§7 CN pipeline 条目对称
- **判定**: 传导链已从 CLI 到 workflow 全链路固定，authoritative recheck 机制已 spec。**closed**。

### DS-04 — `resolve_upload_action` 与 overwrite precondition 归属 — **closed**

- **修订后 plan 证据**: §6.5 明确 "`dayu/fins/pipelines/docling_upload_service.py` 继续是 action/overwrite/prepare 分支的唯一 owner"，列出 `resolve_upload_action` 与新增 `UploadOverwritePrecondition` / `evaluate_upload_overwrite_precondition`
- **补充**: §7 docling_upload_service.py 条目 "保留并共享 `resolve_upload_action`；新增 `UploadOverwritePrecondition` 与 `evaluate_upload_overwrite_precondition`"
- **判定**: 归属已明确，validator/workflow/prepare 共用同一 helper。**closed**。

### DS-05 — company stage 失败注入与 delete 失败注入 — **closed**

- **修订后 plan 证据**: S3 新增 "company stage 写 staging 中途失败：`rollback=1/commit=0`，published company/source before/after tree 与逐文件 SHA-256 完全相同" 与 "delete source stage 失败：`rollback=1/commit=0`，company tree/SHA 不变、source 完整恢复且所有文件 SHA 不变"
- **判定**: 两条缺失的失败注入路径已补充。**closed**。

### DS-06 — UF-FIX09 共享 converter identity 断言落点 — **closed**

- **修订后 plan 证据**: S3 新增 "`DefaultFinsRuntime.get_ingestion_runtime` owner test 构造一次 production composition，断言 SEC upload、CN upload、CN download、HK download 持有的 `ProcessDoclingConverter` 均 `is` 同一实例，重复调用返回同一 ingestion runtime；operation cancellation token 从 runtime→runner→SEC/CN facade→`DoclingUploadService.prepare_upload`→converter 保持 object identity，且 `prepare_upload` 仍为 async/await 路径。禁止以 caller-local fake converter 证明共享装配事实"
- **补充**: S3 owner tests 列表新增 `tests/fins/test_fins_ingestion_runtime.py`（DefaultFinsRuntime composition owner）
- **判定**: 断言已落在装配层 owner test，禁止 fake converter。**closed**。

### DS-07 — CLI 异常处理顺序 — **closed**

- **修订后 plan 证据**: §6.1 固定 catch 顺序："该 catch 必须紧随既有 usage catch，位于 `FinsDirectStreamProtocolError`、`KeyboardInterrupt` 和最终 generic `except Exception` 之前；generic branch 只映射 runtime/content/storage failure 为 exit `1`"
- **补充**: §7 "`run_fins_direct_command` 按 6.1 exact renderer/catch 顺序映射 `FinsUploadUsageError` 为 exit `2`"
- **判定**: 顺序约束已显式声明。**closed**。

### DS-08 — fresh absent fast path 实现顺序 — **closed**

- **修订后 plan 证据**: 与 F01 同源，§6.3 已显式固定 `_ticker_dir_for_read` 前置判定顺序
- **补充**: §12.1 "fresh canonical-root absent 必须在 guard 前短路且零 lock"
- **判定**: DS-08 与 F01 为同一缺陷的独立复证，均已由 §6.3 的显式顺序固定关闭。**closed**。

## 新 material flaw 检查

逐项检查修订后 plan 是否引入新问题：

1. **§6.2.1 authoritative recheck 是否过度设计？** — 不是。TOCTOU 风险真实存在（preflight 后 state 可能变化），recheck 是 fail-closed 的最小防御。workflow 丢弃旧派生值、只用 fresh result 驱动 prepare/stage/commit，符合 AGENTS.md 的 "不做过度设计，以最小化满足需求为标准"。
2. **§6.5 `UploadOverwritePrecondition` 是否越界到 UF-FIX02/08/10？** — 不是。plan 明确 "本 WU 只把现有判断前移并类型化，不改变 UF-FIX02/08/10 的 action、identity、repair 或 overwrite 业务语义"。枚举只是把现有的 `FileExistsError` / `FileNotFoundError` 异常路径类型化为 typed disposition。
3. **§6.2.1 非 CLI consumer 的 usage error 投影是否合理？** — 是。plan 明确 "只有 CLI 把它映射为 exit `2`；Service/tool/wait consumer 原样得到 typed error，并由其既有调用边界处理。Host/Engine 不新增 error type、schema、event 或映射"。这保持了 Host/Engine 边界不变。
4. **§7 "明确不修改" 节是否完整？** — 已列出 `_fs_repository_factory.py` 和 `dayu/host/**`、`dayu/engine/**`。完整。
5. **S1–S4 依赖顺序是否仍合理？** — 是。S1 storage read → S2 validation → S3 atomic publication → S4 typed failure → S5 docs。S2 依赖 S1 的 storage protocol，S3 依赖 S2 的 validated handoff，S4 依赖 S3 的 typed failure pipeline。
6. **§12.2 Blocking questions 是否全部关闭？** — Q1/Q3/Q4 resolved，Q2 rejected with reason。无 blocking question。

未发现新 material flaw。

## 结论

**pass**

MiMo F01–F04 全部 closed，AgentDS DS-01–DS-08 全部 closed。Controller 裁决的所有 accepted findings 均已在修订后 plan 中修复，4 个 Open Questions 均已 resolved/rejected。修订后 plan 未引入新 material flaw。

plan 已达到 code-generation-ready 状态：所有关键设计决策已固定（guard bypass 顺序、usage code 穷尽枚举、validated handoff 全链路签名、authoritative recheck 机制、action/overwrite helper 共享、CLI catch 顺序、UF-FIX09 composition owner test），无 blocking question，无 deferred finding。
