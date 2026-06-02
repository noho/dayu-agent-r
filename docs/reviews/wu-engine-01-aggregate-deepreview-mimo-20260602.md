# Aggregate Deepreview: WU-ENGINE-01

## Scope

- Mode: current changes (full branch diff against `main`)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: `main`
- Output file: `docs/reviews/wu-engine-01-aggregate-deepreview-mimo-20260602.md`
- Included scope: 38 changed files, covering `dayu/engine/runners/openai/diagnostic_payload.py` (new), `dayu/engine/runners/openai/runner.py`, `dayu/engine/runners/openai/sse_parser.py`, `dayu/engine/runners/openai/non_stream_parser.py`, `dayu/engine/contracts/runner_events.py`, `dayu/engine/contracts/engine_events.py`, `dayu/engine/README.md`, and 6 test files
- Excluded scope: `dayu/host/` production (verified unchanged), `dayu/service/`, `dayu/ui/`, `dayu/fins/`
- Parallel review coverage: 无；单 reviewer 全分支走读

## Findings

### 1-未修复-低-测试 helper 跨文件重复

- **入口/函数**: `_leaf_strings` / `_serialized_size` 测试辅助函数
- **文件(行号)**: `tests/engine/runners/openai/test_diagnostic_payload.py:40`, `tests/engine/runners/openai/test_protocol_error.py:66`, `tests/engine/runners/openai/test_http_error_event.py:338`；`_serialized_size` 在同文件 `:29`, `:86`, `:358`
- **输入场景**: 任何运行这三个测试文件的场景
- **实际分支**: 三处各有一份完全相同的 `_leaf_strings` 与 `_serialized_size` 实现
- **预期行为**: 项目编码硬约束要求"数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"；测试 helper 也应优先复用
- **实际行为**: 同一逻辑在三个测试文件中各写一份
- **直接证据**: 三个函数实现完全相同，均为递归 JSON 叶子遍历与紧凑 JSON 序列化大小计算
- **影响**: 维护性问题；修改其中一处时容易遗漏另外两处，导致测试 helper 行为漂移
- **建议改法和验证点**: 在 `tests/engine/runners/openai/` 下新增共享 conftest 或 helper 模块，三个测试文件统一 import；运行三个测试文件确认通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 审查路径记录

### raw_payload=dict(parsed) 残留检查

`rg "raw_payload=dict\(parsed\)" dayu/ tests/` → 0 命中（仅 plan/review artifact 中有历史描述引用）。所有 `raw_payload=` 赋值在 production code 中为以下三类之一：

1. `raw_payload=None`：用于无 JSON object 可摘要的路径（invalid UTF-8、invalid JSON、non-object payload、missing choices、tool call 结构错误）
2. `raw_payload=<diagnostic helper>(...)`：`provider_error_diagnostic_payload` / `protocol_object_diagnostic_payload` / `invalid_utf8_diagnostic_payload` / `http_error_diagnostic_payload`
3. `raw_payload=error_body.raw_payload`：传递已由 helper 有界化的 `_HTTPErrorBody.raw_payload`

### Host ingest 不变验证

`git diff main...HEAD -- dayu/host/engine_ingest.py` → 无变更。`tests/host/test_engine_ingest_mapping.py` 仅将测试数据中的 `raw_payload` 从 `{"raw": "payload"}` 改为 diagnostic-like 结构以贴近新语义，断言仍为 `raw_payload_ref` 存在 + Run/Attempt 状态不变。

### 分层架构检查

- `dayu/engine/runners/openai/diagnostic_payload.py` 只 import 标准库 + `dayu.contracts.json_value.JsonValue`；不 import Host / Service / UI / Fins
- Engine Agent (`agent.py:1259`) 原样透传 `data.raw_payload`，不解析 diagnostic payload 内部结构
- Host ingest 不变

### 有界性检查

- `_DIAGNOSTIC_PAYLOAD_MAX_BYTES = 4096`
- `_bounded_payload` 有两级 fallback：先截断 preview/scalar，再删到最小结构（version/source/kind/canonical_byte_size/sha256_digest）
- 最小结构仍超限时 warning 日志并返回最小结构，不返回原始 payload
- 测试覆盖超大 payload fallback 路径（`test_large_payload_falls_back_to_minimal_structure`）

### 脱敏检查

- `_SENSITIVE_KEY_FRAGMENTS` 覆盖 `api_key`/`secret`/`token`/`password`/`authorization`/`credential`
- `_is_sensitive_key` 使用 case-insensitive substring match
- 敏感字段值在 `_top_level_preview` 和 `_provider_error_summary` 中被替换为 `<redacted>`
- 测试构造含敏感字段输入并断言值不在 diagnostic payload 中（`test_diagnostic_payload_redacts_sensitive_values`、`test_http_json_object_error_body_produces_bounded_diagnostic_payload`）

### Stream / Non-stream Parity

- `test_stream_and_non_stream_provider_error_object_parity` 断言两条路径产出相同 message、相同 diagnostic canonical_byte_size、相同 sha256_digest、相同 provider_error sub-object
- 允许 `error_code` 保持 path-specific（`sse_provider_error` / `non_stream_provider_error`）

### 非流式 missing choices / choice_not_object 路径差异

`non_stream_parser.py` 的 `non_stream_missing_choices` 和 `non_stream_choice_not_object` 使用 `raw_payload=None`，而 `sse_parser.py` 的 `sse_missing_choices` 使用 `protocol_object_diagnostic_payload`。这是行为差异但非缺陷：non-stream missing choices 时 parsed object 无有意义诊断信息（choices 缺失或为空），SSE 端 parsed object 是完整 data line 且可能含有用键。两条路径均不泄漏原始 provider JSON。

### 测试覆盖

- 95 target tests passed
- pyright 0 errors, 0 warnings
- 覆盖：helper 结构/大小上限/redaction/fallback/provider error 提取/canonical metadata、SSE provider error object、non-stream provider error object、SSE missing choices/invalid choice object、invalid UTF-8、HTTP error body bounded diagnostic、HTTP error body byte cap、stream/non-stream parity、Host ingest mapping

### README / Docs Sync

- `dayu/engine/README.md` 新增一条 `raw_payload` 契约说明：有界、脱敏、摘要化诊断载荷，不保证保留 provider 原始 payload
- 不更新 `docs/host/design.md`、`dayu/host/README.md`、根目录 `README.md`、`tests/README.md`（本 work unit 不改变 Host 架构、状态机或公共接口）

## Open Questions

- 无。

## Residual Risk

- `_leaf_strings` / `_serialized_size` 测试 helper 跨文件重复，属维护性风险，不影响 correctness。建议后续统一到共享 helper。
- `_is_sensitive_key` 的 fragment 列表不覆盖所有可能的敏感 key（如 `auth`、`bearer`、`private`），但这是 plan 明确的设计选择，当前 fragment 列表覆盖了最常见的 provider 返回敏感字段。
- 非流式 missing choices / choice_not_object 路径与 SSE 路径的 raw_payload 处理存在差异（None vs diagnostic），当前无 correctness 风险，未来若需要统一可作为 follow-up。

## 结论

**PASS** — 未发现 blocking / high / medium finding。

WU-ENGINE-01 全分支 diff 正确实现了目标：

1. 所有 `raw_payload=dict(parsed)` 路径已替换为 bounded diagnostic helper
2. HTTP JSON error body 通过同一 helper 摘要化，保留 `_HTTP_ERROR_BODY_MAX_BYTES` 读取上限
3. Stream / non-stream provider error object parity 测试存在并通过
4. Host ingest production 未变更
5. 未违反 UI -> Service -> Host -> Engine 分层
6. 无 raw provider JSON 泄漏、secret 泄漏、无界 payload
7. 测试 / pyright / README sync 均足够

建议 **ready-to-open-draft-PR**。
