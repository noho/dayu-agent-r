# CNInfo 单日发现窗口：Gateflow goal confirmation

- Gate：用户于 2026-09-29 确认修订后的 goal：CNInfo 公开 `filing_date` 采用**中国本地披露日**，只修新发现/新下载；历史已发布数据另议。隔离工作区 `/private/tmp/dayu-cninfo-single-day`，分支 `codex/cninfo-single-day`，基线 HEAD `9735800cb55a40336469593fa2fddae43c9c69ad`。本 work unit 纳入 PR #197，不改 #198 S1 的 accepted typed-failure 计划。
- 一手证据在主工作区 `docs/gateflow/issue-198-s1-cninfo-single-day-evidence-20260929.md` 及本隔离工作区 `docs/gateflow/fins-cninfo-single-day-plan-20260929.md`：000333/FY 的 `2025-03-28~2025-03-28` provider 零公告，而 `2025-03-29~2025-03-29` 返回两条；后者数值 `announcementTime=2025-03-28T16:00:00Z`，对应中国本地 `2025-03-29T00:00:00+08:00`。当前 `_format_announcement_date` 用 UTC `time.gmtime` 错投 03-28。这定位为来源时间戳日历投影与 provider 查询日历不一致；不能再把相等端点本身称为根因。

## 第一性原理判断

`CnReportQuery` 的闭区间在中国本地披露日上解释。当前 provider `seDate=03-29~03-29` 正确返回该公告，Dayu DTO 却用 UTC `gmtime` 产出 03-28，导致公共日期与来源查询日历不一致，单日发现和发布的 `filing_date` 可能漂移。严重性是漏财报或发布错误日期，而非内容抽取准确率。证据只覆盖当前 ticker/样本，转换规则应基于来源时间戳类型和中国固定时区语义，不用样本日期硬编码。

## 目标、成功信号和 owner

1. CNInfo downloader 的原始公告 DTO owner 把毫秒时间戳整数及数字字符串统一投影为中国本地 `YYYY-MM-DD`；provider 已给出的普通 `YYYY-MM-DD` 字符串保持其本地日历值。公开 `filing_date`、候选 selection、source meta、manifest 从该同一日历事实派生；`seDate` 继续使用用户闭区间，不基于 03-28 样本扩窗。
2. 单日 `2025-03-29~2025-03-29` 能发现并正确发布上述有效公告；前后邻日不得误入。测试覆盖 UTC+8 午夜前后、12 月 31 日跨年、数值/数字字符串/普通日期字符串，直接锁 CNInfo DTO→candidate→selection→身份/发布读取链。跨年日期可能影响标题缺年份时的财年推断与文档 ID，必须核真实 owner，不宣称 ID 一律不变。
3. 至少一条隔离真实 CNInfo CLI/只读发现复验 03-29 单日与邻日，保留 argv/exit/双流、公共仓储读回和外部服务可用性界限。受影响测试、pyright、每改动生产文件单文件覆盖率 ≥80%，按 README 触发规则判断更新。旧 source/meta/manifest 不在此项自动重写。

## 非目标、依赖与停止条件

- 不改 #198 S1 typed source integrity、公用失败分类、job/direct 投影；不把三天窗口的 #198 验收补证冒充单日产品修复。HKEX、SEC、Docling 内容抽取、财报财期推断和 schema 不在本项。
- 历史已发布 CNInfo `filing_date`、可能间接受影响的财年/身份及 manifest 另立迁移或核查 work unit，不能让本次新下载修复暗改旧存储；不发送 CNInfo 上游 issue，不改 HKEX/SEC、Docling 抽取或 #198 typed failure。
- 相关证据和本 goal 是当前未合并工作，不代表产品已修。下一 gate：Sol 基于修订后 goal 产出 code-generation-ready plan，Kimi/MiMo 同版 `$planreview`；闭环代码经独立 review 后集成 PR #197，由用户手工 merge。
