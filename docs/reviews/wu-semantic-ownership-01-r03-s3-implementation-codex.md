# WU-SEMANTIC-OWNERSHIP-01 R03-S3 implementation handoff

## 1. 身份与边界

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- gate：同一 WU 的 `R03-S3 implementation`，不是新 WU
- branch：`phaseflow/host-issues-control`
- S2 accepted commit：`4b4696e5`
- 本 slice transition baseline：`44e68550`
- implementation handoff 时 HEAD：`44e68550ed226a3a207a73bd257478ab1bbbdce4`
- 状态：工作区未提交；未 commit、未 push、未进入 S3 code review、未运行 aggregate 外部 smoke
- accepted plan：`docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` §11、§12、§15.1、§16

动机成立。baseline 中 accepted result projection 把 opaque envelope refs 带入共享 projection，并按 `ref_kind` blacklist/guessing 生成业务来源；renderer 和多个消费者又允许 material 缺失 fallback。该路径使 internal provenance、业务 citation 与 LLM-readable source 没有唯一 owner，和 accepted plan 直接一致，不需要改动产品裁决。

## 2. Exact implementation diff

Production（精确 8 个）：

- `dayu/host/accepted_result_projection.py`
- `dayu/host/evidence.py`
- `dayu/host/run_input.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/tool_trace.py`

Tests/smoke：

- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`（新增）
- `utils/smoke_host_public_r03_semantic_ownership.py`（新增）

Docs：

- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-semantic-ownership-01-r03-s3-implementation-codex.md`（本 artifact，新增）

Allowlist 内的 `tests/host/test_tool_trace_queries.py` 本 slice 无需修改，作为 §11.5 regression 执行。以下明确 no-diff 文件经 `git diff --exit-code 44e68550 -- ...` 验证为零差异：

- `dayu/host/compaction.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/domain/tool_models.py`

control doc、accepted plan、design truth、prior artifacts、Issue 177/178、authorization owner 均无本 slice diff。

## 3. Owner 与 old-to-new call path

### 3.1 Accepted evidence owner

旧路径：

```text
TOOL_RESULT_ACCEPTED envelope source_refs/locator_refs
  -> AcceptedToolResultProjection.source_locator_refs
  -> ref_kind blacklist / unknown kind guessing
  -> shared LLM business source
```

新路径：

```text
TOOL_RESULT_ACCEPTED digest-checked payload
  -> accepted evidence envelope（identity/request link/internal provenance）
  -> read_event_by_id(request link)
  -> strict tool_call_request_atoms（exact query/arguments/digests）
  -> raw_outcome exact codec path
       kind == completed
       -> result object / ok is True
       -> value object
       -> citation object
  -> canonical_json_dumps(完整 citation object)
  -> AcceptedToolEvidenceLLMMaterial(query/source/result)
```

`OpaqueEvidenceRef` 仍由 `AcceptedEvidenceEnvelope` 产生、校验、序列化并在 EventLog/audit/internal provenance round-trip 中保留；`AcceptedToolResultProjection` 不再携带它，也不再存在 `_INTERNAL_SOURCE_REF_KINDS`、`_READABLE_SOURCE_SEPARATOR` 或 `_readable_ref_text`。Host 不 import Fins，不枚举 citation key，不新增 `BusinessSource`。

### 3.2 Renderer 与四消费者

`render_accepted_tool_evidence_for_llm` 现在只接受非 optional `AcceptedToolEvidenceLLMMaterial`。唯一四行文本继续由该 owner 产生：工具名称、查询语义、业务来源、工具结果。整体 material fallback constant/branch 已删除。

四消费者在各自 owner boundary 收窄 typed material：

- RunInput：memory EventLog projection 与 fallback material block 缺 material 均抛 `HostDurableError`；不局部 catch。
- Memory：durable projection view 和 selected evidence renderer 缺 material 均抛 `HostDurableError`；不 skip snapshot item。
- Compact：pre-dispatch material block 与 compact pipeline message projection 缺 material均抛 `HostDurableError`；不发布局部 compact material。
- LLM-ready Tool Trace：accepted result summary 缺 material/raw result 时抛 `HostDurableError`；不发布 limited signal/hot/cold summary。

无 explicit citation 的唯一业务文本为 `该工具结果未提供业务来源。`。缺失、`citaiton` 拼错或 citation 非 object 均走同一语义；不会回退到 opaque refs、URL/path、event id、digest 或其它字段。

### 3.3 Tool Trace request owner

`TOOL_CALL_REQUESTED` 不再使用 placeholder 或 event payload 松解析：

```text
ProjectionEventView
  -> read_event_by_id(event.event_id)
  -> require CANONICAL_FACT / TOOL_CALL_REQUESTED
  -> tool_call_request_atoms(transaction, row)
  -> inline/descriptor storage + digest strict validation
  -> bounded canonical exact args/query
  -> hot row + cold JSONL readable summary
```

missing row、wrong event type/class、storage conflict、descriptor/digest corruption 在 summary 发布前 fail closed；测试同时断言 hot row 与 cold JSONL 均没有局部输出。arguments descriptor ref/digest 只留在 internal row，不进入 readable summary。

## 4. §11.3 八项 closure

1. `AcceptedToolResultProjection` 删除 opaque locator field；shared projection 只携带 exact query/result/explicit citation material 与 internal diagnostic payload refs。
2. `_source_projection` 直接消费 digest-checked `raw_outcome`；`_explicit_citation` 只识别 accepted outcome codec 的精确 JSONPath，并 canonical-render 整个 object。
3. unknown、拼错和 internal `ref_kind` 不再产生任何业务来源 guessing；旧 blacklist/helper 完全删除。
4. `evidence.py` 删除整体 material fallback，renderer 参数改为 required typed material；source unavailable 收敛为唯一中性文案；无消费者的 query unavailable/“参数未安全展开”常量与 export 也已删除，不保留兼容符号。
5. Memory 与 durable Memory 在 canonical accepted result owner boundary 严格拒绝缺 material。
6. Tool Trace result 只映射 shared projection 的 `business_source_text/state`；opaque provenance 与 diagnostic reason 不进入业务 source 文本。
7. RunInput、CompactMaterial、CompactPipeline 均先收窄 non-null typed material，再调用唯一 renderer；没有 skip/fallback/局部 catch。
8. Tool Trace request 通过真实 EventLog row 与 strict request atom owner 恢复 bounded exact args/query；inline/descriptor 与 corruption 路径闭环。

## 5. Propagation、negative 与 corruption evidence

| case | owner-level evidence | result |
| --- | --- | --- |
| real citation fixture | `accepted_tool_outcome_json(ToolCompletedOutcome(ToolResultSuccess(...)))` | 使用真实 codec shape，不手写漂移 fixture |
| unknown citation member | citation 含 `unknown_future_member` nested object | RunInput、Memory、Compact、Tool Trace canonical text 完全相同，未知 member 未被 Host 筛除 |
| no citation | completed success value 无 `citation` | 唯一中性 unavailable 文案 |
| misspelled citation | `citaiton` | 同一 unavailable 文案，无 ref fallback |
| wrong citation type | citation 为 string | 同一 unavailable 文案，无 loose parsing |
| opaque provenance | `fliing-typo`、`eventlog`、`eventlogg` sentinel | envelope source/locator refs round-trip 保留；四消费者实际文本均不可见 |
| canonical result 缺 typed material | 移除 raw outcome/material | RunInput、Memory、Compact、Tool Trace 分别在 owner boundary 抛 `HostDurableError` |
| request row missing | Tool Trace projection event 找不到 EventLog row | fail closed；无 hot/cold output |
| request wrong type/class | row 不是 canonical `TOOL_CALL_REQUESTED` | fail closed；无 hot/cold output |
| inline request | canonical inline args/query | 展示 bounded exact canonical arguments/query |
| descriptor request | descriptor-backed large args | 先校验 storage/digest，再展示 bounded exact arguments；ref/digest 不进入 readable summary |
| storage conflict | payload storage 与 canonical row 不一致 | fail closed；无 hot/cold output |
| digest mismatch | request argument/descriptor digest 漂移 | fail closed；无 hot/cold output |
| evidence strict decoder negatives | non-object、extra field、required/optional string、bool、list 错误 | owner decoder 全部 `ValueError`；该最小矩阵把 evidence branch gate 提升到 91% |

### 5.1 Controller independent-validation finding closure

| finding | root evidence | owner-level closure |
| --- | --- | --- |
| `R03-S3-CV-F01` | `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 只有定义/export，strict request atom 后没有 query fallback owner | 从 `evidence.py` 删除常量与 `__all__` export；active production/tests/smoke source scan 零命中，无 compatibility alias；不可修改的历史 plan/review 记录仍如实提及旧符号 |
| `R03-S3-CV-F02` | `list_documents` result 没有 citation；同一 Fins storage/source owner 的 `get_document_sections` 明确返回 citation | 保留 `get_document_sections(ticker, document_id)` 作为 explicit citation producer；其前增加 F05 要求的真实 grounding round，未回退为无 citation 的 list result；Fins owner files no-diff |
| `R03-S3-CV-F03` | 初版 smoke 只重算 observed digest，未比对 typed expected arguments，也未读取 `TOOL_AWAITING` | 从 `SmokeArgs/FinsAwaitingTool` 构造五个 typed expected calls；strict atoms 必须 exactly-once、arguments exact equality、normalized/payload digest 同源；digest-checked `TOOL_AWAITING` 必须存在、严格链接 selected awaiting request，任何 arguments/digest 副本 fail closed |
| `R03-S3-CV-F04` | smoke 不执行 cleanup，但初版按 flag 输出 `WORKSPACE_KEPT=false` | 输出始终为 `WORKSPACE_KEPT true ... cleanup=never`；flag 仅标记 `caller_requested=true/false`，未新增 destructive cleanup |
| `R03-S3-CV-F05` | Fins tool schema 与 base tools prompt 均规定 `document_id` 必须先由同 ticker `list_documents.documents[].document_id` 产生；直接要求模型调用 read 违反 producer-owned LLM contract | 新增只暴露 `list_documents` 的 `fins-list` public round，exact args 为 `{"ticker": fins_ticker}`；随后 `fins-read` 只暴露 citation producer，并自足要求仅在上一轮同 ticker 确实返回调用方 ID 时按 exact ticker/document_id 调用，否则 stop/fail、禁止猜测；Fins/config owner 均 no-diff |

## 6. 窄 public smoke 与 guard

新增脚本只用 current production assembly：`ConfigLoader -> ToolsDiscovery -> ScenePrepare/Service assembly -> open_host -> ensure_session -> submit_followup`。它使用 configured real runner、真实 Doc/Web/Fins ToolDefinition 与 production Fins wait poller；不使用 fake/scripted runner/tool，不手工写 wait result。public watch 只观察 public terminal event，不写 Host truth。

所有 public runs 结束并关闭 Host 后，脚本才打开同源 durable store，明确标为 **internal diagnostic read**，用于 catch-up/read Memory、Compact、Tool Trace、strict request atoms、`TOOL_AWAITING` payload 与 final runner-call projection；该 read 不是 public product API，不接受/恢复工具结果，也不参与执行链。

纯 assembly/secret-output guard 覆盖：

- CLI 参数为 typed explicit inputs；
- configured real tool definitions、production wait poller 与 local Engine worker 装配；
- 固定 `read_file`、`search_web`、selected Fins awaiting、`list_documents` grounding、`get_document_sections` citation read 与 no-tool observation 轮次；grounding 只传 exact ticker，read prompt 自足携带前置验证条件与 exact ticker/document_id；
- 三个 awaiting variant 分别从 `SmokeArgs` 构造 exact arguments；五个 required request atoms 均要求 exactly-once、canonical arguments 与 typed expected 完全相同，且 normalized/payload digest 与 exact arguments 同源；
- `TOOL_AWAITING` 使用 `event_payload_object` 读取 digest-checked payload，要求 strict request link 指向 selected awaiting row，并拒绝 `accepted_arguments`、`accepted_arguments_source_digest`、`normalized_arguments_digest` 及任意其它 arguments/digest 副本；
- public execution command chain 与 internal diagnostic read 分离；
- failure text 对 `api_key/authorization/bearer/token/secret/cookie` 脱敏，并限制为 240 chars；
- 禁止 stdout 输出 headers、完整 prompt、完整 raw outcome、opaque sentinel 或 credential。
- 脚本从不删除 Host/runtime artifacts；stdout 始终如实输出 `WORKSPACE_KEPT true`，CLI flag 只记录调用方是否显式要求保留。

Opaque sentinel 的直接证据边界：§11.4 中注入 sentinel 的 owner tests 才证明 envelope opaque refs 实际 round-trip 存在且 RunInput、Memory、Compact、Tool Trace 四消费者不可见。real smoke 没有注入这些 internal refs；其 absence assertion 只能防止可见输出意外包含 sentinel，**不得**表述为 real smoke 证明 internal refs 实际存在。

本 slice **没有运行、没有宣称** §12 aggregate 真实外部 public-run smoke PASS。这里只交付可实际运行脚本和 deterministic assembly/secret guard；aggregate Web/network/provider/Fins 环境 gate 留给后续 Controller aggregate validation。

## 7. Validation commands 与结果

### 7.1 §11.5 exact suites

```bash
source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_public_compact_smoke.py tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py -q
```

结果：F05 最终重跑为 `354 passed, 1 skipped, 3 warnings in 3.71s`。skip 是既有 opt-in real compactor smoke；新 R03 aggregate 外部 smoke 未运行。

```bash
source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -k 'source or ref or projection or memory or compact or trace or citation' -q
```

结果：F05 最终重跑为 `261 passed, 63 deselected in 1.91s`。

### 7.2 补充受影响回归

```bash
source .venv/bin/activate && pytest tests/host/test_compact_pipeline.py tests/host/test_memory_repair.py -q
```

结果：`21 passed in 0.31s`。

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py -q
```

结果：F05 最终重跑为 `17 passed in 1.07s`（3 条第三方 deprecation warnings）。round label/tool-set 顺序、五个 required calls、三个 awaiting variant 的 expected exact args、strict atom digest helper、TOOL_AWAITING no-copy/link helper 与 workspace retention truth 均有直接 unit guard。

```bash
source .venv/bin/activate && pytest tests/host -q
```

结果：`1973 passed, 1 skipped, 5 deselected in 60.33s`。

### 7.3 单文件 coverage

每行均用对应 owner tests 和独立 `--cov=<module> --cov-report=term-missing -q` 运行；没有用 package aggregate 代替。

| production module | result | missing lines |
| --- | ---: | --- |
| `dayu.host.accepted_result_projection` | 93%（273 stmts / 18 miss）；`--cov-branch` 91% | `167, 277-278, 301, 362-363, 412, 472, 666-669, 685, 715, 728, 761-763` |
| `dayu.host.evidence` | 94%（200 stmts / 12 miss）；`--cov-branch` **91%** | `235, 270, 275, 277, 280, 283, 294-295, 499, 598, 600, 628` |
| `dayu.host.run_input` | 89%（1252 stmts / 141 miss） | `456, 708, 877, 879, 967, 1069, 1157, 1169, 1212, 1310-1311, 1389, 1425, 1592-1593, 1632, 1804, 2138, 2140, 2142, 2144, 2146, 2175, 2177, 2179, 2193, 2206, 2495, 2539, 2547-2550, 2553, 2637, 2689, 2692, 2703, 2720, 2825, 2887, 2895-2896, 2926, 2936-2943, 2965, 2970, 2972, 2983, 2998, 3000, 3002, 3004, 3006, 3011, 3021-3025, 3036, 3078, 3255, 3274, 3276, 3299, 3307-3308, 3332, 3344-3347, 3361, 3374, 3392, 3418-3419, 3435-3439, 3451-3455, 3476, 3523, 3526, 3543, 3549-3550, 3554, 3570, 3599-3606, 3626, 3641, 3644, 3680, 3682, 3684, 3686, 3704, 3706, 3708, 3710, 3712, 3746, 3749, 3775, 3778, 3890, 3913-3915, 3984-3986, 4132-4134, 4338, 4422, 4424, 4504, 4507, 4519, 4544, 4713, 4734, 4751, 4766` |
| `dayu.host.memory` | 91%（925 stmts / 84 miss） | `236, 265, 268, 270, 293-296, 336, 341, 385, 389, 426, 430, 472, 475, 519, 521, 544, 578, 582, 617, 620, 624, 701, 704, 734-739, 852, 859, 866, 870, 872, 920, 931, 980, 992, 995, 997, 1005, 1063, 1189, 1192, 1202, 1264, 1379-1381, 1411-1412, 1443, 1572-1573, 1615, 1617, 1619, 1621, 1977, 1997, 2007, 2163, 2892, 2994, 3006, 3018, 3030, 3080, 3093, 3108, 3127, 3146, 3162, 3177, 3180, 3196, 3212, 3228-3231` |
| `dayu.host.durable.memory` | 85%（351 stmts / 52 miss） | `167, 195, 206, 322, 427, 518, 582, 701, 730, 760-773, 793-823, 840-855, 905, 1010, 1222-1225, 1436-1437, 1456-1464, 1558, 1569-1576, 1595-1596, 1607-1611` |
| `dayu.host.compact_material` | 85%（916 stmts / 140 miss） | `228, 230, 233, 240, 243, 266, 275, 277, 291, 293, 297, 307, 341, 343, 345, 347, 349, 404, 450, 582, 685, 687, 714, 716, 719, 722-727, 741, 984, 994, 1055, 1058, 1080-1083, 1104-1107, 1128-1131, 1163, 1218, 1223, 1237, 1264, 1266, 1269, 1284, 1292, 1321, 1396-1407, 1459, 1581-1590, 1602, 1604, 1644, 1646, 1648, 1652, 1654, 1656, 1707, 1721, 1738, 1777-1779, 1836, 1890, 1951, 1958, 1966, 2010, 2036-2037, 2055-2056, 2149-2150, 2221, 2509, 2553, 2556, 2560, 2564, 2659, 2677, 2708, 2747, 2806, 2808, 2810, 2868, 2916, 2919, 2934, 2937, 2952, 2955, 2974, 2976, 2978, 2991-2992, 3032, 3049, 3063, 3079, 3093-3101, 3190, 3221, 3223` |
| `dayu.host.compact_pipeline` | 93%（251 stmts / 18 miss） | `413, 415, 417, 498, 590, 704-729, 791, 803-804, 923, 1059, 1109, 1119-1124` |
| `dayu.host.tool_trace` | 88%（756 stmts / 92 miss） | `257, 383, 438, 456, 522, 547, 573, 576, 768, 825-835, 1091, 1105, 1189, 1258, 1277, 1448, 1451, 1486, 1499, 1510, 1514, 1532, 1586-1607, 1626, 1631, 1634, 1642, 1651, 1669, 1675, 1694, 1701, 1707-1711, 1717, 1747, 1759, 1772, 1870, 1875, 1880, 1888, 1903, 1908, 1944, 1952, 1956, 1974, 1991, 2014, 2034, 2067, 2081, 2083, 2118, 2160, 2232, 2254, 2257-2258, 2260, 2276, 2290, 2292` |

关键 branch gate 的完整重跑命令：

```bash
source .venv/bin/activate && COVERAGE_FILE=/tmp/r03-s3-cv-evidence.coverage pytest tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py --cov=dayu.host.evidence --cov-branch --cov-report=term-missing -q
```

结果：`194 passed in 1.96s`；`dayu/host/evidence.py: Stmts 200, Miss 12, Branch 52, BrPart 10, Cover 91%`。本结果满足 §11.5 的 renderer/source branch `>=90%`，未用总 line coverage 或 residual 豁免代替。

### 7.4 Static、source 与 diff gates

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
source .venv/bin/activate && python -m ruff check dayu/host/accepted_result_projection.py dayu/host/evidence.py dayu/host/run_input.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_pipeline.py dayu/host/tool_trace.py tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py utils/smoke_host_public_r03_semantic_ownership.py
```

结果：`All checks passed!`

执行 accepted plan §13.5 三组 `rg` propagation scans：

- 五个 production consumer 文件中 `OpaqueEvidenceRef` 零命中；`source_refs/locator_refs/ref_kind/ref_id` 命中均为既有 Memory/Compact internal canonical provenance、空 `PromptLocalProvenanceEntry.source_locator_refs=()` 或 Tool Trace diagnostic ref parser，不进入 accepted source material。
- id/ref/digest scan 命中均为 EventLog identity、payload resolution、artifact/digest validation、memory cursor 或 internal Tool Trace row；人工核对 `source_text`、compact `source_note`、LLM-ready Tool Trace business source 只取 typed projection。
- 旧三条 fallback/placeholder 文案 scan 零命中。
- `_INTERNAL_SOURCE_REF_KINDS|_READABLE_SOURCE_SEPARATOR|_readable_ref_text` 在五个 shared/consumer production 文件中零命中。
- §11.4 injected sentinel owner tests 读取实际 RunInput message、Memory snapshot、compactor material 与 trace summary，证明 envelope 中实际存在的 `opaque-should-never-reach-llm`、`event-typo-should-never-reach-llm` 在四消费者中均不可见。real smoke 不承担“internal refs 实际存在”的证明。
- `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT|参数未安全展开` 在 `dayu tests utils` active source scan 零命中；没有 dead fallback export 或 compatibility constant。不可修改的历史 plan/review artifacts 中仍有旧事实记录，不将历史文本误报为 active consumer。
- R03 smoke/assembly 中 `fins-list -> fins-read` 顺序、两个 exact Fins tool sets、同 ticker/id 条件式 prompt 与五个 required-call definitions 均有正向 source/assembly guard；`WORKSPACE_KEPT false` scan 零命中，retention 输出与 non-destructive 行为一致。

```bash
rg -l 'AgentRunRequest|SystemMessage|UserMessage|ToolFunctionSchema|ToolDefinition' dayu tests utils --glob '*.py' | sort
```

结果：114 个既有 constructor candidates，数量和 accepted plan §8.4 baseline 相同；新增 R03 script/test 没有新建另一套 message/schema constructor。

```bash
git diff --check
git diff --exit-code 44e68550 -- dayu/host/compaction.py dayu/host/durable/tool_trace.py dayu/fins/tools/read_runtime.py dayu/fins/domain/tool_models.py
```

结果：均 exit 0，无 whitespace error，四个 no-diff owner 保持不变。coverage 数据文件已清理，不在交付 diff 中。

## 8. README decision

- `dayu/host/README.md`：已按触发规则更新当前稳定事实，删除 Memory material fallback 描述，改为 exact request atom、strict corruption、explicit citation 与 internal provenance 分离；不写 WU 流程状态。
- `tests/README.md`：已记录当前 accepted projection/source propagation/Tool Trace corruption tests，以及 R03 narrow smoke assembly/secret guard；保留 R01 既有段落。
- root、`dayu/README.md`、Engine/Config/Fins README：职责或稳定契约没有本 slice 变化，no-diff。

## 9. Security retained

- opaque refs、EventLog ids、payload/artifact refs、digest、cursor 与 wait/poll lifecycle 不进入四消费者的业务来源文本。
- exact arguments 只来自 strict canonical request atom；本 slice 不新增 credential guessing、blacklist、redaction normalization 或兼容分支。
- producer citation 机械显示完整 object，但只有精确 typed success path 可进入；Host 不解释 Fins domain。
- public smoke stdout 只输出 bounded count/PASS 或脱敏失败摘要；不输出 provider secret、headers、完整 prompt/result payload或 opaque refs。
- no Host import Fins；no `BusinessSource`；no `Any/object/getattr/hasattr/type-ignore` 绕过。

## 10. Deferred boundaries 与 stop conditions

按 slice 裁决明确 deferred，且不宣称完成：

- §12 aggregate 真实 Web/provider/Fins public-run smoke：脚本已可运行，但本 slice 不执行、不标 PASS，由 Controller aggregate validation 提供/确认外部环境。
- Issue 177、Issue 178、统一 authorization、aggregate 外部 smoke gate：均不在本 slice。
- S3 code review、deepreview、commit、push：均未进入。

§16 stop conditions 检查结果：没有发现实际 owner 与 Controller 裁决冲突；不需要 Host import Fins、发明 `BusinessSource`、解析 arbitrary citation/ref kind、修改 Engine contract、引入 compatibility schema/normalization、修改 no-diff owner 或降低 corruption equality。implementation 可以停在 handoff，等待 Controller validation。
