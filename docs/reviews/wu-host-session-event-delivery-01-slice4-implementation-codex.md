# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 4 Implementation

- 角色：AgentCodex implementation
- gate：`implementation-slice-4`
- accepted base：`24efe9bd`
- 结论：`READY_FOR_CODE_REVIEW`

## 动机与语义 owner 核对

问题真实存在：accepted base 中 Service 仍把 Host public iterator 复制到自身 relay queue，并通过 drain task/异常 side channel 决定 terminal fallback；CLI 同步 renderer callback 又运行在事件循环线程。前者形成第二个投递 owner，后者会让慢 UI callback 阻塞 Service consumer。按照冻结设计，Host 继续拥有 subscription mailbox 与 typed delivery error，Service 只拥有单 consumer 的 terminal observation disposition，CLI 只拥有 renderer execution domain 与生命周期。

实现未恢复 relay、drop queue、第二 observation channel、default executor、byte/global quota或 Engine public contract，也未实施 R2 smoke、CLI 参数或 terminal 格式变更。

## 实现结果

### Service observation owner

- `dayu/service/entrypoint_runtime.py` 删除 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、Service event-copy queue、drain task、queue item/failure union、drain helper、task-exception side channel、private closable protocol与 cast。
- 每个 watch runtime 只保留一个 public `HostSessionEventIterator`、一个 sole-consumer task 和一个 capacity-one generation slot。封闭联合恰好为 `TARGET_TERMINAL`、`DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED`。
- submit 固定为 attach/consumer UNBOUND → submit → accepted id bind → `on_run_accepted`；cancel 固定为 initial durable probe，非终态时 attach/bind 后 cancel；startup 固定为 watcher-first，target terminal commit 后 consumer 暂停，由 coordinator 仅 ack `TARGET_TERMINAL` 并 rebind 下一 generation。
- stop 在空 slot 上取得仲裁后拒绝 late commit；fatal member sticky；terminal identity 统一按 `terminal_event_id` 与 dedupe identity 处理，live/Outbox 共用同一 seen terminal id 真源。
- 只有 typed `DELIVERY_INTERRUPTED/TRANSIENT_MAILBOX_OVERFLOW` 进入一次 durable recovery；其它 EOF、public/non-public iterator failure与 callback failure按 exact-five 唯一 disposition 传播。terminal/recovery success 不被 iterator close failure覆盖，cleanup diagnostic 使用固定去敏字段且 callback failure被吞掉。
- cleanup 固定先 stop/await consumer、确认无 active `anext()`，再恰好一次 public `aclose()`；callback、EOF、iterator、delivery recovery、slot-empty、caller cancellation及 consumer construction failure的 primary/cause 链均由 owner tests 冻结。
- `EntrypointCallbackExecutionPort` 只含 typed async activity/thinking invocation；存在 callback 时 required，无 callback 时必须为空。Service 为当前 callback job 建 task、shield 并等待真实结束，consumer 在此前不读取下一项；callback/scheduling failure进入 `CALLBACK_FAILED` 并保留原异常。

### CLI execution-domain owner

- `dayu/cli/runtime_display.py` 的每个 controller 实例拥有私有 `ThreadPoolExecutor(max_workers=1)` 与 event-loop async serial gate；activity/thinking callback、guard、toggle、finish、cancel/local-exit、interactive terminal renderer和最终 renderer close均通过显式 executor 串行执行。
- execution domain 不使用或替换 default executor，不跨 lifecycle/Session 共享，不保存 Host event/Service outcome，也不建立 queue、Future或 observation side channel。
- `dayu/cli/session_execution.py` 是 controller/executor 唯一 production lifecycle owner。prompt 与 interactive 在 callback consumer 存在时于 Host attach 前构造 execution domain；无 callback consumer 时不构造。
- close 顺序固定为 event-loop mark closing → cancel/await Service task及当前 shielded callback → 同 executor renderer close → executor shutdown → monitor/SIGINT/task 等 caller-local release。renderer/executor实际关闭恰好一次；已有 primary保持 identity，cleanup failure按发生顺序追加为 cause。
- `dayu/cli/activity.py` 与 `dayu/cli/run_view.py` 只把原 toggle 入口统一为 typed `toggle_runtime_display()`，未复制 Host/Service observation 状态；`dayu/cli/thinking.py` 无需修改。

### Tests 与真实跨层回归

- Service fake 全部使用 async watcher factory、public iterator、typed callback port与 event/barrier；无 unbounded queue、default executor或 task-exception读取。
- owner tests覆盖 attach/submit/cancel/startup时序、callback scheduling/阻塞、exact-five、fatal sticky、only-target ack、old-generation五类 late commit、stop arbitration、seen terminal identity、全部列明的 failure/close chain，以及 consumer construction双故障。
- startup A/B probe 在每次 Session read 前记录 iterator progress 为 `[0, 1, 2]`，直接证明 A ack/rebind B 之前没有预读 B。
- `tests/cli/test_transient_slow_consumer_path.py` 已删除；新增 `tests/cli/test_transient_delivery_interruption_path.py` 使用真实 Host、两个 subscription、queued Run promotion、Service sole consumer与 CLI blocking renderer。阻塞期间 Host terminal commit、第二 Run promotion及独立 watcher继续；释放后原 typed overflow identity触发恰好一次 durable recovery，CLI terminal恰好展示一次。
- CLI tests覆盖 execution-domain construction failure先于 Host attach、同一 worker串行、blocking close barrier、terminal renderer、close/shutdown identity与 `callback_started -> close_requested -> callback_released -> callback_finished -> renderer close -> executor shutdown -> caller-local release`。

## README 审计

- 更新 `dayu/service/README.md`：sole consumer、capacity-one exact-five、delivery-only durable recovery与 typed callback execution port。
- 更新 `dayu/README.md`：`UI -> Service -> Host` 消费边界、无 Service relay、CLI 私有 execution domain。
- 更新 `tests/README.md`：S4 focused 命令、exact failure matrix、真实 interruption E2E与 CLI close ordering。
- `dayu/host/README.md` 与 `dayu/config/README.md` 在 accepted base 已准确记录 item-bound/per-Session contract、packaged `512/4`、无 logical-byte/resident-heap 承诺及双字段 config schema；按各自更新约束审计后不做机械修改。
- 根 `README.md` 已审计：CLI 参数、用户步骤、terminal 格式和最终工作流均未变化，因此未触发修改。`dayu/engine/README.md` 不触发。

## 验证

- S4 focused：`193 passed`。
- affected suites：`pytest tests/host tests/runtime tests/service tests/cli -q` → `3440 passed, 9 skipped, 6 deselected`。
- Host production stress：`5 passed`。
- transient delivery stress：`1 passed`。
- modified production 单文件 coverage：
  - `dayu.service.entrypoint_runtime`：`86.36%`，显式 `--cov-fail-under=80`；
  - `dayu.cli.session_execution`：`80.23%`；
  - `dayu.cli.runtime_display`：`92.86%`；
  - `dayu.cli.activity`：`91.30%`；
  - `dayu.cli.run_view`：`95.38%`。
- 完整 `pyright`：`0 errors, 0 warnings, 0 informations`。
- 四个 public smoke helper `py_compile`：通过。
- `git diff --check`：通过。
- 旧 delivery 语义 scan：空。
- relay/queue/default-executor/task-exception/extra Future side-channel scan：空。
- `TerminalPostCommit|session_event_delivery` in `dayu/engine`：空。
- `dayu.runtime` 反向 import：无真实 import；raw scan 唯一命中是包文档中的禁止说明。
- watcher callsite、terminal promotion、constructor/source propagation与 boundary：AST/完整回归通过；调用点为显式 await 或专门验证 cancellation/admission failure 的受控 coroutine。
- root README diff：空；Host/config README diff：空。

## Scope 与风险

- S4 修改只落在 accepted production/test/README allowlist与本 implementation artifact。`docs/host/issues-implementation-control.md` 是 Controller-owned 的既有 dirty change，实施期间未写入。
- 未 commit、未 push、未创建 PR。
- 当前无已知未覆盖项或 residual risk；现存 edgartools deprecation warnings 与本 WU 无关，不影响 gate。
