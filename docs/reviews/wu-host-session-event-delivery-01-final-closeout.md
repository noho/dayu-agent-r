# WU-HOST-SESSION-EVENT-DELIVERY-01 Final Closeout

- 日期：2026-07-22
- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01` Host Session Event Delivery Ownership and Bounded Mailbox
- 类型：architecture-sensitive public contract / ownership correction
- branch：`phaseflow/wu-host-session-event-delivery-01`
- Draft PR：`https://github.com/noho/dayu-agent-r/pull/181`
- final decision：`final-closeout-pass`

## What changed

1. Host public `watch_session_events(...)` factory改为async attach；successful return才表示cursor transaction、per-Session reservation、subscription mailbox、fanout registration与可关闭iterator全部生效。
2. Host成为Session Event Delivery唯一owner。每订阅只有一个items-only mailbox和一个counted in-flight引用；两者合计retained items。packaged defaults为`transient_mailbox_max_items=512`、`max_subscriptions_per_session=4`。
3. admission与overflow使用typed public errors；low-cardinality metrics/log dimensions不包含Session/Run/subscription/payload/capacity identity；accepted prefix先交付，耗尽后才报告overflow。
4. durable causal fence、bounded single-page catch-up、mailbox-empty periodic reconciliation和双opener deterministic ordering barriers落在Host owner boundary；不增加第三sequence domain。
5. 新增local-only `TerminalPostCommitPort`和exact-run-event projection helper，完整接线terminal producers；promotion side effect只由opener-local coordinator执行，Engine不拥有delivery contract。
6. 删除Service event-copy relay。Service使用sole consumer、capacity-one first-commit slot与冻结的exact-five observation/cleanup contract；delivery interruption只走一次durable recovery。
7. CLI callback/rendering通过显式execution port在每个caller lifecycle的private single-worker executor中串行执行，慢UI不阻塞Host/Agent/Engine；prompt/interactive cancel与terminal identity/cleanup语义保持。
8. strict runtime config、Host assembly、public exports、CLI/Service/utils callers、tests、stress、coverage与README trigger audit全部同步。

## Explicit boundaries

- 不提供logical-byte、Python resident-heap或Host-global跨Session总内存上界。
- 不持久化、重放或断线补放delta。
- 不建立第三sequence domain或durable/transient全局总序。
- 不实现跨进程terminal broadcast。
- 不让慢UI/Service暂停Agent或Engine。
- 不实施`WU-CLI-SMOKE-01-R2`。
- 不创建GitHub Issue；本WU owner/destination来自用户明确裁决。

## Accepted commits

- accepted plan：`8b29462c`
- accepted plan amendment：`33af05fa`
- accepted Slice 1：`64383186`
- accepted Slice 2：`5ac328f0`
- accepted Slice 3 plan amendments：`6c1cf62a`、`b33bb80b`
- accepted Slice 3：`24efe9bd`
- accepted Slice 4：`035d0035`
- accepted aggregate deepreview：`0a72396d`
- aggregate bookkeeping：`6e20767d`
- accepted PR review：`3439a1a1`

## Review and finding status

- plan review与plan re-review：AgentMiMo、AgentDS独立完成；所有accepted findings closed。
- 每个implementation slice均经过独立双路code review；所有accepted findings由AgentCodex修复并由原reviewers re-review关闭。
- Slice 4最终状态：`S4-CR-F01/F02/F05` closed；`S4-CR-F03/F04`按Controller直接代码证据拒绝且边界保持。
- aggregate deepreview：AgentMiMo与AgentDS均PASS，0 material finding。
- PR #181 review：AgentMiMo与AgentDS均PASS，0 material finding；Controller adjudication为`docs/reviews/wu-host-session-event-delivery-01-pr-181-review-controller-adjudication.md`。
- 当前无unclassified residual risk、blocking open question或需要新Issue的finding。

## Validation

- affected suites：`3443 passed, 9 skipped, 6 deselected`。
- stress：`6 passed`。
- 完整pyright：`0 errors, 0 warnings`。
- 单文件coverage：`transient_delta.py 92%`、`open_host.py 84%`、`terminal_post_commit.py 95%`、`entrypoint_runtime.py 86%`；Slice 4另验证`session_execution.py 80.56%`。
- `git diff --check`：通过。
- stale delivery、Service relay/side-channel、promotion bypass、Engine boundary与runtime reverse-dependency scans：通过。
- Draft PR #181 accepted PR review HEAD `3439a1a1`的GitHub checks：
  - `windows-upload-script`：PASS，3m41s。
  - `windows-init-transaction`：PASS，4m18s。

## Docs decision

已按README trigger更新：

- `dayu/host/README.md`
- `dayu/service/README.md`
- `dayu/config/README.md`
- `dayu/README.md`
- `tests/README.md`

根`README.md`不修改：本WU没有用户安装、CLI参数、默认命令、工作区路径或最终用户workflow变化。`docs/phaseflow-umbrella-optimization-control.md`未修改。

## GitHub bookkeeping

- Draft PR #181保持OPEN/DRAFT，base=`main`，head=`phaseflow/wu-host-session-event-delivery-01`。
- PR body不含Issue closing directive；没有关联或创建GitHub Issue。
- 未发布GitHub review/comment，未request reviewers，未mark ready，未merge，未删除分支。

## Remaining risks / owners

没有未分类产品risk。以下均为用户确认的设计tradeoff而非residual work item：无byte/heap bound、无cross-process terminal broadcast、delta不持久化/重放/补放、无Host-global跨Sessionquota。它们不自动创建后续WU或Issue。

## Next entry point

等待用户或maintainer手工处理Draft PR #181。不得由Phaseflow Controller擅自mark ready或merge。PR合并后，应从最新`github/main`重新preflight，再由用户或主总控选择下一Work Unit；`WU-CLI-SMOKE-01-R2`不会因本closeout自动启动。
