# S1 Implementation：空公告列表解析修复 + 回归测试

- Gate: `implementation`（slice S1）
- Work unit: 000333 下载时巨潮公告列表格式异常（cninfo-empty-announcement-parse）
- 日期：2026-09-25
- 依据 plan：`docs/gateflow/cninfo-empty-announcement-parse-plan-20260925.md`（§7/§8/§9）

## Objective / Expected outcome

`hisAnnouncement/query` 空结果 `announcements: null` 不再中断 discovery；缺 key / 非 list 非 null 形态维持协议失败。
预期：FY 有候选而 H1/Q1/Q3 为 null 时只产出 FY 候选。

## Changed files

1. `dayu/fins/downloaders/cninfo_downloader.py`
   - `_query_announcements` 分页循环内 `announcements` 解析改为显式三分支：
     - 缺 key → 协议失败（未知契约形态，fail-closed，防空成功伪装）；
     - 值为 `null` → 空页，与 `[]` 同路径 `break`（巨潮空结果编码，与 `totalRecordNum=0` 同现）；
     - 值为 list → 原行为；其它类型 → 协议失败。
   - 模块 docstring 补充空结果编码事实。
   - 未动：`hasMore` 检查位置、翻页逻辑、`_parse_raw_announcement`、selection / workflow / CLI。
2. `tests/fins/test_cninfo_downloader.py`
   - 新增 `test_list_report_candidates_treats_null_announcements_as_empty`。
   - 新增 `test_list_report_candidates_null_empty_period_does_not_block_other_periods`
     （事故回归：FY 两条公告（摘要+正文）+ H1/Q1/Q3 null，断言仅正文 FY2024 候选）。
   - 新增 `test_list_report_candidates_missing_announcements_key_raises`（缺 key → 协议失败）。
   - 新增 `test_list_report_candidates_non_list_announcements_raises`（dict/str 参数化 → 协议失败）。
   - 模块 docstring 覆盖清单补一行。

## Goal alignment

- 空编码归一 / fail-closed：对应 goal 本体与非目标“不把失败改成空成功”。
- 事故回归测试：对应 success signal 的前置证明。

## Decisions（与 plan §7 一致）

- 修复只在 owner boundary（`_query_announcements`）；无下游补偿、无新机制、无诊断增强（deferred）。
- wire 字段名字面量沿用解析器现状内联写法；未做全文件常量化重构。

## Validation

| 检查 | 结果 |
|---|---|
| `pytest tests/fins/test_cninfo_downloader.py -q` | 58 passed |
| `pytest tests/fins -q` | 2124 passed, 1 skipped；1 failed 为 `test_fins_storage_provider.py::test_blob_read_projects_real_socket_io_error_without_private_locator`（沙箱 Seatbelt 禁止 AF_UNIX bind 致 `PermissionError`；**非沙箱复跑通过**，与本次改动无交集，属环境伪失败） |
| `pyright dayu/fins/downloaders/cninfo_downloader.py tests/fins/test_cninfo_downloader.py` | 0 errors, 0 warnings |

## Docs decision

- `dayu/fins/README.md`：按其 `Agent更新约束`（不写实现细节），downloader wire 适配不属其职责 → 不更新。
- `tests/README.md`：未定义更新约束；本次未新增测试层级/命令 → 不机械同步。
- 根 README / `dayu/README.md`：无用户可见变化 → 不更新。

## Residual risks

| 项 | 分类 |
|---|---|
| 巨潮未来省略 `announcements` key 表达空结果 → 再次协议失败（fail-closed 设计使然） | fixed in current slice 的已知残留边界；接受 |
| 空页提前 break 不检查 `hasMore`（`[]`/`null` 同语义，既有行为） | assigned to later work unit（仅当出现矛盾响应证据） |
| 协议失败不记录响应特征 | deferred：需新 issue（owner：Dayu 维护方） |
| `test_blob_read_projects_real_socket_io_error_without_private_locator` 在沙箱内必失败 | 环境限制，非产品缺陷；tracked by 测试运行环境约定（沙箱外验证） |

## Completion status

S1 implementation 完成，进入 code review gate。CLI 复验与元数据核验在 slice review 通过后执行（plan §9）。
