# WU-SEMANTIC-OWNERSHIP-01 P3-B plan-fix（AgentCodex）

## Gate metadata

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-B`。
- Gate：plan-fix only。
- Timestamp：`2026-07-10T14:20:30+08:00`（本机系统时钟）。
- Target：`docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`。
- Inputs：
  - `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-b-plan-review-controller-adjudication.md`
- Write scope：只修改 target plan，并新建本 artifact；未修改生产代码、测试、control doc、其它 review artifact或并发 CLI-CI 文件。

## 第一性原理与 owner boundary

动机成立，且 controller 对严重性的判断合理：生产 success closeout 已把 `FinalAnswerData.content` 写入可校验 descriptor，但当前 Outbox inline-only reader会把 descriptor-backed answer投影成 `succeeded + final_answer=None`。根因位于 Host terminal-answer source-selection/projection owner，不能在 Service/UI 或 fixture 中补洞。

事实传播边界保持不变：Engine 首次产生 `FinalAnswerData.content`；Host ingest 校验并持久化 terminal descriptor；`_run_terminal_payload` 持久化 canonical descriptor pair与metadata；Host terminal-answer resolver选择 inline/design-approved continuity source或 digest-checked descriptor content；HostEvent、Outbox和 typed memory/compact/run-input material消费该 owner 输出。metadata 继续由 canonical `RUN_SUCCEEDED` 拥有，不随 content source 切换。

## Controller accepted plan fixes

### P3-B-PF-01 — fixed

- 将 Engine-origin 事实产生点精确到 `engine_ingest._final_answer_plan`（`4885-4931`）。
- 将 Engine-origin closeout精确到 `engine_ingest._close_terminal`（`1184-1283`）和 `_write_terminal_payload`（`3533-3573`）。
- 将 Host-lifecycle closeout精确到 `engine_ingest._close_host_lifecycle_terminal`（`1285-1372`）。
- 将最终 durable canonical payload builder精确到 `durable/run_transition._run_terminal_payload`（`4551-4584`），明确它写 descriptor pair与canonical metadata、不写 inline answer。
- 引用 `docs/host/design.md:3082`：inline `RUN_SUCCEEDED.final_answer` 与 digest-checked terminal artifact `content` 都是明确允许的 continuity source；保留 inline policy不是兼容代码，也不要求 production同时生产两种 shape。

### P3-B-PF-02 — fixed

- 增加 `projection.py:464-471,626-644`、`outbox.py:147-168`、`durable/outbox.py:243-305` 和 `durable/transaction.py:288-360` 的具体事务证据，证明 consumer apply、Outbox insert、checkpoint advance与failure clear共享同一 `HostTransaction`，异常整体 rollback。
- 增加 `projection.py:472-489,653-685` 的证据，证明 failure row在 apply transaction rollback后由独立 `run_write` 持久化。
- 固定 Outbox 专项原子性断言，并把任何非原子代码事实设为 implementation stop condition。当前假设经核验成立，未触发 stop。

### P3-B-PF-03 — fixed

- 核实 `tests/host/public_smoke_support.py:242-292,314-371` 的 `FinalAnswerHandle` / `FinalAnswerWorkerFactory` 实际产出 `EngineEventType.FINAL_ANSWER`，并经 `open_host` production ingest/closeout运行。
- 规格化 `tests/host/test_public_offline_outbox_smoke.py` 的新增门槛：直接读取 canonical `RUN_SUCCEEDED.payload_json`，断言无 inline `final_answer` key、有完整 descriptor pair且 digest可校验；随后断言 live/read/drain answer content和terminal identity一致。
- 明确 inline-only `ProjectionEventView` fixture不能代替 production smoke。

### P3-B-PF-04 — fixed

- 否定模糊的“正式 PayloadStore恢复同 ref/digest”说法：typed SQLite payload writer会同时插 payload row与descriptor，不能在 payload row仍存在时只恢复缺失 descriptor。
- 固定使用仓库已有 test-only durable mutation模式：保存 descriptor全部 durable columns，只删除 descriptor row；首次 catch-up验证 failure/item/checkpoint；另一笔测试 transaction原样插回同一 row并断言 ref/digest/sqlite payload id不变；重试验证 item+checkpoint提交和failure清除。
- 对同一 typed event再次调用 consumer，断言 `DUPLICATE` 且 item计数仍为1；禁止新增 production repair API或更换 ref/digest。

### P3-B-PF-05 — fixed

- 在 `_terminal_answer.py` 固定 descriptor pair owner check，并要求 required/optional helper共用一个模块级私有 resolution core。
- 封闭区分：双缺失、ref-only、digest-only、descriptor row missing、SQLite row missing、digest mismatch、invalid JSON、top-level non-object、content missing、content blank、content non-text。
- 每类 failure 均要求 `HostDurableError` 与可区分的稳定 cause fragment；ProjectionRunner failure row断言 `last_error_code == "HostDurableError"` 且 `last_error_message` 保留对应根因。诊断保持 internal，不进入 LLM-facing material。

## Controller rejected concerns preserved

- 不把当前 `HostFinalAnswerView`、Outbox public/durable validator尚未实现的 invariant gap重复判成 plan gap；原 plan的 exact changes与行为测试继续负责实施。
- final-answer content source与metadata owner保持分离：`filtered` / `degraded` / `finish_reason` 继续从 canonical `RUN_SUCCEEDED` 派生，不随 inline/descriptor content source切换。
- 不移除 design-approved inline source，不把它标成测试兼容路径。
- 不强制修改 `dayu/host/terminal_payload.py`；只有实施时出现真实 docstring语义缺口才允许触碰。
- implementation slice保持 1 个，不拆出会产生中间非法 contract 的子 slice。

## Gate result

- PF-01：fixed。
- PF-02：fixed；原子性假设成立，stop condition未触发。
- PF-03：fixed。
- PF-04：fixed。
- PF-05：fixed。
- Implementation slices：1（S1）。
- Blocking questions：0。
- Next gate：parallel plan re-review；本轮未进入。

## Validation

- `git diff --check`：pass（exit 0，无输出）。
- plan 未跟踪文件 no-index check：pass（无 whitespace diagnostic；exit 1 仅表示与 `/dev/null` 存在内容差异）。
- 本 plan-fix artifact 未跟踪文件 no-index check：pass（无 whitespace diagnostic；exit 1 仅表示与 `/dev/null` 存在内容差异）。
- pytest / pyright：未运行；本 gate只修改 Markdown plan/review artifact，未修改生产代码或测试。

Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-b-plan-fix-codex.md`。
