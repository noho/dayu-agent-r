# F5-IV03：远端年度证据先于查询窗口过滤

状态：中／accepted／未修复。同一 F5-S1 必要修复；不是新业务裁决。唯一 owner 为 `dayu/fins/pipelines/cn_report_selection.py:select_hkexnews_report_candidates` 的远端证据选择。

## 直接证据与根因

固定中断候选SHA9396f25fc3128b87b38e81cfca00b51d9140b7f11c426cb0de4effec2993c65e，函数319–322先对全部去重raw提取年度end，329处才按 query.start_date/end_date 跳过候选。`HkexnewsDiscoveryClient._query_period_announcements`实际只按合法raw/stock匹配传递rows，未在上游执行日期过滤，因此来源响应存在窗口外行时可真实到达此owner。既有selector的日期过滤本身表明窗口边界由该owner负责；新anchor路径绕开它。

root明确标记合成内存反例（非官方实际HTTP观察、无network/PDF/FS业务写）：query只2025-11-13，B标题截至2025-09-30止三个月；local_annual_ends空。仅B→known0/uncertain1；额外放入披露日2025-03-19的年度raw（截至2024-12-31）→known1/uncertain0。远端年度在查询窗外，仍使B被确定；HEAD helper使用真实typed测试输入，无网络。全部72源码前后SHA保持。

反例实证 `workspace/tmp/pr197-f5-interrupted-source-audit-20261001/root-outside-window-probe.json`，本轮 .venv Python exit0。结果证明输入边界缺陷，不声称官方当前响应真的越界。

## 依据和最小owner修复

accepted plan §4/§6要求完整取得**当前窗口**raw并使用同公司可用证据；§11明确不扩历史网络窗口。用户允许推断，仍须按已定可用证据边界。不能用窗口外远端行作为新证据；已登记本地COMPLETE可信年度是独立合法证据，不应因此按其披露日过滤。

在selection source-of-truth中对去重raw建立当前query窗口集合，年度anchor和主候选均从此同一集合取。保同sourceID核心冲突原ValueError/去重语义、完整stock-scope运输、英文年度先参与证据后英文候选过滤、366唯一calendarowner。不能在CLI/adapter/header/测试夹具局部补过滤。

必要回归：窗口外远端年度不能改变Bunknown/触发HEAD；同一年度纳入更宽实际窗口后允许确定；local可信年度仍能在窄窗确定；冲突/重复ID原行为及英文anchor保。集中必要fix及正式同版双审，不另小slice/重开既有裁决。

## 2026-10-02 最终状态覆盖

accepted / 已修复；完整作者、正式两审及同版复审由总控独立核准。最终裁决见 pr-197-r1-f5-s1-code-review-final-adjudication-20261002.md。原未修状态为历史，不覆盖本条；code gate PASS，aggregate/PR/final closeout另行推进。
