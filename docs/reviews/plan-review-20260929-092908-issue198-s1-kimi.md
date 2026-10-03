# plan review：issue #198 S1 第八次 plan re-review(Kimi 独立复审,第十次 fix 候选)

- RUNTIME/PROVIDER/MODEL: claude/kimi/kimi-k3[1m]
- 日期:2026-09-29;reviewed target:`docs/gateflow/issue-198-download-failure-projection-plan-20260928.md` 第十次 fix 候选(Sol label `issue198-s1-plan-fix10-sol-20260929-01`;按总控裁决其派发有两条失败 command,`agent_status=failed`,落盘仅作候选)
- 停止条件核验(预检通过后才开始审查):
  - 计划 SHA-256=`2d18014ce605c8368d53247a43669f6ba597ecc875fe6d5a7b2ce558c0d92cd7` ✓ 与任务给定逐字一致,无版本漂移
  - HEAD=`8d8d494fbbce0052372fb1b42097c9f7222cfa28` ✓ 与计划 fix6 起记录的基线一致
  - 三产品候选 `git diff -- dayu/fins/ingestion_runtime.py dayu/fins/direct_events.py dayu/cli/output.py | shasum -a 256`=`d9af4d09c3226616ccae2a9f2bd44281d1ad48021f9ced1d14b49291cf580783` ✓ 与计划记录指纹一致
  - `git diff --cached --name-only` 为空 ✓
- 阅读范围:本计划全文、总控裁决 `docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md`(至末段「Sol 第十次 plan fix」与独立静态验证)、上一轮 MiMo artifact `docs/reviews/plan-review-20260929-033643.md`、当前未提交产品/测试/README diff、相关 owner 代码(storage/workflow/adapter/Fins runtime/Service/CLI)与测试现状;**未读**另一模型本轮第八次审查 artifact
- 本路只产出本 artifact;未改计划、产品、测试、README、旧 artifact,未 stage/commit/push/PR/外部评论,未派发子 Agent
- 方法说明:fix9 版本(任务给定的旧 SHA `2e4bce41...`)只是被覆盖的工作树状态,无法从 git 独立取得做逐行 diff;本路改为把现行正文逐句对照 MiMo 第七次 review 的 F1/F2/OQ1/OQ3 与 owner 代码直接验证,等效覆盖「第十次是否闭合前轮」的审查目标

## 独立重证方法

对任务指定的攻击点逐一直接读真实代码验证,不接受 plan/裁决/上轮 review 转述:

1. `dayu/fins/pipelines/cn_download_workflow.py`:初始 whole-kind 预检 227–231、循环前 `_publish_cn_company_after_repair` 249–256、候选循环 257、单 filing 宽 catch 311–331、post-repair classify+显式 revision conflict 332–342、post-repair company publish 349–355、外层取消 catch 356–358、共享函数 `_publish_cn_company_after_repair` 410–448、`_build_candidate_failed_result` 598–635
2. `dayu/fins/pipelines/cn_download_filing_workflow.py`:`project_cn_filing_failure` 71–88(typed → `filing_execution_failed` 现状)、Phase A typed 167–173、churn 耗尽裸 `SourceIntegrityRevisionConflictError` 510–512、Phase B typed 593–603、finally 回滚 709–714 + `_rollback_cn_batch_preserving_primary` 717–742
3. `dayu/fins/pipelines/cn_pipeline.py`:`collect_cn_download_result_from_events` 186–211(异常裸传、无回填)、`CnDownloadAdapter.download` 1335–1382、`_summary_from_pipeline_result` 1403–1447(ok/cancelled 封闭)、`_project_cn_document_row` 1450–1536(failed 行接受任意 reason_code)、`CnPipeline.download`/`download_stream` Raises 现状
4. `dayu/fins/storage/_fs_storage_infra.py`:`begin_batch` 417–533(copytree 483 种子 staging)、`commit_batch` 533–611(`_validate_complete_source_tree` 559 严格先于 guard/swap;`raise commit_error from rollback_error` 571–584)、`_validate_complete_source_tree`/`_validate_complete_source_kind_tree` 1069–1160(whole-kind inspection 1124–1130)、`_commit_batch_with_publication_guard` 676–719(physical swap 702–704)、`_rollback_precommit_batch` 1328–1352(pre-swap 只动 journal/staging)
5. `dayu/fins/storage/_fs_source_integrity.py`:whole-kind typed 抛点 312–315/332–342/438–441、root entry 枚举与 `unassignable_root_fact` 275–304、exact-target 无 descriptor → `IDENTITY_UNTRUSTED` 287–298;`source_integrity.py`:四值封闭 enum 182–188、`SourceIntegrityPreflightError(RuntimeError)` 191–208、`SourceIntegrityRevisionConflictError(RuntimeError)` 211–227
6. `dayu/fins/ingestion_runtime.py`:direct producer 异常收口 4307–4346(零候选 FAILED + 共用投影)、`_run_download_job` 4918–4963(现仅 unsupported + generic)、`_save_failed` 5905–5945(`result_summary` 参数)、`_save_download_unsupported` WARN 5980–5987、`_save_failed_from_exception` WARN 6003–6016(动态类名 + `exc_info=True` 现状)、`_execute_download_request` 5275–5331(成功路径双验证 5319–5323)、`_empty_download_summary_from_request` 6787–6823(`terminal_disposition` 参数)、未提交 `_SOURCE_INTEGRITY_PUBLIC_REASONS` 6826–6831 与 typed 分支 6874–6882、EXECUTION 尾支 6891–6897(无 `str(exc)`)、`_classify_direct_error` typed 分支 7084–7088
7. `dayu/fins/direct_events.py` 未提交候选:`FinsDownloadFailureReason` 四值、`reason_code` 字段/校验(非空仅允许 STORAGE + 无 transport)、JSON 投影;`FinsResultSummary.__post_init__` 677–690(现行 FAILURE 强制 FAILED disposition 的待放宽点)
8. `dayu/fins/download_contract.py`:`_terminal_disposition_from_counts` 524–552(failed_count=0 → SUCCEEDED)、`from_document_rows` 410–459、`empty_terminal_override` 398–404(仅 FAILED/CANCELLED)
9. `dayu/fins/pipelines/cn_download_company_meta.py:26–71`(identity 不变时 intent=None → rollback 而非 commit)
10. `dayu/service/fins_wait_adapter.py:_failure_message` 592–617(typed 失败帧缺 download 的拒绝已在该 owner)
11. `dayu/cli/output.py`:未提交 `reason=` hunk(计划要求改 `reason_code=`)、`_EMPTY_CELL="-"` 39
12. 测试现状:`tests/fins/test_cn_download_workflow.py:2627` post-repair 先例(先发布、再损坏唯一 selected source、同请求 repair)、`tests/fins/test_cn_download_runtime.py:814/853/956/976/1042` `_summary_from_pipeline_result` owner 测试、未提交 `test_fins_ingestion_runtime.py`/`test_output.py`/`test_fins_wait_adapter.py` typed case;`tests/service/test_fins_direct.py`、`tests/runtime/test_log.py`、`tests/cli/test_fins_commands.py` 存在性
13. 三份 README 未提交 hunk:#198 句与点号/inspector 句确实处于同一 diff hunk(根 README、 fins README、tests README 逐一核对)

## 攻击点逐项重证结果

### A. MiMo 第七次 F1:循环前 company pre-swap typed 零候选 vs post-repair 快照,catch 放置陷阱 —— 计划层收口成立

- 契约句(45 行):「无 repair 时、候选循环前调用 `_publish_cn_company_after_repair`,若 company `commit_batch` 在 physical swap 前抛同一 typed preflight,此时尚无已处理候选:原始异常裸透传,不构造空 `filings` 的私有 abort、快照或伪 filing 行;direct/job 均使用请求级 `FAILED` 零候选摘要。该函数还被 post-repair 路径调用,私有快照 catch 只能放在后者的调用点,不能放进共享函数内部或包住循环前调用点」——直接命中 MiMo 反例的两个落点禁令。
- 共享函数陷阱复证:`_publish_cn_company_after_repair`(410–448)确被 250(循环前,`filings` 初始化后尚无任何 append)与 349(post-repair,`filings` 已有终态行)共享;若 catch 写入共享函数内部,循环前路径会产出携带空快照的 `CnDownloadIntegrityAbort` → adapter 纯投影空 rows → `from_document_rows` → `_terminal_disposition_from_counts(failed_count=0)` 返回 `SUCCEEDED`(546–547),而 `empty_terminal_override`(398–404)只允许显式 FAILED/CANCELLED——两种空形状公开终态相反,陷阱真实存在。
- 测试句(57 行):新增独立用例「让初始 whole-kind gate 先通过,在第一次 `_publish_cn_company_after_repair` 的 company `commit_batch` 前,以受控 batching wrapper 在真实 staging whole-tree 写入非点号非法条目,再委托真实 `commit_batch`/`_validate_complete_source_tree` 抛 typed,不能直接伪造 classifier 返回值或异常;核对 pre-swap target 未动、原 typed 裸透传而非 `CnDownloadIntegrityAbort`、无伪 filing 行或私有空快照」,且「尤其断言 `terminal_disposition=FAILED`,使误用空 `filings` 快照派生的 `SUCCEEDED` 必然失败。该用例与 post-repair 已有 filing 的 company spy 用例分别证明两个调用点,不相互替代」——判别性断言正是 MiMo 要求的空快照 SUCCEEDED 形状必然失败。
- 真实触发可行性复证:`begin_batch` 对已发布 ticker 用 `shutil.copytree`(483)种子 staging;wrapper 持有 token(transaction_id)可定位 `batch_root/transaction_id/ticker_key` staging 树;在 `staging/<ticker>/filings/` 写入非点号普通文件后,真实 `commit_batch` → `_validate_complete_source_tree`(559)→ `_validate_complete_source_kind_tree`(1097)→ `_inspect_source_kind_unguarded` whole-kind(requested_document_id=None,1124–1130)→ root entry 为非目录普通文件 → `unassignable_root_fact`(284–285)→ 312–315 抛 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`,严格先于 publication guard/backup/swap(692–716)。配方可达到目标抛点,不依赖 monkeypatch owner 事实。
- direct/job 同源复证:direct producer 现有异常收口(4307–4344)已对 download 请求用 `_empty_download_summary_from_request(..., terminal_disposition=FAILED)`(4317–4321)+ `_download_public_failure_from_exception`(4327–4330,未提交 typed 分支 6874–6882);job 侧计划新增 typed catch 落点在 `_UnsupportedDownloadSourceError`(4960)与普通 `except Exception`(4962)之间,用同一 helper 的 `to_json_summary()` 与同一投影的 safe_message——两个入口消费同一 Fins 真源,零候选形状一致。
- **残余观察见 Finding 1(低,实现前提未钉死,可自纠)。**

### B. MiMo 第七次 F2:新 typed job WARN 只保留固定事件标识 —— 计划层收口成立

- 契约句(53 行):「新增 WARN 仅记录固定事件标识 `fins.download.typed_failed_record_save_failed`,不设置 `error_type` 字段、不记录任何动态异常信息(包括异常类名、`str/repr`、`exc_info`、路径、秘密或 traceback)」,并禁止复用既有 WARN 的动态类型 + `exc_info` 写法;WARN 只诊断二次保存失败,不虚称终态、不以 `{}` 覆盖原摘要。与总控「简化为固定诊断事实」逐字一致。
- 测试句(57 行):注入自定义异常类(类名及内容分别含可识别秘密、路径),断言不逃逸、WARN 事件存在、日志文本及记录字段均无该类名/秘密/路径/traceback/`exc_info`/`error_type`/异常原文;读 job store 核对不虚称已持久化。MiMo 要求的「逐字断言类名与秘密均不出现」具备。
- 边界复证:既有两处 WARN(`_save_download_unsupported` 5981–5986、`_save_failed_from_exception` 6009–6015)确为动态 `type(...).__name__` + `exc_info=True`,计划 91 行继续将其登记在 `fins-other-raw-diagnostics-audit` 并声明不冒充审计完成——F5 边界未回退。
- 文档卫生:fix9 历史段(4 行)仍含「可信 `error_type`」旧表述,fix10 头(3 行)明文「若旧 WARN `error_type` 表述与本次冲突,以现行 S1 正文为准」,现行正文 53/57 行一致地无 `error_type`—— supersede 标记到位,不构成实施歧义。

### C. MiMo 第七次 OQ1:post-repair catch 范围与抛点归属 —— 计划层收口成立

- 47 行:「`classify_source_integrity_preflight` 可抛 `SourceIntegrityPreflightError`,其返回 `SelectedSourceRepairRequired` 时由 workflow 显式抛 `SourceIntegrityRevisionConflictError`;typed catch 必须同时覆盖 classifier 调用和随后这项显式检查,不得只包住 classifier」——抛点归属与代码精确一致:classifier 本身只抛 preflight(source_integrity.py:311–324),revision conflict 是 workflow 342 行的显式 `raise`;catch 区域覆盖 336–342 整块。
- 补充复证:catch 区域内的 `_raise_if_cancelled`(343–348)若抛 `CnDownloadCancelledError`,typed catch 不捕获它(两类异常均为独立 RuntimeError 子类),沿外层 356 取消 catch 收口——与 47 行「`CnDownloadCancelledError` 先保留原取消控制流和唯一终态合同,不被后置 catch 转为 FAILURE」一致。
- post-repair company publish(349–354)的 typed 同由该调用点 catch 覆盖,循环前 250 调用点明确不改——与 A 项的放置禁令互洽。

### D. MiMo 第七次 OQ3:mid-filing 注入的证据界限 —— 计划层收口成立

- 57 行:「另在单 filing 流边界受控注入裸 `SourceIntegrityRevisionConflictError`,锁定外层 workflow 宽 `except Exception` 形成 `filing_execution_failed` 行、继续处理下一候选及其未修复残余归属,不误断言为 preflight reason;此用例只证明 workflow 收口,不证明 `cn_download_filing_workflow.py` 的三轮 identity churn 真会耗尽、storage owner 真抛冲突或重试次数正确。若改用真实 owner churn 配方,须以可控并发/身份变更和 owner 抛点证据另行证明,不得把注入结果冒充真实 churn」——证据界限逐字在位。
- 现状复证:churn 耗尽裸抛(510–512,`_MAX_SOURCE_IDENTITY_ROUNDS=3`)在单 filing try 内,落入宽 catch(311)→ `project_cn_filing_failure`(71–88)→ `"filing_execution_failed"` + 循环继续;45 行维持其为 `fins-download-storage-sibling-errors` 待修残余,Raises 只列真实裸出口(preflight 首候选前 / 私有 abort),不列已被吞下的裸 revision conflict——与 MiMo B 项复证结论一致,未回退。

### E. 已确认 filings 快照守恒与 typed 投影链 —— 复证通过(未回退)

- 单 filing Phase A/B typed:Phase A(167–173)在 `begin_batch` 前,无 batch;Phase B(593–603)在 `commit_batch`(707)前,finally(709–714)经 `_rollback_cn_batch_preserving_primary` 回滚 caller-owned token——「单 filing storage batch 已由自身 owner 回滚」属实。
- workflow 新单 filing typed catch(先于 311 的宽 catch)记当前候选一行私有 `failed`(通用 `source_integrity_preflight` 类别,不复制四值)、保留此前终态行、发 `FILING_FAILED`、终止循环,再以 `_build_result/_build_summary` 构造 `integrity_failed` 快照经 `CnDownloadIntegrityAbort` 携带原异常;`_project_cn_document_row` 的 failed 分支(1524–1535)接受任意 reason_code 字符串,新私有类别不会被投影拒绝,可行。
- adapter 侧:`_summary_from_pipeline_result` 现封闭 ok/cancelled(1424–1426);计划抽纯投影 helper、`integrity_failed` 快照按自身失败 status 严格校验后复用同一 helper,不伪造 `ok`——与 8th 轮 Kimi F3 裁决一致;`_execute_download_request` 成功路径双验证(5319–5323)存在,异常路径补验在同一文件内可实施;`collect_cn_download_result_from_events`(186–211)异常裸传、无事件顺序回填,与「collector 不从已发事件反推部分结果」一致。
- 计数口径:`from_document_rows`(437–441)由 rows 机械派生;post-repair 唯一完成行场景 `failed_count=0` → `terminal_disposition=SUCCEEDED`,请求 RESULT 仍 FAILURE——`FinsResultSummary.__post_init__` 现行 681–682 强制 FAILED 正是计划要放宽的点(51 行),放宽合同与总控 fix4 修订裁决(FAILURE + public failure 可携带 FAILED/PARTIAL_FAILURE/SUCCEEDED,不按 kind/reason 猜进度)逐字一致。
- job typed 收口:`_save_failed` 的 `result_summary` 参数(5910)与 `_EMPTY_SUMMARY` 默认(5935)证实「现状落 `{}`」;新增两条 typed catch(私有 failure 用已验证 `persisted_summary.to_json_summary()`、裸 typed 用请求级零候选摘要)直接消除该不一致,不复用 generic 路径。

### F. storage pre-swap 与 physical swap 边界、独立后续项隔离 —— 复证通过,未把泛异常塞回 S1

- 调用序:`commit_batch` 559 `_validate_complete_source_tree` 严格先于 `_commit_batch_with_publication_guard` 的 backup/swap(692–706);pre-swap typed 失败时 `_rollback_precommit_batch`(1328–1352)的 staging-exists 分支不触碰 target,backup 尚不存在,只写 journal + 删 staging;即使该 cleanup 失败,`commit_batch` 以 `raise commit_error from rollback_error`(579)保留原 typed 与异常链——「只允许声明文档未被本次 swap 改动,不得声明 rollback/cleanup 成功、不得以 `__cause__` 判定已发布文档归零」与 owner 行为一致。
- 泛化禁令:47 行明确「不得对 company `commit_batch` 的 ValueError、OSError、post-commit release 或其它物理失败使用泛 `except Exception` 保留快照;若 owner 证据显示 target 已动,或 physical swap/restore 及发布状态不确定,触发停止条件并转独立 work unit」;87 行把 physical swap/restore 双失败、postcommit、precommit ValueError/OSError 统一登记为 `fins-download-indeterminate-publication-state`,并称「现有泛异常零摘要是明确残余缺陷,非正确行为」——不确定发布错误没有被偷纳入 S1 成功信号,已接受业务目标与独立后续项边界清晰。
- ValueError 侧注:`_validate_complete_source_kind_tree` 对 manifest/inventory 不一致抛 ValueError(1131–1151)而非 typed;whole-kind typed 只来自 `_inspect_source_kind_unguarded` 的 312–315/332–342/438–441——计划把 typed 守恒严格限定在后者的可证明路径,前者落 generic 残余,口径与 owner 抛点精确一致。

### G. WARN 脱敏、LLM wait 范围、测试/验证/证据链 —— 复证通过

- S2 安全诊断边界(28–31 行)本轮未动;`safe_exception_trace` 不抛出兜底、内建祖先 + 16 hex 指纹、受信根帧校验与 S2 测试注入要求仍在位(本路抽查,非本轮攻击点)。
- LLM wait:`_failure_message`(592–617)确为 typed 失败帧唯一投影 owner,缺 download 的拒绝已在 601–602;63 行固定 `scope_note` 字段名、私有常量 `_DOWNLOAD_FAILURE_SCOPE_MESSAGE` 与逐字文案「下载摘要只统计已处理文档;整体下载操作失败,请按失败原因和处理建议处理。」,独立字面量断言、不扩公共 schema、hint 仍来自 Fins 公共 `retry_hint`——与总控 OQ2/F4 一致;该文案恰好解释 E 项 FAILURE+SUCCEEDED 同帧,语义自足。
- 验证命令(75 行)覆盖 S1 全部六个允许测试文件 + S2 三个;`tests/service/test_fins_direct.py`、`tests/runtime/test_log.py`、`tests/cli/test_fins_commands.py` 实际存在;pyright 全量命令与 ≥80% 覆盖率目标在位。
- README:三份 README 的 #198 句与点号/inspector 句经逐一核对确处同一 diff hunk,计划要求 patch 编辑按行 stage、`git diff --cached --check`、staged patch 只含 #198 句—— grounded;根 README #198 句改写为自足条件句并使用 `reason_code=` 的要求与未提交 hunk 现状(仍为 `reason=`)的差距是计划已声明的待实施改动,不是 drift。
- 真实 CLI(81 行):baseline 先行(退出 0 + 至少一个真实 published filing)、在 `portfolio/000333/filings/` 根放唯一命名非点号普通文件 → `_inspect_source_kind_unguarded` whole-kind `unassignable_root_fact` → 313 typed → `UNSAFE_PUBLICATION`,与代码逐点一致;失败分类要求区分 provider/网络阻塞与「不 init 可建库」假设证伪,不用旧事故证据顶替;隐私断言按 RESULT/CLI 失败文本/安全诊断/普通 INFO 分类核对并记录行号——MiMo F5(第 5 轮)边界未回退。

## Assumptions tested(证伪尝试)

1. 「循环前 company typed 裸透传确实零候选」——成立:250 调用点在 `filings` 初始化后、候选循环前,无任何 append 路径;唯一外层 catch(356)只捕取消,typed 必裸传。
2. 「误放空快照会产出公开 SUCCEEDED 且形状合法」——成立且强化判别断言:放宽后的 `FinsResultSummary` 接受 FAILURE+SUCCEEDED,错误实现不会构造失败,只有 `terminal_disposition=FAILED` 断言能杀死它;57 行已逐字要求。
3. 「新 WARN 固定标识合同可被指定断言破坏」——证伪:注入自定义类后,若实现照抄既有 pattern 记录 `type(exc).__name__`,类名(含秘密)出现在日志文本即被 57 行断言捕获;`error_type` 字段出现亦被显式拒绝。闭环。
4. 「post-repair 测试先例可支撑新配方」——成立:`test_cn_top_level_repairs_selected_corruption_with_overwrite_false`(2627)确为「先发布、再损坏唯一 selected source、同请求 repair」真实配方;59 行 post-repair 注入窗口(list_source_integrity 之后、classify 之前向 published filings/ root 写非点号非法条目)与 313 抛点一致。
5. 「fix10 只改了 F1/F2/OQ1/OQ3 对应文本,未夹带范围变更」——基本成立:fix10 头声明的四项修订均在 45/47/53/57 行找到对应;S2、验证命令、README 决策、延期项清单与 fix9 状态一致,未发现新允许文件或新成功信号。fix9 原文无法从 git 取得逐行 diff,此为方法限制,已在头部声明。
6. 「既有 Kimi 第五轮 F1–F5 未因 fix10 回退」——成立:F1(job 结构化零候选)扩展到循环前 company typed 且方向一致;F2(单点 unwrap)、F3(纯投影 helper)、F4(wait scope_note)原文在位;F5(既有 WARN 审计)继续登记独立 WU。

## Findings

### 1-未修复-低-循环前 company pre-swap 真实触发配方的 commit 可达性前提未钉死
- **位置**: S1 正文 57 行(「在第一次 `_publish_cn_company_after_repair` 的 company `commit_batch` 前,以受控 batching wrapper 在真实 staging whole-tree 写入非点号非法条目,再委托真实 `commit_batch`/`_validate_complete_source_tree` 抛 typed」)
- **问题类型**: 测试配方精度(实现前提)
- **当前写法**: 配方假设 `_publish_cn_company_after_repair` 必达 `commit_batch`;但 `stage_company_meta_for_cn_download` 在 identity 不变时返回 `None`(cn_download_company_meta.py:65–71),`_publish_cn_company_after_repair` 随即走 rollback 分支(445–446),`commit_batch` 根本不会被调用,wrapper 注入的 staging stray 永远等不到校验。
- **反例/失败场景**: 实施者按「先跑一次建立真实来源、再用同参重跑让初始 whole-kind gate 通过」的最自然解读设计用例——第二次相同请求(同 aliases、同 fake profile)intent=None → rollback,无 typed 抛出,测试失败;实现者需自行发现须让第二次请求携带新 `ticker_aliases`、变更 fake profile 的 company_name,或改用 fresh ticker 路线(fresh 时 existing_meta=None,必有 intent),才能到达 commit。
- **为什么有问题(但不阻塞)**: 该前提属于 owner 函数的静默分支,计划其余配方(Phase B identity 目录、post-repair 窗口)都钉到了同等精度,唯独此新增用例差一句;但失败模式是响亮失败(typed 不出现 → 断言直接挂),不可能静默假通过,实施/code re-review 可自纠。
- **直接证据**: `cn_download_company_meta.py:61–71`(merged identity 不变返回 None)、`cn_download_workflow.py:445–448`(None → rollback,否则 commit)、`run_cn_download_stream_impl` 的 `ticker_aliases` 参数链。
- **影响**: 实施一次往返成本;不影响设计语义与公开合同。
- **建议改法和验证点**: 实施时在测试 docstring 或计划补一句「触发请求必须产生非 None company intent(新 alias/变更 profile/fresh ticker)」;code re-review 核对所选路线确实到达 `commit_batch` 且 typed 从 `_validate_complete_source_tree` 抛出。
- **修复风险(低/中/高)**: 低。
- **严重程度(低/中/高/严重)**: 低。
- **状态**: accepted-candidate。

## Open Questions(实施注意事项,非新 finding)

1. 共用 unwrap 的函数名与返回形状仍未钉死(总控已接受为实施选择):实施/code re-review 核对 direct producer(4309)与 job typed catch 只调一处解包 + 一处投影,无第二份 `__cause__` 遍历;direct 异常路径改用 `_public_download_summary(persisted_summary)` 替换现零候选构造时,保持「恰一个最后 RESULT」。
2. `_execute_download_request` 异常路径补验(`_bounded_download_summary` + `_validate_download_summary_request_identity`)若自身抛 ValueError,落 generic 零摘要——按总控裁决属已登记残余,实施时显式确认归入而不报新缺陷。
3. 真实 CLI baseline 的「不 init 可建库」假设与 provider/网络状态仍是待取得证据,失败时按 81 行分类回报,不用旧事故证据顶替。

## Residual Risks(既有登记逐项复证,去向不变)

| 残余 | 复证 | 去向 |
| --- | --- | --- |
| physical swap/rollback 双失败、restore、postcommit、precommit ValueError/OSError 发布状态不确定;generic 异常在已确认文档后仍可能零摘要 | `commit_batch` 533–611/676–719/1328–1352 复证;47/87 行明文停损与「明确残余缺陷」 | `fins-download-indeterminate-publication-state` |
| mid-filing revision conflict / RepairBlocked 落普通 filing 失败行 | 510–512 抛点与 311 宽 catch 复证;45/57 行只锁现状不冒充保真 | `fins-download-storage-sibling-errors` |
| 既有两处 WARN `exc_info=True`、generic job `str(exc)` 投影、非 download direct 原始 traceback | 5981–5986/6009–6016 复证;新 WARN 站点按 F2 收口不入该队列 | `fins-other-raw-diagnostics-audit` |
| SEC/其它来源 bare typed 中途丢行投零摘要 | 计划 93 行登记;S1 只承诺 CN/HK 可证明路径 | `fins-download-other-source-summary-conservation` |
| 投影/RESULT 二次失败、logger 二次抛出 | 91 行明文不承诺 | `fins-direct-projection-failsafe` |
| 无来源文档 retry_hint 指向退出后不可查临时日志 | 27/94 行明文 | `fins-download-no-source-retry-hint` |
| 点号元数据 hunk 与本 issue 隔离;README 相邻句按行 stage | 三份 README diff 复证同 hunk;`_fs_source_integrity.py` +39 行与 atomicity 测试 +109 行确属独立 WU | 独立 storage work unit |

## 结论

**pass-with-risks**。

第十次 fix 候选对 MiMo 第七次 F1/F2/OQ1/OQ3 的收口全部成立且与 owner 代码事实一致:F1 的循环前 company pre-swap typed「原异常裸透传 + 请求级 `FAILED` 零候选摘要」与「catch 只能放在 post-repair 调用点」双禁令直接命中共享函数陷阱,新增真实触发用例以 `terminal_disposition=FAILED` 断言杀死空快照 SUCCEEDED 错位,两个调用点各有独立证明;F2 的新 WARN 固定事件标识合同(无 `error_type`、无任何动态异常信息)与自定义类注入断言闭环,既有 WARN 的 F5 审计登记未回退,fix9 旧 `error_type` 表述有显式 supersede 标记;OQ1 的 catch 范围(classifier 调用 + workflow 显式 revision conflict 整块)与抛点归属和代码逐点一致;OQ3 的 mid-filing 注入证据界限明文不冒充真实 churn。任务指定的其余攻击点——已确认 filings 快照守恒链(workflow 私有 abort → adapter 严格投影 → direct/job 同源)、storage pre-swap 与 physical swap 调用序、首候选前零摘要、job/direct 同源 typed reason+retry、二次落盘幂等与不逃逸、LLM wait scope_note、六个测试文件 + pyright + 覆盖率 + README 按行 stage + 真实 CLI baseline-first 证据——逐项复证通过;`fins-download-indeterminate-publication-state` 等独立后续项边界清晰,泛异常不确定发布错误未被塞回 S1 成功信号。

唯一新 Finding 1 为低严重度测试配方精度缺口(commit 可达性前提),失败模式响亮、可在实施/ code re-review 自纠,不构成结构性 fail;建议实施时按计划外补一句前提说明,不阻塞本轮。本路不构成双路 gate pass:fix10 派发按协议为 failed candidate,须与另一路有效 re-review 一并由总控裁决,通过前不进入 S1 implementation、S2、checkpoint 或 PR 操作。

CANARY=kimi-07f71790
