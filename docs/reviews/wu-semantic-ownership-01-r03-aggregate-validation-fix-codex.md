# WU semantic ownership 01 / R03 aggregate validation fix（Codex）

## 1. 范围与结论

- 本次工作属于同一 umbrella WU 的 `R03 aggregate validation fix`，不是新 WU、不是新 slice，未进入 R04。
- accepted findings 为 `R03-AGG-CV-F01`、`R03-AGG-CV-F02` 与
  `R03-AGG-CV-F03`。
- 修复分别落在 shared material construction / invariant owner、shared
  accepted-result payload resolution owner 与 smoke internal diagnostic harness
  owner：
  - `dayu/host/compact_material.py`
  - `dayu/host/accepted_result_projection.py`
  - `utils/smoke_host_public_r03_semantic_ownership.py`
- 实现与直接测试只修改：
  - `dayu/host/compact_material.py`
  - `dayu/host/accepted_result_projection.py`
  - `tests/host/test_compact_material.py`
  - `tests/host/test_accepted_result_projection.py`
  - `tests/host/test_toolruntime_accept_barrier.py`
  - `utils/smoke_host_public_r03_semantic_ownership.py`
  - `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`
- 未修改 Web payload、shared renderer key/filter、`payload_resolution.py` strict
  primitive、Fins、Service、Memory/Trace/Compact/RunInput 消费者、兼容路径或
  invariant；未修改 Controller artifact、control doc、既有 review artifact；未
  commit/push。

三个 owner fix 与 focused 验证均通过。第二个 fresh-root smoke 暴露的
Memory/Tool Trace projection failure 已由 F02 修复；第三、第五个 fresh-root smoke
分别暴露 F03 request/result collection 对同名 Engine preview 的 typed row-selection
遗漏，均由同一个 canonical-fact collection owner 修复。第四个 fresh-root 的单次
provider refusal 已由 Controller 裁定为外部 nondeterministic observation，不是 code
finding，也不计 hard-gate pass。第六个全新 root 的五个 required exact calls、六轮
`ROUND_PASS` 与 post-run projection summary 全部通过，exit code 为 0。

## 2. 第一性原理与语义 owner

### 2.1 finding 是否成立

成立，且 Controller 给出的严重性准确。typed accepted evidence 已由 accepted-result projection 产生结构化 `llm_material`，shared renderer 是该材料对 LLM 的唯一文本投影。`RunInputMaterialBlock` 同时携带 typed material 与 rendered text，因此其 `__post_init__` 对二者 exact equality 的校验是正确 owner-level invariant，不应放宽。

### 2.2 root cause（直接代码路径）

旧路径：

1. typed accepted outcome 经 canonical request/outcome 校验与 accepted-result projection 形成 `AcceptedToolEvidenceLLMMaterial`；
2. `render_accepted_tool_evidence_for_llm(...)` 生成唯一 exact renderer text；
3. `_accepted_tool_evidence_delta_blocks` 把 exact text 传给 `run_input_material_block`；
4. `run_input_material_block` 无条件调用 ordinary `normalized_material_text`，改写 renderer 内生产者重复空白；
5. `RunInputMaterialBlock.__post_init__` 重新使用 shared renderer 校验 typed material，正确拒绝 `block.text != renderer(accepted_tool_evidence)`。

真实 Web 证据中，该错误把 shared renderer 从 19,981 chars 改成 19,381 chars，涉及 271 个 multi-space runs，delta 600。根因不是 Web payload 或 renderer，而是 shared material builder 把 ordinary generic normalization 错用于已有唯一 renderer owner 的 typed evidence。

### 2.3 修复后的路径

`run_input_material_block` 现在按语义输入分流：

- ordinary generic material 继续使用 `normalized_material_text`；
- 携带 `accepted_tool_evidence` 的 typed material 原样保留调用方传入的唯一 renderer exact text；
- `size_units` 与 `content_digest` 从最终 exact text 同源派生；
- 既有 `RunInputMaterialBlock.__post_init__` exact invariant 保持不变，错误或非 renderer 文本仍会失败。

此修复没有在 builder 内静默重渲染，也没有增加 fallback、loose parsing、兼容分支或消费者补偿。

## 3. owner-level regression

`tests/host/test_compact_material.py::test_pre_dispatch_evidence_preserves_shared_renderer_exact_whitespace` 使用真实路径：

1. 构造 typed `ToolCompletedOutcome` / `ToolResultSuccess`，其业务 material 包含重复空白；
2. 写入 canonical `TOOL_CALL_REQUESTED` atom 与 `TOOL_RESULT_ACCEPTED` outcome/envelope；
3. 通过真实 accepted-result projection 和 `build_pre_dispatch_compact_material_view` 构造 pre-dispatch block；
4. 证明 ordinary normalization 确实会改写该 renderer text；
5. 断言 block 构造成功，且：

```text
block.text == render_accepted_tool_evidence_for_llm(block.accepted_tool_evidence)
```

既有 ordinary material normalization 测试保持通过。RunInput、Memory、Trace 与 assembly focused 测试共同复核四消费者继续复用 shared projection，没有新增回退路径。

## 4. 验证记录

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### 4.1 owner suite 与覆盖率

```text
pytest tests/host/test_compact_material.py \
  --cov=dayu.host.compact_material --cov-report=term-missing -q
```

结果：`65 passed`；`dayu/host/compact_material.py` 为 `916 statements / 152 missed / 83%`，达到单文件 `>=80%` 要求。

F02 shared projection owner：

```text
pytest tests/host/test_accepted_result_projection.py \
  --cov=dayu.host.accepted_result_projection --cov-report=term-missing -q
```

结果：`34 passed`；`dayu/host/accepted_result_projection.py` 为
`271 statements / 17 missed / 94%`。真实 ToolRuntime producer suite
`tests/host/test_toolruntime_accept_barrier.py` 结果为 `49 passed`。

### 4.2 Compact / RunInput / Memory / Trace / assembly focused tests

```text
pytest \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_public_compact_smoke.py \
  tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py -q
```

结果：`290 passed, 1 skipped`；另有 3 条既有 `edgar` deprecation warnings。

F02 最终版本补充传播矩阵：

```text
pytest tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_public_compact_smoke.py -q

pytest tests/host/test_memory_projection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py -q
```

结果分别为 `178 passed, 1 skipped` 与 `147 passed`；第二组包含 3 条既有
`edgar` deprecation warnings。

F03 request/result typed row-selection 完成后的最终 focused 矩阵：

```text
pytest tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_public_compact_smoke.py \
  tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py -q
```

结果：`360 passed, 1 skipped`；另有 3 条既有 `edgar` deprecation warnings。
F03 direct assembly/diagnostic 文件单独运行结果为 `18 passed`。

### 4.3 pyright

```text
python -m pyright dayu/ tests/ utils/
```

F01 首次运行发现新增测试的 `view` 可能未绑定；F02 首次运行同样发现两个
新增测试的局部 projection 变量可能未绑定。两次均只把断言放回 durable store
context 内完成类型收窄。最终全仓结果：`0 errors, 0 warnings, 0 informations`。

### 4.4 Ruff

```text
python -m ruff check \
  dayu/host/compact_material.py \
  dayu/host/accepted_result_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_toolruntime_accept_barrier.py \
  utils/smoke_host_public_r03_semantic_ownership.py \
  tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py
```

结果：`All checks passed!`

### 4.5 diff 与工作区边界

```text
git diff --check
```

结果：通过，无 whitespace error。

修复前已有、并保留的 Controller dirty artifacts：

- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-semantic-ownership-01-r03-aggregate-controller-validation.md`

本次没有修改它们。最终实现 diff 只涉及
`dayu/host/compact_material.py`、`dayu/host/accepted_result_projection.py`、
`tests/host/test_compact_material.py`、
`tests/host/test_accepted_result_projection.py` 与
`tests/host/test_toolruntime_accept_barrier.py`、
`utils/smoke_host_public_r03_semantic_ownership.py` 与
`tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`，并更新
本文。

## 5. accepted plan §13.5 source scans

### 5.1 opaque/source-ref scan

执行：

```text
rg -n 'OpaqueEvidenceRef|source_refs|locator_refs|ref_kind|ref_id' \
  dayu/host/accepted_result_projection.py dayu/host/run_input.py \
  dayu/host/memory.py dayu/host/compact_material.py dayu/host/tool_trace.py
```

结果：`OpaqueEvidenceRef` 在上述生产文件中为 0；其余命中为 durable/internal source contract、canonical source refs 与 diagnostic refs。人工复核 shared LLM material 构造和四消费者投影，未发现从 opaque ref 反推业务 source 或新增 fallback。

### 5.2 governance-token scan

执行：

```text
rg -n 'payload_ref|artifact_ref|event_id|digest|cursor|tool_call_id' \
  dayu/host/accepted_result_projection.py dayu/host/evidence.py \
  dayu/host/compact_material.py dayu/host/tool_trace.py
```

结果：501 个命中行（657 次命中），均需按内部治理字段人工分类，不能以非零本身判失败。关键投影复核结果：

- accepted projection 的 `payload_refs` 明确只用于诊断，不进入 LLM-facing source；
- LLM material 的 `source_text` 只来自已校验 `projection.source.text`；
- compactor `source_note` 只来自 typed material 的 `source_text`；
- tool-trace readable `business_source_text` 只来自同一 `projection.source.text`；
- 对 `source_text/source_note/business_source_text` 与上述治理 token 的赋值交叉扫描为 0。

因此没有把裸 payload/event/digest/cursor/tool-call 标识投影成业务来源。

### 5.3 forbidden LLM-facing fallback text scan

执行：

```text
rg -n '工具证据不可用；缺少可安全展示|业务来源不可用；工具结果未提供可安全展示|参数正文由 accepted-result 同源投影提供' dayu tests
```

结果：0 matches（`rg` exit 1，符合预期）。

## 6. README 决定

已先阅读 `tests/README.md` 的 Agent 更新约束，并复核 `dayu/host/README.md` 的职责边界：

- Host README 已记录 typed accepted evidence、唯一 renderer、shared projection、
  descriptor strict resolution 与四消费者 fail-closed invariant；
- tests README 已记录 Compact previous block 的 typed exact invariant、真实 outcome
  codec、descriptor-backed accepted result 与四消费者等价性；
- F03 只修正既有 mandatory smoke 的 internal diagnostic typed row collection；
  `utils/` 依项目规则无需 coverage，直接 assembly test 仍属于 README 已记录的真实
  R03 smoke 职责；
- 本修复没有新增稳定测试层级、测试入口、维护流程或用户可见 contract，只修正
  owner 对既有 contract 的实现。

因此不修改任何 README。

## 7. fresh-schema 真实 public smoke

### 7.1 fresh root 与输入

新建且保留：

```text
workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-01
```

机械复制 `workspace/portfolio/600519` 到该 root；没有删除、覆盖旧 workspace 或 Controller 前次失败 root。运行参数保持 Controller 同一非秘密参数：

- scene：`interactive`
- Doc：`docs/reviews/wu-semantic-ownership-01-r03-s3-controller-validation.md`
- Web query：`OpenAI official documentation`
- Fins ticker：`600519`
- Fins document id：`fil_cn_2fa0bb0cabae8145a99d7607195e671ad6d815e5`
- awaiting tool：`start_fins_preprocess`
- `rebuild_processed=false`（脚本固定参数）
- `--keep-workspace`

### 7.2 chain 结果

脚本输出依次确认：

```text
R03 SMOKE ROUND_PASS label=doc
R03 SMOKE ROUND_PASS label=web
R03 SMOKE ROUND_PASS label=fins-awaiting
R03 SMOKE ROUND_PASS label=fins-list
R03 SMOKE ROUND_PASS label=fins-read
```

这证明原 `R03-AGG-CV-F01` 已不再阻塞 Web accepted evidence 进入 Fins awaiting，完整 Doc/Web/Fins chain 均已执行。

### 7.3 新 defect 的直接证据与停止点

随后脚本以 exit 1 结束：

```text
host.memory_repair.catch_up.failed
consumer_id=host.memory.session.v1
started_cursor=282
finished_cursor=282
failures=1
stop_reason=failure
max_event_sequence=350

dispatch.memory_projection.repair_not_reached
required_event_sequence=350
started_cursor=282
finished_cursor=282
stop_reason=failure

R03 SMOKE FAIL round observation failed: none
```

fresh SQLite 的只读证据进一步显示：

- `host.memory.session.v1` checkpoint 停在 sequence 282；
- `host_projection_failures` 在 sequence 315 的 `TOOL_RESULT_ACCEPTED` 记录：`TOOL_RESULT_ACCEPTED memory LLM material is missing`；
- 同一 sequence 315 的 `host.tool-trace` failure 为：`TOOL_RESULT_ACCEPTED tool trace LLM material is missing`；
- 新 observation run 的 sequence 348/349/350 已写入 `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` / `RUN_STARTED`；sequence 352/353 以 `memory_projection_repair_required` 写入 `ATTEMPT_FAILED` / `RUN_FAILED`。

证据位置：

- `workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-01/.dayu/host/dayu_host.sqlite3`
- `workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-01/.dayu/artifacts/audit/host-audit.jsonl`（相关 canonical failure 为第 70–75 行）
- `workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-01/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`

该 failure 位于原 accepted finding 之后，且不属于本次获准修改的 shared material normalization owner。按用户约束未诊断、未修复、未修改其它代码；Controller 需要把它作为新的 aggregate smoke 证据独立裁决。

## 8. `R03-AGG-CV-F02`

### 8.1 第一性原理、owner 与 root cause

Controller 接受 F02 后补充的 durable 证据与代码同源：sequence 315 是真实
`get_document_sections` canonical `TOOL_RESULT_ACCEPTED`；EventLog row 的
`payload_ref/payload_digest` 指向完整存在的 82,196-byte cold descriptor，hot
`payload_json` 只保留 envelope、descriptor pair 与治理字段，不含
`raw_tool_outcome`。

`ProjectionEventView.payload` 由 `_event_payload.payload_object(row)` 只解析 hot
`payload_json`，同时从 raw row 保留 descriptor columns。Memory 与 Tool Trace
把这个 hot payload 作为 `resolved_payload` 传给 shared projection。

旧路径：

1. `_result_event_payload` 接受 caller 提供的完整性已读 hot payload；
2. `project_accepted_tool_result` 把“caller 提供了 payload”编码成
   `resolved_payload_available=True`；
3. `_result_payload` 把该状态误解释为“cold result 已解析”，直接返回不含
   `raw_tool_outcome` 的 hot payload；
4. shared projection 产生 `result_text=None / llm_material=None`；
5. Memory 与 Tool Trace 在同一 canonical event 上分别 fail closed，最终阻塞下一
   observation Run。

语义 owner 是 `dayu/host/accepted_result_projection.py` 的 shared result-payload
resolution。`resolved_payload` 只证明 EventLog hot payload 已读取，不能证明 cold
result 已解析。

### 8.2 最小修复路径

`_result_payload` 不再接收或推理 `resolved_payload_available`：

- 当前 payload 实际含非空 `raw_tool_outcome` 时，作为 inline result 直接使用；
- 当前 payload 不含 raw outcome 时，无论 caller 是否传入 resolved hot payload，
  都继续调用既有 `event_payload_object_for_result_ref`；
- 既有 resolver 使用 accepted envelope 的 result ref 与 `EventLogRow` 保留的
  descriptor columns 校验 ref/digest，并通过 durable descriptor resolver 校验
  descriptor、SQLite/artifact bytes 与 canonical JSON；
- resolver 异常继续投影为 `result_payload_unavailable / LOST / llm_material=None`，
  strict Memory/Trace/Compact/RunInput 消费者据此 fail closed，不发布 fallback。

因此没有修改 `payload_resolution.py`，没有从 hot payload 字符串重新实现 descriptor
规则，也没有在四消费者分头补偿。

### 8.3 owner / producer / propagation regressions

- `test_tool_result_accepted_large_payload_uses_sqlite_payload_descriptor` 复用真实
  `DefaultHostToolFactAcceptPort` 与 ToolRuntime threshold，证明生产 hot payload
  无 raw outcome、cold descriptor 有完整 outcome，shared projection 仍取得 exact
  typed material。
- `test_projection_resolves_hot_payload_cold_result_and_keeps_inline_direct` 证明
  resolved inline payload 直接使用，而 producer-shaped hot payload 会解析 cold
  result。
- `test_projection_hot_payload_cold_descriptor_corruption_fails_closed` 覆盖 row/envelope
  ref mismatch、digest mismatch、ref missing、digest missing，统一得到 LOST、无
  result text、无 LLM material 与 `result_payload_unavailable`，没有 fallback。
- `test_same_accepted_result_has_equivalent_consumer_projection` 改为
  producer-shaped hot/cold result；shared projection、Memory、Tool Trace 与下一轮
  pre-dispatch Compact 同时取得同一个 typed material，并继续验证 renderer/source
  等价与 opaque refs 不可见。

全仓扫描 `resolved_payload_available` 为 0；`payload_resolution.py` 无 diff。

## 9. 第三个 fresh-schema 六轮 public smoke

### 9.1 fresh root

新建并保留：

```text
workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-02
```

机械复制 `workspace/portfolio/600519`：94 MiB、29 files。没有删除或覆盖前两个
root。运行参数与第 7 节相同，保留 `start_fins_preprocess`、
`rebuild_processed=false` 与 `--keep-workspace`。

### 9.2 六轮结果与 F02 closure

脚本依次输出：

```text
R03 SMOKE ROUND_PASS label=doc
R03 SMOKE ROUND_PASS label=web
R03 SMOKE ROUND_PASS label=fins-awaiting
R03 SMOKE ROUND_PASS label=fins-list
R03 SMOKE ROUND_PASS label=fins-read
R03 SMOKE ROUND_PASS label=observation
```

fresh SQLite 的只读证据：

- `host.memory.session.v1`、`host.tool-trace`、`host.audit-log-jsonl` 与
  `host.outbox-terminal` checkpoint 全部到达 sequence 280；
- `host_projection_failures` 为 0 rows；
- 最终 observation 已完成，不再出现 `memory_projection_repair_required`，证明
  sequence 315 同类 hot/cold result 的 shared projection closure 已恢复。

### 9.3 六轮后的新 harness failure

六轮完成后，脚本 post-run semantic assertion 以 exit 1 结束：

```text
R03 SMOKE FAIL arguments_payload_digest must be non-empty text
```

直接代码/数据证据表明这不是 F02 production path 的新失败：

- smoke 脚本 `request_rows` 只按 `event_type == TOOL_CALL_REQUESTED` 过滤，未限定
  `EventClass.CANONICAL_FACT`，随后把全部 rows 传给 strict
  `tool_call_request_atoms`；
- 每次真实调用都同时存在 Engine preview row 与 Host canonical atom：sequence
  `21/22`、`59/60`、`94/95`、`159/160`、`235/236`；
- preview rows 的 `event_class=preview`、`source=host.engine_ingest`，按其诊断
  schema 没有 `arguments_payload_digest`；canonical rows 的
  `event_class=canonical_fact`、`source=host.tool_runtime.accept` 或
  `host.tool_runtime.awaiting_accept`，strict digest 完整；
- 第一个 sequence 21 preview 被 strict canonical parser 读取后产生上述错误。

证据位置：

- `workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-02/.dayu/host/dayu_host.sqlite3`
- `workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-02/.dayu/artifacts/audit/host-audit.jsonl`
- `workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-02/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`

该失败发生在六轮全部成功、所有 projection checkpoint 追平之后，owner 位于 smoke
post-run canonical-row selection/assertion，不属于 F02 shared projection resolution。
Controller 随后将其接受为同一 aggregate validation 的
`R03-AGG-CV-F03`。

## 10. `R03-AGG-CV-F03`

### 10.1 第一性原理、owner 与 root cause

EventLog 允许 Engine activity preview 与 Host semantic canonical fact 使用相同
`event_type`；二者的 typed owner discriminator 是既有 `EventClass`。preview 只承诺
Engine activity fields，不承诺 strict accepted request atom 或 accepted result evidence
envelope。strict parser/projection 拒绝 preview 缺少 canonical 字段是正确行为，不能
放宽。

旧 diagnostic collection 有两处同源遗漏：

1. `request_rows` 只按 `TOOL_CALL_REQUESTED` event type 选择，Engine preview 被
   传给 `tool_call_request_atoms`，因无 `arguments_payload_digest` 正确失败；
2. 首次 request 修复后，`result_rows` 仍只按 `TOOL_RESULT_ACCEPTED` event type
   选择，Engine preview 被传给 shared accepted projection，因无
   `accepted_evidence_envelope` 正确失败；`awaiting_rows` 同样尚未表达 strict
   canonical-fact contract。

owner 是 mandatory smoke internal diagnostic harness 的 typed row collection，不是
产品 EventLog、Engine ingest、payload resolver 或 accepted projection。

### 10.2 最小修复

新增单一 `_canonical_fact_rows(rows, event_type=...)` collection owner：

- 唯一条件是 `row.event_class is EventClass.CANONICAL_FACT` 且 event type exact
  match；
- request、awaiting、result 三组 diagnostic rows 全部复用该 helper；
- request canonical rows 之后仍逐个调用 strict `tool_call_request_atoms`；
- result canonical rows 之后仍逐个调用 shared `project_accepted_tool_result`；
- 不按 source、event-id prefix 或 payload field presence 猜测，不增加 loose
  parsing、fallback、retry 或兼容分支。

产品 EventLog、Engine ingest、accepted-result projection、payload resolver 与四个产品
消费者均无 F03 diff。

### 10.3 direct regression

`test_strict_diagnostic_collection_ignores_engine_previews` 在真实 durable EventLog
transaction 中写入 request、awaiting、result 三组同名 canonical/preview rows：

- request canonical 使用生产 `build_tool_call_requested_event_request`，preview
  故意不含 strict digest；
- result canonical 使用 typed `ToolCompletedOutcome/ToolResultSuccess`、生产 accepted
  outcome codec 与 typed evidence envelope codec；preview 只含 Engine activity
  fields；
- 断言三组 collector 都只保留 canonical facts；
- 断言 request arguments/digests exact；
- 对筛选后的 canonical result 调用真实 shared projection，并断言 typed material 的
  result text 等于 raw outcome canonical JSON。

若 collector 错把 result preview 纳入，shared projection 会以
`accepted result evidence envelope is missing` fail closed，测试不会用 fake fallback
掩盖。

## 11. F03 后续 fresh-root 真实 smoke

### 11.1 第四个 Agent root `-03`：外部 nondeterministic observation

保留：

```text
workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-03
```

六个 public rounds 全部 `ROUND_PASS`，四个 projection checkpoints 全部到达
sequence 437，`host_projection_failures=0`。post-run exact assertion 以
`required tool get_document_sections must occur exactly once` 失败；canonical accepted
request 实际只有四个，`get_document_sections` 为 0 次。

Controller 的只读 durable 证据同时证明该 fins-read Run 的
`effective_tool_set.requested/effective_business_tool_names` 均为
`get_document_sections`、selector 为 `subset`、Host input assembly complete；真实
provider response 却声称工具不可用并未发出 tool call。Controller 裁定这是单次真实
LLM 未遵守自足 exact-tool prompt 的外部 nondeterministic observation，不是 F03、Host
schema transport 或产品 owner defect。脚本的 exactly-once 拒绝正确，未放宽、未增加
自动重试/兼容逻辑；该 root 不计 hard-gate pass。

### 11.2 第五个 Agent root `-04`：F03 result-row 传播

保留：

```text
workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-04
```

该次五个 required canonical requests 全部存在且 digest 非空，六个 public rounds 全部
`ROUND_PASS`；四个 projection checkpoints 全部到达 sequence 329，
`host_projection_failures=0`。post-run 以以下 strict error 结束：

```text
R03 SMOKE FAIL accepted result evidence envelope is missing
```

直接 durable metadata 证明普通工具同时产生 canonical
`host.tool_runtime.accept/TOOL_RESULT_ACCEPTED`（含 envelope）与 preview
`host.engine_ingest/TOOL_RESULT_ACCEPTED`（无 envelope）。旧 `result_rows` 同时选入
两者；这是 F03 typed EventClass row-selection finding 的 result-row 第二处传播，不是
新 finding。该 root 证明 `-03` 的 provider refusal 未复现，但因 harness result
selection 失败，不计最终 pass。

### 11.3 第六个 Agent root `-05`：最终 hard-gate pass

新建并保留：

```text
workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-05
```

机械复制同一 94 MiB / 29-file `workspace/portfolio/600519` fixture；运行参数与第 7
节完全相同。脚本 exit code 为 0，bounded stdout 摘要为：

```text
R03 SMOKE ROUND_PASS label=doc
R03 SMOKE ROUND_PASS label=web
R03 SMOKE ROUND_PASS label=fins-awaiting
R03 SMOKE ROUND_PASS label=fins-list
R03 SMOKE ROUND_PASS label=fins-read
R03 SMOKE ROUND_PASS label=observation
R03 SMOKE PROJECTION_PASS requests=5 accepted_results=5 explicit_citations=1
R03 SMOKE PASS real Doc/Web/Fins public execution closure
R03 SMOKE WORKSPACE_KEPT true caller_requested=true cleanup=never
```

这同时证明五个 required exact calls、六轮 terminal success、F01 exact renderer、F02
hot/cold result resolution、F03 canonical request/awaiting/result collection 与四消费者
post-run projection summary 完整闭合。

## 12. residual risk / handoff

- `R03-AGG-CV-F01/F02/F03` 的 owner fix、owner/producer regressions、四消费者
  focused 回归、coverage、全仓 pyright、Ruff、diff 与 source scans 均通过。
- `-03` 记录真实 provider 的单次非确定性拒绝；strict smoke 正确 fail closed。没有为
  它放宽 exactly-once、修改 prompt/产品代码或增加自动 retry，因此 residual 仅是外部
  provider 调用固有非确定性，不是已知产品 correctness 缺口。
- `-05` 是最终 fresh-schema hard-gate pass；没有剩余已知 aggregate validation code
  finding。
- 本次停在同一 R03 gate 的 Controller handoff，不自行进入 R04；未 commit/push，
  也未改写 Controller 的 control/artifact 状态。
