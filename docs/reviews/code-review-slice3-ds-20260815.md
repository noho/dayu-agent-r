# Code Review（UF-FIX06 Slice 3，AgentDS 第二路独立严格 review）

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：Slice 3 code review（第二路独立严格 review）
- Reviewer：AgentDS
- 日期：2026-08-15
- 基线 commit：`affa665b`（与 implementation artifact 声明一致）
- 评审对象：当前未提交 workspace diff（10 个允许的 production/test 文件 + 新增
  `tests/fins/test_upload_failure.py` + 本 slice implementation artifact）
- 已读文档：`AGENTS.md`、accepted plan、`uf-fix06-slice2-acceptance-20260815.md`、
  `uf-fix06-slice3-implementation-20260815.md`
- Output file：`docs/reviews/code-review-slice3-ds-20260815.md`
- 约束遵守：未修改任何 production/test 文件；未运行 UF-PF06/UF-PF12；未改 README/registry/evidence；未 commit

## 复跑验证结果（均在 `source .venv/bin/activate` 后）

- focused 7 个 test 文件（docling_upload_service / upload_failure / sec filing+material /
  cn / ingestion_runtime / ingestion_tools）：`493 passed, 3 warnings`（warnings 为 3 条既有
  edgar deprecated-module warning；docling 集成测试按既有约定显式 skip）。
- Changed-file pyright（4 个 production 文件）：`0 errors, 0 warnings, 0 informations`。
- Ruff（全部 12 个 changed 文件）：`All checks passed!`。
- `git diff --check`：通过。
- 符号审计：`SUPPORTED_UPLOAD_SUFFIXES` / `_pick_primary_docling_file` / `FINS_UPLOAD_FILE_SUFFIXES`
  在 `dayu/`、`tests/` 的 Python 文件中零引用；唯一残留是 `dayu/fins/README.md:201` 的文档引用（见 F5）。

## 结论

- **Verdict：pass**
- **Blocking count：0**
- 非阻塞 finding：5（F1-F2 文档准确性、F3-F4 测试反例缺口、F5 Slice 4 交接项）

---

## Adversarial failure pass 逐项核验

### A. Service 非法 type/source/action/empty 是否真的在 Path.read_bytes/converter/batch 前失败 —— 是

- `_prepare_upload_selection` 是 `prepare_upload` 第一个语句（`docling_upload_service.py:282`），
  source kind 与 selection 具体类型错配在入口即 `ValueError`；未知 source_kind 在收窄分支后兜底
  `ValueError`（`:1030`）。action 非法（`:287`）与 action/emptiness 双向校验（`:289-293`）紧随其后。
  `read_bytes` 只发生在 `_build_original_assets`（`:710`），converter 只在 `_build_pending_assets`
  调用，batch 只由 workflow 在 `prepare_upload` 返回后创建——全部晚于上述校验。
- 测试证据：`test_prepare_upload_rejects_source_kind_selection_mismatch_before_io` 与
  `test_prepare_upload_rejects_action_emptiness_mismatch_before_io` 均用 monkeypatch 将
  `Path.read_bytes` 换成必抛 AssertionError 的拒绝桩，断言非法组合零读取、零转换、零发布树。
- 边界确认：filing delete 空 selection 的 `converter_inputs=()` 不会到达
  `_build_pending_assets` 的 `RuntimeError("未生成 docling 主文件")`——delete 在 `:304-310`
  先行返回 `_PreparedDeleteMutation`。`require_primary()` 只在 `is_empty=False` 时求值
  （`:1018`），空 filing + create/update 先被 emptiness 校验拒绝，不会触发
  `require_primary` 的 ValueError。

### B. filing companion read failure / corrupt primary / material 多转 / 取消中断 / commit 取消

- **companion read failure**：fresh validation（workflow 内、try 外）已对每个文件做
  exists/regular/suffix 检查；Service 侧 `_validate_source_files`（`:1033-1054`）与
  `_build_original_assets` 对全部 ordered files（含 companions）做 exists/regular + read_bytes，
  缺失/读失败在转换前以 `FileNotFoundError`/`OSError` 拒绝，SEC filing stream 既有
  `except OSError` 投影 STORAGE_IO。空 companion 由既有 filing empty-input owner
  （`_build_original_assets:711-718`）拒绝，测试 `test_empty_filing_companion_fails_before_conversion_and_publication`
  断言 `EMPTY_INPUT_FILE`、label 为 companion basename、converter 零调用、零发布。
- **corrupt primary**：filing 仅 primary 进 converter；`except DoclingConversionError` 分支
  只对 FILING 包装为 `FinsUploadFailureError`（带 primary 的 canonical label），material re-raise。
  测试矩阵（service / SEC / CN / runtime）均断言单次转换、整批零发布。
- **material 多转**：`converter_inputs = selection.files`（`:1027`），逐项转换；
  `test_execute_upload_material_converts_every_selected_file` 断言两文件全部转换、
  `primary_document == "first_docling.json"`、6 个文件事件。
- **取消中断**：见 D 节专项分析。prepare 阶段取消（loop-top raise 与 converter 抛出两条路径）
  均收敛为 `cancelled` 计划，已收集的 conversion_events 与 partial assets 随 `_build_cancelled_result`
  丢弃（`file_events=[]`）。
- **commit 取消**：`_store_upload_assets` 的 per-asset 与 final checkpoint 取消检查、
  `commit_prepared_upload_batch` 的线性化点均未被本 slice 触碰；回归测试
  `test_existing_replacement_cancellation_keeps_entire_published_tree`（cancel_at=2/4/5）、
  `test_commit_winner_ignores_cancel_after_ownership_transfer`、rollback evidence 测试全部通过。
- **行为收敛确认（对比基线）**：基线 filing 会把 companions 也送入 converter（所有文件全转换），
  并从 stored entries 后缀扫描 `_pick_primary_docling_file` 反推 primary。本 slice 按 frozen plan
  收窄为「filing 仅转 primary、material 全转」，`test_execute_upload_counts_only_successful_original_stores`
  的 entries 断言 4→3 与此一致，属计划内契约变更而非回退。

### C. conversion_started 与 file_uploaded 事件是否精确 —— 是

- `conversion_started` 仅在 `_build_pending_assets` 的 converter_inputs 循环内、converter 调用前
  追加（`:770-779`）：filing 恰一条（primary），material 每条各一条。companion 不产生
  `conversion_started` 也不产生 Docling 派生资产，只在 `_store_upload_assets` 的资产循环中产生
  `source="original"` 的 `file_uploaded`。
- 测试断言：`test_filing_converts_only_primary_and_publishes_all_companions` 断言
  `conversion_started == [names[0]]` 且 `original` 来源的 `file_uploaded == list(names)`；
  material 6 事件计数断言。取消/失败路径的事件随无发布语义整体丢弃，无泄漏。

### D. 新 DoclingConversionCancelledError 分支专项（首因/末因/cleanup）

- 关键事实（逐行对比基线确认）：`prepare_upload` 中的 `except DoclingConversionCancelledError`
  **在基线已存在**（基线 `:350`）；本 slice 的实际变更只有 loop-top 的 `break` → `raise`
  （当前 `:768-769`）与循环体索引化。
- 类层级：`DoclingConversionCancelledError` 是 `RuntimeError` 的直接子类，与
  `DoclingConversionError` 是兄弟类（`docling_process_converter.py:216,242`），因此
  **不可能**被循环内 `except DoclingConversionError`（filing 分支）捕获误投影为
  `FinsUploadFailureError`——取消优先级的 frozen typed priority 未被改变。
- cleanup：loop-top raise 发生在 `conversion_started` 追加与 converter 调用之前，无任何资源
  已分配；converter 自身抛出的取消异常按其契约「cleanup 完成后抛出」（`:399-401,509`），
  Service 层无资源需收口，catch 后直接返回 cancelled 计划。
- 首因/末因：raise 路径直接返回 `_build_cancelled_result`，跳过基线 `break` 后的第二次
  `_is_cancelled` 读（对真实 idempotent token 不可观测；对计数型 token 少一次读，无测试依赖此计数）。
  partial conversion_events/assets 被整体丢弃，与基线 post-check 路径最终结果一致。
- 观测分类回归测试：`test_upload_filing_observably_classifies_cancelled_docling_storage_and_generic`
  （converter 抛 `DoclingConversionCancelledError` → status `cancelled`、`UPLOAD_COMPLETED`、
  无 failure 字段、caplog 为空）与 service 级 `test_prepare_maps_shared_converter_cancel_without_starting_publication`
  均通过，证明取消未落为失败终态、未开启 batch。

### E. primary_document 是否始终首项转换产物 —— 是

- `_build_pending_assets:802-804` 在**首次成功转换**时赋值 `docling_name`；converter_inputs
  顺序即 ordered 顺序（filing 首项 primary / material 首文件），故 `primary_document` 恒为首项
  转换产物的 `stem + "_docling.json"`。文件名由输入 stem 派生，与被 store 的 asset.name 同源，
  不再从 stored entries 名称或顺序反推（`_pick_primary_docling_file` 已删除）。
- 同源一致性：`meta["primary_document"]`（`_create_source_document` 写入）与 result payload
  `primary_document` 为同一值，测试同时断言两者等于预期名。loop 空输入不可达
  `RuntimeError`（delete 提前返回；create/update 非空已前置校验）。

### F. failure enum kind-code JSON 是否 fail closed —— 是

- `_FAILURE_KIND_BY_CODE`（`upload_failure.py:177-184`）覆盖全部 11 个 code（1 usage + 7 content
  + 2 storage + 1 runtime），import 时以 frozenset 相等 guard 强制完整，缺失 code 直接
  `RuntimeError` 阻止模块加载。
- JSON parser：未知 kind/code 字符串在 enum 构造即 `ValueError`；已知 code 与 kind 错配经
  `_FAILURE_KIND_BY_CODE[code]` 比较拒绝（`:350-352`）。基线用 membership 条件算 expected kind
  （未知 code 落入 RUNTIME 分支），新映射语义等价且更严，无放宽。
- 新 USAGE 投影：`fins_upload_failure_from_exception` 首个分支（`:205-212`）将三个 role-specific
  `FinsUploadFormatError` 统一投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`，message/retry_hint 为固定
  有界 path-free 文案（20/15 字符），`file_label` 取 owner 产生并 canonicalize 的
  `error.file_label`（caller 传入的 `file_label` 被正确忽略——round-trip 测试用
  `file_label="ignored.pdf"` 反证）。
- 反例测试：`test_upload_failure_json_rejects_unknown_or_mismatched_kind_code` 覆盖
  content+usage code、usage+content code、usage+unknown code 三种反例；
  `test_unsupported_upload_format_reason_strict_json_round_trip` 断言 exact JSON 往返。
- 消费面无破坏：`FinsUploadFailureKind` 在 production 中无其它 closed-set 消费点，唯一读取方
  `ingestion_runtime.py:6498` 以 `kind.value` 通用投影，新 `usage` 值可安全流动。

### G. workflow material admission 位置与捕获 —— 通过

- SEC 与 CN 两条 material stream 的 typed selection 构造均是 `try` 块内**第一条语句**
  （`sec_upload_workflow.py:459-463`、`cn_pipeline.py:1074-1078`），严格先于
  `_safe_get_document_meta`（published-state 读）、`UPLOAD_STARTED` 事件、
  `stage_company_meta_for_upload`（company staging/batch）与 service 调用；
  `FinsUploadFormatError`/`ValueError` 被既有 `except Exception` → `fins_upload_failure_from_exception`
  捕获，产出 `UPLOAD_FAILED` 事件与 usage failure JSON，不产生 batch、不触碰公司元数据。
- 测试证据：SEC/CN 两条 `test_upload_material_unsupported_suffix_fails_before_reads_or_mutation`
  用 monkeypatch 把 published-state 读、`begin_batch`、`Path.read_bytes` 全部替换为必抛桩，
  断言事件流恰为单个 `UPLOAD_FAILED`、failure JSON 精确匹配 usage/unsupported_upload_format/
  `file_label=deck.zip`、converter 零调用、workspace 无 portfolio 目录。tools 级
  `test_upload_tool_raw_material_request_reaches_production_usage_failure_owner` 进一步证明 LLM
  tool 原始请求经 production runner 直达该 failure owner，无 adapter 旁路。
- 注：`delete + files` 仍静默忽略 files（`for_delete()` 空 selection），为 slice 2 acceptance
  明确排除的其它 work unit 历史行为，未越权改变。

### H. fresh selection 是否被消费 —— 是

- SEC/CN filing stream 将 `authoritative_request.file_selection`（workflow 内 fresh
  `validate_fins_upload_filing_request(raw_request, published_state=fresh_state)` 的产物，非入口
  preflight 的 selection）原样传入 service（`sec_upload_workflow.py:209`、`cn_pipeline.py:838`）。
- 测试证据：SEC/CN 各自 `test_upload_filing_consumes_fresh_authoritative_file_selection`
  monkeypatch 替换 fresh validator 产出的 selection 为不同文件，断言落盘字节与 converter 调用
  均来自替换后的 authoritative 文件——证明 workflow 未从 raw files 重建 selection。
- production 中 4 处 `prepare_upload` 调用点全部使用 `selection=`，无 `files=` 残留。

---

## Findings

### F1 [low，doc] `FinsUploadFailureReason.kind` 属性 docstring 未包含新 USAGE 分类

- **证据**：`dayu/fins/upload_failure.py:79` 仍写「content、storage 或 runtime 分类」，而
  `FinsUploadFailureKind` 已新增 `USAGE = "usage"`（`:31`）且 `fins_upload_failure_from_exception`
  会实际产出该 kind。
- **影响**：纯文档漂移，不影响运行时行为；但该 docstring 是 kind 语义的公开描述，
  与实现不一致会误导后续 owner 判断。
- **必要修复**：改为「usage、content、storage 或 runtime 分类」。

### F2 [low，doc] `_build_pending_assets` docstring Raises 未列出 DoclingConversionCancelledError

- **证据**：`docling_upload_service.py:752-756` Raises 仅列 `FinsUploadFailureError`/`RuntimeError`/
  `ValueError`；本 slice 新增的 loop-top `raise DoclingConversionCancelledError()`（`:769`）对
  filing 与 material **均可达**（token 在 read 窗口或多次转换之间翻转），且它是
  `RuntimeError` 的子类而非「material Docling 转换失败」——现有「RuntimeError: material Docling
  转换失败时抛出」与取消 raise 语义混叠。
- **影响**：CLAUDE.md 要求 docstring 完整声明异常；取消语义与转换失败语义被同一行 RuntimeError
  概括，误导读代码的人。
- **必要修复**：Raises 增加「DoclingConversionCancelledError: 转换前或转换间观察到取消时抛出」，
  并将 RuntimeError 行明确限定为 material 的 `DoclingConversionError` 透传。

### F3 [low-med，test] 新增 loop-top 取消 raise 分支无直接反例测试

- **证据**：本 slice 将 loop-top `break` 改为 `raise DoclingConversionCancelledError()`。现有
  取消测试只有两类：(a) `_CancelledDoclingConverter`——由 **converter** 抛出取消异常（服务级与
  workflow 级各一条，均为既有测试）；(b) `_CancelOnNthCheck(cancel_at=2/4/5)`——只注入
  `_publish_prepared_upload` 的 publish/commit 阶段，**没有任何测试**把计数型 token 传入
  `prepare_upload` 使 token 在 prepare 阶段翻转（单文件 read 窗口、或多文件 material 两次转换
  之间）。因此该新分支的三个可观察行为——不追加当前文件的 `conversion_started`、已收集事件与
  partial assets 随 cancelled 计划整体丢弃、不开启 batch——均无直接断言。
- **影响**：分支本身经分析与原 `break` 语义等价（最终结果同为 cancelled 计划），不构成
  correctness 风险；但它是本 slice 新增生产行，属「测试跟着实现边界迁移」的缺口。
- **必要修复**：补一条 prepare 阶段取消测试：material 两文件 + 计数型 token 在第二次
  loop-top 检查翻转（或 read 窗口翻转），断言 `status == "cancelled"`、`file_events == []`、
  `begin_calls == 0`、零发布树。

### F4 [low，test] material 多文件部分转换失败（第 N>1 个文件损坏）无反例测试

- **证据**：loop 重构后 material 的 re-raise 分支（`except DoclingConversionError: if
  source_kind is not SourceKind.FILING: raise`，`:787-789`）没有任何失败用例：service 级
  `_SelectiveFailingDoclingConverter` 仅用于 corrupt **primary** filing；runtime 级
  `_UploadRuntimeConverter(failing_stream_names=...)` 也仅覆盖 filing；material 测试矩阵只有
  成功路径（两文件全转换）与 suffix admission。workflow 级 material 转换失败 →
  `CONTENT/xxx`、`file_label=None` 的投影同样无覆盖。
- **影响**：该路径自基线未变（非回归），但 material 全转换语义由本 slice 正式确立，且循环体
  本轮重构（索引化 + 前缀校验），部分失败时「前序 conversion_started 事件被丢弃、零发布、
  失败事件无文件归属」是本契约的核心反例，缺测即失去对该边界的持续保护。
- **必要修复**：补一条 service 级（或 SEC/CN workflow 级）用例：material
  `[ok.pdf, corrupt.docx]`，断言 `DoclingConversionError` 传播（或 workflow 终态
  `content` failure、`file_label=None`）、converter 调用序为 `[ok.pdf, corrupt.docx]`、
  零发布。

### F5 [info，handoff] `dayu/fins/README.md:201` 仍引用已删除的 `FINS_UPLOAD_FILE_SUFFIXES`

- **证据**：README 第 201 行仍写「公开常量 `FINS_UPLOAD_FILE_SUFFIXES` 是 upload 输入后缀真源」，
  该符号自 Slice 2 已删除。implementation artifact 的「零引用」审计只覆盖 Python 文件。
- **影响**：文档与实现不一致；README 同步已被 accepted plan 归属 Slice 4，且用户本轮明确禁止
  改 README，故不构成 Slice 3 blocking，登记为 Slice 4 交接项。
- **必要修复**：Slice 4 统一同步 README 时删除或改写该引用。

---

## 项目指令与范围审计

- 语义所有权：selection 由 `upload_format_contract` 唯一产生，Service 只消费 closed typed union 并
  显式拥有 `primary_document`；格式错误唯一经 `upload_failure` 投影，workflow 不重建 selection、
  不重分类 failure（`reject_workflow_reclassification` 反例测试继续存在）。未发现下游 fallback/
  hasattr/getattr/兼容分支；diff 无 `Any/object` 签名。
- 分层与目录：改动全部落在既有 owner 边界内；无 `dayu.runtime` 反向依赖；无新 helper 重复实现。
- 修改范围：workspace diff 恰为 Slice 3 允许的 11 个文件 + 2 个 gateflow artifact；未触碰
  registry、oracle/scenario、design doc、README、冻结 evidence。
- 无魔法数字/字符串；新增文案为 bounded、path-free、LLM-facing 自足（usage message 与 retry
  hint 均为固定文案，label 来自唯一 canonicalizer）。
- 未发现 UF-FIX07（显式 primary、重复、collision）范畴被越权实现。

## Residual notes（不阻塞，供 Controller 参考）

- `test_prepare_upload_rejects_source_kind_selection_mismatch_before_io` 与
  `test_prepare_upload_rejects_action_emptiness_mismatch_before_io` 的 monkeypatch 桩签名
  （`reject_read`）对 `Path.read_bytes` 的替换是全局性的，属测试技术而非语义造假，可接受。
- `_FAILURE_KIND_BY_CODE` 的 frozenset guard 能保证「完整」，但「唯一」仅靠四组 set 的模块内
  私有构造约定（merge 覆盖重复 key 不会被 guard 检出）；当前四组集合肉眼可证无交集，风险极低，
  记录备查。
- `_prepare_upload_selection` 的「converter_inputs 保持 ordered_files 前缀顺序」校验在
  `_build_pending_assets:765-766` 复检，属内部不变量防御，当前构造下不可达，保留合理。
