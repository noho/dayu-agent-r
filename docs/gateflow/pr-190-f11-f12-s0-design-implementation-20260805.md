# PR 190 F11/F12 S0 Design Truth 实施记录

## Gate metadata

- Gate：`implementation`，slice `S0 — design truth`
- Work unit：PR 190 F11 public compactor response identity 与 F12 fresh compact v3
- Accepted plan：`docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`
- Accepted checkpoint：`docs/gateflow/pr-190-f11-f12-accepted-plan-checkpoint-20260805.md`
- Implementation base：`427b1c858d5e926f309935fa206963deb1618436`
- Branch：`codex/interactive-oracle`
- Artifact path：`docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md`
- Completion status：S0 implementation complete；未执行 review、stage、commit 或 push

## Preflight

- 新 HEAD 只把 accepted checkpoint 中 DS re-review digest 机械修正为当前文件 SHA-256 `538ff5193b45a70623c4c2bba881e03ceca89a9657f7e76424153bfcdcdc8d64`。
- plan、reviews、两份 design 与生产代码的语义没有基线变化；恢复 S0 前工作树 clean。
- 当前分支不是受保护 trunk，且 S0 allowed files 明确。

## First-principles judgment and direct evidence

### F11

动机成立，root cause 是 public projection 缺口，不是 canonical identity 缺失：

- `dayu/host/context_events.py` 的 compacted / attempt-rejected builder 已把 proposal manifest、operation、attempt 与 `SuccessfulRunnerResponseIdentity` 绑定；strict parser 已验证 compactor Engine run identity。
- `dayu/host/_runner_call_manifest.py::RunnerCallCompactorIdentity` 已保存 parent Host Run、operation、attempt、compactor Engine run 与 input projection binding。
- `dayu/host/durable/tool_trace.py::resolve_runner_call_projection_from_signal` 当前只返回 manifest、runner input projection 与 tool schema snapshot，`RunnerCallResolvedProjection` 没有 response identity。

因此设计 owner 必须是 Host Tool Trace durable resolver 对 canonical terminal 的 strict public projection；Service、CLI、renderer 或 evidence harness 不得旁路反推。

### F12

动机成立，root cause 是 v2 把确定性治理责任分配给模型：

- `dayu/host/compaction.py::CompactCandidateV2` 要求模型产出 diagnostics 与 `explicitly_dropped_sources`；drop reason 是四值主观枚举。
- `dayu/host/context_governance.py::accept_compact_candidate_v2` 已能从 candidate provenance 派生 represented，却仍要求模型补齐 exact drop partition。
- `dayu/host/memory.py::MemoryProjectionPolicy` 实际拥有所有 section cap、default、validation 与 policy digest；v2 input 没有真实 caps boundary DTO。
- `dayu/host/compact_payload.py` 当前 artifact schema 为整数 `3`，durable semantic payload仍读取 represented + explicit drop coverage。
- `dayu/host/llm_compaction.py` 当前 parser / renderer 同时拥有 v2 shape，initial 与 repair 没有 fresh v3 single-structure contract。

因此设计 owner 链固定为：compaction domain typed types、single structure projection、Context Governance accept、fresh durable truth、Memory consumer；模型只生成五类业务语义与必要 provenance。

### Engine

- `AgentRunRequest` 当前没有 structured-output request 字段。
- `AsyncRunner.call` 当前没有 structured-output keyword-only 参数。
- `RunnerSpec` 当前没有 structured-output capability。
- OpenAI-compatible payload builder 当前只投影 typed provider extension，没有 `response_format` generic request。

因此 generic request/capability 属于 Engine public contract 与 transport projection，不属于 Host compact schema，也不能通过 provider/model 名称推断。

## Changed sections

### `docs/host/design.md`

1. §14.1 `Tool Trace Hot / Cold Storage`
   - 冻结 public typed response projection、canonical terminal exact binding、完整 keyset exhaustion、无总页数 cap、corruption/mismatch fail closed、fresh analysis schema v2 与 secret whitelist。
2. §24.2 `LLM-facing Compact I/O 硬边界`
   - 明确模型只生成五类语义与 provenance；真实 caps 进入 input，治理 digest 不进入 LLM，coverage / omission / audit 归 Host。
3. §24.3 `Compact v3 I/O Contract`
   - 整节替换旧 v2 normative truth；逐字段定义 input v3、caps DTO、五个 typed child、candidate v3、required nullable summary、single structure owner、strict old-key rejection与 accept contract。
4. §24.4 `Snapshot Typed Schema`
   - 冻结 `compactor_input_projection.v2`、artifact schema 4、represented / omitted / policy audit 与旧 compact/session replay不兼容边界。
5. §24.5 `五类 Session Semantic Memory`
   - Memory 只消费 `CompactAcceptedTruthV3`；rolling correction 只用 retained current provenance + Host-derived omitted old labels表达。
6. §24.6 `Prompt Assembly`
   - 冻结 shared system contract、single structure source、initial / repair 两种 Host-rendered self-contained body、whole-candidate repair 与 digest 反泄漏。
7. §24.7 `测试与评测边界`
   - 增加 structure同源、policy-to-DTO、coverage/audit、pagination exhaustion、prompt反泄漏、fresh persistence rejection与真实 provider observation边界。
8. §25 `Context Governance`
   - accept owner、coverage partition、caps usage audit、repair binding、fresh persistence消费与 single-terminal路径全部切到 v3；删除模型拥有 drop ledger / reason的规范。
9. §25.1 `Compact Event 响应路径`
   - 保留 canonical terminal / proposal manifest / successful response identity owner，并补 Tool Trace public projection contract。

### `docs/engine/design.md`

1. §2 `公共入口`、§4 `AgentRunRequest`
   - 增加显式 `StructuredOutputRequest | None`，禁止进入 provider extension / headers / extra payload。
2. §6 `Agent 推理循环`
   - 所有 Runner call 原样转发同一 request；provider rejection 不触发弱模式重试。
3. §7 `Runner 协议`
   - 增加 required、无 default 的 keyword-only `structured_output`，冻结 Protocol / implementation / call sites 同 commit迁移。
4. §8 `RunnerSpec 与 RunnerCallOptions`
   - 定义 `none/json_object/json_schema` capability、fail-fast matrix 与 exact OpenAI-compatible `response_format` projection。
5. §15 `Context Compaction`
   - Engine 只提供 generic capability；不了解 compact schema，不按 provider 名称 dispatch，不自动升级或降级。

## Contract decisions

- F11 response identity 只来自 canonical compacted / attempt-rejected terminal与 proposal manifest graph；完整 exhaustion 后的真实缺失才是 limitation。
- F12 v3 不保留 diagnostics、explicit drop ledger/reason、omission kind或兼容 reader。
- `MemoryProjectionPolicy` 继续唯一拥有 caps；`CompactOutputCapsV3` 只是机械 immutable projection。
- represented + omitted 是 immutable boundary 的 Host-derived exact partition；omitted 不携带主观原因。
- artifact、event、Memory、RunInput 与 Tool Trace 只从 `CompactAcceptedTruthV3` 派生。
- initial 与 repair 共用 system / structure source，但 user body 分开渲染；Host internal digest不进入 LLM-facing text。
- Engine structured output 是 provider-neutral一等 request；不通过 provider/model inference或 fallback实现。

## Validation

- 实际章节号已通过 heading scan核对，以语义章节为准：Host §14.1、§24.2-§24.7、§25、§25.1；Engine §2、§4、§6、§7、§8、§15。
- 冲突 v2 normative scan：`CompactInputV2`、`CompactCandidateV2`、`CompactAcceptedTruthV2`、旧 input/output v2 schema、旧 explicit-drop coverage与四值 reason均无命中。
- 新 contract term scan：F11 typed response / keyset、F12 v3 types / persistence / initial-repair / digest boundary、Engine request / capability / response format均有直接命中。
- Markdown fence parity：Host 182 个 fence marker，Engine 8 个，均为偶数。
- `git diff --check`：PASS。
- S0 是纯 design/document slice；accepted plan 只要求 terminology/static scan 与 diff check，本 slice 未运行生产测试、coverage或 pyright。

## Docs and scope decision

- 只修改两份 design truth并新增本 implementation artifact。
- 不修改生产代码、tests、registry、README、finding/review artifacts或旧 evidence。
- README trigger未命中：S0 没有落地生产/public runtime行为，README只能在后续相应代码 slice更新。

## Residual risks and uncovered areas

- F11/F12/Engine contract尚未实现；owner tests、真实 provider observation、registry lifecycle与Oracle状态分别由 accepted plan S1-S5承担。
- Tool Trace analysis schema v2 是 breaking change；仓外 consumer风险留到后续实现与 PR closeout明确。
- schema-3 compact artifact与依赖旧 compact payload的Session replay明确不支持；如产品要求迁移，owner是独立 migration work unit。
- 本 artifact只记录 implementation事实；S0 尚未经过 plan要求的独立 review / re-review，也没有 accepted slice commit。

## Completion signal

S0 design truth implementation完成：后续 S1-S3 不需要重新发明 F11 public resolver、F12 compact v3或Engine generic structured-output contract；当前下一入口是 S0 review gate。
