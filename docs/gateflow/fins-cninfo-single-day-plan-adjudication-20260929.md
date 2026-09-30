# CNInfo 单日发现计划阻断：总控裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol label `cninfo-single-day-plan-sol-20260929-01`，显式绝对工作区 `/private/tmp/dayu-cninfo-single-day`，进程 exit 0、JSONL `turn.completed`、canary `gpt-6-sol-90952cc1` 匹配、stderr 空；但 56 个 command_execution 中三条非零：memory `rg` exit1、错误路径 `rg` exit2、隔离 `.venv` 查询 exit1。按 sub-agents 严格协议本次 `agent_status=failed`，只采纳可独立复核的根因证据，不计 plan gate pass。
- 直接代码同源：provider `seDate` 原样使用请求边界；`announcementTime` 数值在 `cninfo_downloader._format_announcement_date` 经 UTC `time.gmtime` 取日；`CninfoRawAnnouncement.announcement_date` 传给 `CnReportCandidate.filing_date`，随后用于 closed-window 过滤与 publication meta。真实只读 provider 矩阵在 `docs/gateflow/fins-cninfo-single-day-plan-20260929.md`；`2025-03-29~2025-03-29` 返回两个公告，时间戳 `2025-03-28T16:00:00Z`，即中国本地 `2025-03-29T00:00:00+08:00`。因此旧 goal 把该公告叫作「03-28 当日真实披露」、归咎于 provider 相等端点拒绝，均不能成立。
- 当前公共文案称 `filing_date` 为「披露日期」，CNInfo provider 按中国本地日历查询；优先建议 Dayu 在 CNInfo 原始公告 DTO owner 把数值时间戳投影为该本地日，使请求窗口和候选日期同历法。此建议需要用户确认公开日期语义。若确认，仅修新发现/新下载，不把历史已发布 source/meta 直接重写；历史影响先登记和评估 document_id/版本/manifest 真源，必要时另立迁移 work unit。若选择 UTC，则需证明有界请求适配和 selection 前过滤，不从单样本硬编码 +1 日。
- 现有 goal `docs/gateflow/fins-cninfo-single-day-goal-20260929.md` 的错误动机与成功样本须修订。当前 gate 回到 goal confirmation；用户回复日期语义前，不实施日期转换或窗口扩张，未进入 Kimi/MiMo plan review。隔离 worktree 尚无 `.venv`，后续产品实施前需按 AGENTS.md 配齐本工作区可激活 Python 3.11 环境并实测。
- 历史影响初核：`cn_download_identity.resolve_cn_download_ids` 对 CNInfo 根据 ticker/财期/财年分配身份，`filing_date` 不直接参与该 ID；但 `cn_download_filing_workflow` 对已 COMPLETE 且未指定 `overwrite` 的来源在读取 meta 后立即 `integrity_complete` skip，不会把新的日期投影写回旧 source meta/manifest。故修解析器只影响新发布或后续明确覆盖的来源；「旧数据自然自动修正」不成立。对既有来源是否做迁移、重建或保持原样须单独判定，不能在此 WU 以 adapter 侧重算掩盖持久化事实。
- 额外边界：`cn_report_selection._infer_cninfo_fiscal_year` 在标题缺明确年份时可用 `announcement_date` 推断财年；日期跨 12 月 31 日修正可能间接改变候选财年与上述分配 ID。正式 plan 必须用跨年午夜的 owner 测试或证明相关标题族不适用，不能仅用 2025-03-29 样本断言「ID 永远不变」。若确认本地日历，转换应在 CNInfo DTO 的 `_format_announcement_date` 一处处理整数与数字字符串时间戳，普通 `YYYY-MM-DD` 字符串保留其 provider 日历值；测试分别覆盖午夜边界、跨年、选择前过滤与完整发布读回。

## 用户日期真源裁决与 goal 重订（2026-09-29）

- 用户明确选择「中国本地披露日；历史另议」。总控据真实 `2025-03-28 16:00 UTC = 中国本地 2025-03-29` 及 provider `seDate=03-29~03-29` 返回该公告的同源证据，修订 `docs/gateflow/fins-cninfo-single-day-goal-20260929.md`：CNInfo 数值时间戳在 DTO owner 统一转中国本地日，普通日期字符串保留 provider 日历值；新发现/新下载共用该事实，不再把 provider 相等端点误判为根因，也不扩窗。跨年财年/ID 间接影响须测试，历史已发布 source/meta/manifest 只登记独立迁移/核查，不在当前 WU 重写。
- 旧 Sol 计划 `docs/gateflow/fins-cninfo-single-day-plan-20260929.md` 是错误 goal 下的候选，不能进入 review/实施。下一 gate gpt-6-sol 按已确认新 goal 重写同一计划，之后同 SHA Kimi/MiMo 独立 `$planreview`。#198 S1 typed failure 候选与此日期 WU 保持分离，最终均进入 PR #197。

## Sol 修订计划候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `cninfo-local-day-sol-20260929-01` 进程 exit0、JSONL 97 条可解析、`turn.completed`、38 条成功命令、canary `gpt-6-sol-87b406bc` 匹配；三处失败 event 与 stderr `apply_patch` 重叠操作错误，严格不计有效 agent completion。总控实读 `docs/gateflow/fins-cninfo-single-day-plan-20260929.md` 和 `docs/gateflow/fins-cninfo-single-day-plan-local-day-fix-20260929.md`：计划以 DTO 数值时间戳中国固定 UTC+08:00 为唯一日期 owner，不扩 `seDate`，覆盖 UTC 16:00 边界、跨年财年/ID、selection、source meta/manifest、历史 COMPLETE skip、真实隔离 CLI。计划只是候选；下一 gate Kimi/MiMo 同版独立审查，产品未修改。

## Kimi 修订计划同版复审

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr [claude-code:unrecognized_model] 精确白名单模型名提示"
retry_class: none
```

- Kimi `cninfo-local-day-pr1-kimi-20260929-01` 显式绝对 CNInfo workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、49 turns、canary `kimi-70d22772` 匹配。artifact `docs/reviews/plan-review-20260929-183812.md` 锁计划 SHA `b1c5fce35e2549014be0b9bc51436142e0b809f5052f2dfaa015ee4deda56333`，结论 pass-with-risks、无 material finding。总控实读其代码路径与边界：DTO 是 CNInfo announcement_date 产生 owner，`seDate` 原样闭区间、后续 selection 先择优再按窗口过滤、缺年标题用日期年份派 ID，旧 COMPLETE skip 在写入前，meta→manifest 同源。Kimi 指出旧 UTC 午夜测试值两种规则相同，仅新增 UTC16:00 边界有区分力；计划矩阵已要求该新增用例，因此列实施精度，非 blocker。MiMo 同 SHA 仍在途；单路不能通过 plan gate，产品未实施。

## MiMo 同版审查与总控新修复裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr [claude-code:unrecognized_model] 精确白名单模型名提示"
retry_class: none
```

- MiMo `cninfo-local-day-pr1-mimo-20260929-01` 在同 SHA 独立 clone、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、62 turns、canary `mimo-a3041fc3` 匹配。artifact `/private/tmp/dayu-cninfo-review-mimo/docs/reviews/plan-review-20260929-184625.md` 判 pass-with-risks，但含两项可执行 finding；总控直接核 `cninfo_downloader.py:_format_announcement_date` 的 `isinstance((int,float))` 与 `str.isdigit()`、selection 先择优后窗口过滤及 goal 范围后裁决如下。真实 provider 03-29 单日返回两条、03-28/03-30 零条的只读复探是额外同源证据，不替代正式 CLI。
- **PR2-F1 中／accepted／未修复**：计划说 bool、float、畸形/越界数字不可暗中当有效毫秒，验收却写“按明确 DTO 规则”，没有给精确输入类型、数字字符串语法、异常值处置。当前 `bool` 是 `int` 子类，`True` 会被转成 1970 日期；若实施者自定规则会固化旧错误。Sol 在 DTO owner 计划明确：只接受非 bool 的整数与 ASCII 十进制毫秒数字字符串，统一以整数毫秒加固定中国 UTC+08:00 转日期；bool、float、负号/非 ASCII/非整数/不可表示的越界时间返回 `None`，沿既有 DTO 丢弃路径，不在下游猜。对于 8 位紧凑日期候选与合理年份边界，先核实际 provider 协议/现有历史测试再定最小可证约束；不得凭 reviewer 举例直接引入 1990–2100 等任意范围或用启发式猜 `YYYYMMDD`。计划必须明确该决策及测试，不能留给实现者自选。
- **PR2-F2 低／accepted／未修复**：计划“检验先择优后过滤顺序”未指定断言方向，可能把窗口外竞争者压制窗口内候选的偶然危险行为写成期望测试，或诱导超白名单改 selection owner。计划改为仅锁 03-29 窗口内全文正确选中、邻日排除及标题无年份时披露日历年份→财年/ID 的 owner 规则；**不**为外日压制写期望断言。若真实 provider 返回窗口外同组竞争者，保留既定 stop condition、另行裁决 selection，不在本 WU 偷改。两 finding 均先由 Sol 修计划并同版 Kimi/MiMo 复审，不能以两路 pass-with-risks 忽略未修复项；产品未实施。

## Sol PR2 候选与总控 PR3-F1 反例

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Sol `cninfo-local-day-pr2-sol-20260929-01` 进程 exit0、JSONL 79 条可解析、`turn.completed`、31 条成功命令、canary `gpt-6-sol-b832ada2` 匹配、stderr 空；三条错误路径/无匹配/`diff --no-index` 非零产生 failed event，严格 `agent_status=failed`，仅作计划候选。新计划 SHA `8a7c87dd347dd0a41a0f13fdb4c5f08595f1a59ed15f2818f59189dd632c9c2c`，fix artifact `docs/gateflow/fins-cninfo-single-day-plan-fix-pr2-20260929.md`。PR2-F2 测试意图内容已修；PR2-F1 的 bool/float/ASCII/整数毫秒基本合同已明确，但出现下列新问题，不能进同版 review。
- **PR3-F1 中／accepted／未修复**：新计划 §输入边界把“恰好 8 位”的非负整数/ASCII 数字字符串单独拒绝，理由仅是没有 compact `YYYYMMDD` 协议证据；同一计划却允许 9～12 位数字仍按 epoch 毫秒落入 1970～2001，不能用 8 位特殊长度证明值不属于毫秒，更不能防其他 compact 或截断形态。总控直接核 plan 第 15/33/41 行与真实 provider 13 位整数 `1743177600000`、既有代码通用 `gmtime`：8 位特殊分支既无协议/历史边界证据，也让同一“整数毫秒”合同按偶然长度分叉，违反 AGENTS.md 的自适应/唯一 owner 规则。Sol 计划须二选一且给来源：①统一支持可表示的非负整数毫秒与 ASCII 数字字符串，不猜 compact 日期；在真实目标公告出现不符协议形态时以证据触发停止；或 ②有直接 provider 协议/历史范围证据后给**统一**时间范围/格式规则并对所有数值输入同一判定，不能只排 8 位或任意 1990–2100 魔法窗。当前证据只支持①。保留 bool/float/负数/不可表示拒绝、固定 UTC+08:00、PR2-F2 与历史边界；删 8 位特判及对应测试，写明 8 位作为毫秒会落 1970，这是源协议解释而非支持 compact 日期。若真实 provider 出现 compact 日期形态，独立停下裁决协议，不在 DTO heuristic 猜。新修复先登记，Sol 只修计划后再同版 Kimi/MiMo 复审；产品未改。

## Sol PR3-F1 计划修订候选

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Sol `cninfo-local-day-pr3-sol-20260929-01` 进程 exit0、JSONL 64 条可解析、`turn.completed`、26 条成功命令、零失败事件、stderr 空、canary `gpt-6-sol-68b358c4` 匹配。新计划 SHA `a0ef88af7de5a6335cb3a343c600f6c563a5bd0baf8d5c828e79435af67af30c`，fix artifact `docs/gateflow/fins-cninfo-single-day-plan-fix-pr3-20260929.md`。总控核第 15/33/41 行：非 bool 非负整数及 ASCII 数字字符串同一 epoch 毫秒→UTC+08:00，8 位 `20250328` 按协议是 1970-01-01 而非 compact 日期；无长度/任意年份分支，真实 provider 形态冲突再停并裁协议。PR2-F1/F2 与用户本地日/历史边界未回退。PR3-F1 **内容候选已修**，尚须 MiMo 与经用户授权的 Kimi 额度不足 `ds-flash` 备份同 SHA 独立 plan review；产品未实施。

## PR3 同版双路计划审查派发

- 计划 SHA `a0ef88af7de5a6335cb3a343c600f6c563a5bd0baf8d5c828e79435af67af30c` 已在主计划 workspace 与独立 MiMo clone 复核相等。用户已授权 Kimi 额度不足时使用 `ds-flash` 备份；此前同类 Kimi HTTP403 已结构化登记。`cninfo-pr3-dsflash-backup-20260929-01` 与 `cninfo-pr3-mimo-20260929-01` 均预检 `setup_status=ok`，显式绝对 workspace，独立 output/stderr/canary；sessions `59136`/`25290` 在途。未读终态前不计 plan gate，产品未实施。

## PR3 ds-flash 同版审查 DS-1/DS-2 裁决

- `cninfo-pr3-dsflash-backup-20260929-01` 进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `ds-flash-a753a10f` 匹配，stderr 仅白名单模型名提示。review `docs/reviews/plan-review-20260929-191231.md` 锁 SHA `a0ef88af7de5a6335cb3a343c600f6c563a5bd0baf8d5c828e79435af67af30c`，内容 pass-with-risks，PR2-F1/F2 与 PR3-F1 已闭合，新增两项。总控实读 `cninfo_downloader.py:_parse_raw_announcement`：日期返回 None 与其它缺字段共用静默丢弃；计划停止条件要求真实 provider 日期形态冲突时停下，却没有可观察诊断。
- **PR4-F1 中／accepted／未修复**：在 CNInfo DTO 解析 owner 的日期输入拒绝分支增加固定、去原文/凭据的告警或同等可观察计数，尤其只针对 PDF 且其它必需业务字段完整的公告，不把所有非 PDF 或残缺 DTO 当 date protocol drift；计划写清格式不符时日志仅供 operator 发现并触发人工停工/协议裁决，不能把记录 WARN 伪称自动停止。测试断言 malformed 时间不会入候选且有安全可观察信号；仍拒绝 bool/float/非 ASCII/越界，不擅扩成整数浮点或位数 heuristic。真实样本验收须检查零结果与告警区分。
- **PR4-F2 低／accepted 为独立残余／未修复**：`resolve_window` 缺省锚点用宿主 `date.today()`，docstring 却称 UTC；新中国本地披露日只在显式窗口保持同日历，缺省窗口可滞后。计划明确本 WU 的 CLI 验收固定显式日期，另立 `fins-cninfo-default-window-local-day` WU 裁决缺省窗口 owner 与日期/docstring；不在本日期 DTO 修复中凭样本改默认窗口。MiMo 同 SHA 仍在途，收齐后 Sol 同版计划修订。

## PR3 MiMo 同版审查内容与协议状态

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: ["[claude-code:unrecognized_model]"]
retry_class: none
```

- MiMo `cninfo-pr3-mimo-20260929-01` 进程 exit0、JSON success/52 turns、canary `mimo-ba888d88` 匹配，stderr 仅白名单提示；但 review `docs/reviews/plan-review-20260929-193116.md` 自报两条非零 shell 命令（无匹配 zsh glob、预期缺 `.venv` 的 ls），违反本轮“所有检查命令自身 exit0”额外合同，故内容只作候选，**不计有效第二路**。锁计划 SHA `a0ef88af7de5a6335cb3a343c600f6c563a5bd0baf8d5c828e79435af67af30c`，内容 pass-with-risks、无 material finding；PR2-F1/F2、PR3-F1 未见回退。
- **PR4-F3 中／accepted／未修复**：现计划“普通 ASCII YYYY-MM-DD 字符串保留 provider 日历值”没有精确定义非法日历、首尾空白、非 ASCII 数字；现码 `strip()` + Unicode `\d` 会接纳一部分畸形值。DTO 日期是唯一 owner，不能让实施者自选。计划改为日期文本**精确 ASCII YYYY-MM-DD 且实际存在**才原样返回，复用 `dayu.fins.domain.filing_semantics.parse_iso_calendar_date` 的严格日历合同或同源 parser；非法日期、空白、非 ASCII 返回 None 走既有丢弃路径，不给下游补偿。补 `2025-02-30`、`2025-13-45`、`0000-01-01`、空白及全角负例。此处与已接受 O11 非法日期拒绝同源，属于 DTO owner 的拒绝规则，不更改 `seDate`。
- **PR4-F4 低／accepted 为验收证据精度／未修复**：正式真实 CLI 03-29/邻日复验须保存三次 provider 原始响应字节、SHA-256 和对应窗口/网络时点；邻日自动测试要使同一 03-29 原始公告经过闭区间过滤或按 `seDate` 键返回该公告，避免 mock 恒空的空转断言。此项不改变选择策略。
- PR4-F1/F3 共享 DTO owner，PR4-F2 独立 WU，PR4-F4 是验收精度；先由 Sol 同版修计划，再用新 SHA 有效双路审查。产品未实施。

## Sol PR4 修订候选

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `cninfo-pr4-sol-20260929-01` exit0、68 条 JSONL 有 `turn.completed` 且无 failed/error event，stderr 空，canary `gpt-6-sol-471e9590` 匹配。计划从 SHA `a0ef88af...` 修到 `d5c56f0680c8d885a78b31656b108f2dde28d0e3c004ddf5a719ae67c00ecba4`，fix `docs/gateflow/fins-cninfo-single-day-plan-fix-pr4-20260929.md`。总控实读：完整 PDF 必需字段但日期非法时固定脱敏告警，非 PDF/残缺条目不产噪；普通日期字符串复用 domain 精确 ASCII 真日历规则；缺省窗口归独立 WU；邻日 mock 不恒空，同次三日 provider 响应原始字节+SHA 与网络时点留证。PR4-F1/F3/F4 内容候选已修，F2 归属明确；仍须新 SHA 双路 plan review，产品未实施。
