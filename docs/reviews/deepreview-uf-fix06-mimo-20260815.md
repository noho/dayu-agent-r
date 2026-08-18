# Deepreview: UF-FIX06 converter-capability-owner

## Scope

- **Mode**: Current Changes Mode (aggregate)
- **Branch**: `codex/upload-filing-oracle`
- **Base**: `main`
- **Output file**: `docs/reviews/deepreview-uf-fix06-mimo-20260815.md`
- **Review date**: 2026-08-15
- **UF-FIX06 commits** (4):
  - `c1db7b49` feat(documents): centralize Docling capability contract
  - `affa665b` feat(fins): define upload file role contract
  - `8033a56e` feat(fins): enforce typed upload workflow roles
  - `f61ddb95` docs(fins): document upload format ownership

### Included scope

核心生产文件（UF-FIX06 diff 范围，约 990 行增/113 行删）：

| 文件 | 变更类型 |
|------|---------|
| `dayu/documents/docling_runtime.py` | 新增 `DoclingConverterCapability`、`DoclingConverterFormat`、`DOCLING_CONVERTER_CAPABILITY`、`_resolve_docling_allowed_formats`；`build_docling_pdf_converter` 注入 `allowed_formats` |
| `dayu/fins/upload_format_contract.py` | 全新模块：`FinsUploadFormatCapability`、`FinsUploadFileRole`、`FinsUploadFilingFiles`、`FinsUploadMaterialFiles`、`FinsUploadFormatError`、`FINS_UPLOAD_FORMAT_CAPABILITY`、`FINS_UPLOAD_FORMAT_TEXT` |
| `dayu/fins/upload_failure.py` | 新增 `USAGE` failure kind、`UNSUPPORTED_UPLOAD_FORMAT` failure code、kind/code 映射完备性校验、`FinsUploadFormatError` 投影 |
| `dayu/fins/pipelines/docling_upload_service.py` | 移除 `SUPPORTED_UPLOAD_SUFFIXES`；`prepare_upload` 接收 typed selection；`_prepare_upload_selection` 收窄 source_kind/selection；`_build_pending_assets` 产出 `primary_document`；`_pick_primary_docling_file` 移除 |
| `dayu/fins/ingestion_runtime.py` | 移除 `FILE_SUFFIX_NOT_ALLOWED`/`CONVERTER_SUFFIX_UNSUPPORTED` usage codes；`_validate_fins_upload_filing_static` 使用 role-based validation；`file_selection` 进入 `ValidatedFinsUploadFilingRequest` |
| `dayu/fins/pipelines/sec_upload_workflow.py` | filing 传递 `authoritative_request.file_selection`；material 构造 `FinsUploadMaterialFiles` |
| `dayu/fins/upload_batch.py` | 移除 `FINS_UPLOAD_FILE_SUFFIXES`；`_discover_source_files` 使用 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` |
| `dayu/cli/commands/fins.py` | 移除 `FINS_UPLOAD_FILE_SUFFIXES` 引用；`_validated_upload_files` 返回 `FinsUploadMaterialFiles`；catch `FinsUploadFormatError` |
| `dayu/fins/tools/upload_tools.py` | `files` description 使用 `FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` |

测试文件（约 2,227 行）：

| 文件 | 变更类型 |
|------|---------|
| `tests/fins/test_upload_format_contract.py` | 全新：capability 冻结、filing/material selection 角色、failure kind 边界 |
| `tests/fins/test_upload_failure.py` | 全新：format error→usage failure 投影、JSON round-trip、kind/code 完备性 |
| `tests/documents/test_docling_runtime.py` | 扩展：product capability 冻结、FormatToExtensions 子集校验、静态无 Docling 导入、第三方新增扩展名不扩面 |
| `tests/fins/test_docling_upload_service.py` | 扩展：typed selection、source_kind/selection 错配、action/selection 空性双向校验 |
| `tests/fins/test_fins_ingestion_runtime.py` | 扩展：file_selection 传播、format failure kind 投影 |
| `tests/cli/test_fins_commands.py` | 扩展：material CLI bounded format error、filing suffix matrix 更新 |

### Excluded scope

- `docs/gateflow/` artifacts（plan、slice implementation、acceptance、code-fix）：作为上下文参考，不作为真源
- `docs/reviews/code-review-slice*-*.md` / `code-re-review-slice*-*.md`：作为上下文参考
- 非 UF-FIX06 的其余 branch commits（UF-FIX01/02/03、calendar-year-validation、ticker-alias-contract 等）

### Parallel review coverage

- 子任务 1：读取 plan、slice implementation/acceptance/code-fix artifacts（15 文件）
- 子任务 2：读取 slice reviews 与 adjudications（22 文件）
- 子任务 3：读取 design docs、CLAUDE.md、`upload_format_contract.py`、`upload_failure.py`
- 子任务 4：读取全部 UF-FIX06 生产代码（16 文件）
- 主 reviewer：直接读取 diff、测试、交叉验证 ownership 链路

未覆盖区域：无。所有 UF-FIX06 涉及的生产与测试文件均已完整读取。

---

## Verdict

**PASS**

未发现阻塞性问题。UF-FIX06 正确实现了 converter-capability-owner 的语义集中：Documents 层冻结产品转换能力，Fins 层叠加角色语义，全链路无独立 suffix allow-list。所有已知 slice review 与 adjudication findings 均已在代码中修复。

---

## Findings

### 1-未修复-低-FinsUploadUsageFailure.code 联合类型可演进性

- **入口/函数**: `FinsUploadUsageFailure` dataclass，`dayu/fins/ingestion_runtime.py:690`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:690`
- **输入场景**: 格式错误通过 `_raise_upload_format_usage` 投影为 usage failure
- **实际分支**: `code` 字段为 `FinsUploadUsageCode | FinsUploadFormatFailureKind` 联合类型
- **预期行为**: usage failure code 保持单一 closed enum
- **实际行为**: 因为 `FinsUploadFormatFailureKind` 是 format contract owner 的 failure kind，将其混入 usage code 是两次 owner 边界的交叉——format owner 的 failure kind 被当作 usage owner 的 code 使用
- **直接证据**: `dayu/fins/ingestion_runtime.py:690` — `code: FinsUploadUsageCode | FinsUploadFormatFailureKind`；`dayu/fins/ingestion_runtime.py:707` — `isinstance` 校验接受两个 enum
- **影响**: 功能正确（`.value` 在两个 str enum 上均可用），但后续如果 `FinsUploadUsageCode` 和 `FinsUploadFormatFailureKind` 的值域重叠或需要不同序列化行为，联合类型会增加维护成本
- **建议改法和验证点**: 当前可接受。若后续 usage failure 需要更细粒度的 code，可考虑在 `FinsUploadUsageCode` 中新增 `FORMAT_PRIMARY_UNSUPPORTED` / `FORMAT_COMPANION_UNSUPPORTED` / `FORMAT_MATERIAL_UNSUPPORTED` 三个 code 并移除联合类型。验证点：`test_upload_format_error_maps_to_closed_usage_failure` 覆盖所有 format kind
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-batch discovery 不再发现 companion-only 文件

- **入口/函数**: `_discover_source_files`，`dayu/fins/upload_batch.py:418`
- **文件(行号)**: `dayu/fins/upload_batch.py:418`
- **输入场景**: 用户通过 batch discovery 模式上传包含 `.xsd` companion 的 filing 目录
- **实际分支**: `accepts_primary(lexical_candidate.suffix)` 对 `.xsd` 返回 `False`，文件被跳过
- **预期行为**: 旧行为中 `.zip` 也在 `FINS_UPLOAD_FILE_SUFFIXES` 中但不可转换，batch discovery 会发现它
- **实际行为**: `.xsd`（companion-only）和 `.zip`（完全不支持）均被 batch discovery 跳过
- **直接证据**: `dayu/fins/upload_batch.py:418` — `if not FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary(lexical_candidate.suffix)`
- **影响**: batch 模式下 companion-only 文件无法被自动发现。但这是正确行为——batch discovery 无法确定文件顺序（谁是 primary、谁是 companion），且 `.xsd` 作为 companion 时其转换语义无意义
- **建议改法和验证点**: 无需修改。若未来需要 batch companion 发现，需引入文件排序语义
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-material CLI 与 runtime 双重格式校验

- **入口/函数**: `_validated_upload_files` (CLI) + `_prepare_upload_selection` (runtime)
- **文件(行号)**: `dayu/cli/commands/fins.py:1116` + `dayu/fins/pipelines/docling_upload_service.py:995`
- **输入场景**: CLI material 上传包含不支持格式的文件
- **实际分支**: CLI `_validated_upload_files` 构造 `FinsUploadMaterialFiles` 时抛出 `FinsUploadFormatError`；若绕过 CLI 直接调用 runtime，`_prepare_upload_selection` 再次校验
- **预期行为**: 格式校验在单一入口完成
- **实际行为**: 格式校验在 CLI 和 runtime 两个入口各执行一次
- **直接证据**: `dayu/cli/commands/fins.py:1134` — `FinsUploadMaterialFiles.from_upsert_paths(tuple(paths))`；`dayu/fins/pipelines/sec_upload_workflow.py:460` — 同样构造
- **影响**: 功能正确——CLI 提供快速用户反馈，runtime 保证不依赖入口。轻微冗余但符合 defense-in-depth 原则
- **建议改法和验证点**: 无需修改。两层校验分别服务不同关注点（CLI: 用户体验；runtime: 正确性保证）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## Adversarial Failure Analysis

### 认证/权限/信任边界

- 格式校验不涉及认证或权限。`FinsUploadFormatError` 产生的错误信息是路径无关的（只包含 canonicalized file label），不泄漏文件系统路径。

### 数据丢失/损坏/不可逆状态

- 格式校验在任何文件 I/O 或存储写入之前执行（`_validate_filing_path` 在 `FinsUploadFilingFiles.__post_init__` 中，早于 `prepare_upload`）。非法格式不会进入转换或存储流程。
- `primary_document` 从第一个转换结果确定，不再从存储后的条目中搜索（旧 `_pick_primary_docling_file` 已移除），消除了"转换成功但 primary 未选定"的风险。

### 取消/超时/中断

- `_build_pending_assets` 在循环顶部检查 `_is_cancelled(cancellation)` 并抛出 `DoclingConversionCancelledError`，替代了旧的 `break` 行为。这保证了取消时不会产生半转换状态。

### 竞争写入/孤儿状态

- 格式校验是纯内存操作，无竞争风险。typed selection 对象是 frozen dataclass，不可变。

### 非预期输入

- `_normalize_docling_product_suffix` 和 `_normalize_fins_upload_suffix` 对空串、空白、仅点号均返回 `None` 或抛出 `ValueError`。
- `accepts_product_suffix` 对空串、空白、仅点号安全返回 `False`（不抛出）。
- `FinsUploadFormatError.__init__` 校验 `kind` 类型和 `file_label` 安全性。
- `FinsUploadFailureReason.__post_init__` 校验 kind/code 一致性、类型严格性（`type(x) is not Enum`）。

### 版本漂移/schema 不一致

- `DOCLING_CONVERTER_CAPABILITY` 是静态冻结的产品声明。`_resolve_docling_allowed_formats` 在构造时延迟校验产品声明仍是已安装 Docling 能力的子集。第三方新增扩展名不扩面，第三方移除扩展名导致构造失败——这是正确行为。
- `_FAILURE_CODES_BY_KIND` 在模块加载时校验完备性和互斥性（`raise RuntimeError` 若不满足）。

---

## Semantic Ownership Analysis

### Documents capability 唯一驱动 allowed_formats

**确认通过。** `DOCLING_CONVERTER_CAPABILITY` 定义在 `dayu/documents/docling_runtime.py`，是产品转换能力的唯一真源。`build_docling_pdf_converter` 通过 `_resolve_docling_allowed_formats(DOCLING_CONVERTER_CAPABILITY)` 将其注入 `DocumentConverter(allowed_formats=...)`。Fins 层通过 `FINS_UPLOAD_FORMAT_CAPABILITY.converter_capability` 复用同一实例，不自行定义格式列表。

### Fins overlay/help/CLI/Service/workflow 无独立 suffix allow-list

**确认通过。** 已移除：
- `SUPPORTED_UPLOAD_SUFFIXES`（原 `dayu/fins/pipelines/docling_upload_service.py`）
- `FINS_UPLOAD_FILE_SUFFIXES`（原 `dayu/fins/upload_batch.py`）
- `_UPLOAD_SUFFIX_NOT_ALLOWED_TEMPLATE`（原 `dayu/cli/commands/fins.py`）
- `FinsUploadUsageCode.FILE_SUFFIX_NOT_ALLOWED` / `CONVERTER_SUFFIX_UNSUPPORTED`（原 `dayu/fins/ingestion_runtime.py`）

全仓 `grep` 确认无残留引用。所有格式判断统一收敛到 `FINS_UPLOAD_FORMAT_CAPABILITY` 或其 `converter_capability`。

### filing primary/companion 与 material 角色合同

**确认通过。**
- `FinsUploadFileRole.PRIMARY` / `COMPANION` 枚举定义角色
- `FinsUploadFilingFiles` 强制首文件为 primary、后续为 companion；delete 为空状态
- `FinsUploadMaterialFiles` 强制每个文件都是 converter-required
- `require_filing_path(path, role=...)` 按角色校验
- `require_material_path(path)` 校验 converter-required
- `ingestion_runtime._validate_fins_upload_filing_static` 按 index 确定 role（index==0 → PRIMARY，else → COMPANION）

### XBRL companion 合同

**确认通过。** `.xbrl` 和 `.xml` 在 `DOCLING_CONVERTER_CAPABILITY` 中（`XML_XBRL` 格式），可作为 primary 或 companion。`.xsd` 在 `companion_only_suffixes` 中，只能作为 companion。`accepts_companion` 同时接受 primary 能力和 companion-only overlay。

### failure kind/code 合同

**确认通过。**
- `FinsUploadFailureKind` 新增 `USAGE`
- `FinsUploadFailureCode` 新增 `UNSUPPORTED_UPLOAD_FORMAT`
- `_FAILURE_CODES_BY_KIND` / `_FAILURE_KIND_BY_CODE` 在模块加载时校验完备、互斥
- `FinsUploadFailureReason.__post_init__` 用 `type(x) is not Enum` 严格拒绝 open string
- `fins_upload_failure_from_exception` 正确映射 `FinsUploadFormatError` → `USAGE` / `UNSUPPORTED_UPLOAD_FORMAT`

### ticker/calendar 保留合同

**确认通过。** `normalize_ticker` 调用位置未变（`docling_upload_service.py:294`）。`fiscal_year` / `fiscal_period` 参数在 `prepare_upload` 签名中保留，不被格式校验影响。

### UF-FIX07/PF/protected scope

**确认通过。** UF-FIX06 不修改 `dayu/fins/storage/` 下的仓储协议实现（除 `repository_protocols.py` 的 import 清理外）。`upload_format_contract.py` 是纯新增模块，不侵入既有 storage 或 pipeline 状态机。

---

## Coupling Analysis

### 模块间依赖

- `upload_format_contract.py` → `docling_runtime.py`（capability 真源）+ `direct_events.py`（file label canonicalizer）：依赖方向正确（fins → documents + fins 内部）
- `upload_failure.py` → `upload_format_contract.py`（`FinsUploadFormatError`）：同包内合理依赖
- `ingestion_runtime.py` → `upload_format_contract.py`：validation 层使用 format contract，依赖方向正确
- `docling_upload_service.py` → `upload_format_contract.py`：service 层使用 typed selection，依赖方向正确
- `upload_batch.py` → `upload_format_contract.py`：batch discovery 使用 `accepts_primary`，同包内合理依赖
- `cli/commands/fins.py` → `upload_format_contract.py`：CLI 层使用 `FinsUploadMaterialFiles`，依赖方向正确

**无反向依赖。** `upload_format_contract.py` 不 import `ingestion_runtime`、`docling_upload_service`、`upload_batch` 或 CLI 模块。

### 跨层穿透

**未发现。** 格式校验在两个层面执行：
1. CLI 层（`_validated_upload_files`）：用户快速反馈
2. Runtime 层（`_prepare_upload_selection` + `FinsUploadFilingFiles.__post_init__`）：正确性保证

两层均使用同一 `FINS_UPLOAD_FORMAT_CAPABILITY` 真源，不各自维护独立逻辑。

### typed selection 传播链路

```
CLI _validated_upload_files → FinsUploadMaterialFiles → .files → service.upload_material
                                                                    → runtime.run_upload_material_stream
                                                                      → FinsUploadMaterialFiles.from_upsert_paths
                                                                        → DoclingUploadService.prepare_upload(selection=...)

ingestion_runtime._validate_fins_upload_filing_static → FinsUploadFilingFiles
  → ValidatedFinsUploadFilingRequest.file_selection
    → sec_upload_workflow.run_upload_filing_stream
      → DoclingUploadService.prepare_upload(selection=authoritative_request.file_selection)
```

链路清晰，selection 在 validation 层构造，原样传递至 service 层，不被中间层修改或重建。

---

## Test Coverage Assessment

| 维度 | 覆盖情况 |
|------|---------|
| capability 冻结（9 格式、13 扩展名） | ✅ `test_product_capability_freezes_exact_formats_suffixes_and_metadata_subset` |
| 静态无 Docling 导入 | ✅ `test_static_capability_projection_does_not_import_docling` |
| 第三方新增扩展名不扩面 | ✅ `test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix` |
| FormatToExtensions 缺失 | ✅ `test_converter_construction_fails_typed_when_format_extension_mapping_is_missing` |
| admission predicate 边界（空/空白/点） | ✅ `test_product_suffix_predicate_returns_false_for_inputs_without_effective_suffix` |
| filing primary/companion 角色 | ✅ `test_filing_upsert_selection_preserves_primary_and_companion_order` |
| XSD companion-only 边界 | ✅ `test_xsd_is_accepted_only_as_filing_companion` |
| material 全文件转换 | ✅ `test_material_selection_requires_every_file_to_be_convertible` |
| delete 空状态 | ✅ `test_filing_delete_is_typed_empty_and_upsert_rejects_empty` |
| format error → usage failure 投影 | ✅ `test_upload_format_error_maps_to_closed_usage_failure` |
| JSON round-trip | ✅ `test_unsupported_upload_format_reason_strict_json_round_trip` |
| kind/code 完备性与互斥 | ✅ `test_upload_failure_kind_code_mapping_is_disjoint_complete_and_single_source` |
| kind/code 直接构造拒绝错配 | ✅ `test_upload_failure_reason_direct_construction_rejects_kind_code_mismatch` |
| open enum 拒绝 | ✅ `test_upload_failure_reason_direct_construction_rejects_open_enum_values` |
| source_kind/selection 错配 | ✅ `test_prepare_upload_rejects_source_kind_selection_mismatch_before_io` |
| action/selection 空性双向校验 | ✅ （docling_upload_service 测试） |
| CLI material bounded format error | ✅ `test_upload_material_cli_uses_bounded_converter_required_format_owner` |
| CLI filing suffix matrix | ✅ 更新为新的 format owner 错误文案 |
| file_selection 传播到 validated request | ✅ ingestion_runtime 测试 |

---

## Residual Risk

1. **`FinsUploadUsageCode | FinsUploadFormatFailureKind` 联合类型**：当前功能正确，但若后续 usage failure 需要更细粒度序列化，联合类型会增加维护成本。风险低，可在后续迭代中收束。

2. **batch discovery 不发现 companion-only 文件**：`.xsd` 在 batch 模式下不可被自动发现。这是正确行为（batch 无法确定文件顺序），但用户需通过显式 `--files` 上传 companion 文件。风险低。

3. **material 格式双重校验**：CLI 和 runtime 各执行一次格式校验。轻微冗余但符合 defense-in-depth。风险低。

4. **`DOCLING_CONVERTER_CAPABILITY` 中 `.json` 的语义**：`.json` 在 `JSON_DOCLING` 格式下，仅指 Docling JSON 输出格式，不是任意 JSON。已在 help 文案和测试中说明，但依赖第三方 Docling 的 `FormatToExtensions` 映射保持一致。风险低。

---

## 与既往 Slice Review / Adjudication 的对账

| Adjudication | 状态 | 代码证据 |
|-------------|------|---------|
| Plan: lazy import boundary for help projection | ✅ 已修复 | `upload_format_contract.py` 使用 `from dayu.documents.docling_runtime import DOCLING_CONVERTER_CAPABILITY`（非 lazy） |
| Plan: `.xml` as XBRL-only | ✅ 已修复 | `XML_XBRL` 格式包含 `.xbrl` 和 `.xml` |
| Plan: material suffix admission ownership | ✅ 已修复 | `FinsUploadMaterialFiles.__post_init__` 调用 `require_material_path` |
| Plan: `prepare_upload` closed-union signature | ✅ 已修复 | `selection: FinsUploadFilingFiles \| FinsUploadMaterialFiles` |
| Plan R1: USAGE failure kind + UNSUPPORTED_UPLOAD_FORMAT code | ✅ 已修复 | `upload_failure.py` 新增枚举值和映射 |
| Plan R2: frozen product declaration | ✅ 已修复 | `DOCLING_CONVERTER_CAPABILITY` 是 module-level frozen dataclass |
| Plan R3: `file_selection` required non-Optional field | ✅ 已修复 | `ValidatedFinsUploadFilingRequest.file_selection: FinsUploadFilingFiles` |
| Slice 1 F1: product-neutral suffix naming | ✅ 已修复 | `_normalize_docling_product_suffix`，`DoclingConverterFormat` |
| Slice 1 F2: FormatToExtensions owner tests | ✅ 已修复 | `test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix` |
| Slice 1 O1: admission predicate empty/blank/dot | ✅ 已修复 | `test_product_suffix_predicate_returns_false_for_inputs_without_effective_suffix` |
| Slice 2 A1: self-contained LLM help | ✅ 已修复 | `FINS_UPLOAD_FORMAT_TEXT` 包含完整规则说明 |
| Slice 2 A2: 240-char message invariant | ✅ 已修复 | `_bounded_format_failure_message` + `FinsUploadFormatError.__init__` |
| Slice 2 A4: `.json` help clarification | ✅ 已修复 | help 文案包含 ".json 仅是 Docling JSON 候选" |
| Slice 3 A1: failure kind docs list USAGE | ✅ 已修复 | `FinsUploadFailureKind` 含 `USAGE` |
| Slice 3 A5: kind/code self-validation | ✅ 已修复 | `FinsUploadFailureReason.__post_init__` 校验 type + mapping |
| Slice 4 A1: format-owner text XSD conversion claim | ✅ 已修复 | help 文案正确描述 XSD 为 companion-only、不转换 |
| Adjudication N1: JSON round-trip guard for usage codes | ✅ 已修复 | `upload_failure_reason_from_json` 使用 `_FAILURE_KIND_BY_CODE` |

所有 adjudicated findings 均已在最终代码中确认修复。
