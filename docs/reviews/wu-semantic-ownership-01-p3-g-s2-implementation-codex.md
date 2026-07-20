# WU-SEMANTIC-OWNERSHIP-01 P3-G S2 Implementation - AgentCodex

## 状态

- Completion state: `ready-for-code-review`
- Slice: S2 - CN/HK report candidate classification and fiscal inference ownership
- 本轮只实现 S2；未修改 S3 typed SEC rejection registry，未修改 S4 XBRL `total` contract，未 commit。

## 动机校验

动机成立。S2 前 CNInfo / HKEXNews downloader 同时承担 HTTP adapter 与财报产品语义：title blocklist、语言过滤、财期/财年推断、同 period/year 去重、amended 优先和 `CnReportCandidate` 构造都在 downloader 内。HTTP adapter 是 provider raw 字段与网络边界，不应拥有“哪份公告是财报正本”的业务真源；该语义应在 pipeline helper 中统一持有并由 workflow 消费。

## 文件变更

- 新增：
  - `dayu/fins/pipelines/cn_report_selection.py`
  - `tests/fins/test_cn_report_selection.py`
- 修改：
  - `dayu/fins/pipelines/cn_download_models.py`
  - `dayu/fins/downloaders/cninfo_downloader.py`
  - `dayu/fins/downloaders/hkexnews_downloader.py`
  - `dayu/fins/README.md`
  - `tests/README.md`

未触碰 handoff 列出的无关 untracked 文件。

## Source Finding Coverage

- AgentMiMo BI-1 / downloader-owned financial-report filtering and fiscal inference：已在 S2 内处理 CNInfo/HKEXNews。新增 `dayu.fins.pipelines.cn_report_selection`，下载器只做 provider raw announcement 拉取、provider raw 字段归一、股票代码匹配、PDF URL 归一和 HEAD/GET HTTP 边界；产品级候选筛选和 `CnReportCandidate` 构造迁入 pipeline helper。
- S2 非目标保持：未触碰 SEC rejection registry；未触碰 XBRL `total` contract；未修改 S1 SEC form parser。

## Owner Boundary 与传播审计

- first producer：CNInfo/HKEXNews HTTP endpoint 返回 provider raw announcement JSON。
- raw adapter owner：`cninfo_downloader.py` / `hkexnews_downloader.py`。
  - 保留 HTTP 请求/响应、JSON decode、provider 字段解析、provider URL 构造、stock/company id 查询、PDF HEAD/GET 与 PDF bytes 校验。
  - 新增/消费 raw DTO：`CninfoRawAnnouncement`、`HkexnewsRawAnnouncement`、`CnReportHeadMeta`。
- business selection owner：`dayu.fins.pipelines.cn_report_selection`。
  - CNInfo：title blocklist、英文/摘要/公告类排除、fiscal year 推断、同 period/year 分组、amended 优先、candidate 构造。
  - HKEXNews：英文副本过滤、fiscal period/year 推断、同 period/year 分组、amended 优先、candidate 构造。
  - HEAD 读取仍由 downloader 通过 `Callable[[str], CnReportHeadMeta]` 提供；这是为了保留 HTTP owner，同时让 candidate construction 发生在 pipeline helper。
- workflow consumer：`CnReportDiscoveryClientProtocol.list_report_candidates(...)` 仍作为既有 workflow contract 存在；具体 downloader 的实现变为 raw fetch + pipeline helper selection，不在 downloader 内重建业务筛选真源。
- persistence/projection：`CnReportCandidate` 后续仍进入 CN/HK download workflow、source/blob commit、source meta 和 direct stream summary；字段语义由 pipeline helper 统一产生。

## 行为变化

- 用户可见候选选择行为保持不变；现有 CNInfo/HKEXNews downloader、workflow、pipeline 测试通过。
- 下载器模块顶层文档与 README 已同步：下载器不是 report selection owner。
- `CnReportCandidate` 构造从 downloader 私有方法迁入 `cn_report_selection.py`。

## 测试迁移 / Assertion Mapping

- 新增 `tests/fins/test_cn_report_selection.py`，以无 HTTP mock 的纯 helper 测试覆盖迁移后的业务断言：
  - `test_cninfo_selection_filters_blocklisted_titles_and_builds_candidate`：对应原 CNInfo downloader 中 title blocklist / candidate 字段断言。
  - `test_cninfo_selection_keeps_years_and_prefers_amended_per_year`：对应原 CNInfo downloader 中 amended 优先与不同 fiscal year 保留断言。
  - `test_hkexnews_selection_filters_english_and_infers_periods`：对应原 HKEXNews downloader 中英文过滤、FY/Q2 财期推断与 candidate 构造断言。
  - `test_hkexnews_selection_groups_by_year_and_prefers_amended`：对应原 HKEXNews downloader 中同 period/year amended 优先断言。
- 既有 downloader tests 保留为 concrete `list_report_candidates(...)` wrapper integration coverage，用于证明 raw HTTP adapter + pipeline helper 组合后仍保持原用户可见行为；纯业务 owner 断言已在新 helper tests 中覆盖。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py -q`
  - 结果：`76 passed`
- `source .venv/bin/activate && pytest tests/fins/test_cn_report_selection.py --cov=dayu.fins.pipelines.cn_report_selection --cov-fail-under=80 -q`
  - 结果：`4 passed`
  - `dayu/fins/pipelines/cn_report_selection.py` coverage：84%，满足 80%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && rg -n "def _infer_fiscal_year|def _infer_fiscal_period_from_text|_is_title_blocked|_looks_like_english_report_text" dayu/fins/downloaders dayu/fins/pipelines`
  - 结果：仅 `dayu/fins/pipelines/cn_report_selection.py` 命中：
    - `_is_title_blocked` 调用与定义；
    - `_infer_fiscal_period_from_text` 定义；
    - `_looks_like_english_report_text` 调用与定义。
- `git diff --check`
  - 结果：通过，无输出。

## Source Scan Classification

- `dayu/fins/pipelines/cn_report_selection.py` 命中均为 S2 迁移后的 owner 真源，属于预期 pipeline helper match。
- `dayu/fins/downloaders/` 无 `_infer_fiscal_year`、`_infer_fiscal_period_from_text`、`_is_title_blocked`、`_looks_like_english_report_text` 命中。

## README 决策

- 已阅读 `dayu/fins/README.md` Agent 更新约束。S2 改变了当前已实现的 Fins 稳定 owner boundary，因此更新 `dayu/fins/README.md`，新增 Downloaders 与 CN/HK report selection 边界说明。
- 已阅读 `tests/README.md`。本轮新增 `tests/fins/test_cn_report_selection.py` 并调整测试职责描述，因此更新 `tests/README.md` 中 Fins 测试覆盖说明。

## 残余风险 / Deferred

- `CnReportDiscoveryClientProtocol.list_report_candidates(...)` 为保持 workflow 稳定仍返回 `CnReportCandidate`；具体 downloader 实现内部委托 pipeline helper。若后续要把 protocol 本身改成 raw discovery contract，应作为单独 breaking-contract slice 处理。
- CNInfo/HKEXNews 具体 provider category 参数仍在 downloader 内，因为这是 HTTP adapter 请求构造事实；产品级筛选和 fiscal inference 已迁出。
- 新 helper 通过 callback 读取 HEAD meta，这是刻意保留 HTTP owner 的窄边界，不是第二份候选选择真源。
