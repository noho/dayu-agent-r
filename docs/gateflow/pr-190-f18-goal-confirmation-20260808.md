# PR 190 F18 Goal Confirmation

## Gate state

- Work unit：F18，PR 190 上的 architecture-sensitive bug / scenario-correction / formal-observation work unit。
- 当前 gate：goal confirmation 已由用户以“按照你的建议继续”确认。
- next entry point：`plan`。
- 下一具体任务 owner：AgentCodex。
- 设计裁决真源：`docs/host/design.md`、`docs/engine/design.md`。
- 既有 Oracle / scenario 真源：`docs/cli_ci.md`、`docs/cli_ci_oracles.json`、
  `docs/cli_ci_scenarios.json` 与 `docs/reviews/pr-190-oracle-adjudication-20260808.md`。
- 本 work unit 没有独立 project `control_doc`；不得把 CLI CI assessment 或其它项目 control 文档冒充 F18
  control truth。F18 按既有 PR 190 Gateflow artifact 方式逐 gate 记录状态。

## Confirmed goal and motivation

F18 包含两个已确认、但裁决边界不同的交付面：

1. 按既有 accepted Oracle / scenario 记录方式写入 B1 用户裁决：
   `interactive.interactive.g06.tool-trace-formal@2` 行为正确并可裁决为 `accepted`。正式
   mandatory evidence 只要求 public Host Tool Trace resolver / analysis response identity、canonical terminal
   identity equality 与 secret scan；fresh hot owner evidence 六字段 6/6 exact match 满足该义务。cold analyzer
   `compactor_responses=0` 与 provider-native request id unavailable 继续作为 limitation / residual evidence
   question，不得伪装成该 scenario 的 mandatory readiness gap。
2. 从 Trial2 durable owner chain 证明 `USER_INPUT_ACCEPTED` sequence 325、`RUN_ACCEPTED` sequence 326、
   `RUN_FAILED(reason=runner_candidate_invalid)` sequence 327 的真实原因；若是 scenario / harness / setup
   错误，只修合法 setup 或外部 observation tooling；若是产品缺陷，只在唯一语义 owner 或其直接上游输入
   校验修复。根因闭合后，使用合法、从启动即固定的 fresh production setup 完成
   `cap-constrained-memory-replacement@1` 所需真实观察并形成逐项 human-readable report。

动机成立：当前 B1 已有用户裁决但 registry 仍为 `unadjudicated`；B2 的 fresh Trial2 在 provider dispatch 前
失败，阻止 cap-constrained scenario 进入 compactor，因而既不能形成 mandatory observation，也不能由现有
unit test、旧 durable state 或进程 exit 0 替代。

## Direct owner evidence

1. `dayu/cli/commands/interactive.py` 的 production path 先完成 runtime assembly，再在整个 interactive 进程
   生命周期内以 `open_host(prepared.runtime.host_assembly.options)` 打开一个 Host，并 attach / reuse label Session。
2. `dayu/service/host_assembly.py` 的 `compose_open_host_options` 先选定 `execution_profile_id`，再由同一 profile
   机械构造 ordinary baseline、`ContextBudgetPolicy`、compactor baseline 与 `MemoryProjectionPolicy`。
3. `docs/host/design.md` 的配置边界明确：当前 per-run override 闭集只有 system prompt、tool selection、
   runner spec/options 与 agent policy；context budget policy、compactor baseline、memory projection policy 等是
   `open_host` construction-time inputs，Host handle 打开后不由 scene 或单个 Run 改写。需要新增 per-run profile
   或 caps 必须先回到 Host public interface design gate，不能从 assembly / harness 旁路。
4. `dayu/host/dispatch.py` 在 Attempt start 前先调用
   `_catch_up_memory_projection_before_candidate(session_id)`，再由
   `prepare_runner_call_candidate_in_transaction(...)` 冻结完整 candidate。该调用使用当前 opener 的
   `memory_projection_policy`；候选构造异常目前在这一边界被统一收口为
   `RUN_FAILED(reason=runner_candidate_invalid, error_code=runner_candidate_invalid)`。因此 sequence 325-327
   只能证明 failure 位于 Host admission 后 / Attempt dispatch 前，不能证明 provider、Runner 或 compactor 已被调用。
5. `dayu/host/run_input.py` 的 pre-start memory reader 按当前
   `digest_memory_projection_policy(policy)` 查询 snapshot；`dayu/host/memory_repair.py` 的 catch-up 则从固定
   Conversation Memory consumer checkpoint 继续。attached Session 在不同 opener policy 下重开是否产生
   checkpoint / snapshot policy identity 矛盾，是优先调查假设；必须用 Trial2 typed SQLite rows、policy state 与
   owner exception chain直接证实或推翻，不能仅凭 profile digest、事件顺序或错误文案下结论。
6. `docs/engine/design.md` 明确 Engine 不拥有 Host context budget、memory、compact artifact 或 Host attempt budget；
   sequence 327 发生在 Attempt-free pre-dispatch path 时，不应把根因或修复下沉到 Engine。

## Success signals

### B1

- `tool-trace-formal@2` 以既有 schema/style 更新为 `accepted`，引用当前 immutable evidence 与用户裁决 identity。
- cold analyzer / provider request id limitation 原样保留并有明确 owner / destination。
- 不改变 B2 裁决，不把 interactive registry 或 overall readiness 提前标为 ready。

### B2 implementation / setup

- Trial2 原始失败由 owner code path、typed state 与直接 durable data 同源证明；明确唯一 owner。
- 明确裁决 execution profile / caps 切换对 attached Session 的 contract：合法或非法均要有设计、public typed
  input 与 durable state 证据，不能靠现象推断。
- scenario / setup 错误时，产品零迁就；产品缺陷时，只在 owner boundary 或直接上游输入校验修复，并补 owner-level
  contract tests。
- 如公共 failure 缺 owner 必需的稳定结构化原因，只在真正 error owner 评估最小 typed cause；不得公开 traceback、
  原始私有异常字符串或实现细节。
- provider-independent 诊断、测试和审查完成前不消耗真实 provider。

### B2 formal observation

- 从一开始就用合法固定配置、完全 fresh workspace、production CLI、POSIX PTY、真实 AAPL corpus 与真实 MiMo；
  不使用 DeepSeek、fake/mock provider/tool，不复用 Trial1/Trial2 durable state。
- bounded observation 原样归档全部 attempted outcome；失败不覆盖、不重标 PASS。
- 人类可读 report 逐项覆盖用户列出的 caps、audit、accepted replacement、EvidenceFact keep/omit、新 provenance、
  omitted exact complement、真实 repair/fallback 链、artifact/EventLog/Memory/RunInput/public Tool Trace 同源、fresh
  reconnect、screen/argv/keys/exit/files/log/trace/SQLite before-after 与 secret/path scan。
- 自然未触发分支如实标 `needs-more-evidence`，不 injection、不伪造 provider 输出。
- B2 最终保持 `unadjudicated`，直到用户基于 report 明确裁决；overall readiness 不得标 ready。

## Non-goals and binding scope boundary

- 不修改 Issue 192 duplicate-governance INFO 行为。
- 不处理 Fins tool schema 优化。
- 不扩大到 B1 cold analyzer enhancement。
- 不用 CLI、adapter、展示层、fixture 或 analyzer fallback 掩盖 owner 语义。
- 不引入 profile patch dict、extra payload、兼容 shim、旧 schema 读取或新的第二真源。
- 不用 unit test 冒充真实 repair / exhausted fallback observation。
- 不 merge、mark ready、approve/request reviewer、rebase/force-push、创建新 PR、删除分支或替用户接受 B2。
- 不读取、修改、stage 或提交 ownership 不明的
  `docs/reviews/plan-review-20260808-095346.md`。

## Minimal-design judgment

本轮先证明现有 setup 与 typed owner contract，再决定是否需要产品修改。若现有 public contract 已明确禁止
attached Session 上切换 construction-time memory/caps，最小正确方案是从 fresh workspace 启动时固定 constrained
profile，并修 scenario / observation tooling；不为错误 setup 增加产品动态 profile 能力。只有直接证据证明合法 setup
仍触发 owner 缺陷时，才规划最小 owner 修复。B1 只记录既有用户裁决，不借机扩展 analyzer 或 readiness 模型。

## Risks and blocking questions

- 非阻塞 investigation question：Trial2 private evidence root 的 exact location、SQLite 与 log ownership 必须由
  AgentCodex 在不提交 raw SQLite / absolute private path / secret 的前提下恢复；若原 bundle 不再可读，则必须用
  provider-independent owner reproduction 补足直接证明，不能凭用户摘要猜根因。
- blocking open question：无。用户已确认目标、范围与自动推进要求；若 root-cause 证据指向需要新增/改变 public
  contract、schema 或 user-visible behavior，必须回到 Controller 重新确认，不由 implementation Agent 自行扩 scope。

## Completion status

Goal confirmation：`accepted`。

Next entry point：`plan`，由 AgentCodex 产出 code-generation-ready artifact；禁止在 plan gate 修改产品、运行真实
provider、commit、push、PR 或进入后续 gate。
