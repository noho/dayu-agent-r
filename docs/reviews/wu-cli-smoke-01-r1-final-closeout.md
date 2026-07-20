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

## README Decision

本 WU 触发并完成了对应稳定文档检查：`dayu/README.md`、`dayu/host/README.md`、`dayu/service/README.md` 与 `tests/README.md` 已按职责同步；`docs/host/design.md` 已记录 transient/durable owner 边界。没有用户安装、命令参数或工作区位置变化，因此根目录 `README.md` 不需要机械更新。

## Residual Risk Reconciliation

| 边界 | 状态 | Owner / Destination | 接受理由或重开条件 |
|---|---|---|---|
| overflow、detach、断线、Host close / crash / restart 后不补放 delta | accepted live-only boundary | Host transient runtime contract / `docs/host/design.md` | per-chunk delta 不是 durable fact；需要 replay 时必须以新的 durable product requirement 重新设计，不能给当前 contract 加 fallback。 |
| watcher 与 Service relay 容量固定为 256，尚无真实负载调优数据 | accepted internal bound | Host transient hub 与 Service relay owner | 当前有 bounded slow-consumer failure contract；仅在生产负载证据表明容量不合适后重开 tuning，不提前暴露 public knob。 |
| durable 与 transient 不承诺跨域可重放总序 | accepted ordering boundary | Host public event contracts | 两个域各自有序，并由同 Run terminal fence 防止 terminal 后交付；全局 replay order 会混淆不同语义 owner。 |
| E2E 以可控 worker 替代外部 LLM provider | accepted test boundary | Future provider integration smoke / user decision | worker 之后的 Host、Service、SQLite / Outbox 与 CLI 均为生产路径；真实 provider 波动不应成为 owner-level deterministic contract test 的真源。 |
| CLI thinking 仍为 160 字符单行展示 | deferred-with-owner | `WU-CLI-SMOKE-01-R2` / future CLI UI enhancement | 仅在用户要求可展开 thinking panel 时进入独立 UI work unit。 |

没有未归属或阻塞 `final-closeout-pass` 的 residual risk。

## Final Status And Next Entry Point

`WU-CLI-SMOKE-01-R1` 已到达 `final-closeout-pass`。Draft PR #180 保持 open / draft，等待用户或 maintainer 审阅和处理。

未经明确授权，不得 mark ready、merge、request reviewers、close issue、发布外部 closeout comment 或 delete branch。该 WU 没有独立 Issue owner，因此没有 issue closeout 动作。PR #180 被处理后，从 `main` 同步最新代码，再按 `docs/host/issues-implementation-control.md` 由用户选择下一 work unit。
