# UM-O14/O15 state plan PR-C4 独立 plan re-review（MiMo 修复性复审）

- RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
- Review target：`/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`
- Target SHA-256：`1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`（本机 `shasum -a 256` 实测，与任务锁定值一致）
- Review mode：只读 adversarial `$planreview`。唯一新增本 artifact；不实施 state/O12，不修改 plan/goal/旧 review/裁决/产品/测试/README，不 commit/push/PR/merge，不派发子 Agent。
- Scope：重点以一手代码反证 PR-C4-F1 的 format owner 角色/公共文案、hint、canonical label 事实，统一 usage producer 装箱边界、hint 全 code 必填校验、`upload_failure.py` 唯一 public 映射、tool `invalid_argument` 与 direct/实际可达 awaited 同源；PR-C4-F2 的 alias/public reason 测试白名单与 focused 命令；兼审 O12/O34/UM-A09/F8–F11、三态目标动作表、公司/材料 guard、O16/O05 等实施硬依赖是否成立或回退。
- 本机时钟戳：2026-09-29 19:43:04 +0800（`date` 实测；artifact 文件名按任务指定固定，不使用自动时间戳命名）。

## 预检与版本锁定（一手证据，除披露项外检查命令自身 exit 0）

| 检查项 | 一手结果 |
| --- | --- |
| state plan SHA-256 | 实测 `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`，与锁定一致 |
| O12 accepted checkpoint | `git cat-file -t b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c` 为 `commit` |
| checkpoint 内 O12 plan SHA-256 | `git show b201d9f3:docs/gateflow/upload-material-o12-company-plan-20260929.md` 实测 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`，与锁定一致 |
| O12/state 产品未实施 | `rg "MaterialUploadPublishedState\|upload_usage_contract" dayu/ tests/` 无匹配（预期无匹配，记录为正向证据）：accepted plan 的状态类型与 usage contract 模块在本 checkout 不存在，plan「待实施／产品未集成」定性准确 |
| 工作树基线 | HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，与 plan 自述读码基线一致；goal/plan/fix/裁决/review 均为未跟踪文档 |

已读文档：workspace `AGENTS.md`、binding goal `docs/gateflow/upload-material-state-goal-20260929.md`、总控裁决 `docs/gateflow/upload-material-state-plan-review-adjudication-20260929.md` 全文（含末节 PR-C4 复审与本轮修复性重派登记）、Sol `docs/gateflow/upload-material-state-plan-prc4-fix-20260929.md`、Kimi 同版 `docs/reviews/plan-review-state-prc4-kimi-20260929.md`、MiMo 旧版 `docs/reviews/plan-review-state-prc4-mimo-20260929.md`、state plan 全文、O12 accepted plan（checkpoint 内 blob 关键节），以及本 checkout 的 `dayu/fins/upload_failure.py`、`dayu/fins/upload_format_contract.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/tools/_ingestion_tool_helpers.py`、`dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/pipelines/filing_upload_publication.py`、`dayu/fins/storage/_fs_source_document_core.py`、`dayu/cli/commands/fins.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_company_identity_storage_contract.py` 相关区域。

## Assumptions Tested（逐条独立反证）

1. **PR-C4-F1 的现状反例真实，plan 未虚称既有 API。** 成立。`ingestion_runtime.py:707-741` 的 `FinsUploadUsageFailure` 仅 `code/message`，`code` 为 `FinsUploadUsageCode | FinsUploadFormatFailureKind`；`fins_upload_usage_failure`（:1062-1097）只查 `_USAGE_MESSAGES`（仅普通 code）；`_raise_upload_format_usage`（:1121-1134）直接 `FinsUploadUsageFailure(code=error.kind, message=str(error))` 构造 fact 绕过 producer；format 的 `hint/public_message/file_label` 与统一 producer 均为待实施新增。plan §5「现状反例与待实施 producer 边界」与代码逐句吻合。
2. **format owner 的角色/公共文案、hint、canonical label 事实成立。** 成立。`upload_format_contract.py:26-31` 三个 role 模板与有界文案、:41-58 三个 role-specific kind、:85-111 `FinsUploadFormatError` 自带 `kind/file_label` 且构造时经 `validate_fins_public_file_label` 校验（:108）、:137-150 `_safe_file_label` 经 `canonicalize_fins_public_file_label` 产生标签。canonicalizer/validator 算法唯一真源在 `direct_events.py:1080/:1100`，format contract 只产生并校验携带值——plan「由唯一 canonicalizer 产生并验证的非空 public label」与该分工一致。plan 引用的既有 public 通用文案「文件格式不受支持，请选择支持的文件后重试」与 retry hint「请查看上传帮助中的支持格式后重试」逐字存在于 `upload_failure.py:236-237` 的 format 分类分支，plan 把其生产收回 format owner、producer 装箱、mapper 消费，消除真实第二文案源，方向正确。
3. **hint 全 code 必填与 path-free 校验分层和代码约束精确对齐。** 成立。`upload_failure.py:519-536` 的 `_validate_failure_reason_text` 对 public reason 的 `message/retry_hint` 禁空、超长、控制字符、`/`、`\`；而既有 `_USAGE_MESSAGES` 中 `MISSING_FILES`（:1049）含字面 `create/update`、日期文案（:1045-1046）含 `YYYY-MM-DD`，现有测试 `test_fins_ingestion_runtime.py:1467-1468` 也只禁 `/Users/` 与反斜杠而非一切斜杠。plan 把 path-free 限定在映入 public reason 的 target/format `public_message`，fact 层 message 保留字面斜杠、hint 对全部 code 禁斜杠，既满足 `retry_hint` 既有校验又不误伤 filing 既有文案，无冲突。
4. **`upload_failure.py` 唯一 public 构造/映射成立且可保持。** 成立。全 `dayu/` 15 处 `FinsUploadFailureReason(` 构造均在该文件（rg 实测）；`FinsUploadFailureCode`（:37-54）当前无 target 码，USAGE 分组仅 `UNSUPPORTED_UPLOAD_FORMAT`（:179-181）；新增三 target 码「全部且仅归 USAGE」是对封闭分组（:199-208 完整/互斥校验）的合法扩展；`retry_hint`/`file_label` 为既有字段，JSON exact-key round-trip 由 `upload_failure_reason_from_json`（:443-474）承载；`fins_upload_failure_from_exception` 现无 `FinsUploadFailureError.failure` 直通分支，plan 列为待实施与 O12-PR4-F1 接续，非本 WU 私造。
5. **tool `invalid_argument` 与 direct/实际可达 awaited 同源可达。** 成立。`upload_tools.py:50/58-60/117-124` 现状：无 typed 分支，`FinsUploadUsageError`（ValueError 子类）落通用 `invalid_argument` + 通用 hint；`_ingestion_tool_helpers.py:55-92` 的 tool 失败形状为 `error/message/hint`，无 Fins code、无 file_label 字段——plan「只取 fact.message/hint、保持 `invalid_argument`、不增 Fins code/file_label」无需改 tool 协议即可落实，与 F11 裁决一致。CLI `dayu/cli/commands/fins.py:198-200` 既有 `except FinsUploadUsageError → exc.failure.message → EXIT_USAGE_ERROR`；runtime admission（`ingestion_runtime.py:4714-4744`）在 producer/job/observation 前执行，稳定拒绝不建 job/observation，「不造任务测不可达 awaited 分支」与结构一致。
6. **usage producer 装箱合同存在 kind 维度缺口（见 Finding 1）。** 不成立的部分：plan §5 同时要求 filing 两 target 码文案逐字保持、material 三码说明「目标材料…」，但 producer 合同只写「接受普通 usage code 或 `FinsUploadFormatError`」，未含 source kind 入参，`_USAGE_MESSAGES` 现为一码一文案，无法同码产出两种文本。
7. **PR-C4-F2 修复属实。** 成立。`tests/fins/test_company_identity_storage_contract.py:636-670` 的 `test_alias_conflict_and_corruption_have_distinct_bounded_upload_projection` 真实断言 alias conflict→`TICKER_ALIAS_CONFLICT`、corruption→`STORAGE_IO`、精确文案、`file_label is None` 与 `upload_failure_reason_from_json(conflict.to_json()) == conflict`；plan S1（§切片表）与 S2 测试白名单、§验证命令两条 focused pytest（含 `--cov` 版）均已列入该文件，owner 测试要求含 alias/漂移优先级与 strict JSON round-trip。
8. **O12 依赖成立且锚定 accepted plan。** 成立。checkpoint/blob SHA 实核一致；O12 accepted plan 明文规定同版 `MaterialUploadPublishedState`（COMPLETE tombstone 保留 `is_deleted=true`、`deleted_at`、`document_version`、`first_ingested_at`、`created_at` 等完整可信 business meta 与独立 opaque revision，`MISSING`/`UNSAFE` 公开 meta/revision 为 None）、typed admission/公司决策、公司独立 commit outcome、材料自身 batch/skip guard（expected source + post-company meta，单一 `MaterialUploadPublishedStateConflictError` 在 material 语境投影 `source_publication_conflict`）、alias 在 company commit 最终检查且 alias 优先于漂移、O12-PR4-F1 的 `FinsUploadFailureError.failure` 直通与 material/filing 分类、O12-PR4-F3 的 upload job typed 终态双摘要（`_save_failed_from_exception`/`_save_failed` 保持 preprocess/download 旧投影）——与本 plan §依赖核对清单逐项对应。本 checkout 的 `save_*_if_active` 家族（`ingestion_runtime.py:2104/2126/2154` 等）已存在 active-only 终态保存 API，plan 的「active-only 原子终态」措辞指该既有 API 族与 O12-PR4-F3 的组合，不是凭空名词。产品未实施与 rg 零匹配一致。
9. **O34/UM-A09/F8–F11、三态表、原子 guard 无回退。** 成立。`_resolve_document_version`（`docling_upload_service.py:1745-1770`）同指纹保留旧版本、异指纹（或非 identical-safe）递增，支持 F10 两格矩阵；`_can_skip_upload`（:1616-1643）`overwrite` 即禁 skip、tombstone 禁 skip，支持「create --overwrite 同内容仍发布、同内容 tombstone auto 恢复不 skip」；`evaluate_upload_overwrite_precondition`（:259-285）现为二元判定，plan 明确其未来纯输入扩为 kind×三态且列为待实施；`prepare_upload`（:447-465）delete 不经 precondition、create 拒绝仅 filing（:462）、update 拒绝 `FileNotFoundError` 迟发（:465），与 plan 现状表一致；material tombstone create 无 overwrite 现行走 `_upsert_source_document` 的 `meta_path.exists()`→`FileExistsError`（`_fs_source_document_core.py:1707/1747-1749`），plan 记为既有拒绝而非新 typed 规则，与 F1 裁决一致；filing 侧「接收后漂移→`source_publication_conflict`」已有 `_STATE_DEPENDENT_USAGE_CODES` 先例（`filing_upload_publication.py:71-78/747-751`，状态相关 usage 码在重验时统一改报 conflict 而非 usage），支持 plan §4 的接收后语义；SEC material stream `UPLOAD_STARTED`（`sec_upload_workflow.py:502）先于公司 batch（:523-536）再材料 batch（:565），与 goal 时序动机一致；filing admission 目标检查（`ingestion_runtime.py:1506-1514`）先于公司名决策（:1517），支持「目标错误不被缺名遮蔽」的既定顺序。
10. **O16/O05 等依赖接缝真实，plan 未猜未实施 API。** 成立。`FinsUploadMaterialFiles.from_upsert_paths/for_delete`（`upload_format_contract.py:486/506`）、`build_material_ids`/`validate_material_upload_ids`/`_normalize_optional_upload_fiscal_period`（`docling_upload_service.py:1820/1859/2027`）均在；plan 将其表述为「本读码基线定位点，不是未集成修复的 API 承诺」，并固定「静态字段/文件组合 → exact 目标动作状态 → O12 公司名称决策 → lifecycle」顺序，与 O12 accepted plan 的集成顺序节一致。

## Findings

### 1-未修复-低-usage producer 装箱合同缺 source kind 维度，同码双文案无法由合同产出
- **位置**: plan §「最小设计与唯一 owner」第 5 项「现状反例与待实施 producer 边界」段（producer 合同句）与同项「material 三码分别说明…filing 既有 create/update 文案逐字保持」句。
- **问题类型**: 契约缺失／不可直接实施。
- **当前写法**: 「producer 明确接受普通 usage code（含全部既有码和三 target）或已由 format owner 校验的 `FinsUploadFormatError`」，文案「仍由唯一 `_USAGE_MESSAGES` 产生」；同时要求 material 三码说明「create 目标材料已存在、update 目标材料不存在、delete 目标材料不存在」，且「filing 既有 create/update 文案逐字保持」。
- **反例/失败场景**: `CREATE_TARGET_EXISTS`/`UPDATE_TARGET_MISSING` 是 filing/material 共享 code（plan 自身「保留前两码」）。现有 `_USAGE_MESSAGES` 一码一文案：`create 目标已存在；请改用 update 或允许覆盖`／`update 目标不存在；请改用 create`（`ingestion_runtime.py:1054-1055`），已由 filing admission 逐字消费（:1511-1514），且代码既有文案惯例区分「目标 filing」（如 `EXISTING_SOURCE_REPAIR_REQUIRES_AUTO`、`fins_upload_source_publication_conflict_failure` 的「目标 filing 在上传准备期间…」）。实施者若按 §5 producer 合同字面实现（只收 code/format error），material 消息只能复用通用文案，不满足「目标材料…」；若改共享文案则破「逐字保持」；若在 precondition/CLI/tool 另写 material 文案表则破「唯一 `_USAGE_MESSAGES` 产生」并复活第二文案源。
- **为什么有问题**: 合同输入集无法支撑合同输出集，implementation agent 必须自行重设计 producer 签名或违规补偿，正中本轮「统一 usage producer 装箱」的审查焦点；两种走偏都会在 tool/CLI 的 LLM-facing 文案上留下不明确动作语义或双真源，违反 AGENTS 语义所有权约束。
- **直接证据**: plan §5 上述两句；`ingestion_runtime.py:1027-1059`（一码一文案表）、:1511-1514（filing 抛出点）、:702-703（共享 code）；`tests/fins/test_fins_ingestion_runtime.py:1434-1470`（现行测试按码锁精确文案、无 kind 维度）。
- **影响**: 实施 Agent 跑偏（第二文案表或错误共享文案）／tool 与 CLI 文案不达「目标材料」动作明确性／返工 producer 与全部引用。
- **建议改法和验证点**: 在 §5 producer 合同处显式写入 source kind（或等价目标名词选择器）作为装箱入参，`_USAGE_MESSAGES` 对两个共享 target 码按 kind 分文案（material 用「目标材料…」、filing 原文逐字），DELETE_TARGET_MISSING 仅 material；测试锁「同一 code 两 kind 双文案」与「filing 原文案逐字不变」两组断言。
- **修复风险（低/中/高）**: 低（仅 plan 文案与后续测试矩阵精确化，不动方向）。
- **严重程度（低/中/高/严重）**: 低。

无其它 material finding。PR-C4-F1/F2 的修复目标经一手代码逐项反证成立；停止条件（SHA 漂移、format/usage/public 同源无法由真实 API 支持、O12 依赖不成立）均未触发；O12/O34/UM-A09/F8–F11、三态动作表、公司与材料 guard、O16/O05 依赖未发现回退或新反例。

## Open Questions

- OQ-M1（低）：§5「fact 在 owner 构造时拒绝缺失/非法字段；`FinsUploadFailureReason` 再按既有 public contract 校验，不允许 optional hint 或消费者 fallback」中「不允许 optional hint」的落点有歧义。fact 的 `hint: str` 必填无歧义；但 `FinsUploadFailureReason.retry_hint` 现为 `str | None`（`upload_failure.py:93`）且 `UNEXPECTED_RUNTIME` 等既有 reason 使用 `None`（:284）。若实施者误收紧 reason 级必填，将破坏既有构造与 JSON 往返。建议下一修订点明：仅 fact hint 必填，reason 级 `retry_hint` 保持既有 optional 合同，target/format 映入时才非空。
- OQ-M2（低）：raw `FinsUploadFormatError` 在 CLI 的 material file selection 边界仍可先于 typed producer 出现（`dayu/cli/commands/fins.py:201-203` 现有独立 raw 捕获，渲染 role 文案但无 hint；:1138/1147 直接构造 `FinsUploadMaterialFiles`）。S1 的 CLI/tool typed fact 断言必须覆盖该实际入口并消费同一 message/hint（或明示由共享 validator 接管后 raw 分支退役），不能只测 runtime `_raise_upload_format_usage`（承接 MiMo 旧 OQ，补行号证据）。
- OQ-M3：canonicalizer/validator 算法 owner 是 `dayu/fins/direct_events.py:1080/1100`，format owner 装入并校验携带值。实施时须保持单一算法真源与逐值透传，不得在 format/usage/public mapper 复制 canonicalization 规则；若总控要求字面上的「format owner 独占算法」，应先裁决是否迁移全部调用点，不能用 re-export 表面满足。

## Residual Risks And Tracking

- O12 accepted plan 尚未实施/集成（本 checkout rg 零匹配实证）；实际 `MaterialUploadPublishedState`、typed admission、公司独立 commit outcome、材料 writer-owned guard、alias 优先级与 active-only 终态 API 可能与 accepted plan 漂移。跟踪去向：O12 implementation gate + state plan §停止条件（漂移即回 O12 owner/本 plan gate）。
- `FinsUploadFailureError.failure` 分类器直通为 O12-PR4-F1 待实施项；S2 的 material conflict 投影依赖它随 O12 落地。跟踪去向：O12 implementation gate。
- 冻结 A04 不覆盖「已有不同内容 create」真实 CLI 证据；补跑前不能声称修复可用。跟踪去向：state implementation gate 真实 CLI 矩阵（plan 已列必交新证据）。
- material tombstone create 无 overwrite 维持现有 `FileExistsError`→storage 拒绝、`REPAIR_REQUIRED`/`UNSAFE` repair 授权未裁决、O13 时间幂等/O18/O33/tombstoned create 属各自 WU。跟踪去向：对应 goal/work unit。
- 其余既有 usage code 若集成后可达 public failure，需回 plan/schema 裁决新增 public code，不得映 `storage_io`/`unsupported_upload_format`。跟踪去向：plan §停止条件。
- O12 checkpoint `b201d9f3` 非本 checkout HEAD 祖先（相邻分支快照，Kimi 已披露拓扑）；对象/blob SHA 已核，锁定效力不受影响。跟踪去向：总控登记，无需动作。
- 本 review 为 plan review，未运行 pytest/pyright（属未来 implementation gate），不授权实施。

## Execution Notes（合规与偏差披露）

- 除下述一条外，全部检查命令自身 exit 0；两处预期无匹配的 `rg`（`MaterialUploadPublishedState|upload_usage_contract`）以 `|| true` 归一退出码，并按任务约定把「无匹配」记录为 O12/state 产品未实施的正向证据。
- 偏差披露：一条复合命令 `rg -n "def _failed_outcome" … && sed …` 因内层 `rg` 在 `upload_tools.py` 无定义点匹配而 `&&` 短路 exit 1；未从该命令得出任何结论，随即改用安全写法（`rg … || true`）定位 `_failed_outcome` 真实定义于 `dayu/fins/tools/_ingestion_tool_helpers.py:55` 并完成核证。
- 未派发子 Agent；未 commit/push/PR/merge；未运行故意失败的差异/反例测试；未改 plan/goal/旧 review/裁决/产品/测试/README；唯一新增文件为本 artifact。

## Final Plan Review Conclusion

`pass-with-risks`

PR-C4-F1/F2 的计划修复经一手核证成立：format owner 对角色 message、既有 public 通用 message/hint 的生产与 canonical `file_label` 的携带/校验可由 `upload_format_contract.py` 真实承载（算法唯一真源 `direct_events.py`）；统一 usage producer 装箱 + hint 全 code 必填/分层校验 + `upload_failure.py` 唯一 public 映射（15/15 构造点单文件实证）+ tool `invalid_argument`/direct/可达 awaited 同源，均与现行代码结构相容且未虚称既有 API；alias/public reason 合同测试已入 S1/S2 白名单与两条 focused 命令。O12 依赖锚定 accepted plan（checkpoint `b201d9f3`/plan SHA `48e0598b…` 实核，合同逐项在案，产品未集成实证），O34/UM-A09/F8–F11、三态动作表与公司/材料 guard 无回退，O16/O05 等依赖以定位点而非 API 承诺表述。新增 1 项低 finding（usage producer 装箱合同缺 kind 维度，含一手双文案反例）与 3 项 OQ，均不推翻「计划内容候选已修」，但应由总控裁决后在实施前或下一修订精确化。本 review 不授权实施：O12 accepted+integrated 仍是 S1/S2 硬门槛，实施前须按 plan §停止条件实读 O12 最终 API 复核。

## 最终 canary、结论与绝对路径

- CANARY=mimo-4d4e69a4
- 结论：`pass-with-risks`
- Review artifact（本文件）：`/private/tmp/dayu-upload-state/docs/reviews/plan-review-state-prc4-mimo-rereview-20260929.md`
- Review target：`/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`（SHA-256 `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`）
- O12 依赖锚点：checkpoint `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c` 内 `docs/gateflow/upload-material-o12-company-plan-20260929.md`（SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`）
