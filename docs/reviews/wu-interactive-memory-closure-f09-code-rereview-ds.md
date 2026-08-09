# Interactive Conversation Memory closure F09：DS 第二路独立 code re-review

## Gate identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Gate：DS 第二路独立 code re-review（不依赖 MiMo，不读取 MiMo review 证据）。
- Reviewed artifact：`codex/interactive-oracle` branch 上 F09 未提交 diff（基于 F08 checkpoint `47b6a2af`）。
- Prior DS review：`docs/reviews/wu-interactive-memory-closure-f09-code-review-ds.md`（结论 `PASS`，8 项 adversarial checks 全部证伪，3 项附加发现）。
- Fix artifact：`docs/reviews/wu-interactive-memory-closure-f09-code-review-fix-codex.md`（结论 `fix-pass`，no-op，accepted findings = 0）。
- Implementation artifact：`docs/reviews/wu-interactive-memory-closure-f09-implementation-codex.md`。
- Accepted plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
- Artifact path：`docs/reviews/wu-interactive-memory-closure-f09-code-rereview-ds.md`。
- Re-review 时间：2026-08-04。

## 输入完整性

本 re-review 的输入仅包括：

| Durable input | 来源 |
|---|---|
| F09 完整 diff（三文件，544 行） | `git diff 47b6a2af -- dayu/host/compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_tool_trace_queries.py` |
| 原始 DS review | `docs/reviews/wu-interactive-memory-closure-f09-code-review-ds.md` |
| Fix artifact | `docs/reviews/wu-interactive-memory-closure-f09-code-review-fix-codex.md` |
| Contract owner 文件（只读） | `dayu/host/_runner_call_manifest.py`、`dayu/host/durable/tool_trace.py` |
| Frozen baseline | `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/reviews/wu-interactive-memory-closure-f08-f10.md`、`workspace/tmp/interactive-memory-observed-behavior.md`、`workspace/tmp/interactive-memory-report-freeze.json` |

本 re-review **未读取** MiMo review（`wu-interactive-memory-closure-f09-code-review-mimo.md`），以保证第二路完全独立。

## 独立复核方法

对原始 DS review 的每个 adversarial check 执行以下独立复核步骤：

1. 从 F09 diff 中直接读取相关代码片段。
2. 从 contract owner 文件中独立读取被引用的类型定义、不变量和 fail-closed 路径。
3. 不依赖原始 review 的结论——仅基于直接读取的代码证据判断 claim 是否成立。
4. 对 DS low/info findings 执行独立的"是否构成修复"裁决。
5. 独立验证 no-op fix gate 后代码指纹未变、tests 仍通过、baseline 未变。

---

## 独立复核：8 项 adversarial checks

### AC1：row descriptor 修复后 formal resolver 是否仍需 manifest projection artifact 字段

**独立证据**：

读取 `dayu/host/durable/tool_trace.py:385-396`：

```python
projection_ref = _json_optional_text(
    manifest.payload,
    _RUNNER_CALL_PROJECTION_ARTIFACT_REF,
)
...
if projection_ref is None:
    raise HostDurableError("runner-call manifest has no projection artifact ref")
```

`_json_optional_text` 从 `manifest.payload`（raw JSON dict）读取字段，不经过 `RunnerCallInputManifest.projection_descriptor` 的 typed contract optional 通路。若 manifest JSON 不含 `runner_call_projection_artifact_ref`，返回 `None`，立即 fail closed。

**独立判定**：CLAIM FALSIFIED。Formal resolver 在 JSON 层独立 fail closed，不依赖 typed contract optionality。producer 必须在 manifest JSON 中显式填充此三字段。

---

### AC2：新增字段是否 schema 扩张

**独立证据**（全部从 `dayu/host/_runner_call_manifest.py` 直接读取）：

1. `_RUNNER_CALL_HOT_FIELDS`（line 44-46）已包含三字段。F09 diff 未修改此 frozen set。
2. `RunnerCallHotAtoms`（line 366-368）已声明三字段为 `str | None` / `int | None`。F09 diff 未修改此 dataclass。
3. `_RUNNER_CALL_MANIFEST_PROJECTION_FIELDS`（line 93-99）已定义完全相同三字段。F09 diff 未修改。
4. `_validate_manifest_fields`（line 1016-1025）已处理 projection 字段全有/全无规则：`projection_field_count in (0, len(_RUNNER_CALL_MANIFEST_PROJECTION_FIELDS))`。F09 diff 未修改。
5. `parse_runner_call_hot_payload`（line 707-718）已按 `_optional_text` / `_optional_digest` / `_optional_non_negative_int` 解析三字段。F09 diff 未修改。
6. `_validate_hot_atoms`（line 1750-1757）已有 ref/digest/size 三元组配对不变量。F09 diff 未修改。
7. `_validate_manifest_hot_identity`（line 1629-1647）已将 projection triplet 纳入 16-tuple identity comparison。F09 diff 未修改。
8. `_parse_manifest_projection_descriptor`（line 1086-1124）已处理全有/全无/partial 规则。

F09 唯一做的事：在 `compaction_operation.py` 的 producer 侧将三字段从 `None` 改为从同一 transaction 已写入 `projection_descriptor` 派生的实际值。

**独立判定**：CLAIM FALSIFIED。无 schema 扩张、无 field set 修改、无 contract 弱化。所有 typed contract 定义在 F09 前已存在且为 Optional。

---

### AC3：projection digest/size/ref 是否与 descriptor 逐字节同源

**独立证据**（从 F09 diff 直接追踪值链）：

1. **写入端**（`compaction_operation.py:256-275`）：`write_bounded_json_payload` 校验 `expected_digest == prepared_input.compactor_input_projection_digest`，失败拒写。返回的 `projection_descriptor` 的 `payload_digest` 等于 `expected_digest`。
2. **manifest body 取值**（line 282-284）：`compactor_input_projection_ref=projection_descriptor.payload_ref`、`compactor_input_projection_digest=projection_descriptor.payload_digest`、`compactor_input_projection_size_bytes=projection_descriptor.payload_size_bytes`。全部从同一个 `projection_descriptor` 对象取，不经 `prepared_input` 绕路。
3. **manifest JSON 写入**（line 1801-1803）：三个字段直接写入 manifest dict。
4. **hot payload 读取**（line 1870-1881）：`_required_manifest_text(manifest, "runner_call_projection_artifact_ref")` 等从同一 manifest JSON 读取。
5. **读取端验证**：`resolve_runner_call_projection_from_signal` → `read_tool_trace_json_payload` → `resolve_json_payload`（`durable/payload_resolution.py:45-83`），校验 descriptor ref/digest 匹配、SQLite row 与 descriptor 一致、实际 bytes digest 等于 descriptor digest。

**独立判定**：CLAIM FALSIFIED。全链路单源：`prepared_input.compactor_input_projection_digest` → `write_bounded_json_payload` expected_digest 校验 → descriptor row → manifest body → hot atoms → formal resolver → `resolve_json_payload` 逐字节 re-verify。无分裂点。

---

### AC4：response identity 与 attempt mapping 是否被 tests 准确关联

**独立证据**（从 F09 diff 的 `_resolve_and_assert_compactor_calls` 直接读取）：

1. `catch_up_tool_trace_projection` 投影 `RUNNER_CALL_INPUT_ASSEMBLED` events 到 Tool Trace hot table。
2. `read_runner_call_reconstruction_signals_by_run` 按 `run_id` 筛选 compactor signals。
3. `source_events` dict 以 `event_id` 为 key，从 EventLog 直接读源 rows。Tool Trace projector 保留源 `event_id`，故 `source_events[signal.event_id]` 精确映射。
4. `zip(prepared_inputs, attempt_payloads, resolved_calls, strict=True)` + `enumerate(start=1)` 保证按 attempt 序号一一对应。
5. 每条断言验证 EventLog row → signal → resolved manifest → projection → compactor identity → response identity 的交叉一致性。

**独立判定**：CLAIM FALSIFIED。四层 identity（EventLog row、Tool Trace signal、resolved manifest、projection payload）经 `strict=True` zip 对齐，逐项交叉断言。

---

### AC5：prepared_inputs 数量是否掩盖未覆盖 attempt

**独立证据**（从 F09 diff 直接读取）：

三个测试路径：
| Test | Compactor | Attempts | accepted_attempt_number |
|---|---|---|---|
| `test_multi_turn_proactive_compact_feeds_subsequent_run_input` | `_PreparedManifestProactiveCompactor` | 1 | 1 |
| `test_proactive_compaction_retries_quality_rejection_before_accept` | `_QualityRejectOnceCompactor` | 2 | 2 |
| `test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback` | `_AlwaysQualityRejectingCompactor` | 3-4 | None |

`_PreparedManifestProactiveCompactor.prepare_compactor_proposal_run_input`（line 772）每次调用 append 到 `self.prepared_inputs`。子类 `_AlwaysQualityRejectingCompactor` 调用 `super().run_prepared_compactor_proposal(prepared_input)`，基类逻辑完整执行。

`attempt_payloads` 从 canonical EventLog events（`CONTEXT_COMPACTION_ATTEMPT_REJECTED` / `CONTEXT_COMPACTED`）派生，每个 attempt 有一条 EventLog row。`_resolve_and_assert_compactor_calls` 第一行 `assert len(prepared_inputs) == len(attempt_payloads)` 确保数量一致。

旧测试用的 `_RecoveryScenarioCompactor(accept_call=99)` 抛 `RuntimeError` → `failure_category == "proposal_failed"`，无 `successful_response_identity`。新 `_AlwaysQualityRejectingCompactor` 确保每个 attempt 有 valid response identity → `failure_category == "quality_check_rejected"`。因此 helper 的 response identity 断言对每条 attempt 都有意义。

**独立判定**：CLAIM FALSIFIED。三条路径覆盖单次接受、repair 循环、全失败 fallback。prepared_inputs、attempt_payloads、signals、resolved_calls 四者数量经 `strict=True` zip 和显式 assert 交叉验证。

---

### AC6：private SQLite 是否仍是通过条件

**独立证据**（从 F09 diff import 变更直接读取）：

移除的 imports：
```python
from dayu.host._runner_call_manifest import (
    parse_runner_call_hot_payload,    # 移除
    parse_runner_call_manifest,       # 移除
)
from dayu.host.payload_resolution import sqlite_payload_object  # 移除
```

新增的 imports：
```python
from dayu.host.durable.tool_trace import (
    read_runner_call_reconstruction_signals_by_run,
    resolve_runner_call_projection_from_signal,
)
from dayu.host.tool_trace import (
    ToolTraceSinkOptions,
    catch_up_tool_trace_projection,
)
```

所有新增调用路径均为 public Tool Trace formal contract API（`durable/tool_trace.py` 的 `__all__` 导出）。`sqlite_payload_object`（`payload_resolution.py:162-189`）是 Host 层私有便利函数，已被完全移除。

**独立判定**：CLAIM FALSIFIED。测试不再通过任何私有 SQLite 路径。全部使用 public `read_runner_call_reconstruction_signals_by_run` → `resolve_runner_call_projection_from_signal` 链路。

---

### AC7：mismatch 严格失败

**独立证据**（从 F09 diff 和 contract owner 直接读取）：

F09 diff 新增 `test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch`（`test_tool_trace_queries.py:1848-1915`）：

1. 写入 manifest JSON（`payload_ref="payload-manifest-row-hot-mismatch"`）。
2. 构造 hot payload（`manifest_payload_ref` 同上）。
3. EventLog row 使用 `payload_ref="payload-row-descriptor-mismatch"`（故意不同）。
4. Catch up Tool Trace projection。
5. 调用 `read_runner_call_reconstruction_signals_by_run`。
6. 断言 `pytest.raises(HostDurableError, match="tool trace row and runner-call hot identity mismatch")`。

Fail-closed 机制位于 `durable/tool_trace.py:1036-1047`（`_validated_runner_call_contract`）：

```python
if (
    row.session_id != hot_payload.session_id
    or row.run_id != hot_payload.host_run_id
    ...
    or row.payload_ref != hot_payload.manifest_payload_ref   # ← 严格相等
    or row.payload_digest != hot_payload.manifest_digest      # ← 严格相等
):
    raise HostDurableError("tool trace row and runner-call hot identity mismatch")
```

F09 diff 未修改此函数。

**独立判定**：CLAIM FALSIFIED。mismatch 严格触发 `HostDurableError`，不静默跳过，不返回空结果。F09 未修改 fail-closed 逻辑。

---

### AC8：大规模 test 变更/formatting 是否存在 scope 污染或错误 helper

**独立证据**（从 F09 diff 逐段检查）：

**Helper 正确性**：

`_required_json_int`：
```python
assert isinstance(value, int)
assert not isinstance(value, bool)
```
Python `bool` 是 `int` 子类，第二个 assert 正确排除 `True`/`False`。所有调用点 `attempt_payload[attempt_field]` 语义为正整数。

`_required_json_text`：
```python
assert isinstance(value, str)
assert value != ""
```
正确拒绝空字符串。

`_required_json_mapping`：
```python
assert isinstance(value, Mapping)
```
Python 3 中 `str` 不是 `Mapping`，正确拒绝字符串。

**Scope 污染检查**：

F09 diff 中所有 removal 为精确 import 移除（`parse_runner_call_hot_payload`、`parse_runner_call_manifest`、`sqlite_payload_object`），所有 addition 为功能必需的新 import 和 helper 定义。无 whitespace-only 变更、无 reformatting、无 dead code。

`_AlwaysQualityRejectingCompactor` 使用 `dataclasses.replace`，已在文件头 line 9 导入。无新增 import。

新增测试常量 `_COMPACTOR_RUNNER_CALL_KIND` 等全部在 `_resolve_and_assert_compactor_calls` 中被引用。

**独立判定**：CLAIM FALSIFIED。无 dead code、无 formatting 扩散、无 scope 污染、无类型错误。

---

## 独立复核：DS low/info findings 为何不构成修复

### Finding 9（low）：`_required_json_int` 不校验值域

**独立裁决**：`rejected-with-reason`。不构成修复。

直接证据：
- `_required_json_int` 的语义 owner 是 JSON type coercion（`JsonValue → int` 且排除 `bool`），不是 attempt-number 值域校验。
- 当前仅有两个调用点，均立即执行 `assert _required_json_int(attempt_payload[attempt_field]) == attempt_number`。`attempt_number` 来自 `enumerate(..., start=1)`，必定为正整数。
- 负值、0 或错序值均在同一 `== attempt_number` 断言中失败。不存在"helper 静默通过且测试也通过"的反例。
- 若在 helper 中硬编码正值校验，会把 attempt-number 语义耦合进通用 JSON type helper，且对未来允许 0 或负数的 JSON integer 字段产生错误耦合。

**结论**：无真实漏测。不修改。

### Finding 10（informational）：diagnostic code 非 enum

**独立裁决**：`rejected-with-reason`。不构成修复。

直接证据：
- `CompactCandidateDiagnosticV2.code` 的当前契约是任意非空 `str`。
- `CompactValidationIssueCodeV2` 是 parser-level issue code enum，属于不同语义 owner。
- 把 `"invalid-current-anchor"` 强行纳入无关 enum 或在本 slice 统一 diagnostic namespace，均造成 contract/schema 扩张与 goal drift。

**结论**：非 F09 finding。不修改。

### Finding 11（verified）：catch_up 幂等性

**独立裁决**：positive confirmation。无需修复。

直接证据：
- `catch_up_tool_trace_projection`（`tool_trace.py:521-573`）通过 `ProjectionRunner.run_once` 逐批处理，内部读取 projection checkpoint 并只消费新 events。
- `_resolve_and_assert_compactor_calls` 在每个独立 test store 中调用 catch_up，checkpoint 机制保证不重复消费。

**结论**：无问题。无需修复。

---

## 独立复核：no-op fix gate 后代码指纹

### Diff 指纹

```bash
$ git diff 47b6a2af -- dayu/host/compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_tool_trace_queries.py | shasum -a 256
cc49580c26c8fea3b8fb64532727056d435e0123c3e72a7e13ed05d4d9f926cd  -
```

与 fix artifact（`wu-interactive-memory-closure-f09-code-review-fix-codex.md` line 142）记录的指纹完全一致。no-op gate 后三文件未发生任何修改。

### 测试

```bash
$ pytest -q \
  tests/host/test_dispatch_scheduler.py::test_multi_turn_proactive_compact_feeds_subsequent_run_input \
  tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept \
  tests/host/test_dispatch_scheduler.py::test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback \
  tests/host/test_tool_trace_queries.py::test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch
4 passed in 0.48s
```

### Pyright

```bash
$ python -m pyright dayu/host/compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_tool_trace_queries.py
0 errors, 0 warnings, 0 informations
```

### Frozen baseline

| 文件 | Accepted digest | 本 re-review 重算 | 匹配 |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `da049231...` | `da049231...` | ✓ |
| `docs/cli_ci_scenarios.json` | `7c991d14...` | `7c991d14...` | ✓ |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543...` | `95a09543...` | ✓ |
| `workspace/tmp/interactive-memory-observed-behavior.md` | `ad643151...` | `ad643151...` | ✓ |
| `workspace/tmp/interactive-memory-report-freeze.json` | `7ba64926...` | `7ba64926...` | ✓ |

全部五个 frozen baseline SHA-256 未改变。

---

## 结论：PASS

本独立 re-review 对原始 DS review 的全部 8 项 adversarial checks 逐一执行了独立复核——仅基于 F09 diff 的直接代码证据和 contract owner 文件的独立读取，未依赖原始 review 结论或 MiMo review。全部 8 项 claims 仍被独立证伪。

DS low/info findings（#9、#10、#11）经独立裁决均不构成修复：#9 和 #10 为 `rejected-with-reason`，#11 为 positive confirmation。

No-op fix gate 后代码指纹未变（`cc49580c...`）、4 条 focused tests 全部通过、pyright 零错误、5 个 frozen baseline digest 全部匹配。

无 blocking finding。无 NEEDS_FIX。
