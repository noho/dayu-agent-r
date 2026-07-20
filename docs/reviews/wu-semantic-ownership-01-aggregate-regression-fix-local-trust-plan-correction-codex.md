# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix local-trust plan correction（AgentCodex）

## 1. Gate identity / disposition

- 日期：`2026-07-19`。
- 执行者：本 gate 指定的 AgentCodex plan author；未作为 phaseflow Controller 行动，未启动或派发 subagent。
- umbrella：`WU-SEMANTIC-OWNERSHIP-01`；这是同一 umbrella 的 plan-correction gate，不是新 WU、feature、issue、sub-WU 或 implementation slice。
- 状态：`PLAN_ONLY_CORRECTION_COMPLETE / DUAL_PLAN_REVIEW_PENDING / IMPLEMENTATION_NOT_AUTHORIZED`。
- 用户裁决：本地 Config 与 Host SQLite / EventLog 属于同一受信任产品域；Host internal EventLog 持久化 resolved provider headers / API key 是 exact effective execution truth，不构成新增当前产品泄露面。Tool Trace、audit、public / LLM-facing projection、operator logs、git diff 与 review artifacts 仍必须零明文。
- Finding disposition：`S1-SEC-F01=CLOSED_AS_NO_CODE_BLOCKER`。当前没有发现真实 projection leak，故没有 production repair；只修正 design truth、三-slice aggregate plan 与 Slice 1 verification contract。
- 本 artifact 不记录任何 configured secret value、secret ref 名称或命中正文。

## 2. Strict full-read ledger

首先严格按用户指定顺序完整读取前九项；随后完整读取裁决、prior evidence / adjudication、两路 corrected reviews、accepted plan与commit validation、Slice 1 authorization / implementation artifact及五次 stop。表中 Host/UI design与aggregate plan记录 correction entry 的读取版本；其它文件未由本 gate 修改，SHA 是本次读取版本。

| 顺序 | 完整读取文件 | 读取行数 | 读取版本 SHA-256 |
| ---: | --- | ---: | --- |
| 1 | `AGENTS.md` | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| 2 | `docs/host/issues-implementation-control.md` | 2313 | `4b6488ff4fc9004b8373af5f785ca503d86fd884c6904632d9b1367aef64bcbb` |
| 3 | `docs/phaseflow-umbrella-optimization-control.md` | 302 | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
| 4 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| 5 | `docs/host/design.md` | 3696 | `276d35e15edfbf3efb1b9bff8ff4abbb38de48e075050379218fd19df90f43e9` |
| 6 | `docs/engine/design.md` | 553 | `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31` |
| 7 | `docs/tool/design.md` | 134 | `ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c` |
| 8 | `docs/fins/design.md` | 123 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| 9 | `docs/ui/design.md` | 111 | `5a19c829151777b1d9f3c69f1a9a305396f75c8e73eb5ea31577663c55bed973` |
| 10 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-user-decision-controller-record.md` | 48 | `4a75899fbdb8244d93f1633b0be3f36e65d2ae211a3211f57f326289f6c3f12b` |
| 11 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-evidence.md` | 79 | `2f3fc19e4cdab8b93fd2e4e8b09008169e95d0ece4f7183431d3bd643b574bea` |
| 12 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-adjudication.md` | 134 | `ff64706df0ba9e814f7eeef4f836ad9f0deebdc374b892f59ec6ceff76e0eec0` |
| 13 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-designtruth-review-mimo.md` | 454 | `fd1897411497b039f05cda6891d547c0d09a2130659e479758d3a3f2581c674f` |
| 14 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-designtruth-review-ds.md` | 522 | `0aef51d2a9eef88eb98f650b7a5d87c66d3d3257a78e4da7e11828c528088d84` |
| 15 | `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`（accepted entry） | 640 | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` |
| 16 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md` | 13 | `cad213bdb7b02abf9cf4a876a0925e4318df8908cdb1f0bb17090155d3c67114` |
| 17 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md` | 42 | `ebb6a9dc92cc4ab24961228891f97442444f4c98228e2693c43aba08328dddcd` |
| 18 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md` | 1245 | `05800914dfd66912c05ca7eef4d8cacfab1a506572b161c4ce39362a4443b32a` |
| 19 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-stop-controller-adjudication.md` | 38 | `db221c9ac75fbb1029ea1ad27ead96e36fe9dd791a4cb81d4f76a90467453762` |
| 20 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-second-stop-controller-adjudication.md` | 45 | `7174396e8c923e9e7a142b79f34815358ed2b48f58b8aa0e2a6dbfc0b1cb8b66` |
| 21 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-third-stop-controller-adjudication.md` | 30 | `52524fdfd0e819a5c311e2a967f84667b29a1c66c57f791234e1f794ca7fe418` |
| 22 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fourth-stop-controller-adjudication.md` | 30 | `ac5cf521d2f76a73fa42132a2b7374b47b42d91273d5da1458a9788d20e6c88d` |
| 23 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md` | 32 | `220bf5f98fe3b1a131c08599aeef171b38305993d16f26bc7be306151492e4c8` |

## 3. 第一性原理与 design disposition

旧 blocker 把“内部 durable state 有 configured value”直接等同于“新增泄露面”，动机被用户产品裁决否定。正确 owner chain 是：ConfigLoader产出typed config；Service / execution environment解析secret并构造resolved typed `RunnerSpec`；Host admission冻结exact effective execution canonical fact；dispatch / retry / replay / recovery恢复同一typed truth；所有public、LLM-facing、audit、trace与log surface由各自projection owner选择安全字段。

本 gate 对 design 的处理：

- `docs/host/design.md`：删除“Host 不接收 API key明文”和“EventLog 不能包含headers / API key”的冲突承诺；明确Service仍解析secret、Host可接收并内部durable冻结resolved typed `RunnerSpec`、Host SQLite / EventLog是trusted store；同时把Tool Trace、audit、HostEvent / read API、outbox、memory / compact / evidence、runner-call observation与operator log的零明文边界写回各自projection contract。
- `docs/ui/design.md`：删除“运行时secret不能进入Host durable state”的冲突承诺；明确CLI init仍只管理现有secret source storage，不新增第二套init secret store，不扩张到CLI init改造；运行时Service解析后，Host internal durable copy被允许，但UI / public / LLM / trace / audit / log仍为零。
- `docs/engine/design.md`：完整核对后不修改。它已把Engine执行所需`RunnerSpec`与LLM-facing runner input observation区分开，并明确observation不包含provider headers / Authorization / API key；没有需要本裁决修正的冲突。
- 未引入Host-safe / Engine-only split、header descriptor、secret resolver callback、secret manager或统一tool authorization framework；未进入Issues 142、151、175、177、178。

## 4. Direct production code evidence

### 4.1 Trusted internal effective-execution owner path

- `dayu/service/host_assembly.py:1702` 的 `_runner_spec_from_model` 构造typed `RunnerSpec`；`dayu/service/host_assembly.py:1736` 的 `_render_headers` 从当前environment解析configured value并替换header template。解析owner仍是Service。
- `dayu/host/admission.py:3517` 的 `_resolve_followup_effective_facts` 选择per-run override或opener baseline，并在 `:3552` 调用effective execution serializer冻结完整typed config。
- `dayu/host/_execution_config_projection.py:54` 的 `effective_execution_config_json` 生成canonical snapshot；`:156` 的 `runner_spec_json` 在 `headers` 中排序保存完整mapping。
- `dayu/host/_execution_config_projection.py:93` 的 `effective_execution_snapshot_from_json` 与 `:184` 的 `runner_spec_from_json`恢复相同typed `RunnerSpec`。`dayu/host/admission.py:3696` 的replay path及 `dayu/host/dispatch.py:4667` 的dispatch snapshot path消费该恢复owner。
- 因此real smoke SQLite中的exact match不是fixture旁路；它与production admission / dispatch / replay同源，并按用户裁决分类为trusted internal truth。

### 4.2 Tool Trace owner

- `dayu/host/tool_trace.py:204` 的 `_CANONICAL_EVENT_TYPES` 是显式事件白名单，不包含`USER_INPUT_ACCEPTED`；Host admission event set没有被该tuple整体展开。
- `dayu/host/tool_trace.py:397` 的 `event_filter`只注册该canonical白名单、diagnostic白名单与projection-signal白名单。
- `dayu/host/tool_trace.py:579` 的 `_extract_canonical_trace`只读取命名tool / ref / digest / signal字段，不复制`effective_execution_config`或raw canonical payload。
- 结论：当前没有configured secret进入Tool Trace的直接路径；现有测试覆盖一般raw payload不进入trace，但缺少secret-bearing `USER_INPUT_ACCEPTED` owner-level negative case。

### 4.3 Audit owner

- `dayu/host/audit.py:331` 的audit filter消费canonical facts，因此必须检查builder而不能仅凭event filter推断安全。
- `dayu/host/audit.py:411` 的 `build_audit_json_line` 构造固定字段集合；`:461-462`只保存`payload_ref` / `payload_digest`，没有复制`event.payload`、`payload_json`或effective execution config。
- 结论：当前没有configured secret进入audit line的直接路径；`tests/host/test_audit_sink.py`已有exact key contract，但缺少source payload含resolved header sentinel的negative case。

### 4.4 Public / LLM-facing / log owners

- `dayu/host/read_api.py:875` 的 `_host_event_from_row` 对非terminal row只构造typed progress DTO；`:1063` 的 `_activity_from_row`是显式event-type allowlist，`USER_INPUT_ACCEPTED`不产生activity，也不复制raw payload。
- `dayu/host/run_input.py:856` 的 current-run fact loader读取`USER_INPUT_ACCEPTED`后，在 `:907-915` 只选择`display_text`、`system_prompt`与`operation_kind`；不把effective execution config写入LLM messages。
- `dayu/host/memory.py:1215` 的memory projection对user input调用`:1625`的selected-user owner；`:2958` 的 `_user_visible_text`只读取`display_text`。`dayu/host/compact_material.py:2463` 的user-input delta owner同样只在`:2484`读取`display_text`。
- `tests/host/test_logging.py:44-148` 已验证prompt / authorization claim不进入Host logs；`tests/engine/test_agent_phase2.py:1336`起与`tests/engine/runners/openai/test_diagnostic_payload.py`已有Engine exception / diagnostic secret redaction cases。source callsite inspection与fresh output scan均未发现resolved header进入logger，但当前Host log tests尚未直接使用resolved runner header sentinel。
- 关键分类：`AgentRunRequest.runner_spec.headers`是Engine HTTP执行输入，保留resolved value是正确行为；需要为零的是`messages`、memory / compact / evidence、runner-call observation、HostEvent、audit、trace与日志，不能扫描整个execution request后误报。

## 5. Read-only configured-secret scan

扫描从current `dayu/config/models.json` 的typed `api_key_ref`集合解析当前environment中非空values；过程只在内存处理value bytes，输出计数与semantic分类，不输出value、ref名称、header名称或正文。扫描根是全部 `workspace/tmp/wu-semantic-ownership-01-ar-fix*` outputs，同时扫描aggregate review artifacts与`git diff --binary HEAD`。

Pre-artifact correction scan：

```text
configured_secret_value_count=5
scan_root_count=8
trusted_host_internal_match_count=3
trusted_host_internal_matched_path_count=1
trusted_logical_matching_rows=2
trusted_logical_user_input_rows=2
trusted_logical_payload_match_count=2
trusted_effective_runner_headers_match_count=2
trusted_logical_other_match_count=0
tool_trace_match_count=0
tool_trace_matched_path_count=0
audit_match_count=0
audit_matched_path_count=0
log_match_count=0
log_matched_path_count=0
other_output_match_count=0
other_output_matched_path_count=0
review_surface_match_count=0
git_diff_surface_match_count=0
```

解释：物理SQLite file的3次occurrence对应2条logical current canonical facts；两条都精确属于`USER_INPUT_ACCEPTED`的effective runner headers，logical other为0。这个唯一非零surface按用户裁决接受。Tool Trace、audit、log、其它output、review与diff全部为零，因此没有基于直接证据成立的projection leak。

## 6. Aggregate plan correction

- 保持原有Slice 1 -> Slice 2 -> Slice 3，未新增slice、sub-WU或并行implementation路线。
- findings matrix新增`S1-SEC-F01=CLOSED_AS_NO_CODE_BLOCKER`，明确internal match accepted、zero-required projections继续fail closed。
- Slice 1 production allowlist继续为空；现有三个test delta保持原样，新增五个精确owner-test allowlist path：`test_audit_sink.py`、`test_tool_trace_projection.py`、`test_host_activity_event_projection.py`、`test_run_input_builder.py`、`test_logging.py`。它们只允许增加synthetic sentinel negative contract。
- Slice 1 test contract先证明internal EventLog与Engine execution `RunnerSpec.headers`保留sentinel，再分别证明Tool Trace、audit、HostEvent、LLM-facing messages / memory / compact / runner-call observation与logs为零；禁止header字段名黑名单、下游repair、mock-only bypass。
- configured-secret gate改为semantic classification：Config / Host internal exact effective-execution owner可以非零；Tool Trace、audit、public / LLM、log、其它output、diff、review必须分surface为零。SQLite物理命中必须做logical event / JSON path核对，不能合并计数后waive。
- 当前没有真实projection leak，因此没有扩充production allowlist。若owner sentinel test以后暴露真实leak，必须在同一umbrella、同一三-slice plan内停止并把修复限制到唯一source projection owner及其直接test；不得新增slice、字段名黑名单或下游repair。

## 7. Exact changed paths / hashes

| Path | Entry SHA-256 | Correction SHA-256 | Disposition |
| --- | --- | --- | --- |
| `docs/host/design.md` | `276d35e15edfbf3efb1b9bff8ff4abbb38de48e075050379218fd19df90f43e9` | `2be90cc2e107ce14fd5ee594c85e2a223217b9d6689b2d4a0cafba2adf3ec628` | modified，local trust / projection boundary writeback |
| `docs/ui/design.md` | `5a19c829151777b1d9f3c69f1a9a305396f75c8e73eb5ea31577663c55bed973` | `ed25d5d4577864cbf7ca6860aad043607921bd7db4f72cffb876c871fb99b4b7` | modified，runtime durable trust writeback；CLI init workflow不扩张 |
| `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714` | `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252` | modified，三slice local-trust correction |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-codex.md` | `ABSENT` | self hash由最终handoff在本文件不再修改后报告 | added，本 gate唯一新artifact |

`docs/engine/design.md`保持 `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31`，未修改。产品代码、测试、README、workflow、control与其它review artifacts均未由本 gate修改。

三个protected test delta在design / plan writeback后的SHA仍与entry一致：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
```

## 8. Final validation / stop

- `git diff --check`：exit `0`，无输出。
- final configured-secret semantic scan：exit `0`，结果与§5完全一致；trusted internal仍为物理3次 / 1 path、logical 2 rows且全部是exact effective runner headers、logical other为0；Tool Trace、audit、log、其它output、review与git diff仍全部为0。
- `git diff --cached --name-status`：无输出，staged tree为空。
- gate-owned `git status --short`精确为 `M docs/host/design.md`、`M docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`、`M docs/ui/design.md`与 `?? docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-codex.md`；其余status均为entry已存在的Controller / user-owned control、三测试delta与review artifacts，本 gate未修改或清理它们。
- 三个protected tests的final SHA-256仍精确为§7记录值；Engine design SHA也保持不变。
- 未运行pytest、pyright、Ruff、build或implementation smoke：本 gate明确是plan-only correction，且用户要求保护当前三个test delta并等待dual plan review。
- 本节更新后只再次执行只读diff-check、secret scan、staged/status/hash确认，不再修改文件；随后停止。next entry只能是Controller组织的AgentMiMo / AgentDS dual full plan review。
