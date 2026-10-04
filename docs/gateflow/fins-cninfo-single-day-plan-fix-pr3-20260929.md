RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-68b358c4

# CNInfo 单日计划 PR3-F1 修订记录

- 任务标签：`cninfo-local-day-pr3-sol-20260929-01`。
- 对象：`/private/tmp/dayu-cninfo-single-day/docs/gateflow/fins-cninfo-single-day-plan-20260929.md`。
- 修订前 SHA-256：`8a7c87dd347dd0a41a0f13fdb4c5f08595f1a59ed15f2818f59189dd632c9c2c`；动笔前实测与锁定值一致。
- 修订后 SHA-256：`a0ef88af7de5a6335cb3a343c600f6c563a5bd0baf8d5c828e79435af67af30c`。

## 直接证据与判断

1. `/private/tmp/dayu-cninfo-single-day/docs/gateflow/fins-cninfo-single-day-plan-adjudication-20260929.md` 最新 PR3-F1 已接受：原计划仅凭 8 位长度拒绝整数/数字字符串，与其余位数统一按毫秒解释矛盾，且没有直接 provider 协议来源。该特殊拒绝的动机不成立。
2. `/private/tmp/dayu-cninfo-single-day/docs/gateflow/fins-cninfo-single-day-plan-fix-pr2-20260929.md` 记录生产字段的只读 provider POST：`stock=000333,9900005965`、`category=category_ndbg_szsh;`、`seDate=2025-03-29~2025-03-29`，返回两条目标公告，`announcementTime` 均为 13 位 JSON 整数 `1743177600000`。本轮读取该原始样本记录与当前代码，未重新请求 provider；现有证据未显示推翻统一 epoch 毫秒解释的响应。
3. `/private/tmp/dayu-cninfo-single-day/dayu/fins/downloaders/cninfo_downloader.py` 当前 `_query_announcement_page` 原样传 `seDate`；`_parse_raw_announcement` 从 `_format_announcement_date` 取得唯一 DTO 日期，无效日期丢弃。现有数值路径用 `time.gmtime` 投影 UTC 日；计划修复仍归这个 DTO owner，不在下游补偿。
4. 本轮用 Python 标准库整数毫秒与固定 UTC+08:00 复核：`1743177600000` → `2025-03-29T00:00:00+08:00`；`20250328` → `1970-01-01T13:37:30.328000+08:00`。后者只是 epoch 毫秒值，不能据此声称 provider 支持 compact `YYYYMMDD`。

## 修订

- 只修 PR3-F1：删除计划输入边界、验收矩阵和停止条件中的“恰好 8 位拒绝”。可表示的非 `bool` 非负整数与无符号、无空白、仅 ASCII `[0-9]` 的十进制数字字符串统一按整数 epoch 毫秒和固定中国 UTC+08:00 投影；8 位 `20250328` 的整数/字符串应得 `1970-01-01`。普通 ASCII `YYYY-MM-DD` 日期字符串保留；`bool`、`float`、负号、非 ASCII、非整数及不可表示越界仍拒绝。
- 真实目标公告若出现原始形态或 provider 日历归属与统一毫秒解释冲突，以直接 provider 证据停止并交 provider 协议与 DTO owner 裁决；计划不增加长度、日期外观或年份 heuristic。
- PR2-F2 的测试指令仍不固化“先择优后过滤”导致的窗口外竞争者压制；`seDate` 保持用户闭区间原样，旧已发布 source/meta/manifest 的处理仍另议。没有实施代码、测试或 README 修改。

## 验证、失败命令与风险

- 验证：修订前后运行 `shasum -a 256`；读回计划输入边界、日期 owner 验收和停止条件，核对 8 位整数/字符串的期望为 `1970-01-01` 且不再按长度拒绝；读回 PR2-F2、历史与 `seDate` 边界；用标准库复核两个时间值。上述检查是文档与算术验证，不是产品验收。
- 失败命令：本轮无失败命令。未运行 pytest、pyright、coverage 或真实 CLI；仅修计划，不能声称这些门槛通过。
- 剩余风险：已记录的真实 provider 样本只覆盖指定 ticker、财期和日期，不能证明未来或其他公告没有不同时间协议。若真实目标公告证实协议变化，实施须按计划停止并裁决；selection 的窗口外同组竞争者风险及历史数据核查仍独立保留。计划仍待同版 review，产品未修改。
