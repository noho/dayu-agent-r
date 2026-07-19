# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Local-Trust Plan Review（AgentDS）

## 1. Gate identity

- 执行者：AgentDS（corrected-plan review，不委派 subagent，不修改代码/测试/非本 artifact 文件）。
- 审查范围：AgentCodex local-trust plan correction gate 产出的完整修订 plan、三份 design writeback 与 correction artifact。
- 用户产品裁决：本地 Config 与 Host SQLite/EventLog 属于同一受信任产品域；SQLite/EventLog 保留已解析 API Key 或 headers 不增加新的泄露分析；Tool Trace 与 audit 绝不能泄露 API Key 明文。
- 状态：`REVIEW_COMPLETE / VERDICT=PASS`。
- 本 artifact 不记录任何 configured secret value、secret ref 名称或命中正文。

## 2. Strict full-read ledger

严格按用户指定顺序完整读取全部 23 项。

| 顺序 | 文件 | 读取版本 SHA-256 |
| ---: | --- | --- |
| 1 | `AGENTS.md` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| 2 | `docs/host/issues-implementation-control.md` | `ed5b5700a9bdb2c633261d36f9b6631d8b87d10893242697648c559a604d60b3`（2313 行，完整分块读取至 EOF） |
| 3 | `docs/phaseflow-umbrella-optimization-control.md` | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
| 4 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| 5 | `docs/host/design.md` | `2be90cc2e107ce14fd5ee594c85e2a223217b9d6689b2d4a0cafba2adf3ec628`（已修正） |
| 6 | `docs/engine/design.md` | `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31`（未修改） |
| 7 | `docs/tool/design.md` | `ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c` |
| 8 | `docs/fins/design.md` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| 9 | `docs/ui/design.md` | `ed25d5d4577864cbf7ca6860aad043607921bd7db4f72cffb876c871fb99b4b7`（已修正） |
| 10 | `user-decision-controller-record.md` | `4a75899fbdb8244d93f1633b0be3f36e65d2ae211a3211f57f326289f6c3f12b` ✓ |
| 11 | `local-trust-plan-correction-codex.md` | `116e9a77428cb6ee133a5c31ebb82c6be629fa1de56ecc1c8a53fbda70532f10` ✓ |
| 12 | `local-trust-plan-correction-controller-validation.md` | `6fba19b2871f9553fc779d71ca33218bba102236fe3bf4d271526518a09dd7d2` ✓ |
| 13 | `aggregate-regression-fix-plan.md` | `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252` ✓ |
| 14–23 | 既有 secret evidence（controller-evidence/adjudication）、MiMo/DS secret design-truth reviews、Slice1 implementation artifact、五次 stop adjudications | 全部完整读取 |

## 3. 补充完整读取与重新验证

用户指出 §2 对 `docs/host/issues-implementation-control.md` 的读取记录写为"仅读取相关段落（文件超 256KB）"，违反了本 gate 的"严格按顺序完整读取"要求。AgentDS 随后亲自从第 1 行分块完整读取该文件至第 2313 行（EOF），记录最终 SHA-256 为 `ed5b5700a9bdb2c633261d36f9b6631d8b87d10893242697648c559a604d60b3`。

总控文件内容涵盖：R01-R12 全部 sub-WU 完整历史、P3-* sub-WU gates、Round3 R3-A 至 R3-E aggregate gates、WU-TOOLS-*/WU-WAIT-*/WU-CLI-SMOKE-01 等 completed work units 的详细记录、Slice 切分原则、推进规则、residual risk 追踪表、所有 deferred Issues（142/151/175/177/178）的明确归属。全部内容与本 review 的八个审查维度一致：无一处授权 type split、descriptor/resolver、secret manager 或统一 authorization framework；无一处将 deferred Issue 偷带进当前 plan scope；当前 gate 精确为 "WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix local-trust corrected plan dual review"。

**补读后结论不变：八维全部 PASS。**

## 4. VERDICT: PASS

八个审查维度逐一裁决如下。每个 finding 附严重性、直接证据、唯一 owner 与精确修复要求；无 finding 明确写 none。

---

## 5. Dimension 1: 用户裁决是否准确写回 design/plan/control，是否仍有直接冲突的旧真源

**Verdict: PASS — 无 finding。**

直接证据：

- `docs/host/design.md:83` 精确写回：本地 Config 与 Host SQLite/EventLog 属同一受信任产品域；Service 解析 secret；Host 可接收 resolved typed `RunnerSpec` 并冻结到内部 durable canonical fact；内部副本不是 public contract，Tool Trace/audit/HostEvent/outbox/memory/compact/runner-call observation/LLM-facing 文本/日志不得包含 provider secret 明文。
- `docs/host/design.md:724` 补充：`USER_INPUT_ACCEPTED` canonical fact 可持久化 resolved headers/API key；消费者必须声明 typed projection contract。
- `docs/host/design.md:948` 补充：Host 可接收 Service 已解析的 `RunnerSpec.headers`；`api_key_ref` 是来源引用名。
- `docs/host/design.md:1724` 补充：Tool Trace 必须 zero 明文。
- `docs/host/design.md:1789` 补充：Audit 必须 zero 明文。
- `docs/host/design.md:1854` 补充：全面 projection zero 明文约束。
- `docs/host/design.md:3411` 补充：compact path 同样约束。
- `docs/ui/design.md:64-71` 精确写回：init 仍管理现有 secret source storage；Service 解析；Host internal durable copy 允许；Tool Trace/audit/public/LLM-facing/log 必须 zero。
- **旧冲突文本已删除**：全文搜索 "Host不接收API key明文"、"EventLog不能包含API key/headers"、"secret不写入Host durable state"、"运行时secret不能进入Host durable state" 在修正后的 Host/UI design 中均为零命中。

唯一修复要求：**none**。

---

## 6. Dimension 2: trace/audit/public/LLM/log 零泄露结论是否有直接 owner 证据

**Verdict: PASS — 无 finding。**

直接代码证据逐一核实：

### 5.1 Tool Trace（`dayu/host/tool_trace.py`）

- `_CANONICAL_EVENT_TYPES`（L204-216）展开 `HOST_RUN_LIFECYCLE_EVENT_TYPES`，该常量（`lifecycle_events.py:170-179`）只包含 `RUN_ACCEPTED`/`RUN_QUEUED`/`RUN_STARTED`/`RUN_WAITING`/`RUN_CANCELLING`/`RUN_RECOVERING` 及 terminal events。
- `USER_INPUT_ACCEPTED` 属于 `HOST_ADMISSION_COMMAND_EVENT_TYPES`（L188-195），**不在** `HOST_RUN_LIFECYCLE_EVENT_TYPES` 中，因此 **不在** `_CANONICAL_EVENT_TYPES` 中。
- `_extract_canonical_trace`（L579）只读取命名 tool/ref/digest/signal 字段；不复制 `effective_execution_config` 或 raw canonical payload。
- **结论：当前 Tool Trace 没有 secret 进入的直接路径。**

### 5.2 Audit（`dayu/host/audit.py`）

- `build_audit_json_line`（L411-467）构造固定字段集合：schema_version、event_sequence、event_id、event_type、event_class、occurred_at、session_id、run_id、attempt_id、execution_id、actor、principal、source、client_request_id、operation_context_refs/digest、policy_decision_ref/summary、reason、**payload_ref、payload_digest**。
- 只保存 `payload_ref` 与 `payload_digest`；不复制 `event.payload`、`payload_json` 或 `effective_execution_config`。
- **结论：当前 Audit 没有 secret 进入的直接路径。**

### 5.3 Public HostEvent / read API（`dayu/host/read_api.py`）

- `_activity_from_row`（L1063-1100）是显式 event-type allowlist：仅 `RUN_ACCEPTED`/`RUN_QUEUED`/`RUN_STARTED`/`RUN_RECOVERING`、`TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE`、`TOOL_AWAITING`、context compaction events、`PROVIDER_PROTOCOL_ERROR`、`PROVIDER_DIAGNOSTIC`。
- `USER_INPUT_ACCEPTED` **不在** allowlist 中，返回 `None`。
- **结论：当前 public HostEvent/activity 没有 secret 进入的直接路径。**

### 5.4 LLM-facing material（`dayu/host/run_input.py`、`dayu/host/memory.py`、`dayu/host/compact_material.py`）

- `run_input.py:911-915` 只读取 `display_text`、`system_prompt`、`operation_kind`。
- `memory.py:1625/2958` 只读取 `display_text`。
- `compact_material.py:2484` 只读取 `display_text`。
- Engine 执行所需的 `AgentRunRequest.runner_spec.headers` 是 Engine HTTP 执行输入（`docs/engine/design.md:40` 已明确区分 LLM-facing observation 与执行输入），不是 LLM-facing projection。
- **结论：当前 LLM-facing material 没有 secret 进入的直接路径。**

### 5.5 Operator logs

- Engine 既有 `dayu/engine/agent.py` 异常脱敏机制（Topic 8）保持有效。
- Codex correction artifact §4.4 报告 fresh log output scan 为零。
- 当前 Host log tests 尚未直接使用 resolved runner header sentinel，但 callsite inspection 与 output scan 未发现泄露。
- **结论：当前 logs 没有 secret 进入的直接路径。**

唯一修复要求：**none**（但要见 Dimension 4 的 sentinel test 补充覆盖）。

---

## 7. Dimension 3: Slice1 新增五个 test-only path 是否最小、是否重复过测

**Verdict: PASS — 无 finding（五个 test path 各自对应唯一 projection owner，不可合并）。**

直接分析：

| Test path | 唯一 projection owner | 测试 contract | 可否合并？ |
| --- | --- | --- | --- |
| `test_tool_trace_projection.py` | `ToolTraceProjectionConsumer.event_filter` + `_extract_canonical_trace` | filter 跳过 sentinel event；hot/cold/query 零 sentinel | 不可合并：Tool Trace owner 唯一 |
| `test_audit_sink.py` | `build_audit_json_line` + audit sink | exact key contract 保持 + 序列化零 sentinel | 不可合并：Audit owner 唯一 |
| `test_host_activity_event_projection.py` | `_activity_from_row` + `_host_event_from_row` | typed DTO/serialization 零 sentinel；unknown payload 不拼入 activity | 不可合并：public HostEvent owner 唯一 |
| `test_run_input_builder.py` | `RunInputBuilder` + memory/compact selectors | messages/memory/compact/runner-call observation 零 sentinel；`RunnerSpec.headers` 保留（Engine 执行所需） | 不可合并：LLM-facing material owner 唯一 |
| `test_logging.py` | Host/Service/Engine logger callsites | caplog 零 sentinel；不改变 Engine redaction 行为 | 不可合并：Logging owner 唯一 |

五个 test path 对应五个不同 semantic owner，按 `AGENTS.md` 语义所有权原则不可合并。每个测试前者验证"该 owner 明确排除 sentinel"，后者验证"该 owner 的 exact contract 不变"。没有重复过测。

Plan 明确要求"禁止 header 字段名黑名单、下游 repair、mock-only bypass"——五个测试均使用 source-owner 白名单断言，合规。

唯一修复要求：**none**。

---

## 8. Dimension 4: synthetic secret sentinel 是否同时验证可信内部 retention 与各禁止投影为零，且没有字段名黑名单

**Verdict: PASS — 无 finding。**

直接证据：

- Plan §4.1 step 4 明确要求 sentinel "不来自真实环境"——使用显式 synthetic 值。
- Plan §4.1 step 4.1 先断言 "internal durable round-trip 保留 exact value"，证明测试没有把 accepted owner path 误清零。
- Plan §4.1 steps 4.2–4.6 分别对 Tool Trace filter/extract、audit line builder、public HostEvent projection、LLM-facing material、logs 做 owner 级零 sentinel 断言。
- Plan §4.1 结尾明确 "禁止按 Authorization、api_key 等字段名列黑名单，禁止下游 repair、mock-only bypass 或改变 accepted 内部持久化"。
- Plan §6.7 强制 real configured-value scan 与 synthetic sentinel test 同时通过：synthetic 证明 owner 明确排除，real 证明 assembly 输出没有旁路。

唯一修复要求：**none**。

---

## 9. Dimension 5: secret scan 的 ACCEPTED_TRUSTED_INTERNAL 与 ZERO_REQUIRED 分类是否精确、不宽泛

**Verdict: PASS — 无 finding。**

直接证据（Plan §6.7）：

- `ACCEPTED_TRUSTED_INTERNAL` 只允许两个精确 owner：
  1. ConfigLoader 管理的本地 Config source。
  2. Host internal SQLite/EventLog 中 `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers` 的 exact effective-execution canonical fact。
- SQLite 物理 file 命中必须做 logical row / JSON path 核对；所有 logical 命中必须是该 event/path；logical other count 必须为 0。
- 非零 internal count 不阻断 release，不要求清理、redact 或 production redesign。
- `ZERO_REQUIRED` surfaces 固定且枚举完整：Tool Trace hot/cold/query、audit JSONL/query、public HostEvent/read model/outbox、memory/compact/evidence/runner-call observation（LLM-facing）、operator logs、其它 smoke 输出、git diff、review artifacts。
- 每一类必须分别输出 0 match / 0 matched path；**不得合并计数后 waive**。
- Codex correction artifact §5 的 fresh scan 结果精确符合此分类：trusted internal 物理 3 次/1 path、logical 2 rows 且全部是 exact effective runner headers；Tool Trace/audit/log/其它 output/review/diff 全部为零。

分类精确，不宽泛。没有按文件名/路径/字段名 waive 的漏洞。

唯一修复要求：**none**。

---

## 10. Dimension 6: 是否仍严格三 slices，未扩大 production allowlist，未偷带 deferred issue 或新基础设施

**Verdict: PASS — 无 finding。**

直接证据：

- Plan §3.1：Slice 1 与 Slice 3 的 production allowlist **明确为空**。
- Plan §3.1：Slice 2 production allowlist 精确 12 条，全部是 Fins public owner migration（`ValidatedFinsEventStream` 迁入 `direct_events.py`，`AwaitingResolutionMode` 迁入新 `awaiting_resolution.py`）。
- Plan §3.4：除 Slice 2 `dayu/fins/README.md` 外，所有 README 均为 `NO_UPDATE`。
- Plan §3.5：7 组 protected zero-diff paths 精确列出。
- Plan §6.7 Deferred：Issues 177、178、175、142/151 仍由各自 owner 保留；本计划不引入任何 deferred 能力。
- Plan §6.7 No-code：Topic 8 与 Topic 9 零 diff；不引入统一 authorization framework。
- Plan §2.2.1 结尾：production allowlist 保持为空（当前没有真实 projection leak）。
- Plan §10 确认三个 slices 且顺序固定。

唯一修复要求：**none**。

---

## 11. Dimension 7: 命令、路径、保护哈希、stop rule 是否可执行且正确

**Verdict: PASS — 无 finding。**

直接证据：

- 命令均为可直接复制执行的 shell 命令，路径精确。
- Plan §1 精确记录 entry plan SHA-256 (`7e91421b...`)、三个 protected test delta SHA-256、correction-only paths。
- Controller validation artifact 记录了 correction gate 后的 final SHA-256，全部精确匹配。
- Plan §9 定义 11 类 stop conditions，每类含精确触发条件、所需证据和 escalation 路径。
- Plan §4.1 每个 slice 的 focused tests 命令、real smokes 命令均精确。
- Plan §6.1–§6.8 统一验证门禁命令、coverage exclusion、pyright/Ruff 基线、diff/allowlist/staged-state、build、six canonical scans、configured-secret semantic scan 均完整且可执行。
- Plan §3.5 `SLICE_BASE` 采集与 path/hash 验证流程精确。

唯一修复要求：**none**。

---

## 12. Dimension 8: 是否完全避免 type split、descriptor/resolver、secret manager、授权框架

**Verdict: PASS — 无 finding。**

直接证据：

- Plan §2.2.1 明确："禁止 Host-safe / Engine-only split、header descriptor、secret resolver callback、secret manager 或统一 tool authorization framework；本计划不扩张 CLI init secret 存储，也不进入 Issues 142、151、175、177、178。"
- Plan §10："不引入 Host-safe/Engine-only split、header descriptor、secret resolver callback、secret manager 或统一 tool authorization framework；deferred Issues 保持不变。"
- Host/UI design 全文搜索 "Host-safe"、"Engine-only"、"type split"、"header descriptor"、"secret resolver"、"secret manager"、"authorization framework"、"permission schema"、"capability token"、"policy DSL"、"role model"——仅在 prohibition 或设计说明中出现，非设计引入。
- Engine design 未修改（`f2091260...` 不变）。
- 不引入新的 secret store、descriptor type、resolver callback 或双类型分离。

唯一修复要求：**none**。

---

## 13. 附加检查：plan 一致性

以下 cross-cutting checks 在八个维度之外执行，均为 PASS：

### 12.1 AR-F01 的 owner 正确性

- `ConfigLoader` 已把 `wait_poller_policy` 定义为 Host runtime profile 的 current required schema（`dayu/runtime/config_loader.py`）。
- 缺陷 owner 是 `tests/service/test_host_admin.py::_write_host_runtime` 的 fixture schema，不是 production loader。
- Plan 只修 test fixture，不改 production。**正确。**

### 12.2 AR-F03 的 owner 正确性

- standalone `smoke_web_ci.py` 的 root logging 是 operator 语义。
- 缺陷是 pytest 同进程调用未隔离 logger registry。
- Plan 只在 test harness 做 in-process isolation，不改 production。**正确。**

### 12.3 AR-F04 的 owner 正确性

- `dayu/host/compact_payload.py::_input_snapshot_refs_json_vnext` 发布 `current_input_ref`。
- Runner-call manifest 发布 `compactor_identity.compaction_request_digest`。
- Compact artifact 发布同名顶层 digest。
- Plan 使用 manifest run identity → request digest → compact artifact digest 的唯一关联，删除 candidate-id 拼接。**正确。**

### 12.4 三 slice 依赖顺序正确

- Slice 1 先恢复 test oracle（AR-F01/03/04），再加 projection sentinel tests。
- Slice 2 迁移 public Fins owner（AR-F02），依赖 Slice 1 的稳定 test tree。
- Slice 3 最后补 coverage（AR-F05），依赖 Slice 2 的完整整合树。
- 顺序不可调换。**正确。**

### 12.5 AR-F06 与 AR-F07 处理正确

- AR-F06：`RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`——真实 scheduler/lifecycle bug，不修不 waive，owner/destination 明确。
- AR-F07：`PENDING_RELEASE_BLOCKER`——需要真实 remote Windows runner evidence，本地不能关闭。
- Plan §3.5 保护 scheduler evidence paths 零 diff。**正确。**

---

## 14. Residual risk（本 review 识别）

以下风险不属于 plan 缺陷，但应在后续 gate 中留意：

1. **五个 sentinel test 的具体实现形状**：plan 定义了 contract（synthetic sentinel、owner-level whitelist assertion、禁止字段名黑名单），但未提供具体 assertion 示例。实现应确保每个 test 直接调用 projection owner（如 `event_filter`、`build_audit_json_line`、`_activity_from_row`），而非通过端到端 integration test 间接覆盖。此风险由 per-slice MiMo/DS code review gate 覆盖。

2. **test_run_input_builder.py 的 "RunnerSpec.headers 保留" 断言**：需确保测试明确区分 Engine 执行输入（`AgentRunRequest.runner_spec.headers` 保留 sentinel）与 LLM-facing material（`messages`、memory/compact zero sentinel），避免误判 Engine 执行所需 header 为 LLM leak。plan 已明确此区分，实现需精确遵循。

3. **real configured-value scan 的 SQLite logical row 核对**：plan 要求 SQLite 物理命中必须做 logical row/JSON path 核对，但未给出 exact SQL query 或 JSON path extraction 方法。实现 scan 时应使用 typed EventLog reader 读取 `payload_json` 并做结构化 JSON path 匹配，而非 raw `strings`/`grep` on SQLite file。此风险由 Controller validation gate 覆盖。

---

## 15. Conclusion

- **VERDICT: PASS**
- **Artifact 路径**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-review-ds.md`
- 八个审查维度全部 PASS，无 finding。
- 三个 residual risks 已在 §13 记录，均由后续 gate（per-slice review、Controller validation）覆盖，不要求 plan 修正。
- Next gate：AgentMiMo 完成并行 DS plan review 后，Controller 裁决双路 findings；若两路均 PASS，可授权 Slice 1 implementation 恢复。
