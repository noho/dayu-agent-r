RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-b832ada2

# CNInfo 单日计划 PR2-F1/F2 最小修订记录

- 任务标签：`cninfo-local-day-pr2-sol-20260929-01`。
- 对象：`docs/gateflow/fins-cninfo-single-day-plan-20260929.md`；修订前 SHA-256 `b1c5fce35e2549014be0b9bc51436142e0b809f5052f2dfaa015ee4deda56333`，修订后 SHA-256 `8a7c87dd347dd0a41a0f13fdb4c5f08595f1a59ed15f2818f59189dd632c9c2c`。动笔前实测前者与任务锁定值一致。
- 决策依据：`docs/gateflow/fins-cninfo-single-day-goal-20260929.md` 的“中国本地披露日；历史另议”；`docs/gateflow/fins-cninfo-single-day-plan-adjudication-20260929.md` 的最新 PR2-F1/F2 accepted 裁决；同版 Kimi `docs/reviews/plan-review-20260929-183812.md` 与 MiMo `/private/tmp/dayu-cninfo-review-mimo/docs/reviews/plan-review-20260929-184625.md`。

## 直接证据与判断

1. `dayu/fins/downloaders/cninfo_downloader.py` 的 `_query_announcement_page` 原样发送 `seDate=start_date~end_date`；`_parse_raw_announcement` 只从 `_format_announcement_date(raw["announcementTime"])` 取得 DTO 日期，无效时丢弃。现有 `_format_announcement_date` 把 `bool` 纳入 `int`、接受 `float`，对数字字符串先 `isdigit()` 再转 `float` 并用 `time.gmtime` 取 UTC 日。这正是 PR2-F1 的 owner 级合同缺口。
2. 本轮用生产相同字段只读 POST `http://www.cninfo.com.cn/new/hisAnnouncement/query`，`stock=000333,9900005965`、`category=category_ndbg_szsh;`、`seDate=2025-03-29~2025-03-29`：`totalRecordNum=2`，公告 `1222951198` 摘要与 `1222951181` 全文的 `announcementTime` 均为 JSON 整数 `1743177600000`。该值为中国固定 UTC+08:00 的 `2025-03-29T00:00:00+08:00`。MiMo 的独立实时探针还记录 03-28/03-30 邻日零结果、三日无窗口外泄漏；本轮未重做邻日探针。
3. `tests/fins/test_cninfo_downloader.py` 的 `_build_announcement` 注释说明真实 provider 用整数毫秒，但历史夹具统一用 `YYYY-MM-DD` 字符串；既有整数用例 `1743638400000` 投影 04-03，在 UTC/UTC+08:00 下同日。检索该测试、selection/workflow 测试与本项文档，未找到真实 8 位 `announcementTime` 响应或 compact-date 协议。`20250328` 若被误当毫秒，会成为 `1970-01-01T13:37:30.328+08:00`。因此不按任意年份区间筛选，也不猜 `YYYYMMDD`；8 位整数与数字字符串明确不支持并丢弃。若真实目标公告出现这种形态，停止并核证 provider 协议、裁决 DTO owner。
4. `dayu/fins/pipelines/cn_report_selection.py` 先按财期/财年择优，`cn_download_workflow` 随后按日期闭区间过滤；窗口外同组竞争者可能压制窗口内候选。`_infer_cninfo_fiscal_year` 对标题缺年回退到 DTO 披露日期年份。PR2-F2 应只测试 03-29 窗口内全文、邻日排除及缺年标题的财年/ID 真源，不把压制风险写成期望行为。

## 修订

- **PR2-F1**：计划的 DTO 输入合同现在限定非 `bool` 非负整数及无符号、无空白、仅 ASCII `[0-9]` 的数字字符串，共用 UTC epoch 整数毫秒到固定 UTC+08:00 的转换。普通 ASCII `YYYY-MM-DD` 保持原值；`bool`、`float`、负号、非 ASCII、非整数、不可表示越界及无协议证据的 8 位数字均返回 `None` 并由 DTO 丢弃。验收矩阵明确上述断言，真实 provider 若出现 8 位目标公告即停止裁决。
- **PR2-F2**：删除模糊的“检验当前先择优后过滤的顺序”要求；测试只锁 03-29 全文、邻日排除、标题缺年时披露日历年份到财年和 ID 的规则。真实窗口外同组竞争者沿原停止条件另裁 selection owner，本项不改算法。
- `seDate`、历史 source/meta/manifest 的边界未变；计划仍待同版复审，未进入实施 gate。

## 验证、失败命令与剩余风险

- 验证：修订前后各执行 `shasum -a 256`；只读 provider 请求返回两条预期 JSON 整数；用 Python 标准库复核 `20250328` 毫秒与 `1743177600000` 毫秒的 UTC+08:00 日期；读回计划对应段落并核对仅修订输入合同、验收指令和停止条件。仅文档修改，未运行 pytest、pyright、coverage 或真实 CLI，不能据此声称产品验收。
- 失败命令：`rg --files -g AGENTS.md dayu tests docs/gateflow docs/reviews` 无匹配，exit 1；对隔离工作区不存在的 `docs/gateflow/issue-198-s1-cninfo-single-day-evidence-20260929.md` 执行 `rg`，exit 2（证据实际在主工作区）；`git diff --no-index -- /dev/null docs/gateflow/fins-cninfo-single-day-plan-20260929.md` 因比较未跟踪文件与空文件返回 exit 1，输出仅供人工检查，非计划校验通过。未把这些非零结果计作成功。
- 剩余风险：实时协议证据只覆盖此 ticker/财期/日期及评审探针，不能证明所有历史或未来响应都没有 8 位形态；该形态按本计划被丢弃并触发真实目标公告的停止条件。selection 的先择优后过滤压制风险保留原停止条件。旧已发布日期与可能关联的财年/ID 仍须独立核查。没有代码或正式 CLI 结果。
