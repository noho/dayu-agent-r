# D1 数量诊断条件修复

## 当前 gate 与新增授权

current gate / next entry point：ready-to-open-draft-PR → 必要提交 / push → create draft PR → 总控交付核对。

这是提交前的已审版本记录；精确PR/OID、远端diff/checks、最终放行与closeout以后续本地 `workspace/tmp/tsm-6k-20261022/d1/delivery-closeout.md` 为准，未创建PR前不宣布draft-PR-pass。

用户已核收 [调查及停报](tsm-6k-rejection-20261022-adjudication.md) 的限定结论，明确 D1 纳入当前同一 work unit：原“正确拒绝后停止”对过滤调查已满足，继续独立的 D1 最小修复。当前基线 commit `26ed15b91fc3ee81d5c6cde4dbd0a4fa709d2536`，分支 `investigation/tsm-6k-20261022`；既有 dirty 全是本单元调查/审核文档，ownership 清楚，保留。

成功信号：同源拒绝行有效数=0、rejected=1；真正完整缓存跳过仍有效；真实有效2+拒绝1不能掩盖不足警告。数量诊断必须复用确认 disposition 的统一投影，不在 warning/CLI 按文件或原因码补特判；不扩展日志清理、6-K 保留政策或框架。

按 gpt-6-sol plan/writer/fix、mimo-flash 与 ds-flash 并行独立审核推进；DS 明确使用 Codex runtime，既有 Claude 403 失败保留。包版本升 `0.1.6`，修复、回归/pyright、审核和同一 draft PR 交付自动推进。live 安装仍需核收后明确 sync to live；merge 另授权。

## 根因与 owner 核对起点

`sec_download_diagnostics.warn_insufficient_filings` 对 raw `status=skipped` 直接计数，把 filtered rejected 算入有效数；正常 workflow summary 和 public typed row 已有 rejected 语义投影，但判定在 `sec_download_workflow` / `sec_pipeline` 重复，warning 未复用。正确 owner 是 SEC 已确认 filing disposition；数量 warning、workflow summary、public row 都应消费同一投影。

建议最小方向：将现有 disposition 判定收束为层内窄投影 helper（朴素显式参数、返回现有 enum），正常/取消快照、typed row、数量诊断复用；不引入新的状态框架或改变字段/公开原因。提议须由 gpt-6-sol 用当前调用链核实，主控检查后实施。

## 证据复用与条件验证

既有附件/输入/保留规则调查仍有效：这轮不改 downloader、6-K 规则、候选提取、拒绝发布或存储 schema。历史 GET 不可恢复的限制继续保留。

D1 直接反例为 `workspace/tmp/tsm-6k-20261022/s1/diagnostic-proof-configured/` 的 quantity-warning-observation / finding-verification；总控无注入 CLI 在 `controller/clean-cli/`。旧回归通过仅作基线，不充当修复验证。

需要新跑 owner 级计数正反例、真实 pipeline/typed summary 一致性与受影响失败/取消快照；修后对保存响应做严格离线 D1 补证（不改历史证据、不再联网也可），断言有效数0、rejected1。全量 pyright、必要包 metadata/wheel 版本验证；构建不安装。按职责检查 Fins / tests README；用户排障行为确有变化时按根 README 边界处理，禁止写治理流水账。

调查版本原件、raw 输入和旧警告证据只读；新修复验证放 `workspace/tmp/tsm-6k-20261022/d1/`。临时脚本仅 workspace/tmp；分析辅助代码仅 utils（本次不需新增通用工具）。

## 风险与下一入口

- D1 尚未修复：fixed in current slice（当前已授权 slice 待完成），owner SEC disposition / diagnostics；destination 本次实现和新验证。
- 取消/中止快照有独立 raw 计数路径：同一语义受影响面，需计划说明与同源投影验证，不作为无关扩展。
- 旧调查断言不得外推为修复通过；writer 新命令/退出/被测版本需单独保存。
- 不同包安装或 live 行为：covered by later approved slice，仅收到明确 sync to live 后执行；当前只交付0.1.6源码/wheel证据。

## Plan 核对通过

gpt-6-sol 计划为 [D1计划](tsm-6k-rejection-20261023-d1-plan.md)，runner 外层/runtime 均退出0，持久 session `01a16465-c5aa-7552-897e-9ef0abe09fcd`；实际日志 `controller/D1-plan.jsonl` / stderr。已读完整结果和计划，owner/分层/单slice/三个成功信号及取消失败受影响验证足够。

采用窄 `project_sec_filing_disposition`，返回已有 enum，三个消费者复用；删除重复判定，取消事件复用既有正常 builder。不改变raw字段、公共原因/locator、发布/存储或6-K筛选；只改包声明至0.1.6，不刷新download认证版本。无重要公共契约、架构、迁移或状态机决策，无独立planreview适用条件，主控核对放行。

实施 binding 修正：离线复现取权威 `s1/pipeline-clean-requests`，不取早期失败探针的请求目录；wheel 在隔离源码副本中构建，优先复用现有 package entrypoints测试的构建产物，不在checkout构建以免污染源码/metadata。保留实际wheel并校验0.1.6及改动源码字节，不安装；新验证不得写旧s1/controller业务证据。覆盖率优先验证新owner和改变分支，按计划检查四个生产文件>=80%目标，不为追数引入无关产品改动。

## 实施收集与主控补查

gpt-6-sol 实施 runner 已实际退出0，同一持久session；完整日志 `controller/D1-implementation.jsonl` / stderr，报告 [D1实施](tsm-6k-rejection-20261023-d1-implementation.md)。新328项受影响回归、10项最终边界、4项包入口通过，全量pyright841文件零错误。去除默认Protocol空体排除的最终覆盖率四文件100%/98.33%/86.17%/89.08%。产品10文件当前字节与 `d1/source-snapshot` 和manifest逐一核对一致；生产四文件与隔离副本/0.1.6 wheel一致。主控已走读投影及三个消费者，取消docstring修正已包含，暂无产品finding。

实施gate暂未放行：主控显式包含四个D1临时脚本运行pyright（默认全量exclude workspace），`d1/commands/scripts-pyright` 真实退出1、Found4/error1，`verify_offline.py:188` 的 `list[str]` 与 JsonValue 可变列表类型不匹配。已交同一 gpt-6-sol session 窄修复脚本类型、显式四脚本检查、新fresh base离线重跑及报告更新，保存旧失败；不修改产品源码，不重复无影响产品回归/wheel。范围内缺陷由当前slice修复，不需用户裁决。下一入口仍为完成 implementation/validation，再并行MiMo/DS Codex完整审核。

上述补查现已完成：gpt-6-sol 窄修复 runner 外层/runtime退出0，`controller/D1-script-fix.jsonl` / stderr；四脚本严格JSON列表构造修正，`scripts-pyright-final` 实际分析4文件、错误0、退出0。`offline-final` fresh base真实退出0，10/10请求消费、有效0/rejected1/active0、原件hash不变；四脚本副本/hash在 `d1/script-snapshot-final/manifest.json`。主控已核对产品十文件未变，原新回归/覆盖率/wheel仍适用；调用方manifest13文件大小/SHA再核对全部一致（`d1/controller-original-manifest-verification.json`）。实施gate通过，进入完整代码审核，无accepted未修产品finding、无范围blocker；不以runner退出或作者自报替代后续独立判断。

## 完整双路审核裁决

两个runner均实际退出0。DS-flash Codex session `01a1647d-a5d2-71d0-a4d8-af98d32a3c66`，报告 [DS完整审核](../reviews/code-review-20261023-004540.md)，独立聚焦44项通过；MiMo-flash Claude session `7fa631db-e7db-4ea3-a8c2-1b44f0484f96`，报告 [MiMo完整审核](../reviews/code-review-20261023-005556.md)，独立46项通过。日志 `controller/D1-review-ds-codex` / `D1-review-mimo` 的jsonl/stderr。DS历史Claude403失败仍保留，未改写为审核成功；本轮DS遵用户指令使用Codex。

两路均确认D1三个成功信号、失败/取消/中止、存储与版本目标成立。MiMo未发现实质问题；DS发现低严重度确认行原因校验缺口。总控裁决 DS Finding1 为 **accepted / 未修复**：当前内置生产者不会触发，但缺因skipped先在数量诊断算有效、后被typed拒绝；冲突原因能投影出REJECTED却公开完整缓存成功原因，是直接可复现的不一致。修在新disposition输入校验owner，要求skipped至少一个非空原因、两者均有时规范化文本一致；保留单原因入口和所有合法既有行。这是本轮统一投影的严格非法输入边界修复，非新保留政策或泛化框架，不将其冒称历史事故。已交gpt-6-sol修复，产品重新变化后需新覆盖率/必要回归/全量pyright/离线/wheel和双路受影响面复审，旧wheel与pass不得替代新版。

DS对 `raw_fields_preserved` 标签的证据限制由主控补齐：`d1/controller-raw-row-comparison.json` 对修前保存的数量反例与修后offline-final的同一确认行10字段做完整相等断言，全部相等。分类为fixed in current slice；此断言仍只覆盖当前保存响应，不复原历史输入。

MiMo列的XBRL raw判断与workflow流程控制宽松status均为未修改的既有路径，当前合法生产行下等价，无证据显示本单元行为错误，裁决 **deferred-with-owner** 到后续确实触碰相应政策/分支的work unit（owner SEC diagnostics/workflow；assigned to later work unit）。当前用户明确禁止无关日志清理，不能为假设未来状态扩围；将来扩展到其它拒绝表单时需重新评估，不在本轮制造issue或改实现。typed raw分支保持原原因字段契约属于已核对不变式，不是待修finding。历史GET限制沿已核收边界，live/merge继续等待明确授权。

## Finding 1 修复收集

gpt-6-sol 同一session修复runner已实际退出0，日志 `controller/D1-owner-fix.jsonl` / stderr；[修复报告](tsm-6k-rejection-20261023-d1-owner-fix.md) 和 `d1/fix-owner/` 保存新真实快照/命令/结果。相对完整审核版仅owner、owner测试与两份README四文件变化，三个消费者与合法行规则不变。新345项回归、4项包入口、全量pyright841文件/四脚本显式检查均退出0；无排除覆盖率100%/98.33%/86.17%/89.51%。新离线10/10请求消费有效0/rejected1/active0、原件hash一致；主控完整raw十字段比较与修前反例相同（`fix-owner/controller-raw-row-comparison.json`）。新wheel SHA256 `069929799b54dfcbfcb9427102f06dd153f2311a56306e4aa26ef0f8d748bccc` 与当前四生产文件一致，未安装。

作者修复证据足以进入复审；Finding1在独立复审确认前不宣布最终已修复/pass。复审只覆盖上述增量与三个消费者影响，未变调查/合法流程/存储事实复用上一轮的可取回快照和实质审核；禁止机械重开历史GET/全窗调查或无关框架。下一入口为双路受影响面re-review，完成后总控裁决并推进draft PR。

## 复审最终裁决与提交前核对

双路受影响面复审已实际退出0：DS Codex [复审报告](../reviews/code-review-20261023-010744.md)，独立51项owner测试通过；MiMo [复审报告](../reviews/code-review-20261023-011132.md)，首次因reviewer basetemp父目录缺失setup失败，建目录后真实退出0、56项通过，失败记录保留。两者均确认Finding1已修复、无新实质问题。日志 `controller/D1-rereview-ds-codex` / `D1-rereview-mimo` 的jsonl/stderr。总控已完整阅读并核对直接owner分支、同一非法行三消费者同错、合法行/三个成功信号、新源码快照与验证适用性，裁决 **DS Finding1：accepted / 已修复**；原D1数量误计本身为 **accepted / 已修复**，不遗留accepted未修项。

完整审核+必要修复/双路复审通过，当前无blocker/needs-more-evidence。新345项回归与包4项、841文件pyright及4脚本显式pyright、四文件>=80%无排除coverage、严格离线及新wheel证据对当前最终十文件hash一致，mandatory checks满足。README决定完成。主控补证完整raw十字段相等已被MiMo复审核对。安装查询 `d1/commands/installed-query-final` 实际退出0，调查`.venv`分发metadata仍0.1.5，位置 `.venv/lib/python3.11/site-packages`，模块editable来自当前checkout；明确不把源码/wheel0.1.6冒称live已安装。

风险最终分类：既有XBRL/流程控制维护隐患维持上述deferred-with-owner / assigned to later work unit；非法skipped提前硬失败是严格owner契约的预期（当前生产者不产生），归owner生产者后续变更时评估，不构成当前缺陷；历史GET不可恢复为已核收证据上限，future远端变化由来源owner重新取证；live/merge为requiring explicit user decision，等待后续明确授权，不阻塞当前draft交付。未覆盖行见coverage，不声称全仓/线上验证。

本任务无外部issue编号，issue关联/closeout comment不适用，不创建issue或对外评论。branch相对main目前无额外commit、所有dirty均本单元；提交只纳入源码/测试/README、调查/裁决与实际审核报告，不纳入workspace原始证据或临时构建。下一步自动提交push并建同一draft PR，再以精确OID完整diff核对、必要CI及首尾版本不变核对放行；live安装和merge继续禁止。
