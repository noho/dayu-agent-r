# UF-FIX06 Slice 2 code review — AgentMiMo

## Review metadata

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：2（建立 Fins role contract 并迁移所有静态消费者）
- Reviewer：AgentMiMo
- 日期：2026-08-15
- 基线提交：`c1db7b49`
- 输入：workspace diff（未提交）

## Review scope

6 个 production 文件（1 新增、5 修改）+ 6 个 test 文件（1 新增、5 修改）+ 1 个 artifact。

- `dayu/fins/upload_format_contract.py`（新增）
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/upload_batch.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`
- `dayu/fins/tools/upload_tools.py`
- `tests/fins/test_upload_format_contract.py`（新增）
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_upload_batch.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_tools.py`

## 逐项验证结果

### 1. 唯一 converter owner → Fins role projection 无漂移

**PASS。** `upload_format_contract.py` 直接持有 `DOCLING_CONVERTER_CAPABILITY`，primary 集合始终投影 `converter_capability.product_suffixes`，companion 集合为 primary + `.xsd`。没有复制 converter allow-list，没有 consumer-local suffix set。

### 2. 13 suffix 精确集合

**PASS。** 测试断言 `_PRIMARY_SUFFIXES` 精确等于 13 个冻结 suffix。batch 测试逐个断言 13 个 suffix 都能进入 standalone filing plan。拒绝矩阵覆盖 10 个已知 skip suffix（`.doc/.ppt/.xls/.zip/.xsd/.text/.rmd/.qmd/.xlsm/.potx`）。

### 3. primary/companion/material/delete typed contract

**PASS。** `FinsUploadFilingFiles` 提供 `from_upsert_paths`（非空）和 `for_delete`（唯一空状态）。`FinsUploadMaterialFiles` 同理。`__post_init__` 执行格式校验。delete 空 primary + 非空 companion 被 `ValueError` 拒绝。

### 4. `.xsd` companion-only

**PASS。** `companion_only_suffixes=frozenset({".xsd"})`。测试断言 XSD 作为首文件 primary 失败，HTML primary + XSD companion 成功。batch 测试断言 XSD 不进入 standalone candidate。

### 5. legacy/zip 拒绝

**PASS。** `.doc/.ppt/.xls/.zip` 全部在 `_REJECTED_STANDALONE_SUFFIXES` 中被 parametrized 测试覆盖。CLI filing usage matrix 测试包含 `.doc/.ppt/.xls/.zip/.xsd`。

### 6. validated request non-Optional

**PASS。** `ValidatedFinsUploadFilingRequest.file_selection: FinsUploadFilingFiles` 是必需字段，无默认值。测试断言 create/update 携带 `from_upsert_paths`，delete 携带 `for_delete()`。

### 7. batch 不分组

**PASS。** batch 继续按单文件生成独立 upload 命令。没有自动 companion association。XSD 稳定 skip。

### 8. CLI help 与 LLM schema 自足同源

**PASS。** 两者均消费 `FINS_UPLOAD_FORMAT_TEXT`。测试断言 CLI help 和 LLM schema 包含全部冻结语义片段（"首文件是主文件"、"必须实际转换成功"、"仅原样保存、不转换"、".xsd"、".xml 仅是 XBRL XML 候选"、"不代表任意 XML"、"不保证文件内容转换成功"）。

### 9. 不 eager import Docling

**PASS。** `test_contract_and_cli_projection_import_without_loading_docling` 在子进程中 import `upload_format_contract`、`arg_parsing`、`upload_tools` 并断言不触发 `docling` import。

### 10. 错误类型严格/bounded/path-free

**PASS。** `FinsUploadFormatError` 只携带 `FinsUploadFormatFailureKind` 与安全 basename。消息由固定中文模板产生，不含绝对路径。测试断言 `str(tmp_path) not in str(error)`、`"/" not in str(error)`、长度 `<= 240`。

### 11. 未越界 Slice 3/UF-FIX07

**PASS。** `SUPPORTED_UPLOAD_SUFFIXES` 仅存在于 `docling_upload_service.py`（Slice 3 文件），不在本 Slice 改动范围内。`FINS_UPLOAD_FILE_SUFFIXES` 已从代码库完全移除。未修改 `upload_failure.py`、Service、workflow、storage 或 Host/Engine。

### 12. 既有 contract 不回退

**PASS。** `FinsUploadUsageCode` 成员删除了 `FILE_SUFFIX_NOT_ALLOWED` 和 `CONVERTER_SUFFIX_UNSUPPORTED`，对应的 `_USAGE_MESSAGES` 和 `_FILE_USAGE_CODES` 也同步清理。`_USAGE_MESSAGES` 集合与 `FinsUploadUsageCode` 枚举精确一致。ticker/date/action/state 测试原样通过。

### 13. 静态 owner 审计

**PASS。** `rg -n 'FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES' dayu tests -g '*.py'` 结果：仅 `docling_upload_service.py` 保留 `SUPPORTED_UPLOAD_SUFFIXES`（approved Slice 3 文件）。无 `Any/object` 签名、`hasattr/getattr`、兼容 wrapper 或 consumer fallback。

## Findings

### F1：`FinsUploadUsageFailure.code` 联合类型扩大了 closed contract

- **Severity**：low
- **位置**：`dayu/fins/ingestion_runtime.py:690`
- **证据**：`code` 字段类型从 `FinsUploadUsageCode`（closed enum，16 成员）变为 `FinsUploadUsageCode | FinsUploadFormatFailureKind`（closed union，16 + 3 = 19 成员）。
- **影响**：下游消费 `failure.code` 的代码若做 exhaustive match on `FinsUploadUsageCode`，需要额外处理 3 个 `FinsUploadFormatFailureKind` 变体。当前 `ingestion_runtime` 内无 exhaustive match，`upload_failure.py`（Slice 3）尚未消费该 union。pyright 通过。
- **必要修复**：无需修复。这是设计意图——格式错误直接使用角色 owner 的 failure kind，避免在 `FinsUploadUsageCode` 中复制格式语义。Slice 3 的 `fins_upload_failure_from_exception` 需要显式匹配 `FinsUploadFormatError`，该函数在 plan 中已定义。建议 Slice 3 实现时在 `upload_failure.py` 增加对 `FinsUploadFormatFailureKind` 的投影测试。

### F2：filing 静态校验中逐文件 suffix 检查与 `from_upsert_paths.__post_init__` 重复验证

- **Severity**：low
- **位置**：`dayu/fins/ingestion_runtime.py:971-990`
- **证据**：`_validate_fins_upload_filing_static` 在文件循环中对每个文件调用 `FINS_UPLOAD_FORMAT_CAPABILITY.require_filing_path(file_path, role=role)`，然后在循环后再次调用 `FinsUploadFilingFiles.from_upsert_paths(request.files)`，后者在 `__post_init__` 中对 primary 和每个 companion 再次调用 `require_filing_path`。
- **影响**：对 N 个文件，suffix 校验执行 2N 次而非 N 次。对于典型的 1-5 个文件，开销可忽略；对理论上限 100 个文件，开销翻倍但仍为微秒级。正确性不受影响——两遍验证使用同一 owner、同一 predicate。
- **必要修复**：无需修复。逐文件验证提供更早、更精确的错误定位（哪个文件、哪个位置失败），而 `from_upsert_paths` 的 `__post_init__` 保护了直接构造 `FinsUploadFilingFiles` 的路径。两层防御是正确的分层设计。

### F3：`_raise_upload_format_usage` 绕过 `_USAGE_MESSAGES` 验证路径

- **Severity**：informational
- **位置**：`dayu/fins/ingestion_runtime.py:845-858`
- **证据**：`_raise_upload_format_usage` 直接构造 `FinsUploadUsageFailure(code=error.kind, message=str(error))`，不经过 `fins_upload_usage_failure()` 函数。消息有界性由 `FinsUploadFormatError.__init__` 的模板保证（`_FORMAT_FAILURE_MESSAGES`），而非 `_USAGE_MESSAGES`。
- **影响**：两条路径（`fins_upload_usage_failure` 和 `_raise_upload_format_usage`）各自独立保证消息有界性，但验证逻辑不统一。当前无运行时风险。
- **必要修复**：无需修复。两条路径的消息模板都是模块级常量、固定中文、长度受控。`FinsUploadFormatError` 的 `__init__` 已通过 `validate_fins_public_file_label` 保证 file_label 安全。

### F4：material CLI 将 `None` files 映射为 `FinsUploadMaterialFiles.for_delete()` 而非空 tuple

- **Severity**：informational
- **位置**：`dayu/cli/commands/fins.py:95`
- **证据**：旧代码 `if raw_files is None: return ()`，新代码 `if raw_files is None: return FinsUploadMaterialFiles.for_delete()`。`.files` 属性返回空 tuple `()`，传给 `upload_material(files=())`，语义等价。
- **影响**：对当前 Slice 2 无影响——`upload_material` 仍接收 `list[Path]`。对 Slice 3，该 typed empty 为 Service 入口的 action/emptiness 校验提供了明确语义。
- **必要修复**：无需修复。这是正确的前向准备工作。

## Architecture 与 semantic ownership 审查

| 审查维度 | 结果 |
|---|---|
| converter capability owner | `DoclingConverterCapability` 唯一持有，Fins 通过组合引用而非复制 |
| Fins role owner | `FinsUploadFormatCapability` 唯一持有 primary/companion/material 角色语义 |
| format error owner | `FinsUploadFormatError` 唯一持有 failure kind，`_raise_upload_format_usage` 唯一投影 |
| batch suffix admission | `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` 唯一消费方 |
| help/schema projection | `FINS_UPLOAD_FORMAT_TEXT` 唯一消费方，两处 import 一致 |
| CLI error handling | `FinsUploadFormatError` catch 在 `FinsUploadUsageError` 之后（正确：前者不继承后者） |
| validated request | `file_selection` 必需非 Optional，validator 直接产生 typed selection |
| import boundary | `upload_format_contract` 不 import Docling，子进程 import guard 通过 |
| reverse dependency | 无。`upload_format_contract` 依赖 `documents`（下层）和 `direct_events`（同层 peer），不依赖 `ingestion_runtime`、`upload_batch`、CLI 或 Service |

## Verdict

**PASS**

0 blocking findings。4 个 informational/low findings 均为有意的设计决策或无运行时影响的实现细节。

Slice 2 的 Fins role owner、role-specific typed failures、filing/material selections、non-Optional validated selection、batch/material CLI owner migration、统一 help/schema projection、owner tests、focused regression、changed-file pyright、逐文件 coverage 与静态审计均满足 accepted plan contract。无类型回退、无架构越界、无语义漂移。
