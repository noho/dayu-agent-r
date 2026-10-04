# CNInfo 单日发现：中国本地披露日实施计划

- Gate：PR4-F1～F4 修订后 plan 候选，待新 SHA 的同版独立 plan review；本文不代表代码已实施或验收通过。
- 工作区：`/private/tmp/dayu-cninfo-single-day`；分支 `codex/cninfo-single-day`；核查基线 HEAD `9735800cb55a40336469593fa2fddae43c9c69ad`。
- 决策真源：`fins-cninfo-single-day-goal-20260929.md` 和 `fins-cninfo-single-day-plan-adjudication-20260929.md` 中用户已确认的“中国本地披露日；历史另议”及 PR4-F1～F4 裁决。`fins-cninfo-single-day-plan-local-day-fix-20260929.md` 列出逐层验收矩阵；本计划的 PR4 验收细化优先于该旧矩阵中较宽泛的文字。

## 动机和根因

主工作区只读证据 `issue-198-s1-cninfo-single-day-evidence-20260929.md` 记录 000333/FY 在 `2025-03-28~2025-03-28` 的 provider 零结果；隔离工作区旧计划中的真实 provider 矩阵补证：`2025-03-29~2025-03-29` 相等端点返回 `1222951198` 和 `1222951181`，两者 `announcementTime=1743177600000`，即 `2025-03-28T16:00:00Z = 2025-03-29T00:00:00+08:00`。因此“provider 拒绝相等端点，应扩窗”的旧动机被直接反证，不能用于实施。

当前 `cninfo_downloader._query_announcement_page` 原样发送 `seDate=start~end`；`_parse_raw_announcement` 调用 `_format_announcement_date`，后者对毫秒数值和数字字符串都用 `time.gmtime` 取 UTC 日期。CNInfo DTO 因而把上述中国本地 03-29 公告写成 03-28。公开查询和 provider 用中国本地日历，DTO 却用 UTC 日历；这一同源差异解释了 03-29 单日候选被后续闭区间排除的风险。证据仅覆盖这个 ticker、财期和日期，不推断所有 provider 日期行为。

## 语义 owner 和不变式

1. **输入边界**：`dayu/fins/downloaders/cninfo_downloader.py` 的 CNInfo 原始公告 DTO 解析唯一产生 `CninfoRawAnnouncement.announcement_date`。数值输入只接受非 `bool` 的可表示非负整数；数字字符串只接受无符号、无空白且逐字符属于 ASCII `[0-9]` 的纯十进制字符串。两者不按位数分支，共用整数毫秒转换：以 UTC epoch 加整数毫秒，再按固定中国 UTC+08:00 投影成 `YYYY-MM-DD`，不得先转浮点或读取宿主本地时区。普通日期字符串只有**原文精确为 ASCII `YYYY-MM-DD` 且该公历日期实际存在**时才原样返回；DTO 日期 owner 直接复用 `dayu.fins.domain.filing_semantics.parse_iso_calendar_date` 的严格日历校验（该 domain 模块只依赖公共契约，不反向依赖 downloader），捕获该校验的 `ValueError` 后返回 `None`，不先 `strip()`、不另写宽松正则或另建日期规则。`bool`、浮点、负号、非 ASCII 数字、非整数、日期转换不可表示的越界值，以及 `2025-02-30`、`2025-13-45`、`0000-01-01`、首尾空白、全角日期文本均返回 `None`，沿 `_parse_raw_announcement` 既有 DTO 丢弃路径处理，不在下游猜测或补偿。当前实测 provider 的 `announcementTime` 是 13 位 JSON 整数，现有历史测试的普通日期字符串是夹具；没有 compact `YYYYMMDD` 协议证据。8 位 `20250328` 无论作为整数还是 ASCII 数字字符串，在此协议下都是 epoch 毫秒值，投影为 `1970-01-01`，明确不表示 compact 日期支持。若真实目标公告出现与统一 epoch 毫秒解释冲突的形态，先以原始 provider 证据停止并裁决协议与 DTO owner，不在 DTO 加长度或年份 heuristic。不得按 URL 路径、当前日期或样本日期推断，也不设置任意合理年份阈值。
2. **拒绝诊断 owner**：仍由同一 CNInfo DTO 解析边界负责。先确认原始条目是 PDF，且 `secCode`、`announcementId`、清洗后的 `announcementTitle`、`adjunctUrl` 均按 DTO 必需字段规则非空；告警资格检查还须排除原始字段缺失或显式 `null` 被 `str()` 变成非空文本 `"None"` 的情形。仅这类其它必需字段完整的 PDF 因 `announcementTime` 缺失或不满足上述日期合同而被拒绝时，记录固定 `Log.warn` 正文「巨潮 PDF 公告时间不符合日期合同，已跳过」。正文及固定模块标签不得插入原始响应、字段值、凭据、公告 ID、标题、URL、ticker、时间值、类型或长度；不记录整个 payload。非 PDF 或其它必需字段残缺的条目沿原有静默丢弃路径，不触发该日期告警；成功解析也不告警。告警只给 operator 可观察信号，**不会自动中止任务或将该条升级为 provider typed failure**；`discovered=0` 与无公告仍需结合告警和受控留存的原始 provider 响应，由人工判断是否协议漂移并决定暂停、提交总控裁决。合法但可疑的 8 位整数毫秒不会触发拒绝告警，也必须在真实原始响应审查中判定其协议含义。
3. **请求与选择**：本 WU 只覆盖显式 `start_date/end_date`，其 `seDate` 继续是用户闭区间，保持原样，不增加天数。`select_cninfo_report_candidates` 从同一个 DTO 日期推断财年、同财期/财年择优并赋予 `CnReportCandidate.filing_date`；`cn_download_workflow._select_candidates_for_a4` 按这个 `filing_date` 做闭区间筛选。03-29 内的摘要/全文应择全文，03-28 和 03-30 邻日不能误入。当前选择先择优后按窗口过滤；若真实 provider 在单日响应中返回邻日同财年/财期候选并盖过窗口内候选，应停下核实选择 owner 和改动范围，不能用日期 DTO 修复掩盖。缺省窗口是独立残余：`cn_form_utils.resolve_window` 的 `today=None` 现取宿主 `date.today()`，其 docstring 却写 UTC，可能与中国本地日不同；另立 `fins-cninfo-default-window-local-day` WU 裁决窗口 owner、锚点日期及 docstring，本 WU 不改缺省窗口。
4. **身份与发布**：`resolve_cn_download_ids` / `build_cn_filing_ids` 使用财年、财期和修订状态，不直接使用 `filing_date`；但 `cn_report_selection._infer_cninfo_fiscal_year` 在标题缺年份时回退到公告日期的年份，跨年修正可能改变财年及 ID。`cn_download_source_upsert._build_base_meta` 从候选写 source meta 的 `filing_date`，storage 的 `FilingManifestItem.from_source_meta` 再生成 manifest，同一日期必须贯穿事件/结果、meta、manifest 和仓储读回；禁止在 CLI、adapter、storage 或显示层重算日期。
5. **历史边界**：已 COMPLETE 且未指定 overwrite 的来源在 `cn_download_filing_workflow` 以 `integrity_complete` 跳过；新解析器不会自动改写旧 source meta/manifest。当前只修新发现/新下载，不借 overwrite、rebuild 或测试预置数据静默迁移历史。历史 source 的日期、可能受影响的财年/ID/版本/manifest 另立核查或 migration work unit。

## 改动白名单和实施顺序

| 顺序 | 允许修改的路径 | 具体动作与边界 |
| --- | --- | --- |
| 1 | `dayu/fins/downloaders/cninfo_downloader.py` | 只在 CNInfo `announcementTime` → DTO 日期 owner 修改 `_format_announcement_date`、`_parse_raw_announcement` 及必要的模块级常量/私有辅助函数。用显式 UTC 与固定 UTC+08:00 做毫秒时间戳转换；整数与数字字符串共用一个转换路径；日期文本直接调用 domain 严格日历 parser 验证后原样返回。PDF 与其它必需字段完整性检查先于日期拒绝告警，在 owner 写固定脱敏 `Log.warn`，不改变拒绝或请求策略。补齐中文 docstring 的参数、返回值、异常说明。不得触碰 `seDate`、其它 provider 或下载/发布策略。 |
| 2 | `tests/fins/test_cninfo_downloader.py` | 以真实 JSON 形态的整数、数字字符串和普通日期字符串测 DTO → candidate；断言严格日期字符串、非法日期/空白/全角拒绝，完整 PDF 的时间拒绝有且仅有固定安全告警，非 PDF/其它字段残缺无该告警，拒绝项不入候选。断言原样 `seDate`。现有 UTC 午夜用例若两种规则同日，保留其值并补语义说明；区分力由新增 UTC 16:00 边界用例提供。 |
| 3 | `tests/fins/test_cn_report_selection.py`、`tests/fins/test_cn_download_workflow.py` | 前者锁标题有/无年份的财年与择优结果；后者通过真实 DTO/selection/identity/storage 边界测试闭区间、文档 ID、source meta 与 manifest 同源，以及旧 COMPLETE 来源未自动改写。邻日 mock 均让同一 03-29 公告通过 DTO/selection 到闭区间过滤，不能恒回空。测试可隔离 HTTP/PDF/Docling 外部依赖，但不能伪造 DTO 日期或用 fake 的候选替代需要验证的解析链。 |
| 条件触发 | `dayu/fins/README.md`、`tests/README.md`、根 `README.md` | 仅按各 README 的 `Agent更新约束` 和职责范围更新：若实现后的 CNInfo 日期合同属 Fins 稳定能力，更新 Fins 手册；新增测试层级或维护约定才更新测试手册；用户可见 CLI 用法、工作流或排障说明实际变化才更新根手册。先读约束，不机械同步未来计划。 |

计划内不修改 goal、裁决文档、`#198` S1 typed failure、HKEX/SEC/Docling、公共 schema、CLI 展示层、storage 合同或缺省窗口 owner。若测试揭示必须修改白名单外 owner，先停下并说明直接证据与新的所有权裁决，不能临时补下游分支。

## 验收测试与执行门槛

- **日期与诊断 owner**：UTC `15:59:59.999` 与 `16:00:00.000` 对应中国当日 `23:59:59.999` / 次日 `00:00:00.000`；覆盖 03-29 样本和 `12-31 → 01-01` 跨年。每个边界分别用非 `bool` 整数和 ASCII 纯十进制数字字符串；有效普通 ASCII `YYYY-MM-DD` 原样保留，`2025-02-30`、`2025-13-45`、`0000-01-01`、首尾空白及全角数字日期文本均拒绝。断言可表示的 8 位 `20250328` 整数/字符串均按 epoch 毫秒投影为 `1970-01-01`，不当作 compact `YYYYMMDD`。断言 `True`、浮点毫秒、负值或带符号字符串、非 ASCII 数字、非整数及不可表示的越界值返回 `None` 并由 DTO 丢弃。对其它必需字段完整的 PDF，逐一覆盖缺失/畸形时间拒绝：不入候选且产生准确、固定、无原始值和凭据的告警；给原始字段填入敏感哨兵并断言日志不包含它。非 PDF、其它必需字段缺失或合法时间不产生该日期告警；告警不改变任务终态。断言与宿主时区无关，不加入位数特判或任意年份阈值。
- **选择/身份 owner**：模拟 provider 对 `seDate=2025-03-29~2025-03-29` 返回原样时间戳公告，断言 03-29 单日有全文候选 `1222951181`、`filing_date=2025-03-29`。对 03-28/03-30 邻日测试，让同一条 03-29 原始公告在每个显式单日请求中通过真实 DTO → selection，再由 workflow 的闭区间规则排除；同时检查请求 `seDate` 恰为各自原窗口，不用恒空 mock 制造空转通过。此合成反例只检验本地过滤，不声称真实 provider 会在邻日返回该公告；跨年标题显式年份维持标题财年，标题缺年份按披露日历年份推断财年并核对由此分配的 ID。不为窗口外同组候选压制窗口内候选的现有顺序写期望断言；真实 provider 若返回这类竞争者，按上述停止条件另行裁决 selection owner，本项不改算法。
- **发布 owner**：在隔离仓储运行一条从 provider JSON/DTO 经 selection、workflow、`resolve_cn_download_ids` 到 source commit 的测试，读回 result/event、source meta、`filing_manifest.json`，比较同一 `filing_date`、财年及 ID；再用旧 COMPLETE source 验证无 overwrite 时 source meta/manifest 字节或规范投影不变。测试读取遵循 storage 仓储协议，manifest 原始文件仅用于核对发布投影。
- **环境和本地门槛**：当前隔离工作区没有 `.venv`。实施前先准备本工作区可激活的 Python 3.11 `.venv`，记录来源与命令；`source .venv/bin/activate` 后运行 `python -m pytest tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py tests/fins/test_cn_download_workflow.py -q` 及相关 CN 下载回归，再运行 `python -m pyright dayu/ tests/ utils/`。用 pytest-cov 对每个实际修改的生产 `.py` 文件分别采集并记录 coverage，目标 ≥80%；不足则补 owner 行为测试。不得以主工作区解释器或本轮文档检查冒充隔离工作区通过。
- **真实隔离 CLI**：三个各自全新的临时 `--base`，固定显式 `--start/--end` 分别为 `2025-03-28~2025-03-28`、`2025-03-29~2025-03-29`、`2025-03-30~2025-03-30`，其余 argv 均为 `dayu-cli download --ticker 000333 --forms FY`；逐次保存完整 argv、exit、stdout、stderr、日志与 `discovered/downloaded/failed`。在 HTTP 响应边界受控留存这三次真实 `hisAnnouncement/query` 响应的**原始 body 字节**（若有分页，每页另存），逐份记 SHA-256、显式窗口、实际 `seDate`、category/page、网络请求/响应时间及 CLI 运行对应关系；不得把 JSON 重序列化文本冒充原始字节，也不得把另一次只读探针伪称 CLI 的响应。查看每次是否出现上述固定日期告警，结合原始响应区分真实空结果与 DTO 拒绝；WARN 只触发人工审查，不自动停工。03-29 须发现并发布目标全文，通过 `FsSourceDocumentRepository` 只读获取 source ID、完整性、meta、primary file，并核对 manifest 中 `filing_date=2025-03-29`；03-28 与 03-30 不得发布该 source。若拿不到同次原始响应、真实 provider/Docling 不可用，保留已获证据并明确 CLI 验收未完成，不能用 mock 或计划检查宣称真实 CLI 验收成功，也不重复写入既有工作区。

## 依赖、停止条件与后续 gate

修订 goal、用户日期裁决、当前代码和原始 provider 响应必须一致；实施前需可用的隔离 Python 环境和受控真实 CNInfo/Docling 路由。若复核发现 goal 与代码/原始响应冲突、真实目标公告的原始时间形态或其 provider 日历归属与统一 epoch 毫秒解释冲突、DTO 日期并非唯一 owner、domain 严格日历 parser 无法在 DTO owner 合理复用、固定中国本地日历或固定脱敏诊断无法在 owner 处表达，或实现必须扩白名单修改 selection/storage 合同、在展示层补偿/静默改写历史 source，立即停止相应实施并提交直接代码链与原始 provider 证据供总控裁决；不能在 DTO 用位数或日期外观 heuristic 猜 compact 日期。固定 WARN 是人工核查线索，不是自动停止机制；operator 应据同次原始响应判定协议漂移并决定暂停、升级，不能单凭 `discovered=0` 或 WARN 自动推断协议。provider 变化或真实 CLI 外部故障只记录为验收阻塞，不能扩大 `seDate` 或跳过验收。缺省窗口锚点另由 `fins-cninfo-default-window-local-day` WU 裁决，本 WU 只以显式日期验收。

同版计划经独立 plan review 裁决后才实施；完成 owner 测试、逐文件 coverage、pyright、README 判断和真实隔离 CLI 读回后再进入代码 review。历史数据核查/迁移单独立项；不发 CNInfo issue，不 commit、push、PR 或 merge。
