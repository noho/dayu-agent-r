# F5-N03：非空官方 raw 公告证据

## 目的与来源

为消除Sol F5提案“只有官方空fixture不能冒称非空真实公告”的资料gap，根只做两个受控公开GET，不扩生产下载窗口、不爬取历史列表、不读私人语料、不取PDF/HEAD/Docling/仓储写入、不修改现有fixture。复用既有官方0700协议capture的stockId7609及其它固定参数，分类按生产季度结果request：t1code10000/t2Gcode3/t2code-2；分别精确单日20250319／20251113。scope及响应股票字段用真实严格owner复核，不靠stockId猜公司。

请求使用当前venv httpx、25秒每次上限、trust_env=False、无cookies/auth/代理credentials及headers保留。端点https://www1.hkexnews.hk/search/titleSearchServlet.do。托管67799 outer0，两次200，年度结果2rows／季度1row，无累计下一页，原body bytes与完整JSON envelope在workspace/tmp/pr197-controller-collection-20261001/f5-official-raw-capture/，各captured_at_utc由系统时钟生成。

| 捕获 | 请求日期 | 原响应SHA256 | 原始内容概览 |
| --- | --- | --- | --- |
| annual-results | 2025-03-19单日 | 62582cfbfa1aaeb588971f339bbbb33767420528718b916877d0e05d0c6cb94a | 一份年度末期股息、一份截至2024-12-31全年业绩公告；不把股息公告当年度财期证据 |
| quarter-results | 2025-11-13单日 | 0d6bbb3ba351b9a8cdd1966dea75234efb9dbfdb686fba89a289cd5924b59f32 | 截至2025-09-30三个月及九个月业绩公告 |

根亲调用当前生产_parse_title_search_snapshot、_parse_announcement、_announcement_matches_stock，验证完整累计协议exact字段类型、raw解析非None、每row STOCK_CODE=00700或含00700的多代码字段、原bytes↔UTF8全文↔SHA逐字对应。owner-validation.json保存全部实际观察；原raw没有任何标题/日期/ID/URL改写。不等于未来F5完整方案或publication验收。

## 失败、恢复及证据限制

第一次根owner-validation命令exit1：不当地预设官方三个月及九个月标题“无annual必None”。实际生产resolver把该标题直接确定为Q3，所以该预设断言错。已保留工具失败，恢复时不修改raw／代码／假fixture，而是重新严格验证并如实记录：无anchor与有官方年度anchor均为2025/Q3/coverage[Q3]；年度日期2024-12-31、季度截止2025-09-30。此官方例是明确季度正例，不是窄窗口缺anchor反例，不能声称实测它原来不确定。原长度型“三个月”合成反例已由根生产resolver独立复现，仍单独标合成；后续基于真实raw调整标题的变体也必须明确合成，不篡改capture provenance。

## N03裁决与下一用途

**资料gap已补证：非空原始年度/季度official body存在且运输解析owner可复核。** 不是产品finding已修，不把官方capture当语义未知的真实案例，也不新增必须更多历史爬取的验收。后续F5 accepted plan实施时可把这两原始envelope/body按不变hash纳入获授权测试fixture，保留请求scope/provenance；真实受控Fs及明确合成标题变体证明未知/冲突/窄宽/删除/损坏等owner行为。当前不写tests新fixture、不更新README、不改F5尚未裁Q1方案。

F5新公开行为仍待用户Q1，N01/N02源码未修，proposal需Sol固化和同版双审；Q2/Q3根原goal技术判断保持。root不以资料补齐绕过plan gate或替换Docling职责。
