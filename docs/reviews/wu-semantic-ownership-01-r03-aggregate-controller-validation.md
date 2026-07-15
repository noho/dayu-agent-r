# WU-SEMANTIC-OWNERSHIP-01 / R03 aggregate Controller validation（修复后独立复核）

## 1. Gate 结论

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- accepted R03 plan：`8c6ae966`，artifact 为 `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`。
- accepted slices：S1=`3e48f09e`、S2=`4b4696e5`、S3=`3f777753`。
- aggregate validation transition：`d6a1ef97`。
- Controller verdict：`PASS / READY_FOR_AGGREGATE_DEEPREVIEW`。

首轮 mandatory real public-run smoke 发现 Compact owner defect `R03-AGG-CV-F01`；后续 fresh runtime 依次暴露 shared accepted-result projection defect `R03-AGG-CV-F02` 与 smoke harness typed row-selection defect `R03-AGG-CV-F03`。AgentCodex 已在各自 owner boundary 完成窄修复和 owner-level regression；Agent fresh hard-gate smoke 与 Controller 独立 fresh smoke 均通过。Controller 接受 F01-F03 全部关闭，并授权下一 gate 仅为 R03 双路 aggregate deepreview；R04 与后续 remediation sub-WU 仍未授权。

## 2. 已通过证据

Controller 在 `d6a1ef97` tree 上独立执行 accepted plan §13.1 的直接受影响矩阵：

```text
pytest <§13.1 第一组 22 个 suites> -q
=> 927 passed, 2 skipped, 3 warnings
```

三条 warning 均为 edgar 依赖弃用提示。Controller 按 AGENTS.md 的真实激活方式执行：

```text
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
=> 0 errors, 0 warnings, 0 informations
```

曾直接调用 `.venv/bin/python -m pyright` 的一次结果因没有设置 `VIRTUAL_ENV`，使 pyright 无法解析虚拟环境依赖并产生 missing-import；该 harness invocation 不作为产品或 gate 证据，已由上述 canonical command supersede。

accepted plan §13.1 第二组全量六域回归首次结果为：

```text
pytest tests/host tests/tools tests/fins tests/runtime tests/engine tests/service -q
=> 4228 passed, 4 skipped, 5 deselected, 2 failed, 3 warnings
```

失败为 `test_sec_request_debug_logs_success_response` 与 `test_configure_does_not_touch_root_by_default`。二者不经过任何 R03 changed owner；按原相对顺序共同隔离运行为 `2 passed`，分别运行均为 `1 passed`。当前只分类为全量顺序性 logging-state observation，不接受为 R03 产品 finding；fix 后 canonical aggregate rerun 必须重新证明整组结果，不能用隔离通过代替。

## 3. Mandatory real public-run smoke

### 3.1 前置与首个环境结果

Controller 确认真实 provider credential、Web 网络与真实 Fins fixture 均存在。第一次使用既有 `workspace` 时，Host 在进入任何工具轮次前以 schema 20 / expected 23 拒绝旧 durable DB。该结果符合项目 fresh-schema policy；Controller 没有增加兼容读取或迁移，而是在 `workspace/tmp/r03-aggregate-public-smoke` 建立 fresh runtime root，并只机械复制真实 `workspace/portfolio/600519` fixture。

非秘密 smoke 输入：

```text
workspace_root = workspace/tmp/r03-aggregate-public-smoke
scene_id = interactive
doc_file = docs/reviews/wu-semantic-ownership-01-r03-s3-controller-validation.md
web_query = OpenAI official documentation
fins_ticker = 600519
fins_document_id = fil_cn_2fa0bb0cabae8145a99d7607195e671ad6d815e5
fins_awaiting_tool = start_fins_preprocess
keep_workspace = true
```

public execution chain 为脚本声明的 `ConfigLoader -> ToolsDiscovery -> ScenePrepare/Service assembly -> open_host -> ensure_session -> submit_followup`，使用真实 configured DeepSeek provider、真实 `read_file`、真实 `search_web` 与 production wait poller；未使用 fake/scripted runner 或手工 wait result。

### 3.2 真实失败

Doc round 与 Web round 均完成；进入 Fins awaiting round 的 pre-dispatch compaction 时失败：

```text
dayu.host.dispatch._operation
  -> build_pre_dispatch_compact_material_view
  -> _pre_dispatch_delta_material_blocks
  -> _accepted_tool_evidence_delta_blocks
  -> run_input_material_block
  -> RunInputMaterialBlock.__post_init__
  -> ValueError("accepted evidence block text must use shared renderer")
```

Host 将该错误 fail closed 为 `Context compaction material source failed before dispatch`。因此真实 smoke 为 FAIL，不能标 skip/pass，R03 completion 不成立。

## 4. Accepted finding `R03-AGG-CV-F01`

### 4.1 直接根因证据

`_accepted_tool_evidence_delta_blocks` 把唯一 shared renderer 输出同时作为 `text` 与 typed `accepted_tool_evidence` 传给 `run_input_material_block`。后者无条件调用 `normalized_material_text(text)`，会折叠每行连续空白；`RunInputMaterialBlock.__post_init__` 随后又要求存下的 `text` 与 `render_accepted_tool_evidence_for_llm(accepted_tool_evidence)` 字节级相等。

Controller 从失败 fresh durable DB 只读投影 accepted evidence，得到：

| tool | renderer 与 generic normalization | renderer chars | normalized chars | 多空格 runs | 最大 run | delta |
|---|---|---:|---:|---:|---:|---:|
| `read_file` | equal | 7419 | 7419 | 0 | 0 | 0 |
| `search_web` | **not equal** | 19981 | 19381 | 271 | 7 | 600 |

这证明 defect 由真实 Web result 中合法的 producer-owned空白触发；不是 opaque ref、secret、schema 20、Fins、provider随机性或下游展示误差。当前测试只使用了 normalization-stable evidence text，未覆盖 shared renderer 输出含重复空白的真实 owner path。

### 4.2 Owner 与 required fix

- semantic owner：`dayu/host/compact_material.py` 的 shared material block construction / invariant boundary。
- 不应修改：Web producer payload、`accepted_result_projection.py` citation/source owner、四消费者分别加 fallback、renderer 内容筛选、Fins 或 Service。
- required behavior：accepted evidence block 必须保留唯一 shared renderer 的 exact text；generic ordinary-material normalization不得改写该 typed evidence文本。builder/invariant 之间必须只有一个同源规则，不能靠 consumer catch、兼容分支或放宽 invariant 掩盖。
- required test：在 owner-level Compact path 使用真实 typed accepted outcome/projection，注入含重复空白的 result material，证明 pre-dispatch evidence block 构造成功、`block.text == render_accepted_tool_evidence_for_llm(block.accepted_tool_evidence)`，且 RunInput/Memory/Compact/LLM-ready Trace 的既有传播断言不回退。
- required validation：受影响测试、`compact_material.py >=80%`、Ruff、canonical pyright、`git diff --check`、active source/propagation scans，以及从另一个 fresh runtime root 完整重跑真实 Doc/Web/Fins public smoke。

## 5. Scope、安全与 deferred 边界

本 finding 不授权修改 Topic 8/9、统一 tool authorization、Issue 177/178、wait lifecycle、Fins Docling isolation、Web security/resource budget、旧 DB compatibility/migration 或新的 BusinessSource abstraction。现有 DNS/peer、path containment、symlink、resource budget、atomic/process fencing 与 opaque provenance internal-only 语义必须保持。

## 6. Accepted finding `R03-AGG-CV-F02`

### 6.1 真实组合失败

AgentCodex 修复 F01 后，在另一个 fresh schema-23 runtime root 完整运行同一真实 public chain。Doc、Web、Fins awaiting、`list_documents` 与 `get_document_sections` 五个 required tool rounds 均成功；最终 no-tool observation Run 在任何 `RUNNER_CALL_INPUT_ASSEMBLED` 之前以 `memory_projection_repair_required` fail closed。

Durable direct evidence：

- sequence 315 是 producer-owned `get_document_sections` canonical `TOOL_RESULT_ACCEPTED`；其 accepted envelope、strict request link 和 tool identity 完整。
- 该真实 result 的冷 descriptor 为 `payload-tool-result-event-tool-result-accepted-6f1fc95d...`，payload size `82196` bytes，descriptor row与 digest存在；hot EventLog payload只携带 descriptor pair，不携带 `raw_tool_outcome`。
- `host_projection_failures` 对同一 sequence 315 同时记录 Conversation Memory `TOOL_RESULT_ACCEPTED memory LLM material is missing` 与 Tool Trace `TOOL_RESULT_ACCEPTED tool trace LLM material is missing`。
- `project_accepted_tool_result(..., resolved_payload=hot_event_payload)` 把“EventLog hot payload已读取”错误等同于“result payload已解析”，`_result_payload(... resolved_payload_available=True)` 直接返回缺 `raw_tool_outcome` 的 hot payload，不再解析 envelope 指向的冷 descriptor，最终 `result_text=None`、`llm_material=None`。

### 6.2 Owner 与 required fix

- semantic owner：`dayu/host/accepted_result_projection.py` 的 shared result-payload resolution；严格 descriptor integrity primitive 继续由 `dayu/host/payload_resolution.py` owner。
- `resolved_payload` 只证明 EventLog hot payload已通过完整性读取，不能证明其中引用的 accepted result cold payload已经解析。
- inline `raw_tool_outcome` 继续直接使用；hot payload缺 raw outcome 时，必须从同一 hot payload与 accepted envelope 的 descriptor ref/digest同源解析冷 result，并严格校验 ref/digest/descriptor/canonical JSON。不得在 Memory、Tool Trace、Compact 或 RunInput分别修复，不得把 missing material降级为 fallback。
- required regression 必须覆盖真实 hot-inline + cold-result descriptor shape，并证明 shared projection、Memory、Tool Trace和下一轮 pre-dispatch material都取得同一个 typed material；descriptor ref/digest mismatch或缺失仍 fail closed。
- 修复后必须从第三个 fresh runtime root重跑全部六轮真实 public chain；前五轮成功不能替代最终 projection closure。

F02 仍属于 accepted R03 Topic 3/4 shared projection closure，不进入 Fins schema、Issue 177/178、BusinessSource、旧 DB compatibility或统一 authorization。

## 7. Accepted finding `R03-AGG-CV-F03`

### 7.1 真实组合证据

AgentCodex 关闭 F02 后使用第三个 fresh schema-23 runtime root 重跑同一真实 public chain。脚本明确输出 Doc、Web、Fins awaiting、Fins list、Fins read 和最终 no-tool observation 六个 `ROUND_PASS`，证明 F01/F02 的真实 runtime 阻断已消失；失败发生在全部 public runs 之后的 internal diagnostic read：

```text
R03 SMOKE ROUND_PASS label=observation
R03 SMOKE FAIL arguments_payload_digest must be non-empty text
```

直接 durable 证据表明，每个工具调用都有两类同名 `TOOL_CALL_REQUESTED` row：

- `event_class=preview`、`actor/source=host.engine_ingest` 的 Engine preview，只保存 Engine activity fields，不承诺 `arguments_payload_digest`。
- `event_class=canonical_fact`、`actor=host.tool_runtime` 的 Host accepted request atom，保存 strict arguments storage/digest contract。

`utils/smoke_host_public_r03_semantic_ownership.py::_projection_observation_in_transaction` 当前只按 `event_type` 选择 row，因此把 preview row 送入仅解析 accepted canonical atom 的 `tool_call_request_atoms`。失败不是 public Host、provider、Fins、Memory/Trace projection 或 strict resolver defect，而是 mandatory smoke 的 internal observation 没有使用 EventLog 已有 typed `event_class` 语义。

### 7.2 Owner 与 required fix

- semantic owner：`utils/smoke_host_public_r03_semantic_ownership.py` 的 post-run internal diagnostic row selection。
- required behavior：post-run strict accepted-fact 集只能包含 `EventClass.CANONICAL_FACT` 的 request/awaiting/result row；request 再由 strict atom resolver 验证，result 再由 shared accepted-result projection 验证。Engine preview 仍由自身 activity 语义 owner，不得按 event id prefix、source、payload field presence、loose parsing 或 fallback 猜测。
- required regression：构造同 session 的 preview 与 canonical request/result pairs，证明 preview 不进入 strict atom/accepted-result validation，canonical request 仍按 exact arguments/digest 验证且 canonical result 仍按 accepted envelope/material 验证。
- required validation：在第四个 Agent-owned fresh runtime root 重跑六轮 public chain 与全部 post-run projection assertions；随后 Controller 还必须在自己的全新 root 独立复核。

F03 不授权改变 EventLog event type、Engine ingest、Host request atom schema、strict payload resolver 或任何产品 runtime 语义。

### 7.3 同一 finding 的 result-row 传播证据

首次 F03 修复只收窄了 request atom 集。随后一个 fresh runtime 完成五个 required exact calls、六轮 `ROUND_PASS`、四个 projection checkpoint 追平且 `host_projection_failures=0`，但 post-run 诊断继续失败：

```text
R03 SMOKE FAIL accepted result evidence envelope is missing
```

同一 durable EventLog 显示 ordinary tool 每次都有 Host `canonical_fact` `TOOL_RESULT_ACCEPTED` 与 Engine `preview` `TOOL_RESULT_ACCEPTED`；前者携带 accepted envelope，后者只是 Engine activity view。脚本的 `result_rows` 仍只按 event type 选择，使 preview 被误送入 shared accepted-result projection。这与 request-row 失败是同一 typed row-selection root cause，继续归属 F03；不增加新产品 finding。

## 8. 修复后独立验证

### 8.1 直接受影响矩阵与静态门槛

Controller 在当前完整 fix tree 上重新执行 accepted plan §13.1 第一组矩阵：

```text
933 passed, 2 skipped, 3 warnings
```

三条 warning 均来自 edgar 依赖弃用提示。其余静态门槛：

```text
python -m pyright dayu/ tests/ utils/
=> 0 errors, 0 warnings, 0 informations

ruff check <全部 R03 changed implementation/test paths>
=> All checks passed!

git diff --check
=> PASS
```

sentinel closure `test_opaque_provenance_round_trips_but_stays_out_of_projection`、`test_same_accepted_result_has_equivalent_consumer_projection` 与 `test_run_input_messages_use_explicit_citation_and_hide_opaque_refs` 为 `3 passed`。旧 safe-arguments repair、`resolved_payload_available`、`json_redaction.py`、Doc product limits 与 oversized skip 的 active source scans 均无生产命中；opaque ref 扫描命中只保留 internal provenance / audit / diagnostic owner，未发现进入 typed LLM business source 的猜测或 fallback。

### 8.2 全量六域回归与 baseline observation

修复后 canonical 六域结果为：

```text
pytest tests/host tests/tools tests/fins tests/runtime tests/engine tests/service -q
=> 4235 passed, 3 skipped, 5 deselected, 2 failed, 3 warnings
```

两个失败仍为：

- `tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response`
- `tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default`

二者在 fresh process 共同隔离运行是 `2 passed`。直接 owner 证据显示前序 `tests/tools/web/test_smoke_web_ci.py` 调用 `utils/smoke_web_ci.py::main` 后以 `configure_root=True` 改写全局 logging state 且未恢复，导致后续顺序敏感；该路径不经过 R03 changed owner，故继续裁决为既有全量顺序污染 observation，不接受为 R03 finding，也不在本 sub-WU 越界修复。

### 8.3 单文件覆盖率

Controller 取得的 production-owner 覆盖率如下，全部达到单文件 `>=80%` 门槛：

| owner file | coverage |
|---|---:|
| `dayu/host/_event_payload.py` | 98% |
| `dayu/host/accepted_result_projection.py` | 96%（完整 Host frozen matrix；当前 fix focused 为 94%） |
| `dayu/host/durable/run_transition.py` | 93% |
| `dayu/host/payload_resolution.py` | 96% |
| `dayu/host/run_input.py` | 90% |
| `dayu/host/tool_call_request.py` | 95% |
| `dayu/host/tool_runtime.py` | 86% |
| `dayu/host/waiting.py` | 89% |
| `dayu/host/evidence.py` | 91% branch coverage |
| `dayu/host/memory.py` | 92% |
| `dayu/host/durable/memory.py` | 82% |
| `dayu/host/compact_pipeline.py` | 84% |
| `dayu/host/compact_material.py` | 83% |
| `dayu/host/tool_trace.py` | 88% |
| `dayu/tools/web/web_tools.py` | 81% |
| `dayu/fins/tools/fins_tools.py` | 80% |
| `dayu/runtime/__init__.py` | 100% |

macOS 下 coverage 预载入 NumPy/Pandas 会破坏 `spawn` pickling identity，因此 Web/Fins coverage run 排除了各 6 个真实子进程用例；这些用例没有被跳过验证，而是在无 instrumentation 的完整文件测试中分别通过：Web `194 passed, 1 skipped`，Fins `65 passed`。这与既有 Host frozen coverage 对 process-spawn 用例的处理一致，不构成产品豁免。

### 8.4 Mandatory real public-run smoke

AgentCodex 在 `workspace/tmp/r03-aggregate-public-smoke-fix-codex-20260715-05` 完成 hard-gate PASS：六轮全部 `ROUND_PASS`，并得到 `requests=5 accepted_results=5 explicit_citations=1`。

Controller 使用独立 root `workspace/tmp/r03-aggregate-public-smoke-controller-20260715-02`，只机械复制真实 `workspace/portfolio/600519` fixture，按同一 public chain 重跑：

```text
R03 SMOKE ROUND_PASS label=doc
R03 SMOKE ROUND_PASS label=web
R03 SMOKE ROUND_PASS label=fins-awaiting
R03 SMOKE ROUND_PASS label=fins-list
R03 SMOKE ROUND_PASS label=fins-read
R03 SMOKE ROUND_PASS label=observation
R03 SMOKE PROJECTION_PASS requests=5 accepted_results=5 explicit_citations=1
R03 SMOKE PASS real Doc/Web/Fins public execution closure
```

Controller 的 `-01` root 因未复制 Fins fixture 而在 awaiting round 报 source missing；保留现场证明该结果来自 Controller 装配输入缺失。补齐与既有 Controller artifact 同源的 fixture 后，`-02` fresh root 完整通过；没有修改产品代码、增加重试、弱化 exact-call prompt 或使用 fake provider。

## 9. Findings 最终状态

| finding | status | owner closure |
|---|---|---|
| `R03-AGG-CV-F01` | `CLOSED` | Compact typed accepted evidence 保留 shared renderer exact text；ordinary material 继续由 generic normalization owner。 |
| `R03-AGG-CV-F02` | `CLOSED` | shared accepted-result projection 区分 inline raw outcome 与 cold descriptor，并继续由 strict descriptor integrity owner fail closed。 |
| `R03-AGG-CV-F03` | `CLOSED` | smoke post-run diagnostics 对 request/awaiting/result 共用 typed `EventClass.CANONICAL_FACT` selection；preview 不再进入 strict accepted-fact resolver。 |

当前没有遗留 accepted aggregate-validation finding。现有 DNS/peer、path containment、symlink、resource budget、atomic/process fencing 与 opaque provenance internal-only 行为均保留；未设计或实现统一 tool authorization framework，未偷带 Issue 142、151、175、177、178。

## 10. 下一入口

下一入口为 AgentMiMo 与 AgentDS 对完整 R03 组合行为执行并发 aggregate deepreview。review 必须覆盖 accepted plan、S1-S3 accepted commits、F01-F03 working-tree fix、Controller validation、真实 public smoke、LLM-facing propagation、安全保留项与 deferred ISSUE 边界。只有 Controller 裁决并关闭 deepreview findings 后，才可形成 R03 accepted local commit；R04 仍未授权。
