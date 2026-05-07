# Conversation Memory 多轮财报分析实测 Prompt 集

## 目标

本文档用于在 Conversation Memory / RunInputBuilder、context overflow compaction、persistent projection、
audit / trace 等能力全部落地后，做真实财报对话语义实测。它不是 P3 当前代码验收，也不要求当前阶段立即跑通。

测试目标是验证 `docs/host/design.md` 第 12 节的记忆子系统语义：

1. `USER_INPUT_ACCEPTED` 是用户输入 canonical 真源。
2. `TaskFrame` / `pinned_state` 能保持公司、期间、口径、单位、比较基准和用户约束不漂移。
3. `MemoryClaim` / `ClaimStatus` 能区分 verified fact、assistant conclusion、assumption、superseded / rejected / stale。
4. `EvidenceAnchor` 能让财报数字、页码、XBRL fact、工具 chunk 或 quote hash 可追溯，且不被自然语言 summary 替代。
5. 最近 N 轮 raw turn 是语义保底，不是“最多 N 轮”，也不是超大旧轮全文无限保底。
6. compaction / episode summary 后，verified claim、assumption、evidence anchors 和 supersession 关系不丢失。
7. reasoning / preview / delta / display timeline 不回流 RunInputBuilder 或 memory projection。
8. `RunInputBuildTrace` 能解释本轮纳入和排除了哪些 memory、原因、来源和预算。

## 启动方式

具体命令以最终落地后的 CLI / Service 入口为准。若仍使用 interactive 入口，可参考：

```bash
source .venv/bin/activate
python -m dayu.cli interactive --scene interactive
```

每组测试结束后，应结合以下信息交叉确认：

- RunEvent / EventLog 中的 `USER_INPUT_ACCEPTED`、tool facts、final answer、terminal event。
- Conversation Memory projection / snapshot。
- `RunInputBuildTrace`。
- tool trace / audit projection。
- compaction / episode summary 日志和 projection。

不要只看模型回答是否“看起来对”；必须核对回答背后的 claim status 和 evidence anchors。

---

## 测试组 A：TaskFrame / pinned_state 演进与抗漂移

**目的**：确认当前公司、期间、报告类型、口径、单位和用户约束稳定保留；公司切换和回切时不混淆。

观察项：

- 每轮用户输入是否写入 `USER_INPUT_ACCEPTED`，并按 session turn 顺序可追溯。
- `TaskFrame` 是否记录当前公司、报告期、报告类型、单位、口径和比较基准。
- 第 6 轮切换公司后，五粮液的 task frame 是否与茅台历史 claim 分离。
- 第 7 轮回到茅台时，回答是否引用此前茅台相关 verified claim / evidence anchor，而不是重新猜测。

```text
1. 我想看看贵州茅台 2024 年半年报的营收增长结构。
2. 用百万元口径展示，按产品系列拆分。
3. 茅台酒和系列酒分别同比增长多少？
4. 毛利率有变化吗？
5. 把刚才提到的产品系列对应的销量也一起列出来。
6. 切换到五粮液 2024 半年报，做同样口径的产品系列拆分。
7. 回到茅台，刚才你给的茅台酒和系列酒同比增速我再确认一遍。
```

**预期**：

- 第 7 轮能回到茅台 task frame，且数值、期间、单位与第 3 轮一致。
- 茅台相关 `MemoryClaim(status=verified)` 保留原 evidence anchors。
- 五粮液相关 claim 不覆盖茅台 claim；如存在同名指标，也应通过 task frame / subject ref 区分。
- assistant final answer 不自动变 verified claim；verified claim 必须来自 tool fact、evidence-backed projection 或用户确认。

---

## 测试组 B：追问连续性与 USER_INPUT_ACCEPTED 真源

**目的**：验证代词追问依赖 canonical user turn 与 recent semantic floor，而不是 display transcript 或 preview delta。

观察项：

- 第 3、5 轮的“这个数”“这部分支出”是否解析到正确的上文。
- RunInputBuilder 是否从 canonical `USER_INPUT_ACCEPTED` 和 memory projection 构造输入。
- `RunInputBuildTrace` 是否说明 recent raw turns / evidence anchors 被纳入的原因。

```text
1. 拉一下宁德时代 2024 年报里现金流量表的关键数据。
2. 经营性现金流净额是多少？
3. 这个数和净利润比，差异在哪个项目最大？
4. 投资活动的支出主要花在什么上？
5. 那这部分支出和扩产计划匹配吗？
6. 如果按 IFRS 口径重看一次，关键数据有差别吗？
```

**预期**：

- 第 3、5 轮代词解析无错。
- 第 6 轮新增或更新 task frame / user constraints 中的 IFRS 口径，但不删除原口径 claim。
- 如果 IFRS 口径需要重新查工具，系统可以重新调用工具；不能把旧口径 claim 直接当作 IFRS verified claim。
- `RunInputBuildTrace` 能指出哪些 user turn、tool facts、claims 和 anchors 被纳入。

---

## 测试组 C：超大单轮输入的语义保底

**目的**：验证 recent floor 是语义保底，不是超大旧轮全文无限保底。超大轮次应降级为 user intent、assistant final 摘要和 evidence anchors。

观察项：

- 第 2 轮粘贴 8000-15000 字披露文本后，第 3 轮“第二个因素”能正确指代。
- RunInputBuilder 不应把第 2 轮全文无条件塞入下一轮。
- `RunInputBuildTrace` 应记录 oversized raw turn 被降级的原因和保留形式。

```text
1. 我准备分析比亚迪 2024 半年报的毛利率结构变化。
2. （粘贴一份 8000-15000 字的官方披露原文片段，比如 MD&A 中关于毛利率影响因素的整段描述）
   基于以上原文，给我提炼影响毛利率的三个最重要因素，按重要性排序。
3. 第二个因素能再展开讲讲吗？
4. 这三个因素和你之前给我的拆分口径一致吗？
5. 把这次讨论的毛利率结论和测试组 A 里茅台的毛利率对比一下。
```

**预期**：

- 第 3 轮能正确展开“第二个因素”。
- 第 2 轮超大 raw turn 在 trace 中被标记为降级，而不是全文保留。
- 被保留的 evidence anchors 能追到原始披露片段或工具 chunk。
- 第 5 轮跨公司对比时，两个公司的 task frame、claims 和 anchors 分离，不把口径混在一起。

---

## 测试组 D：compaction 后 verified claim 与 EvidenceAnchor 不漂移

**目的**：验证 compaction / episode summary 后，已验证事实仍通过 `MemoryClaim(status=verified)` 和 `EvidenceAnchor` 保留，而不是只靠自然语言 summary。

观察项：

- compaction 前后，关键财务数据的 claim id / anchor id / source event cursor 是否仍可追溯。
- 第 12 轮再问“刚才确认过的数据”时，系统应优先使用 existing verified claim + evidence anchor。
- 如果 claim stale、缺 evidence 或 scope 不匹配，允许重新调用工具；但必须能在 trace 中解释原因。

```text
1. 帮我看看招商银行 2024 半年报的息差数据。
2. 净息差是多少？
3. 同比变化幅度多少？
4. 生息资产收益率分项给我列一下。
5. 计息负债成本率呢？
6. 资产端的零售贷款占比变化怎么样？
7. 负债端定期存款占比呢？
8. 把这些数据按“资产 / 负债 / 息差”分三组重新组织一下。
9. 哪一组对净息差下行贡献最大？
10. 给个一句话结论。
11. 我换个问题：招行的不良率怎么样？
12. 回到刚才息差讨论，净息差的具体数值再确认一次。
13. 这次确认的数和第 2 轮一致吗？
```

**预期**：

- compaction 发生后，净息差相关 verified claim 和 evidence anchor 仍存在。
- 第 12 轮如果已有足够 verified claim，应基于 claim + anchor 回答；如果重新查工具，必须说明是因为 claim stale、evidence 不足或 scope 变化。
- 第 13 轮数值、期间、单位、口径与第 2 轮一致；若发生 supersession，应明确旧 claim 被哪个新 claim 覆盖。

---

## 测试组 E：纠错、supersession 与 assumption register

**目的**：验证用户纠错和临时假设不会只追加为自然语言历史，而是进入 claim correction / assumption / supersession 结构。

观察项：

- 用户提出假设时，系统应进入 `AssumptionRegister`，不是 verified claim。
- 用户纠错时，旧 claim 应变成 `superseded` / `rejected`，新 claim 保留来源。
- 后续追问不能继续使用被覆盖的旧 claim。

```text
1. 我们先看美的集团 2024 半年报的海外收入占比。
2. 假设海外业务毛利率比国内高 3 个百分点，后面估值时先用这个假设。
3. 基于这个假设，海外收入增长对整体毛利率有多大影响？
4. 等一下，把刚才的假设改成高 1.5 个百分点。
5. 重新算一遍影响。
6. 现在回顾一下，我们还保留了哪些未验证假设？
```

**预期**：

- 第 2 轮假设进入 assumption register，状态不是 verified。
- 第 4 轮产生 correction / supersession，旧假设不再作为有效假设使用。
- 第 6 轮只列出当前有效假设，不列已 superseded 的旧假设，除非作为历史说明。

---

## 测试组 F：reasoning / preview / display transcript 防污染

**目的**：验证展示态内容不会回流运行态。

观察项：

- reasoning / preview delta 可以出现在 display timeline 或 debug 视图，但不能进入 RunInputBuilder、memory pool、claim ledger 或 compaction 输入。
- final answer 只能作为 assistant conclusion / raw turn，不能自动升级为 verified claim。

```text
1. 分析一下海天味业 2024 年报里酱油业务收入变化。
2. 你刚才推理里提到“可能是渠道库存影响”，这个能作为结论吗？
3. 请只基于财报披露和工具证据，把已确认事实和待验证假设分开列出来。
```

**预期**：

- 第 2 轮不能把 reasoning 中的“可能是渠道库存影响”当 verified fact。
- 第 3 轮输出应区分 verified claims 与 assumptions。
- `RunInputBuildTrace` 证明 reasoning / preview 未进入运行态输入。

---

## 测试组 G：长会话稳定性（连续 20+ 轮）

**目的**：观察长会话中 task frame、claim ledger、evidence anchors、assumption register 和 memory budget 是否稳定。

操作：选定一家公司（推荐美的集团 000333.SZ 或宁德时代 300750.SZ），围绕其 2024 半年报，按“营收 → 毛利 → 费用 → 利润 → 资产 → 负债 → 现金流 → 估值 → 同行对比”的展开顺序，每个主题问 2-3 个具体问题。目标 25-30 轮。

观察项：

- compaction / episode summary 数量增长后，verified claims 不丢 source cursor / anchor。
- task frame 中公司、期间、单位、口径不漂移。
- assumptions 不与 verified claims 混同。
- memory budget 不持续扩大到挤占当前财报材料窗口。
- `RunInputBuildTrace` 能解释每轮 memory 裁剪。

**预期**：

- 第 25 轮提问“我们这次对话定下了哪些口径约束和未验证假设？”时，系统能完整列出当前有效约束和 assumptions。
- 对已 verified 的关键数值，回答能引用 evidence anchors。
- 对被 superseded / rejected 的 claim，不再作为当前事实使用。

---

## 验证清单

每组测试结束后核对：

- [ ] 每个用户 turn 都有 `USER_INPUT_ACCEPTED` canonical event，且 RunInputBuilder / timeline / memory projection 读取同一 event cursor。
- [ ] `RunInputBuildTrace` 存在，能列出 included / excluded facts、source event cursor、claim id、anchor id、裁剪原因和估算 size。
- [ ] verified claim 只来自 tool fact、evidence-backed projection、用户确认或受控 compaction；assistant final answer 没有自动升级。
- [ ] evidence anchors 没有被自然语言 summary 替代；关键财报数字能追到 source ref / tool call / event cursor。
- [ ] reasoning / preview / delta 没有进入 RunInput、memory pool、verified claim ledger 或 compaction 输入。
- [ ] 不同 session 的 memory 不互相串读。
- [ ] recent floor 在预算充足时不是上限；在超大旧轮时不是全文无限保底。
- [ ] compaction 后 claim status、supersession、assumptions、evidence anchors 不丢失。
- [ ] 对 stale / rejected / superseded claim，系统不会无提示继续使用。

## 调参信号判读

实测中如果观察到以下现象，对应调整方向：

| 现象 | 判断与调整 |
|---|---|
| 追问频繁忘上一轮 | 先看 `RunInputBuildTrace` 是否纳入 recent semantic floor；若未纳入，修 RunInputBuilder；若已纳入但仍失败，再小步上调 memory cap 或 recent floor |
| 当前问题被旧内容淹没 | 降低 memory cap 或提前 compaction；确认旧轮超大 raw turn 是否已降级 |
| 财报数字跨轮不一致 | 先查 claim status 与 evidence anchor，不先调 budget；确认是否误把 assistant conclusion 当 verified claim |
| compaction 后事实丢失 | 检查 compaction 是否保留 claim id、anchor id、source cursor 和 supersession |
| 工具重复调用过多 | 检查已有 verified claim 是否被标为 stale / missing evidence；若证据足够却仍重查，修 retrieval / RunInputBuilder 策略 |
| 用户假设污染事实 | 检查 assumption register 与 verified claim ledger 是否混同 |
| 群聊 / 多用户场景串记忆 | 检查 memory scope、owner_ref、visibility 和 ingestion policy |
