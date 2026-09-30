# CNInfo 单日计划 PR4-F1～F4 修订记录

- 性质：只修计划，不代表产品实现、测试或真实 CLI 验收通过；待新 SHA 同版独立 plan review 与总控裁决。
- 目标计划：`fins-cninfo-single-day-plan-20260929.md`。
- 修订前 SHA-256：`a0ef88af7de5a6335cb3a343c600f6c563a5bd0baf8d5c828e79435af67af30c`，修改前按原始字节实测一致。
- 修订后 SHA-256：`d5c56f0680c8d885a78b31656b108f2dde28d0e3c004ddf5a719ae67c00ecba4`。
- 依据：已确认 goal、`fins-cninfo-single-day-plan-adjudication-20260929.md` 的 PR4-F1～F4、PR3 同 SHA 两路 review（本工作区 `docs/reviews/plan-review-20260929-191231.md` 与独立 MiMo clone 的 `docs/reviews/plan-review-20260929-193116.md`），以及本工作区直接代码。MiMo 路原审查的命令协议失败状态由裁决保留；引用其内容不将其计作有效 plan gate。

## 动机与直接代码链

`cninfo_downloader.py:_query_announcement_page` 原样发送 `seDate=start~end`；`_format_announcement_date` 当前以 `time.gmtime` 将整数/数字字符串毫秒值投成 UTC 日。`_parse_raw_announcement` 把解析失败与非 PDF、其它缺字段合并为静默 `None`，`_query_announcements` 仅追加非 `None` DTO。该链使真实 `1743177600000` 毫秒公告被投为 03-28，而 provider 在显式 03-29 单日返回该公告；扩大 `seDate` 不是同源修复。

`dayu/fins/domain/filing_semantics.py:parse_iso_calendar_date` 使用 ASCII `[0-9]` 精确形状、真实 `datetime.date` 与原文一致性检查，`ValueError` 是拒绝契约。该模块依赖标准库及公共 JSON 契约，无 downloader 反向依赖，DTO owner 可直接复用，不需下游解析。`cn_form_utils.resolve_window` 的缺省 `today` 当前取宿主 `date.today()`，docstring 却称 UTC；这是独立窗口 owner 议题。

## 裁决落实与 owner

| 裁决 | 唯一 owner | 计划变动与验收边界 |
| --- | --- | --- |
| PR4-F1 | CNInfo 原始公告 DTO 解析边界 `_parse_raw_announcement`，日期值由 `_format_announcement_date` 产生 | 仅 PDF 且其它必需字段完整时，对缺失/非法 `announcementTime` 的拒绝写固定 `Log.warn` 正文「巨潮 PDF 公告时间不符合日期合同，已跳过」；原始字段缺失/`null` 不得被 `str()` 伪装成完整。日志不含原始内容、值、ID、标题、URL、ticker、类型、长度、凭据。非 PDF、其它字段残缺、有效日期无此告警。告警只供人工察觉，不能声称自动停工或自动认定协议漂移；operator 用受控原始响应裁决。 |
| PR4-F2 | `cn_form_utils.resolve_window` 是另一个窗口 owner | 本 WU 及真实 CLI 配方只用显式单日 `--start/--end`。缺省锚点及其 UTC docstring 不在 DTO 修复中改，登记独立 `fins-cninfo-default-window-local-day` WU 待裁决。 |
| PR4-F3 | CNInfo DTO 日期 owner 复用 Fins domain 严格日历真源 | 普通日期字符串必须原文精确 ASCII `YYYY-MM-DD` 且实际存在，验证通过后原样返回；`2025-02-30`、`2025-13-45`、`0000-01-01`、首尾空白、全角数字及其它非法值返回 `None`。数字字符串仍按统一整数 epoch 毫秒解释；不加 8 位或年份特判。 |
| PR4-F4 | 自动测试在 DTO→selection→workflow 闭区间边界；真实证据在 CLI 对应 HTTP 响应边界 | 邻日 mock 使同一 03-29 公告真正流过解析与选择，再按各自显式单日闭区间过滤，验证 `seDate` 未扩张；不能恒回空。真实 03-28/03-29/03-30 CLI 各存同次原始 provider 响应 body 字节、SHA-256、窗口、实际 `seDate`、category/page、网络时点和运行对应关系；不可把重序列化 JSON 或另次探针冒充同次原始响应。 |

PR2-F1 的 `bool`/浮点/非 ASCII/越界拒绝、PR2-F2 的选择 owner 停止条件、PR3-F1 的统一非负整数毫秒→固定 UTC+08:00、8 位按毫秒落 `1970-01-01`、历史不迁移与 `seDate` 不扩窗均保持。若必须扩白名单改 selection/storage 合同，或无法在 DTO owner 复用 parser/输出安全诊断，停止相应实施，提交直接代码链与原始响应给总控，不做下游补偿。

## 后续测试与真实 CLI 验收配方（本轮未执行）

1. 在隔离工作区建立并激活 Python 3.11 `.venv`，记录环境来源；运行 `python -m pytest tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py tests/fins/test_cn_download_workflow.py -q`、相关 CN 回归、`python -m pyright dayu/ tests/ utils/`，对实际修改的每个生产文件分别检查 pytest-cov ≥80%。日期 owner 用 UTC 16:00 毫秒边界、跨年、整数/数字字符串、严格日期正反例；告警测试用敏感哨兵断言拒绝、不入候选、固定日志及非 PDF/残缺条目无噪声。发布测试读回 result/event、source meta、manifest 与旧 COMPLETE skip。此处是未来实施门槛，不是本轮测试结果。
2. 三次 `dayu-cli download --ticker 000333 --forms FY` 分别带显式 `--start/--end`：03-28、03-29、03-30 各自同日，并各用全新 `--base`。每次保存 argv、exit、stdout、stderr、日志、`discovered/downloaded/failed`；在同次 HTTP 边界留原始 `hisAnnouncement/query` 响应字节（分页逐份）、SHA-256、窗口/`seDate`、category/page、网络请求与响应时间。人工对照告警和响应，区分真实空页与 DTO 日期拒绝；03-29 应发现并发布目标全文 `1222951181` 且只读仓储 meta/manifest 日期为 `2025-03-29`，两邻日不得发布该 source。若网络、Docling 或原始字节采集失败，明确验收未完成，不以 mock、计划检查或另次探针替代。

本次仅完成计划文本静态核对、源代码与 owner 依赖核对、计划 SHA 与改动范围检查；未建立 `.venv`，未运行 pytest、pyright、coverage 或真实 CLI。后续只有新 SHA 的有效独立审查和总控裁决才能推进实施 gate。
