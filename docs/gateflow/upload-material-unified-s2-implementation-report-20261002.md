RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-d37db409

# S2 implementation 记录

label: `upload-material-unified-s2-implement-sol-20261002-01`。实际模型未由运行时事件暴露，不能以路由或 canary 推断。终态为**部分实施、依赖待总控裁决**；不是完整 S2 implementation pass、gate accepted 或 WU 完成。本轮按用户“accepted contract 不能表达则停该依赖、独立可做部分继续”的停止条件收口，不自赋 gate 状态。

## 冻结身份

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`，首 HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。计划 SHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`；input manifest SHA `3f661c072771c262235f6ab9f9b52cca56a9480647f5551565e486ae1e6892b8`。首核全部 9770 件零漂移，`workspace/tmp/upload-material-unified-s2-implement-sol-20261002-01/preflight.json`。S1接受记录已读；总控 control 为唯一首 dirty，不修改。AGENTS、Gateflow 和计划全文已读。

## Pending：US2-C01 公司初始缺席下历史不可观测

状态 `needs-more-evidence / requiring explicit root decision`，不是本 Agent 新裁业务规则。owner 为公司 commit contract 与其 storage 输入边界。计划 §6.5/§6.7 允许旧 `company=None` 的等价首次公司提交 no-op，但 §6.5/V11 又要求额外公司时间变动不能 skip。当前 required contract 没有首次公司提交 revision、意图 provenance 或 source→company 发布关联。

直接源码：`CompanyMeta` 仅 company_id/name/ticker_identity/resolver_version/updated_at；`CompanyMetaCommitIntent.expected_non_identity=None` 不携任何已有时点；`merge_company_meta_for_commit` 在 resolver 相同时保当前 published，公司 no-op 静态事实可等价。不能从 source 时间/JSON 反猜原公司时点。

真实 Fs 探针 `workspace/tmp/upload-material-unified-s2-implement-sol-20261002-01/company_history_probe.py`，票据 `company-history-probe-01/{command.json,stdout.txt,stderr.txt,actual-exit.json}`，actual exit 0。两 fresh 独占根同为 source MISSING/revision=None/company absent；三次真实公司 stage/commit/read：历史一在 T2 首次创建，历史二 T1 创建后 T2 经现公司 owner 合法 refresh、仅 updated_at 改变。最终 CompanyMeta 逐字段相同，旧 None intent 与当前公司 merge 均精确等于 current。固定提交时钟仅生成可复核历史，不替换仓储/merge/结果/提交；不是并发或 V11/V12 pass。证据 `company-history-evidence/single-create.json` 与 `create-then-refresh.json`。

精确缺项：若“额外时间变化拒绝”也覆盖从 None 观察开始的公司历史，当前冻结输入无法区分这两种历史。需总控明确：拒绝时间漂移只约束已观察已有公司，还是补足可辨识 provenance/revision owner 合同。未自行选择、新造字段、加默认或以时间推断。该依赖暂停；独立严格删除事实、健康重删 no-op 和 amended strict reader 可继续。不能以这些独立改动代替完整 V7–V14。

## 工具非零及恢复

- 读取实际 now_iso8601 定位时，`rg` 同查不存在 `dayu/fins/time_utils.py`，内部输出 ENOENT；同命令其它读取使 outer exit 0，不能掩盖该定位失败。恢复为实际 `domain/document_models.py:1152`，已确认秒精度时间 owner；未把缺失路径当产品问题。
- 第一份 README 合并 patch 的末 hunk 因整行上下文未匹配被 apply_patch 拒绝（工具失败）；复读 git diff 确认三个文档尚未改变后，拆为精确完整上下文重施并验证。未把该失败冒充成功。
- 首次读取 combined coverage JSON 时其写出进程尚在运行，inline 读取 actual exit 1 / JSONDecodeError（Expecting value）；这是依赖等待错误，不是覆盖缺失或产品错误。wait 确认 coverage-json-01 actual exit 0 后再读成功。该首次失败仅在本轮工具返回中，未虚构独立 stdout 原件；成功完整票据和 JSON 保存于本独占根。

## Pending：US2-T01 白名单外的既有材料夹具不满足 S1

补充 coverage 的只读 `tests/fins/test_fins_storage_provider.py` 回归 actual exit 1，104 passed / 5 failed；票据 `storage-coverage-01` 全保。五个失败为 `test_snapshot_explicit_source_kind_ignores_other_kind_with_same_document_id`、`test_complete_filing_and_material_commit_share_one_source_truth`、`test_read_runtime_citation_projects_provider_owned_source_types`、`test_read_runtime_citation_inventory_uses_complete_published_sources`、`test_list_documents_meta_less_corpus_coexists_with_healthy_alias_corpus`。

直接原因在材料 primary 声明缺少 `source=docling` 或声明不合法，经 S1 `validate_material_source_primary` 拒绝，早于本轮严格删除投影/重删逻辑。该 owner 函数未改，夹具文件冻结未改；不得重裁 S1 或下游补兼容。此测试文件不在 28 件修改白名单中，登记 `needs-more-evidence / requiring explicit root decision`，owner 为仓储测试夹具迁移，总控决定纳入/后续去向。失败不能被宽套件的 2011 passed 掩盖；当前不宣称全部受影响验证通过。

## 独立实施与真实改动边界

源文档 owner 先读严格 is_deleted，再处理 delete/restore；健康 tombstone 重删必须由同次 writer view 的 exact inspector 确认 COMPLETE 才无业务写，不刷新 meta/manifest/revision/时间/资产。REPAIR_REQUIRED 与 UNSAFE 不借重删修复。filing/material manifest 都由 storage helper 读取同一严格删除事实并显式传入模型，删去原 `.get(...) is True` 推断；全部 classmethod caller 已迁至两个 helper，无旧签名兼容。材料 amended strict reader 已实现并测试，但尚未接入完整发布/manifest/terminal，不能冒 V9 完成。

这些修改位于现 owner，未重算 S1 identity/role/fingerprint、未改静态准入首错、未新增下游 fallback 或默认业务值。没有添加新 stage/guard/cancel 状态机，也没有把一部分协议冒充完整 MaterialUploadStateRepositoryProtocol。后者的 company final 合同依赖 US2-C01；状态受理、D候选、八格、terminal/read 投影均依赖该完整协议和发布链，保持未实施，避免用 optional seam 继续。

§6.7 现有生产 commit caller 实读为 SEC 250/528、CN 903/1178、filing publication 859 共五处，未把第五处遗漏；本轮未迁 required material_state_repository，因为完整 material publication/repository 尚未实现。没有新 executor caller。AST 清单见 `E/caller-audit.json`；它记录实际旧 caller，而不是迁移通过票据。

本节及下文 `E/` 指 `workspace/tmp/upload-material-unified-s2-implement-sol-20261002-01/`。完整实际 diff 为 `E/delivery.diff`（11 个既有修改文件及新增本报告全文），逐件 delivery SHA 为 `E/delivery-hashes.json`；报告自身 SHA 仅在该外部清单，不自嵌循环。所有临时脚本只在 E。

| 全部既有 changed files | delivery SHA-256 |
| --- | --- |
| `dayu/fins/domain/document_models.py` | `f68b5b539a25d72972842cfd1d185a5e8e634cf02cfd5931ff5347c0724e5db1` |
| `dayu/fins/storage/_fs_source_document_core.py` | `54af91ccff22b606145578debbbb7dee5f6e14ed861d41f0b8dbbe4ca3572f26` |
| `dayu/fins/storage/_fs_source_integrity.py` | `805eda1b4e8247b4fefefd0da5a20b27f87247c624eb4d89d7e430951bb2d72f` |
| `dayu/fins/storage/source_manifest_contract.py` | `7c43a86c9577d8e1db097925c1102121d58476b9e2b9eeba7eaf1d5834db02a7` |
| `dayu/fins/storage/source_meta_contract.py` | `c4657260b8c30cf2e799eac84579bfa8c418679a7c2fc206cd505cefc6799855` |
| `tests/fins/test_fins_storage_atomicity.py` | `2dad6354ee97ddf489e61b3e211c502760d8969c7c0ec2e66ad5f5e6b21693cf` |
| `tests/fins/test_source_manifest_contract.py` | `4d027523cf4c294b7a74f0b5edfffaf5baf2c6f6daf3629d7b2296380c10ebd1` |
| `tests/fins/test_source_meta_contract.py` | `c2022ac19541a41e449e6d797662e6e31119721bb4489e9634dd7cb290cff4e4` |
| `README.md` | `7a8b9ee639fcee9684e170cf9a5101a41b2d4cd884090de391e146168a55f6c0` |
| `dayu/fins/README.md` | `e90e00186f8baeb64afc08256cf524898e4b08110cd38367fce43885b964221c` |
| `tests/README.md` | `8baf0e22111790db3e9bff98b94a94b8dcd262032037e6ee18ac284bc226891f` |

新增交付只有本文 `docs/gateflow/upload-material-unified-s2-implementation-report-20261002.md` 与 E 技术资产。根 control dirty 为总控既有变更，不归本作者。

## 验证原件、失败保全与覆盖

所有验证在唯一 workspace 先 `source .venv/bin/activate`。Python 3.11.15、实际解释器 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python`。record_run 的实际 Popen cwd 固定绝对 workspace，stdin DEVNULL；每 label 的 `command.json/stdout.txt/stderr.txt/actual-exit.json` 为新独立原件，精确 argv 不以本表摘要替代。pytest 禁 cacheprovider、每轮独占 basetemp/COVERAGE_FILE/JUnit/coverage JSON，无根 coverage 污染、依赖安装或类型抑制。

| label（E 下独占目录） | actual exit | 真实结论 |
| --- | --- | --- |
| `company-history-probe-01` | 0 | 两真实 Fs 历史、三真实 commit、当前 typed 公司精确相等；不是 V11/V12 |
| `focused-01` | 0 | 32 passed、286 deselected；严格字段/投影、真实首删/重删/恢复/再删、损坏拒绝 |
| `pyright-01` | 0 | 中间全量 0 errors |
| `final-regression-01` | 0 | 26 个实际受影响测试模块，2011 passed、3 skipped；JUnit tests=2014/failures=0/errors=0/skipped=3 |
| `final-pyright-02` | 0 | 全量 0 errors |
| `final-pyright-03` | 0 | 最后两个仅 module-doc/unused-import 清理后的最终全量 0 errors/0 warnings/0 informations |
| `probe-pyright-01` | 0 | 早期两独占脚本 0 errors |
| `audit-pyright-01`、`audit-pyright-02`、`audit-pyright-03` | 0 | 最终三独占脚本显式检查 0 errors；03包括新增逐件 coverage 审核 |
| `scoped-diff-check-01` | 0 | 本轮 11 个既有交付文件 diff check；不是全 PR Raw 收口检查 |
| `storage-coverage-01` | 1 | 104 passed/5 failed；US2-T01 未修，原件保留 |
| `storage-independent-02` | 0 | 104 passed/5 明确 deselected；仅验证独立合法分集，不能当五失败已修或 provider suite pass |
| `coverage-combine-01`、`coverage-json-01` | 0 | 含失败轮执行痕迹的中间联合；不作为最终 coverage 依据 |
| `coverage-combine-clean-02`、`coverage-json-clean-02` | 0 | 只合并 2011-pass 宽套件与 104-pass 独立分集的新覆盖文件 |
| `delivery-audit-01`、`delivery-audit-02` | 0 | 9770 输入实核：11 个允许修改，9759 受保护件零漂移；HEAD/main/branch/两冻结 SHA 保持；5prod coverage均≥80。01元数据/报告副本保全于 `E/audit-01-snapshot`，02为最终索引 |

宽回归启动后只删除完整性模块 unused import、改 manifest 模块概览，无行为变化；最终 full pyright-03 绑定这些末源码，后续独立 provider 验证也使用末源码。没有机械重复完整宽 suite。新增 helper/状态逻辑的生产改动都由对应测试验证。

最终 coverage 原件 `E/combined-clean.coverage.json` SHA `df2645fa8cc6f75aea16d4c52eb70ef4bcd198097a9506118328e02311cd591b`，结构化逐件为 `E/final-production-coverage.json`。没有借全包平均放行，失败 provider 轮不在最终联合中。

| 每件修改生产文件 | covered / statements | 实际覆盖率 |
| --- | --- | --- |
| `domain/document_models.py` | 429 / 449 | 95.55% |
| `storage/_fs_source_document_core.py` | 464 / 541 | 85.77% |
| `storage/_fs_source_integrity.py` | 546 / 589 | 92.70% |
| `storage/source_manifest_contract.py` | 8 / 8 | 100% |
| `storage/source_meta_contract.py` | 25 / 25 | 100% |

宽 JUnit `E/final-regression-01.junit.xml` SHA `a23187fd27058d968354ee2dc106066734b7bf0d9f08fdfa24d68929fa6da1b1`。3 known skips：两个 `requires real cmd.exe`（CLI 模块 1205/1265）；一个旧真实 PDF 集成开关未设置（Docling integration 模块54）。文本 Docling 集成实际执行。104-pass 分集的5 deselected 是 US2-T01 全部显式失败名，区别于平台/开关 skip；其精确 `-k` 原 argv 保存在 command.json，五个失败持续待总控裁决。

US2-T01 同源证据 `E/US2-T01-owner-evidence.json` 确认拒绝函数与 accepted HEAD AST/源码字节均全等，body SHA `33f5fa2fe993a2fae884d5fba3ce8daa35365dd25b2e6100d9a57dac382300ca`，原 fixture SHA `a1f92d98277012429f37e8825acb1bab5b63dd60aba6e31730e69e9157859f26`。未执行完整历史 checkout baseline，因此只作该直接根因归属，不冒历史全 suite 通过/失败。

CANARY 从本轮指定文件实际读取，逐字保留；company 对照 JSON SHA 分别 `07591138543a893ba2b078c8037504ab46c2cf9ede7655e11b26a66291c84484` / `3f3ae49a3bedabe1dd479a83fcc203390a213505dceae42866144726578b58c5`。全部验证文件/双流/exit/脚本 SHA 索引为 `E/ticket-hashes.json`；最终 pyright stdout SHA `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb`。不编造未产生或已删证据 hash。

## V7–V14 与 V12 六段票据

| 验证 | 状态 / 未覆盖 |
| --- | --- |
| V7 | 未实施同版完整状态受理及公司 name/目标首错；依赖待裁完整 repo/publication |
| V8 | 未实施双阶段 guard、required 登记/final snapshot；不能称注册前/最终 guard 已验证 |
| V9 | 仅 strict amended reader 已验证；八格、metadata_updated、actual amended/两列表/摘要未实施 |
| V10 | 独立 source-owner strict 删除/健康重删完整字节与 revision/恢复再删已验证；完整材料 terminal amended 与 admission 未覆盖 |
| V11 | US2-C01 仅合同可观测性反例；未实施完整相同性 arbitration/真实竞争/COMMITTED release 新消费链 |
| V12 | 全部六段未执行，无 CLI 并发 pass |
| V13 | 本轮未改 job/no-runner/typed terminal/commit capability 取消；没有新 V13 pass |
| V14 | 26-module 宽回归已通过，额外 provider 单模块109-case suite 有5未修失败；不声称全回归通过 |

V12 必需六段单独核记：①owner wrap→CLI/SEC/CN same binding：未生成/未执行；②两 owned PID ready、共同 MISSING/revisionNone/companyNone：未执行；③同窗真实 Fs before：未执行；④releaseA/waitA/实际ok：未执行；⑤read winner 完整 source/manifest/assets：未执行；⑥releaseB/wait skip、winner→loser 全业务字节/revision/time 零漂移、restore/finally 仅回收 owned PIDs：未执行。company-history 单进程对照不能替其中任何一张票据。没有用同步启动或顺序 skip 猜竞态。

## README、风险分类与停止入口

已先读三个 README 各自职责。根 README 仅补当前健康材料重删的用户行为和损坏排查；Fins README 解释 strict owner 投影/重删 revision 不变；tests README 记录实际新增 owner 回归。无新 UI/Service/Host/Engine 分层或装配变化，不触发 dayu README，也未写未落地完整 S2 宣称。

| 风险/未覆盖 | 分类 / owner / destination |
| --- | --- |
| 独立严格删除事实/健康 no-op/strict amended reader | fixed in current partial implementation；storage/domain；本报告与实际 diff，仍待 root 核收 |
| US2-C01 None 公司例外与时间历史适用范围 | requiring explicit root decision；公司 commit contract/storage；本报告 pending，不自行补 provenance 或猜规则 |
| US2-T01 白名单外5材料夹具失败 | requiring explicit root decision；仓储测试 owner；总控决定窄白名单迁移或明确后续去向，现未修 |
| 完整 repo、publication、caller、V7–V14 行为链 | current S2 remaining approved work；storage/ingestion/D/publication/各真实入口；两 pending 裁决后继续同一 slice，不新增 mini-slice/gate |
| S3 XBRL/UP-RR-T01、平台后续/正式 CLI campaign 与 registry、Raw EOF | 原 binding later slice/WU/post-WU 归属不变；本轮未实施或冒通过 |

末 HEAD/main/branch/accepted plan/frozen manifest 与首值相同，逐输入核对及所有允许变更见 `E/end-freeze.json`，其余受保护输入（含旧 S1 双流/失败/Raw/control）无漂移；root 仍需独立核收。没有子 Agent、stage/commit/push/PR/merge/approve/外发、branch/worktree/clone/detached 或 main 修改。

停止入口为总控对 US2-C01/US2-T01 的直接同路径核证与裁决；本 Agent 不将 partial 交付送作完整 S2 pass，也不推进 code review/gate。没有以自报告或 reviewer 一致代替 root 接受。
