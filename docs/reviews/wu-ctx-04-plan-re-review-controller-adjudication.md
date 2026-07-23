# WU-CTX-04 plan re-review 总控裁决

## Gate metadata

- Work unit：`WU-CTX-04`
- Gate：plan re-review adjudication
- Plan：`docs/reviews/wu-ctx-04-plan-codex.md`
- Plan fix：`docs/reviews/wu-ctx-04-plan-fix-codex.md`
- Re-review artifacts：
  - `docs/reviews/plan-review-20260722-113813.md`（AgentMiMo，`pass-with-risks`）
  - `docs/reviews/plan-review-20260722-113814.md`（AgentDS，`pass-with-risks`）
- Controller decision：`needs-fix`
- Blocking open questions：None

## Closure of the original accepted findings

两路 re-review 均确认前轮总控接受的7组fix requirements已经修复；总控复读plan、fix artifact与直接代码证据后同意该结论：同handle唯一attachment、close/drain基本顺序、deterministic one-shot reconcile、terminal exact cancel query、Slice 2/3不稳定checkpoint合并、direct Host caller lifecycle和fixture迁移清单均已达到code-generation-ready候选标准。

本轮`needs-fix`不是重新打开这些已闭合finding，而是re-review暴露了两个新的可执行性/correctness缺口。

## New finding adjudication

### PRR-001 — accepted — high — Host close在execution owner quiesce前释放mutex

- 来源：AgentMiMo `NEW-001`；总控基于代码与设计真源强化严重度和反例。
- 直接证据：
  - plan §5.4 当前顺序为actor/pre-start drain后先释放全部native mutex，再调用`scheduler.close()`。
  - 当前`HostDispatchScheduler.close()`入口才会把host instance标为`STOPPING`，随后`active_registry.cancel_all(...)`、取消active tasks、关闭worker handles/lane，最后best-effort标为`STOPPED`。
  - `docs/host/design.md` §27.1要求Host正常close先传播lifecycle cancel并关闭本地execution owner；fresh RW attach之后以`STOPPED` proof推进恢复。
  - fresh attachment的target recovery是attach-time one-shot；plan中的periodic owned-session reconciliation只处理queued/accepted promotion，不重新执行旧RUNNING Attempt的positive orphan recovery。
- 反例：A完成actor/pre-start drain后释放mutex、尚未进入`scheduler.close()`；B立即获得RW并执行target recovery，此时A host instance仍为RUNNING且active worker尚未收到lifecycle cancel，因此B正确地不把Attempt判为orphan。随后A scheduler才cancel并标STOPPED，但B的一次性recovery已结束，periodic promotion不会补做该recovery；Run可能一直停留到下一次detach/reattach，违反“正常close后fresh attach最终恢复”的design truth。
- Fix requirement：Host close专用顺序必须改为：关闭public/new-work gate → stop wait poller → durable actor drain → 等待全部attachment mutation/pre-start work lease收口但继续持有native mutex → 在mutex仍持有时完成scheduler lifecycle close（停止promotion/background supervisor、传播active worker lifecycle cancel、关闭本地worker/task/lane并完成host instance stopping/stopped收口）→ 最后释放native mutex/关闭attachment record → 其余owner close。单独attachment close仍保持existing stable Attempt继续、无需关闭scheduler的原语义。
- Required proof：确定性barrier测试在scheduler lifecycle close完成前尝试第二opener，必须只能得到RO；scheduler close完成且mutex释放后fresh RW attach必须在同一次target recovery中看到old owner已STOPPED并推进recoverable Attempt，不依赖第二次reattach。worker cancellation token与`LocalWorkerHandle.on_cancel(...)`必须在mutex释放前可观察。cleanup异常路径不得宣称mutex已安全释放而旧scheduler仍可运行本地worker/new work。

### PRR-002 — accepted — medium — reactive production call site被allowed scope遗漏

- 来源：AgentDS `RRN-02`；总控以直接调用点证据强化为plan fix。
- 直接证据：
  - plan要求`run_compaction_operation(...)`从旧`max_attempts`改为显式`first_attempt_number`/`max_attempt_number`，且reactive producer同步写入新的request operation id与frozen attempt budget。
  - production调用不仅位于`dayu/host/dispatch.py`，还位于`dayu/host/engine_ingest.py::_execute_reactive_compaction(...)`；后者当前传`max_attempts=attempts`。
  - plan §6与Slice 2 allowed production files没有`dayu/host/engine_ingest.py`；allowed tests/validation没有主要owner contract测试`tests/host/test_engine_ingest_mapping.py`，也未覆盖因required signature变化必须更新的`tests/host/test_compaction_cancellation_scope.py`。
- 影响：严格按allowed scope实施将只能越权修改、保留兼容默认值或让reactive路径/测试失效，均违反plan和项目约束。
- Fix requirement：把`dayu/host/engine_ingest.py`加入affected/allowed Slice 2范围，精确限定为reactive requested schema字段与`run_compaction_operation` required attempt-range机械适配：首次reactive operation传`first_attempt_number=1`、`max_attempt_number`取同一policy budget snapshot；不得改变reactive operation count、overflow/recovery状态机或扩展其它Engine ingest语义。把`tests/host/test_engine_ingest_mapping.py`与`tests/host/test_compaction_cancellation_scope.py`加入allowed tests和focused validation，更新所有required-signature call sites，并断言reactive新request shape与既有count/overflow/fallback语义不回归。

### MIMO-NEW-002 — rejected-with-reason

plan §5.5已经冻结one-shot的输入、typed输出、ACTIVE RW稳定快照、逐Session重新申请work lease、target-scoped queued promotion/accepted reconciliation、close race、production loop与deterministic tests。具体私有函数拆分属于implementation plan执行，不需要在总计划复制现有scheduler内部算法；没有证据表明implementation agent必须自行决定新业务语义。

### MIMO-NEW-003 — rejected-with-reason

plan已明确proactive部分只是Slice 2全集中的职责分组、不是额外allowed范围或独立handoff；重复列出同一文件用于展示同一slice内部owner分组不会扩scope。该项仅为可选排版偏好。

### DS-RRN-01 — evidence-invalid

reviewer只检查了`dayu/host/compaction_operation.py`中的Protocol声明。真实`LLMContextCompactor.run_prepared_compactor_proposal(...)`位于`dayu/host/llm_compaction.py`，调用`_run_agent_request(..., timeout_seconds=self._runner_spec.default_timeout_seconds)`；该helper在当前代码中明确执行`asyncio.wait_for(run_agent_and_wait(request), timeout=timeout_seconds)`，并在`TimeoutError`后传播cancellation token。plan的直接证据成立。本项不保留为缺证风险；“如发现其它pre-start provider绕过既有timeout则阻塞”继续作为合理实施守卫。

## Deferred / residual risk reconciliation

- MIMO-003继续deferred到Slice 2/3 implementation diff review；owner=`AgentMiMo / AgentDS`。
- Windows strict-native backend仍由Slice 1与Windows环境验证。
- Provider crash外部call非exactly-once、poll cadence和fresh schema边界维持原plan owner。
- Slice 2上下文规模是真实执行风险，但不能用可发布的错误checkpoint拆分；AgentCodex可在同一slice内部按依赖顺序实施和验证，accepted commit仍只能在联合completion signal通过后产生。

## Completion status

- Original accepted fix requirements：7/7 closed。
- New accepted findings：2。
- New rejected findings：2。
- Evidence-invalid findings：1。
- Blocking open questions：0。
- Plan re-review gate：`needs-fix`。
- Next gate：second targeted plan fix by AgentCodex，随后仅复核`PRR-001`与`PRR-002`并确认无新回归。
