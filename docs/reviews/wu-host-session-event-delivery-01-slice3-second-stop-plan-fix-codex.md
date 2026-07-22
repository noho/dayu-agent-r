# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Second Stop Plan Fix

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`plan-amendment-slice-3-r2`
- Base：accepted Slice 3 plan amendment commit `6c1cf62a`
- Second stop artifact：`docs/reviews/wu-host-session-event-delivery-01-slice3-second-stop-scope-codex.md`
- Controller adjudication：`docs/reviews/wu-host-session-event-delivery-01-slice3-second-stop-controller-adjudication.md`
- 修订对象：`docs/host/wu-host-session-event-delivery-01-plan.md` S3及其同一dual-opener验证文字
- 执行边界：只修订accepted plan并新增本artifact；不修改production、tests、control doc或phaseflow umbrella，不继续implementation，不commit、push或创建PR。

## 第一性原理与直接证据

动机成立。S3 focused gate已通过，完整Host affected suite只剩`tests/host/test_watch_session_events.py::test_dual_opener_b_fence_catches_up_pages_before_terminal_handoff`失败；直接失败断言是跨两个opener的class/global `local_hook_calls.call_count == 0`。

该断言只适合S2 local hook尚未接线的阶段。S3接线后，opener A提交terminal并推进A自己的local watermark/hook是合法且必需的；跨opener隔离真正需要证明的是opener C的local watermark/hook未被A推进、C watcher未被A的local action唤醒。全局计数器把A的合法本地动作与C的barrier混为一谈，因此问题owner是目标dual-opener test instrumentation，而不是production coordinator、mailbox或跨opener补偿。

## 精确修订

1. S3 Allowed tests只新增`tests/host/test_watch_session_events.py`。
2. 授权只覆盖`test_dual_opener_b_fence_catches_up_pages_before_terminal_handoff`的barrier instrumentation与对应局部断言：从全局hook总调用数切换为opener C局部watermark/hook与no-cross-opener wake观测。
3. opener A本地hook允许前进；A terminal action前后，必须直接证明C的local watermark/hook未被推进，C watcher保持pending，且C reconcile clock未推进时没有page read或其它wake。
4. S2 durable DB/fence correctness与其它业务断言保持不变，包括共享Host DB/lane DB、multi-page catch-up、B fence、A terminal先于B、page/timeout/retained-items与cleanup语义。
5. S3 validation补齐目标case、`tests/host/test_watch_session_events.py`完整文件、`tests/host -q` affected suite、完整pyright、`git diff --check`以及constructor/source/scope scans无新缺口。

## 冻结边界

- 不授权任何production修改、fallback、默认值、兼容分支、跨opener广播或补偿逻辑。
- 不授权修改其它test、fixture/support file、control doc、phaseflow umbrella、README、design或既有review artifact。
- 不授权削弱或改写S2 durable DB/fence、multi-page、ordering、retention、timeout或cleanup correctness。
- partial S3 workspace changes及既存Controller-owned修改全部保留，不撤销、不格式化、不stage、不提交。

## 验证合同

恢复同一个S3 implementation后必须执行：

```bash
source .venv/bin/activate
pytest tests/host/test_watch_session_events.py::test_dual_opener_b_fence_catches_up_pages_before_terminal_handoff -q
pytest tests/host/test_watch_session_events.py -q
pytest tests/host -q
pyright
git diff --check
```

同时继续执行accepted plan §8.4的constructor/source/boundary scans与最终scope审计。扫描必须确认没有新增production caller、terminal producer、fixture/support file或第三个scope缺口；目标test diff只能包含C-side barrier instrumentation与对应局部断言，原S2业务断言不得减少。

本次plan amendment不修改代码，因此不提前运行implementation tests或pyright；当前gate只完成plan/artifact的diff、whitespace与scope审计。

## 本轮文档验证结果

- `git diff --check`：通过，无whitespace error。
- 新增artifact相对`/dev/null`的no-index diff check无whitespace diagnostic；两份目标文档也无行尾空白或冲突标记。
- `tests/host/test_watch_session_events.py`与`docs/phaseflow-umbrella-optimization-control.md`相对index均为零diff；production、tests、control doc及既存dirty baseline未被本轮写入。
- 本轮新增scope只有accepted plan修改与本artifact；constructor/source/scope要求已写入恢复implementation后的硬gate，未增加production、其它test、fixture/support file、README、design、control或umbrella授权。

## 结论

最小测试owner与验证边界已按second stop Controller adjudication写回plan，无blocking open question。完成文档diff check与scope scan后交回AgentMiMo、AgentDS独立`$planreview`及Controller逐项裁决；此前不得恢复implementation。

READY_FOR_PLAN_REVIEW
