# WU-TOOLS-01-F01-02-R3 Slice 3 Code Review — DS

## 1. Verdict

**PASS_WITH_FINDINGS** — 无 blocking findings。3 条 LOW severity actionable findings，4 条 INFO observations。

Slice 3 的 Fins read native tools 实现正确达成 plan 目标：九个工具的声明、参数校验、取消语义、错误投影、storage 边界、provider lock 并发控制均正确。取消不会被 semantic enrichment fallback、parent-title fallback、XBRL filtering 或 search expansion 路径吞掉。测试矩阵覆盖了 plan 要求的全部 cancellation checkpoint 场景。

---

## 2. Review Scope

依据 `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` Slice 3 边界，审查以下文件当前未提交改动：

| 文件 | 行数 | 角色 |
|---|---|---|
| `dayu/fins/tools/provider.py` | 267 | Provider discovery，config 解析，`include_read_tools=false` |
| `dayu/fins/tools/fins_tools.py` | 1478 | 九个原生 `ToolDefinition`/`ToolCallable` 定义 |
| `dayu/fins/tools/read_runtime.py` | 2099 | FinsReadRuntime 业务体，含 cancellation checkpoint |
| `dayu/fins/tools/read_runtime_helpers.py` | 1900 | 领域错误类型、辅助函数、`raise_if_fins_cancelled` |
| `dayu/fins/tools/search_engine.py` | 1355 | 搜索引擎核心，含搜索循环内取消检查 |
| `tests/fins/test_fins_storage_provider.py` | 1618 | 迁移后的 provider/tools 测试 |

对照真源：

- `AGENTS.md` — 编码硬约束、Agent 语义约束
- `docs/host/design.md` §ToolRuntime、§ToolsDiscovery
- `docs/engine/design.md` §10-13 — 工具调用协议、outcome 联合、取消语义
- `docs/host/issues-implementation-control.md` — R3 active work unit、residual risk 追踪
- `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` §8 Slice 3

---

## 3. Key Positive Confirmations

### 3.1 取消语义未被吞掉（adversarial pass）

逐一追踪了 plan 要求的全部取消路径，结论是取消在所有路径中正确投影为 `ToolCancelledOutcome(reason=host_cancelled)`：

**(a) search_document 语义增强降级块** — `read_runtime.py:578-599`

```python
try:
    # ... list_sections + enrich + bm25f + semantic profiles ...
except FinsReadCancelledError:
    raise          # ← 显式 re-raise，先于 except Exception
except Exception:
    pass           # ← 降级：索引/画像构建失败不阻断搜索
```

`FinsReadCancelledError` 在 `except Exception` 之前被捕获并 re-raise。测试 `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed` (line 797) 通过 monkeypatch 注入 `_raise_fins_cancelled_during_semantic_enrichment` 验证该路径。

**(b) read_section 父标题查询降级块** — `read_runtime.py:441-447`

```python
try:
    _raise_if_fins_cancelled(cancellation_token)
    parent_title = processor.get_section_title(str(parent_ref))
    _raise_if_fins_cancelled(cancellation_token)
except FinsReadCancelledError:
    raise          # ← 显式 re-raise
except Exception:
    parent_title = None   # ← 父标题查询失败降级
```

测试 `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed` (line 870) 验证 `_ParentTitleLookupCancellingProcessor` 在 `get_section_title` 中触发取消后正确投影。

**(c) search_document 搜索循环** — `search_engine.py:576-663`

`_execute_query_search` 在精确搜索前后、扩展阶段遍历、每个扩展查询前后均调用 `_raise_if_search_cancelled(cancellation_token)`。无 try/except 可吞掉 `FinsReadCancelledError`。

测试 `test_search_document_cancellation_during_search_stops_before_all_candidates` (line 765) 验证 keyword 模式下 `processor.search("annual")` 触发取消后不再继续执行 `"recurring"` 和 `"revenue"` 的后续搜索。

**(d) XBRL facts 过滤检查** — `read_runtime.py:1329-1340`

```python
raw_facts_for_checkpoint = payload.get("facts")
if isinstance(raw_facts_for_checkpoint, list):
    for _raw_fact in raw_facts_for_checkpoint:
        _raise_if_fins_cancelled(cancellation_token)
# ...
facts = normalized_payload.get("facts")
if isinstance(facts, list):
    for _fact in facts:
        _raise_if_fins_cancelled(cancellation_token)
```

两段事实迭代中均插入了取消检查点。无 try/except 包裹。

测试 `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly` (line 901) 验证 `_XbrlFactsProcessor` 返回 3 条 facts 后 token 被取消，第一条 fact 的 `_raise_if_fins_cancelled` 即触发取消 outcome。

**(e) pre-cancel** — `fins_tools.py:770-772`（lock 前）、`fins_tools.py:774-775`（lock 后）

测试 `test_list_documents_pre_cancel_returns_cancelled_outcome` (line 747) 验证入口即取消场景。

**(f) processor create 后立即取消** — `read_runtime.py:1971-1989`

`_get_or_create_processor` 在 `_create_processor` 返回后检查取消。测试 `test_read_section_cancelled_before_processor_read_returns_cancelled_outcome` (line 834) 通过 `cancel_token_after_create` 参数在 processor 创建后立即标记取消，验证 `read_section` 在调用 `processor.read_section()` 之前返回 cancelled outcome。

### 3.2 九个工具顺序、schema、tags、display、truncate

`FINS_READ_TOOL_NAMES` (`fins_tools.py:56-66`) 严格按 plan 顺序排列：

```
list_documents → get_document_sections → read_section → search_document →
list_tables → get_table → get_page_content → get_financial_statement → query_xbrl_facts
```

每个工具：
- 均有 `tags=("fins",)` (`fins_tools.py:44`)
- 均有中文 `display_name`
- 截断声明使用 `ToolTruncateSpec` 当前契约（`list_truncate`/`text_truncate` helper）
- LLM-facing schema 不包含 `execution_context`、`cancellation_token` 等治理字段
- 测试 `test_fins_read_tool_schemas_do_not_expose_execution_context` (line 684) 直接断言 schema properties/required 不包含治理字段

### 3.3 Provider lock — SERIAL_PER_PROVIDER

`build_fins_read_tool_definitions` (`fins_tools.py:93`) 创建一把 `asyncio.Lock()`，传递给九个 builder 函数，九个 callable 通过闭包共享同一实例。

锁获取时机（`fins_tools.py:773`）：
1. 参数 schema 校验（`validate_and_project_arguments`）在锁外
2. pre-cancel checkpoint 在锁外（line 771）
3. `async with provider_lock:` 内再次检查取消（line 774）
4. 业务逻辑在 `asyncio.to_thread` 内执行

锁释放由 `async with` 保证，异常安全。无死锁风险（单锁，无嵌套获取）。

测试 `test_same_provider_read_tools_do_not_enter_read_runtime_concurrently` (line 932) 通过 `_ConcurrentReadRuntimeProbe` 记录并发进入计数，断言 `max_active_count == 1`。

### 3.4 Storage 边界保持

`provider.py:61-62`：
```python
runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
read_runtime = runtime.get_read_runtime(processor_cache_max_entries=limits.processor_cache_max_entries)
```

所有财报文件读取均通过 `FinsReadRuntime` → `ProcessorRegistry` → `DocumentProcessor` → 仓储协议。无直接 `Path` 拼接读取财报文件。

测试 `_build_fins_workspace` (line 1125) 仍通过 `FsCompanyMetaRepository`、`FsSourceDocumentRepository`、`FsDocumentBlobRepository` 构造 fixture，不绕过 `dayu.fins.storage`。

### 3.5 `include_read_tools=false` 行为

`provider.py:51-57`：
```python
if not include_read_tools:
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(source_ref,),
        definitions=(),
    )
```

不解析 `workspace_root`，不创建 `DefaultFinsRuntime`。测试 `test_fins_provider_can_disable_read_tools_without_workspace_root` (line 700) 验证传入 `workspace_root: None` 时也不触发 `ValueError`。

### 3.6 错误码语义保持

| 场景 | 投影 | 证据 |
|---|---|---|
| 参数 schema 非法 | `ToolFailedOutcome(error="invalid_argument")` | `fins_tools.py:877-903` |
| 业务错误（ticker 未收录等） | `ToolFailedOutcome(error=exc.code, message=exc.message, hint=exc.hint)` | `fins_tools.py:795-803` |
| 文件不存在 | `ToolFailedOutcome(error="file_not_found")` | `fins_tools.py:804-812` |
| 权限拒绝 | `ToolFailedOutcome(error="permission_denied")` | `fins_tools.py:813-821` |
| 未预期异常 | `ToolFailedOutcome(error="execution_error")` | `fins_tools.py:822-830` |
| Host 取消 | `ToolCancelledOutcome(reason="host_cancelled")` | `fins_tools.py:778-785` |

### 3.7 Legacy adapter 零依赖

`test_fins_read_tools_do_not_import_retired_adapter` (line 659) 对六个文件做字符串级禁止词检查。Controller 验证 `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|ToolBusinessError\(.*tool_cancelled" dayu/fins/tools tests/fins/test_fins_storage_provider.py` 无命中。

### 3.8 AGENTS.md 合规

- 所有函数/类/模块有完整中文 docstring ✅
- 无 `object`、`Any` 扩散（`read_runtime.py:15` 的 `Any` 在 `Optional[dict[str, Any]]` 中属于 JSON 载荷边界，是合理的）✅
- 无 `hasattr`/`getattr` 逃避类型设计 ✅
- 无兼容 re-export、兼容 facade、兼容 wrapper ✅
- 无魔法数字（字符串字面量在 tool schema 内属于例外）✅
- 无 `_legacy_adapter` 依赖 ✅
- 无反向依赖（`test_fins_import_boundaries_do_not_reverse_depend` line 1099 覆盖）✅

---

## 4. Findings

### F001 [LOW] `_cancelled_from_token` 的 `cancel_reason()` 直接嵌入 LLM-facing message

**文件**: `dayu/fins/tools/fins_tools.py:925-929`

```python
reason = cancellation_token.cancel_reason()
message = "财报读取工具调用已被取消。"
if reason is not None and reason.strip() != "":
    message = f"{message}取消原因: {reason}"
```

**分析**: `CancellationToken.cancel_reason()` 是公共契约方法，返回 `str | None`。当前测试 token 返回 `"test cancellation"`，生产 token 的实现未在本 slice 变更范围内。该 message 最终进入 `ToolCancelledOutcome.message`，会被 LLM 作为 tool message 消费。若生产 token 的 `cancel_reason()` 返回含 Host 内部术语的值，可能违反 Agent 语义约束（AGENTS.md:36-41）。

**缓解**: 当前 `_assert_host_cancelled_outcome` 已断言 `"run_id" not in (outcome.message or "")` 和 `"cancellation_token" not in (outcome.hint or "")`。但未覆盖 `cancel_reason()` 可能返回的其他治理术语。

**建议**: 在 `_assert_host_cancelled_outcome` 或新增 focused test 中，用 mock token 返回典型生产 `cancel_reason` 值（如空字符串、`"host_cancelled"`），断言 message 不包含 `run_id`、`session_id`、`correlation_id`、`execution_id`、`attempt_id`、`event_sequence`、`digest`、`payload_ref` 等 Host 内部标识。或在 `_cancelled_from_token` 中显式过滤/不嵌入 `cancel_reason()`，改用固定的 LLM-readable 消息。

### F002 [LOW] 参数提取 helper 在 provider lock 内执行

**文件**: `dayu/fins/tools/fins_tools.py:163-177`（及九个 builder 中的类似模式）

**分析**: `_required_string`、`_optional_string` 等 helper 在 `business_call` lambda 内被调用，该 lambda 在 `_invoke_fins_read_business` 的 `async with provider_lock:` 块内通过 `asyncio.to_thread` 执行。虽然这些 helper 只是字典查表和 `isinstance` 检查（schema 验证已在锁外完成），理论上不应失败，但若未来有人新增一个会抛 `FinsReadArgumentError` 的复杂参数提取逻辑，该失败将在持有 lock 的情况下发生并需要线程调度。

**当前严重度**: LOW。这些 helper 在当前实现中是 O(1) 的纯类型提取，不会阻塞。且 lock 由 `async with` 保证释放，无泄漏风险。

**建议**: 长期可考虑将参数提取提升到 `_invoke_fins_read_business` 调用之前，在锁外完成。这样 `business_call` 只接收已提取的强类型参数，不需要在闭包内做 `_required_string` 调用。当前不需要修复。

### F003 [LOW] `build_fins_read_tool_definitions` 与 `_validate_fins_definitions` 存在重复名称校验

**文件**: `dayu/fins/tools/fins_tools.py:105-107` 与 `dayu/fins/tools/provider.py:240-242`

**分析**: 两处校验逻辑完全相同——比较 `tuple(definition.name for definition in definitions)` 与 `FINS_READ_TOOL_NAMES`。`build_fins_read_tool_definitions` 中已保证输出顺序与 `FINS_READ_TOOL_NAMES` 一致，`_validate_fins_definitions` 的 names 校验是冗余防御。

**建议**: 保留 `_validate_fins_definitions`（provider 层防御是合理的），但可简化断言——只检查 `definitions` 的 names 等于 `FINS_READ_TOOL_NAMES` 而不需同时在 builder 内做同样的检查。或在 builder 内只做 `Log.verbose` 而不抛 `ValueError`。当前双重校验不影响正确性，作为 INFO 级记录。

---

## 5. Observations (INFO)

### OBS-01: `_optional_number` 精度丢失风险

**文件**: `dayu/fins/tools/fins_tools.py:1393`

```python
return float(value)
```

`float` (IEEE 754 double) 的有效精度约 15-17 位十进制数字。对于 XBRL `min_value`/`max_value` 过滤，若传入 `10**18`（百亿亿级别，如某些 hyperinflation 货币或总资产），转换为 float 后会丢失精度。这是已有行为模式，非本 Slice 引入，记录供后续 XBRL 精度专项处理。

### OBS-02: Schema 声明常量散落在各 builder 函数内

九个 schema 声明函数（`_list_documents_parameters` 等）定义在 `fins_tools.py` 模块底部（line 938-1239），与对应的 builder 函数分离。这种布局在当前规模下可接受，但若未来工具数增加，可考虑抽取到独立 `_schemas.py` 模块。非本 Slice 问题。

### OBS-03: `_SearchCancellingProcessor` 的 `supports` 接受所有 source

**文件**: `tests/fins/test_fins_storage_provider.py:214-234`

```python
@classmethod
def supports(cls, source, *, form_type=None, media_type=None) -> bool:
    del source, form_type, media_type
    return True
```

测试 processor 的 `supports` 返回 `True` 对所有 source。这是测试 fixture 的合理简化，因为测试通过 `_install_processor` monkeypatch 注入 processor，实际不会走到 `supports` 的注册匹配路径。但若未来有人复用 `_SearchCancellingProcessor` 到需要真实 processor 注册表匹配的测试场景，需注意此简化。

### OBS-04: `_invoke_fins_read_business` 的通用 `except Exception` 可能掩盖未知取消路径

**文件**: `dayu/fins/tools/fins_tools.py:822-830`

```python
except Exception:
    return failed_outcome(
        tool_name=tool_name,
        error="execution_error",
        ...
    )
```

当前所有已知的取消路径均通过 `FinsReadCancelledError` 传播，在 `except Exception` 之前被捕获。但如果未来有人在深层业务代码中引入一个新的取消异常类型（不继承 `FinsReadCancelledError`），会被此处分笼统地投影为 `execution_error`。当前无此类新异常类型，记录为防御性观察。

---

## 6. Adversarial Cancellation Pass

以下六个 cancellation checkpoint 场景均已通过测试直接验证，无吞并取消的路径：

| # | 场景 | 测试函数 | 断言 |
|---|---|---|---|
| 1 | pre-cancel | `test_list_documents_pre_cancel_returns_cancelled_outcome` | `ToolCancelledOutcome` + `host_cancelled` + meta |
| 2 | search loop cancel | `test_search_document_cancellation_during_search_stops_before_all_candidates` | 只执行 1 次 `processor.search` |
| 3 | semantic enrichment cancel | `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed` | `processor.search_calls == []` |
| 4 | read before processor | `test_read_section_cancelled_before_processor_read_returns_cancelled_outcome` | `processor.read_section_calls == 0` |
| 5 | parent title lookup cancel | `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed` | `processor.get_section_title_calls == 1` |
| 6 | XBRL filtering cancel | `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly` | `processor.query_calls == 1` |

所有六个测试均通过 `_assert_host_cancelled_outcome` 断言：
- `isinstance(outcome, ToolCancelledOutcome)`
- `outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED`
- `outcome.meta is not None`
- `outcome.meta.tool_name == tool_name`
- `outcome.meta.started_at <= outcome.meta.finished_at`
- `"run_id" not in (outcome.message or "")`
- `"cancellation_token" not in (outcome.hint or "")`

---

## 7. Controller Verification Reconciliation

Controller 已验证：
- `pytest tests/fins/test_fins_storage_provider.py` — 21 passed ✅
- `pytest tests/fins/test_fins_ingestion_tools.py -k cancellation` — 1 passed ✅
- `pyright` — 0 errors ✅
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|ToolBusinessError\(.*tool_cancelled" dayu/fins/tools tests/fins/test_fins_storage_provider.py` — 0 matches ✅
- `git diff --check` — passed ✅

Reviewer 独立验证了以上结果与本地代码一致性。

---

## 8. README 触发判断

- `dayu/fins/` 修改触发 `dayu/fins/README.md` 检查。当前改动是从 legacy adapter 迁移到 native current `ToolDefinition`，不改变 Fins 包对外能力、storage 边界、read tool 列表或 provider 行为。`dayu/fins/README.md` 若已描述 current `ToolDefinition` 边界则无需更新。不在本 review 中强制修改 README。
- `tests/` 修改触发 `tests/README.md` 检查。测试从 legacy collector 迁移到 native builder，但测试层分类（fins storage provider tests）和测试策略未变。建议 Slice 4（adapter deletion）完成后统一更新 `tests/README.md`。

---

## 9. Summary

| 维度 | 结论 |
|---|---|
| 取消语义 | PASS — 全部六类 checkpoint 正确投影 `ToolCancelledOutcome(host_cancelled)`，无吞并 |
| 工具声明 | PASS — 九个工具顺序、schema、tags、display、truncate 符合 plan |
| provider lock | PASS — 单锁共享，lock 获取时机正确，异常安全 |
| storage 边界 | PASS — 通过 `DefaultFinsRuntime`/仓储协议，无直接路径访问 |
| 错误投影 | PASS — `invalid_argument`/业务错误码/`file_not_found`/`permission_denied`/`execution_error` 语义正确 |
| legacy 零依赖 | PASS — AST + source string 双重验证 |
| AGENTS.md | PASS — docstring、类型签名、无 Any/object 扩散、无兼容 wrapper |
| 测试覆盖 | PASS — 21 个 focused tests + 1 cancellation smoke，覆盖全部 checkpoint |
| **总体** | **PASS_WITH_FINDINGS** — 3 LOW findings，0 blocking |

---

## 10. Actionable Findings Summary

| ID | Severity | 文件 | 行号 | 说明 | 建议动作 |
|---|---|---|---|---|---|
| F001 | LOW | `fins_tools.py` | 925-929 | `cancel_reason()` 直接嵌入 LLM-facing message | 补 focused test 断言 message 不含 Host 内部标识 |
| F002 | LOW | `fins_tools.py` | 163-177 | 参数提取 helper 在 lock 内执行 | 长期可将参数提取提升到 lock 外；当前可接受 |
| F003 | LOW | `fins_tools.py:105` / `provider.py:240` | — | 双重名称顺序校验 | 可保留 provider 层防御，builder 内降级为 log |

---

*Reviewer: DS (Claude Fable 5)*
*Date: 2026-06-10*
*Artifact: docs/reviews/wu-tools-01-f01-02-r3-slice3-code-review-ds.md*
