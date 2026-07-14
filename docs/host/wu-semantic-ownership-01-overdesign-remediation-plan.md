# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Continuation 总计划

## 0. Gate 身份与执行边界

- **状态**：remediation plan re-review fix complete；初次双路 re-review 已由 controller 裁决，本轮只关闭 accepted `DS-RR-F01`，等待 AgentMiMo / AgentDS 对最终全文做第二轮双路 re-review，尚未进入任何 R01—R12 sub-WU plan 或 implementation。
- **所属 work unit**：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。本文中的 `R01`—`R12` 都只是 umbrella 内部 remediation sub-WU，不是 feature、issue 或替代 umbrella 的新 work unit，也不得单独改写 control document 中的 work-unit 身份。
- **证据范围**：`b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`；计划编写时核验的 HEAD 为 `01bbf74c3c408b1b8eaafae20b5a9c68cb733c3f`。
- **风险**：Topic 1—7 全部为 `production-high`。本文拥有 R01—R12 的切分、顺序、全局不变量、最低验证意图和基于当前代码证据的 mandatory starting baseline，不能替代任一 sub-WU 自己的 code-generation-ready plan；umbrella baseline 与 later accepted sub-WU plan 的唯一时序规则见第 7.3 节。每个 sub-WU 都必须独立完成第 7.3 节的 plan、双 plan review、fix、双 re-review、accepted plan commit、implementation、双 code review、fix、双 re-review和 accepted sub-WU commit；aggregate review 不能替代其中任何一环。
- **本 gate 的写权限**：只允许修改本文并新增 `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-fix-codex.md`。当前脏工作区中的 design/review/control artifacts 均视为既有输入，不删除、不回滚、不覆盖。
- **本 gate stop condition**：本文与 re-review-fix artifact 完成并通过 artifact-only 检查后立即停止；不进入第二轮 re-review、任一 sub-WU plan、implementation、commit、push、PR、merge 或下一 gate。

## 1. Goal、动机与成功信号

### 1.1 Goal

在不扩大 umbrella 范围的前提下，把 controller 已裁决的 Topic 1—7 accepted code fixes 转换为 code-generation-ready、可按语义 owner 顺序实施、可独立验证和回滚的总计划；删除没有产品必要性的公开 schema、隐式 authority、重复状态机和下游补偿，同时保留已经裁决的本地防御、路径 containment、资源治理和原子发布能力。

### 1.2 First-principles judgment

问题动机成立，且 `production-high` 评估准确，原因不是“代码多”或“测试复杂”，而是以下直接 contract 冲突：

1. **输入限制被冒充业务事实**：`dayu/tools/doc_tools.py` 与 `dayu/documents/processors/bounded_source.py` 把 32 MiB、10,000 entry、oversized skip 写入运行结果、错误码与 LLM 文本；合法输入因此被拒绝或静默漏扫，而输出截断已另有 Host-owned contract。
2. **配置、权限与 capability 互相代签**：Web 的私网开关同时控制 browser；Service 根据 scene 工具选择自行启用 wait poller；一个工具是否可见因此意外成为网络或后台 runtime authority。
3. **下游从无语义字段反推事实**：Host 以参数 key 黑名单猜测 LLM-safe 语义，并把未知 opaque ref 猜成业务来源；同一错误随后进入 RunInput、Memory、Compact 和 trace。
4. **Fins 同一事实有多个 owner**：batch 同时依赖显式 token 与 ContextVar/task/thread；source meta 兼任 staging acknowledgement；read 双读 consumer-selected revision；terminal invariant 在 Fins、Service、CLI 三层重复校验。
5. **公开入口承诺不存在的产品**：`upload_filings_from` 发布 JSON argv schema而不是 OLD-aligned shell/cmd workflow；Web/WeChat/render 只有 placeholder grammar；`init` 具备局部文件事务，却缺少产品裁决要求的 provider/model/API-key/manifest/optional integration 工作流。

上述判断均由代码 owner 处的直接读写链证明，不依赖 README、测试成功或旧 plan 作为“正确性”证据。controller discussion 已解决产品选择；本计划不重新打开已裁决问题。

当前 HEAD 的直接证据索引：

| Topic | owner-side code evidence | 被影响的真实入口/消费者 |
| --- | --- | --- |
| 1 | `dayu/tools/doc_tools.py::DocResourceBudget`、`_bounded_local_source`、`list_files`/`search_files`的entry break与oversized skip；`dayu/documents/processors/bounded_source.py::SourceBudgetExceeded/BoundedSourceSnapshot` | `dayu.tools.doc_provider:discover_tools -> Doc callable -> processor/list/search -> ToolRuntime`；tests直接锁定exact/+1与10,000边界 |
| 2 | `dayu/config/tool_discovery.json` Web config；`provider.py` complete-object parser；`web_egress_policy.py` custom/private/DNS；`web_http_session.py` proxy ban；`web_playwright_backend.py` private flag前置拒绝；`utils/diagnose_web_access.py` lifecycle | Web discovery→HTTP/browser/challenge/diagnostics；Web CI和diagnostic CLI消费v2 artifact |
| 3/4 | `dayu/host/accepted_result_projection.py::_contains_unsafe_argument_key/_readable_ref_text`；`_event_payload.py::llm_safe_replay_arguments`；ordinary `tool_runtime.py`与awaiting `waiting.py`写不同request facts | `run_input.py`、`durable/memory.py`、`compact_material.py`、`tool_trace.py`共享同一错误projection |
| 5 | `dayu/service/host_assembly.py::with_entrypoint_wait_poller_policy`按scene构造默认；`dayu/host/wait_adapter.py::WaitPollerRuntimePolicy`藏12个默认并把`WaitObservationTimedOut`转`ResolveWaitLostOutcome`；`_wait_observation.py`已有publication token fencing | `entrypoint_runtime -> open_host -> wait supervisor -> adapter -> resolve_wait`；Engine `agent.py`只在`ToolExecutor.execute` handshake等待outcome |
| 6 | `domain/document_models.py::BatchToken`携带owner/path；`storage/_fs_storage_infra.py` ContextVar/task/thread与journal；`stage_source_document`/`ingest_complete=false`；`read_runtime.py` revision-before/after；financial/XBRL contracts；Fins/Service/CLI三处terminal scan；HKEX单`rowRange=100`；`_fs_storage_utils.py` raw component grammar | ingestion/CN/SEC/Docling producers、storage repository、九类Fins read tools、direct Service/CLI、HKEX discovery |
| 7 | `dayu/cli/commands/fins.py::_render_upload_batch_plan`输出JSON argv；`pyproject.toml`发布3个placeholder scripts；`dayu/cli/commands/init.py`只做tree copy/swap | `dayu-cli upload_filings_from`、wheel entry points、`dayu-cli init`；OLD直接证据在 `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py::_generate_upload_filings_script`、`upload_recognition.py`与OLD init catalog |

代码证据范围的入口核验命令包括 `rg -l 'begin_batch|stage_source_document|_execute_with_auto_batch' dayu/fins`、`rg -n 'tool_execution_timeout|ToolAwaiting' dayu/engine tests/engine`、`rg -n 'upload_filings_from|dayu-(web|wechat|render)' pyproject.toml dayu tests README.md`；这些命令只读，不产生产品修改。

### 1.3 Aggregate success signal

Topic 1—7 只有同时满足以下条件才算完成：

- controller accepted contract 在唯一 owner 处实现；所有 downstream consumer 只消费同一 source of truth；
- 所有必须删除的 schema、文案、状态、fallback、placeholder 与测试断言在生产/测试/README/source-propagation scan 中均为零残留；
- 所有 retained 安全行为在 owner-level 测试和真实 smoke 中仍有效；
- 每个 sub-WU 的 targeted tests、changed-file coverage、全量 pyright、diff check、README decision、真实入口 smoke、两路 code review 均通过；
- 每个 sub-WU 都有独立 plan/review/fix/re-review/accepted-plan-commit 与 implementation/review/fix/re-review/accepted-sub-WU-commit 证据；任一 severity 的 controller-accepted actionable finding 均已修复，rejected/deferred/note 未被误实现；
- 全部 sub-WU 后 aggregate regression、aggregate deepreview、PR gate 和 final closeout 矩阵全部通过，且无未归属 residual risk。

## 2. 真源优先级与冲突规则

冲突时按以下顺序裁决，低优先级材料只能提供证据，不能覆盖高优先级裁决：

1. 本次用户明确指令与 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`；controller discussion 是 Topic 1—9 的最终产品裁决。对本次双路 plan review finding，`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-controller-adjudication.md` 是唯一 disposition owner；reviewer 原始 verdict、severity 和建议不能覆盖它。
2. 已按裁决更新的永久设计真源：`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`。
3. `docs/host/issues-implementation-control.md` 与 `docs/phaseflow-umbrella-optimization-control.md`：只拥有 umbrella gate 状态、成本控制、baseline/closeout 纪律，不重新定义产品语义。
4. 三路 code-evidence review：Codex、DS、MiMo；只提供代码位置、漂移和反例。三者冲突时采用 controller discussion。
5. 当前代码、测试和 README：是被修复对象或回归证据，不是授权真源。

## 3. 明确非目标

- Topic 8：保留 `dayu/engine/agent.py` 的敏感值先脱敏、原始异常消息 240 字符上限、显式截断后缀和完整 traceback 日志；不改配置、不新增 durable full-detail ref。
- Topic 9：不设计或实现统一 tool authorization framework、角色模型、policy DSL、capability token 或 sandbox。
- 不删除或弱化 Doc `allowed_paths`、Web redirect/DNS/peer/资源预算防御、路径 containment、symlink 拒绝、原子写/原子 swap、process late-publication fencing。
- 不实施 Issue 142、151、175、177、178；不把现有 Web/WeChat/render tracker 能力搬入本 WU。
- 不为旧 schema、旧路径布局、旧 JSON argv、旧测试或旧入口加兼容读取、兼容 wrapper、re-export、下游 fallback、loose parsing 或 test shim。
- 不修改 accepted findings 无关代码；不顺手重构模块、引入通用安全归一层或创建 speculative `BusinessSource`。
- 不把 Doc 输入完整性改成 Issue 177 的完整 `TruncationManager` 接通；不为 HKEX 添加无证据的日期递归切分；不把 Fins 长事务迁往 Issue 175 的进程隔离。

## 4. Accepted / deferred / no-code 追踪表

| Controller topic / evidence finding | 最终 disposition | 实施归属 | 关闭证据 |
| --- | --- | --- | --- |
| Topic 1；Codex F-03/F-04；DS F-03/F-DS-01/02/03；MiMo 01/05/06 | accepted code fix：删除 32 MiB、10,000 entry、`source_limit`、`directory_entry_limit`、oversized skip 及其 LLM 文案；保留完整输入读取与结果截断 | R01 | 删除扫描 + 大文档/大目录真实回归 |
| Issue 177 | deferred：完整 `TruncationManager` 接通 | Issue 177 owner，不在本 WU | R01 source scan 证明未引入新 manager wiring |
| Topic 2；Codex F-05/F-06/F-07/F-14/F-15/F-16；MiMo 02/03/04/06 | mixed accepted：private/custom port 默认允许；DNS peer proof 默认 off；proxy 默认允许；browser 独立；owner-split/局部 override 大预算；challenge 与 diagnostics v2 保留；storage-state lifecycle 删除 | R02 | config→transport→browser/diagnostics smokes；lifecycle 删除扫描 |
| Issue 178 | deferred：credential storage-state retention/refresh/concurrent publish/cleanup lifecycle | Issue 178 owner | R02 只保留路径输入，不实现生命周期 |
| Topic 3；Codex/DS F-01 | accepted：删除 normalized/safe-arguments repair 与字段黑名单；不新建安全归一层；保留内部 canonicalization/digest；从 prompt/schema/测试 prompt/Host-Engine-Tool source owner 修正 | R03 | ordinary/awaiting 同一 request atom；全 LLM source scan |
| Topic 4；Codex F-12、DS F-02 | accepted：opaque ref 仅 internal provenance；未知/拼错/internal ref 不进入 LLM material；不创建 `BusinessSource` | R03 | RunInput/Memory/Compact/LLM trace propagation tests |
| Topic 5；Codex F-02 | accepted：provider resolution mode 与 Host poll policy 分置 config；Service 不按 scene 造 policy；observation timeout release/backoff 且非 LOST；已接受 awaiting 不受 handshake timeout | R04、R05 | config/composition matrix；state-transition tests；Engine regression |
| Issue 175 | deferred：Fins 长事务进程隔离 | Issue 175 owner | R05 不改变 long-operation executor ownership |
| Topic 6.1；Codex F-08 | accepted：唯一显式 batch authority | R06 | 无 ContextVar/task/thread authority；原子事务测试 |
| Topic 6.2；Codex F-09 | accepted：commit 一次发布完整 source，业务 meta 不作 staging ack | R06 | reader 不见半文档；失败/取消 rollback |
| Topic 6.3；Codex F-10 | accepted：storage-owned provenance、revision、snapshot；read 只消费 snapshot | R07 | concurrent snapshot/cache/citation tests |
| Topic 6.4；Codex F-11 | accepted：最小 financial/XBRL contract，移除 diagnostic/public duplication | R08 | producer contract + schema/LLM projection tests |
| Topic 6.5；Codex F-20 | accepted：单一 Fins terminal validator | R09 | 三层只有一处 protocol decision |
| Topic 6.6；Codex F-21 | accepted：HKEX official cumulative `rowRange` 续取到完整 | R10 | 多轮累计、变动总数、矛盾响应 tests/smoke |
| Topic 6.7；Codex F-22 | accepted：opaque external id→storage-owned key mapping；containment 保留 | R07 | Unicode/层级/逃逸/round-trip tests |
| Topic 7.1；Codex F-17 | accepted：OLD-aligned shell/cmd workflow；删除 JSON argv public schema | R11 | 跨平台 quoting 与 POSIX 实执行 smoke |
| Topic 7.2；Codex F-18 | accepted：删除未实现 Web/WeChat/render scripts、packages、grammar、README、tests | R11 | packaging/help/import surface scan |
| Topic 7.3；Codex F-19 | accepted：恢复 OLD-aligned、current-schema init；保留并补齐 lock/containment/confirmation/atomic swap | R12 | temp HOME/workspace 与并发/中断 smoke |
| Issue 142 / 151 | deferred：workspace migration；future write/product assets | 各 issue owner | R12 不创建/搬入`dayu/assets`或产品assets，不迁移旧schema；仅为未来Issue151 owner保留同一managed-root manifest扩展边界 |
| Topic 8；DS F-DS-04 | no code：保留 Engine 240 字符异常消息策略 | aggregate guard | exact regression 不变；diff 中无相关修改 |
| Codex F-13 / DS 对 128-char runner-specific code 的非 finding | no code：controller 未纳入修复；不得借 Topic 8 扩域 | aggregate guard | `error_codes.py` 无无关 diff |
| Topic 9 | no code：不实现统一授权；保留现有局部权限与 I/O 防御 | 每个 sub-WU security guard | retained behavior matrix 全绿 |

## 5. Owner map 与内部 sub-WU 切分

计划建议 **12 个**内部 remediation sub-WU：

| ID | 语义 owner / 目标 | Topic | failure blast radius | slices |
| --- | --- | --- | --- | --- |
| R01 | Documents source snapshot + Doc result producer | 1 | 所有文档读/section/list/search | 2 |
| R02 | Web provider config + HTTP/browser/diagnostic executors | 2 | 外网、内网、proxy、浏览器、CI 诊断 | 3 |
| R03 | Host accepted-call/evidence LLM projection | 3、4 | durable event、resume、Memory、Compact、trace | 3 |
| R04 | Tool provider resolution config + Host runtime composition | 5 config | 所有 awaiting provider 的 poll/callback/manual 装配 | 3 |
| R05 | Host wait observation state machine + Engine handshake regression | 5 behavior | durable wait 状态、claim、late publication | 2 |
| R06 | Fins storage transaction + complete source publication | 6.1、6.2 | 全部 ingest producer 与仓储原子性 | 3 |
| R07 | Fins storage snapshot/revision/opaque identity + read projection | 6.3、6.7 | storage layout、read cache、citation | 3 |
| R08 | Fins financial/XBRL domain contracts | 6.4 | processor/tool public schema 与 LLM 质量语义 | 2 |
| R09 | Fins direct-stream terminal validator | 6.5 | Fins→Service→CLI 终态 | 2 |
| R10 | HKEX cumulative discovery | 6.6 | 港股 filing completeness | 1 |
| R11 | CLI upload script workflow + placeholder surface removal | 7.1、7.2 | 安装脚本、用户命令、packaging surface | 3 |
| R12 | CLI init workflow | 7.3 | workspace config、secret persistence、atomic reset | 3 |

没有 sub-WU 超过 3 个 implementation slices，因此无需容量例外。R03 合并 Topic 3/4，是因为二者共享同一 accepted-evidence LLM projection 和四个 downstream consumers；拆开会产生暂时把 opaque ref 暴露给新参数投影或反向重复修改的中间态。R06 合并 batch authority 与 source publication，是因为 transaction commit point 必须和 complete source 的唯一可见点同时切换。R07 合并 revision/snapshot 与 opaque ID mapping，是因为二者共同改变 storage path/read snapshot layout；分两次会要求同一 fresh schema 和全 producer/read migration 重做两遍。其余边界按独立 durable state、public contract、真实入口或可独立回滚风险拆开，而不是按文件或 raw finding 机械拆分。

## 6. 依赖图与 sequencing

```text
R01  Doc complete input ───────────────────────────────────────┐
R02  Web config -> HTTP/browser/diagnostics ──────────────────┤
R03  accepted-call owner -> LLM projections ─────────────────┤
R04  provider mode config -> Host composition ──> R05 wait behavior
R06  Fins transaction -> complete publication ──> R07 storage snapshot/id -> R08 domain/read contract
                                                ├─────────────> R09 terminal validator
                                                └─────────────> R10 HKEX producer
R06 ──> R11 upload plan/script ─────────────────────────────────┐
R08/R09/R11 ───────────────────────────────────────────────────> R12 init/docs/smoke awareness
all R01-R12 ──> aggregate tests ──> aggregate deepreview ──> PR gates ──> final closeout
```

Sequencing 规则：

1. **config contract → composition/runtime → behavior**：R04 必须先让 provider mode 与 Host policy 具有显式配置真源，R05 才能改变 timeout 状态机；R02 每个 slice 也按 config parser→transport/browser→diagnostics 顺序。
2. **Fins storage transaction → producer migration → read projection**：R06 先建立唯一 transaction/commit point并一次发布完整 source；R07 才能定义 storage snapshot/revision/key；R08/R09/R10 再消费稳定 storage/domain boundary。
3. **Fins domain contract → consumer**：R08 先改 producer contract，再改 tool schema/LLM read projection，禁止 read side补造字段。
4. **Fins validator → Service/CLI consumer**：R09 owner 先落地，再删除 Service/CLI duplicate scanner，任何时间不得形成“零 validator”的可合并 commit。
5. **CLI init/upload contract → docs/smoke**：R11/R12 先形成真实行为，再更新 help/README 和跨平台 smoke；文档不能先承诺未实现 surface。

所有 sub-WU 都在当前 `phaseflow/host-issues-control` 工作分支按 `R01 -> R02 -> ... -> R12` 串行推进；不得为 R01/R02/R03 或其它 sub-WU 创建独立实施分支，也不得通过 rebase 汇总。每个下一 sub-WU 都以前一 sub-WU 的 controller accepted local commit 为 base，因此 R04→R05、R06→R07→R08→R09→R10→R11→R12 的硬依赖天然满足；无硬依赖只表示子计划无需等待额外产品 contract，不授权并发写共享工作区。唯一允许的并发是同一 immutable review target 上的 AgentMiMo / AgentDS 两路 reviewer。R01 completion report 的 Doc LLM-facing 删除/保留清单必须作为 R03 人工 source inventory 的显式输入，R03 不得回改 R01 owner 或重复发明删除规则。

## 7. 所有 slice 共用的实施与验证协议

### 7.1 Slice transaction

每个 slice 都是一个可审 diff 单元，按以下顺序执行：

1. 记录 slice base SHA、允许文件集合与 control doc 中既有 baseline failure registry 快照；禁止创建新的平行 failure registry。
2. 先写/更新 owner-level contract tests，再修改 owner 与直接消费者；不接受仅改 fixture 使旧行为继续通过。
3. 运行该 slice 列出的 targeted tests；再对所有 changed production files 做单文件覆盖率检查，目标 `>=80%`。
4. 运行全仓 `pyright`。若 baseline 已有失败，只能按第 7.2 节证明与本 slice 同指纹；触及的旧报错必须修复，任何新增/扩散立即 stop。
5. 运行 `git diff --check`、allowed-file diff scan、LLM/source/security propagation scan。
6. 读取每个命中 README 的 `Agent更新约束【必须遵守】`，作出“更新/无需更新 + 证据”决定；README 修改与该 sub-WU 最后一个 slice 同一 review closure。
7. 完成 sub-WU 全部 slice 后运行真实入口或跨平台 smoke、两路独立完整 code review；所有 finding 先由 controller 裁决。任何 severity 的 `accepted` actionable finding 都由 AgentCodex 修复，随后两路 reviewer 重新审完整 sub-WU 最终 diff；`rejected-with-reason`、`deferred-with-owner`、note 不进入 fix，也不得被顺手实现。

通用命令模板（`<targets>`、`<changed-files>` 和 `<allowed-regex>` 必须替换成各 slice 下的精确值）：

```bash
source .venv/bin/activate
pytest <targets>
coverage run --data-file=workspace/tmp/.coverage-<slice> -m pytest <targets>
coverage report --data-file=workspace/tmp/.coverage-<slice> --include='<changed-production-files>' --fail-under=80
pyright
git diff --check
git diff --name-only <slice-base> -- | rg -v '<allowed-regex>'
```

最后一条预期 **无输出**。若 coverage 工具按文件合并显示，必须用 `coverage json` 核对每个 changed production file，不能用总体覆盖率掩盖低覆盖文件。`dayu/render/` 与 `utils/` 脚本虽按仓库规则可免覆盖率，R02 仍要求 diagnostics lifecycle 删除与 smoke 行为测试。

### 7.2 Baseline failure registry 复用

- 只复用 `docs/host/issues-implementation-control.md` 已有 baseline registry；implementation agent 不另建 artifact、不把新失败登记成 baseline。
- sub-WU 开始时按“命令、test/node、错误类型、首个稳定栈帧/pyright rule、文本指纹、基线 SHA”匹配。只有六项均相同且 changed files/source propagation 与该失败无交集，才可标为 inherited。
- 任一数量增加、node 改变、错误位置进入 changed owner、指纹变化或同一失败从 warning 变 error，都视为新增/扩散并触发 stop。
- 修掉触及范围内的旧失败后，不得恢复；把 baseline delta 写入 sub-WU completion report，由 umbrella controller 更新唯一 registry。

### 7.3 每个 sub-WU 的统一完成、stop 与 handoff

本文不是 R01—R12 任一 sub-WU 的 plan artifact。每个 sub-WU 都必须独立、完整、不可折叠地执行以下状态机；即使 umbrella 总计划、相邻 sub-WU 或 aggregate review 已讨论过相同模块，也不能跳过：

```text
controller entry / previous accepted commit
  -> sub-WU code-generation-ready plan
  -> AgentMiMo + AgentDS 双路独立 plan review（只并发读同一 immutable target）
  -> controller finding adjudication
  -> AgentCodex plan fix：修复全部 controller-accepted finding，不限 severity
  -> AgentMiMo + AgentDS 双路完整 plan re-review
  -> controller accepted-plan decision + accepted plan local commit
  -> implementation（按 approved slices 串行）
  -> AgentMiMo + AgentDS 双路独立完整 code review
  -> controller finding adjudication
  -> AgentCodex code fix：修复全部 controller-accepted finding，不限 severity
  -> AgentMiMo + AgentDS 双路完整 code re-review
  -> controller accepted-sub-WU decision + accepted sub-WU local commit
  -> handoff to next numbered sub-WU
```

- **umbrella baseline 与 accepted sub-WU plan 的时序执行真源（本计划唯一规范位置）**：
  1. 在某个 sub-WU 的 accepted-plan local commit 产生前，本文拥有该 sub-WU 的边界、顺序、全局不变量、最低验证意图，以及第 7.4 节 production allowlist、第 7.5 节和各 Rxx 正文给出的 per-slice 文件集合、测试命令/test node、coverage 与 scan 的 mandatory starting baseline。这些基线是后续独立 plan 必须消费的最低输入，不是跳过 sub-WU plan、review 和 accepted-plan commit 的直接实施授权。
  2. 每个 sub-WU plan 必须在其实际 base 上重新核对真实文件、test node、slice 原子性和 propagation/source/security scan。只有该 plan 完成双路 review、controller adjudication、accepted finding fix、双路完整 re-review并由 controller 创建 accepted-plan local commit 后，该 commit 中的 plan 才成为该 sub-WU 对 exact slice、文件、命令、test node 与 scan 的唯一 execution truth；本文继续独占 sub-WU 边界、顺序、全局不变量和最低验证意图，不与 accepted sub-WU plan 形成第二份 exact 执行真源。
  3. sub-WU plan 必须逐项记录 umbrella baseline 到 accepted-plan exact 项的 `保留 | 基于直接代码证据细化 | 以等价验证替换` 映射；任何差异都必须附真实调用链、文件或 test collection 证据，baseline 项不得静默遗漏。细化或等价替换不得弱化 controller accepted contract、retained security、changed production file 逐文件覆盖率 `>=80%`、全量 pyright、README decision、真实/跨平台 smoke 或 LLM/source/security propagation scan。
  4. 若重新核对发现语义 owner、依赖、production allowlist 或 controller accepted contract 发生实质变化，sub-WU plan 必须停止并回到 controller 裁决；不得以调整 exact slice/命令为名静默扩域、改变 owner 或重写 accepted contract。
- **review/fix 不变量**：两路 reviewer 只可并发 review，不可并发修改共享工作区。每次 controller adjudication 把每个 finding 且只把它裁决为 `accepted`、`rejected-with-reason`、`deferred-with-owner` 或 `needs-more-evidence`。AgentCodex 只修 `accepted`；任一 severity 均不得过滤。若某轮零 accepted finding，fix artifact 记录 zero-change/no-fix evidence；双路 re-review 仍检查最终完整 plan 或完整 sub-WU diff，而不是只看补丁 hunk。`needs-more-evidence` 未裁决前不得进入下一 gate。
- **artifact naming**：Rxx 的 `<rxx-slug>` 由其独立 plan 固定为 `rxx-<short-owner-name>`；同一 sub-WU 后续不得换 stem。最少产出以下闭集，花括号表示必须分别存在两份而不是一份合并文件：

  ```text
  docs/host/wu-semantic-ownership-01-<rxx-slug>-plan.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-plan-review-{mimo,ds}.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-plan-review-controller-adjudication.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-plan-fix-codex.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-plan-rereview-{mimo,ds}.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-plan-rereview-controller-adjudication.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-implementation-codex.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-code-review-{mimo,ds}.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-code-review-controller-adjudication.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-code-review-fix-codex.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-code-rereview-{mimo,ds}.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-code-rereview-controller-adjudication.md
  docs/reviews/wu-semantic-ownership-01-<rxx-slug>-completion.md
  ```

  零修改 fix gate也必须在相应 fix artifact写明依据，不得用 conversation-only pass 替代 artifact。若独立plan批准多个implementation slices，可在`implementation`与`code-review/fix/rereview`文件名中加入`-sN-`，但每个sub-WU最终仍必须对完整diff执行本节的两路code review/re-review并形成单一accepted sub-WU commit。
- **plan entry criteria**：当前分支是 `phaseflow/host-issues-control`；前一 numbered sub-WU 已有 controller accepted local commit；本 sub-WU owner、允许文件、依赖、success signal 和 residual destination 可由本计划与直接代码证据确定。R01 的 LLM-facing 删除清单是 R03 的 mandatory input。
- **implementation entry criteria**：本 sub-WU 独立计划已双 re-review，所有 accepted plan finding 状态为“已修复”，无 blocking question；controller 已创建 accepted plan local commit。umbrella 本文通过 re-review 不等于任何 Rxx 通过 plan gate。
- **完成信号**：全部 approved slices、targeted/owner/consumer tests、changed-file coverage、全量 pyright、diff/scan、README decision、真实 smoke 通过；两路完整 code re-review 已确认所有 accepted code-review finding（不限 severity）已修复且无新 material finding；controller 创建只含本 sub-WU 授权文件的 accepted local commit。R11 的 Windows 实际 runner 例外只允许按第 18/22 节作为显式 release-blocking gate 延迟到 aggregate/PR check，不能降级为 residual。
- **stop condition**：owner 不清、设计与 controller 冲突、需要越界 issue、出现无法同源的中间 schema、retained security 失败、新/扩散 baseline、allowed files 外 diff、accepted finding 未闭合或 Windows release blocker 未被追踪时立即停止，不以 fallback/兼容 shim 继续。
- **handoff**：按“sub-WU/plan与实现 accepted commit SHA/owner contracts/删除 contracts/验证命令与结果/coverage/pyright/baseline delta/README/smoke/双 plan+code review/fix/re-review artifacts/所有 finding 最终状态/residual risks/下一依赖”格式交给 umbrella controller。AgentCodex/reviewer不得 commit、开启下一 sub-WU 或进入 PR；accepted local commit 和 gate 状态更新只由 controller 执行。

### 7.4 Closed affected-module manifest

下表是 production/config/package 的闭集；各 sub-WU正文中的“必要/相关”只能指向本行已经列出的文件。implementation若需本行外生产文件，必须先以真实调用链证据回到 plan review，不得现场扩域。测试与README闭集在各sub-WU正文列出。

| sub-WU | allowed production/config/package files |
| --- | --- |
| R01 | `dayu/documents/processors/bounded_source.py`（原地改，或同slice删除并新增`source_snapshot.py`）、`dayu/documents/processors/__init__.py`、`dayu/documents/__init__.py`、`dayu/tools/doc_tools.py`、`dayu/tools/doc_provider.py` |
| R02 | `dayu/config/tool_discovery.json`；`dayu/tools/web/provider.py`、`web_egress_policy.py`、`web_resource_budget.py`、`web_http_session.py`、`web_playwright_backend.py`、`web_tools.py`、`web_fetch_orchestrator.py`、`web_recovery.py`、`web_diagnostics.py`、`web_tool_projection_text.py`、`web_search_projection.py`；`utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`、`utils/diag_web_batch.sh` |
| R03 | `dayu/host/evidence.py`、`_event_payload.py`、`tool_runtime.py`、`waiting.py`、`accepted_result_projection.py`、`run_input.py`、`compact_material.py`、`durable/memory.py`、`tool_trace.py`、`durable/tool_trace.py`、`tool_trace_signals.py`；只有source scan证明现有文本owner错误时才允许 `dayu/config/prompts/base/*.md`、`prompts/scenes/*.md`、`dayu/tools/doc_tools.py`、`dayu/tools/web/web_tools.py`、`dayu/fins/tools/fins_tools.py`、`download_tools.py`、`preprocess_tools.py`、`upload_tools.py`，无证据则这些候选必须无diff |
| R04 | `dayu/config/tool_discovery.json`、`host_runtime.json`、`dayu/runtime/config_loader.py`；`dayu/fins/tools/download_provider.py`、`preprocess_provider.py`、`upload_provider.py`、`_ingestion_tool_helpers.py`；`dayu/service/host_assembly.py`、`entrypoint_runtime.py`、`fins_wait_adapter.py` |
| R05 | `dayu/host/_wait_observation.py`、`wait_adapter.py`、`waiting.py`；`dayu/engine/agent.py`仅在回归先证明现有实现错误时允许，否则必须无diff |
| R06 | `dayu/fins/domain/document_models.py`；`dayu/fins/storage/repository_protocols.py`、`_fs_storage_infra.py`、`_fs_storage_core.py`、`_fs_repository_factory.py`、`_fs_blob_core.py`、`_fs_company_meta_core.py`、`_fs_maintenance_core.py`、`_fs_processed_core.py`、`_fs_source_document_core.py`、`fs_batching_repository.py`、`fs_company_meta_repository.py`、`fs_document_blob_repository.py`、`fs_filing_maintenance_repository.py`、`fs_processed_document_repository.py`、`fs_source_document_repository.py`；`dayu/fins/ingestion_runtime.py`；pipelines `cn_download_company_meta.py`、`cn_download_filing_workflow.py`、`cn_download_rebuild.py`、`cn_download_source_upsert.py`、`docling_upload_service.py`、`sec_6k_primary_document_repair.py`、`sec_company_meta.py`、`sec_download_filing_workflow.py`、`sec_download_persistence.py`、`sec_download_source_upsert.py`、`sec_rebuild_workflow.py`、`upload_company_meta.py` |
| R07 | `dayu/fins/domain/document_models.py`；storage中R06列出的全部core/repository，加`_fs_storage_utils.py`、`_fs_identity.py`（新增）、`local_file_source.py`、`local_file_store.py`、`file_store.py`；`dayu/fins/tools/read_runtime.py`、`read_runtime_helpers.py`、`cache.py`；`dayu/fins/processors/registry.py`、`source_text.py`、`fins_docling_processor.py`、`fins_markdown_processor.py` |
| R08 | `dayu/fins/domain/financial_result_contract.py`、`xbrl_result_contract.py`；processors `financial_base.py`、`html_financial_statement_common.py`、`report_form_financial_statement_common.py`、`sec_report_form_common.py`、`bs_report_form_common.py`、`six_k_form_common.py`、`sec_processor.py`、`bs_six_k_processor.py`、`sec_xbrl_query.py`；tools `read_runtime.py`、`read_runtime_helpers.py`、`result_types.py`、`fins_tools.py`、`error_contract.py` |
| R09 | `dayu/fins/direct_events.py`、`direct_stream.py`（新增）、`ingestion_runtime.py`；`dayu/service/fins_direct.py`；`dayu/cli/commands/fins.py` |
| R10 | `dayu/fins/downloaders/hkexnews_downloader.py`；若typed response必须跨模块复用，只允许已有 `dayu/fins/pipelines/cn_download_models.py` |
| R11 | `dayu/fins/upload_batch.py`；`dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`、`dayu/cli/upload_script.py`（新增）；`pyproject.toml`；删除 `dayu/web/**`、`dayu/wechat/**`、`dayu/render/**` placeholder files |
| R12 | `dayu/cli/commands/init.py`、`dayu/cli/arg_parsing.py`、新增 `init_catalog.py`、`init_environment.py`、`init_workspace.py`；`dayu/runtime/filelock.py`、`config_loader.py`；`dayu/config/models.json`与 `dayu/config/prompts/manifests/*.json` |

### 7.5 Per-slice verification substitution matrix

本节不另设执行真源；全部字段按第 7.3 节的唯一时序规则解释。这里和各 Rxx 正文列出的命令、test node、文件集合、coverage `--include` 与 scan 是基于当前代码证据的 mandatory starting baseline；later accepted sub-WU plan 必须逐项映射并核实，只有其 accepted-plan commit 后的 exact 项才支配该 sub-WU implementation。每个slice先使用正文中的精确`pytest`命令作为7.1 `<targets>`、使用下表 `--include` 作为changed-file coverage上界；随后仍需从coverage JSON逐个核对实际changed production file。每行都必须执行全量`pyright`、`git diff --check`、基于7.4闭集的allowed-file scan，并记录README decision。表中scan命令允许“期望零命中”；`rg`退出1表示零命中而非测试失败，但命中必须逐条解释。

| slice | coverage `--include` | mandatory source/propagation scan | README decision |
| --- | --- | --- | --- |
| R01-S1 | `dayu/documents/processors/*source*.py,dayu/tools/doc_tools.py` | `rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded' dayu tests` | documents无README；config/tests，根按文本 |
| R01-S2 | `dayu/tools/doc_tools.py` | `rg -n 'directory_entry_limit|source_limit|skipped_oversized_files|10_000' dayu tests README.md` | config/tests/根 |
| R02-S1 | `dayu/tools/web/provider.py,dayu/tools/web/web_egress_policy.py,dayu/tools/web/web_resource_budget.py` | 旧flat七字段/default数值与新group字段双向scan | config/tests |
| R02-S2 | `dayu/tools/web/web_http_session.py,dayu/tools/web/web_playwright_backend.py,dayu/tools/web/web_tools.py,dayu/tools/web/web_fetch_orchestrator.py` | private/custom/proxy/peer/browser每个config字段只有一个parser owner与对应consumer | config/tests |
| R02-S3 | `dayu/tools/web/web_diagnostics.py,utils/diagnose_web_access.py,utils/smoke_web_ci.py` | `rg -n 'ttl|orphan|expired|owner_filename|reconcile|storage.state.lifecycle|0700|0600' utils/diagnose_web_access.py tests/tools/web` | config/tests/根诊断工作流 |
| R03-S1 | `dayu/host/tool_runtime.py,dayu/host/waiting.py,dayu/host/_event_payload.py,dayu/host/run_input.py` | ordinary/awaiting `TOOL_CALL_REQUESTED` builder调用点与`TOOL_AWAITING` args/digest scan | Host/Engine/tests |
| R03-S2 | `dayu/host/accepted_result_projection.py,dayu/host/_event_payload.py,dayu/host/durable/memory.py,dayu/host/compact_material.py,dayu/host/run_input.py,dayu/host/tool_trace.py` | 人工逐文件 LLM source inventory/audit + `rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|unsafe.argument' dayu tests` 等自动门禁；grep不是完整性证明 | Host/config/tests；Engine按diff |
| R03-S3 | `dayu/host/evidence.py,dayu/host/accepted_result_projection.py,dayu/host/durable/memory.py,dayu/host/compact_material.py,dayu/host/run_input.py,dayu/host/tool_trace.py,dayu/host/durable/tool_trace.py` | `_INTERNAL_SOURCE_REF_KINDS|kind:id`及event/payload/digest/cursor/tool_call_id进入LLM renderer scan | Host/tests |
| R04-S1 | `dayu/fins/tools/*provider.py,dayu/fins/tools/_ingestion_tool_helpers.py` | provider mode不得从tool name/scene反推 | Fins/config/tests |
| R04-S2 | `dayu/runtime/config_loader.py,dayu/host/wait_adapter.py` | 30/5/8等数值只在`host_runtime.json`与测试expected snapshot | Host/config/tests |
| R04-S3 | `dayu/service/host_assembly.py,dayu/service/entrypoint_runtime.py,dayu/service/fins_wait_adapter.py` | `with_entrypoint_wait_poller_policy`与scene-derived policy零残留 | Service/Host/config/tests |
| R05-S1 | `dayu/host/_wait_observation.py,dayu/host/wait_adapter.py,dayu/host/waiting.py` | timeout→LOST/resolve operation零残留；late publish token路径唯一 | Host/tests |
| R05-S2 | `dayu/engine/agent.py,dayu/host/waiting.py` | accepted awaiting后不得再读`tool_execution_timeout_seconds` | Engine/Host/tests |
| R06-S1 | `dayu/fins/domain/document_models.py,dayu/fins/storage/*.py` | `ContextVar|owner_scope|owner_token|current_task|thread.*ident|auto_batch` | Fins/tests |
| R06-S2 | `dayu/fins/storage/_fs_source_document_core.py,dayu/fins/storage/_fs_blob_core.py,dayu/fins/storage/_fs_storage_infra.py` | `stage_source_document|ingest_complete.*false` | Fins/tests |
| R06-S3 | `dayu/fins/ingestion_runtime.py,dayu/fins/pipelines/*.py` | 所有repository mutation调用均显式`batch=`；begin/commit owner逐flow计数 | Fins/tests |
| R07-S1 | `dayu/fins/storage/_fs_identity.py,dayu/fins/storage/_fs_storage_utils.py,dayu/fins/storage/_fs_*core.py` | raw ticker/document id参与Path join零残留；containment/symlink仍有调用 | Fins/tests |
| R07-S2 | `dayu/fins/domain/document_models.py,dayu/fins/storage/_fs_source_document_core.py,dayu/fins/storage/repository_protocols.py` | revision只有storage生成；consumer field-hash零残留 | Fins/tests |
| R07-S3 | `dayu/fins/tools/read_runtime.py,dayu/fins/tools/read_runtime_helpers.py,dayu/fins/tools/cache.py` | revision-before/after、path/provider guessing与LLM revision零残留 | Fins/tests |
| R08-S1 | `dayu/fins/domain/*result_contract.py,dayu/fins/processors/*.py` | 限定 internal producer validation/diagnostic types 扫描并逐条归属 raw `total`；financial/public路径 `statement_locator|statement_method_missing` 零残留 | Fins/tests |
| R08-S2 | `dayu/fins/tools/read_runtime.py,dayu/fins/tools/read_runtime_helpers.py,dayu/fins/tools/result_types.py,dayu/fins/tools/fins_tools.py` | public/LLM `statement_locator|raw_total|deduped_fact_count|去重前total`零残留；`fact_count == len(deduplicated facts)`且唯一 | Fins/tests |
| R09-S1 | `dayu/fins/direct_events.py,dayu/fins/direct_stream.py,dayu/fins/ingestion_runtime.py` | terminal protocol decision只在validator | Fins/tests |
| R09-S2 | `dayu/service/fins_direct.py,dayu/cli/commands/fins.py` | Service/CLI无missing/duplicate/event-after-result构造分支 | Service/Fins/根按用户错误/tests |
| R10-S1 | `dayu/fins/downloaders/hkexnews_downloader.py` | 只解析`hasNextRow|loadedRecord|recordCnt|rowRange`，无generic total/date recursion/fixed cap | Fins/tests |
| R11-S1 | `dayu/fins/upload_batch.py` | 分类/财期/优先级/上限不得出现在CLI renderer | Fins/tests |
| R11-S2 | `dayu/cli/commands/fins.py,dayu/cli/arg_parsing.py,dayu/cli/upload_script.py` | `schema_version.*commands|JSON argv`零残留；platform quoting owner唯一 | 根/Fins/tests |
| R11-S3 | `pyproject.toml,dayu/web/*,dayu/wechat/*,dayu/render/*` | `dayu-web|dayu-wechat|dayu-render` package/help/README零残留 | 根/tests |
| R12-S1 | `dayu/cli/init_catalog.py,dayu/cli/init_environment.py,dayu/cli/commands/init.py` | catalog列表单一；secret值进入JSON/log/prompt零残留 | 根/config/tests |
| R12-S2 | `dayu/cli/init_workspace.py,dayu/cli/commands/init.py,dayu/runtime/filelock.py` | 每个mutation都在同一lock/containment/swap路径；旧schema merge零残留 | 根/config/tests |
| R12-S3 | `dayu/cli/commands/init.py,dayu/runtime/config_loader.py` | prewarm无network且只first/reset；当前不创建/搬入/删除用户自建assets，不新增Issue142 migration | 根/config/tests |

## 8. R01 — Doc 输入完整性与结果 contract 收敛

### 8.1 Owner、依赖与允许范围

- **owner**：`dayu.documents.processors` 拥有一次性可重读 source snapshot；`dayu.tools.doc_tools` 拥有 Doc tool schema/result/error 与目录完整遍历。Host 的 `ToolTruncateSpec` 只拥有输出结果截断，不能反向成为输入 byte/entry cap。
- **依赖**：无；可最先实施。
- **允许生产模块**：`dayu/documents/processors/bounded_source.py`（若移除 bound 后应同 slice 重命名为语义准确的 `source_snapshot.py`，禁止兼容 re-export）、`dayu/documents/processors/__init__.py`、`dayu/documents/__init__.py`、`dayu/tools/doc_tools.py`、必要的 `dayu/tools/doc_provider.py`。
- **允许测试/文档**：`tests/documents/test_processors.py`、`tests/tools/test_doc_tools_provider.py`、相关 import-boundary/package-export tests；按触发决策更新 `dayu/config/README.md`、`tests/README.md`，仅当根 README 实际描述被删 cap/error 时更新根 `README.md`。

### 8.2 输入、输出、删除/保留 contract

- **输入**：provider 已授权的 `Source`、file/directory/pattern/recursive 参数、cancellation token、Host 注入的结果 `ToolTruncateSpec`。
- **输出**：完整扫描事实与已有 output-limit 截断事实；读取/section/search 的业务结果或既有 typed I/O/解析错误。
- **必须删除**：`DocResourceBudget`、32 MiB/10,000 常量、`SourceBudgetExceeded`、declared/observed source size hard-fail、`source_budget_exceeded`/同义 error、`directory_entry_limit`、`source_limit`、`skipped_oversized_files`、oversized skip 分支以及所有相关 LLM-facing description/hint/test prompt/assertion。
- **必须保留**：`allowed_paths`、resolved containment/symlink guard、cancellation、一次性 source 的 seekable spool/materialization、每次 processor 独立 cursor、输出 `result_limit`/Host truncation contract。spool memory threshold 是内部性能细节，不是业务输入 cap。

### 8.3 真实入口、data flow 与不变量

```text
tool_discovery.json
  -> dayu.tools.doc_provider.discover_tools
  -> doc_tools tool definition/callable
  -> Source -> SourceSnapshot(context manager)
  -> selected processor / list_files / search_files
  -> complete input observation
  -> ToolTruncateSpec applies only to returned result
  -> typed tool outcome -> Host ToolRuntime
```

状态只允许 `new -> active -> closed`；`close` 幂等，active 时每次 `open()` 获得独立 cursor。任何 source 长度都不得产生 budget terminal/partial/skip；I/O、decode、unsupported format 仍按各自 owner 的 typed error 失败。目录遍历必须 deterministic（统一稳定排序），遍历所有授权 entry 后才声明 complete；只有返回结果数量达到 output limit 才能出现既有 result truncation。取消立即终止且不伪造 complete。

### 8.4 Implementation slices

#### R01-S1 — 去除 source byte budget，保留无业务上限 snapshot

- 把 snapshot contract 改成只解决“一次性 Source 可供 processor 多次稳定读取和清理”的 `SourceSnapshot`；删除 declared-length 与 `limit+1` 判定、budget exception 和错误映射。
- exact call path：`read_file/read_file_section/get_file_sections -> _source_snapshot -> processor -> snapshot.open/materialize`；所有调用点不再传 `max_source_bytes`。
- error handling：source open/read/temp materialization 的真实异常映射保持；不得把异常改名为“过大”，不得接 Issue 177。
- tests：

```bash
pytest tests/documents/test_processors.py tests/tools/test_doc_tools_provider.py -k 'source or read_file or section'
```

必须断言：声明长度大但实际小、无声明长度的大 source、超过旧 32 MiB 的 source 都进入 processor；取消与 cleanup 生效；`rg -n 'DocResourceBudget|SourceBudgetExceeded|32.?MiB|source_budget_exceeded|max_source_bytes' dayu tests` 对 remediation 范围无残留。按 7.1 对本 slice changed files 做 coverage/pyright/diff。

#### R01-S2 — 完整目录扫描并删除 partial/LLM contract

- 删除 entry counter break 与 oversized-file skip；`list_files/search_files` 稳定排序后完整遍历授权树，输出截断只由现有 result limit 表达。
- exact call path：`list_files/search_files -> allowed root resolution -> stable recursive/nonrecursive iterator -> all eligible files -> match/decode -> result truncation projection`。
- tests：

```bash
pytest tests/tools/test_doc_tools_provider.py -k 'list_files or search_files or schema or description'
```

必须断言：匹配项位于旧 10,000 边界之后仍可见；不同创建顺序得到相同结果；超过旧 32 MiB 的可搜索文本不被 skip；tool schema/description 不出现 `source_limit`、`directory_entry_limit`、`skipped_oversized_files` 或“较小文件”；`allowed_paths`、symlink/containment 与 result-limit tests 仍绿。

### 8.5 完成与 handoff 特有信号

- 真实 smoke：在临时 allowed root 创建 `>10,000` 个小文件和一个 `>32 MiB` 可解析文本，真实 discovery→tool callable 验证尾部命中；另验证 escaped/symlink 路径仍拒绝。
- README：`dayu/config/README.md` 仅删除实际存在的预算说明；`tests/README.md` 更新大输入/完整扫描测试意图；根 README 无相关文本则记录“无需更新”。
- handoff 到 R03/aggregate：逐文件列出全部 Doc tool name/description/参数/枚举/错误说明、真实 LLM prompt fixture 与其它 LLM-facing 文本中被删除、保留或改写的项，记录 source owner 和最终 disposition；该清单是 R03 人工 source inventory 的必填输入。不得只交一条 grep 结果，也不得声称 Issue 177 已完成。

## 9. R02 — Web 配置、网络能力与 diagnostics 收敛

### 9.1 Owner、依赖与允许范围

- **owner**：`tool_discovery.json`/Web provider parser 拥有部署默认；HTTP transport 拥有 attempt-local DNS/peer/proxy enforcement；browser backend 拥有 browser capability；HTTP/browser/diagnostics 分别拥有自己的资源预算；diagnostics v2 producer 拥有诊断 schema。credential storage-state lifecycle 属于 Issue 178。
- **依赖**：无；内部必须 `config -> executors -> diagnostics cleanup`。
- **允许生产模块**：`dayu/config/tool_discovery.json`、`dayu/tools/web/provider.py`、`web_egress_policy.py`、`web_resource_budget.py`、`web_http_session.py`、`web_playwright_backend.py`、`web_tools.py`、`web_fetch_orchestrator.py`、`web_recovery.py`、`web_diagnostics.py`、必要的 `web_tool_projection_text.py`/`web_search_projection.py`，以及 `utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`。
- **允许测试/文档**：`tests/tools/web/test_web_tools_provider.py`、`test_diagnose_web_access.py`、`test_smoke_web_ci.py`；`dayu/config/README.md`、`tests/README.md`，根 README 仅在诊断 CLI 用户工作流变化时更新。

### 9.2 新 config contract 与保留/删除项

packaged Web provider 必须显式给出：

```json
{
  "allow_private_network_url": true,
  "allow_custom_port_url": true,
  "dns_peer_proof_enabled": false,
  "allow_environment_proxy": true,
  "browser_enabled": true,
  "playwright_channel": "<existing value>",
  "playwright_storage_state_dir": "<existing value>",
  "resource_budget": {
    "http": {"wire_body_bytes": 134217728, "decoded_body_bytes": 268435456},
    "browser": {"warmup_body_bytes": 1048576, "dom_chars": 16777216, "text_chars": 8388608},
    "diagnostics": {"error_chars": 8192, "events": 512}
  }
}
```

typed parser 允许按 owner group 和 field **局部 override**，未给字段取代码中与 packaged config 同值的 typed default；未知字段、bool-as-int、非正数仍拒绝。HTTP、browser、diagnostics 使用三个小 dataclass；可有只负责组合而不重复规则的 aggregate snapshot，禁止恢复七字段 complete-object god schema。

这些数值是本 remediation 的初始 Tool-config safety ceilings：HTTP wire/decoded 分别为 128/256 MiB，browser warmup 为 1 MiB、DOM/text 为 16/8 Mi characters，diagnostic error/event为 8 Ki characters/512。它们相较旧值显著放大以容纳财报页面，但仍阻止不可信远端输入无限占用内存；它们不表示业务结果 complete，也不进入 LLM 文本。若 plan review不能从现有 Web fixture/真实财报smoke证明这些 ceiling足够，必须在 R02 implementation 前只调整这组 config值并记录证据，不能让 backend另藏第二默认。

- **必须修改**：private/custom port 默认 allow；peer proof 默认 off；环境 proxy 默认 allow；browser 与 private flag 解耦；预算扩大并按 owner split。
- **必须保留**：逐 redirect 重新解析、危险/unspecified/multicast 防御、配置为 deny 时的 private/custom-port 拒绝、peer proof 开启时的 numeric target/peer verification、body/DOM/text/diagnostic budget、challenge detection/fallback、diagnostics v2、storage-state path 作为显式输入。
- **必须删除**：diagnostic utility 的 TTL、host-derived owner filename、0700/0600 lifecycle authority、orphan/expired cleanup、publish/reconcile 状态机与对应 artifact fields/tests。删除 lifecycle 不等于输出可非原子：普通 diagnostic artifact 的既有原子写可保留；credential state 的生成/刷新/保留交给 Issue 178。

### 9.3 Implementation slices

#### R02-S1 — Config owner 与 typed policy split

- call path：`ConfigLoader -> tool_discovery.json -> provider._load_* -> HttpResourceBudget/BrowserResourceBudget/DiagnosticResourceBudget + WebEgressPolicy + BrowserCapability -> tool factory`。
- invariant：只调整 diagnostics 不要求复制 HTTP/browser 字段；配置 snapshot 在一次 tool attempt 内不可变；错误定位到精确 owner/field。
- tests：

```bash
pytest tests/tools/web/test_web_tools_provider.py -k 'config or resource_budget or egress_policy or provider'
```

断言 packaged defaults、每个局部 override、未知/缺失 group、非法数值、private/custom/peer/proxy/browser 五个独立 bool；scan 证明旧七字段 flat schema 和 25/50 MiB、64 KiB、5M/1M、1024/80 默认无残留。

#### R02-S2 — HTTP/proxy/peer 与 browser 独立执行

- HTTP flow：`web tool -> URL decision per hop -> resolve -> (peer proof on ? pinned transport : standard Session) -> proxy policy -> response budget -> redirect repeat`。
- proxy semantics：`allow_environment_proxy=true` 且 peer proof off 时 `Session.trust_env=true`；proxy active 时记录非敏感 warning。peer proof on 且检测到 proxy 时，以 typed config/attempt incompatibility fail closed，因为无法证明目标 peer；不得静默取消 peer proof。proxy disabled 时 HTTP 不读取环境 proxy，browser worker 也获得剥离后的 proxy env。
- browser flow：`HTTP failure/challenge -> browser_enabled -> browser backend -> each URL still applies address/custom-port policy`。`browser_enabled=true` 不授予 private；`allow_private_network_url=false` 仍允许公网 JS。peer proof on 而 browser backend不能提供等价证明时，browser path typed fail，不绕过。
- tests：

```bash
pytest tests/tools/web/test_web_tools_provider.py -k 'private or custom_port or proxy or peer or redirect or browser or challenge'
```

必须覆盖 default private/custom port success、显式 deny、mixed DNS、redirect recheck、proxy stub、peer mismatch、public JS browser 成功、private=false 仍拒私网、browser disable、challenge 保留。

#### R02-S3 — 删除 storage-state lifecycle，保留 diagnostics v2

- call path：`diagnose_web_access CLI -> explicit storage-state file/dir input -> Web attempt -> diagnostics-v2 projection -> ordinary atomic artifact output`；不再 derive owner name、TTL、cleanup 或 reconcile credential files。
- diagnostics v2 exact schema/revision、header/error allowlist、challenge evidence 与 resource limits保持；storage state 是否存在/可读是普通输入校验，不产生 lifecycle state。
- tests：

```bash
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_web_tools_provider.py -k 'diagnostic or storage_state or challenge'
```

scan：`rg -n 'ttl|orphan|expired|owner_filename|reconcile|storage.state.lifecycle|0700|0600' utils/diagnose_web_access.py tests/tools/web` 只能命中与别的安全 contract 明确相关的代码，并逐条人工归属；diagnostics-v2/revision=2 tests 必须继续通过。

### 9.4 真实 smoke、README 与 stop

- 本地 HTTP server 使用 loopback + 非标准端口验证默认成功；显式 deny 验证拒绝；本地 proxy recorder 验证 proxy env 被采用/禁用；peer proof 使用可控 DNS/peer；Playwright 可用环境验证公网 JS，缺依赖环境验证 typed unavailable；challenge 与 diagnostics v2 跑现有真实 smoke。
- optional external Web smoke 只作网络可用时补充，不得替代本地确定性 smoke。
- README 必须发布新 config 字段、owner split、默认值和 peer/proxy incompatibility；不得写 Issue 178 未实现 lifecycle。
- retained DNS/peer/redirect/resource/containment 任一回归立即 stop。

## 10. R03 — accepted call 语义与 opaque provenance 的单一 LLM 投影

### 10.1 Owner、依赖与允许范围

- **owner**：Tool/Engine accept boundary 拥有已接受的原始 canonical arguments identity；能提供业务语义的 tool producer/schema 拥有 `semantic_query_text`；Host accepted-result projection 只组合这些显式事实；`OpaqueEvidenceRef` 只归 internal provenance/audit owner。
- **依赖**：无硬依赖；实施前需冻结当前 prompt/tool schema/source scan 清单。
- **允许生产模块**：`dayu/host/tool_runtime.py`、`waiting.py`、`_event_payload.py`、`accepted_result_projection.py`、`run_input.py`、`compact_material.py`、`durable/memory.py`、`tool_trace.py`、`durable/tool_trace.py`、相关 Host typed contract/serializer；必要的 Engine tool-call typed record；相关 production tool schema 与 `dayu/config/prompts/**` 仅在 scan 证明它们是错误 LLM source owner 时允许修改。
- **允许测试/文档**：`tests/host/test_accepted_result_projection.py`、`test_run_input_builder.py`、`test_compact_material.py`、`test_tool_trace_projection.py`、`test_tool_trace_queries.py`、`test_wait_awaiting_accept.py`、ToolRuntime/Memory tests及真实 smoke prompt fixtures；`dayu/host/README.md`、`dayu/engine/README.md`、`dayu/config/README.md`、`tests/README.md` 按实际影响。

### 10.2 必须删除/保留的 contract

- **删除**：`llm_safe_replay_arguments` 及字段黑名单/递归 sensitive-key taxonomy；`arguments_summary_unsafe` 这类下游 repair；awaiting 分支对 accepted args 的 redaction/rewrite；自动拼接“工具…参数…”的 synthetic semantic query；`_INTERNAL_SOURCE_REF_KINDS` 和 unknown `kind:id` business-source rendering；将 opaque refs装入共享 LLM projection 的字段。
- **保留**：ToolRuntime 对 accepted arguments 的内部 normalization/canonical JSON/digest；EventLog/envelope/audit 中的 opaque refs；真实 result payload 中 producer-owned、业务可读 citation；Host durable replay identity。
- **不新增**：通用安全归一层、字段名 validator/denylist、`BusinessSource` speculative type、兼容 safe/raw 双写。

### 10.3 Canonical data flow 与状态

```text
LLM tool call
  -> Tool schema validation
  -> ToolRuntime canonical accepted arguments + digest
  -> shared Host request-atom builder
       ordinary call ─┐
       awaiting call ─┴─> one TOOL_CALL_REQUESTED(original canonical args, digest,
                                                   optional producer semantic_query_text)
  -> execute / TOOL_AWAITING(governance + external wait refs only)
  -> accepted result envelope(internal opaque provenance stays internal)
  -> AcceptedToolResultProjection(query + result + explicit business citation or source-unavailable)
  -> same projection -> RunInput / Memory / Compact / LLM-ready Tool Trace
```

`TOOL_AWAITING` 不再持有 accepted args/digest；resume 通过关联的 `TOOL_CALL_REQUESTED` 重放原始 identity。ordinary 与 awaiting 必须调用同一个模块级 request-atom helper。若 producer 未提供 `semantic_query_text`，projection 机械渲染 schema-owned accepted arguments；不根据 key 猜安全性。当前生产 tool schemas 不应把 API key/password/token secret 暴露为 LLM 参数；若 source scan 找到真实 secret 参数，必须在该 tool schema/producer owner 删除或改成 config ref，而不是 Host blacklist。

opaque refs 仍可进入 EventLog/audit/internal trace，但任何会被 LLM 消费的 RunInput、Memory、Compact material、tool trace text 都只能使用 result 内显式业务 citation；没有则统一投影自解释的“该结果未提供业务来源”，不从 ref 拼业务事实。

### 10.4 Implementation slices

#### R03-S1 — Ordinary/awaiting 共用 request atom

- 新建一个 Host-owned 小型模块级 builder（文件名以实施时现有命名惯例为准，不得成为 facade），输入仅 canonical accepted call 与可选 producer semantic query，输出唯一 typed `TOOL_CALL_REQUESTED` payload。
- ordinary ToolRuntime 与 waiting accept 都调用它；`ToolAwaitingAcceptCandidate` 可在 accept transaction 内暂存 canonical args用于建 atom，但 durable `TOOL_AWAITING` 删除 args/digest。
- resume call path：`TOOL_AWAITING link -> linked TOOL_CALL_REQUESTED -> exact canonical args -> tool resume`；找不到或 digest 不一致是 durable corruption/invalid state，不用 fallback。
- tests：

```bash
pytest tests/host/test_wait_awaiting_accept.py tests/host/test_run_input_builder.py tests/host -k 'tool_call_requested or awaiting_accept or replay_arguments'
```

断言 ordinary/awaiting payload identity 相同、合法 `file_path`/业务 `scope_token` 不被删、digest 来自 original canonical args、awaiting durable payload 无重复 args、断链 fail closed。

#### R03-S2 — 删除 blacklist repair，修正所有 LLM source owner

- projection 优先使用显式 semantic query，否则使用 schema-owned canonical arguments；删除 `_event_payload.py` repair 与 accepted projection classifier。
- 在修改前产出并在 R03 completion report 保存人工逐文件 source inventory。Inventory 必须枚举：`dayu/config/prompts/**` 的每个 prompt asset；所有 production ToolDefinition/tool schema 的 name、description、参数、枚举和错误说明；Host/Engine/Tool 中会进入 system/user/assistant/tool message、Memory、Compact、Trace、Evidence 的 renderer；tests/smoke 中模拟真实 LLM 调用的 prompt/schema fixture；以及 R01 handoff 的 Doc LLM-facing 删除清单。每项记录文件、具体 source、是否 LLM-facing、语义 owner、`compliant | modify-at-owner | not-LLM-facing-with-evidence` disposition与验证证据，不能用目录级“已扫描”代替逐文件审计。
- 自动 `rg`/schema 枚举只作为防回归门禁，不是 inventory 完整性证明。每个真实 credential 必须来自 config/环境，不得成为 tool arg；内部 governance id 只有任务必须引用且自解释时才可进入文本。不得新增 credential fallback、字段 blacklist、特例脱敏或下游 repair；若 owner 无法明确，按 10.5 stop 回 controller。
- tests：

```bash
pytest tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
```

并执行 `rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|api_key.*token.*secret.*password|unsafe.argument' dayu tests` 及由 inventory 暴露出的 owner-specific scans，所有命中逐条归属；禁止用扩大敏感词表替代人工审计或形成 generic key blacklist。更新测试 prompt 的 fake secret 字段为真实业务 schema，不保留 test-only shim。

#### R03-S3 — opaque ref internal-only propagation closure

- 从 shared accepted result projection 移除 source/locator opaque refs 与 readable `kind:id`；internal diagnostic trace 若确需 refs，使用独立 internal provenance view，类型上不得被 LLM renderer接受。
- tests：

```bash
pytest tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -k 'source or ref or projection or memory or compact or trace'
```

注入 unknown、typo、internal kinds，逐一断言 EventLog/audit仍可查但 RunInput、Memory、Compact、LLM-ready trace 均无 ref kind/id；显式 Fins citation在四消费者一致；无 citation 时为 source-unavailable。scan 所有 renderer，禁止把 `payload_ref`、`event_id`、digest、cursor、tool_call_id 当业务来源。

### 10.5 真实 smoke、README 与 stop

- smoke：真实普通 Doc/Web call 与真实 Fins awaiting accept/resume，各自经过 Host public run→memory/compact/trace 读取；确认参数语义一致、无 secret fake、opaque refs不泄漏。
- `dayu/engine/README.md` 只有 Engine typed call contract 真受影响才更新；Host README 必须说明 request atom/projection owner；config README 仅在 prompt/schema用户可见变化时更新。
- completion report 必须附完整 inventory、逐项 disposition、R01 handoff消费记录、实际 owner 修改清单和全部自动门禁结果；仅有 grep 零命中不得完成 R03。
- 若任一现有 tool schema确实要求 LLM 提交 credential 且无法在该 tool owner内迁移到 config，owner 已不清晰，立即 stop 回 controller；不得预设 credential fallback、Host/tool blacklist、特例脱敏或其它兼容路径。

## 11. R04 — Awaiting provider resolution config 与 Host composition

### 11.1 Owner、依赖与允许范围

- **owner**：每个 provider 配置拥有 `poll|callback|manual` resolution mode；`host_runtime.json` 拥有 poller runtime policy 数值；Service composition 只验证并连接显式输入，不按 scene 发明 policy。
- **依赖**：先于 R05。
- **允许生产模块**：`dayu/config/tool_discovery.json`、`dayu/config/host_runtime.json`、`dayu/runtime/config_loader.py`、Fins `download_provider.py`/`preprocess_provider.py`/`upload_provider.py` 及一个共享 typed mode parser、`dayu/service/host_assembly.py`、`entrypoint_runtime.py`、`fins_wait_adapter.py`、必要的 Host assembly contract。
- **允许测试/文档**：runtime config tests、`tests/service/test_host_assembly.py`、`test_entrypoint_runtime*.py`、`test_fins_wait_adapter.py`、Fins provider tests、`tests/host/test_open_host_runtime.py`；`dayu/config/README.md`、`dayu/host/README.md`、`dayu/service/README.md`、`tests/README.md`。

### 11.2 Config contract、composition matrix 与不变量

- `tool_discovery.json` 的 financial download/preprocess/upload awaiting providers 各自显式写 `"awaiting_resolution_mode": "poll"`；closed enum 是 `poll|callback|manual`，由 Fins provider 公共 helper 一次解析，Service 不解析 raw string。
- `host_runtime.json` 新增完整必填 `wait_poller_policy` snapshot：`enabled=true`、`poll_interval_seconds=1`、`claim_ttl_seconds=60`、`claim_batch_size=100`、`backoff_initial_delay_seconds=30`、`backoff_multiplier=2`、`backoff_max_delay_seconds=300`、`not_ready_observe_interval_seconds=1`、`idle_poll_interval_seconds=5`、`adapter_call_timeout_seconds=30`、`close_drain_timeout_seconds=5`、`max_outstanding_adapter_calls=8`。这些名称就是现有 `WaitPollerRuntimePolicy` canonical fields，不建立别名。该 JSON snapshot 是所有部署 policy 数值的唯一真源；`WaitPollerRuntimePolicy` 的全部字段都是 required，不提供带部署数值的字段 default 或无参构造，Service/Host 不复制其中任何数值作为 fallback/default。所有字段由 ConfigLoader 的完整 typed snapshot 显式构造并严格 finite/positive 校验。
- composition：

| effective mode / policy / registry | 结果 |
| --- | --- |
| 无被选 poll provider，或 policy disabled | 不启动 poller |
| 至少一个 poll provider + enabled policy + 对应非空 registry | 用该 snapshot 启动 |
| poll provider + 缺 registry | composition error |
| callback provider + 已显式注入 authenticated callback transport | 注册 callback，不启动 poller |
| callback provider + 当前无 transport | composition error；不实施 Issue 175 |
| manual provider | 不启动 poller；仅显式 Host resolve/cancel/deadline |

### 11.3 Implementation slices

#### R04-S1 — provider resolution mode 真源

- flow：`tool_discovery config -> Fins provider parser -> typed AwaitingResolutionMode -> discovered provider metadata -> Service assembly input`。
- tests：provider 三模式、缺失/未知/错类型、非 awaiting provider误配；packaged config 三个 provider为 poll。不得按 tool name/scene反推。

```bash
pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_wait_adapter.py -k 'provider or resolution or awaiting'
```

#### R04-S2 — Host runtime policy 真源

- flow：`host_runtime.json -> ConfigLoader HostRuntimeProfileConfig -> OpenHostRuntimeRequest/assembly -> WaitPollerRuntimePolicy`；一个 run 使用不可变 snapshot。
- 删除 `WaitPollerRuntimePolicy()` 无参路径及 dataclass 上所有 deployment-value defaults；Service/Host 生产代码只能接收 ConfigLoader 已校验的完整 snapshot，不得以模块常量、helper default、factory fallback 或测试 fixture复制部署值。与部署 policy 无关的内部算法常量可以保留，但任何数值命中必须逐条证明其语义不属于 `wait_poller_policy`；当前承载同一部署语义的 30/5/8 等模块常量必须删除。unit tests 显式传入全部字段，并把 packaged exact snapshot作为测试 expected value而非第二个生产默认。

```bash
pytest tests/runtime tests/host/test_open_host_runtime.py tests/host/test_wait_adapter_polling.py -k 'runtime_config or poller or policy'
```

必须断言 packaged exact values、missing/unknown/wrong/NaN/nonpositive、disabled policy、policy type不能无参构造；source scan证明部署数值只存在于`host_runtime.json`与明确的测试 expected snapshot，Service/Host生产代码无复制值。命中与 policy 无关的内部常量时逐条记录 owner，不按数值字符串盲删。

#### R04-S3 — 删除 scene-derived policy 并闭合 composition

- 删除 `with_entrypoint_wait_poller_policy` 及 `entrypoint_runtime` 的 scene 自动启用路径；Service 只对 typed mode/policy/registry 做上述矩阵组合。
- tests：

```bash
pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_fins_wait_adapter.py
```

断言同一 scene 改工具可见性不会改变 policy；poll/callback/manual/disabled/missing registry矩阵 exact；callback 没有 transport 明确失败且无 process-isolation代码。

### 11.4 真实 smoke、README 与 handoff

- 更新 config/Host/Service README，删除“选中 Fins 工具自动开启”说明；写清 mode 与 runtime policy分属两个 owner。
- smoke：真实 ConfigLoader + entrypoint assembly，poll 模式有 registry时运行一次 not-ready；manual不创建后台 task；callback缺 transport在启动前失败。
- handoff R05 必须包含 effective policy snapshot 与 mode/registry组合证据。任何通过 scene/name heuristic恢复的 policy 立即 stop。

## 12. R05 — Wait observation timeout 状态机与 Engine handshake 边界

### 12.1 Owner、依赖与允许范围

- **owner**：Host `WaitObservationRunner` 拥有同步 adapter调用的 fencing；Host wait adapter/state store 拥有 claim/retry/durable status；Engine只拥有 `ToolExecutor.execute` 返回 `ToolAwaitingOutcome` 前的 handshake timeout。
- **依赖**：R04 完成。
- **允许生产模块**：`dayu/host/_wait_observation.py`、`wait_adapter.py`、相关 wait state/store operations、必要的 `waiting.py`；Engine 生产代码原则上不改，只有真实证据表明 accepted awaiting仍被二次计时才允许改 `dayu/engine/agent.py`，否则仅加 regression tests。
- **允许测试/文档**：`tests/host/test_wait_observation_runner.py`、`test_wait_adapter_polling.py`、`test_phase7_waiting_integration.py`、`tests/engine/test_agent_phase3_tool_call.py`、service public awaiting smoke；`dayu/host/README.md`、`dayu/engine/README.md`、`tests/README.md` 按需。

### 12.2 State transition 与错误语义

```text
WAITING, due
  -> claim(attempt token, ttl)
  -> observation worker
     -> resolved/not-ready/fatal: existing typed transition
     -> timeout:
          invalidate publication token
          record transient diagnostic(wait_observation_timeout)
          release claim
          schedule next_observe_at using policy backoff
          remain WAITING (never LOST)
     -> late callback/result after timeout: token rejected, no durable publication
```

poll 与 cancelled-wait abandon observation 只要是“同步 observation timeout”，都遵守非 LOST release/backoff；若 abandon 的 provider明确返回终态则沿既有 cancel/abandon transition。删除只为 timeout 生成 LOST/abandon-terminal 的 operation。adapter exception、capacity、close drain 各按现有设计，但不得把“不确定是否完成”伪造成 LOST；LOST 只保留有明确不可恢复 proof 的路径。

Engine transition：`EXECUTING_TOOL --handshake timeout--> RUN_FAILED(tool_execution_timeout)` 仅发生在 `ToolExecutor.execute` 尚未返回；一旦 `ToolAwaitingOutcome` accepted，Engine立即 `TOOL_AWAITING -> RUN_SUSPENDED`，外部长事务由 Host/Fins观察，不再受同一 timeout。

### 12.3 Implementation slices

#### R05-S1 — timeout 释放、退避与 late-publication fence

- 将 `WaitObservationTimedOut -> WaitPollLost(ResolveWaitLostOutcome)` 改为 transient timeout outcome；复用现有 release/backoff owner，不新建第二 scheduler。
- tests：

```bash
pytest tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py tests/host/test_phase7_waiting_integration.py -k 'timeout or late or lost or backoff or abandon or claim'
```

断言 timeout 后 `status=WAITING`、claim为空、`next_observe_at`由同一 policy计算、adapter_errors/timeout diagnostic增加而 lost计数不增；晚返回无法发布；下一次到期可重新 claim并 resolve；poll/abandon timeout一致。

#### R05-S2 — Engine accepted-awaiting 回归与真实入口

- 优先只加 regression：executor 在 handshake budget 内迅速返回 awaiting，随后模拟远端事务超过 budget，Engine仍已 suspended；Host后续 resolve可启动新 run。保留 handshake 未返回时 timeout失败的既有测试。

```bash
pytest tests/engine/test_agent_phase3_tool_call.py -k 'awaiting or tool_execution_timeout'
pytest tests/host/test_phase7_waiting_integration.py tests/service/test_entrypoint_runtime.py -k 'awaiting or resume'
python utils/smoke_host_public_awaiting_entrypoint.py
```

若测试证明生产路径已正确，`dayu/engine/agent.py` 必须无 diff；若不正确，只在 handshake owner边界最小修复，不触及 Fins executor/process isolation。

### 12.4 完成与 stop

- README 明确 observation timeout 是 transient unknown，不是 durable LOST；Engine README维持 handshake定义。
- 真实 smoke必须让 remote operation 时长大于 Engine handshake timeout并最终 resolve；同时超时 observation的 late result被拒、下一轮成功。
- 任何把 timeout结果 publication接受、重复 terminal、或迁移 Issue 175 executor 的方案立即 stop。

## 13. R06 — Fins 唯一显式 transaction 与完整 source 发布

### 13.1 Owner、依赖与允许范围

- **owner**：`dayu.fins.storage` 独占 batch transaction、staging、commit/recovery 和 source 可见性；producer 只持显式 handle并提供完整 source 事实，不拥有 transaction 状态。
- **依赖**：无外部硬依赖；R07/R08/R09/R10/R11 均依赖它。
- **允许生产模块**：`dayu/fins/domain/document_models.py` 中最小 transaction handle；`dayu/fins/storage/repository_protocols.py`、`_fs_storage_infra.py`、`_fs_storage_core.py`、`_fs_repository_factory.py`、`fs_batching_repository.py`、`_fs_source_document_core.py`、`_fs_blob_core.py`、`_fs_processed_core.py`、各 repository wrapper；所有实际写 producer：`ingestion_runtime.py`、CN/SEC download/upload/rebuild workflow、source upsert、`docling_upload_service.py`、company meta/material persistence，以及它们直接的 typed protocol/callback。
- **允许测试/文档**：`tests/fins/test_fins_storage_atomicity.py`、`test_fins_storage_provider.py`、ingestion/CN/SEC/Docling pipeline tests；`dayu/fins/README.md`、`tests/README.md`。

### 13.2 新 transaction contract

- public `BatchToken` 仅包含 opaque `transaction_id` 与 transaction scope 所需的业务 key（当前为 ticker）；不包含 `owner_token`、task/thread/scope id、PID、hostname、physical staging/backup path 或 lock object。
- storage internal `_ActiveBatchState` 保存 lock、staging、backup、journal phase和 locator；调用方只能提交已由同一 repository core登记且 transaction/ticker匹配的 token。显式 token 是唯一 authority，允许合法 helper/child task传递；未登记、已关闭、ticker不匹配拒绝。
- mutating repository protocol 的每个方法都新增 keyword-only、非 optional `batch: BatchToken`；不得 auto-batch。reads 默认只读 published tree；只有明确 transaction-internal read API 可读 staging。
- `begin_batch/commit_batch/rollback_batch` 只由 `BatchingRepositoryProtocol` 声明；其他 repository不做兼容 re-export/facade。composition必须保证 batching/source/blob/processed/company/maintenance repositories共享同一 storage core。
- journal 只持 crash recovery 必需的 `transaction_id/ticker/phase/relative locators`；不持进程内 owner身份。ticker lock只是 mutual exclusion，不是第二 authority。

### 13.3 Source publication contract

- 删除 `stage_source_document()`、`ingest_complete=false` staging ack、空 files/primary meta 与 stable-field re-entry规则。
- blob `store_file(..., batch=token)` 写入 transaction staging；不要求先存在 source meta。producer可从已有业务输入构造 opaque `SourceHandle` identity，但只有完整 source meta + 完整 file manifest + primary file + provenance 都写入 staging 后，source才具备 commit资格。
- `commit_batch(token)` 在同一 ticker 原子 swap中一次发布完整 source及所有相关 blobs/processed/company facts；失败/取消 rollback，published reader永远看不到 half source。commit成功是唯一可见点；recovery按 journal phase决定旧或新完整 tree，不能产生混合 tree。

### 13.4 Implementation slices

#### R06-S1 — 显式 transaction protocol 与 storage core

- flow：`producer -> begin_batch(ticker) -> BatchToken -> every mutation(batch=token) -> commit/rollback`；删除 `_BATCH_OWNER_CONTEXT`、`asyncio.current_task()`/thread id scope、`_execute_with_auto_batch` 和 owner fields。
- tests：

```bash
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -k 'batch or atomic or recovery or owner or token'
```

断言同一 token可跨模块 helper/child task；无 token/伪造/已关闭/跨 ticker拒绝；并发 ticker lock；每个 recovery phase只有一个完整结果。scan：`rg -n 'ContextVar|owner_scope|owner_token|current_task|thread.*ident|auto_batch' dayu/fins/storage tests/fins` 无 transaction authority残留。

#### R06-S2 — 完整 source 的单 commit point

- storage先删除 staging-ack protocol，再让 blob/source core只在 explicit transaction staging工作；final source validator在 commit前验证完整 meta/files/primary/provenance。
- tests：

```bash
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py -k 'source or blob or incomplete or commit or rollback'
```

断言 blob可先在 staging写；published read仍 not-found；完整 source commit后一致可见；missing file/primary/provenance不能 commit；失败、取消、crash recovery不见 `ingest_complete=false`。scan 删除 `stage_source_document` 与 staging ack文案/schema。

#### R06-S3 — 迁移全部 producer，删除隐式 mutation

- exact write paths：
  - `FinsIngestionRuntime -> begin -> download/preprocess/upload persistence -> complete source -> commit`；
  - `cn_download_workflow/cn_download_filing_workflow -> source upsert/blob/processed -> commit`；
  - `sec_download_workflow/sec_download_filing_workflow/sec_upload_workflow/rebuild -> mutations -> commit`；
  - `DoclingUploadService -> blob/processed/source -> commit`。
- callback/protocol必须显式带 token；不得用 closure/ContextVar藏 authority。每个 top-level flow只有一个 begin和一个 commit/rollback owner。
- tests：

```bash
pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py
```

source-propagation scan枚举 `repository.create|update|store|delete|replace` 的全部 mutating call，逐个证明显式 `batch=`；不存在 auto-batch fallback。

### 13.5 Smoke、README 与 stop

- 真实 filesystem smoke：一个 source含多 blob + processed artifact；在每个 journal phase注入进程崩溃并重开 repository，最终只能是旧完整版本或新完整版本；并发 reader循环不得见 half source。
- README写清 explicit handle、唯一 commit point和published visibility；删除 acknowledgement/ambient owner说明。
- 若某 producer无法在一个 batch内表达完整发布，stop并回到 storage/producer owner澄清；不得恢复 `ingest_complete=false`。

## 14. R07 — Fins storage-owned snapshot/revision 与 opaque identity

### 14.1 Owner、依赖与允许范围

- **owner**：storage拥有 external identity→internal key、published revision与一致 snapshot；read runtime只消费 snapshot并投影 citation/cache，不从路径、document id、ingest method或时间戳反推。
- **依赖**：R06。
- **允许生产模块**：Fins domain中最小 opaque ID/revision/snapshot types；`dayu/fins/storage/_fs_storage_utils.py`、新建单一 `_fs_identity.py`（或在已有 utils 中保持唯一 helper）、source/blob/processed/maintenance/company/storage infra/core/repository protocols；`dayu/fins/tools/read_runtime.py`、`read_runtime_helpers.py`、`cache.py`、processor registry/source adapters及 citation/error contract直接消费者。
- **允许测试/文档**：storage provider/atomicity、`test_processor_read_consistency.py`、`test_fins_read_runtime.py`、semantic ownership guards、provider/financial read tests；`dayu/fins/README.md`、`tests/README.md`。

### 14.2 Opaque ID mapping contract

- external ticker/document id 是非空 opaque Unicode业务值，永不直接作 path component，也不因包含 `/`、`\\`、drive-like、`.`、`..` 而改变业务 identity。
- storage 的唯一 mapping/encoding owner 把 external exact identity 映射为 namespace-separated internal key；算法、前缀、编码长度、revision grammar及是否需要某种 registry 都不是 umbrella contract，由 R07 独立子计划基于当前 storage layout 与直接代码证据决定。不得让 repository、read consumer、CLI或测试 fixture各自实现第二套映射。
- external exact identity 与 internal key 的对应关系必须由同一 storage meta/manifest 真源持久化并可 round-trip；每次读取都验证 key 与 meta identity 同源。collision、篡改、缺失或映射损坏必须 typed fail closed，不能读取另一 identity，也不能从路径反推出 external identity。
- source/processed/blob/rejected/maintenance/manifest所有路径只消费该 owner 的 internal key；entry file name仍按 file-name owner校验。lexical + resolved containment、symlink拒绝、atomic write保留。fresh schema直接使用新布局，不兼容旧布局、不迁移旧库。本文不要求或禁止某一种 reverse registry 形态，只禁止第二语义 owner。

### 14.3 Snapshot/revision contract

- 每次会改变 processor/read 结果的完整 source publication都由 storage生成并持久化 opaque revision/version；具体 revision 编码、前缀和生成算法由 R07 独立子计划基于 storage layout决定，不是业务/public/LLM contract。read consumer不得挑字段hash或自行生成 revision，LLM不得看到 opaque revision。
- storage read boundary 必须原子取得同一 published version 的 external identity、complete meta、provenance、revision/version 与全部声明 source/files；不得把 A 版 meta 与 B 版文件混成一个 snapshot。实现可以在 storage 内做有界重试，但 retry 次数、snapshot API/类型名、copy/digest策略和资源生命周期形态都由 R07 子计划基于代码证据决定，不在 umbrella 计划固定。
- 无法取得稳定同版本 source 时，必须复用 Fins 既有 typed `source_changed_during_read` 业务错误；不得新增另一异常名或让下游从异常消息/revision mismatch恢复分类。read runtime只消费一次 storage-owned snapshot contract，不再拥有 revision-before/meta/path/revision-after 双读协议。
- cache 只能以 storage-owned revision/version失效，且不得持有已经失效、关闭或越过其合法生命周期的资源。如何表达 cache entry、resource handle或关闭责任由 R07 子计划决定；本文不固定任何 lease、context manager或cache class形态。citation必须从同一 snapshot provenance派生；not-found、source-changed、decode/processor/XBRL 等错误仍由各自 owner区分。

### 14.4 Implementation slices

#### R07-S1 — storage-owned opaque key

- 先在子计划中用当前 storage layout 选择单一 mapping/encoding owner，再迁移所有 storage path consumer；禁止各 repository自行 hash/quote/encode。算法、前缀、registry形态不得成为业务/public/LLM contract。
- tests：

```bash
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py -k 'path or identifier or containment or symlink or unicode or document_id or ticker'
```

断言层级、Unicode、drive-like、`.`/`..` external ID均可 round-trip且不可逃逸；absolute/local URI与 entry filename攻击仍拒绝；collision/corruption/meta mismatch fail closed；所有 repository使用同一 mapping owner。scan禁止 raw ticker/document id参与 `/` path join，不断言某个 hash、prefix或registry实现。

#### R07-S2 — published revision 与 snapshot API

- 在R06 complete source commit中由 storage生成/persist revision；R07 子计划依据现有代码选择最小 snapshot API与有界内部重试策略，保证同一 snapshot 的 source/files/meta/provenance/revision同版本，并复用 typed `source_changed_during_read`。不得在子计划无直接证据时固定 retry次数、新异常名、hash/digest grammar或资源类名。
- tests：

```bash
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_processor_read_consistency.py -k 'revision or snapshot or concurrent or changed or provenance'
```

断言每次有效发布revision变化、无发布不变；并发更新后只返回完整A或完整B，永不混合；短暂变化可在有界策略内恢复，持续变化耗尽该策略后返回既有 typed `source_changed_during_read`；snapshot 内所有 files/meta/provenance同一 revision，资源 cleanup无泄漏。测试不得把固定尝试次数或具体 revision grammar冻结为 contract。

#### R07-S3 — read/cache/citation迁移

- flow：`Fins read tool -> storage-owned stable snapshot -> cache lookup(storage revision) -> processor消费有效snapshot资源 -> result + citation(same snapshot provenance) -> cache/runtime按所选资源contract释放`。
- 删除 `get_source_revision` consumer double-read、consumer digest preimage、path guessing和零重试 mismatch。
- tests：

```bash
pytest tests/fins/test_processor_read_consistency.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_financial_read_contracts.py
```

断言并发发布时结果/citation同一 snapshot；cache不会返回失效/关闭资源并在owner边界释放；source changed typed error仅由storage无法取得稳定版本产生；read不反推 provider/source type。scan证明 revision只由storage写、LLM输出无 opaque revision，不绑定 lease/类名。

### 14.5 Smoke、README 与 stop

- filesystem并发 smoke：writer持续原子发布两个明显不同版本，reader多轮读取；每次结果/文件/citation必须全属于A或B，不混合。覆盖Unicode与含分隔符 external ID。
- README发布opaque business ID与storage key分离、fresh schema、snapshot/revision ownership；不公开internal key grammar供业务依赖。
- containment/symlink任一弱化、创建旧布局兼容或 read重新hash revision立即 stop。

## 15. R08 — 最小 financial/XBRL producer contract 与单一 projection

### 15.1 Owner、依赖与允许范围

- **owner**：Fins domain producer拥有 financial/XBRL业务结果；tool projection只添加 snapshot-owned ticker/document/citation并生成同源 schema/LLM文本；read consumer不重算producer事实。
- **依赖**：R06、R07。
- **允许生产模块**：`dayu/fins/domain/financial_result_contract.py`、`xbrl_result_contract.py`、相关 enums/filing semantics；实际 financial processors/common helpers、`sec_xbrl_query.py`；`dayu/fins/tools/read_runtime.py`、`read_runtime_helpers.py`、`result_types.py`、`fins_tools.py`、`error_contract.py`。
- **允许测试/文档**：`tests/fins/test_financial_read_contracts.py`、`test_fins_read_runtime.py`、processor/XBRL/semantic guard/provider tests；`dayu/fins/README.md`、`tests/README.md`。

### 15.2 最小 contract

Financial producer result只承诺：`statement_type`、`periods`、`rows`、`currency`、`units`、`scale`、`data_quality`、可选业务可行动 `reason`。删除 `statement_locator`；删除 `statement_method_missing` 等内部实现 reason。各 processor在 producer owner将“method不存在/空结果”归一为业务 `statement_not_found`，但不得由 read side猜。reason闭集只保留会改变下一步动作的 unsupported、XBRL unavailable、statement not found、low confidence、scale/period semantics unavailable等设计真源值。

XBRL processor-owned internal result只承诺 `query_params`、raw `facts`、`data_quality`、可选 reason；provider raw `total`只允许保留在明确的 producer validation/diagnostic owner，用于核验 provider 响应，不是 public或LLM业务事实。read projection可以清洗/去重 raw facts，但必须生成一个独立的 public typed result，输出 deduplicated `facts` 与唯一 `fact_count = len(deduplicated facts)`；不得覆盖processor raw facts后把重算值冒充producer事实，也不得在 public/tool schema/LLM文本同时暴露去重前 total、dedupe diagnostic与fact_count。

tool schema、description、result serializer必须从同一 typed projection/helper派生，当前 prompt内自足解释字段、类型、必填、枚举与最小示例；不得暴露processor类名、内部 reason或 revision/id。

### 15.3 Implementation slices

#### R08-S1 — producer domain contract 与所有 processor

- 先收紧 financial public producer contract及XBRL processor-internal contract，再迁移 SEC/BS/SIX-K/HTML等 producers；每个 producer直接满足自身contract，不在read补 financial default。
- tests：

```bash
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_processor_registry.py -k 'financial or statement or xbrl or quality or reason'
```

断言所有 producer contract；missing essential field在 producer terminal validator失败；financial public无 `statement_locator`/internal reason；XBRL provider raw `total`只在限定的 internal validation/diagnostic type中存在并参与owner-level校验，raw facts不被read原地改写，public facts已dedup且唯一count与实际返回facts同源。

#### R08-S2 — read/tool/LLM projection

- flow：`snapshot -> processor typed result -> one projection helper adds ticker/document/citation -> serializer/tool schema/LLM description`；read只机械计算 `fact_count=len(facts)`这一投影值。
- tests：

```bash
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_fins_ingestion_tools.py
```

断言 producer与public字段一一映射；citation来自R07 snapshot；tool schema/description自足。验证必须同时提供：(1) 限定 internal processor/diagnostic类型的正向 scan，逐条证明 raw `total` 只用于 provider校验/诊断；(2) 限定 public result/tool schema/serializer/LLM renderer 的反向 scan，证明 `raw_total|deduped_fact_count|去重前total` 零残留且只有 `fact_count`；(3) owner-level test 断言 `fact_count == len(returned deduplicated facts)`。不得用全仓 `total` 零命中误删内部校验，也不得把内部残留当 public closure。

### 15.4 Smoke、README 与 stop

- 使用真实 AAPL XBRL fixture和至少一个HTML财务表fixture经真实 read tool，验证最小字段、唯一 fact_count、可读citation；无statement走 business reason。
- README只描述最小contract和consumer动作；测试README更新owner-level断言。
- 若某字段只有“可能以后有用”而无当前 consumer，删除；若 producer无法提供必填事实，stop澄清contract，不在tool projection加默认。

## 16. R09 — 唯一 Fins direct-stream terminal validator

### 16.1 Owner、依赖与允许范围

- **owner**：`dayu.fins` 的 typed stream validator独占“恰好一个且最后一个 RESULT”；Service/CLI只消费已经验证的stream/error。
- **依赖**：R06；与R08可顺序执行，但同一最终 Fins public surface需一起aggregate。
- **允许生产模块**：`dayu/fins/direct_events.py`、新建或扩展一个真正执行状态机的Fins stream module、`ingestion_runtime.py`及各 direct producer接入点；`dayu/service/fins_direct.py`；`dayu/cli/commands/fins.py`只删除重复校验/机械映射。
- **允许测试/文档**：Fins ingestion runtime、Service direct、CLI Fins tests；`dayu/fins/README.md`、`dayu/service/README.md`、根 README仅在用户错误/工作流变化时、`tests/README.md`。

### 16.2 Validator 状态机

```text
OPEN
  progress -> yield progress, remain OPEN
  first RESULT -> buffer, RESULT_BUFFERED
  upstream error/cancel -> propagate typed owner error, no synthetic RESULT
RESULT_BUFFERED
  second RESULT -> FinsDirectStreamProtocolError(DUPLICATE_RESULT)
  later progress -> FinsDirectStreamProtocolError(EVENT_AFTER_RESULT)
  upstream end -> yield buffered RESULT exactly once, CLOSED
OPEN + upstream end -> FinsDirectStreamProtocolError(MISSING_RESULT)
```

buffer first RESULT直到 upstream结束，才能证明唯一且terminal。Fins runtime返回这个已验证 typed stream；Service不得重新扫描或改错误；CLI使用流中最后的 RESULT，不生成缺失/重复 fallback。取消和producer异常不合成第二 terminal。

### 16.3 Implementation slices

#### R09-S1 — Fins validator owner

- 建立 `ValidatedFinsEventStream`（命名可按现有风格）并让所有 direct runtime入口只返回它；删除 runtime内部散落 missing/duplicate扫描。

```bash
pytest tests/fins/test_fins_ingestion_runtime.py -k 'result or terminal or duplicate or missing or cancel or stream'
```

覆盖上述状态机、async iterator close/exception/cancel、exact-one terminal。

#### R09-S2 — Service/CLI 机械消费

- 删除 `dayu/service/fins_direct.py` 和 CLI 的 duplicate/missing logic；只透传 progress，保存 owner已经证明的terminal供exit/output映射。

```bash
pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -k 'result or terminal or duplicate or missing or direct'
```

source scan必须证明 `MISSING_RESULT/DUPLICATE_RESULT/EVENT_AFTER_RESULT` 的判断分支只在Fins validator；Service/CLI tests断言同一错误object/code传播，不自行构造。

### 16.4 Smoke、README 与 stop

- 真实 upload/download/preprocess direct stream各跑一条 success；注入 missing/duplicate producer各一条，Fins/Service/CLI观察同一error。
- README按层说明唯一 owner；删除“三层都防御”的暗示。
- 为保留旧测试而在Service/CLI留fallback立即 stop。

## 17. R10 — HKEX cumulative rowRange 完整续取

### 17.1 Owner、依赖与允许范围

- **owner**：`dayu/fins/downloaders/hkexnews_downloader.py` 拥有 HKEX provider exact cumulative protocol与 completeness proof。
- **依赖**：R06；它产生的完整 filing collection在同一 Fins transaction发布。
- **允许生产模块**：HKEX downloader及必要的 typed provider response model；不得添加通用日期切分框架。
- **允许测试/文档**：`tests/fins/test_hkexnews_downloader.py`、直接 CN/HK workflow tests；`dayu/fins/README.md`、`tests/README.md`。

### 17.2 Protocol 与单 slice

请求从 `rowRange=100` 开始。每次响应严格解析官方 `hasNextRow`、`loadedRecord`、`recordCnt` 与 rows：

1. 若 `hasNextRow=true`，下一请求保持完全相同的 query/sort/date/filter，只把 `rowRange` 扩为 `max(current_row_range * 2, recordCnt)`；响应是**累计 snapshot**，仅保留最新一页，禁止拼接造成重复。
2. `recordCnt` 在轮次间增加是允许的，以最新值继续；必须有进展（loaded/rows或range），否则 typed provider protocol error，避免无限循环。
3. 只有 `hasNextRow=false` 且 `loadedRecord == recordCnt == len(rows)` 时证明 complete并返回。字段缺失/类型错误/相互矛盾 typed fail；恰好100不再凭数量失败。
4. 不设 speculative hard cap，不做date-range recursion。取消在每轮前后检查，不返回 partial为complete。

```bash
pytest tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py -k 'hkex or rowRange or complete or pagination or cumulative'
```

必须覆盖 100 exact complete、>100两/多轮累计、累计页包含前页且不重复、recordCnt增长、hasNext/loaded/len矛盾、无进展、取消。真实 smoke使用可控 captured fixture或官方端点非破坏查询，证明一次 >100 场景最终无遗漏；外部端点不可用时记录环境限制，但本地协议fixture仍是必过 gate。

### 17.3 完成与 stop

- 删除 `_raise_if_title_search_truncated` 的“100即未知/失败”规则及 generic total猜测；scan只保留官方字段。
- README说明cumulative不是page append；不承诺无证据的日期递归。
- 若官方实测出现无法由rowRange扩大解决的cap，只记录 residual交给后续 evidence-driven WU，当前立即 stop，不自行加第二分页机制。

## 18. R11 — OLD-aligned upload shell/cmd workflow 与 placeholder surface 删除

### 18.1 Owner、依赖与允许范围

- **owner**：`dayu.fins.upload_batch` 拥有文件发现、业务分类、优先级/去重与 typed upload plan；CLI script renderer只把 typed entries投影为平台命令；packaging只发布真实入口。
- **依赖**：R06 的 final upload transaction/command contract；R09 的 direct upload terminal contract。不得让 script生成器调用 live service。
- **允许生产模块**：`dayu/fins/upload_batch.py`、`dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`，可新增职责单一的 `dayu/cli/upload_script.py`；`pyproject.toml`；删除仅属 placeholder 的 `dayu/web/**`、`dayu/wechat/**`、`dayu/render/**`。
- **允许测试/文档**：`tests/fins/test_upload_batch.py`、`tests/cli/test_upload_filings_from_command.py`、`test_fins_commands.py`、`test_arg_parsing.py`、删除/改写 `test_public_package_entrypoints.py` 中 placeholder contract；根 `README.md`、`dayu/fins/README.md`、`tests/README.md`。`dayu/render/`删除无需覆盖率，但 packaging scan必须完整。R11 独立子计划在 implementation 前必须确认真实 Windows runner/CI owner、触发方式与 artifact 读取位置；若当前仓库仍无 runner，子计划必须把新增最小 Windows workflow 的精确文件列入自己的 closed allowlist并经双 plan review/controller接受，umbrella计划不预设 workflow 文件名。

### 18.2 Typed batch plan 与 script contract

- 扫描 `--from` 授权目录中当前 upload命令真正支持的后缀；从文件名/父目录按 OLD规则推断 fiscal year/period、report/material type、amended/date，公司/ticker元数据只来自 CLI显式参数或Fins resolver，不从偶然排序猜。
- material/report分类、每 period 优先级与去重由Fins唯一 helper产出。OLD直接证据为 `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py:120-125,371-458` 与 `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py:1520-1544`：annual最多5；periodic只保留识别到的最新 fiscal year且最多6；presentation最多6；call cap等于过滤后 recognized report 数量；`FINANCIAL_STATEMENTS` 不在 material cap map中，因此无材料数量cap；同一 `(fiscal_year, fiscal_period)` 先由Fins-owned、等价 `_pick_best_per_period` 的优先级规则选唯一主报告，再应用年度/数量规则。计划输出 typed `recognized entries`、`material entries`、`skipped(path, reason)`；CLI renderer不再自行分类、排序、同期去重或补cap。
- `BatchUploadAction` 使用 current Fins runtime已支持的 `auto|create|update`，默认 `auto`；同时把 `upload_filing/upload_material` CLI默认修正为 `auto`。只有用户显式选 create/update时脚本才固定 `--action`，否则省略并让执行时按workspace事实决定；不为batch生成delete。
- `--ticker` 继续接受CSV：首项经现有ticker normalization成为canonical，其余显式aliases去重保留。`--infer` 对齐OLD但复用当前 `dayu.fins.resolver.fmp_company_info.FmpCompanyInfoResolver`：CLI从环境显式读取`FMP_API_KEY`并只在生成阶段调用一次，把同名ticker aliases与company name作为typed输入交给batch plan；resolver失败是生成失败，不把网络错误或API key写进脚本。每条生成命令bake同一canonical+aliases/company metadata，不在脚本执行时再次调用FMP。
- `upload_filings_from` 生成平台脚本而非 JSON argv。未传 `--output` 时写入 `--base` workspace root：POSIX为 `upload_filings_<TICKER>.sh`，Windows为 `.cmd`；`--output` 指定文件，若是既有目录则在目录中用默认名。目标路径走 containment/symlink检查与原子 temp+replace。
- POSIX：UTF-8/LF、`#!/usr/bin/env sh`、`set -eu`、逐 argv用 `shlex.quote`/`shlex.join`，文件 mode 755。Windows必须由职责单一的平台专用 batch renderer拥有 `argv -> .cmd command line`，输出UTF-8/CRLF、`@echo off`、`chcp 65001 >nul`，并在处理任何不可信参数前显式 `setlocal DisableDelayedExpansion`，直到脚本结束都不得重新开启 delayed expansion。`subprocess.list2cmdline`只面向 Windows application/C runtime argv编码，不能作为cmd.exe batch quoting owner或安全证明；不得把其输出直接写入 `.cmd` 后宣称安全。
- Windows renderer 的稳定 outcome/invariants 是：typed plan中的每个参数经“batch file读取/百分号展开/cmd.exe元字符解析/目标Python argv解析”后恰好恢复为一个原始 argv；空格、Unicode、单引号、双引号、连续/尾随反斜杠均不得改变字符或参数边界；batch literal `%` 必须按 batch 语义避免环境变量/参数展开，`!` 在 `DisableDelayedExpansion` 下保持字面量；`&|^()`（以及同类重定向/分组元字符）不得启动第二命令、管道、分组或改变控制流。具体 quote/escape算法由 R11 子计划依据 cmd.exe 文档和真实 runner evidence固定在该 renderer内，CLI command builder、测试fixture和调用方不得各自 `replace`。renderer必须同样证明脚本尾部追加参数的转发边界；如果 raw `%*` 不能满足 exact argv invariant，子计划必须在同一 owner内替换，不能用调用约定掩盖。
- 每条命令调用不依赖外部console-script安装状态的真实 `python -m dayu.cli upload_filing|upload_material` grammar，包含 base/ticker/action/path/fiscal/date/amended/company/material/overwrite中该 entry真实拥有的显式字段；无字段不传，不塞 extra payload。脚本头包含一条平台注释形式、可复制执行的同源重生成命令；脚本把调用者追加参数按平台安全转发（POSIX `"$@"`，cmd `%*`）。stdout只报告脚本位置、recognized/material/skipped counts和可读skip reasons，不发布第二机器schema。
- **必须删除**：`schema_version:1`、commands/argv JSON renderer、README/schema tests；未实现 `dayu-web`/`dayu-wechat`/`dayu-render` scripts、packages、future grammar、help/diagnostic/README/tests。不得实现tracker能力。

### 18.3 Implementation slices

#### R11-S1 — Fins OLD batch classification owner

- flow：`source dir -> stable file discovery -> typed metadata inference -> domain routing -> priority/dedup -> UploadBatchPlan`。
- tests：

```bash
pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py -k 'scan or classify or priority or dedup or skip or recursive'
```

覆盖 supported/unsupported、递归/结构化年度子目录、文件名/父目录、annual=5、periodic=6且仅最新年、presentation=6、call=count(recognized reports)、`FINANCIAL_STATEMENTS`无材料cap、同期报告按Fins-owned等价`_pick_best_per_period`优先级/去重、amended、ticker aliases/company metadata、稳定排序、无可识别文件typed failure。CLI测试只消费typed plan，不重复规则；completion report附上述OLD文件/行号与current typed rule逐项对照。

#### R11-S2 — Shell/cmd renderer 与 CLI contract

- flow：`ParsedCliArgs -> build_upload_batch_plan -> platform renderer -> atomic script write -> human summary`；不创建Fins direct service。
- tests：

```bash
pytest tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py tests/cli/test_arg_parsing.py tests/fins/test_fmp_company_info_resolver.py -k 'upload_filings_from or upload_filing or upload_material or fmp'
```

覆盖路径含空格、单/双引号、连续/尾随反斜杠、`&|^()%!`、Unicode、empty optional、ticker CSV、`--infer`单次成功/缺key/provider失败且secret不落盘、default `--base` output、output file/dir、auto省略action、显式action、overwrite、重生成注释、write failure、KeyboardInterrupt；断言JSON schema字符串零残留。Windows renderer unit tests必须覆盖 delayed expansion明确关闭、batch `%`、每个cmd元字符、引号/反斜杠组合和脚本追加参数；unit test只证明局部变换，不替代真实cmd.exe。
- **recorder quoting smoke**：POSIX用真实`/bin/sh`执行生成脚本，Windows runner用真实`cmd.exe`执行生成`.cmd`；受控 recorder只记录最终argv而不进入Service/Fins。两端逐entry与typed plan exact比对，并包含空格、Unicode、单双引号、连续/尾随反斜杠、`%`、`!`、`&|^()`的对抗矩阵，证明没有命令注入、变量展开或参数边界漂移。
- **真实端到端 smoke**：另行执行生成的POSIX脚本，使每条命令真实进入`python -m dayu.cli upload_filing|upload_material` parser、Service/Fins direct path与临时storage；外部provider只能用可控fixture。该 smoke验证CLI grammar、typed routing、transaction和文件落地，不能由recorder冒充。Windows runner还必须至少让生成`.cmd`真实进入同一`python -m dayu.cli` grammar并成功解析对抗性路径；若环境允许，复用临时storage闭环。
- 非Windows开发机可以先运行 renderer unit tests和POSIX两类 smoke，但不能宣称 Windows closure。真实Windows `cmd.exe` recorder + CLI grammar smoke最迟在第22节aggregate/PR check通过；runner owner、workflow/run URL或artifact必须可追踪。未执行、跳过或失败是release blocker，unsafe quoting不得进入residual risk。

#### R11-S3 — 删除 placeholder package surface并更新 docs

- 从 `pyproject.toml` 删除三个 scripts及只为placeholder存在的 optional dependency/comment；删除placeholder packages和public entrypoint tests；arg help/README不再显示未实现grammar。

```bash
pytest tests/cli/test_public_package_entrypoints.py tests/cli/test_arg_parsing.py tests/cli/test_upload_filings_from_command.py
python -m build
```

构建wheel后检查 metadata entry points与archive：只含真实入口，无 `dayu.web`/`dayu.wechat`/`dayu.render`；`rg -n 'dayu-web|dayu-wechat|dayu-render|schema_version.*commands|JSON argv' pyproject.toml dayu tests README.md` 对删除surface无残留。若 test文件仅测placeholder应删除文件而非保留空壳。

### 18.4 README、完成与 stop

- 根 README发布真实 `upload_filings_from`脚本生成/执行/排障、平台后缀、输出位置；删除placeholder说明。Fins README描述typed classification owner，不承诺CLI argv schema。
- smoke必须分别证明 renderer的实际argv边界与真实`python -m dayu.cli -> Service/Fins`执行；不接受只比较生成字符串，也不得把recorder结果表述为端到端上传成功。
- 若 OLD规则与当前真实 upload grammar发生无法机械映射的产品矛盾，stop并以直接证据上报；不得生成JSON fallback或新增兼容subcommand。

## 19. R12 — OLD-aligned、current-schema `dayu-cli init`

### 19.1 Owner、依赖与允许范围

- **owner**：CLI init orchestration拥有交互、workspace mutation和首次预热；runtime ConfigLoader/current JSON schemas拥有配置合法性；provider/model/scene catalog是CLI typed product catalog；secret persistence必须经用户明确选择并由OS-specific writer执行。
- **依赖**：R11定型用户入口；R08/R09 current Fins/tool config可加载；基础实现可准备，但最终 docs/smoke在这些依赖完成后。
- **允许生产模块**：`dayu/cli/commands/init.py`、`dayu/cli/arg_parsing.py`，可新增职责分离的 `init_catalog.py`、`init_environment.py`、`init_workspace.py`；`dayu/runtime/filelock.py`只复用/最小扩展层中立lock；`dayu/runtime/config_loader.py`仅当前schema验证需要的直接修复；packaged `dayu/config/*.json`、prompt manifest只按已裁决 init selection投影修改。
- **允许测试/文档**：`tests/cli/test_init_command.py`、arg parsing/runtime config/scene prompt tests；根 `README.md`、`dayu/config/README.md`、`tests/README.md`。不修改/创建 Issue 142/151 artifacts。

### 19.2 Product catalog 与输入输出

typed catalog必须在一处列出并验证 current `models.json`：Mimo plan/SG/pro、DeepSeek flash/pro、OpenAI GPT-5.4、Anthropic Sonnet 4.6、Gemini 2.5 flash/pro/flash-lite与3.1 pro/flash-lite preview、Qwen plus、Ollama动态模型、custom OpenAI-compatible动态endpoint/model/context。每个选项声明 provider id、display、non-thinking/thinking model id与API-key env ref；具体ID必须以当前 packaged model contract为准，若catalog所需ID缺失则同slice补到 current schema并由ConfigLoader验证，不加旧schema别名。

init catalog 的静态部分固定为下表；这是从当前 `dayu/config/models.json` 与 OLD init 直接对照得到的 current-schema投影：

| 选项 | non-thinking model id | thinking model id | required env ref |
| --- | --- | --- | --- |
| Mimo Token Plan | `mimo-v2.5-pro-plan` | `mimo-v2.5-pro-thinking-plan` | `MIMO_PLAN_API_KEY` |
| Mimo Token Plan SG | `mimo-v2.5-pro-plan-sg` | `mimo-v2.5-pro-thinking-plan-sg` | `MIMO_PLAN_SG_API_KEY` |
| Mimo Pro | `mimo-v2.5-pro` | `mimo-v2.5-pro-thinking` | `MIMO_API_KEY` |
| DeepSeek Pro | `deepseek-v4-pro` | `deepseek-v4-pro-thinking` | `DEEPSEEK_API_KEY` |
| DeepSeek Flash | `deepseek-v4-flash` | `deepseek-v4-flash-thinking` | `DEEPSEEK_API_KEY` |
| OpenAI | `gpt-5.4` | `gpt-5.4-thinking` | `OPENAI_API_KEY` |
| Anthropic | `claude-sonnet-4-6` | `claude-sonnet-4-6-thinking` | `ANTHROPIC_API_KEY` |
| Gemini 2.5 Flash | `gemini-2.5-flash` | `gemini-2.5-flash-thinking` | `GEMINI_API_KEY` |
| Gemini 2.5 Pro | `gemini-2.5-pro` | `gemini-2.5-pro-thinking` | `GEMINI_API_KEY` |
| Gemini 2.5 Flash-Lite | `gemini-2.5-flash-lite` | `gemini-2.5-flash-lite-thinking` | `GEMINI_API_KEY` |
| Gemini 3.1 Pro Preview | `gemini-3.1-pro-preview` | `gemini-3.1-pro-preview-thinking` | `GEMINI_API_KEY` |
| Gemini 3.1 Flash-Lite Preview | `gemini-3.1-flash-lite-preview` | `gemini-3.1-flash-lite-preview-thinking` | `GEMINI_API_KEY` |
| Qwen Plus | `qwen-plus` | `qwen-plus-thinking` | `QWEN_API_KEY` |
| Ollama | 更新current `ollama` record为用户model id | 同一用户model id | 无 |
| Custom OpenAI-compatible | 新增current-schema `custom-openai` record | 与non-thinking使用同一用户model id | `CUSTOM_OPENAI_API_KEY` |

Custom必须收集endpoint、model id、正整数context window；Ollama收集model id、endpoint（沿current record默认/显式值）和正整数context window。当前两者没有独立thinking variant，known manifest的两个角色都引用同一动态model record；不得从model名字猜thinking能力。

- scene manifest角色映射由catalog显式决定哪些已知manifest用thinking/non-thinking；只更新init-owned已知manifest。当前 **non-thinking**：`conversation_compaction`、`fix`、`overview`、`regenerate`、`repair`、`smoke_host_public_conversation_memory`、`smoke_host_public_conversation_memory_scenarios`、`write`；当前 **thinking**：`audit`、`confirm`、`decision`、`infer`、`interactive`、`prompt`、`smoke_host_public_multiturn`、`wechat`。用户新增manifest不重写、不猜role，不新增 `_init_model_role`治理字段。
- 交互收集 provider/model、必需API key；可选 Web provider keys（当前 TAVILY/SERPER）、FMP API key、HF endpoint/token。只收当前真实 integration；不因 OLD考古添加未裁决项。
- secret不写任何JSON、日志、trace或LLM文本。用户明确选择持久化目标后：POSIX更新检测到的 zsh/bash profile中一个有marker的原子block，使用shell-safe quoting、保留mode、拒绝symlink；Windows使用argument-safe user environment API/`setx`。输出只显示env name和masked状态。必需/用户选择持久化的secret失败时，config tree保持未发布；成功后才更新当前进程env。

### 19.3 Workspace transaction/state machine

```text
PARSE
  -> if reset: show exact managed targets, default No confirmation
  -> acquire <workspace>/.dayu-init.lock
  -> revalidate containment/symlink
  -> select staging input:
       first/reset/overwrite -> packaged current defaults
       ordinary existing     -> existing config tree; copy only missing packaged prompt assets
  -> collect/validate provider/model/optional integrations
  -> persist explicitly selected required env
  -> ConfigLoader + scene/prompt manifest validate entire staging
  -> backup/swap whole managed config atomically
  -> rollback old tree on failure
  -> first/reset only: non-network prewarm
  -> release lock
```

- init owner必须维护唯一 managed-root manifest，reset展示、确认、containment与删除全部消费它，禁止CLI展示层和filesystem helper各写一份白名单。当前产品manifest只包含 `<workspace>/.dayu`（整个Dayu-owned Host/runtime/CLI/artifact/storage-state可重建根）与 `<workspace>/config`；当前package没有`dayu/assets`，本WU不得创建空`assets`、从OLD搬入assets，也不得把用户自行建立的`<workspace>/assets`视为Dayu-owned后删除。未来Issue151真正交付product-owned workspace assets时，由Issue151 owner把该root及其ownership证据加入同一managed-root manifest，届时reset才显示并删除该product-owned root。
- reset confirmation必须在任何 mutation前从manifest列出当前 `.dayu`与`config`精确目标；默认No，取消exit非成功且workspace不变。`portfolio`和其它用户业务文件永不进入manifest、永不删除。reset后按first init重新建立当前产品拥有的roots。
- lock覆盖reset、staging、env/config decision、swap/rollback，放在不会被reset删除的 workspace root；并发进程只有一个publisher。
- ordinary init不overwrite：existing tree为staging输入，现有JSON、prompt、用户自有文件全部保留，只补缺失packaged prompt assets，再对用户本次显式model/manifest选择做owner-owned更新。
- `--overwrite`：packaged defaults为新staging，不merge旧config；fresh current schema。不得旧schema migration/compat。
- whole-tree atomic staging/backup/swap、resolved containment、nested symlink拒绝、SIGINT/ENOSPC/rename rollback继续保留并纳入lock。跨文件系统必须在目标同父目录staging，保证`os.replace`语义。
- prewarm只在first/reset成功发布后运行一次：加载 ConfigLoader、prompt/interactive/session assembly、Fins processor registry，不发真实LLM/HTTP请求。ordinary init与`--overwrite`都不prewarm；不得因overwrite使用packaged defaults而把它重分类为first。prewarm失败给warning但已完成init仍成功；所有config validation失败必须在swap前硬失败。

### 19.4 Implementation slices

#### R12-S1 — typed catalog、交互与 secret persistence

- flow：`init args/input -> InitCatalog selection -> staged models/manifests -> EnvironmentUpdatePlan -> explicit confirmation -> OS writer`。
- tests：

```bash
pytest tests/cli/test_init_command.py tests/runtime -k 'init or model or manifest or environment or api_key'
```

覆盖每个catalog pair可由ConfigLoader加载、Ollama/custom动态字段、known manifest角色、用户manifest保留、required/optional keys、masked output、POSIX marker幂等/quoting/mode/symlink、Windows argv。tests不得把secret写入snapshot artifact。

#### R12-S2 — lock、preserve/overwrite/reset 与 atomic swap

- 复用 `dayu.runtime.filelock.file_lock`，不在CLI复制lock实现。状态机按19.3一次落地；所有异常路径清理staging/backup并恢复old tree。
- tests：

```bash
pytest tests/cli/test_init_command.py -k 'preserve or overwrite or reset or lock or concurrent or symlink or containment or interrupt or rollback'
```

覆盖first、ordinary preserve、overwrite clean defaults、reset No/Yes、portfolio不删、两个真实并发process、SIGINT/ENOSPC/replace失败、nested symlink/escape、config validation failure、env persistence failure时config unchanged。

还必须断言当前managed-root manifest只含`.dayu`与`config`：reset删除这两者；用户自建`assets`与`portfolio`均保持；package/init不创建`assets`。测试不得预造Issue151 product assets并反向冻结未来owner contract。

#### R12-S3 — prewarm、真实 smokes 与 docs

- prewarm只import/load真实 assembly，不mock“成功”；unit test用spy证明无network，first/reset各调用一次，ordinary/overwrite明确零调用。
- POSIX temp HOME/workspace smoke：Ollama（无需secret）first init→ConfigLoader/scene manifest成功→人工编辑+用户manifest→ordinary init保留并补missing prompt→overwrite重置→reset No不变→reset Yes重建；检查portfolio始终存在。secret smoke用fake HOME profile和假值，只断言masked。
- Windows CI运行同样current-schema加载、user env writer mock/isolated process、atomic tree和R11 `.cmd` smoke。

```bash
pytest tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_tools_discovery.py
```

### 19.5 README、source scan 与 stop

- 根 README完整说明选择provider/model、API key/可选integration、preserve/overwrite/reset、lock冲突、prewarm warning、workspace路径与排障；config README说明current schema与manifest变化；tests README说明真实smoke。
- source scan：secret值不在JSON/artifact/log/prompt；无 Issue 142 migration、无`dayu/assets`或从OLD搬入的product assets、无旧schema alias/merge；managed-root manifest是reset目标唯一真源，所有 mutation在同一lock/containment/atomic owner内。用户自建`<workspace>/assets`不因名称命中而删除。
- 环境变量持久化对Windows不是和config同一原子事务，这是明确 residual：必须先完成所选env写入再发布config；若config swap随后失败，报告已写env names但不打印value，不能假装跨OS原子。该风险归 R12/CLI owner并在closeout披露。
- 任何需要迁移旧schema、当前产品未拥有的workspace assets、未设计入口或无确认写用户profile的路径立即 stop。Issue151未来交付后只能由其owner更新managed-root manifest，R12不得预先代签。

## 20. README 触发决策矩阵

implementation 期间先读目标 README 内 `Agent更新约束【必须遵守】`，再按职责更新：

| sub-WU | 必查 README | 更新条件/预期 |
| --- | --- | --- |
| R01 | `dayu/config/README.md`、`tests/README.md`、根 README | 删除Doc cap/schema说明；根README仅有用户工作流文本才改 |
| R02 | config、tests、根 README | 新Web config/诊断CLI属于职责，更新；不得发布Issue178 |
| R03 | Host、Engine、config、tests | Host必查；Engine仅typed call contract变；prompt/schema变才改config |
| R04/R05 | Host、Service、config、Engine、tests | mode/policy/composition/timeout各归对应README；Engine只确认handshake |
| R06—R10 | Fins、tests；必要时Service/根 README | Fins owner contract必改；只有用户CLI/error改变才改根/Service |
| R11 | 根、Fins、tests | 用户命令/安装surface显著变化，必须更新 |
| R12 | 根、config、tests | init工作流/current schema/排障显著变化，必须更新 |

`dayu/README.md` 只有实际改变 `UI -> Service -> Host -> Engine` 分层或装配边界才更新。本计划是在既有边界内把语义放回 owner，不改变层级，因此预期无需更新；若 implementation出现反向依赖需求，应 stop而不是用README合理化。

## 21. 安全相关 retained / modified 行为清单

| 行为 | disposition | owner-level验收 |
| --- | --- | --- |
| Doc `allowed_paths`、resolve containment、symlink拒绝 | retained | R01 escaped/symlink smoke仍拒绝 |
| Doc output truncation / cancellation | retained | 大输入完整读，返回仍受结果limit且可取消 |
| Web private/custom-port authority | modified defaults, retained configurable enforcement | default allow；explicit deny逐hop有效 |
| Web DNS resolve、redirect recheck、peer proof | retained；peer proof default off | on时pinned/peer mismatch fail；proxy冲突fail closed |
| Web环境proxy | modified default allow | off不读env；on且peer-off实际走proxy |
| Web resource budgets | retained、放大、按owner split | exact/+1 owner tests；局部override |
| Browser capability | modified为独立开关 | public browser不授予private |
| challenge detection/fallback | retained | decision/evidence/diagnostics/smoke同源 |
| diagnostics v2/header/error allowlist | retained | exact v2 consumer tests |
| browser storage-state lifecycle | deleted/deferred | 只剩显式输入；Issue178拥有后续生命周期 |
| Host canonical args digest/EventLog audit | retained | ordinary/awaiting同一identity；无下游repair |
| opaque provenance | retained internal | audit可查，LLM四消费者不可见 |
| wait late-publication fence/claim | retained+timeout修正 | timeout invalidates token、release/backoff、非LOST |
| Fins ticker transaction lock、journal recovery、atomic swap | retained并收敛authority | token唯一authority；crash仅旧/新完整tree |
| Fins path containment/symlink/atomic write | retained | opaque key后攻击用例仍拒绝 |
| CLI upload script atomic write/平台专用quoting | retained/新增真实contract | POSIX `/bin/sh`与Windows真实`cmd.exe`对抗argv recorder；`DisableDelayedExpansion`，`% ! &|^()`、引号、反斜杠、Unicode exact round-trip且无命令注入；不以`list2cmdline`代签batch quoting |
| init containment/symlink/atomic swap/managed roots | retained并加入lock/confirmation | 并发、SIGINT、reset No、rollback；当前只删`.dayu`/`config`，用户assets与portfolio不删 |
| process fencing | retained | R05 late observation与现有工具process tests |

任何 retained 项失败均为 release blocker，不能以“Topic 9不做统一授权”为由删除。

## 22. Aggregate 验证、deepreview、PR gates 与 final closeout

### 22.1 Aggregate regression（R01—R12 全部完成后）

在当前 `phaseflow/host-issues-control` 分支、R01—R12串行accepted commits已整合且工作区只含授权文件时执行：

```bash
source .venv/bin/activate
pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli
pyright
git diff --check
python -m build
```

再运行以下 aggregate scans，任何非预期命中逐条归属并写入证据：

```bash
rg -n 'DocResourceBudget|SourceBudgetExceeded|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' dayu tests README.md
rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|_INTERNAL_SOURCE_REF_KINDS' dayu tests
rg -n 'stage_source_document|ingest_complete.*false|owner_scope_id|owner_token|_BATCH_OWNER_CONTEXT|_execute_with_auto_batch' dayu/fins tests/fins
rg -n 'statement_locator|statement_method_missing|raw_total|deduped_count' dayu/fins/tools dayu/fins/domain tests/fins
rg -n '\btotal\b|raw_total' dayu/fins/domain/xbrl_result_contract.py dayu/fins/processors tests/fins
rg -n 'schema_version.*commands|JSON argv|dayu-web|dayu-wechat|dayu-render' pyproject.toml dayu tests README.md
```

真实 smoke矩阵：

| Surface | 必过 smoke | 通过信号 |
| --- | --- | --- |
| Doc | >32 MiB source、>10k目录、symlink escape | 大输入/尾部命中；escape拒绝 |
| Web | private custom-port local server、proxy、peer、Playwright、challenge/diagnostics v2 | defaults/overrides与config同源 |
| Host LLM | ordinary + awaiting + resume + memory/compact/trace | 同一query/result/citation；opaque ref零泄漏 |
| Wait/Engine | observation timeout后重试；远端事务长于handshake | WAITING→resolved，never LOST；Engine已suspended |
| Fins storage | crash phases、concurrent reader/writer、opaque Unicode IDs | 只见完整A/B；round-trip且contained |
| Fins read |真实financial/XBRL fixtures + internal/public限定扫描 | internal raw total只作provider校验；public/LLM只有`fact_count=len(deduplicated facts)`；同源citation |
| Fins direct | success/missing/duplicate through Service/CLI | 唯一validator error identity |
| HKEX | cumulative >100 fixture/official nonmutating query | 最终count完整且不重复 |
| CLI upload recorder | POSIX真实`/bin/sh` + Windows真实`cmd.exe` | 对抗矩阵最终argv等于typed plan；无变量展开/命令注入；runner artifact可追踪 |
| CLI upload E2E | 生成脚本真实`python -m dayu.cli` | POSIX进入parser→Service/Fins→临时storage；Windows至少进入同一CLI grammar |
| CLI init | temp HOME/workspace + Windows CI | current schema可加载、preserve/overwrite/reset/lock正确；first/reset prewarm，ordinary/overwrite不prewarm；用户assets/portfolio不删 |

R11 独立子计划必须在 implementation 前写明 Windows runner/CI owner；actual `cmd.exe` recorder与真实CLI grammar smoke可以在非Windows本地开发之后执行，但最迟必须在本 aggregate regression或随后的draft-PR check中成功。缺少runner、workflow未触发、job skipped、artifact不可读或任一对抗字符失败都阻塞aggregate/PR/final closeout；不得把unsafe quoting或未验证Windows行为列为residual。

### 22.2 Aggregate deepreview

只有所有 sub-WU 的独立plan/review/fix/re-review/accepted-plan-commit与implementation/code-review/fix/re-review/accepted-sub-WU-commit全部通过后，才由AgentMiMo与AgentDS对最终整合diff并发执行两路独立全范围 `$deepreview`；base固定为 remediation开始前 umbrella SHA，必须覆盖：

- correctness/stability/maintainability；adversarial failure pass；项目/README约束；过度耦合；semantic ownership drift；
- durable state、trace、memory、LLM projection同源；config→composition→runtime；storage→producer→read；
- security retained matrix、failure injection、跨平台脚本、fresh schema无兼容；
- accepted/deferred/no-code追踪表逐项反证：确认没有越界完成Issue 142/151/175/177/178，没有改Topic8/新增Topic9框架。

两路 deepreview findings 先由controller逐项裁决。任何 severity 的 accepted actionable finding都由AgentCodex回到对应owner/sub-WU修复，并重跑该sub-WU双路完整code review及两路aggregate deepreview/re-review；不得只review修补hunk。rejected/deferred/note不得误实现。全部accepted finding关闭后，controller创建accepted deepreview local commit。

### 22.3 PR gates

本 plan-fix gate禁止创建commit或PR。未来只有以下全满足，umbrella controller才进入已授权的`ready-to-open-draft-PR -> push -> create draft PR` gates：

1. R01—R12各自的plan、双plan review、controller adjudication、plan fix、双plan re-review、accepted plan commit、implementation、双code review、code fix、双code re-review、accepted sub-WU commit与completion reports齐全；umbrella总计划不得替代任一artifact；
2. aggregate regression/smoke/pyright/diff/source scans通过；changed production files各自coverage `>=80%`；
3. 两路aggregate deepreview/fix/re-review最终pass；任何severity的accepted finding均已关闭，controller已创建accepted deepreview local commit；
4. README触发矩阵完成，design truth/control doc只由其gate owner按流程更新；
5. `git status`只含本umbrella授权文件，无临时coverage、secret、generated scripts、staging/backup；
6. Windows真实`cmd.exe` recorder与CLI grammar checks有成功runner/CI artifact，不能pending或skip；
7. PR title/body明确这是既有 umbrella remediation continuation，列出Topics、non-goals、baseline、smoke、residual risks；PR只创建为draft。

本轮用户已授权 controller 在明确gate创建 accepted-plan、accepted-sub-WU、accepted-deepreview、accepted-PR-review local commits，并在上述criteria满足后push和创建draft PR；这些动作无需再次询问。draft PR创建后仍必须执行双路PR review、controller adjudication、AgentCodex修复全部severity的accepted finding、双路完整re-review、controller accepted PR-review local commit与follow-up push。未经额外授权始终禁止 mark ready、merge、approve、request reviewers、发布任何外部comment、创建/修改issue或删除branch。

### 22.4 Final closeout 验收矩阵

| 验收维度 | 必需证据 | closeout判定 |
| --- | --- | --- |
| Topic decisions | 第4节每行对应diff/test/scan | accepted全闭合；deferred/no-code无越界diff |
| Semantic owner | owner map + exact call path + tests | 无重复producer/validator/policy |
| Durable consistency | EventLog/wait/storage crash tests | state/trace/memory/public一致 |
| LLM-facing | prompt/schema/result/source scans与smoke | 自足、无internal ref/secret/实现术语 |
| Config/runtime | packaged config/parser/composition tests | 无scene heuristic或hidden default |
| Fins atomic/read | crash/concurrency/snapshot tests | 不见half source，不从consumer反推revision |
| Cross-platform CLI | POSIX与真实Windows `cmd.exe` CI artifacts | recorder argv exact round-trip、无注入、真实CLI grammar；unsafe quoting/runner pending均不通过 |
| Security | 第21节逐项证据 | retained全部通过，modified符合裁决 |
| Quality | targeted/full pytest、每文件coverage、pyright、diff | 无新增/扩散failure |
| Reviews | 每sub-WU独立双plan review/re-review、双code review/re-review + 双路aggregate/PR review | 所有severity的accepted finding已修复；rejected/deferred/note未误实现 |
| Documentation | README decision log | 用户/开发者contract与代码同源 |
| Scope | diff/file/issue scan | 无Issue142/151/175/177/178、Topic8/9越界 |

final closeout只有矩阵全绿才可 `final closeout pass`。任一项为partial/unknown必须标blocked，不能用residual risk替代accepted contract。

## 23. Residual risk owner / destination

| residual risk | 当前处理 | owner / destination |
| --- | --- | --- |
| Doc极大输入可能耗尽资源 | 本WU删除未经裁决的业务hard-fail，保留spool/cancel/output limit | Issue177：完整TruncationManager/输入治理设计 |
| browser credential state retention/refresh/并发cleanup | 本WU删除utility自造lifecycle，只保留显式输入 | Issue178 |
| Fins thread-backed长事务不可物理取消 | wait fencing防late publication，不迁移executor | Issue175 |
| future product assets与其它init迁移 | 当前package不创建/搬入assets，用户自建assets不删；未来product assets只由Issue151加入同一managed-root manifest | Issue142/151各自owner |
| Windows env写与POSIX profile/config无法形成跨资源全局原子事务 | 必需env先成功再config swap；失败报告env names不泄值 | R12 CLI owner；closeout明确披露 |
| HKEX未来可能出现rowRange硬cap | 当前官方累计协议无证据支持第二机制 | HKEX provider后续evidence-driven issue；观察到真实cap才立项 |
| Web peer proof与企业proxy同时启用不可证明最终peer | typed incompatibility fail closed，默认peer proof off/proxy allow | Web config owner；README/diagnostics说明 |
| unified tool authorization尚未设计 | 保留局部permission/I/O防御，不建立临时框架 | Topic9后续独立design WU |

这些 residual 均不得把 Topic 1—7 已接受行为降为partial；若实施发现新的accepted contract缺口，必须回controller，不得自行转成residual。

## 24. Completion report format

每个 sub-WU和最终umbrella closeout都使用以下格式，禁止只写“tests pass”：

```text
状态：complete | blocked
umbrella：WU-SEMANTIC-OWNERSHIP-01
内部 remediation sub-WU：Rxx（不是独立WU）
实现 SHA / diff base：
独立plan artifact / accepted plan commit：
双路plan review / fix / 双路re-review / controller adjudication：
语义 owner：
改了什么：
删除了什么 contract：
保留/修改了什么安全行为：
真实入口与调用链证据：
状态/错误不变量：
targeted tests（命令、passed/failed）：
changed-file coverage（逐文件百分比）：
pyright：
git diff --check / allowed-file scan：
LLM/source/security propagation scan：
真实/跨平台 smoke：
README decision：
baseline failure registry delta：
双路code review / fix / 双路re-review / controller adjudication：
全部finding final disposition/status（不限severity）：
accepted sub-WU commit：
blocking open questions：无 | 逐项
residual risks（owner/destination）：
下一依赖 handoff：
```

最终报告另加 aggregate deepreview、PR checks、final closeout矩阵和 deferred/no-code无越界证据。

## 25. 为什么该计划没有过度设计

1. 只计划 controller 已接受的 Topic 1—7，不把 review建议或未来issue自动升级成实现。
2. 12个sub-WU按唯一 owner、durable/public blast radius与可独立失败/回滚闭环切分；没有按22个finding或文件数机械拆分，也没有新建umbrella替代物。
3. 每个sub-WU最多3个slice；共享一个真实commit point或projection的事项合并，独立状态机/配置/跨平台入口才分开。
4. 接口优先使用显式参数和现有typed contract；没有profile/factory/god bag、兼容层、下游fallback或speculative通用框架。
5. 预算、catalog与脚本业务规则只在controller/design已裁决或OLD-aligned真实工作流要求处出现；R07 retry次数、hash/revision grammar、新异常/lease类型等内部实现细节留给独立子计划基于代码证据决定，不暴露成business/public/LLM contract。
6. 验证成本按umbrella optimization复用baseline、共同命令模板与aggregate gate，但production/public/LLM/state-machine风险仍保留每sub-WU双路完整review，不用成本优化稀释正确性。

## 26. 本 plan gate 的最终 stop

本文与re-review-fix artifact写完后只执行：必读材料/真实入口核对、`git diff --check`、两个目标artifact diff审阅、`git status --short`确认仅新增/修改期望artifact。所有命令只作plan evidence，不修改产品。完成即停止，本 gate 不进入第二轮 re-review；下一动作只能由umbrella controller另行派发AgentMiMo/AgentDS对完整最终计划执行第二轮双路re-review，在两路closure与controller裁决前不得进入R01子计划或implementation。
