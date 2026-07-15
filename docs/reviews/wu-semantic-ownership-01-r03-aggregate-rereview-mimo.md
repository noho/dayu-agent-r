# WU-SEMANTIC-OWNERSHIP-01 / R03 aggregate re-review（AgentMiMo）

## Scope

- Mode: current changes（working tree，含已验证 F01-F03 fixes + zero-change fix record + Controller validation）
- Branch: `phaseflow/host-issues-control`
- Base: `8c6ae966`（R03 accepted plan commit）
- Baseline range: `8c6ae966..HEAD + working tree`
- Output file: `docs/reviews/wu-semantic-ownership-01-r03-aggregate-rereview-mimo.md`
- Included scope: S1=`3e48f09e`、S2=`4b4696e5`、S3=`3f777753` + working tree F01-F03 fixes + zero-change fix record + Controller validation + Controller-authorized control gate diff
- Excluded scope: credential/raw config、design truth（非代码输入）、Issue #177/#178 实现
- Parallel review coverage: 无（单 reviewer 完整独立复核）

## 真源文档确认

已完整读取并以之为真源：
- `AGENTS.md`（CLAUDE.md）
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（controller discussion）
- `docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`（design truth）
- `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`（accepted plan）
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-mimo.md`（初轮 MiMo deepreview）
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-ds.md`（初轮 DS deepreview）
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-controller-adjudication.md`（Controller adjudication）
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-codex.md`（zero-change fix record）
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-controller-validation.md`（Controller validation）
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-controller-validation.md`（aggregate Controller validation，含 F01-F03）

裁决优先级：controller discussion > design truth > accepted plan > 直接代码/数据证据。

## Final Verdict

**PASS。**

| 指标 | 值 |
|---|---|
| 总体 verdict | **PASS** |
| accepted findings | **0** |
| blocking open questions | **0** |
| observation 最终状态 | 全部 `NO_CURRENT_FIX`，不阻塞 R03 |
| residual risk 最终状态 | 全部归类为 baseline owner 或 instrumentation limit，不阻塞 R03 |

---

## 1. 80-path protected proof 独立复核

### 1.1 集合构成

protected set 由 `git diff --name-only 8c6ae966..HEAD` 的 75 个完整 R03 accepted-range paths，加 aggregate validation fix、Controller validation、MiMo deepreview、DS deepreview 与 Controller adjudication 5 个 paths，按 `LC_ALL=C sort -u` 形成。

本 re-review artifact 不属于创建前 80-path set。

| 检查 | fix record 值 | 独立复算值 | 结论 |
|---|---|---|---|
| protected path count | `80` | `80` | **PASS** |
| ordered path SHA-256 | `75d464307db88470d1f8efcb9b302c9f18b3d3bc4396ca8bff5ae0ff4ee10e9a` | `75d464307db88470d1f8efcb9b302c9f18b3d3bc4396ca8bff5ae0ff4ee10e9a` | **PASS** |

### 1.2 关键 production file content 独立验证

逐文件 SHA-256 与 zero-change fix record §3.2 对比：

| 文件 | fix record SHA-256 | 独立复算 | 结论 |
|---|---|---|---|
| `dayu/host/accepted_result_projection.py` | `896598c0...` | `896598c0...` | **IDENTICAL** |
| `dayu/host/compact_material.py` | `cd5dea21...` | `cd5dea21...` | **IDENTICAL** |
| `dayu/host/tool_call_request.py` | `274e1085...` | `274e1085...` | **IDENTICAL** |
| `dayu/host/_event_payload.py` | `9940cdfd...` | `9940cdfd...` | **IDENTICAL** |
| `dayu/host/waiting.py` | `6c0a7675...` | `6c0a7675...` | **IDENTICAL** |
| `dayu/host/evidence.py` | `3738ee06...` | `3738ee06...` | **IDENTICAL** |
| `dayu/host/run_input.py` | `9111e6ca...` | `9111e6ca...` | **IDENTICAL** |
| `dayu/host/payload_resolution.py` | `d5b8cc0f...` | `d5b8cc0f...` | **IDENTICAL** |
| `dayu/host/tool_trace.py` | `9a9b157b...` | `9a9b157b...` | **IDENTICAL** |
| `dayu/host/memory.py` | `32c2a831...` | `32c2a831...` | **IDENTICAL** |
| `dayu/host/durable/memory.py` | `9423b7d6...` | `9423b7d6...` | **IDENTICAL** |
| `dayu/host/compact_pipeline.py` | `70cd1c87...` | `70cd1c87...` | **IDENTICAL** |
| `dayu/host/durable/run_transition.py` | `623f3749...` | `623f3749...` | **IDENTICAL** |
| `dayu/host/tool_runtime.py` | `459577c6...` | `459577c6...` | **IDENTICAL** |
| `dayu/runtime/__init__.py` | `e9a9a5dd...` | `e9a9a5dd...` | **IDENTICAL** |
| `utils/smoke_host_public_r03_semantic_ownership.py` | `9a50d6d2...` | `9a50d6d2...` | **IDENTICAL** |
| `tests/host/test_accepted_result_projection.py` | `a1c1e56b...` | `a1c1e56b...` | **IDENTICAL** |
| `tests/host/test_compact_material.py` | `f585fb13...` | `f585fb13...` | **IDENTICAL** |
| `tests/host/test_toolruntime_accept_barrier.py` | `a6d7c798...` | `a6d7c798...` | **IDENTICAL** |
| `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py` | `1bd299ed...` | `1bd299ed...` | **IDENTICAL** |

### 1.3 post-proof additions 确认

zero-change fix record 之后，仅有以下三项新增/变更，均为 Controller 授权的 post-proof additions：

| 项目 | 类型 | 授权来源 |
|---|---|---|
| `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-codex.md` | 新增 | Controller adjudication §4 |
| `docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-controller-validation.md` | 新增 | Controller adjudication §5 |
| `docs/host/issues-implementation-control.md` gate 行更新 | 修改 | Controller validation §4 |

**结论：** protected content 未漂移；post-proof additions 均为 Controller 授权的 gate-state 写入。

---

## 2. F01-F03 仍为 CLOSED 确认

### 2.1 F01（Compact shared renderer exact text preservation）

**直接证据：** `dayu/host/compact_material.py::run_input_material_block`（line 807-811）：

```python
material_text = (
    text
    if accepted_tool_evidence is not None
    else normalized_material_text(text)
)
```

当 `accepted_tool_evidence is not None`（即 typed accepted evidence block），跳过 `normalized_material_text()`，直接使用 shared renderer exact text。`RunInputMaterialBlock.__post_init__`（line 294-297）继续校验 `self.text == render_accepted_tool_evidence_for_llm(self.accepted_tool_evidence)`，不允许 generic normalization 改写。

**状态：CLOSED。** 未漂移。

### 2.2 F02（Hot/cold accepted-result integrity）

**直接证据：** `dayu/host/accepted_result_projection.py::_result_payload`（line 295-296）：

```python
if fallback_payload.get(_FIELD_RAW_TOOL_OUTCOME) is not None:
    return fallback_payload, ()
```

直接检查 hot payload 是否含 `raw_tool_outcome`。inline 路径直接使用；缺少时通过 envelope 的 `payload_ref/payload_digest` 解析冷 descriptor 并严格校验。旧 `resolved_payload_available` 参数已完全删除，`resolved_payload_available` 在 active source 中零命中。

**状态：CLOSED。** 未漂移。

### 2.3 F03（EventClass.CANONICAL_FACT typed row selection）

**直接证据：** `utils/smoke_host_public_r03_semantic_ownership.py::_canonical_fact_rows`（line 965-981）：

```python
return tuple(
    row
    for row in rows
    if row.event_class is EventClass.CANONICAL_FACT
    and row.event_type == event_type
)
```

request/awaiting/result 三类 row 共用同一 typed `EventClass.CANONICAL_FACT` 选择器。Engine preview 与 Host canonical fact 共享同一 event type 时，只有 `CANONICAL_FACT` 进入 strict resolver。`_strict_accepted_request_atoms`（line 949-963）确保 request atoms 也经过同一选择器。

**状态：CLOSED。** 未漂移。

---

## 3. 四消费者同源验证

| 消费者 | evidence 文本来源 | material 缺失处理 |
|---|---|---|
| RunInput | `render_accepted_tool_evidence_for_llm(material)` | `HostDurableError` |
| Memory | `render_accepted_tool_evidence_for_llm(material)` via `_selected_evidence_text` | `HostDurableError` |
| Compact | `render_accepted_tool_evidence_for_llm(projection.llm_material)` | `HostDurableError` |
| Tool Trace | `project_accepted_tool_result` → `_tool_result_summary_from_projection` | `HostDurableError` |

四消费者从同一 shared `AcceptedToolEvidenceLLMMaterial` 通过唯一 renderer `render_accepted_tool_evidence_for_llm` 生成 LLM-facing 文本。缺 material 时均抛 `HostDurableError`，不走 skip/fallback/limited signal。该同源关系在初轮 deepreview 中已验证，本次复核确认未漂移。

---

## 4. Opaque internal-only 验证

**直接证据扫描：**

- `OpaqueEvidenceRef` 在 `accepted_result_projection.py`、`run_input.py`、`memory.py`、`compact_material.py`、`tool_trace.py` 五个 shared/LLM path 中零命中。
- `OpaqueEvidenceRef` 只存在于 `dayu/host/evidence.py`（line 71, 258, 259, 279, 280），作为 typed internal provenance/audit owner。
- `compact_material.py` 所有 `source_locator_refs` 均设为空 tuple `()`。
- `memory.py` 的 `source_refs` 类型为 `OpaqueMemoryRef`（内部 memory provenance），不出现在 LLM-facing 文本中。
- `tool_trace.py` 的 `ref_kind`/`ref_id` 仅用于 hot row/cold JSONL 诊断字段，不进入 readable summary。

**结论：** opaque refs 保持 internal-only，未进入 LLM-readable business source。未漂移。

---

## 5. LLM-facing 文本验证

- `_source_projection` 只从 completed+ok outcome 的 `result.value.citation` object 提取 producer-owned 业务来源。Host 机械渲染整个 citation object（`canonical_json_dumps`），不枚举/筛选/排序 citation 业务 key。缺 citation 时使用唯一业务中性文案 `"该工具结果未提供业务来源。"`。
- `semantic_query_text` 存在时原样使用；否则对 exact `arguments_json` 做 bounded canonical JSON 展示（1200 字符上限），不做 key 分类。
- 旧 safe/fallback 文本（`工具证据不可用；缺少可安全展示`、`业务来源不可用；工具结果未提供可安全展示`、`参数正文由 accepted-result 同源投影提供`）在 production/test 中零命中。
- `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 包含 16 个内部治理标识，不得出现在 LLM-facing system content 中。

**结论：** LLM-facing 文本符合当前动作所需的业务可读语义。未漂移。

---

## 6. 安全机制验证

- DNS/peer、path containment、symlink、resource budget、atomic/process fencing 语义均保持。
- `file_path`、上传文件路径、合法业务字段和 framework `scope_token` 不因字段名被删除或改写。
- `dayu/tools/web/web_tools.py::password` 只属于 URL userinfo 解析，不是 LLM schema 参数。
- current production tool schemas 没有 `api_key/password/credential/access_token` 参数。
- `resolved_payload_available`、`json_redaction.py`、`_SENSITIVE_KEY_FRAGMENTS`、`JSON_REDACTION_MARKER`、`_INTERNAL_SOURCE_REF_KINDS`、`_readable_ref_text` 等已删除符号在 production/test 中零残留。

**结论：** 安全机制保持。未漂移。

---

## 7. 统一 tool authorization 检查

`rg -rn 'unified.*tool.*auth|tool.*authorization|authorization.*framework|credential.*broker' dayu/ tests/` 在 production code 中零命中。`BusinessSource` 在 production/test 中零命中。未引入统一 tool authorization。

---

## 8. Deferred Issue 边界

- Issue #142（workspace migration）：代码中无引用。
- Issue #151（write/assets）：代码中无引用。
- Issue #175（Fins Docling/process isolation）：代码中无引用。
- Issue #177（Doc output continuation wiring）：不在 R03 scope。`fetch_more` schema 文案修正是 S2 owner-level 修改，不声称 #177 完成。
- Issue #178（Web storage-state lifecycle）：完全不进入 R03。
- 未新增第四 slice、兼容分支或 legacy fallback。

**结论：** deferred Issue 边界保持。未越界。

---

## 9. Wait-resolution execution identity 验证

**直接证据：** `durable/run_transition.py::_invalid_waiting_resolution_precondition` 校验 `wait_record.execution_id == source_attempt.execution_id`。不一致返回 `INVALID_STATE`，发生在任何 result/resume/terminal append 及 state mutation 之前。

**测试覆盖：** `test_resolve_wait_command.py::test_waiting_resolution_transition_rejects_execution_identity_mismatch` 参数化 `completed` 和 `failed` 两个 transition branch。

**结论：** wait-resolution execution identity 保持。未漂移。

---

## 10. 测试与静态门槛验证

### 10.1 直接受影响矩阵

```text
pytest <§13.1 第一组 affected suites> -q
=> 2339 passed, 2 skipped, 5 deselected, 3 warnings
```

三条 warning 均为 edgar 依赖弃用提示。2 skipped 与 Controller 结果一致。

### 10.2 pyright

```text
python -m pyright dayu/ tests/ utils/
=> 0 errors, 0 warnings, 0 informations
```

### 10.3 git diff --check

```text
git diff --check
=> PASS
```

---

## Findings

### 未发现实质性问题

对 R03 完整组合行为（S1+S2+S3+F01-F03+zero-change fix+Controller validation）的完整 re-review 未发现可由直接代码/数据证据支撑的实质性 defect。所有维度与初轮 deepreview verdict 一致。

---

## Open Questions

无。

---

## Residual Risk

- 全量六域的两个 logging-order failure 继续归 Web smoke/test harness baseline owner；它们在 fresh process 隔离为 green，不进入 R03 fix。
- macOS coverage 预载入对 Web/Fins spawn pickling 的影响继续归 validation harness/environment owner；真实子进程用例已有无 instrumentation 的通过证据。
- `waiting.py::_expire_wait_in_transaction` 本地实例化 store 继续归 `STYLE_OBSERVATION / NO_FIX`；同一 durable transaction 内功能正确。
- `_WAIT_EXPIRY_MESSAGE` 硬编码中文继续归 `OWNER-CORRECT / NO_FIX`；它明确说明 Host 期限与结果未接受，不伪装成财报事实。

上述 residual risk 均不是 accepted finding，不要求当前 R03 fix，不阻塞 R03 aggregate completion。

---

## 审查覆盖总结

| 区域 | 覆盖方式 | 结论 |
|---|---|---|
| 80-path protected proof | 独立 ordered-path SHA 复算 + 20 个关键文件逐文件 SHA 对比 | **PASS** |
| post-proof additions | Controller 授权确认 + 控制文档 diff 审查 | **PASS** |
| F01 compact whitespace preservation | 直接读取 `compact_material.py` line 807-811 + `__post_init__` invariant | **PASS** |
| F02 cold descriptor resolution | 直接读取 `accepted_result_projection.py` line 295-296 + source scan | **PASS** |
| F03 EventClass.CANONICAL_FACT selection | 直接读取 `smoke_host_public_r03_semantic_ownership.py` line 965-981 | **PASS** |
| S1 shared request atom + durable replay identity | `tool_call_request.py` writer 不变量 + `run_transition.py` execution identity | **PASS** |
| S2 blacklist 删除 + owner schema 修正 | source scan 零命中 + `json_redaction.py` ABSENT | **PASS** |
| S3 opaque refs internal-only | 5 个 shared path 零命中 + `evidence.py` internal-only | **PASS** |
| 四消费者同源 | shared renderer + `HostDurableError` fail closed | **PASS** |
| LLM-facing 文本 | source/query projection + 旧文案零残留 | **PASS** |
| 安全机制 | DNS/peer/path/symlink/resource/fencing + deleted symbol scan | **PASS** |
| 统一 tool authorization | 全仓 scan 零命中 | **PASS** |
| Deferred Issue 边界 | Issue 142/151/175/177/178 零代码引用 | **PASS** |
| Wait-resolution execution identity | `run_transition.py` precondition + parametrized test | **PASS** |
| 测试验证 | 2339 passed, 2 skipped, pyright 0 errors | **PASS** |
