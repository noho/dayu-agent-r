# WU-HOST-SESSION-EVENT-DELIVERY-01 Aggregate Deepreview Controller Adjudication

- 日期：2026-07-22
- gate：`aggregate-deepreview`
- base：`main` / `2c02079a82c049b49914be412178006ccd354049`
- reviewed HEAD：accepted Slice 4 commit `035d0035ddc7a707344ade7377009261ce753572`
- reviewers：AgentMiMo、AgentDS（独立并行）
- decision：`accepted-deepreview-ready-for-commit`

## 输入 artifacts

- AgentMiMo：`docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-mimo.md`
- AgentMiMo `$deepreview` artifact：`docs/reviews/code-review-20260722-034010.md`
- AgentDS：`docs/reviews/wu-host-session-event-delivery-01-aggregate-deepreview-ds.md`

两路均从 `main` 到 `035d0035` 独立审查完整四个 slices，没有读取对方 aggregate artifact。两路 verdict 都是 `PASS`、零 material finding；本裁决不以票数放行，而是按 acceptance、直接代码证据与验证矩阵逐项裁决。

## Acceptance adjudication

1. **Public async attach 与 successful-return boundary：PASS。** durable cursor transaction、reservation、mailbox attach 与 iterator构造都在 factory return 前完成；cancellation、Host close 与 partial allocation failure 在 owner边界释放 reservation，没有 pending attach 暴露给 caller。
2. **Host sole delivery owner 与 item-only bound：PASS。** `dayu.host.transient_delta` 唯一拥有fanout、每订阅mailbox、唯一in-flight retained count、overflow与admission；packaged policy为items=`512`、per-Session subscriptions=`4`，不存在byte/heap字段或Service第二relay。
3. **Typed error、metrics与确定性overflow：PASS。** admission和delivery interruption detail为typed public contract；metric/log维度来自closed low-cardinality enums，不含Session/Run/subscription/payload；accepted prefix先交付，耗尽后才抛typed overflow。
4. **Durable causal fence与ordering：PASS。** same-transaction terminal fence、bounded page catch-up、mailbox-empty periodic reconciliation、delayed cursor、双opener隔离barrier都有真实owner-path测试；不引入第三sequence domain或durable/transient全局总序。
5. **Local TerminalPostCommitPort与producer completeness：PASS。** exact-run-event projection helper是唯一真源；terminal producer manifest/runtime barriers完整；terminal producer没有直接promotion bypass，剩余五个`wake_queue_promotion`调用均属于coordinator或ordinary non-terminal路径；Engine没有delivery contract泄漏。
6. **Service exact-five与CLI/UI isolation：PASS。** Service只有一个consumer和capacity-one first-commit slot，disposition union保持exact-five，cleanup/primary error precedence冻结；callback通过显式execution port，CLI使用private single-worker executor，不阻塞Host/Agent/Engine；旧event-copy relay和task side channel删除。
7. **Config、assembly、callers与docs：PASS。** strict exact-field parser、one-to-one assembly、public exports与所有production/test/utils async callers一致；Host/Service/config/layering/tests README trigger已审计，根README没有用户安装/入口/workflow变化，故不机械修改。
8. **Validation：PASS。** 两路均报告affected suites `3443 passed, 9 skipped, 6 deselected`、stress `6 passed`、完整pyright `0 errors`、`git diff --check`通过；核心生产文件coverage为`transient_delta.py 92%`、`open_host.py 84%`、`terminal_post_commit.py 95%`、`entrypoint_runtime.py 86%`。

## Finding 与 observation adjudication

两路没有material finding，因此不进入AgentCodex fix/re-review loop。reviewers列出的observations逐项裁决如下：

1. `_close_from_hub()`不再从fanout单独detach：non-issue。caller `Hub.close()`已经先清空fanout字典，subscription只负责清理自身retained state与reservation；重复detach没有额外owner语义。
2. overflow路径直接设置readiness而非调用`_refresh_readiness()`：non-issue。overflow是level-triggered ready条件，直接`set()`与closed state组合保持同一不变量，测试覆盖prefix-drain后typed error。
3. iterator没有`__del__`异步cleanup：non-issue。public contract要求显式`aclose()`；Host close和`__anext__`异常路径负责owner cleanup，不能用不可await的析构器替代async lifecycle。
4. plan叙述中的`DETACHED`与实现直接从successful attach后的`ATTACHED_UNBOUND`开始：non-issue。reservation阶段属于factory内部，不对Service observation state暴露；successful return生效边界后直接进入attached状态与冻结contract一致。
5. health gate与hub closed双重检查：non-issue。Host close先`begin_closing()`再关闭hub；前者是public lifecycle linearization，后者是owner内部安全网，没有冲突状态或额外semantic owner。
6. 无byte/heap bound、无跨进程terminal broadcast、delta不持久化/重放/断线补放：均是用户确认的明确非目标或accepted design tradeoff，不是未归属residual risk，不创建后续WU或Issue。
7. 核心文件剩余未覆盖行：所有修改production单文件均达到`>=80%` gate，未覆盖集中在defensive/operator diagnostic分支；完整affected suites与owner contract测试已覆盖要求的状态机和failure paths，不构成当前finding。

## Gate decision

完整WU acceptance全部满足；此前accepted findings全部closed；零新material finding、零blocking open question、零未分类residual risk。允许Controller创建accepted deepreview commit。commit后的next gate为`ready-to-open-draft-PR`，按Gate Order自动执行push、创建draft PR与独立并行PR review；不得mark ready、merge、request reviewers或删除分支。
