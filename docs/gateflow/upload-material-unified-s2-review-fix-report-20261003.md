RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-1a87183e

# S2 同版双审 accepted findings 集中 fix 候选报告

本轮 R02/R03/R04 和 create-on-tombstone 最小回归候选修复完成，必要验证通过；**不赋 S2 pass、不改写 root finding 最终状态**。下一入口是 root 核收本轮实际轨迹及证据后，同一候选版本的 MiMo/ds-flash 双路 re-review。本轮按指令停止，不派发评审者、不 stage/commit/push/merge、不修改 PR、不进入其他 gate。

表头 provider 是本轮绑定任务名；当前会话未提供可核验的实际 model event，所以 MODEL 如实为 unknown。CANARY 内容由工具实际读取本轮指定文件，逐字写入；不能用该标签、provider、旧轮次报告或 canary 推断实际模型。root 如需确认实际执行模型，须读取自身托管 runner 的实际 event。

## 绑定身份与冻结审计

- label：`upload-material-unified-s2-review-fix-sol-20261003-01`，唯一分支 `codex/upload-material-oracle`。
- HEAD：`f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`；main：`fac32ecbff9bfe792b63ee9667c8697826b631f4`；首末一致。
- 绑定目录：`workspace/tmp/upload-material-unified-repair-20261002/concentrated-s2-review-fix-01/`。首核 9312/9312 input、9292/9292 protected 全部匹配。input manifest SHA `7621b398dc74e0b4787d7088827078203431d28ae4e8e1aa6e9c9077df93b5a1`；protected manifest SHA `bdf9e87c2f9e4259671300bad5c86688c12538600c24a1c02b808d7f1f1f367d`。
- 最终 root 裁决 SHA `f6034337105eaf73355b63ea7775d2e397d021f486eca449ccfacb390ee7b569`；accepted plan SHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`。
- 已完整读取 AGENTS、Gateflow review/fix、plan §6 与 V7–V14、两份原 review、S2 C01–C07/R01/R01-evidence/execution/T01、findings register 和双审最终裁决。原评审在途文字作为历史记录保留，没有重裁业务或重派原版评审。
- 已有 60 件候选保留。本轮仅 12 件白名单 delta：7 产品、3 测试、2 README。原计划/control/root 裁决/旧报告/另一评审/历史 Raw/旧探针均未改。末核 `protected_drift={}`，所有 input delta 均在白名单；暂存 diff 为空。
- 独占票据根下文记为 `T=workspace/tmp/upload-material-unified-s2-review-fix-sol-20261003-01/`。首核 `T/initial-audit.json`、`initial.diff`、`before/`；末核 `T/final-input-protected-audit.json`、`final-git-state.json`。tracked 整体候选 diff SHA `71255a81728f389b7678062c8016ee11d39f0e0f644257f0cf3fc9c7c5f416e5`；untracked 产品全文由逐文件 SHA 和 AST 索引覆盖，不用 tracked diff 代替全文。
- owner 测试完成后和最终报告前分别发现/核对本 HEAD 的 S2 root 文档；没有新裁决文件或既有裁决漂移。票据 `T/root-refresh-after-owner.json`、`root-refresh-before-report.json`。

## Findings 与实现边界

| root finding | 合并来源 | 本轮候选状态与证据 |
| --- | --- | --- |
| US2-R02 | DS01 / MiMo F1 | 候选已修，待同版双复审。公共身份构造唯一按 name 规范 tuple，D/storage 共用；b/a、primary=a 的真实 D 内容/metadata/skip 候选与完整 Fs 身份一致，竞争 skip 及普通文件事件保 b/a。三轮生产 Docling/Fs 多文件双 CLI 正常终态。 |
| US2-R03 | DS02 / MiMo F3 | 候选已修，待同版双复审。D 引用既有 FISCAL_PERIODS、去重复 FiscalPeriod import；R 复用本模块状态常量，metadata_updated 必要常量在原 owner；publication 复用已依赖 R 的 auto 常量。公开 Literal/schema 与测试真实值断言保持。 |
| US2-R04 | MiMo F2 | 候选已修，待同版双复审。只读 protocol/core/public Fs 的 required expected_source_state 接受显式 None，公司阶段取消独立 fresh 材料读；仅 auto 非 overwrite 免该阶段源条件。真实 Fs 修前反例与修后票据、已有公司真实双 CLI 窗口通过。 |
| MiMo OpenQ tombstone create | 最终 root 已批准最小测试 | 新最小 owner 回归锁非 overwrite create 的原 FileExistsError 拒绝，材料保持 tombstone、全部业务字节不动。没有新 oracle、代码、typed reason 或自动 restore。 |

R02 动机是同一业务身份两端的 originals tuple 顺序不一致导致 exact arbiter 误冲突。`MaterialUploadPublicationIdentity.__post_init__` 在原完整性、typed descriptor、空集合、重复 name 校验之后建立规范 tuple；storage 移除该身份投影的重复排序。arbiter 保原 exact 相等及既有版本处理，不做集合比较、重读、fallback、过滤业务字段或宽化相等。primary、roles/fingerprint、original hash/size、amended/company/version 合同保持。

身份排序不承载输入事件顺序。D 的资产 mutation 继续按其 pending original assets 输入顺序构造竞争 skip 事件。metadata 候选最窄增加 required 私有 `file_events` tuple，由原已校验输入生成，在 metadata 竞争 skip 时原样消费；它延续既有文件事件语义，不新增业务身份、持久 schema 或公开字段，不是第二排序真源。该私有构造只有 D 内一处真实 caller，已显式迁移；没有默认值或兼容分支。

R04 动机是独立 read→validate 两个 guard 间的合法材料发布被提前当成 source conflict。只读 validator 的 None **必填、无默认值**，只免该次源比较，不表示 MISSING；仍沿原 recovery→identity→publication 锁序、原 alias owner，严格比较公司全快照，返回完整 current state。非 None 仍复用原完整 source 条件 helper。公司阶段只有原 auto 非覆盖传 None，其余传 observed；initial company=None 等价 no-op 仍归 C01/R01 的公司 commit owner。registration、commit/final guard、D skip/redelete 的 required 完整源条件和异常传播不变，没有新锁/getter/API/状态、generic catch/retry 或公司时间猜测。

先前 C01–C07/R01/T01 候选不回滚、不重新裁决；本轮只迁移 C01 测试原来的已删除 read 暂停点：B 在 A writer 前实际完成公司阶段，A 的真实公司 commit owner 严格等价 no-op；增加“公司阶段不得独立 fresh read”的断言。已有失败覆盖均保留。

## owner 测试与直接根因票据

- `test_publication_identity_constructor_owns_canonical_original_order`：b/a 输入 tuple 不变、构造及 replace 同一规范身份、primary 非首项、空/重复集合拒绝；不同 primary/hash/amended 仍不等。
- `test_unordered_multifile_real_candidate_and_input_events` 三路：真实 D 准备候选→完整 Fs winner→loser skipped，内容路双 old MISSING；candidate/storage 身份 exact 一致、primary=a、所有原件/派生资产完整；winner 后业务 bytes、完整 source/company/revision/time 状态零差异，竞争及普通 request 文件事件均 b/a。
- `test_multifile_different_real_candidate_remains_conflict`：实际准备不同 primary/角色指纹、不同 original 内容、不同 amended 的候选，保持 conflict 与零材料修改。原公司/alias/时间/字段漂移、坏 winner、真实 I/O、取消、COMMITTED 后释放故障、不重试/不回读测试继续保留并通过。
- state owner 新测试：显式 None 返回实际 COMPLETE；具体 old MISSING 源条件仍拒漂移；非法 None 不能绕过 writer required 登记。公司 name/updated_at/resolver/aliases/缺席完整快照漂移仍拒，真实另公司 alias 占用仍在原 owner 优先拒。
- `test_existing_company_old_missing_interleave_keeps_source_owner`：A/B 同已有公司全快照、同 old MISSING；A 公司 guard 前 B 完整发布，无 A writer 等 B。auto 非覆盖到 writer 返回 skipped；create 非覆盖、auto overwrite 保具体 observed 状态并 source conflict；B 后业务 bytes 零差异。
- `test_create_on_tombstone_keeps_storage_rejection`：真实发布/删除/受理/准备/材料 executor，在真实 storage create 处捕获既有 FileExistsError，tombstone 未恢复、全部业务字节保持。市场入口原失败投影不变。

`T/r04_interleave.py` 与 `r04-interleave-evidence.json`：先导入本轮首核保存、与 input manifest SHA 完全相同的**修前公司阶段片段**；其非 None validator 路径仍是未改变的严格 source helper。真实 Fs 在 A 独立 read guard 返回后完成 B 发布，原公司不变，产生 `SourceIntegrityRevisionConflictError → FinsUploadFailureError(source_publication_conflict)`，原 traceback 保存。修后 A 只读公司 guard 前完成 B，返回 actual company，真实 D/材料 writer 得 skipped，业务 bytes 和完整状态相等、包装恢复。这是受控 converter 的 owner 定向证明，**不是旧整版 CLI、生产 Docling 或历史 provenance 证明**。副本仅在新 tmp 技术导入，未创建 Git 开发树。

## 真实多文件双 CLI / production Docling / Fs

复用原 V12 `barrier_launch.py`、`cli_race_final.py` 技术 harness 的新独占 copy。每轮新 label/base，真实 console owner、正常 stdout/stderr、debug log 分存；stdin DEVNULL、启动单调时间、owned Popen PID、双实际 wait、timeout 与 restore 保存。没有生产 hook、mock converter、fake success 或绕过 CLI。

所有请求 `files=(b.txt,a.txt)`，真实 `--primary a.txt`；ready 明确断言原请求顺序及非首项 primary。双方在真实 admission 返回边界观察同 canonical 身份、old MISSING/revision=None，无材料 meta/identity。fresh 轮公司 None；已有公司轮通过**先运行真实 seed CLI**发布其他材料形成真实公司，全公司快照同版 non-None。

| 独占轮次 | 真实 CLI PID a/b | 实际退出 a/b | 终态 a/b | winner→loser diff |
| --- | --- | --- | --- | --- |
| `T/cli-multifile-sequential/` | 43639 / 43640 | 0 / 0 | ok / skipped | `{}`，全部 portfolio bytes、source 业务字段、revision/company/time/版本 |
| `T/cli-multifile-simultaneous/` | 43692 / 43694 | 0 / 0 | skipped / ok | `null`，没有独立中间快照，不冒称零 diff |
| `T/cli-existing-company/` | 43712 / 43713 | 0 / 0 | ok / skipped | `{}`，含 seed 公司及其他材料所有业务字节 |

已有公司 seed PID 43693 实际 exit0。该轮先放 B 的真实 admission，使其停在 `FsMaterialUploadStateRepository.validate_material_upload_state` 的原 guard 调用前；保存 required source_condition=None 与完整预期公司。此时未持 writer。再放 A 完整发布并 actual wait；再放 B 公司 validator，真实 owner 严格校验原公司，B 到材料阶段 writer verified skip；没有 writer 相互等待。`gate/b.company-validation.ready.json` 保存位置与 PID/company 条件。

每轮 `before.json`、`winner.json`（可观测轮）、`final.json`、`business-diff.json`（可观测轮）、`actual-terminal-exits.json`、`trace.json`、`result.json`、`durable-query.json`、`owned-process-tree.json` 和 `source-before/after.json` 完整保存。最终 canonical originals 为 a/b，主源 `a.txt_docling.json`，actual four files 为两 original+两 Docling，strict published_amended=false；每轮真实公共 Fs COMPLETE 读回。真实 job store 查询为零条 direct CLI job，而非伪造 job 成功。

另在 `T/cli-independent-receipt.json` 独立逐 module 核实际安装 SHA=每轮 source-before=交付源码；逐 original 核真实输入 bytes SHA/size=canonical descriptor，PID=ready/binding/actual wait，双 restore 且无 timeout/termination。没有仅凭 driver 自报判通过。

`gate/{a,b}.bindings.json` 证明先包装真实 admission/company owner 后 import Service/SEC/CN/workflow 真消费者，from-import binding 实际一致；同时保存实际安装 module path/SHA，含 D、protocol、material core/public Fs、integrity。每轮安装 SHA 与该轮 source-before 一致，source-after 零漂移；双方 restore 标记和 wrapper finally 的原 owner 身份断言成立。父/CLI PID 已知；生产成功清理不暴露 Docling 子 PID，保 **unknown**，不扫描 ps/pgrep/kill0 或按 provider 猜模型/进程。

## 验证命令、实际终态与覆盖

每条验证先 `source .venv/bin/activate`，再用本轮 `T/evidence.py` 的 own Popen/actual wait 采集。各票据目录保存真实 argv、cwd、解释器、独占 COVERAGE_FILE、stdout/stderr、owned-process、actual-exit 与 source-before/after/delta；测试禁 cacheprovider，独占 basetemp/JUnit。没有把测试内部失败伪为外层 pass。

| 票据 | 实际结果 | 说明 |
| --- | --- | --- |
| owner-01 | exit1，53 pass / 2 fail | 首轮失败完整保留，下节说明恢复。 |
| owner-02 | exit0，80 pass | 修正 owner 测试迁移和新增测试后真实终态。 |
| types-01 | exit0，0 errors/warnings/informations | 第一次 full pyright。 |
| r04-interleave-01 | exit1 | 未进入产品，技术脚本 import 路径失败，完整 stderr 保存。 |
| r04-interleave-02 | exit0 | 修正启动 PYTHONPATH，保存修前确定反例及修后 skip。 |
| harness-types-01 | exit0，0 errors | evidence/barrier/CLI/R04 四个技术脚本显式 pyright。 |
| cli-multifile-sequential-run | exit0 | driver 实際 exit0，另存双 CLI actual 0/0。 |
| cli-multifile-simultaneous-run | exit0 | driver 实際 exit0，另存双 CLI actual 0/0。 |
| cli-existing-company-run | exit0 | driver 实際 exit0，seed及双 CLI actual 终态分别保存。 |
| final-regression-01 | exit0，**2017 pass / 1 skip** | JUnit tests=2018，failures=errors=0，PID43642；25 个必要影响模块一次合并，未重跑旧35模块宽 suite。 |
| final-types-01 | exit0，0 errors/warnings/informations | 最终产品/测试字节同版 full pyright；source_delta={}。 |
| final-audit-01 | exit0 | refs固定、input delta仅白名单、protected0、无新 root 裁决。 |
| final-diffcheck-01 | exit0 | git diff --check。 |
| audit-script-types-01 | exit0，0 errors | final_audit.py 新技术脚本显式 pyright。 |

最终回归选择根据实际改动的 identity/完整性/只读 guard、D 三种 prepared 候选及事件、R 结果闭集、真实市场/filing/direct/CLI消费者与逐文件覆盖风险合并；既有 download/processor/calendar 等未改源不为报告格式机械扩大。精确 argv 见 `T/final-regression-01/command.json`。最终测试、full pyright、三轮 CLI 对应同版产品 SHA，运行中 source_delta 均空。唯一 skip 为既有可选 PDF 集成 `test_real_docling_upload_service_conversion_when_enabled`，不能称通过；真实文本 Docling 和本轮生产双 CLI 已实际运行。

| 实际修改产品 | statements covered / total | 覆盖率 |
| --- | --- | --- |
| `storage/repository_protocols.py` | 341 / 402 | 84.83% |
| `storage/_fs_source_integrity.py` | 557 / 630 | 88.41% |
| `storage/_fs_material_upload_state_core.py` | 74 / 76 | 97.37% |
| `storage/fs_material_upload_state_repository.py` | 23 / 23 | 100.00% |
| `pipelines/docling_upload_service.py` | 617 / 683 | 90.34% |
| `pipelines/material_upload_publication.py` | 91 / 98 | 92.86% |
| `ingestion_runtime.py` | 2277 / 2506 | 90.86% |

表内路径均相对 `dayu/fins/`。覆盖来自本轮实际 `final-regression-01/coverage.json`，重算票据 `T/actual-modified-product-coverage.json`；七件全部 ≥80%，不是沿用旧版覆盖。

## 非零、compound 内失败与恢复

1. owner-01 PID43496 实际 exit1，53 pass/2 fail。新增 tombstone 测试误在市场返回层期望 FileExistsError，市场原异常投影并不抛该异常；迁到真实材料 executor→storage create owner 捕获原 FileExistsError。旧 C01 测试的 read wrapper 未触发，因为本轮按 R04 删除该 fresh read；改在 B/A 真实公司 commit owner 的 writer 顺序证明等价 no-op，并断言不能独立 fresh read。没有产品 fallback、宽化异常、删测试或 fake success。owner-02 80 pass、最终 2017 pass/1 skip 恢复；原失败 stdout/stderr/JUnit/actual-exit 保留。
2. r04-interleave-01 PID43580 actual exit1，`ModuleNotFoundError: No module named 'tests'`，未进入 owner/无业务根创建。新标签 r04-interleave-02 显式 repo PYTHONPATH 重新执行真实副本/仓储，actual0；没有覆盖失败票据。
3. 两次探索性复合读取中，rg 查询不存在的猜测路径 `dayu/fins/pipelines/upload_events.py`、`dayu/fins/domain/company_identity.py`，原工具结果均含 `No such file or directory`；后续其他读取成功使 compound 外层 exit0，**内 rg 的实际退出码未独立采集，不能称该 compound 全部0**。已用真实 `UploadFileEventPayload` 定义及 `ticker_normalization.py::CompanyTickerIdentity` 源码定位恢复；无修改或测试语义影响。
4. 最终 pytest 尚在途时，一次 `test -f .../actual-exit.json` 票据就绪探测 outer exit1；不属于测试退出。随后对原 managed session actual wait 得到 exit0，JUnit/actual-exit 独立核收。未因慢中断测试、未杀 Agent、未换版本。

本轮没有终止/kill 子进程、timeout、Agent 派发、全局进程查询或覆盖失败/历史 Raw。修前反例中的 expected conflict 是负向断言成功，不混作产品已修或整版旧 CLI 成功。

## 文件 SHA、AST/diff 与 README

完整逐件 before/after SHA、字节数和本轮增量 diff 在 `T/changed-files-index.json`、`T/diffs/`；产品完整 AST before/after 结构索引在 `T/product-ast-index.json`。以下为七件实际产品 SHA，均相对 `dayu/fins/`：

| 文件 | 修前 SHA256 | 修后 SHA256 |
| --- | --- | --- |
| `storage/repository_protocols.py` | `1d55f4c40b9b7bad1a2ab20e115b0f20f785fd2be5a13d0aaf2760a8901b86e3` | `93082b720613509c5b5371c62d6d7b4cd5a12ba5b6ff8bb68cde62377c10cd15` |
| `storage/_fs_source_integrity.py` | `89f7adee03e68fc434db8cbe061b8dcfb14d81c422d6079df1d04dcf8a3e67eb` | `a179edfe83fe200a7ed7ab2ad4c975644f8027bde2347fd85352f4415eb045cf` |
| `storage/_fs_material_upload_state_core.py` | `2a55d3fbd0ef021baafead223bb3509d7a836191e39c7ef9f8db19c5b20fd9f6` | `7819477a9f2653cb2f4b0c114c0461bae617325f9f7ab0e36124d5805f3fbb47` |
| `storage/fs_material_upload_state_repository.py` | `701b8e73e22153b595cc6c7736b7bed1197544320cd9538847517d459eeda2ec` | `c736cd83b0581c04e0cfcfb27e272bdc897d88ac9190f33e8b56a86026681e64` |
| `pipelines/docling_upload_service.py` | `707a9f814c7ce67ead75f625ea1f4ffda75172e29aaa2a1ce2d0ec3156dd1ad3` | `2f6efcdda8e00f45f7b0302fb4b1df50068f11d83412a05bb7bf48a089343722` |
| `pipelines/material_upload_publication.py` | `1cc7c31f2fb427e0c8aabb6772feda3f39296920a131176c3a2984816aee9c50` | `08fa979cf7843958ea37e9664271758719059cf32409c47a0564eb6728eef0c9` |
| `ingestion_runtime.py` | `7c55dd5a3e820cdd74a1470c7d790544d3b6500621a30b02b9c6fb356c1069a6` | `a8bdb6b7e2aed7e5f4ea772f6b0157d176159a7ab65cebdaa70ad3c9a895205f` |

已先读目标 README 的职责约束。Fins README 最窄写当前公共身份规范原件顺序、D 输入事件顺序、required None 公司阶段含义与 writer严格条件；tests README 写已存在的对应回归。根 README 是最终用户操作手册：本轮无参数、安装、初始化、通道/工作区路径或操作流程变化，内部身份/guard 合同不属于其职责，故未新增修改。`dayu/README.md` 不在白名单且架构分层未变。

## 分类 residual 与停止交接

- R02/R03/R04、OpenQ 最小 owner 测试：**fixed in current slice 的候选，待 root 同版双 re-review**；owner 为 storage value/guard、D prepared事件、R常量及 publication。不替 root 回写最终 finding“已修复”或 S2 pass。
- actual model provenance 未在当前会话 event 提供：unknown；**requiring explicit controller verification**，owner=root runner telemetry，不能用 provider/canary 猜。Docling 子 PID unknown 属既有取证边界，保原日志，不伪造进程树。
- 既有可选 PDF 与 Windows真实 cmd.exe验证：**assigned to later work unit**，owner=可选 PDF集成/平台CI；本轮PDF1 skip，Windows2未选入本轮回归，不称通过。
- S3/XBRL/UP-RR-T01：**covered by later approved slice**，owner=S3，不扩大本轮。
- 全部 slices+aggregate 后正式 PR review、完整 upload_material CLI CI/registry 在修复 WU closeout 后：**assigned to later stage**，owner=root/controller，本轮三轮定向CLI不是完整campaign。
- Raw EOF 可逆载体收口：**covered by aggregate/PR 收口**，owner=root，原字节/SHA保留。
- 深冻结 JSON 不可直接 dumps、私有 prepared union 消费与最窄 final-guard 白盒测试：既有接受边界/contract约束，owner=storage/pipelines/tests；没有升级为新增硬化目标。C01 initial None 不可观测历史仍非本WU目标；已有公司全快照严格保留。
- tombstone create迟拒 storage_io投影仍按既定owner边界，最小测试锁原拒绝；没有新增业务裁决。其余已分类22项 residual 的归属不扩张。

没有 scope/owner 白名单外必需缺项或关键冻结漂移；代码/验证候选完成，唯一新 durable 报告为本文件。所有原文件/root裁决保持；原始票据及新失败票据保留。本轮在此停止交 root 同版双复审。
