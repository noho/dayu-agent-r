# Code Review

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-392999d9

- Reviewer：MiMo 独立 deepreview（UM-O11-CR-F1 根 README 修复复审）
- Review 时间：2026-09-29
- 独立性声明：本 review 的全部结论只依据当前工作树的 README diff、CLI/Fins/tool owner 代码逐行走读、本 reviewer 自行运行的只读验证脚本与测试；不以 `docs/reviews/code-review-20260929-094352-o11-mimo.md`、`code-review-20260929-092732-o11-kimi.md` 或任何其它评审结论作为证据。MiMo 原 finding 仅作为被复审对象读取，其断言均独立反证。

## Scope

- Mode: current changes（定向复审 O11-CR-F1 README 修复；任务指定输出文件名 `code-review-o11-readme-rereview-mimo-20260929.md`，覆盖 deepreview 默认 timestamp 命名）
- Branch: `codex/upload-material-o11`（无 PR；候选保持未提交）
- Base: HEAD `9141b5e9c65caaf52416f177a2641f8a7e1134ad`；本轮 target 为 README 修复后工作树状态
- Output file: `docs/reviews/code-review-o11-readme-rereview-mimo-20260929.md`
- 边界文档：`docs/gateflow/upload-material-o11-dates-plan-20260929.md`（accepted plan，含 R1/R2/R3 残余边界）、`docs/gateflow/upload-material-o11-s1-code-review-adjudication-20260929.md`（O11-CR-F1 裁决）、`docs/gateflow/upload-material-o11-s1-readme-fix-20260929.md`（修复记录）、根 `README.md` 的 `Agent更新约束`、`AGENTS.md`
- Included scope：
  - 复审对象：根 `README.md:382-395` 日期段修复 diff（`git diff README.md` 仅此一个 hunk）
  - owner 反证走读（只读）：`dayu/cli/commands/fins.py`（`upload_filing`/`upload_material` 日期投影、`_optional_material_date_text`、usage 退出码投影）、`dayu/cli/arg_parsing.py`（日期参数无归一化）、`dayu/fins/ingestion_runtime.py`（`_validate_fins_upload_filing_static:1288-1289`、`_validate_optional_upload_iso_date:1372-1394`、`_normalize_upload_request:7708-7717`、`_USAGE_MESSAGES:1045-1046`）、`dayu/fins/domain/filing_semantics.py`（`parse_iso_calendar_date:375-404` 与 `_STRICT_ISO_CALENDAR_DATE_PATTERN:57-60`）、`dayu/fins/tools/upload_tools.py`（`_optional_raw_nullable_text`、两日期字段 schema 描述）、`dayu/fins/pipelines/docling_upload_service.py`（`_build_upsert_meta:288-325` meta 合并）、`dayu/fins/pipelines/sec_upload_workflow.py`（meta/事件日期投影）、`dayu/fins/domain/document_models.py`（`MaterialManifestItem.from_source_meta/to_dict`）、`dayu/cli/exit_codes.py`
  - 边界核对：`git diff --check`、根 README SHA-256、8 个 modified 文件与 accepted plan 允许清单比对、六个产品/测试文件 `git diff` SHA-256
  - 只读验证：owner 函数级真值表脚本、null 投影链脚本、focused pytest 714、pyright
- Excluded scope：
  - 其它评审 artifact 的结论（按任务要求不作证据）
  - `upload_filings_from` 扫描/脚本元数据路径（plan 残余 R1，README 明确排除）
  - O05/O16 共享 admission 并发变更（plan 残余 R3，未进入本 HEAD）
  - UM-O12 相邻问题（与本 diff 无关）
  - 非目标：不修改计划、产品、测试、README、旧 artifact（本轮仅产出本文件，未越界）
- Parallel review coverage: 无（任务禁止派发子 Agent；全部走读与验证由本 reviewer 单路完成）

## Findings

对 O11-CR-F1 的逐格反证结论如下（finding 编号沿用总控裁决）：

### O11-CR-F1-已修复-低-根 README 日期空值规则丢失 upload_filing 拒绝承诺且与 CLI 折叠行为表述冲突

- **裁决**: **已修复，验证通过**。原 finding 两个子缺陷均被消除，且未偷增产品承诺、未引入新误导。
- **原 finding 子缺陷 (a)——`upload_filing` 空串/纯空白拒绝承诺丢失**：新文案 `README.md:389-390`「CLI 的 `upload_filing` 两个日期参数若传入空串或纯空白，也会作为用法错误拒绝」显式恢复该承诺。反证：`dayu/cli/commands/fins.py:695-696` 对 filing 日期 `args.filing_date`/`args.report_date` 原文直传（无折叠 helper）；`dayu/fins/ingestion_runtime.py:1288-1289` 经 `_validate_optional_upload_iso_date` 校验，helper 仅跳过 `None`（`:1389-1390`），`""`/纯空白进入 `parse_iso_calendar_date`（`filing_semantics.py:391-393` ASCII fullmatch 失败）→ `INVALID_FILING_DATE`/`INVALID_REPORT_DATE` → `FinsUploadUsageError` → `run_fins_direct_command` 投影 `EXIT_USAGE_ERROR`（`fins.py:198-200`，`exit_codes.py:9` 即 `2`）。本 reviewer 以 owner 函数直调复现：`''`、`' '`、`'  '` 均 typed 拒绝。
- **原 finding 子缺陷 (b)——通用「若填写」句与 `upload_material --report-date ""` 折叠冲突**：新文案 `README.md:386-388` 将格式要求限定为「若提供非空日期」，空值不再落入该句；`README.md:392-394` 单独陈述 CLI `upload_material` 折叠现状。反证：`fins.py:736-737` 经 `_optional_material_date_text`（`:1279-1289`，`None`/纯空白折叠 `None`、非空原文不 trim）构造 request，早于 admission。本 reviewer 直调复现：`''`/`' '`/`'  '` → `None`；`' 2024-02-29 '` 原文保留。冲突消除。
- **是否偷增产品承诺**：无。逐句核对——(1)「若提供非空日期，必须是实际存在、月日补零且无首尾空白的 `YYYY-MM-DD`，完整日期年份允许 `0001..9999`」：正则 `[0-9]{4}-[0-9]{2}-[0-9]{2}`（月日补零）+ `datetime.date` 存在性 + isoformat 回写（年份 0000 被 `datetime.date` 拒绝，故 0001..9999 成立），与 admission 行为一致；(2)「非补零日期、不存在的月日、带首尾空白的非空日期拒绝」：本 reviewer 复现 `'2024-2-29'`、`'2025-02-30'`、`' 2024-02-29 '` 全部 typed 拒绝；(3)「`--filing-date ""` 保持既有支持，保存时为 `null`」：仅此一个是 accepted plan R2 授权的例外，null 投影经本 reviewer 独立验证——`_build_upsert_meta`（`docling_upload_service.py:288-325`）对 `base_meta` 中 `filing_date=None` 全量写入（update 同样落 `null`，与省略参数等价）→ source meta JSON `null` → `MaterialManifestItem.from_source_meta`（`document_models.py:1071-1072`）→ `to_dict` 显式 `null`，即 meta 与 manifest 同源同值；(4) `report_date` 空值只写「当前会……视为未提供」（`当前` 限定现状）并引导「请直接不传对应参数」，未写成受支持用法，符合裁决「不把 material 其它空值折叠提升为新的产品承诺」；(5) `upload_filings_from` 排除句保留，R1 边界未变。
- **是否仍有误导**：无实质误导。两个 CLI 命令 × 两字段 ×（空串/纯空白/非空非法/合法/省略）的真值表在文案中逐格有主：filing CLI 空值拒绝、filing/tool 非空非法拒绝、tool 空值拒绝、material CLI 空值折叠（仅 filing-date `""` 标注既有支持）、省略即未提供（「可选的」+ tool schema「省略或填 null 表示未提供」）。经全文 grep「空串/纯空白」，无其它段落与本段冲突。
- **修复范围**：`git diff README.md` 仅日期段一个 hunk，与裁决「修复仅限根 README 这一段」一致；未触碰产品、测试、其它 README、计划或旧 artifact。
- **严重程度（低/中/高/严重）**: 低（与原 finding 一致；用户文档准确性问题，行为本身方向正确）。

### 新增 finding

未发现实质性问题。

## Open Questions

- 无阻塞性 open question。CLI material 空/纯空白折叠（含 `--report-date ""`）是否升级为稳定产品契约仍属 plan 残余 R2 的独立裁决事项，本 review 不代为裁决。

## Residual Risk

1. **R2 边界（既有）**：CLI `upload_material` 除 `--filing-date ""` 外的空值折叠（`--report-date ""`、两字段纯空白）在 README 中只以「当前会……」陈述并引导省略参数；若未来 R2 裁决收紧为空值拒绝，本段文案需同步修订。文案未承诺这些折叠稳定，风险已收窄。
2. **`保存时为 null` 的 action 边界（措辞级）**：该句紧邻 `--filing-date ""` 例外，create/update 均经 `_build_upsert_meta` 全量投影 `null` 验证成立；`delete` 不携带日期字段、不写日期 meta（`_PreparedDeleteMutation`，`docling_upload_service.py:171-176`），该句对 delete 为空集陈述，不构成误导，但未显式限定 action。update 下空日期会把既有日期覆盖为 `null`（与省略参数等价），属既有 update 全量替换语义，非本修复引入。
3. **测试缺口（既有，非本修复引入）**：CLI 纯空白折叠（`--filing-date " "`）与 `--report-date ""` 折叠未被 `tests/cli/test_fins_commands.py` 新增投影测试覆盖（现覆盖 `--filing-date ""` 与两处非空保真）；两日期同时非法时 `filing_date` 优先的错误顺序未被测试固定。本修复为纯文档、按非目标未改测试，缺口保持登记。
4. **验证边界**：本轮未做 fresh 真实 CLI 端到端实跑（README 修复为纯文案，逐格行为由 owner 函数直调 + focused 测试证明）；未覆盖 CN/HK 真实网络发布。`upload_filings_from`（R1）与 O05/O16 集成（R3）在既有残余范围。

## 验证记录（本 reviewer 实际执行）

- **目标 SHA**：`shasum -a 256 README.md` → `c1cd17458804aa6415beccb03320dd0b2d922df89de596019f81534208775dc3`，与任务 target 逐字匹配，无 drift，未触发停止条件。
- **`git diff --check`**：exit `0`，无空白错误。
- **diff 边界**：`git status`/`git diff --stat` 显示 modified 8 文件 = accepted plan 允许清单（生产 3 + 测试 3 + `dayu/fins/README.md` + 根 `README.md`），README 修复 hunk 仅日期段。六个产品/测试文件 `git diff` SHA-256 = `3c5261daba2736581fc61848749462862c40baf8cdbbc504506e608d53284ee9`，与修复记录声明一致（本轮未改代码/测试，无越界）。
- **真值表反证（owner 函数直调，非测试夹具）**：`''`/`' '`/`'  '`/`' 2024-02-29 '`/`'2024-2-29'`/`'2025-02-30'` → `parse_iso_calendar_date` 全拒绝、`_validate_optional_upload_iso_date` 全 typed 拒绝（`INVALID_FILING_DATE`）；`'2024-02-29'` 接受；`None` 跳过。`_optional_material_date_text`：`''`/`' '`/`'  '`/`None` → `None`，非空原文（含 padded）逐字保留。与 README 逐格一致。
- **null 投影链（只读脚本）**：`_build_upsert_meta(base_meta={"filing_date": None, "report_date": None})` → merged 两字段 `None`；update 场景（previous 有日期）同样覆盖为 `None`；`MaterialManifestItem.from_source_meta(...).to_dict()` 两字段 `None`；JSON 序列化为 `null`。meta 与 manifest 同源。
- **测试**：`tests/cli/test_fins_commands.py` + `tests/fins/test_fins_ingestion_tools.py` → **269 passed**；`tests/fins/test_fins_ingestion_runtime.py` → **398 passed**；`tests/fins/test_sec_pipeline_upload_material_stream.py` + `tests/fins/test_cn_pipeline.py` → **47 passed**；合计 **714 passed**（3 条 edgartools deprecation warning），与既有记录一致。
- **pyright**：`python -m pyright dayu/ tests/ utils/` → **0 errors, 0 warnings, 0 informations**。
- **原文引用核对**：修复记录所引行号（`fins.py:695-696`、`:736-737`、`:1279-1289`、`ingestion_runtime.py:1288-1289`、`:1372-1394`、`filing_semantics.py:375-404`）与当前工作树逐一吻合，无引用漂移。

## 结论

**pass**。O11-CR-F1 的两个子缺陷（`upload_filing` 空值拒绝承诺丢失、通用格式句与 material 空值折叠冲突）均已被根 README 日期段修复正确消除；逐格真值表与 CLI/Fins/tool owner 代码一致，空值 null 投影经 meta/manifest 同源链独立验证；文案未偷增 accepted plan R2 边界之外的产品承诺（仅 `--filing-date ""` 标注既有支持，其余折叠标「当前」并引导省略），无新增误导，修复范围未越界。新增实质性问题：无。残余风险如上登记（R2 独立裁决、update 全量替换语义、既有小测试缺口）。
