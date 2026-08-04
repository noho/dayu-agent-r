# Interactive Conversation Memory closure F09：DS adversarial code review

## Gate identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Gate：DS adversarial code review（第二路独立 review，不依赖 MiMo）。
- Reviewed artifact：`codex/interactive-oracle` branch 上未提交 F09 slice。
- Implementation artifact：`docs/reviews/wu-interactive-memory-closure-f09-implementation-codex.md`。
- Accepted plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
- Review basis：direct production diff、public contract owner files、test changes、resolver/projector/manifest contracts、evidence material。
- Artifact path：`docs/reviews/wu-interactive-memory-closure-f09-code-review-ds.md`。

## Review scope

仅审不改。范围精确等于 git diff 的三个文件及被它们引用的 public contract owner：

- `dayu/host/compaction_operation.py` — 生产改动
- `tests/host/test_dispatch_scheduler.py` — integration test 改动
- `tests/host/test_tool_trace_queries.py` — unit test 改动
- `dayu/host/_runner_call_manifest.py` — hot/manifest typed contract owner（只读）
- `dayu/host/durable/tool_trace.py` — formal resolver/signal owner（只读）
- `dayu/host/durable/payload_resolution.py` — payload integrity owner（只读）
- `dayu/host/payload_resolution.py` — `sqlite_payload_object` host helper（只读）

## Adversarial check 1：为何修完 row descriptor 后 formal resolver 还需要 manifest projection artifact 字段

### Claim to falsify

"补齐 EventLog row descriptor（`payload_ref`/`payload_digest` 从 `None` 改为
`manifest_descriptor.payload_ref`/`manifest_digest`）后，不应再需要把 projection 三元组
写入 manifest body 和 hot atoms。"

### Evidence

生产改动前，`_compactor_runner_call_hot_payload` 把三个 projection artifact 字段设
为 `None`（`compaction_operation.py:1861-1865`）：

```python
runner_call_projection_artifact_ref=None,
runner_call_projection_artifact_digest=None,
runner_call_projection_artifact_size_bytes=None,
```

同时 manifest body 不包含 `runner_call_projection_artifact_ref` 等字段。

首轮 row descriptor 修复后，`_validated_runner_call_contract`（
`durable/tool_trace.py:1036-1059`）的 row/hot identity check 确实通过。但
`resolve_runner_call_projection_from_signal`（`durable/tool_trace.py:362-410`）**直接从
manifest raw JSON 读取字段**，不经过 typed contract 的 optionality：

```python
# durable/tool_trace.py:385-396
projection_ref = _json_optional_text(
    manifest.payload,
    _RUNNER_CALL_PROJECTION_ARTIFACT_REF,
)
...
if projection_ref is None:
    raise HostDurableError("runner-call manifest has no projection artifact ref")
```

关键细节：typed contract `RunnerCallInputManifest.projection_descriptor` 允许 `None`
（通过 `_parse_manifest_projection_descriptor` 的三元组全-none 逻辑）。但 formal resolver
**不使用** typed contract 的该字段，而是读取 `manifest.payload` raw JSON。这是 resolver
的设计选择——不依赖 typed contract 的 optionality，在 JSON 层面 fail closed。

若 manifest body 不包含 `runner_call_projection_artifact_ref`，则该字段在
`_json_optional_text` 中返回 `None`，触发 `"runner-call manifest has no projection
artifact ref"` 错误。首轮修复后确实命中此错误，implementation doc 如实记载。

### Verdict：CLAIM FALSIFIED

Formal resolver 的确需要这三个字段在 manifest JSON 中显式存在。不是 typed contract
约束不够，而是 resolver 在 JSON 层独立 fail closed，不走 typed contract optional 通路。
生产改动在 manifest body 中加入此三元组是正确的。

---

## Adversarial check 2：新增字段是否正确填充已有 typed contract（非 schema 扩张）

### Claim to falsify

"新增字段改变了 hot atoms 或 manifest 的 closed field set，属于 schema 扩张。"

### Evidence

逐一比对 typed contract owner `_runner_call_manifest.py` 的 frozen field sets：

**Hot atoms**（`RunnerCallHotAtoms`，line 324-369）的三个 projection 字段从存在起就定义为
`str | None` / `int | None`。F09 未新增字段，只把值从 `None` 改为 non-null。

**`_RUNNER_CALL_HOT_FIELDS`**（line 26-49）已包含此三字段（line 44-46）：

```python
"runner_call_projection_artifact_ref",
"runner_call_projection_artifact_digest",
"runner_call_projection_artifact_size_bytes",
```

F09 未修改该 frozen set。

**`_RUNNER_CALL_MANIFEST_PROJECTION_FIELDS`**（line 93-99）已定义此三字段。Manifest
field validator `_validate_manifest_fields`（line 1016-1025）已处理三字段的全有/全无
规则。F09 未修改 manifest field validator。

**`parse_runner_call_hot_payload`**（line 707-718）已按 Optional 解析此三字段。

**`_validate_hot_atoms`**（line 1750-1774）已有 "ref/digest/size must pair" 三元组配对
不变量。F09 未修改。

**`_validate_manifest_hot_identity`**（line 1612-1685）已把 projection triplet 纳入
hot/manifest 同源 identity tuple（line 1629-1647）。F09 未修改。

### Verdict：CLAIM FALSIFIED

所有 typed contract 字段已在 F09 之前存在且为 Optional。F09 只是 compactor producer 首次
填充 non-null 值。无 schema 扩张、无 field set 修改、无 contract 弱化。

---

## Adversarial check 3：projection digest/size/ref 是否与 payload descriptor 逐字节同源

### Claim to falsify

"manifest body 中的 `runner_call_projection_artifact_ref`/`digest`/`size_bytes` 与独立
projection descriptor 可能分裂：manifest body 用 `prepared_input.compactor_input_projection_digest`，
而 descriptor 写入使用另一个 digest 源。"

### Evidence

追踪完整值链（`compaction_operation.py:254-343`）：

**Step 1** — projection descriptor 写入：

```python
# line 256-275
projection_descriptor = self._payload_store.write_bounded_json_payload(
    transaction,
    BoundedJsonPayloadWriteRequest(
        payload_ref=projection_ref,
        ...
        expected_digest=(prepared_input.compactor_input_projection_digest),
    ),
)
```

`write_bounded_json_payload` 校验实际 payload bytes digest 等于
`prepared_input.compactor_input_projection_digest`，失败则拒绝写入。返回的
`projection_descriptor.payload_digest` 等于 `expected_digest`（由 `PayloadStore` 内部
保证）。

**Step 2** — manifest body 中字段取值：

```python
# line 282-284
compactor_input_projection_ref=projection_descriptor.payload_ref,
compactor_input_projection_digest=(projection_descriptor.payload_digest),
compactor_input_projection_size_bytes=(projection_descriptor.payload_size_bytes),
```

`projection_descriptor.payload_ref`、`payload_digest`、`payload_size_bytes` 都是
Step 1 同一 descriptor 的字段。没有通过 `prepared_input` 再绕一层。

**Step 3** — manifest body 中写入（line 1801-1803）：

```python
"runner_call_projection_artifact_ref": compactor_input_projection_ref,
"runner_call_projection_artifact_digest": (compactor_input_projection_digest),
"runner_call_projection_artifact_size_bytes": (compactor_input_projection_size_bytes),
```

**Step 4** — hot payload 从 manifest JSON 读取同源值（line 1870-1880）：

```python
runner_call_projection_artifact_ref=_required_manifest_text(manifest, "runner_call_projection_artifact_ref"),
runner_call_projection_artifact_digest=_required_manifest_text(manifest, "runner_call_projection_artifact_digest"),
runner_call_projection_artifact_size_bytes=_required_manifest_int(manifest, "runner_call_projection_artifact_size_bytes"),
```

**Step 5** — formal resolver 重新验证：

`resolve_runner_call_projection_from_signal` → `read_tool_trace_json_payload` →
`resolve_json_payload`（`durable/payload_resolution.py:45-83`）。该函数校验：

1. descriptor ref 等于调用方请求 ref（line 101-102）
2. descriptor digest 等于调用方预期 digest（line 103-105）
3. SQLite row payload_id、format、digest、size 与 descriptor 完全一致（line 168-195）
4. 实际 payload bytes digest 等于 descriptor digest（line 244-247）
5. 实际 payload bytes size 等于 descriptor size（line 244-245）
6. 实际 bytes 是 canonical JSON object（line 250-277）

所有 values 从同一个 `projection_descriptor` 对象派生，经 `write_bounded_json_payload`
digest 验证写入，再经 `resolve_json_payload` 全链路 digest 验证读回。无分裂可能。

### Verdict：CLAIM FALSIFIED

全链路同源：`prepared_input.compactor_input_projection_digest` → `write_bounded_json_payload`
expected_digest 验证 → descriptor row → manifest body → hot atoms → formal resolver →
`resolve_json_payload` 逐字节 re-verify。不存在"manifest 用一个 digest、descriptor 用
另一个"的分裂点。

---

## Adversarial check 4：response identity 与 attempt mapping 是否被 tests 准确关联

### Claim to falsify

"`_resolve_and_assert_compactor_calls` 中 response identity 到 prepared input 的映射
可能因 `zip` 错位或 `_events_for_run_by_type` 的 event_id 冲突而出错。"

### Evidence

**Mapping 正确性**（`test_dispatch_scheduler.py:11639-11726`）：

1. `catch_up_tool_trace_projection` 把 EventLog 中的 compactor `RUNNER_CALL_INPUT_ASSEMBLED`
   events 投影到 Tool Trace hot table（`tool_trace.py:215,607` 确认该 event type 在白名单中）。

2. `read_runner_call_reconstruction_signals_by_run` 从 Tool Trace hot table 按 run_id
   筛选 compactor signals（`durable/tool_trace.py:880-910`）。

3. `_events_for_run_by_type` 从 EventLog 直接读源 events（`test_dispatch_scheduler.py:11482-11503`）。
   EventLog row 与 Tool Trace hot row 的 `event_id` 相同（Tool Trace projector 保留源
   `event_id`），故 `source_events[signal.event_id]` 可精确映射。

4. `zip(prepared_inputs, attempt_payloads, resolved_calls, strict=True)` + `enumerate(start=1)`
   保证按 attempt 序号一一对应，无错位可能。

5. 每条断言（line 11709-11723）验证：
   - `source_event.payload_ref == signal.manifest_ref`（EventLog row descriptor ref 与 Tool Trace signal 一致）
   - `source_event.payload_digest == signal.manifest_digest`
   - `hot_payload["manifest_payload_ref"] == signal.manifest_ref`
   - `resolved.manifest.payload_ref == signal.manifest_ref`
   - `resolved.manifest.payload_digest == signal.manifest_digest`
   - `compactor_identity["compaction_attempt_number"] == attempt_number`
   - `compactor_identity["compactor_engine_run_id"] == prepared_input.compactor_engine_run_id`
   - `compactor_identity["compaction_operation_id"] == attempt_payload["operation_id"]`
   - `resolved.runner_input_projection.payload_ref == compactor_identity["compactor_input_projection_ref"]`
   - `hot_payload["runner_call_projection_artifact_ref"] == resolved.runner_input_projection.payload_ref`
   - `hot_payload["runner_call_projection_artifact_digest"] == resolved.runner_input_projection.payload_digest`
   - `resolved.runner_input_projection.payload_digest == prepared_input.compactor_input_projection_digest`
   - `resolved.runner_input_projection.payload == prepared_input.compactor_input_projection`
   - `response_identity["effective_provider"] == prepared_input.agent_request.runner_spec.provider`
   - `response_identity["effective_model"] == prepared_input.agent_request.runner_spec.model`
   - `runner_request_identity["run_id"] == prepared_input.compactor_engine_run_id`

6. `_successful_response_identity_for_agent_request`（line 323-346）从
   `request.runner_spec.provider`、`request.runner_spec.model`、`request.run_id` 构造
   `SuccessfulRunnerResponseIdentity`。compactor 的 `_PreparedManifestProactiveCompactor`
   在 `run_prepared_compactor_proposal` 中调用此函数（line 797-799），因此 response
   identity 与 `prepared_input.agent_request` 完全同源。

### Verdict：CLAIM FALSIFIED

response identity 通过完整的 public Tool Trace resolver 链路反向映射到
`prepared_input.agent_request.runner_spec` 与 `compactor_engine_run_id`。`strict=True`
zip 保证按 attempt 序号严格对齐。EventLog → Tool Trace → signal → resolved projection
四层 identity 均做交叉断言。

---

## Adversarial check 5：invalid/repair/fallback 是否真正覆盖所有 call（非用 prepared_inputs 数量掩盖）

### Claim to falsify

"`_AlwaysQualityRejectingCompactor` 可能在某些 attempt 中不通过 `prepared_inputs` 记录，
导致 `_resolve_and_assert_compactor_calls` 的 `len(prepared_inputs) == len(attempt_payloads)`
断言掩盖缺失 coverage。"

### Evidence

**Coverage matrix**：

| Test | Compactor | Attempts | accepted_attempt_number | 覆盖路径 |
|------|-----------|----------|------------------------|---------|
| `test_proactive_compaction_retries_quality_rejection_before_accept` | `_QualityRejectOnceCompactor` | 2 | 2 | quality reject → repair → accept |
| `test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback` | `_AlwaysQualityRejectingCompactor` | 3-4 | `None` | all fail → dispatch fallback |
| `test_multi_turn_proactive_compact_feeds_subsequent_run_input` | `_PreparedManifestProactiveCompactor` | 1 | 1 | single accept |

**`_PreparedManifestProactiveCompactor` 记录机制**（line 707-773）：

- `prepare_compactor_proposal_run_input` 是 Host governance 在每次 proposal attempt
  前调用的方法（由 `compaction_operation.py` 的 attempt loop 驱动）。
- 每次调用都把 `prepared_input` append 到 `self.prepared_inputs`（line 772）。
- `run_prepared_compactor_proposal` 在执行后调用 `super().run_prepared_compactor_proposal`。
- 两个子类 `_QualityRejectOnceCompactor` 和 `_AlwaysQualityRejectingCompactor` 在
  `run_prepared_compactor_proposal` 中调用 `super()`，确保基类逻辑执行。

**attempt_payloads 来源验证**：

在三个测试中，`attempt_payloads` 从 EventLog 事件派生：

1. 单 success / repair 测试：`rejected_payload` + `compacted_payload`，从
   `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 和 `CONTEXT_COMPACTED` EventLog rows 读取。

2. 全失败测试：`rejected_payloads` 从 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` events
   读取，每个 rejected attempt 有一条 EventLog row。

3. 每条 `attempt_payload` 都包含 `attempt_number` 或 `accepted_attempt_number` 字段，
   且与 `_required_json_int(attempt_payload[attempt_field]) == attempt_number` 交叉验证。

**`_AlwaysQualityRejectingCompactor` 设计**（line 1034-1061）：

- 继承 `_PreparedManifestProactiveCompactor`，因此 `prepare_compactor_proposal_run_input`
  同样被调用，`prepared_inputs` 同样被记录。
- `run_prepared_compactor_proposal` 调用 `super()` 获取成功 proposal（含 valid
  `successful_response_identity`），再叠加 `invalid-current-anchor` diagnostic。
- 每个 attempt 都有 `successful_response_identity`，不会出现 `proposal_failed`（无
  response identity）的场景。

**反例检查**：旧测试用 `_RecoveryScenarioCompactor(accept_call=99)` 使 proposal
execution 抛 `RuntimeError`，此时 `failure_category == "proposal_failed"` 且无
`successful_response_identity`。新测试改用 `_AlwaysQualityRejectingCompactor` 确保每个
attempt 都有 valid response identity → `failure_category == "quality_check_rejected"`。
因此新 helper 的 response identity 断言对每个 attempt 都有意义，无"用 prepared_inputs
数量掩盖"的问题。

### Verdict：CLAIM FALSIFIED

三个测试路径覆盖了单次接受、repair 循环、全失败 fallback。`_AlwaysQualityRejectingCompactor`
的每次 call 都经过 `prepare_compactor_proposal_run_input` → `prepared_inputs.append` →
`run_prepared_compactor_proposal` → `super()` 的完整记录链。

---

## Adversarial check 6：private SQLite 是否仍是通过条件

### Claim to falsify

"测试中仍可能通过 `sqlite_payload_object` 间接读取私有 SQLite payload table。"

### Evidence

**旧代码**（`test_multi_turn_proactive_compact_feeds_subsequent_run_input`，已被替换）：

```python
from dayu.host.payload_resolution import sqlite_payload_object

manifest_json = store.transaction_runner.run_read(
    lambda transaction: sqlite_payload_object(
        transaction,
        payload_ref=hot.manifest_payload_ref,
        payload_digest=hot.manifest_digest,
        payload_label="proactive post-compact manifest",
    )
)
manifest = parse_runner_call_manifest(manifest_json, hot_payload=hot)
```

**新代码**：

```python
from dayu.host.durable.tool_trace import (
    read_runner_call_reconstruction_signals_by_run,
    resolve_runner_call_projection_from_signal,
)
from dayu.host.tool_trace import (
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)

runner_call_page = store.transaction_runner.run_read(
    lambda transaction: read_runner_call_reconstruction_signals_by_run(
        transaction, compacted.run_id, after_event_sequence=0, limit=100,
    )
)
ordinary_call = store.transaction_runner.run_read(
    lambda transaction: resolve_runner_call_projection_from_signal(
        transaction, ordinary_signals[0],
    )
)
```

**导入变更**：diff 移除 `parse_runner_call_hot_payload`、`parse_runner_call_manifest`、
`sqlite_payload_object` 三个 imports，新增 `read_runner_call_reconstruction_signals_by_run`、
`resolve_runner_call_projection_from_signal`、`ToolTraceSinkOptions`、
`catch_up_tool_trace_projection`。

**`sqlite_payload_object` 定义**（`payload_resolution.py:162-189`）：内部调用
`resolve_json_payload`，而 `resolve_json_payload` 是 `durable/payload_resolution.py`
的公共函数。但 `sqlite_payload_object` 本身是 Host 层私有便利函数，不应由测试直接使用。

新的 `read_runner_call_reconstruction_signals_by_run` 和
`resolve_runner_call_projection_from_signal` 是 `durable/tool_trace.py` 的公共 API
（在 `__all__` 中导出），是 Tool Trace formal contract 的一部分。

### Verdict：CLAIM FALSIFIED

所有测试路径均通过 public `read_runner_call_reconstruction_signals_by_run` →
`resolve_runner_call_projection_from_signal` 链路。`sqlite_payload_object` 导入已被
移除。测试不再通过任何私有 SQLite 路径。

---

## Adversarial check 7：mismatch 严格失败

### Claim to falsify

"EventLog row descriptor 与 hot manifest identity 不一致时，Tool Trace 查询可能静默
跳过或返回空结果而非 fail closed。"

### Evidence

**Mismatch 测试**（`test_tool_trace_queries.py:1848-1915`，
`test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch`）：

1. 写入 manifest JSON（`payload_ref="payload-manifest-row-hot-mismatch"`）。
2. 构造 hot payload（`manifest_payload_ref=manifest_ref`，即
   `"payload-manifest-row-hot-mismatch"`）。
3. Append EventLog row 时使用 `payload_ref="payload-row-descriptor-mismatch"`
   （**故意不同**）、`payload_digest=manifest_digest`（与 manifest digest 相同）。
4. Catch up Tool Trace projection。
5. 调用 `read_runner_call_reconstruction_signals_by_run`。
6. 断言 `pytest.raises(HostDurableError, match="tool trace row and runner-call hot identity mismatch")`。

**Fail-closed 机制**（`durable/tool_trace.py:1036-1059`，
`_validated_runner_call_contract`）：

```python
hot_payload = parse_runner_call_hot_payload(
    _read_event_payload(transaction, row.event_id)
)
if (
    row.session_id != hot_payload.session_id
    or row.run_id != hot_payload.host_run_id
    or row.attempt_id != hot_payload.attempt_id
    or row.execution_id != hot_payload.execution_id
    or row.payload_ref != hot_payload.manifest_payload_ref   # ← 严格相等
    or row.payload_digest != hot_payload.manifest_digest      # ← 严格相等
):
    raise HostDurableError("tool trace row and runner-call hot identity mismatch")
```

测试中 `row.payload_ref`（`"payload-row-descriptor-mismatch"`）≠
`hot_payload.manifest_payload_ref`（`"payload-manifest-row-hot-mismatch"`），精确触发
此错误。

**注意**：EventLog source payload（`_read_event_payload` → `TABLE_EVENT_LOG.payload_json`）
本身不比较 `payload_ref` 与 `payload_json` 内部 `manifest_payload_ref` 的一致性。这是
设计选择：EventLog row 的 `payload_ref` 是 durable 事实，hot payload 中的
`manifest_payload_ref` 是业务语义字段。Tool Trace 在 consumption 时做 identity check，
而非在 EventLog write 时。**这不是 bug**——EventLog row descriptor 和 hot payload 语义
字段由不同 owner 控制，Tool Trace 作为 consumer 做 fail-closed cross-verification 是
正确做法。

### Verdict：CLAIM FALSIFIED

mismatch 严格触发 `HostDurableError`，不静默跳过，不返回空结果。

---

## Adversarial check 8：大规模 test 变更/formatting 是否存在 scope 污染或错误 helper

### Claim to falsify

"新增的 `_required_json_int`/`_required_json_text`/`_required_json_mapping` helpers
可能存在类型错误、Ruff 改行或未使用的 dead code。"

### Evidence

**Helper 正确性**（`test_dispatch_scheduler.py:12121-12156`）：

`_required_json_int`（line 12146-12156）：
```python
def _required_json_int(value: JsonValue) -> int:
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value
```
Python `bool` 是 `int` 子类 → `isinstance(True, int)` 为 `True`。第二个 assert 正确
排除 `True`/`False`。helper 被三处测试中的 `_required_json_int(attempt_payload[attempt_field])`
调用（line 11713），`attempt_field` 是 `accepted_attempt_number` 或 `attempt_number`，
均为正整数。

`_required_json_text`（line 12133-12143）：
```python
def _required_json_text(value: JsonValue) -> str:
    assert isinstance(value, str)
    assert value != ""
    return value
```
正确拒绝空字符串。在 helper 中被多处使用。

`_required_json_mapping`（line 12121-12130）：
```python
def _required_json_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)
```
`str` 不是 `Mapping`（Python 3 中 `str` 是 `Sequence` 非 `Mapping`）。正确拒绝字符串。

**Scope 污染检查**：

diff 中所有 removal 都是精确 import 移除（`parse_runner_call_hot_payload`、
`parse_runner_call_manifest`、`sqlite_payload_object`），所有 addition 都是功能必需的
新 import 和 helper 定义。无 whitespace-only 变更、无 reformatting、无 dead code。

`_AlwaysQualityRejectingCompactor` 使用 `dataclasses.replace`，该函数已在文件头
line 9 导入：`from dataclasses import dataclass, replace`。无新增 import。

新增测试常量（line 314-320）全部在 `_resolve_and_assert_compactor_calls` 中被引用。

新增 docstring（三个测试函数）格式一致，参数/返回/异常声明完整。

### Verdict：CLAIM FALSIFIED

无 dead code、无 Ruff/formatting 扩散、无 scope 污染、无类型错误。helper 函数正确区分
`bool`/`int`、`str`/非空、`Mapping`/非 Mapping。

---

## 附加发现

### 发现 9（low severity）：`_required_json_int` 不校验值域

`_required_json_int` 只校验类型（`int` 非 `bool`），不校验非负/正整数。所有调用点
（`attempt_payload[attempt_field]`）的语义是 attempt number（正整数），但该 helper 不会
捕获意外负值。当前测试 fixture 全部产生正 attempt number，因此不会误报。若未来 test
fixture 产生非法 attempt number，helper 会静默通过，需由调用点的 `assert ... == attempt_number`
间接捕获。

**建议**：非阻塞。当前 tests 无风险。若 helper 被复用，建议在调用点增加显式正值断言。

### 发现 10（informational）：`_AlwaysQualityRejectingCompactor` 的 diagnostic code 非 enum

`CompactCandidateDiagnosticV2.code` 字段是 `str`（非 enum），`"invalid-current-anchor"`
是可接受的任意非空字符串。该值不在 `CompactValidationIssueCodeV2` enum 中，但
`CompactCandidateDiagnosticV2` 与 `CompactValidationIssueCodeV2` 是不同的类型层级——
前者是 candidate-level diagnostic，后者是 parser-level issue code。两者无耦合关系。

**建议**：非阻塞。未来可考虑统一 diagnostic code 命名空间，但不在本 slice scope 内。

### 发现 11（verified）：catch_up 在 `_resolve_and_assert_compactor_calls` 中的幂等性

`catch_up_tool_trace_projection`（`tool_trace.py:521-573`）通过 `ProjectionRunner.run_once`
逐批处理，内部读取 projection checkpoint 并只消费新 events。多次调用安全幂等。helper
在每个 test 调用点独立执行 catch_up，不会受前序 test 影响。

---

## Adversarial failure pass 总结

针对每个 claim 进行了至少一轮 adversarial 证伪尝试：

| # | Claim | Attempted falsification | Result |
|---|-------|------------------------|--------|
| 1 | row descriptor 修复后 resolver 不需 projection 字段 | 追踪 resolver JSON 层读取路径 | FALSIFIED — resolver 读 raw JSON，不走 typed optional |
| 2 | 新字段是 schema 扩张 | 比对 frozen field sets 与 typed contract | FALSIFIED — 字段已在 contract 中为 Optional |
| 3 | projection digest 与 descriptor 可能分裂 | 追踪 descriptor → manifest → hot → resolver 全值链 | FALSIFIED — 全部从同一 `projection_descriptor` 派生 |
| 4 | response identity 映射可能错位 | 验证 zip strict + enumerate + 交叉断言 | FALSIFIED — 四层 identity 交叉验证 |
| 5 | `prepared_inputs` 数量掩盖未覆盖 attempt | 检查 `_AlwaysQualityRejectingCompactor` 的完整 call chain | FALSIFIED — prepare/run 均被调用且记录 |
| 6 | 测试仍走 private SQLite | 检查 import 变更与调用链 | FALSIFIED — `sqlite_payload_object` 导入已移除 |
| 7 | mismatch 静默忽略 | 执行 negative test + 读 fail-closed 代码路径 | FALSIFIED — `HostDurableError` 精确抛出 |
| 8 | scope 污染/错误 helper | 逐行 diff 检查 + helper type safety 验证 | FALSIFIED — 无污染、无类型错误 |

## 结论：PASS

全部 8 项 adversarial checks 均被证伪。F09 slice 的 production change 正确修复了
compactor proposal manifest recorder 的 EventLog row descriptor identity 与 manifest
projection descriptor 字段。所有新增字段填充已有 typed contract Optional slot，不构成
schema 扩张。projection descriptor 到 formal resolver 的全链路 digest/size/ref 逐字节
同源。测试通过 public Tool Trace formal contract 覆盖 single success、repair cycle、
全失败 fallback 三条路径，且严格验证 mismatch fail closed。无 scope 污染、无 private
SQLite 残余路径、无 dead code。

无 blocking finding。无 NEEDS_FIX。
