# WU-TOOLS-01-F01-02 PR Review — AgentDS

## Metadata

| 项目 | 内容 |
|---|---|
| Work unit | WU-TOOLS-01-F01-02 Migrated Tools Cancellation Propagation And Response |
| Review type | PR review（draft-PR-pass gate） |
| Review agent | AgentDS |
| PR | [#128](https://github.com/noho/dayu-agent-r/pull/128) |
| Branch | `work/wu-tools-01-f01-02-cancellation` |
| Design sources | `docs/host/design.md`, `docs/engine/design.md` |
| Plan | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| Control doc | `docs/host/issues-implementation-control.md` |
| Prior gate | Aggregate deepreview PASS (`627b2ca9`) |
| Date | 2026-06-08 |

## Validation

### 1. PR 远端 diff 与本地 accepted commits / artifacts 一致

| 检查项 | 方法 | 结果 |
|---|---|---|
| Commit SHAs | `git log main..HEAD` vs `gh pr view 128 --json commits` | **PASS** — 13/13 SHAs 完全一致 |
| 文件列表 | `git diff main..HEAD --stat` vs PR files | **PASS** — 66 files, +7772/-156, 两边一致 |
| WU 范围外改动 | 逐文件核对 plan Section 5 allowed list | **PASS** — 无范围外生产文件改动 |
| Whitespace | `git diff --check main..HEAD` | 4 个 trailing whitespace 均在 `docs/reviews/` 下，非生产代码 |

PR 包含的 13 个 commits 与本地 accepted chain 完全匹配（`af3ac6b8` → `5f220c4e`）。PR 标题 "WU-TOOLS-01-F01-02 cancellation propagation audit" 与 PR description 中的 Summary / Validation / Residual Risks 与 plan 和 aggregate deepreview 裁决一致。

控制文档变更（`docs/host/issues-implementation-control.md`）仅包含 gate/status/next-entry 的 bookkeeping 更新，从 WU-TOOLS-01-F01-01 的 final closeout 过渡到 WU-TOOLS-01-F01-02 的 draft PR blocked 状态。不涉及生产代码或架构边界变更。

### 2. 已迁移 Fins / Web / Doc tools 的 CancellationToken 传递和取消响应

#### Fins Download / Preprocess Awaiting Tools（Slice 1）

**证据**：

| 位置 | 行为 | 证据 |
|---|---|---|
| `dayu/fins/tools/download_tools.py:80-81` | 读取 `context.cancellation_token`，不再 `del context`；start 前 checkpoint | 第 80 行 `cancellation_token = context.cancellation_token`；第 81 行 `cancellation_token.is_cancelled()` |
| `dayu/fins/tools/preprocess_tools.py:79-81` | 同上 | 第 79-81 行 |
| `dayu/fins/tools/download_tools.py:86-89` | start 后检查 CANCELLING/CANCELLED 状态，捕获 `FinsIngestionStartCancelledError` | 第 86-89 行 |
| `dayu/fins/tools/download_tools.py:117-140` | `_cancelled_outcome` 返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` | 第 131-132 行 |
| `dayu/fins/ingestion_runtime.py:1049` | `_raise_if_start_cancelled` — durable record 创建前同步 checkpoint（download） | 第 1049 行 |
| `dayu/fins/ingestion_runtime.py:1106` | 同上（preprocess） | 第 1106 行 |
| `dayu/fins/ingestion_runtime.py:1058-1059` | `_start_lock` 内 `_is_start_cancelled` → `_save_cancelled` → 返回 cancelled start → 不 submit | 第 1058-1059 行 |
| `dayu/fins/ingestion_runtime.py:1115-1116` | 同上（preprocess） | 第 1115-1116 行 |
| `dayu/fins/ingestion_runtime.py:126` | `FinsIngestionStartCancelledError(RuntimeError)` 定义 | 第 126 行 |
| `dayu/fins/ingestion_runtime.py:2639-2669` | `_is_start_cancelled` / `_raise_if_start_cancelled` 模块级 helper | 第 2639-2669 行 |

**invariant 验证**：

| Invariant | 状态 |
|---|---|
| token cancelled before start 不创建 job | PASS — `_raise_if_start_cancelled` 在 `_create_queued_record_with_start_lock` 之前 |
| token cancelled between create and submit 收口为 cancelled 且不 submit | PASS — `_start_lock` 内同步 checkpoint → `_save_cancelled` |
| durable job create 后、submit 前取消检查是同步 checkpoint | PASS — 在 `_start_lock` 持有期间 |
| token not cancelled 保留现有 awaiting outcome 行为 | PASS — 正常路径未修改 |
| Host cancel truth 不变 | PASS — token 仅在 start 边界观察；submit 后不再用 token 做 truth |

#### Web Search / Fetch（Slice 2）

**证据**：

| 位置 | 行为 | 证据 |
|---|---|---|
| `dayu/tools/web/web_tools.py:1059` | `search_web` 装饰器声明 `execution_context_param_name="execution_context"` | 第 1059 行 |
| `dayu/tools/web/web_tools.py:1076` | `search_web` 签名增加 `execution_context: BatchToolExecutionContext \| None = None` | 第 1076 行 |
| `dayu/tools/web/web_tools.py:1095-1096` | `_resolve_execution_cancellation_token` + `_raise_if_tool_cancelled` | 第 1095-1096 行 |
| `dayu/tools/web/web_tools.py:1112` | `cancellation_token` 传入 `search_public_web` | 第 1112 行 |
| `dayu/tools/web/web_search_providers.py:152` | `search_public_web` 签名增加 `cancellation_token` 参数 | 第 152 行 |
| `dayu/tools/web/web_search_providers.py:187` | query/domain 归一化后 checkpoint | 第 187 行 |
| `dayu/tools/web/web_search_providers.py:190` | provider 候选循环入口 checkpoint | 第 190 行 |
| `dayu/tools/web/web_search_providers.py:192` | 每次 provider 尝试前 checkpoint | 第 192 行 |
| `dayu/tools/web/web_search_providers.py:226` | provider 结果返回后 checkpoint | 第 226 行 |
| `dayu/tools/web/web_search_providers.py:228-229` | 取消错误透传，不吞掉 | 第 228-229 行 |
| `dayu/tools/web/web_search_providers.py:263-282` | `_raise_if_search_cancelled` 通过 `ToolBusinessError(code="tool_cancelled")` 抛出 | 第 278-281 行 |

**invariant 验证**：

| Invariant | 状态 |
|---|---|
| execution_context 不在 LLM-facing schema 中 | PASS |
| 取消后不尝试后续 fallback provider | PASS |
| Provider 循环每轮入口 check token | PASS |

#### Doc Tools（Slice 3）

**证据**：

| 工具 | `execution_context_param_name` | 证据行号 |
|---|---|---|
| `list_files` | ✅ | `doc_tools.py:278` |
| `get_file_sections` | ✅ | `doc_tools.py:391` |
| `search_files` | ✅ | `doc_tools.py:713` |
| `read_file` | ✅ | `doc_tools.py:937` |
| `read_file_section` | ✅ | `doc_tools.py:1071` |

模块级 helper：`_resolve_doc_cancellation_token`（第 115-132 行）、`_raise_if_doc_cancelled`（第 135-150 行）、`_raise_doc_cancelled`（第 153-174 行）。所有 checkpoint 通过 `ToolBusinessError(code="tool_cancelled")` 抛出。

**checkpoint 密度验证**（逐工具）：

| 工具 | 入口 | 循环内 | 阻塞I/O前 | 返回前 |
|---|---|---|---|---|
| `list_files` | ✅(317) | ✅(325) | — | ✅(346) |
| `get_file_sections` | ✅(423) | ✅(429) | ✅(438) | — |
| `search_files` | ✅(754) | ✅(756,770) | ✅(783) | ✅(797) |
| `read_file` | ✅(983) | — | ✅(986) | ✅(1000) |
| `read_file_section` | ✅(1115) | — | ✅(1129) | ✅(1140) |

#### Fins Read Tools（Slice 4）

**证据**：

| 工具 | `execution_context_param_name` | 证据行号 |
|---|---|---|
| `list_documents` | ✅ | `fins_tools.py:197` |
| `get_document_sections` | ✅ | `fins_tools.py:281` |
| `read_section` | ✅ | `fins_tools.py:362` |
| `search_document` | ✅ | `fins_tools.py:460` |
| `list_tables` | ✅ | `fins_tools.py:563` |
| `get_table` | ✅ | `fins_tools.py:650` |
| `get_page_content` | ✅ | `fins_tools.py:732` |
| `get_financial_statement` | ✅ | `fins_tools.py:820` |
| `query_xbrl_facts` | ✅ | `fins_tools.py:913` |

`_resolve_fins_cancellation_token`（`fins_tools.py:37-54`），所有 9 个工具将 `cancellation_token` 传入 `read_runtime` 对应方法。

`dayu/fins/tools/read_runtime.py`：`_raise_if_fins_cancelled` / `_raise_fins_cancelled`（第 122-161 行），所有公开 read 方法在入口和高风险边界（仓储访问、processor 操作、搜索循环、XBRL 查询）做 checkpoint。search_engine 有独立 `_raise_if_search_cancelled`（`search_engine.py:59-82`）。

**整体统计**：

| 工具族 | 工具数 | context 注入 | 不丢弃 context | 长事务 checkpoint |
|---|---|---|---|---|
| Fins awaiting | 2 | N/A（direct callable） | ✅（不再 `del context`） | ✅（start 前/中/后） |
| Web | 2 | ✅ | ✅ | ✅（provider 循环） |
| Doc | 5 | ✅ | ✅ | ✅（文件遍历/processor） |
| Fins read | 9 | ✅ | ✅ | ✅（仓储/搜索/XBRL） |

**合计：18/18 工具完成 token 传递审计**。

### 3. Host cancel 真源未被替代；两阶段启动未被擅自实现

| 检查项 | 方法 | 结果 |
|---|---|---|
| 工具私有 cancel 状态 | Grep `dayu/fins` 整个目录搜索 `two.?stage\|prepare.*activate\|activate.*prepare\|prepare_job\|activate_job\|awaiting.accepted` | **PASS** — 无匹配 |
| Host wait adapter / Fins runtime contract 扩大 | 读取 `ingestion_runtime.py`、`wait_adapter.py` 接口签名 | **PASS** — `start_download/start_preprocess` 仅新增 `cancellation_token` keyword-only 参数；无 prepare/activate split |
| 工具 cancel 替代 Host cancel truth | 读取 tool callable 实现 | **PASS** — 工具只观察 token，Fins job cancel 仍通过 job store `request_cancel` / `claim_running_or_cancelled` / `save_cancelled` |

### 4. LLM-facing schema 不泄漏内部治理字段

**证据**：

`tests/tools/test_combined_tools_acceptance.py:205-210`：
```python
for definition in discovered_tools.tool_bundle.definitions:
    properties = definition.schema.function.parameters.properties
    assert "execution_context" not in properties
    assert "cancellation_token" not in properties
    assert "execution_context" not in definition.schema.function.parameters.required
    assert "cancellation_token" not in definition.schema.function.parameters.required
```

该测试覆盖全部 18 个迁移工具（Fins read 9 + Doc 5 + Web 2 + Fins awaiting 2 的直接 callable schema 由 ingestion tool helpers 管理，不在 bundle 中，但 helpers 生成的 schema 同样不暴露这些字段）。

`execution_context_param_name` 是 `@tool` 装饰器 metadata，adapter 在调用时注入但不在 schema 中暴露。

### 5. README、tests、pyright、residual risk

| 检查项 | 方法 | 结果 |
|---|---|---|
| Fins tests | `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q` | **PASS** — 69 passed |
| Web/Doc/Combined tests | `pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q` | **PASS** — 44 passed |
| pyright | `pyright dayu/fins dayu/tools tests/fins tests/tools` | **PASS** — 0 errors, 0 warnings |
| `dayu/fins/README.md` | `git diff main..HEAD -- dayu/fins/README.md` | ✅ — 更新 cancellation 语义（`cancellation_token` 参数、`FinsIngestionStartCancelledError` 契约、data flow 更新、状态机 arcs），属于 README `Agent更新约束` 的"当前代码已实现能力"范围 |
| `tests/README.md` | `git diff main..HEAD -- tests/README.md` | ✅ — 更新测试覆盖描述以反映新增 cancellation 测试 |
| Residual risk | 对照 aggregate deepreview residual risk reconciliation | **PASS** — 全部 4 个 plan residual risk 有明确 owner/destination |

**Residual risk 当前状态**：

| Risk ID | 状态 | Owner / Destination |
|---|---|---|
| R1 — Orphan job 窗口 / 两阶段启动 | deferred-with-owner | WU-WAIT-03 或独立 follow-up |
| R2 — 同步 I/O 不可物理中断 | accepted | 当前 WU；provider-specific runtime owner |
| R3 — Legacy adapter cancelled outcome 投影 | deferred-with-owner | 独立 adapter contract WU |
| R4 — Fins read runtime 深层 checkpoint | closed | 实现已完成 |

### 6. 控制文档 bookkeeping

`docs/host/issues-implementation-control.md` 的已提交变更（`5f220c4e`）仅为 gate/status/active-workunit/next-entry/blocking-questions 的 bookkeeping 字段更新，不涉及生产代码语义变更。注意：当前本地工作树中有该文件的未提交修改（`M docs/host/issues-implementation-control.md`），但不进入 PR diff，不影响本次 review。

## Findings

### F-DS-PR-01: `_save_cancelled` 在 create-submit gap 直接写 CANCELLED 终态（Non-blocking）

- **位置**：`dayu/fins/ingestion_runtime.py:1058-1059, 1115-1116`
- **事实**：`_save_cancelled` 直接设置 `status=CANCELLED`，不经过 `request_cancel` → `CANCELLING` 过渡。
- **分析**：create-submit gap 场景中 job 从未进入 RUNNING，直接 CANCELLED 终态语义正确。与 aggregate deepreview F-DS-01 同。不阻塞。
- **Severity**：Non-blocking

### F-DS-PR-02: Legacy Web/Doc/Fins read 取消通过 `ToolBusinessError` 而非 `ToolCancelledOutcome`（Known limitation）

- **位置**：`dayu/tools/doc_tools.py:170-174`, `dayu/fins/tools/read_runtime.py:157-161`, `dayu/tools/web/web_search_providers.py:278-282`
- **事实**：所有 legacy 工具取消统一通过 `ToolBusinessError(code="tool_cancelled")` → adapter → `ToolFailedOutcome`。
- **分析**：与 plan R3 一致。不影响 LLM 判断（稳定 error code），但不等价于 `ToolCancelledOutcome`。不阻塞。
- **Severity**：Non-blocking
- **Owner**：独立 adapter cancellation contract WU

### F-DS-PR-03: Review artifacts 存在 trailing whitespace（Cosmetic）

- **位置**：
  - `docs/reviews/wu-tools-01-f01-02-plan-rereview-ds.md:57`
  - `docs/reviews/wu-tools-01-f01-02-plan-review-mimo.md:103`
  - `docs/reviews/wu-tools-01-f01-02-slice1-code-review-ds.md:87`
  - `docs/reviews/wu-tools-01-f01-02-slice4-code-review-ds.md:178`
- **事实**：`git diff --check` 报 4 个 trailing whitespace。
- **分析**：仅在 review artifacts 中，非生产代码。`git diff --check` 报错但 `git am` / `git apply` 不阻塞。不阻塞。
- **Severity**：Non-blocking

## Conclusion

**PASS** — 无 blocking finding。

WU-TOOLS-01-F01-02 PR #128 通过 draft-PR-review gate：

1. **PR 一致性**：远端的 13 个 commits、66 个文件与本地 accepted chain 完全一致，无范围外改动。
2. **Token 传递审计**：全部 18 个已迁移工具完成 CancellationToken 传递审计；Fins download/preprocess 不再丢弃 context；Web search 补齐 execution context 注入；Doc 5 工具和 Fins read 9 工具 100% context 注入。
3. **Host cancel 真源保留**：工具只观察 token；Fins job cancel 仍以 job store 为真源；无工具私有 cancel 状态；两阶段启动未被擅自实现。
4. **LLM-facing schema 清洁**：`test_combined_tools_acceptance` 硬断言全部工具 schema 不含 `execution_context` / `cancellation_token`。
5. **验证充分**：全部 113 个测试通过；pyright 零报错；README 更新在合理范围内；全部 4 个 plan residual risk 有明确 owner/destination。
6. **3 个 non-blocking findings**（F-DS-PR-01/02/03）均为 plan 已知限制或 cosmetic issue，不影响 draft-PR-pass 裁决。
