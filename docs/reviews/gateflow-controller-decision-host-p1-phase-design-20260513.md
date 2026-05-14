# Host Phase 1 Phase Design Controller Decision

## Work Gate

phase design controller decision

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Reviewed Artifacts

- Phase design refinement: `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md`
- AgentMiMo phase design review: `docs/reviews/gateflow-phase-design-review-host-p1-mimo-20260513.md`
- AgentDS phase design review: `docs/reviews/gateflow-phase-design-review-host-p1-ds-20260513.md`
- Phase design fix: `docs/reviews/gateflow-phase-design-fix-host-p1-codex-20260513.md`
- AgentMiMo phase design re-review: `docs/reviews/gateflow-phase-design-re-review-host-p1-mimo-20260513.md`
- AgentDS phase design re-review: `docs/reviews/gateflow-phase-design-re-review-host-p1-ds-20260513.md`

## Controller Decisions

### Finding 1: `FrameworkToolPolicyView` 缺少 typed shape

- Decision: accepted。
- Fix status: fixed。
- Re-review result: AgentMiMo fixed；AgentDS fixed。
- Controller rationale: `HostToolingOptions` 引用 `FrameworkToolPolicyView`，如果没有 typed shape，Phase 1 implementation agent 必须现场决定 reserved name 集合、enablement 语义、是否实现 policy resolution 以及与 `ToolGovernancePolicyView` 的关系，属于 material design gap。

### Finding 2: `implementation-control.md` 当前状态段滞后

- Decision: accepted。
- Fix status: fixed。
- Re-review result: AgentMiMo fixed；AgentDS fixed。
- Controller rationale: 总控文档是 phase gate 与当前状态真源，继续保留 P0 PR gate 会误导后续 Agent。

### Finding 3: `ToolBundleSourceRef.source_kind` Python 类型表达未决

- Decision: accepted。
- Fix status: fixed。
- Re-review result: AgentMiMo fixed；AgentDS fixed。
- Controller rationale: `source_kind` 需要稳定序列化与受限取值。按 Python 3.11 约束，裁决为 `enum.StrEnum`，同时将 `FrameworkToolName` 裁决为 `enum.StrEnum`。

### Finding 4: Phase 1 退出条件缺乏可验证验收标准

- Decision: accepted。
- Fix status: fixed。
- Re-review result: AgentMiMo fixed；AgentDS fixed。
- Controller rationale: 原退出条件是主观判断，容易导致 plan review 和 closeout 分歧。已改为 typed contract、runtime helper、测试、pyright、docs 与 non-goals 的可验证清单。

## Gate Result

Phase 1 phase design refinement 通过 review / fix / re-review loop。用户追加反馈后，controller 重新打开 phase design fix：

- lane 必须支持单机多客户端 / 多进程，因此 process-local lane design 被判定为不成立，已改为 cross-process runtime named semaphore / capacity guard。
- Phase Map 按用户裁决重排：P12 为 ToolsDiscovery / ScenePrepare，原 P12 Audit / Tool Trace / Outbox 后移为 P13，RemoteProxy 后移为 P14，Retention / Purge 后移为 P15。

AgentMiMo 与 AgentDS 的 round2 phase design re-review 均为 PASS，new blocker 为 0。当前没有 blocking open question。当前 gate 停在用户确认点：用户确认后才能进入 Phase 1 phase plan。

## Residual Risks And Tracking

- `dayu.host` 初始模块拆分、公共导出边界和测试文件布局：由 Phase 1 phase plan 覆盖。
- `dayu.runtime.lane` 具体实现细节：由 Phase 1 phase plan 覆盖，必须实现 cross-process runtime capacity guard，同时保持层中立，不表达 Host truth、Run / Attempt owner、EventLog ordering、Host admission、Host durable SQLite transaction、CAS 状态迁移、lease / fencing、Attempt takeover 或 recovery proof。
- Cross-process lane 的 SQLite runtime coordinator 会引入 workspace-level runtime DB；默认路径注入、SQLite schema、heartbeat ownership、busy timeout、TTL cleanup 与多进程测试由 Phase 1 phase plan 明确。
- ToolsDiscovery / ScenePrepare 具体 adapter、manifest schema、provider 注册生命周期和业务装配代码：deferred to Phase 12，不进入 Phase 1 implementation-ready plan。
- 多 scene tool profile、profile registry、tool snapshot durability 与 source ref digest 算法：deferred to ToolRuntime / command path 相关后续 phase。

## Next Gate

等待用户确认进入 Phase 1 phase plan。未获用户确认前，不进入 plan、implementation、commit、PR 或 closeout。

## Artifact Path

`docs/reviews/gateflow-controller-decision-host-p1-phase-design-20260513.md`
