# Code Review — WU-CLI-FINS-OBS-01 S6 README Sync

## Scope

- Mode: current changes (S6 docs-only)
- Branch: `phaseflow/host-issues-implementation`
- Base: `main` (changes are uncommitted, reviewed as workspace diff)
- Output file: `docs/reviews/wu-cli-fins-obs-01-s6-review-ds-20260615-204936.md`
- Included scope:
  - `dayu/README.md` (uncommitted diff)
  - `dayu/fins/README.md` (uncommitted diff)
  - `docs/reviews/wu-cli-fins-obs-01-s6-implementation-codex.md` (Codex implementation artifact)
  - Cross-reference: Slice S6 plan (`docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`)
  - Cross-reference: S1–S5 committed code facts (`dayu/service/fins_direct.py`, `dayu/fins/ingestion_runtime.py`, `dayu/fins/ingestion_events.py`, `dayu/cli/commands/fins.py`, `dayu/cli/main.py`)
  - Cross-reference: `dayu/service/README.md` and `tests/README.md` (unmodified, verified)
- Excluded scope: production code, test code, control_doc files, other READMEs not triggered by S6 plan or S1–S5 implementation
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项核查结果

#### 1. README 是否只写已落地事实

**通过。** 三处 dayu/README.md diff 和一处 dayu/fins/README.md diff 均以 S1–S5 已提交的生产代码为真源：

- `dayu/service/fins_direct.py:550-611` 中存在 `stream_job_events_until_terminal(...)`，产出 event stream 并在 terminal event sidecar 缺失时合成 terminal fallback（`dayu/service/fins_direct.py:815-820`）——与 dayu/README.md diff 的 "event observation / poll terminal fallback" 一致。
- `dayu/fins/ingestion_runtime.py:1423-1478` 中存在 `read_job_events(...)`，`dayu/fins/ingestion_runtime.py:63` 定义 `.events.jsonl` sidecar——与 dayu/fins/README.md diff 的 "Fins job event sidecar" 一致。
- `dayu/cli/main.py:69-70` 调用 `runtime_log.set_level_from_flags(...)`——日志装配已落地。

无任何 README diff 描述未实现能力或未来计划。

#### 2. 是否正确表达 Fins direct start / event observation / poll terminal fallback / cancel

**通过。** 三处 dayu/README.md 变更点均正确表达完整语义链：

| 位置 | 旧描述 | 新描述 | 代码事实 |
|------|--------|--------|----------|
| 稳定边界 `dayu.service` (原 L72) | start / poll / cancel | start / event observation / poll terminal fallback / cancel | `stream_job_events_until_terminal` event loop + `_synthesize_terminal_event` fallback |
| 主要组件 `dayu.service.fins_direct` (原 L88) | poll terminal | event observation、poll terminal fallback | 同上 |
| 工具与 Fins 执行路径 (原 L111) | 轮询 read_job(job_id) | 消费 Fins job event、必要时回退轮询 terminal job record | `read_job_events(...)` 主路径 + terminal job record fallback |

cancel 语义在 dayu/fins/README.md 状态机与关键机制章节和 dayu/README.md Steer 与 cancel 章节保持正确。

#### 3. 是否明确 Fins job event sidecar 不是 Host EventLog/Host truth

**通过。**

- `dayu/fins/README.md` 事件流章节 (L525-530) 新增行明确写："direct job 调用方通过 `read_job_events(...)` 读取的 Fins job event sidecar；这些事件只服务 Service / UI 观察，不是 Host durable truth。" 且同段落首句新增 "也不写 Host EventLog"。
- `dayu/README.md` 的 "消费 Fins job event" 位于工具与 Fins 章节而非 Host 事件章节，且上下文为 "CLI 等 direct 数据命令不创建 Host Run"，语义边界清晰。

#### 4. 未修改 dayu/service/README.md 和 tests/README.md 的理由是否成立

**成立。** 逐一验证：

- `dayu/service/README.md` (L13)：已包含 "job start、job event observation、poll terminal fallback、durable cancel request 与 terminal exit mapping"，以及 "stream_job_events_until_terminal(...) 消费 Fins job event；若 terminal event sidecar 缺失但 job record 已终态，Service 会记录 bounded WARN 并合成 terminal event"。这与 S6 plan 要求的 "加入 event stream consumer" 完全一致，是在 S1–S5 实施中同步更新的。
- `tests/README.md` (L94-102)：`tests/cli/` 章节已覆盖 "Service event stream 消费、progress / terminal summary stdout/stderr 投影" 和 "terminal exit mapping、SIGINT 后 request_cancel(job_id) 与第二次 SIGINT 本地 130"。(L137)：`tests/service/` Fins direct 章节已覆盖 "job event stream 按 sequence 投影 progress 与 terminal、terminal event 缺失时的 bounded WARN + 合成 terminal fallback"。(L178)：`tests/fins/` 章节已覆盖 "ingestion job event sidecar 的 queued/running/terminal/status observation 序列" 和 "read_job_events(...) 游标读取、bounded payload 与敏感内容不落 sidecar"。三项与 S6 plan 要求的覆盖说明高度一致。

#### 5. 是否遗漏 README 触发

**无遗漏。** S6 plan 列出的四份受触发 README 均已检查：

| README | 触发来源 | 检查结论 |
|--------|----------|----------|
| `dayu/README.md` | 分层关系/Service边界变化 | 已更新 ✓ |
| `dayu/fins/README.md` | `dayu/fins/` 修改 | 已更新 ✓ |
| `dayu/service/README.md` | `dayu/service/` 修改 | 已含所需内容，无需修改 ✓ |
| `tests/README.md` | `tests/` 修改 | 已含所需内容，无需修改 ✓ |

未触发 `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/config/README.md`（相关包未被 S1–S5 修改）。

#### 6. 是否有术语/分层/LLM-facing 语义错误

**无。**

- 术语：所有 diff 中 "Fins job event"、"event sidecar"、"Host EventLog"、"Host durable truth" 用法自洽且与 CLAUDE.md 核心术语定义一致。未将 Fins job event 称为 EventLog fact、HostEvent 或 EngineEvent。
- 分层：dayu/README.md 稳定边界中 `dayu.service.fins_direct` 的描述保持在 Service 组合边界内，未穿透到 Host truth。dayu/fins/README.md 事件流章节新增的 sidecar 说明在 Fins 事件流章节内闭合，未混淆为 Host 事件机制。
- LLM-facing 语义：diff 内容为开发者手册，不进入 LLM prompt/schema/tool description，不触发 Agent 语义约束。

## Open Questions

无。

## Residual Risk

- README 变更无独立测试覆盖，验证仅通过人工核对。这是 README-only slice 的正常风险轮廓，可接受。
- 后续 Fins pipeline 细粒度 event stream 扩展（当前 deferred）将再次触发 `dayu/fins/README.md` 和 `dayu/README.md` 更新，届时需重新核对 README Agent更新约束。

## Conclusion

**PASS**

S6 README Sync 的三处 dayu/README.md diff 和一处 dayu/fins/README.md diff 均以 S1–S5 已提交生产代码为事实真源，正确表达 Fins direct 的 start → event observation → poll terminal fallback → cancel 完整语义链，明确区分 Fins job event sidecar 与 Host EventLog。dayu/service/README.md 和 tests/README.md 未修改的理由成立——两者在 S1–S5 实施中已更新至与代码一致。无遗漏 README 触发，无术语、分层或 LLM-facing 语义错误。Codex 实现 artifact 中的直接证据与代码事实一致，验证过程记录完整。
