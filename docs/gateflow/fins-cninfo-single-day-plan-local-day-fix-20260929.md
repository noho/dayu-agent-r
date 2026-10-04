# CNInfo 中国本地披露日：实施与验收对照

本文件是 `fins-cninfo-single-day-plan-20260929.md` 的逐层核对表，不单独扩大改动范围或授权实施。goal 已裁定公开 `filing_date` 采用中国本地披露日；历史已发布来源另议。所有路径相对于仓库根目录。

## 证据 → owner → 预期

| 直接证据/当前代码 | 唯一 owner | 修复后的可观察合同 |
| --- | --- | --- |
| `announcementTime=1743177600000`，UTC 2025-03-28 16:00，即 UTC+08:00 2025-03-29 00:00；provider `seDate=2025-03-29~2025-03-29` 返回两条，03-28 单日为零。 | `dayu/fins/downloaders/cninfo_downloader.py` 的 `_parse_raw_announcement` / `_format_announcement_date` | 整数及数字字符串毫秒值均产生 `CninfoRawAnnouncement.announcement_date=2025-03-29`；普通 `YYYY-MM-DD` 保留 provider 原值。`seDate` 不变。 |
| `select_cninfo_report_candidates` 按 DTO 日期推断缺年份标题的财年、同财期/年择优并构造 `CnReportCandidate.filing_date`。 | `dayu/fins/pipelines/cn_report_selection.py` 消费同一日期，不另造日期 owner。 | 03-29 全文候选日期正确；显式标题年份按标题，缺年份标题跨年时财年可变。 |
| `cn_download_workflow._select_candidates_for_a4` 在候选去重后做闭区间过滤；`resolve_cn_download_ids` 用候选财年/财期/修订状态生成 CNInfo ID。 | 既有选择/身份 owner。 | 03-29 单日选中，03-28/03-30 单日排除；跨年标题缺年份时核对新 ID，不能宣称 ID 恒定。 |
| `_build_base_meta` 从候选写 `filing_date`；`FilingManifestItem.from_source_meta` 从 meta 投影 manifest。COMPLETE 且无 overwrite 会 skip。 | 既有发布/storage owner。 | 新 source 的结果、meta、manifest 同为 03-29；旧 COMPLETE source 原有 meta/manifest 不被本修复自动改写。 |

原始 provider 03-28/03-29 窗口数据来自旧 plan 的只读矩阵；主工作区 `issue-198-s1-cninfo-single-day-evidence-20260929.md` 提供 #198 S1 的窄/三日观察。旧计划中“相等端点导致漏报、应扩窗”的推论已撤销，不能把三日 #198 CLI 结果当作本单日修复验收。

## 测试用例矩阵

| 层与测试位置 | 输入 | 必须断言 |
| --- | --- | --- |
| DTO / `tests/fins/test_cninfo_downloader.py` | UTC 03-28 15:59:59.999 / 16:00:00.000；毫秒整数与十进制数字字符串；日期字符串 `2025-03-28` | 前者本地 03-28、后者本地 03-29；字符串日期仍为 03-28；原始 `seDate` 等于请求的闭区间。既有 `1743638400000` UTC 午夜测试仍应为本地 04-03，另增跨日反例，避免旧测试误通过。 |
| DTO 跨年 / 同文件 | UTC 12-31 15:59:59.999 / 16:00:00.000，及布尔、浮点、畸形/越界值 | 本地分别为 12-31 / 次年 01-01；非法形态按明确 owner 规则拒绝或丢弃，不经 float 宽松转义造成误日。 |
| candidate / `tests/fins/test_cninfo_downloader.py` 与 `tests/fins/test_cn_report_selection.py` | 模拟原始 JSON 的 `1222951198` 摘要与 `1222951181` 全文，只在 03-29 单日响应；分别查询邻日 | 选全文 `1222951181`，`filing_date=2025-03-29`；前后邻日无该 source。标题有年份取标题财年，缺年份跨年按 DTO 日期推断，并核对 ID 输入；若真实 provider 返回跨日竞争候选，停止并裁决选择 owner。 |
| workflow/发布 / `tests/fins/test_cn_download_workflow.py` | 从真实解析/选择链进入隔离仓储的新下载；另预置一条 COMPLETE 旧来源后无 overwrite 再查 | 闭区间、财年、ID、结果/事件、source meta、manifest 和仓储完整性一致；旧来源无自动重写。测试不得用手工填好的 `filing_date` 替代待验证的 DTO 链。 |
| 真实 CLI / 新临时工作区 | `000333`、FY，分别用 03-28、03-29、03-30 三个单日闭区间 | 03-29 `discovered=1` 且有效下载/发布时，仓储 meta 与 manifest 均为 03-29；邻日不能发布 `1222951181`。保存 argv/exit/双流、provider 时间和仓储读回；外部失败单独标注，不算通过。 |

## 实施检查点

1. 先复核修订 goal、裁决、代码及 provider 一手材料；若不一致，按主计划停止。确认只有 CNInfo DTO 生成日期，候选/发布只消费它。
2. 在唯一生产白名单 `dayu/fins/downloaders/cninfo_downloader.py` 做显式 UTC → 固定 UTC+08:00 的毫秒转换，统一整数/数字字符串路径，保留普通日期字符串；不扩 `seDate`，不改 HKEX/SEC、CLI 展示或 storage schema。
3. 只在主计划列出的三个 `tests/fins/` 文件增加 owner 级回归，使用实际 DTO/selection/identity/publication 边界；测试 fixture 不能预先把原始时间戳改成目标日期。
4. 配齐隔离 `.venv` 后激活，运行受影响测试、每个改动生产文件单独 coverage ≥80%、`python -m pyright dayu/ tests/ utils/`；按 README 触发规则核对各文档职责。记录命令、退出码和未通过项。
5. 用全新临时 `--base` 完成真实 03-29 单日 CLI 和邻日复验，按仓储协议读回 source meta/完整性/primary file，并核对 manifest 日期；留存 argv、exit、stdout、stderr。之后才提交同版 plan review 和代码 review 所需证据。

历史 source/meta/manifest 不随本修复迁移；另行核查日期、标题缺年份财年、ID、版本及 manifest 真源，再决定是否立 migration。若这些语义需要在当前 work unit 里靠显示层重算或改写旧来源才能成立，停止并请求所有权裁决。
