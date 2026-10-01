RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-183be2b2

# PR197 F6-S1 实施候选与验证证据

本轮 label=`pr197-f6-s1-implement-sol-20261001-01`。已完成获授权的唯一行为 slice 候选，交 root 独立核收；本文不是实现 gate pass、review、PR readiness 或合并裁决。没有派发子 Agent，没有 stage/commit/push/PR/merge/main/branch/worktree 操作。design_doc=N/A。

runtime 为 codex，任务指定 provider 路由为 gpt-6-sol。当前工具上下文没有独立可核验的实际模型 metadata，故实际模型记 unknown，不以任务名称或 canary 推断。开头 canary 来自本轮指定文件 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.z1JvXZ/canary.txt` 的实际工具读取；本轮 `canary-final.stdout.log` 另保留原内容。

## 输入、授权和首末身份

已读取真实 accepted plan 最新 A–F 前缀、原 goal、owner-preflight、A1–A4 裁决与最终 re-review 裁决，并核真实 source/tests/README。动机成立：真实 publication identity 持续变化与 postrepair 仍损坏需要不同恢复动作；只改 runtime 分类不能修复 SEC 上游裸抛丢已确认摘要的问题。实现沿 storage→workflow→adapter→runtime 真源边界完成，不增加下游补偿。

| 身份 | 实际核查结果 |
| --- | --- |
| 唯一 workspace / branch | `/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`，首末一致 |
| accepted plan commit / 起点 HEAD | `a32ff820623cf16ef631b16db62e61b9f443ed91` |
| binding plan SHA256 | `57ab49b7648444629db3290b7d8ba54b397b63f1495fe70fd0e0d18c71d7f1b1`，首末未变 |
| accepted gate 来源 | `docs/gateflow/pr-197-r1-f6-plan-fix-rereview-adjudication-20261001.md` 的最终 `gate_decision: pass`；仅表示计划已接受 |
| 唯一 freeze | `workspace/tmp/pr197-f6-s1-implement-sol-20261001-01/freeze.json` |
| freeze SHA256 | `4091dc2655ba1287c52015ba70232bef90719aab0fe6666f6f2efbaedf4be95f`，首末一致，未更新 freeze |
| 文件数量与范围 | 65 current / 65 originals；21 allowed / 44 readonly，按 freeze 逐条核查 |
| 首核 | 全部 65 current 与 65 originals 均等于 expected SHA |
| 末核 | 全部 65 originals 和 44 readonly current 等于 expected SHA；变化恰为 8 production + 原 10 tests + 3 README 共 21 allowed current |
| 末检 HEAD | `06369c00d20e81890c8fb7992732ec35dfadfbb7`；accepted commit 仍是祖先 |
| main | `fac32ecbff9bfe792b63ee9667c8697826b631f4`，首末一致 |

逐项 expected/current/original SHA、允许变化标记与 Git 身份原件在本 label 的 `start-hashes.json`、`end-hashes.json`。`input-end` 内层及 wrapper exit=0，核查 130 个身份；没有用旧轮 HEAD 或旧 freeze 替代本轮输入。

HEAD 由并发 root/F3 checkpoint 前进，提交差异仅为非冻结 docs 与授权并行的 F3 五 utils：`ab_ocr_compare.py`、`analysis_sample_inputs.py`、`build_semantic_digests.py`、`docling_schema_regression.py`、`verify_missing_tokens.py`。提交差异逐条保存在 `end-hashes.json`，其中没有冻结路径；我没有写这些文件。末期另外观察到 root 的 queue/sequence/handoff 文档工作树改动和 F3 review/README 裁决新文档，均非冻结输入，只记录并发状态，未恢复或覆盖。已有 draft PR197 与用户 merge 边界保持；本轮没有访问或变更 GitHub 状态。

报告落盘后的额外交付观察：HEAD 为 `a629e581b8a6c16bd946cda626e3470faa0ed59a`。相对上述末检 HEAD，仅新增七个非冻结 F3/root/review 文档提交路径；branch/main 保持、没有冻结路径或其它源码提交。独立核查 exit=0，完整路径见 `concurrent-delivery-head.json` 及同名 command/stdout/stderr。未覆盖首末原件或重新定义 freeze；`delivery-integrity` 同时核实 65 current 仍为 end-hashes 的字节，65 originals 仍冻结、八文件无排除覆盖率达标。

## 实际 owner、调用链和实施

| Owner / 允许 production | 实施行为与语义边界 |
| --- | --- |
| `storage/source_integrity.py` 与 `storage/__init__.py` | 唯一新增无 payload 的 `SourceIntegrityRepairRequiredError`，固定安全内部文字及正常 public export；原 classifier、版本身份、三轮预算、repair/发布政策不改 |
| `pipelines/cn_download_workflow.py` | CN abort cause 封闭为三类型并构造验证；mid-filing 只优先捕真实 Preflight/RevisionConflict，登记一次安全 failed 行后带已确认行中止；postrepair classifier、新 RepairRequired 产生点与三类型 catch 位于同 try，保原 cause 对象与 chain |
| `pipelines/sec_download_workflow.py` | 新私有 SEC abort 持原 cause 和现成确认行快照；single-filing pair catch 覆盖四抛点，当前无终态时恰一 failed 行，保前缀且不补 tail；postrepair 三类型同 try/catch，新损坏不再冒称 churn |
| 同 SEC workflow 的共用 builder | 正常与 abort 共用原八键计数及结果组装；正常显式 cancelled/ok，abort 显式 ok。完成日志仍由正常 caller 读取本次 result summary；builder 无完成日志/事件，abort 无 PIPELINE_COMPLETED。早期取消 helper 不重构 |
| `pipelines/sec_pipeline.py` | collector 原样传播 SEC abort；adapter 只捕自己的 abort，严格复用原 `_summary_from_pipeline_result`，不从日志、事件或库存反推确认行；wrapper 保存同 cause 和 typed summary |
| `ingestion_runtime.py` | 唯一安全 failure mapping 区分 churn 与仍需 repair；direct error_kind 从同 public classification 投影；wrapper/job typed catch 同步三类型；job 仍仅存现有安全 message 与 typed result_summary |
| `direct_events.py` | 保原四 Preflight reason，增两个获批 sibling reason；public serializer 六字段不变，无新 status/schema/source enum |
| `cli/output.py` | 仅消费一次公共 JSON，以 JSON 编码机械展示现有字段；布局、输出通道和 execution 日志提示保持 |

实际调用链：真实 Fs classifier/独立 writer → 原 CN/SEC single-filing owner → 各自 workflow 确认行与 typed abort → 原严格 adapter projection → runtime 公共 failure/typed result → direct RESULT、job 已有持久字段、CLI 和 process observation wait。Service/wait 生产源码只读；wait 读 process observation，不读 job、不解析 message。stage 发布、rollback、manifest 登记与 company commit 仍由原 storage owner 完成；成功文档以真实仓储确认事实为准。

两新增公共输出精确为：

| 原 cause | reason / message / retry_hint |
| --- | --- |
| RevisionConflict | `source_revision_conflict`；本地来源版本持续变化，本次下载已停止；请等待其它来源写入完成后重新发起下载；若仍失败，请检查并发写入。 |
| RepairRequired | `source_repair_required`；本地来源仍需修复，本次下载已停止；请检查并修复工作区来源状态后重新发起下载；不要仅按并发冲突反复重试。 |

两者 classification 均 storage，source 取原请求，transport_category=None。原四 Preflight 分类、未知/provider/configuration/OSError 规则沿原公共 owner。初始整体 preflight 裸 typed 抛出使用请求级零候选摘要；single-filing 已开始后中止保确认前缀。SEC 私有 snapshot 的 ok 表示原行快照形状，操作失败由异常和公共 RESULT 表达，未伪造完成事件。

## Accepted findings 与真实验证

| 项目 | 实施及测试证据 |
| --- | --- |
| F6 主体：CN/HK churn 与 repair 分离 | 真实独立 Fs writer 三轮发布 identity 变化，`test_cn_real_churn_preserves_success_prefix_and_stops_tail[direct/job]` 验证 down=1/failed=1/total=2、原 cause 链与 tail 未执行；HK 原 1/2 轮成功保持，3 轮迁移 typed abort |
| F6 原公共缺分类 | `test_download_integrity_failure_closed_source_projection` 穷尽 SEC/CNINFO/HKEXNEWS × 四 Preflight + 两新 cause + unknown；原 `test_direct_download_preserves_every_preflight_reason` 保 map keys 全集合、四参数 public projection，只把 reason enum 旧全集迁移为原确切四元素子集，新两值独立验证 |
| F6-P1 SEC 必修 | 真实 success→6-K rejected→第二 identity churn 三轮→tail 未请求；`test_sec_real_identity_retry_budget_and_abort_prefix[1/2/3]` 保原预算与 rollback，新 payload 1/2 轮成功，3 轮 typed abort，total=3/down=1/rejected=1/failed=1/skipped=0；首 manifest COMPLETE 与已发布 rejected registry/blob 原字节保全 |
| A1 正常/abort status 与日志 owner | 三个真实 loop checkpoint 取消（首文档前、文档间、single-filing 开始后）及 repair clean 后取消都断 cancelled 和原确认事实；原早期 helper 取消测试保持。真实 abort adapter 链断私有 ok、无完成事件、无“美股下载完成”日志 |
| A2 postrepair 三类型同 try | CN 原真实第二 selected 损坏节点及 direct/job 节点迁移新 cause，断原 wrapper cause 对象/chain、首 repair 行；SEC 真实同长度 digest 损坏证明 revision 未变而 classifier COMPLETE→REPAIR_REQUIRED，断新 cause、首 repair 成功、fail=0、company 未提前、tail 未请求；四真实 postrepair Preflight 原 reason 都保确认前缀 |
| A3 SEC 四真实抛点与迁移 | single-filing 原 238/505 为 UNSAFE_PUBLICATION，275/383 为 SELECTED_REJECTED_REPAIR_REQUIRED，源码只读。真实 Phase A/Phase B stream 节点断一 failed、原 chain、前缀和 tail 守恒；原 6-K repair-rejected 节点迁移 typed abort，保零 mutation/company/registry/payload 全断言；275 用真实仓储注册表与真实单文档 owner 独立验证，见下述边界说明 |
| A4 CN Phase B 与 private/public 边界 | 原 `test_cn_phase_b_real_preflight_aborts_with_confirmed_prior_filing` 只迁移安全行 reason；原 Preflight/UNSAFE、success+failed 行、cause、恰一 FILING_FAILED、无完成、commit=2/rollback=1 和首 meta/第二 unsafe target 断言均保留；CN 私有 abort 固定安全文字保持，由 runtime 原 cause 决定 public reason |
| Strict / 封闭 contract | SEC owner 实产 snapshot 逐项缺失/错误 ticker、document_id、form_type、filing_date、report_date、status、filters、overwrite 均由原 projection 拒绝；三个私有 wrapper 均接受原三类型并保存同对象，拒绝集合外异常，不扩 parser/schema |
| Direct / job / CLI / wait | `test_sec_integrity_failure_public_and_job_conservation` 真实 adapter/runtime 两场景×direct/job；direct validator 原 terminal_result 同对象；CLI output 和主入口用真实 adapter、正确 keyword-only/date/forms 参数，exit=1、安全公共字段和摘要同源；wait 真实 prepare/activate/poll RESULT→observation，failure JSON/counts/hint exact，class-level job read 拒绝 guard 证明无 job reader |

275 的动态验证边界：真实顶层在进入单文档前已按同 registry 预筛选拒绝候选，因此不能把登记拒绝的候选硬塞进顶层 stream 冒充可达。`test_sec_registry_single_filing_real_preflight_preserves_published_state` 从实际持久化读取 registry，真实损坏目标后执行真实 single-filing owner，得到原 SELECTED_REJECTED_REPAIR_REQUIRED，无网络/commit/rollback、无事件，meta 和已发布 registry 保全。顶层 pair catch 对其同类型保持封闭；383 的真实顶层案例已动态验证该类中止与前缀。没有为测试改预筛选、注入假异常或反向修改发布政策。

所有新增场景明确使用离线合成 HTML/descriptor，真实 Fs 仓储共同 core 与独立 writer；真实日期排序、typed date 和 keyword-only 接口。未调用真实 Docling/PDF/外网，没有重跑 PV01 临时取证，没有写旧 probe/日志。普通文档失败继续、普通 repair failure 原 break、已发布拒绝及独立 company 事实、SC13/6-K 政策均由原回归保护。

## 最终验证与八文件覆盖率

全部正式验证先激活 `.venv`。每条验证命令独立保存 `<name>.command.json`、`<name>.stdout.log`、`<name>.stderr.log`，wrapper 退出码等于内层退出码；原件均在本轮 label 目录。`command-ledger.json` 登记 argv、exit 与双流 SHA，登记命令自身返回后另外保存三原件。stdout 使用 `-s` 保留动态 typed 摘要/原快照、public failure、job record、wait 与 CLI 输出；工具显示截断不影响完整原件。

ledger 包含写入时已完成的 40 个命令；其后交付完整性、并发 HEAD 观察与最终 diff/hash 核查各有独立同名三原件，不覆盖旧 ledger。`delivery-artifacts.json` 保留首个报告版本身份；最终报告身份另存 `delivery-artifacts-final.json`，两个原件不互相替换。

| 验证原件 basename | 实际结果 |
| --- | --- |
| `affected-first` | 原十文件受影响测试 1276 passed，exit=0 |
| `affected-coverage-e1` / `affected-coverage-final` | 各 1335 passed，exit=0，八生产范围覆盖数据完整；3 条既有 edgar deprecation warning |
| `sec-final-recheck` | 最终 SEC production 局部变量更名后，两 SEC 文件 158 passed，exit=0，append 到独立复制的 coverage 数据，不覆写原数据 |
| `sec-owner-final-additions` | 新 Phase A、严格 report_date 和前缀 payload 断言，12 passed，exit=0 |
| `sec-registry-owner-final` | 真实 275 owner 节点 1 passed，exit=0 |
| `affected-delivery-isolated` | 最终同版原十文件 **1338 passed / 3 warnings / exit=0**；59.47 秒，显式 cache_dir/basetemp 均在本 label |
| `pyright-delivery-isolated` | 完整 `python -m pyright --stats dayu/ tests/ utils/`，**783 files checked、2282 parsed、0 errors / 0 warnings / exit=0**，35.547 秒 |
| `pyright-script-ledger` | 本轮唯一新 Python 临时文件 `evidence_runner.py`，显式相对 include、exclude=[]、strict；**1 file checked / 0 errors / 0 warnings / exit=0** |
| `coverage-unexcluded` | 从实际 coverage 数据清空全部默认排除规则后，对精确八文件独立生成报告，exit=0 |
| `input-end` | freeze 不变，逐件 65 current+65 originals 身份合同满足，exit=0 |

最终八文件逐项覆盖率采用 `coverage-no-exclusions.json`，各文件 excluded_lines=[]，没有用默认 Protocol/ellipsis 排除提高百分比；没有修改 repo coverage/type 配置、ignore/exclude、依赖或生产 pragma。数据来自完整 1335 用例与最终 SEC 158 用例合并，之后只有测试增补、生产字节未再变化；最终 1338 集额外复核当前测试版本。不能把 aggregate 替代逐件结果。

| changed production file | covered / statements | 无排除 percentage |
| --- | --- | --- |
| `dayu/fins/storage/source_integrity.py` | 120 / 129 | 93.02% |
| `dayu/fins/storage/__init__.py` | 15 / 15 | 100.00% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 250 / 272 | 91.91% |
| `dayu/fins/pipelines/sec_download_workflow.py` | 251 / 289 | 86.85% |
| `dayu/fins/pipelines/sec_pipeline.py` | 406 / 470 | 86.38% |
| `dayu/fins/ingestion_runtime.py` | 2190 / 2412 | 90.80% |
| `dayu/fins/direct_events.py` | 398 / 447 | 89.04% |
| `dayu/cli/output.py` | 166 / 195 | 85.13% |

`.coverage-final-recheck` 与 `coverage-final-verified.json` 保留默认排除口径的原数据/原报告；无排除报告另存，不覆盖它们。SEC 子集 append 的 stderr 有 CLI 模块本次未导入 CoverageWarning，已披露：其完整测试执行数据已在复制的 coverage 文件中，最终独立八文件报告实际包含 CLI 166/195；未将该子集本身声称为 CLI 覆盖测试。其余 warnings 为三条既有 edgar 弃用提示与 pyright 新版本提示，没有安装或更改依赖。

## 所有非零、恢复和证据限制

以下正式验证非零原件全部保留，不以随后成功覆盖。名称均为本 label 下的 command/stdout/stderr basename。

| 非零命令 | 原结果 / 直接原因 | 最小恢复及证据 |
| --- | --- | --- |
| `pyright-product-first` | exit1，5 errors；CLI public JSON 值直接传 str-only helper | 改 JSON 编码机械显示，最终完整 pyright0 |
| `sec-owner-new-first` | exit1，1 failed；测试猜不存在的 pipeline maintenance property | 用真实 Fs maintenance API，后续 owner tests 通过 |
| `sec-owner-new-second` | exit1，1 failed / 9 passed；registry fixture 在来源损坏后提交，被真实 Fs guard 拒绝 | 在损坏前真实提交 registry，不改变 storage guard；四 postrepair 原因通过 |
| `pyright-product-second` | exit1，2 errors；JSON list invariance 与 adapter checker 为 None | 显式 `list[JsonValue]`、真实非取消 checker，无 cast/default 绕过 |
| `owner-new-third` | exit1，26 failed / 23 passed；runtime fixture 用错 source/overwrite 参数，strict case 错认 internal_document_id 是原 public projection 必消费字段 | 使用真实 request 接口；strict case 验证原已消费字段，不扩既有 schema/helper |
| `owner-new-fourth` | exit1，22 failed / 27 passed；新增块误置原测试尾部导致 jobs_root NameError | 恢复原尾断言、把新增块放文件末；`owner-new-fifth` 48 passed |
| `pyright-product-third` | exit1，1 error；optional public failure 未缩窄 | 显式非 None 断言，完整 pyright0 |
| `public-entries-first` | exit1，4 failed / 4 passed / 2 teardown errors；试 patch frozen job instance 与 CLI --forms 误用逗号单值 | class-level typed read guard；真实 nargs 多参数；`public-entries-second` 8 passed |
| `pyright-product-fourth` | exit1，1 error；测试 JSON message 未缩窄为 str | 明确类型断言，完整 pyright0 |
| `pyright-final` | exit1，1 error；SEC 同函数 rebuild 路径旧 JsonValue 局部变量与新 dict annotation 同名 | 更名为 confirmed_filing_result，未改变事实；158 SEC 复验和完整 pyright0 |
| `pyright-scripts-first` | exit1，7 errors；临时 runner 的 JSON strict Unknown | 明确递归 JSON 类型与 Mapping/list 收窄，保冻结校验，不用 Any/cast |
| `pyright-scripts-final` | exit1，1 error；已 typed str key 的冗余 isinstance | 删除冗余检查；最终脚本1-file pyright0 |
| `sec-registry-point` | exit1，1 failed；真实顶层预筛选移除拒绝候选，未进入预期单文档抛点 | 保产品预筛选；改为真实 275 单文档 owner 节点，真实 383 顶层节点负责同类 pair-catch 前缀验证 |
| `sec-registry-owner-recovered` | exit1，1 failed；新增真实 FilingRecord 缺 import，尚未执行 owner | 读取真实类型与观察器接口后补 import，使用现成 commit/rollback counters；`sec-registry-owner-final` 通过 |

只读探索中的非零也披露：若干 rg no-match exit1；猜测不存在的 SEC prefilter/maintenance 文件路径的 rg exit2；一次以 -- 开头的 rg pattern 未加分隔符 exit2；末期查 coverage 配置时 `.coveragerc`/`setup.cfg` 不存在，rg exit2，实际配置以真实 `pyproject.toml` 与 coverage API 验证；一次 `ps` 被 sandbox 拒绝，exit127，未提权或操作进程。两次 apply_patch anchor 不匹配未写文件，重读准确位置后恢复；一次 heredoc 意外残留 `+PY` 在运行测试前发现并删除。上述早期/探索记录在工具轨迹，不伪称每个 read 都有独立文件双流；所有正式验证通过 runner 独立留存真实退出码。

`affected-delivery` 已实跑 1337 passed/exit0，但遗漏显式 pytest basetemp/cache_dir，不能作为本轮临时目录隔离证据；其原日志保留。补 275 owner 节点后，`affected-delivery-isolated` 使用本轮显式目录重新实跑最终1338集，作为交付验证。没有删除外部临时目录或其它并发任务文件。

internal_document_id 并非既有 SEC public projection 消费字段的观察，及真实 registry 提交 guard/预筛选造成的 fixture 失败，均已在本文登记交 root；没有把测试假设伪造为产品 finding，也未扩 schema、放松 parser 或添加 fallback。

## README、范围与残余去向

已按实际职责读取并必要修改三 README：根 README 只补用户恢复动作与失败摘要含已处理事实；`dayu/fins/README.md` 说明唯一 public owner、CN/SEC abort/取消边界和 job 当前 message+summary 能力；`tests/README.md` 只写已落地的真实仓储/四入口测试。没有分层/装配变化，不触 `dayu/README.md`、Engine/Host/Config 文档。修改源码/测试限制为 freeze 允许清单；其余 source、single-filing、storage core、Service/status contract、F3 utils、plan/goal/旧报告/root queue/handoff/registry/config/dependencies/freeze/originals 都未由本作者写入。

| 残余 / 非目标 | Owner 与去向 |
| --- | --- |
| 完整 structured reason durable | 既有独立 `fins-download-job-reason-code-persistence`；job contract/store owner，待 root/用户 goal；本轮只存原安全 message+summary |
| publication indeterminate | storage 既有独立目标，由 root 安排，未纳入本 slice |
| early cancel 空行计数差异、两 rejected helper 统一 | 原独立 SEC workflow/结果协议目标，需独立 goal；不重构既有 helper、不重开 F7 |
| F5 Q1 | 等用户业务选择，未代选；其它 F3/F4/F7 状态由 root 管理 |
| #198 / 成功 manifest / SC13 / 6-K / company / stage | 原已裁 owner 与策略保持，不重开，不从日志/private payload 推断新事实 |
| 最终真实完整 CLI CI→upload_material oracle/scenarios/readiness | 所有获批修复完成后由 root 对最终版安排；本轮离线 unit 验证不是该终点，未补造已删除旧 Raw |

交付物为当前工作树候选、本文、独占临时目录全部验证原件。无新阻塞业务/schema/owner 选择；新观察均已登记，没有静默扩 scope 或 defer accepted 必修。已停止实施，由 root 核收实际 diff/身份/测试原件并安排后续双审；本作者不接受自身实现、不推进其它 gate、不提交。
