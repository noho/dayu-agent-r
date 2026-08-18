# Code Review（UF-FIX06 Slice 2，AgentDS 第二路）

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`implementation Slice 2` → `code review`
- Reviewer：AgentDS（第二路独立严格 review）
- 日期：2026-08-15
- 基线 commit：`c1db7b49`（`feat(documents): centralize Docling capability contract`）
- 评审对象：当前未提交 workspace diff（10 个改动文件 + 2 个新增文件 + 1 个 implementation artifact）
- Output file：`docs/reviews/code-review-slice2-ds-20260815.md`
- 输入文档：`AGENTS.md`、`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（冻结 contract 与 Slice 2）、`docs/gateflow/uf-fix06-slice1-acceptance-20260815.md`、`docs/gateflow/uf-fix06-slice2-implementation-20260815.md`

## 复跑验证结果（均在 `source .venv/bin/activate` 后；未运行 UF-PF06/UF-PF12）

- `pytest tests/fins/test_upload_format_contract.py tests/fins/test_upload_batch.py tests/fins/test_fins_ingestion_runtime.py -q`：`339 passed, 3 warnings`（3 个 warning 均为既有 edgar 依赖 deprecation，非本 Slice 新增）。
- `pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_tools.py -q`：`687 passed, 3 warnings`。
- 合计 `1026 passed`，与 implementation artifact 声称一致。
- pyright（6 个 changed production + 6 个 changed test 文件）：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 范围审计：workspace diff 仅含 plan Slice 2 允许的 6 个 production 文件、6 个 test 文件与 implementation artifact；未触及 Slice 3/4 文件、registry、oracle/scenario、design doc、README、冻结 evidence；未 commit。

## 重点验证项核验

### 1. 唯一 converter owner 到 Fins role projection 无漂移 — 通过

- `dayu/fins/upload_format_contract.py:274-277` `FINS_UPLOAD_FORMAT_CAPABILITY` 直接持有 Slice 1 的 `DOCLING_CONVERTER_CAPABILITY`；`primary_suffixes`（`:158-172`）为纯投影 `return self.converter_capability.product_suffixes`，无本地 suffix 字面量复制。
- `accepts_primary`（`:190-203`）纯委托 `converter_capability.accepts_product_suffix`，无第二套 allow-list。
- 静态 owner audit：`rg -n 'FINS_UPLOAD_FILE_SUFFIXES' dayu tests -g '*.py'` 无结果；`SUPPORTED_UPLOAD_SUFFIXES` 仅存在于 approved Slice 3 文件 `dayu/fins/pipelines/docling_upload_service.py`（计划内保留，Slice 3 删除）。
- 实测（本次 review 运行）：`FINS_UPLOAD_FORMAT_CAPABILITY.primary_suffixes == ('.pdf','.docx','.pptx','.htm','.html','.xhtml','.md','.txt','.csv','.xlsx','.xbrl','.xml','.json')` 为 `True`；`companion_suffixes` 为其后追加 `.xsd`。

### 2. 13 suffix 精确集合 — 通过

- 生产声明在 Slice 1 `docling_runtime.py:220-232` 冻结；Slice 2 无任何新增/删除/重排。
- `tests/fins/test_upload_format_contract.py:21-35,50-69` 以冻结字面量断言 primary 投影精确相等、companion-only 精确为 `frozenset({".xsd"})`；batch enter 与 10 项 skip 矩阵（`.doc/.ppt/.xls/.zip/.xsd/.text/.rmd/.qmd/.xlsm/.potx`）参数化覆盖。
- 实测：`.PDF`（大小写）accept、`.XLS`/`.zip`/空串 reject、`.XSD` companion accept——规范化语义与旧 batch `suffix.lower()` 行为等价，无扩面。

### 3. primary/companion/material/delete typed contract — 通过

- `FinsUploadFileRole`（PRIMARY/COMPANION）、`FinsUploadFormatFailureKind`（三种 role-specific kind）、`FinsUploadFormatError`（仅 kind + 安全 label，`:52-78`）符合 plan §5.2。
- `FinsUploadFilingFiles`（`:280-411`）与 `FinsUploadMaterialFiles`（`:414-495`）均为 `frozen=True, slots=True`；`from_upsert_paths` 拒绝空输入、`for_delete` 是唯一合法空状态（`primary=None, companions=()` 的 `__post_init__` 拒绝「空 primary + 非空 companion」，`:312-315`）；`ordered_files`/`require_primary`/`is_empty` 投影严格。
- delete 不错误访问文件：`for_delete` 构造路径与 validator delete 分支（`ingestion_runtime.py:983-988`）在 `request.files` 为空时零文件系统访问；实测 `delete` 且无 files 的 validated selection 为 `FinsUploadFilingFiles(primary=None, companions=())`。

### 4. .xsd companion-only / legacy / zip 拒绝 — 通过

- `FinsUploadFormatCapability.__post_init__`（`:135-156`）强制 companion-only 非空、规范化且不与 primary 重叠；`companion_only_suffixes=frozenset({".xsd"})` 是唯一叠加。
- validator（`ingestion_runtime.py:971-982`）按位置 role 校验：index 0 用 `require_filing_path(role=PRIMARY)`，其余用 `COMPANION`；`.xsd` 首文件被 PRIMARY 拒绝、非首位置通过（测试 `test_xsd_is_accepted_only_as_filing_companion` 断言）。
- batch 实测：同目录 `2024FY年报.html` + `2024FY年报.xsd` → HTML enter、XSD `unsupported_suffix` skip，无自动关联（plan §6.2 要求）。
- legacy `.doc/.ppt/.xls`、`.zip` 在 contract、validator、batch 三层一致拒绝，拒绝路径均产生 role-specific `FinsUploadFormatError`/usage projection。

### 5. validated request 的 file_selection 非 Optional — 通过

- `ValidatedFinsUploadFilingRequest.file_selection: FinsUploadFilingFiles`（`ingestion_runtime.py:740`）与 `_StaticFinsUploadFilingValidation.file_selection`（`:751`）均为必需非 Optional 字段；构造点唯一（`:1006-1012`、`:1126-1134`），无 `None` 默认值或 delete 的二次翻译点。
- validator 对 create/update 直接 `from_upsert_paths(request.files)`，对 delete 直接 `for_delete()`；workflow 尚未消费（Slice 3 范围），当前无 workflow 内 `None` 转换残留。

### 6. batch 不分组、只消费 owner predicate — 通过

- `upload_batch.py:390` `_discover_source_files` 唯一 admission 为 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary(lexical_candidate.suffix)`；旧 `FINS_UPLOAD_FILE_SUFFIXES` 常量、`__all__` 导出与其 import 全部删除。
- 13 suffix 逐个 enter 并生成 standalone command（`tests/fins/test_upload_batch.py` 参数化 + `tests/cli/test_fins_commands.py::test_upload_filings_from_does_not_start_live_stream` 参数化断言 script 含 resolved 文件路径）；10 个拒绝 suffix 稳定 `unsupported_suffix` skip。
- skip reason（`:395`）为 `f"不支持的上传文件后缀: {suffix or '<none>'}"`，无路径泄漏。

### 7. CLI help 与 LLM schema 自足同源、不 eager import Docling — 通过（见 F1 一处文案缺口）

- 同源：`arg_parsing.py:921-925` 与 `upload_tools.py:236-240` 均直接消费 `FINS_UPLOAD_FORMAT_CAPABILITY` 投影出的 `FINS_UPLOAD_FORMAT_TEXT`；测试 `test_upload_filing_files_help_consumes_self_contained_format_projection` 与 `test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral` 分别断言 `help == FINS_UPLOAD_FORMAT_TEXT.filing_files` 与 `schema description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`。
- 文案自足：filing 部分含「首文件是主文件，必须实际转换成功」「后续文件是仅原样保存、不转换的随附文件」「`.xsd` 只能作为后续随附文件」「`.xml` 仅是 XBRL XML 候选，不代表任意 XML」「后缀通过只表示具备转换资格，不保证文件内容转换成功」；material 部分含「每个文件都必须使用上述主文件支持后缀并逐个实际转换」；13 个 suffix 由同一 projection 展开，无内部 enum/id 泄漏。tool 文案中 `upload_kind` 与 schema 参数名一致（`upload_tools.py:225`）。
- 无 eager import：`test_contract_and_cli_projection_import_without_loading_docling` 子进程 import guard 通过；本次 review 另以 `builtins.__import__` 拦截实测 `dayu.cli.arg_parsing`、`dayu.cli.commands.fins`、`dayu.fins.ingestion_runtime` 均可无 docling import 导入。`direct_events.py` 仅依赖标准库与 contracts，import 链无第三方重依赖。

### 8. 错误类型严格 / bounded / path-free — 基本通过（见 F2 一处边界缺口）

- `FinsUploadFormatError.__init__`（`:58-78`）对 kind 做 isinstance 校验、对 label 调用公共 label owner `validate_fins_public_file_label`；message 只由固定中文模板 + canonical 安全 label 组成。
- label 真源 `canonicalize_fins_public_file_label`（`direct_events.py:1070-1087`）对超长（>240）或需隐藏 basename 投影为固定隐藏标签，正常 basename 原样返回；validator 路径在 suffix 校验前先做 basename admission（`ingestion_runtime.py:973`），CLI material 路径的 exists/regular 前置检查排除了 canonicalizer 会抛 ValueError 的空名/dot 名。
- path-free 由测试显式断言（`test_format_error_is_bounded_and_never_exposes_parent_path`、`test_filing_validator_rejects_unsupported_primary_with_role_specific_usage` 均断言绝对父路径不进入 message）。
- 枚举复用类型安全：`FinsUploadUsageFailure.code: FinsUploadUsageCode | FinsUploadFormatFailureKind`（`ingestion_runtime.py:690`）为显式 union；唯一消费面在 `ingestion_runtime.py` 内（CLI 只读 `failure.message`，无序列化、无反向构造点），pyright 0 errors。旧的 `FILE_SUFFIX_NOT_ALLOWED`/`CONVERTER_SUFFIX_UNSUPPORTED` 引用全仓清零。

### 9. 未越界 Slice 3/UF-FIX07；既有 contract 不回退 — 通过

- Slice 3 文件（`docling_upload_service.py`、workflows、`upload_failure.py`）零改动；`_pick_primary_docling_file`、`SUPPORTED_UPLOAD_SUFFIXES` 原样保留在 Slice 3 文件内，未提前迁移或提前删除。
- 未引入显式 primary selector、重复输入/碰撞处理、batch companion 自动关联（均属 UF-FIX07/后续 work unit，实测确认）。
- date/ticker/action/state 既有测试（`test_fins_ingestion_runtime.py` 中全部原样节点）通过；`fins_upload_usage_failure` 的 closed mapping 测试仅删除两个废弃成员，未放宽 closed contract。
- CLI filing 路径不再叠加第二层 suffix 校验（plan Slice 2 exact changes 第 5 条），只保留 material helper 迁移。

## Adversarial failure pass

### A. 错误枚举复用类型安全 — 通过（一处 bounded 缺口见 F2）

`FinsUploadFormatFailureKind` 作为 `str, Enum` 混入 `FinsUploadUsageFailure.code` union。检查了全部消费面：`fins_upload_usage_failure`（签名仍收 `FinsUploadUsageCode`，`_USAGE_MESSAGES[code]` lookup 不会收到 kind）；`_raise_upload_format_usage` 直接构造 dataclass（绕过 factory，见 F2）；CLI 渲染只读 message。无序列化、无 `FinsUploadUsageCode(code_str)` 反向解析点，无 KeyError 风险。`_FILE_USAGE_CODES` 收缩为两个成员后唯一用途（file_name 必填判定）语义不变。

### B. delete 是否错误访问文件 — 通过

- filing delete 无 files：validator 循环体不执行、`for_delete()` 的 `__post_init__` 零 I/O、Service 尚未迁移。实测 confirmed。
- material delete 无 files：CLI `_validated_upload_files(None)` → `for_delete()` 零 I/O。
- delete 带 files（非法输入）：validator 仍逐文件 exists/regular/suffix 校验后 selection 静默为 `for_delete()`，`request.files` 原样保留——与旧代码行为逐点一致，非本 Slice 引入；但见 F4（与 tool 层「delete 必须省略 files」的显式拒绝不一致，且 Slice 3 Service 的双向 action/emptiness 校验以 selection 为准，拦不住该输入形态）。

### C. CLI material typed selection 与 downstream 签名一致 — 通过

`FinsDirectCommandService.upload_material(files: tuple[Path, ...])`（`dayu/service/fins_direct.py:299-304`）；CLI 传 `_validated_upload_files(args.files).files`（`tuple[Path, ...]`）。类型精确匹配，无 raw list/双输入。`FinsUploadFormatError` 在 `_open_direct_stream`（Service factory 之后、direct stream 之前）抛出，被 `run_fins_direct_command` 的 `except FinsUploadFormatError`（`fins.py:200-202`）投影为 `EXIT_USAGE_ERROR`；except 顺序与其它 ValueError 子类无继承冲突。

### D. 测试是否固化实现细节 — 基本通过（一处观察项见 F5）

- `test_batch_consumes_format_owner_without_legacy_allowlist` 读生产源码文本断言旧常量名不存在、`FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` 存在——是 plan §9 静态 owner audit 的自动化形态，锁的是「禁止重复 owner」的反面 contract，可接受但脆弱（见 F5）。
- 13 suffix 参数化测试用真实文件系统与 owner 公开投影，未 mock/重算 suffix 事实；`test_arg_parsing` 的 help 测试访问 argparse `_actions` 私有属性属既有测试风格，非本 Slice 新增模式。
- 测试中的 suffix 字面量均为 plan 冻结字面量的显式复制（pin contract 用途），与 owner 投影另有相等断言，不会倒逼生产代码保留兼容分支。

## Findings

### F1（severity：medium，非 blocking）— tool schema `files` 描述丢失「auto/create/update 必填」与「delete 禁止提供」的明确性

- 证据位置：`dayu/fins/upload_format_contract.py:535-541`（`upload_tool_files` 文案）与 `dayu/fins/tools/upload_tools.py:236-240`（消费点）。
- 复现/影响：原 schema 描述为「auto、create、update 必填，delete 禁止提供」；新文案只写「delete 不提供文件」，且未在任何位置说明 create/update 必须提供至少一个文件。「delete 禁止」的部分信息残留在 `action` 参数描述（`upload_tools.py:232`「且不能同时提供 files」），但「必填」完全丢失。plan §6.2 明确要求「create/update 与 delete 的 files 要求不变」；AGENTS.md LLM-facing 约束要求判断规则与禁止事项必须自足写在当前 LLM-facing 输入中。运行时行为不受影响（`_upload_files_from_arguments` 仍拒绝），但无状态 LLM 可能因缺必填提示而漏传 files 并触发一次可恢复失败。
- 必要修复：在 `upload_tool_files` 的 filing 与 material 两个分支中显式补「auto/create/update 必须提供至少一个文件；delete 不得提供文件」，并同步更新 `test_text_projection_is_self_contained_and_uses_exact_suffix_order` 与 `test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral` 的断言片段。

### F2（severity：low，非 blocking）— `_raise_upload_format_usage` 绕过 usage failure message 的 240 字符上限

- 证据位置：`dayu/fins/ingestion_runtime.py:845-858` 对比 `:786-821`（`fins_upload_usage_failure` 的 `len(message) > _MAX_TEXT_CHARS` 检查）。
- 复现/影响：本次 review 实测构造 230 字符 basename 的 `.doc` 文件 → `FinsUploadFormatError.message` 246 字符 → `FinsUploadUsageFailure.message` 246 字符，超过其 docstring 声明的「最大 240 字符」且未经 factory 检查（直接构造 dataclass 绕过）。触发窗口为 label 长度 230..240（模板 11 字符）；label 由公共 owner 保证 ≤240 与 path-free，故不泄漏路径、不破坏 fixity，仅破坏 bounded 承诺。同一业务事实（usage failure message）的两个构造路径之一绕过 owner 强制的边界检查，属语义所有权层面的小漂移。
- 必要修复：在 `_raise_upload_format_usage` 中复用同一长度检查（超限抛 `ValueError`），或将 format 模板的 label 上限显式约束为 `_MAX_TEXT_CHARS - 模板长度`；并补一个 ≥230 字符 basename 的边界测试。

### F3（severity：low，非 blocking）— `_upload_material_stream` docstring 未同步新异常类型

- 证据位置：`dayu/cli/commands/fins.py:698-711` docstring `:raises CliFinsUsageError:` 未包含 `FinsUploadFormatError`；其实际调用 `_validated_upload_files` 可抛该异常。
- 复现/影响：违反 AGENTS.md 编码硬约束「函数必须提供完整中文 docstring，至少包含参数、返回值、异常」；无运行时影响。
- 必要修复：docstring 增加 `:raises FinsUploadFormatError: 任一文件不具备 converter-required 格式时抛出。`

### F4（severity：low，观察项，非 blocking）— validator 对 delete+files 静默丢弃，与 tool 层显式拒绝不一致

- 证据位置：`dayu/fins/ingestion_runtime.py:983-988`（delete 分支无条件 `for_delete()`）；对照 `dayu/fins/tools/upload_tools.py:438-441`（delete+files 显式 `ValueError`）。
- 复现/影响：实测 `action=delete, files=(report.pdf,)` 通过 validator，selection 为空但 `request.files` 非空——同一请求事实出现两个互相矛盾的投影。旧代码同样静默（无 selection 概念），本 Slice 未回退；但 Slice 3 的 Service 双向校验以 selection 为准，该输入会以「delete + 空 selection」合法通过，文件被静默忽略，CLI 与 tool 行为永久分叉。plan 未覆盖此输入形态（非 Slice 2 责任）。
- 必要修复：建议在 Slice 3 或 UF-FIX07 由 validator 对 delete+files 显式抛 usage error，使 CLI/tool 对齐；本 Slice 可不动。

### F5（severity：low，观察项，非 blocking）— 一处源码文本断言测试较脆弱

- 证据位置：`tests/fins/test_upload_batch.py` `test_batch_consumes_format_owner_without_legacy_allowlist`（读 `upload_batch.__file__` 文本断言）。
- 复现/影响：对实现文本而非行为断言；任何无关重构（改名、移动）都会破坏该测试。但它自动化的是 plan §9 静态 owner audit 的「旧 allow-list 不得复活」检查，锁的是唯一 owner 的反面 contract，风险可控。
- 必要修复：可选。若保留，建议 comment 说明其 audit 性质；不要求本 Slice 修改。

## Residual risks（plan-aware，非本 Slice 缺陷）

1. 过渡期双 owner 并存：validator 现接受 13 suffix 中旧 Service 集合没有的 `.pptx/.csv/.json/.xbrl/.xhtml/.xml`，在 Slice 3 落地前，这些格式的 filing 会通过预校验但在 `DoclingUploadService._validate_source_files` 被旧 `SUPPORTED_UPLOAD_SUFFIXES` 以 `ValueError` 拒绝，投影为 runtime failure 而非 usage。plan 与 implementation artifact 已声明「当前分支不应在 Slice 3 前发布」，Slice 3 测试必须为这 6 种格式补端到端断言；旧 CLI usage 矩阵中 UF-032~UF-037 场景断言已被移除，回归覆盖依赖 Slice 3。
2. material `--files` CLI help 仍为旧文本「待上传文件路径。」：plan 只要求 filing help 与 tool schema 同源，material help 不在三面范围内；Slice 4 README 同步时建议评估是否顺带对齐。
3. `_validated_upload_files` 对 create/update 缺 `--files` 返回 `for_delete()` 并投影空 tuple 传给 Service——与旧行为一致，但把「缺文件」建模为 delete selection；Slice 3 的 workflow 会重新构造 selection，该 CLI 层中间态届时自然消失。

## Verdict

**pass-with-risks**

- Blocking findings：0。核心 contract 全部核验通过：唯一 converter owner 到 Fins role projection 无漂移、13 suffix 精确、primary/companion/material/delete typed contract、`.xsd` companion-only、legacy/zip 拒绝、validated `file_selection` 非 Optional、batch 不分组、CLI help 与 LLM schema 自足同源且无 eager Docling import、错误类型严格且 path-free、未越界 Slice 3/UF-FIX07、既有 contract 无回退。focused tests 1026 passed、pyright 0 errors 与 implementation artifact 声称一致。
- 建议 Slice 2 内修复：F1（LLM-facing 必填/禁止文案，plan §6.2 明文要求）、F2（bounded 检查复用）、F3（docstring）。
- F4/F5 为观察项，可由 Controller 裁决在本 Slice 或移交 Slice 3/UF-FIX07。

未修改生产代码、测试、registry、evidence；未 commit；未运行 UF-PF06/UF-PF12。
