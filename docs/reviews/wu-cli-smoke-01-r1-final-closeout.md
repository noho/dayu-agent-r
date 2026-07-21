# WU-CLI-SMOKE-01-R1 Final Closeout

## Gate

- Work unit: `WU-CLI-SMOKE-01-R1`。
- Gate: `final-closeout-pass`。
- Date: 2026-07-21。
- Design truth: `docs/host/design.md` 与 `docs/engine/design.md`。
- Draft PR: https://github.com/noho/dayu-agent-r/pull/180
- Branch: `phaseflow/wu-cli-smoke-01-r1`。
- Base: `main`。
- Independent Issue owner: none by current WU decision；PR body 不含 closing directive。
- Accepted PR review head: `3900b0690b39c5e131aa79542130aa08ec22626e`。
- Status: pass。

## Motivation And Semantic Owner

问题成立且严重度合理：三类 per-chunk Engine delta 只表达当前运行期的即时展示材料，其中 `REASONING_DELTA` 却被逐条写入 EventLog。这会按 chunk 数放大 SQLite durable rows，并错误承诺 token-level replay 语义；retention、CLI fallback 或 reasoning 专用旁路都不能修复该所有权错误。

最终唯一 owner 边界如下：

- `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 由同一 `open_host` 当前 runtime 内的 Host typed transient fanout 产生、校验和投影，三者 EventLog row 均为 0。
- durable terminal fact、final answer、activity、Outbox、恢复与离线补读仍由 EventLog / Outbox 拥有；transient identity 不冒充 durable `event_sequence` 或 replay cursor。
- Service 只消费 Host public `HostSessionEvent` union，并通过容量 256 的 bounded relay 传递；CLI 只把 reasoning 投影给 thinking renderer，未选择的 content/tool-call delta 不产生重复输出。
- transient delivery 不跨 detach、overflow、进程断线或 Host restart 恢复。这是明确的 live-only contract，不是 durable 丢失补偿策略。

## Accepted Commits

- Plan: `929691ea`。
- Slice 1: `70ccda60`。
- Slice 2: `d58014cf`。
- Aggregate deepreview: `2d38abad`。
- Accepted PR review: `3900b069`。

Draft PR gate record `5bd27be7` 与 PR review entry record `ff5d515a` 只记录 gate 迁移，不改变上述产品语义 owner。

## Review And Finding Status

- Plan 经过 AgentMiMo / AgentDS 双路 review、AgentCodex fix 与双路 re-review；accepted findings 全部关闭。
- Slice 1 经过双路 code review；唯一 accepted test-owner coverage finding 已由 AgentCodex 修复并经双路 re-review 关闭。
- Slice 2 双路 code review 均 PASS，0 blocking finding。
- Aggregate deepreview artifacts：
  - `docs/reviews/wu-cli-smoke-01-r1-aggregate-deepreview-mimo.md`。
  - `docs/reviews/wu-cli-smoke-01-r1-aggregate-deepreview-ds.md`。
  - `docs/reviews/wu-cli-smoke-01-r1-aggregate-deepreview-controller-adjudication.md`。
- 两路 aggregate verdict 均 PASS；Controller 基于 owner state、可达 schedule 与变更归属裁决 0 个 accepted current-fix finding。
- Draft PR #180 双路完整 review 均确认代码与架构 PASS。Controller 直接检查接受唯一 finding `PR180-F01`：PR body 使用了字面量反斜杠-n。
- AgentCodex 仅修复 PR metadata；Controller 验证后，AgentMiMo / AgentDS 双路 narrow re-review 均确认 `PR180-F01` fixed、0 blocking、0 new finding。
- Supplemental finding-fix batch 已在 `docs/phaseflow-umbrella-optimization-control.md` 标记 completed。
- 用户要求所有 remaining risk 经代码裁决后以 WU 进入主总控。AgentCodex proposal 与 AgentMiMo/AgentDS 双路对抗复核均完成；Controller adjudication 为 `docs/reviews/wu-cli-smoke-01-r1-residual-risk-wu-reconciliation-controller-adjudication.md`，decision=`accepted-residual-risk-WU-reconciliation`。

## Validation

- Host / Service / CLI aggregate suite：`2816 passed, 8 skipped, 6 deselected, 3 warnings`。
- `dayu/host/transient_delta.py` owner coverage：`90.96%`，达到单文件不低于 80% 的目标。
- 新增 owner / E2E 闭环：`21 passed`。
- 独立 `3 × 1000` transient stress：`1 passed`。
- 全量 pyright：`0 errors`。
- EventLog zero-row、public boundary、raw EngineEvent dependency、transient/durable identity 与 propagation scans：pass。
- `git diff --check`：pass。
- Accepted PR review head `3900b069` 的 GitHub Windows checks：
  - `windows-init-transaction`: pass，5m05s。
  - `windows-upload-script`: pass，4m04s。
- PR invariants：Draft=true、base=`main`、head branch=`phaseflow/wu-cli-smoke-01-r1`、review requests 为空、body 为真实 Markdown 多行且无 closing directive。
- Residual-risk owner/path regression：75 passed，3 个第三方 deprecation warnings；独立 transient stress 1 passed；全量 pyright 0 errors；双路 proposal review accepted。

## README Decision

本 WU 触发并完成了对应稳定文档检查：`dayu/README.md`、`dayu/host/README.md`、`dayu/service/README.md` 与 `tests/README.md` 已按职责同步；`docs/host/design.md` 已记录 transient/durable owner 边界。没有用户安装、命令参数或工作区位置变化，因此根目录 `README.md` 不需要机械更新。

## Residual Risk Reconciliation

### Remaining Risks Entered As Work Units

| Work Unit | 状态 | Owner / Destination | 触发条件与下一步 |
|---|---|---|---|
| `WU-HOST-TRANSIENT-CAPACITY-01` | deferred-with-owner / needs-more-evidence | Host transient hub performance-validation lane / user decision | 有代表性 workload/watcher SLO 或实际 slow-consumer、内存、交付延迟证据后，先做 owner-level profile/benchmark，再决定是否调整私有容量；不修改 Service、不增加 public knob/unbounded queue/replay。 |
| `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` | deferred-with-owner / needs-more-evidence | Service entrypoint live relay performance-validation lane / user decision | 有代表性消费 workload/terminal SLO 或实际 relay backlog、fallback、终态延迟证据后，单独 profile Service relay，再决定是否调整；不修改 Host、不共享跨层常量、不 silent drop。 |
| `WU-CLI-SMOKE-01-R2` | deferred-with-owner | CLI UI adapter lane / user decision | 当前是每个 delta 单行化并按 160 字符截断后累计追加，累计行无明确上限/panel/history；用户明确 UX、累计缓冲、TTY/非 TTY 与历史保留要求后进入 goal confirmation。 |

以上三项均已同时进入 `docs/host/issues-implementation-control.md` 的 Residual Risk Reconciliation 表和 Current Work Units 表。

### Removed After Code Adjudication

| 原条目 | 最终裁决 | 删除理由 |
|---|---|---|
| live-only 不补放 | rejected-with-reason as remaining risk | `docs/host/design.md`、Host typed envelope/runtime 与 owner tests 共同证明这是已接受 contract，不是遗漏；修复会引入新的 durable replay 产品协议。 |
| durable/transient 无跨域可重放总序 | rejected-with-reason as remaining risk | 两个 sequence domain 是防止 live presentation 冒充 durable fact 的设计；统一可重放序列需要新的 persistence/query contract。 |
| R1 E2E 使用可控 worker | rejected-with-reason as remaining risk | 可控 worker 是稳定构造三类 delta/overflow/terminal 的正确 oracle；其后的 Host、Service、SQLite/Outbox、CLI 均走生产路径，真实 provider 不能替代该确定性 failure matrix。 |

五项均经过 AgentCodex 代码核对、AgentMiMo/AgentDS 双路复核与 Controller 裁决。没有可在当前 R1 WU 通过最小正确实现关闭的事项，也没有未归属或阻塞 `final-closeout-pass` 的 remaining risk。

## Final Status And Next Entry Point

`WU-CLI-SMOKE-01-R1` 已到达 `final-closeout-pass`。Draft PR #180 保持 open / draft，等待用户或 maintainer 审阅和处理。

未经明确授权，不得 mark ready、merge、request reviewers、close issue、发布外部 closeout comment 或 delete branch。该 WU 没有独立 Issue owner，因此没有 issue closeout 动作。PR #180 被处理后，从 `main` 同步最新代码，再按 `docs/host/issues-implementation-control.md` 由用户选择下一 work unit。
