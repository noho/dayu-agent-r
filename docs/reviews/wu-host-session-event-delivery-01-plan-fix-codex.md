# WU-HOST-SESSION-EVENT-DELIVERY-01 Plan Finding Fix — AgentCodex

## 1. 状态与范围

- target：`docs/host/wu-host-session-event-delivery-01-plan.md`
- source adjudication：`docs/reviews/wu-host-session-event-delivery-01-plan-review-controller-adjudication.md`
- status：`completed`
- scope：只落实 Controller 裁决为 `accepted`、`accepted-in-narrowed-form`、`accepted-as-clarification` 或合并接受的 plan findings；不实施代码，不修改 design/control/goal confirmation/原 review/Controller adjudication/测试/README。
- blocking issues：无；修订后的 plan 需由原 AgentMiMo 与 AgentDS 独立 re-review。

动机核对结论：findings 成立。直接代码证据显示，Service 的 async watch 调用点与旧 relay symbols 位于同一文件；scheduler 当前在 `open()` 返回前启动 heartbeat/watchdog；`dayu.runtime.lane` 使用事件循环默认 executor；CLI renderer 的 callback 与 caller-finally close 当前没有独立串行执行域。这些事实要求在语义 owner 与 slice boundary 收紧 plan，不能由兼容分支、下游 fallback 或测试夹具补偿。

## 2. Accepted finding 修复映射

| Finding | 修改位置 | 修改摘要 |
|---|---|---|
| MIMO-001 | plan §7 S1 Allowed modules、Exact changes、Non-goals | 将 `entrypoint_runtime.py` 的 S1 权限冻结为 async factory/public iterator 机械传播；明确允许的 async/`await`、public iterator type propagation，并逐名冻结 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`_WatcherFailure`、`_WatcherQueueItem`、`_WatchAndWaitRuntime.queue/drain_task`、`_drain_host_events`、`_close_watch_and_wait_runtime` 及两个 queue-drain consumer。旧 relay 只可在 S4 删除/重写，S1 tests 不固化 relay 行为。 |
| MIMO-002 + DS-F2 | plan §4.6 lifecycle；§7 S3 Exact changes、Failure paths、Tests；§10.1 | 冻结 inert scheduler -> typed factory/coordinator -> construction-only one-shot bind -> critical tasks start 的顺序；bind/factory failure 时 critical tasks 从未启动并逆序关闭资源。Host close 先 stop/await wait-poller、actor intake及全部 scheduler-owned producers，再 drain/close coordinator/port，最后 close delivery owner。定义已进入 owner loop、closing race、close 后 notice 的完成/固定低基数 diagnostic 语义与 deterministic barriers；禁止临时 port、public setter或 runtime rebind。 |
| MIMO-003（narrowed） | plan §3.1、§4.1、§4.7；§7 S4 Exact changes、Failure/tests、Non-goals；§10.1 | 用 Service-defined typed callback execution port + CLI-owned private single-thread executor取代共享默认 executor。每个 display lifecycle 独立创建，async serial gate在提交前取得，同一 consumer 至多一个 submitted/in-flight callback；不建 Host event-copy queue、第二 observation channel、executor registry或跨 Session quota。写清创建失败、callback/scheduling异常、renderer close与executor shutdown边界。 |
| DS-F1 | plan §4.5；§7 S2 Exact changes、Failure paths、Tests | periodic reconcile 只由 sole iterator 当前 `__anext__()` readiness wait 的 timeout 分支驱动；每个 timeout 最多处理一页后重新等待。interval 为 Host-internal bounded constant，不进入 public policy、不复用 wait-resolution cadence；无 per-watcher timer/background task。测试使用可控clock/readiness barrier，并证明 Host close立即打断等待。 |
| DS-F4 | plan §7 S2 Allowed tests、Tests、Stop conditions | 删除未限定 support-file 范围，只允许在 `tests/host/test_watch_session_events.py` 内直接构造两个独立 `open_host` contexts；二者仅共享Host DB/lane DB paths，各自拥有scheduler、actor/store、delivery owner、worker和lifecycle。写清 no-local-notice barrier、逐页clock推进与 watcher C -> opener C -> opener A 的关闭顺序；如必须修改其它fixture，立即回plan gate。 |
| DS-F5 | plan §7 S4 Exact changes、Failure/tests | `dayu.cli.session_execution` 成为controller/executor/renderer唯一 lifecycle owner；唯一 caller `finally` 顺序固定为 stop new display work -> await current job -> 同一专用executor串行close renderer并await -> shutdown executor -> 回event loop释放caller-local resources。无primary时close error原样传播，有primary时保持primary identity并以close error为cause；增加精确ordering与exact-once测试。 |
| DS-F6 | plan §3.3、§4.7；§7 S4 Tests/Non-goals | 明确 no-backpressure 只承诺 Host publisher、Agent/Engine、terminal commit、promotion和其它watcher不等待当前Service callback。慢callback可以减速当前consumer并使当前subscription按item cap overflow；不增加relay/drop queue、byte quota、Host-global/cross-Session quota。 |
| DS-O1 | plan §5.3；§7 S3 Exact changes、Tests | 明确static manifest覆盖producer qualified callsites，与完整opener、wait-poller或standalone composition无关。standalone `create_host_command_handle` 显式注入private no-local-delivery port，producer仍必须调用；recording runtime fake证明exact notice dataflow。该port不public export、不兼容转发、不承担跨opener correctness，也不是完整opener的构造期临时port。 |

## 3. Rejected finding 边界

- DS-F3 未实施：没有加入“等待到期后继续cleanup”的机制。Python thread job不能安全取消；让仍运行的callback晚于iterator/controller close会破坏串行lifecycle与late-commit safety，也不会回收executor容量。plan保留快速、同步、非阻塞callback contract，并要求可释放blocking barrier证明隔离；barrier释放后严格完成callback、consumer、iterator、renderer与caller cleanup。
- DS-O2 未实施：未扩展宽泛 source scan。现有精确旧语义scan已经覆盖本 WU 的 stale owner；扩大组合扫描会误报真实availability owner并扩大无关范围。
- reviewer artifact 的 DS-F3 严重度计数不一致未修改：该问题只由 Controller normalization 解释，不属于本次允许修改范围；两份原 review 保持原样。

## 4. Validation

- `git diff --check`：通过，exit 0，无输出。
- plan pre-fix vs post-fix no-index diff：已检查；`57 insertions(+), 29 deletions(-)`，只包含accepted finding对应章节，§8.4既有精确source scans无变更。
- plan/fix artifact no-index whitespace check：通过；两个`git diff --no-index --check`均无check输出，exit 1仅表示比较对象存在预期差异。artifact为新增46行。
- rejected-boundary scans：通过；callback shared-default-executor方案、callback限时后遗留线程方案、旧模糊dual-opener support范围三个定向`rg`均无匹配。DS-O2的宽泛source scan未加入。
- `git status --short` scope audit：通过。相较开始时的既有status，只新增本artifact；既有`design.md`、control、goal confirmation、两份原review与Controller adjudication状态不变，plan仍是唯一被本次修改的既有目标文件。
- 测试/pyright：未运行；本次只修改 plan/review artifact，且用户明确禁止 implementation、测试与配置修改。

## 5. Changed files

- 修改：`docs/host/wu-host-session-event-delivery-01-plan.md`
- 新增：`docs/reviews/wu-host-session-event-delivery-01-plan-fix-codex.md`

除以上两项外，本次未修改其它文件；工作树中原有 design/control/goal confirmation/review 等变更均保留且未触碰。
