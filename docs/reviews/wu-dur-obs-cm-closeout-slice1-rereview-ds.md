# WU-DUR / WU-OBS / WU-CM Closeout Slice 1 Re-Review (AgentDS)

## Gate

- Work unit: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01
- Gate: Slice 1 re-review
- Implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice1-implementation-codex.md`
- Fix artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice1-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-controller-adjudication.md`

## Verdict

**pass-with-findings** (1 non-blocking correctness observation, 0 blocking findings).

## 复审范围

- 当前 git diff 六文件：`dayu/host/durable/schema.py`、`dayu/host/tool_runtime.py`、`dayu/host/payload_resolution.py`、`dayu/host/engine_ingest.py`、`tests/host/test_toolruntime_accept_barrier.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_tool_trace_projection.py`、`tests/host/test_durable_schema.py`。
- README 变更：`dayu/host/README.md`、`tests/README.md`。
- 测试运行结果：119 passed，pyright 0 errors。
- 复审仅按 controller 裁决的两项 accepted fix、Slice 1 原始实现的 blocking correctness / durable schema / LLM-facing / 分层边界问题展开；不重新裁决 deferred finding F1。

## 已核验的 Accepted Fixes

### Fix 1: Storage kind 常量单一真源

**状态：已完全修复，无残留。**

证据：

- `dayu/host/durable/schema.py:204-223`：定义全部 7 个 storage kind / descriptor kind 模块级常量。
- `dayu/host/tool_runtime.py:87-93`：写路径 import 上述常量，`_tool_call_request_payload_plan()` 和 `_semantic_query_payload_plan()` 内使用 `TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON`、`TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR`、`TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT` 等。
- `dayu/host/payload_resolution.py:17-24`：读路径 import 同样常量，`_read_arguments_json()` 和 `_read_semantic_query()` 内统一分支。
- `tests/host/test_durable_schema.py:70-71, 840-847`：测试 import schema 常量，并通过 `test_tool_call_request_payload_descriptor_kinds_are_stable()` 锁定 descriptor kind 字符串值。

两个模块再无私有重复的存储形态字符串常量；读路径和写路径、测试路径共享同一真源。`TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR` 与 `TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR` 字符串值同为 `"payload_descriptor"`，与设计 contract appendix 一致，语义上通过 descriptor metadata 中的 `descriptor_kind`（`tool_call_arguments_json` vs `tool_call_semantic_query_text`）区分。

### Fix 2: inline_json / inline_text 携带 payload ref 的 fail-closed 检查

**状态：已完全修复，测试覆盖充分。**

证据（读路径）：

- `dayu/host/payload_resolution.py:237-239`：`_read_arguments_json()` 在 `storage_kind == inline_json` 分支内，若 `arguments_payload_ref is not None` 则 `raise HostDurableError("inline tool call arguments must not carry payload ref")`。
- `dayu/host/payload_resolution.py:291-293`：`_read_semantic_query()` 在 `storage_kind == inline_text` 分支内，若 `semantic_query_payload_ref is not None` 则 `raise HostDurableError("inline semantic query must not carry payload ref")`。
- 额外 fail-closed 防御：`_read_semantic_query()` 在 `absent` 分支（`payload_resolution.py:283-289`）拒绝非 null `semantic_query_text` / `semantic_query_payload_ref` / `semantic_query_digest`；在 `descriptor` 分支通过 `_validate_descriptor_kind` 校验 metadata `descriptor_kind`。

证据（测试）：

- `test_tool_call_request_atoms_reject_inline_arguments_payload_ref`（`test_toolruntime_accept_barrier.py`）：构造畸形 payload——`arguments_storage_kind == "inline_json"` 且 `arguments_payload_ref != None`，断言 `pytest.raises(HostDurableError, match="inline tool call arguments")`。
- `test_tool_call_request_atoms_reject_inline_semantic_query_payload_ref`（`test_toolruntime_accept_barrier.py`）：构造畸形 payload——`semantic_query_storage_kind == "inline_text"` 且 `semantic_query_payload_ref != None`，断言 `pytest.raises(HostDurableError, match="inline semantic query")`。

写路径不会产生这类畸形 payload（`_tool_call_request_payload_plan` 在写 payload_descriptor 时 `arguments_inline_json = None`，`_semantic_query_payload_plan` 在写 descriptor 时 `inline_text = None`），故 fail-closed 仅防御手动篡改或 bug 导致的畸形 durable payload。

## Findings

### F1 (NON-BLOCKING): 读者对 descriptor 路径下的反向畸形组合无显式防御

**Severity**: low（advisory）

**Location**: `dayu/host/payload_resolution.py:244-257` `_read_arguments_json()` descriptor 分支

**Evidence**:

`_read_arguments_json()` 在 `storage_kind == "payload_descriptor"` 分支不做 `arguments_inline_json is not None` 的 fail-closed 检查。若写入方或手动篡改使 hot payload 同时填入 `arguments_inline_json` 和 `arguments_payload_ref`（且 storage_kind 为 `"payload_descriptor"`），当前实现会静默忽略 inline 值、以 descriptor 路径读取，仅后续 digest 校验提供最终防线。

对比 semantic query 的 `_read_semantic_query()`，该函数在 `absent` 分支显式拒绝所有不应存在的字段（`payload_resolution.py:283-289`），防御粒度更细。

**实际风险**：写路径 `_tool_call_request_payload_plan()`（`tool_runtime.py:3347`）在 descriptor 路径将 `arguments_inline_json` 置为 `None`，且该函数是唯一写路径，因此生产路径不会产生此畸形。风险限于：恶意/损坏的 SQLite 数据库直接篡改 EventLog payload JSON 时，需同时篡改 hot payload 和对应的 SQLite payload descriptor body 使两份 digest 一致才能绕过双重 digest 校验（`payload_resolution.py:136-137` + `payload_resolution.py:143-144`）。实际攻击面极低。

**建议**：非阻塞，可在后续 cleanup 中补防御性 `is not None` 检查以统一防御粒度。

### F2 (VERIFIED NON-BLOCKING): `ToolAcceptCall.accepted_arguments` 可选默认值

**状态**：按 controller 裁决保持 deferred，未在本 gate 修改。

**证据**：`dayu/host/tool_runtime.py:448` 仍为 `accepted_arguments: Mapping[str, JsonValue] | None = None`。

当前生产路径保护链完整：
1. `_validate_tool_accept_call()`（`tool_runtime.py:4311-4321`）：当 `accepted_arguments is not None` 时校验与 `normalized_arguments_digest` 同源。
2. `_required_accepted_arguments()`（`tool_runtime.py:5227-5228`）：在写入 EventLog 前 `fail closed` —— 若为 None 则抛 `HostPayloadReferenceError`。
3. 仅低层测试 fake ack helper 可跳过此字段。

本次复审未发现新的 blocking 证据使 deferred decision 需要立即反转。

## 测试 / Pyright 核验

| 检查项 | 结果 |
|---|---|
| `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_durable_schema.py -q` | 119 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |

测试覆盖矩阵：

- 写路径小参数 inline：`test_tool_call_requested_carries_inline_arguments_atom`
- 写路径大参数 descriptor：`test_tool_call_requested_large_arguments_use_payload_descriptor`
- 写路径 digest mismatch fail closed：`test_tool_accept_call_rejects_arguments_digest_mismatch`
- 读路径畸形 inline + payload_ref：`test_tool_call_request_atoms_reject_inline_arguments_payload_ref`
- 语义 query absent / inline / descriptor：`test_tool_call_requested_semantic_query_inline_and_descriptor`
- 语义 query 畸形 inline + payload_ref：`test_tool_call_request_atoms_reject_inline_semantic_query_payload_ref`
- Tool Trace 大参数不内联：`test_tool_trace_does_not_inline_large_tool_call_arguments`
- Engine ingest preview normalized_arguments_digest：`test_tool_call_requested_and_result_accepted_are_preview` 内断言
- Schema 常量稳定：`test_tool_call_request_payload_descriptor_kinds_are_stable`
- 已有 digest 格式校验更新：`test_tool_accept_call_rejects_invalid_digest` 传入 `accepted_arguments`

Slip 1 未修改的测试文件（`test_engine_ingest_mapping.py`、`test_durable_schema.py`）回归通过，无退化。

## Remaining Risks

| Risk | Owner | Mitigation |
|---|---|---|
| `ToolAcceptCall.accepted_arguments=None` 在低层测试可跳过 durable truth | Slice 7 / closeout cleanup | 生产 accept 和 reuse 路径均 fail closed |
| Tool Trace hot projection 未携带 atom ref/digest 信号 | Later OBS scope（Slice 4） | 当前仅验证大参数不展开，不阻塞 Slice 1 |
| Compact evidence query_text 未接入 `tool_call_request_atoms()` | Slice 5 | Slice 1 已提供 reader 和稳定 contract |
| descriptor 路径反向畸形无显式防御（F1） | Non-blocking advisory | 双重 digest 校验提供有效防线 |
| `_validate_descriptor_kind` 与 `sqlite_payload_object` 双重读取同一 descriptor row | None（minor efficiency） | 同事务内幂等，不产生正确性问题 |

## README / Docs 核验

- `dayu/host/README.md`：新增 `TOOL_CALL_REQUESTED` accepted request atom 说明，正确表述 arguments / semantic query 冷热分离与 descriptor kind。
- `tests/README.md`：新增 ToolRuntime accept barrier 覆盖范围（inline arguments、arguments descriptor、semantic query absent/inline/descriptor、digest mismatch fail-closed）和 Engine ingest preview normalized arguments digest、Tool Trace 大参数 descriptor 边界。
- 未更新根 README（理由合理：未改变 CLI、trace/render 入口或项目级使用方式）。
- 未更新 `dayu/README.md`（理由合理：未改变 Host/Engine/Tool Trace 分层边界）。

## Ready for Controller Adjudication

是。Fix gate 的两项 accepted findings 已完全修复并通过测试验证。Slice 1 实现层面无新增 blocking finding。F1 为 non-blocking advisory，不影响推进到 Slice 2。
