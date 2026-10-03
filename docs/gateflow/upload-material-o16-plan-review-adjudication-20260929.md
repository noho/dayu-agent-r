# UM-O16-F01 plan review 总控裁决

- Gate：`plan review -> fix`。HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`；候选 plan `docs/gateflow/upload-material-o16-action-files-plan-20260928.md` 尚未接受、未提交。
- MiMo `docs/reviews/plan-review-20260929-002513.md` 已完整读取；派发预检 ok、显式 `--cwd /private/tmp/dayu-upload-o16`、独立 output/stderr，退出 0，Claude JSON `subtype=success`、`is_error=false`、64 turns、canary 匹配、stderr 仅模型名白名单提示，`agent_status=completed`。
- Kimi `o16-plan-review-kimi-20260928-01` 派发预检 ok，运行后退出 1，JSON `is_error=true`、`terminal_reason=api_error`、HTTP 403（五小时额度耗尽），**agent_status=failed**；未产生可采纳的完整审查 artifact。本 gate 缺有效 Kimi 路，不能宣告通过。Sol 原 plan 派发 stderr 有非白名单 apply_patch 失败，`agent_status=failed`；落盘 plan 仅作为候选审查。

## Findings 与修复登记

| MiMo finding | 总控裁决 | owner / plan 修复与完成信号 | 状态 |
| --- | --- | --- | --- |
| F1 中：tool 共用 `_upload_files_from_arguments` 两条组合判断，plan 同时要求全删且 filing 不变 | **accepted** | O16 goal 只授权 material。plan 明确仅拆出路径 tuple 解析，material 调用共享 Fins raw action/files owner 后再做必要文件检查；filing 仍走现有校验与文案，本轮不改变 filing 行为。material 分支不得保留 tool 自行重算组合；filing 的既有 tool/owner 重复登记为后续 `fins-filing-tool-combination-owner`，不在本 slice 借机扩权。加 material 与 filing 对照及 delete 携不存在路径优先级测试。 | 待 Sol 修 plan、双路复审 |
| F2 中：`DoclingUploadService.prepare_upload` 另有 action/selection 判定，plan 漏列 | **accepted（所有权关系修正）** | raw request 的 `action/files` 是否允许由 ingestion usage owner 唯一判断；Docling 收到已构造的 typed `FinsUploadMaterialFiles` selection，其内部 action/selection 匹配是不同层的类型不变量，保留 plain ValueError 作为不应由合规 workflow 触达的程序错误。plan 列出四个 caller 与前置 shared validation、selection 构造顺序，测试用禁止调用的 `prepare_upload` 证明非法 raw 组合止于前置边界；如代码证据显示用户输入仍可直达 mismatch，停止实施并扩 scope/重审，不用 unexpected_runtime 下游补偿。 | 待 Sol 修 plan、双路复审 |
| F3 低：新增 `MATERIAL_MISSING_FILES` 与 filing `MISSING_FILES` 同义，旧 filing auto 文案失准 | **accepted** | 复用既有 `MISSING_FILES` closed code，在 owner `_USAGE_MESSAGES` 将文案改为覆盖 auto/create/update；同步 owner/filing/material 断言，明确这是同一缺文件原因的同源公开文案修正，不保留旧误导文案或新同义 code。 | 待 Sol 修 plan、双路复审 |
| F4 低：CLI pre-factory 校验与 runtime ticker-first 的多错误优先级未说明 | **accepted（契约澄清）** | 两入口都消费同一 typed 组合事实；CLI 组合校验先于 Service factory/下游 ticker 解析，runtime 保留 ticker→action→source→组合顺序。该入口局部优先级对同时含多错误的请求可不同；plan 明示并各用多错误测试锁定。O16 只承诺非法组合先于目标状态/文件读取，不承诺跨入口所有字段优先级相同。 | 待 Sol 修 plan、双路复审 |
| F5 低：coverage 命令缺批次 CLI 测试 | **accepted** | 将 `tests/cli/test_upload_filings_from_command.py` 纳入 coverage 集，按文件行报告单文件目标；若大型旧文件不足 80%，明确基线/新增覆盖事实与未达标原因，不写镜像测试。 | 待 Sol 修 plan |

其它审查问题：空串 action 在 workflow 视作 auto、runtime/tool 先拒绝，属于现有入口规范化差异，plan 需写清而不新增兼容；`_validated_upload_files` 的空文件 `for_delete` 在合法 delete 仍是有效 selection 构造，不应误删；受影响 façade 的中文 Raises 应同步，必要时把 `dayu/fins/pipelines/sec_pipeline.py` 的 docstring-only 修改列入允许范围；真实 CLI case run-id 用唯一临时目录即可。MiMo 的 `fins_upload_failure_from_exception` 不识别内部 typed usage：本 slice 的 raw 组合要在 workflow `try` 外拒绝，selection mismatch 应不可由合规调用到达；若实施证伪，该风险不能仅延期成 generic 投影。

动机成立且严重性限于输入错误时机/分类与删除误接收，未有证据宣称已污染既有发布。当前 gate 不通过；Sol 只修 plan，Kimi/MiMo 有效双路 re-review 后才能实施。O14/O15 的目标状态仍为后续 work unit；所有修复项按此表持久登记，最终闭环代码汇入 PR #197，用户手工 merge。

## Sol plan fix 候选状态

`o16-plan-fix-sol-20260929-01` 仅修订候选 plan，并逐条回写 F1-F5、四 caller、入口局部优先级、验证与 stop condition；HEAD 未变。派发退出 0、JSONL 有 `turn.completed`、70 个 command execution、canary 匹配、stderr 空，但六个探索/`git diff --no-index` 命令返回 1，按 sub-agents 协议 **agent_status=failed**。其中 `git diff --no-index` 对新文件返回 1 是差异存在的命令语义，仍须按协议记失败，不能把候选计划或完成消息当派发通过。总控已核对 plan 相关段落，候选可进入后续独立复审；Kimi 403 阻断尚未解除，gate 仍未通过，产品未实施。

## MiMo 第二次 plan re-review 裁决（2026-09-29 02:00）

MiMo `docs/reviews/plan-review-20260929-015320.md` 退出 0，JSON `subtype=success`、`is_error=false`、canary `mimo-0f247548` 匹配，stderr 仅白名单提示。首轮 F1–F5 的候选修订大体经独立证实；但新 F1 中严重度、F2 低严重度和四个开放问题需在计划层收口，故当前计划仍不通过双路 gate。

1. **F1 accepted，选择单 owner 返回 pipeline action 的方案**。现计划“literal auto 经 `resolve_upload_action` 自行解析”被代码证伪：该函数只认 `None/create/update/delete`，独立 US/CN/HK workflow 接到 `"auto"` 会在 `try` 内退化为 `unexpected_runtime`。共享 `validate_fins_upload_material_action_files` 应校验四动作及 files 组合，同时返回给 pipeline 使用的 canonical `str | None`（auto→None）；它在 `ingestion_runtime.py` 作为唯一业务入口真源。runtime admission 保持当前请求 `action="auto"` 的公共表示，但调用同一 owner 作组合准入；`service_runtime._pipeline_upload_action` 改为消费该 owner 返回值并移除本地动作规范化规则；US/CN/HK 独立 workflow 消费返回值后再 `resolve_upload_action`。CLI/tool 只作同一 owner 前置校验，允许忽略返回值。这样既保留现有 runtime 请求表示，又不让 Service、workflow 各自编码 auto→None。未知 action 在独立 workflow 也须由同一 owner 在 `try` 外 typed 拒绝，不让普通 ValueError 退化；CLI/tool/runtime 既有更早 action 错误优先级仍按入口本地契约。把 `dayu/fins/service_runtime.py` 和必要测试加入写入白名单，修正 §23 机制句、§46 façade auto 测试与 stop 条件；如证据表明改变 `request.action` 对外表示或其它 goal 扩张才可成立，则停止而非隐式变更。
2. **F2 accepted**。本隔离 worktree 当前无 `.venv`；实施计划钉死 Python 3.11、本地锁约束安装，先核验解释器和 `dayu.__file__` 解析落在 `/private/tmp/dayu-upload-o16/dayu/`，pytest/coverage/pyright/真实 CLI 使用同一身份。不能把主工作区 editable 环境的通过数冒充本 worktree 测试。
3. **OQ1 accepted，随 F1 收口**：未知动作独立 workflow typed 拒绝；其它 `from_upsert_paths` 格式错误仍按既有分类保留残余，不偷入本项。
4. **OQ2 accepted（测试清单精度）**：计划点名 `tests/cli/test_fins_commands.py` 的 UF-017/UF-019 旧 `MISSING_FILES` 文案断言并更新。
5. **OQ3 accepted（实施位置精度）**：共享函数仅插入 material 分支，filing 死分支不接入。
6. **OQ4 accepted，归 F1 的唯一 owner**：不保留 `service_runtime._pipeline_upload_action` 与 workflow 两套 auto 规则；用 owner 返回 canonical pipeline action 并由两处消费。filing 的三处分立组合规则继续登记 `fins-filing-tool-combination-owner`，独立修复不在本 slice。

修订后重新 Kimi/MiMo 两路 plan re-review；产品仍未实施，后续 O14/O15 状态规则不前移。
## MiMo 第三次计划复审新增裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-025745.md` 进程 exit 0、JSON success、canary `mimo-aefcb564` 匹配、stderr 仅白名单模型提示；首轮 F1–F5 与二轮 F1/F2/OQ1–OQ4 均获独立复证，未发现架构反例。Kimi 同轮 HTTP 403、exit 1、`is_error=true`，provider failure，不算第二路。Sol 第二次 fix 仍按失败派发的候选处理。新增两项低 finding 经总控接受为计划精度修复，当前 gate **plan review → fix**，不得实施。

1. **F1 accepted，保持 requested_action 同一事实**：material 事件/结果中的 `requested_action` 应在 runtime runner 与独立 SEC/CN/HK façade 对同一规范化输入一致，`auto` 不得一路为 `None`、另一路为 `"auto"`。共享 Fins owner 应一次返回足以表达用户请求动作与 pipeline 消费动作的最小 typed 结果（例如只含 canonical requested action 与 `str|None` pipeline action），Service runtime 与独立 workflow 消费同一结果并显式传参，不能在消费者独自 `None→"auto"` 或从 resolved action 反推。保留现行 request.action 对外表示与 filing 语义；测试钉 runtime/direct 与独立 façade 的 requested/resolved pair。
2. **F2 accepted，迁移旧 tool 断言**：计划点名 `tests/fins/test_fins_ingestion_tools.py:2327` 的英文 `files must be omitted` 断言将因 material 共用 typed owner 文案改变，迁移为同一 Fins public usage reason/message 的 owner/入口测试；不在 tool 留兼容英文分支。其余 tool/CLI 本地 action 词法差异作为既有入口规则在计划中明示，不扩大为本项新规范化承诺。

Sol 修订后需有效 Kimi/MiMo 双路 re-review；provider 额度恢复前保留 gate 未通过状态。

## MiMo 第四次计划复审新增裁决

`docs/reviews/plan-review-20260929-034144.md`：exit 0、结构化 success、canary `mimo-37df51e8` 匹配、stderr 仅白名单模型提示。第三轮 F1 typed requested/pipeline action 与 F2 material 英文旧断言均在设计层闭合，其余 owner/入口/合法 delete/环境/覆盖率未见新架构反例。新增一项低 finding 已按 `tests/fins/test_fins_ingestion_runtime.py:test_upload_requests_use_source_kind_for_filing_material_discrimination` 当前代码核对：material 分支以 auto+无 files 建 job，O16 新合同会拒，计划此前未点名迁移；总控 **accepted**，Sol 仅修 plan，要求此测试改用有真实文件、合法 form/name 与 owner 生成身份的 material create 请求，保持 SourceKind 判别的原断言。不要改生产代码容忍旧非法组合；也不要用 missing-target delete 绕过，因为 O14/O15 后续会改变其合法性。

filing 入口对 `None` 请求动作的 requested 投影可能与 material canonical auto 不同，已登记的 `fins-filing-tool-combination-owner` 扩展审计这一 filing 事实；O16 不改 filing 输出以免漂移。其它分类器缺口、巨型文件覆盖率和 O14/O15 依赖仍按既有残余跟踪。Kimi 403 无有效第二路，plan 未通过/产品未实施。

Sol 第四次 plan fix `o16-plan-fix4-sol-20260929-01` 进程 exit 0、JSONL `turn.completed`、canary `gpt-6-sol-9916a1a7` 匹配，26 条 command exit 0，但两次 `apply_patch verification failed` 写入非白名单 stderr，故 **agent_status=failed**，计划 SHA-256 `e599b8cb44f613f5a7137eb567f902df50ae75dabeea917e30950ef4014ac7a2` 仅作候选。总控核对新增迁移段发现一个集成漂移：计划要求 SourceKind 判别测试把旧硬编码 ID 断言改为 `request_summary["document_id"] is None`；O07 后会在 admission 规范生成稳定 ID，届时该断言又变成偶然行为锁。此测试的 owner 目的只是 SourceKind 判别，应**删除 ID 摘要断言**，由 O07 的身份 owner 测试单独覆盖文档 ID；保留有效 create+真实文件/form/name、SourceKind 与 executor 单次断言。Sol 下一轮仅修此 plan 精度，之后有效双路 review；不允许生产代码兼容旧 ID 预期。

## Sol 第五次 plan fix 候选

`o16-plan-fix5-sol-20260929-01` 预检 ok、显式 `/private/tmp/dayu-upload-o16`、独立 output/stderr，退出 0；JSONL `turn.completed`、20 条成功 command execution、无失败/error，stderr 空、canary `gpt-6-sol-33e1f300` 匹配，`agent_status=completed`。总控核对 plan SHA-256 `f50641e2ff0be5a1ad481400cdfa0a9926278e138d5435a389d2bebe77080ab1`，SourceKind 测试迁移已删除 document_id 摘要值断言，仅保留有效 create/文件/form/name、SourceKind 与 executor 断言；O07 owner 单独验证身份。修复项在计划层已落实，产品未实施；下一 gate 仍是有效 Kimi/MiMo 双路 plan re-review。

## 第五修订双路复审的 MiMo provider 失败（2026-09-29）

`o16-plan-rereview5-mimo-20260929-01` 预检 `setup_status=ok`、绝对 O16 workspace、独立 JSON/stderr/canary；runner 进程 exit0，JSON 外层虽为 `subtype=success/is_error=false/terminal_reason=completed`，但 `stop_reason=content_filter`，`result` 只有 `The request was rejected because it was considered high risk`，未读回 canary、未写指定 review artifact。按实际任务证据严格判 **agent_status=failed、tool_evidence=no、canary_status=not_run**，绝不可把 wrapper success 算有效 MiMo 复审。stderr 仅白名单模型提示；Kimi 同 SHA 仍在运行。本次未改计划/产品；下一步可按 sub-agents 协议在查明失败性质后最多一次同 provider、原任务内容的新 label 修复性重试，仍失败则需安全替代路由或用户裁决，不绕过拒绝。

总控已按唯一一次修复性重试规则重新预检 `o16-plan-rereview5-mimo-20260929-02`（`setup_status=ok`），未修改任务正文或审查目标 SHA，只用新 label/独立 output/stderr/canary；session `92414` 正运行。重试结果未返回，不计有效审查；若再次 content filter，停止同 provider 重试并如实报告。

同任务唯一修复性重试 `o16-plan-rereview5-mimo-20260929-02` 已返回：进程 exit 0，JSON `subtype=success/is_error=false/terminal_reason=completed`，`stop_reason=end_turn`，canary `mimo-f6d0256a` 匹配，stderr 仅白名单模型提示，审查 artifact `docs/reviews/plan-review-o16-rereview5-mimo-20260929.md`；因此本次 **agent_status=completed**。MiMo 对同 SHA `f50641e2...` 判 `pass-with-risks`、零 finding；六个聚焦面均有代码重证。两个 implementation open questions 中 workflow 组合校验相对 ID 校验的顺序须在实施任务中固定，并以联合非法测试断言；`tests/README.md` 缺专门更新约束只按 AGENTS.md 触发判断。七项 residual risks 分派实施 gate、O14/O15 和现有独立 work unit，无新的 plan blocking finding。Kimi 同版 session `11659` HTTP 403 无效，故**双路 plan gate 仍未通过**；不得提前实施。

后续跨 work unit 复核发现 O04/O23 资产切片候选新增 `dayu/fins/upload_usage_contract.py`，将 `FinsUploadUsageCode` 与唯一 `_USAGE_MESSAGES` 迁出 `ingestion_runtime.py`，同时引入 validated material handoff。O16 当前 plan §28 仍在旧 owner 修改 `_USAGE_MESSAGES`、§41 白名单不含新 owner 文件。**C3 accepted，待资产切片 accepted+integrated 后修 plan 并重新双路复审**：在真实集成 HEAD 上保留同一 action/files 准入函数与 typed decision 的 owner 判断，但 MISSING_FILES 公共文案必须修改实际唯一 usage contract，允许文件/测试清单、调用形状和错误时序须按真实 handoff 重核；不得在 runtime 重建文案副本或兼容层。当前 MiMo pass 针对旧 SHA/旧 HEAD，不能跨这次产品基线变更直接授权实施。若资产切片最终不接受该迁移，按 accepted HEAD 重新裁定 C3。
