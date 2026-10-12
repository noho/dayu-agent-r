# 601225-annual-fulltext：S1 code review 后 fix r1

- Gate：code review → fix r1；只交付修复与验证，不判 re-review / accepted slice / 最终完成。
- 分支：`fix/601225-annual-fulltext`；HEAD：`7709c015db26c095f16cb77b5d383411cd76b652`，仍为 accepted-plan。S1 与本轮修复均未提交。
- 输入：已读 AGENTS、deepreview/gateflow、goal/accepted plan、S1 implementation/checks/controller-validation、184158/184159 两 review 与 code-review-adjudication。只处理总控 accepted 的 MiMo-01/02。
- 临时证据根：`workspace/tmp/601225-code-fix-r1/`。未改 caller、原 P6 evidence、冻结 plan、旧 review 或总控 state；未 commit/push/PR/comment/issue，未派发、清理或中止其它 Agent。

## Finding 修法与反例闭环

### MiMo-01：selected repair 身份漂移

- **owner**：`cn_download_workflow` 的请求级 repair gate；身份观察仍只由 `cn_download_identity` 投影。原问题成立：initial 的 D_old 与循环 fresh 的 D_new 不同，旧 `document_id == repair_document_id` 判断会跳过失败关闸和 company publication。
- **实现**：从同一次 initial candidate→identity 投影构造 accepted 集合与 `_SelectedRepairIntent(source_key, expected_document_id)`，不再为排序重复解析。唯一 repair 候选先处理；首次处理其 source 前 fresh ID 不同即 `SourceIntegrityRevisionConflictError`→`CnDownloadIntegrityAbort`，尚无 `FILING_STARTED` 或 failed 行。
- **收口**：唯一可写状态是 `pending_repair`，已移除 `repair_gate_completed` 布尔真源。gate 按 source intent 判定，稳定单 filing failed 直接关闸并保留原 reason；成功仍须 fresh inventory clean、取消检查与 company publication 完成才开放 tail。正常非取消终态不得带 pending intent；取消优先保留控制终态，不以终态检查覆盖 provider/conversion 主原因。
- **新反例**：`test_selected_repair_source_rebind_aborts_before_application[True/False]` 先在独立 control Fs base 真正证明 D_new 分别可 skipped、可 failed(period_metadata_mismatch)；再由独立真实 Fs writer 使用公共 batch/reset/blob/source/commit API，在 initial final-preflight 与 fresh identity read 之间发布 D_old→D_new。两类都在应用前 typed 中止；两次身份观察分别实际解析 D_old/D_new；request batch begin/commit/rollback、GET、conversion 均 0，无 filing-start、tail、company、普通完成事件。
- **发布态**：重绑定后的完整 metadata/revision/全部资产与 writer 刚发布的 snapshot 完全相等；旧目标被 writer 合法移除，本请求保持其缺席；无关旧 source 与旧 company 全保持。初始两次 inventory 仅受控模拟符合 storage 不变量的 repair-required 观察；身份读、重绑定发布与持久态断言均来自真实 Fs，未直接篡改该测试受管目录，不冒充真实磁盘损坏。已有真实损坏 repair 回归继续覆盖 repair 的 A/B/commit。
- **稳定路径**：扩展既有 repair 失败测试，覆盖 provider、真实触发转换后的 conversion failure、converter 契约取消；均只启动 repair，tail 未启动，旧公司/损坏源保持，原因按原 owner 投影。既有稳定 repair 成功、fresh post-repair inventory/company 顺序、已提交前缀、rollback、普通 clean、HK 回归全部通过。
- 修复状态：**已修复（fix owner 验证）**；独立双路 re-review 尚未执行，本轮不回写旧 review 或总控裁决。

### MiMo-02：新年度 ID 的内部占用

- **owner**：纯 `cn_download_identity`。旧索引只记录 external key；当其它 source 的 external 不同而 internal 等于新 seed/fallback internal 时，会分配重复 internal。
- **实现**：索引显式增加必填 `allocated_internal_ids: frozenset[str]`；所有构造均显式迁移，无默认兼容字段。一次遍历在 source-key 过滤前收集 owner 已声明的非空 str；不推测名字、不强转其它 JSON 值。
- **规则**：同 key 复用与 missing_internal→read_error→duplicate 原优先序先裁决。CN FY 新 seed 的 external/internal 任一占用→来源 hash fallback；fallback 任一占用→原封闭 ValueError，绝不覆盖或随机后缀。HK 原财期纠正规则和 CN H1/Q 的直接 seed 行为保持。
- **新矩阵**：seed external/internal × fallback 无/external/internal × known/unknown source 共 12 例；再覆盖非空 str 与 None/空/数值/布尔/list/dict，不从 external 名字猜 internal。同 key 复用及 missing/read/duplicate 均先于双占用拒绝；纯 owner 调用前后索引/输入不变、零 I/O/写入。
- 修复状态：**已修复（fix owner 验证）**；独立 re-review 待总控。

## 本轮 changed files

- `dayu/fins/README.md`
- `dayu/fins/pipelines/cn_download_identity.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `tests/README.md`
- `tests/fins/test_cn_download_identity.py`
- `tests/fins/test_cn_download_workflow.py`
- `docs/gateflow/601225-annual-fulltext-code-fix-r1.md`（本 artifact）。

与 accepted-plan 的全 S1 工作树 diff 不等于本轮增量。`before-manifest.json` / `r1-scope-audit.json` 已确认本轮仅以上六个原文件变化，其它初始文件 hash 均不变；临时脚本与输出均留在本轮 tmp 根。

## 测试、覆盖率与类型/依赖

全部命令先激活 `.venv`，最终实际命令/退出见 `checks-commands.json`，原 stdout/stderr 单独保存。

```bash
source .venv/bin/activate
pytest -q tests/fins/test_cn_annual_report_facts.py tests/fins/test_cn_annual_report_source.py tests/fins/test_source_integrity_preflight.py tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py tests/fins/test_cn_download_models.py tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_pipeline.py tests/fins/test_f5_workflow_rebuild.py tests/fins/test_hk_period_rebuild.py --basetemp=workspace/tmp/601225-code-fix-r1/final-basetemp --cov=dayu/fins --cov=tests/fins --cov-report=term-missing --cov-report=json:workspace/tmp/601225-code-fix-r1/coverage-final.json
```

- 实际 exit 0，**758 passed**，3 个既有 edgartools DeprecationWarning。完整 13 文件集含 `test_hk_period_rebuild.py`，无排除、无放宽断言。
- `tests-final.stdout.txt/.stderr.txt`、`coverage-final.json`、`coverage-check.json`；coverage-check 实际 exit 0，全部 12 个 S1 生产文件及 12 个实际新增/修改测试文件均 >=80%。目录 source 方式沿原已验证收集方式，不用总体覆盖率代替逐文件。
- `source .venv/bin/activate && pyright`：实际 exit 0，0 errors / 0 warnings；`pyright-final.stdout.txt/.stderr.txt`。版本升级提示未改依赖。
- `source .venv/bin/activate && python -m pip check`：实际 exit 0，No broken requirements found；`pip-check.stdout.txt/.stderr.txt`。

| 文件 | 可执行语句 | 覆盖率 |
| --- | ---: | ---: |
| `dayu/fins/downloaders/cninfo_downloader.py` | 388 | 90.72% |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 461 | 85.03% |
| `dayu/fins/pipelines/cn_annual_report_facts.py` | 36 | 100.00% |
| `dayu/fins/pipelines/cn_annual_report_source.py` | 68 | 98.53% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 300 | 92.33% |
| `dayu/fins/pipelines/cn_download_identity.py` | 76 | 100.00% |
| `dayu/fins/pipelines/cn_download_models.py` | 182 | 96.15% |
| `dayu/fins/pipelines/cn_download_protocols.py` | 40 | 100.00% |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 78 | 85.90% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 354 | 91.81% |
| `dayu/fins/pipelines/cn_report_selection.py` | 303 | 91.75% |
| `dayu/fins/storage/source_integrity.py` | 131 | 85.50% |
| `tests/fins/test_cn_annual_report_facts.py` | 49 | 100.00% |
| `tests/fins/test_cn_annual_report_source.py` | 100 | 100.00% |
| `tests/fins/test_cn_download_identity.py` | 200 | 99.50% |
| `tests/fins/test_cn_download_models.py` | 60 | 100.00% |
| `tests/fins/test_cn_download_runtime.py` | 1058 | 99.34% |
| `tests/fins/test_cn_download_workflow.py` | 2046 | 98.24% |
| `tests/fins/test_cn_pipeline.py` | 894 | 98.21% |
| `tests/fins/test_cn_report_selection.py` | 135 | 100.00% |
| `tests/fins/test_cninfo_downloader.py` | 795 | 94.34% |
| `tests/fins/test_f5_workflow_rebuild.py` | 230 | 100.00% |
| `tests/fins/test_hkexnews_downloader.py` | 678 | 92.48% |
| `tests/fins/test_source_integrity_preflight.py` | 26 | 100.00% |

保留前期失败而不覆盖：两轮 targeted 的失败是新增测试尚未触发新 PDF 转换、取消类型不符合 converter contract；一轮完整测试/pyright 发现 Docling 取消构造不接收参数。修正夹具为实际不同 bytes 与无参 `DoclingConversionCancelledError()` 后，repair-terminal 3 passed、最终完整集及 pyright 通过。真实 repeat runner 初次在 CLI 启动前因 company 仓储不存在 `create_directories` 入参失败；只修临时脚本，再正式启动各一次，旧失败日志 `repeats.stderr.txt` 保留。未用 production 宽松分支保住 fake。

## Allocation guard 等价 replay

```bash
source .venv/bin/activate
PYTHONPATH=. python workspace/tmp/601225-code-fix-r1/allocation_replay.py
```

- 实际 exit 0；`allocation-replay.json/.stdout.txt/.stderr.txt`。纯 identity owner 零网络、零仓储写、零 conversion。
- 输入来自原四 run 全量 verify metadata、first 真实公开 file-start 与四 run 的逐 filing 终态；对每个输入文件记录 SHA。从 clean 空前态或 `seed.verify.json` 的真实 seed2 前态，按实际处理顺序逐 prefix 建只读索引，再调用当前 pure resolve；每发布一个 prefix 仅加入该 source 的实际完整 meta。
- **clean：0→35，35/35 pair 完全相等；seeded：2→37，35/35 pair 完全相等**。external 与 internal 都逐值比较；两原 repeat 的真实处理顺序同序，并用完整索引确认全部 35 pair 复用。不是仅比较 ID 集合。
- **证据边界**：原 CN 公共 adapter 未保存 `FILING_STARTED` 本体。first 的 35 条实际 `download.file_started` 与 35 条真实 filing downloaded 终态严格同序、唯一；repeat 的 35 条真实 skipped 终态与 first 严格同序。沿串行 workflow→single-filing→adapter 的直接 owner 链验证处理顺序，未从文件名或 metadata 排序猜序，未将此投影写成原始 FILING_STARTED 日志。
- 这是本次 guard 等价 replay，不能称新版首次真实网络下载、重新发现全部事实或历史 raw 恢复。facts/selection/conversion 代码未变，实际 PDF/JSON 的原 SDK/完整 SHA 验证继续有效；没有重做两次完整窗口转换。

## 当前代码的两次真实 bare CLI repeat

正式 runner 实际 exit 0；`repeat-commands.json` 记录 observer/verify/四 compare 全部原 argv 与 exit。observer 直接观察真实 transport/wire，原四 run 与 verify 全保留，run/log/verify/compare 均用新名。

### clean-fix-r1

```json
["/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli", "--base", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/clean", "--debug", "--log-file", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-code-fix-r1/clean-fix-r1.log", "download", "--ticker", "601225.SH", "--start", "2018-01-01", "--end", "2026-10-12"]
```

- 原 CLI exit `0`，PID `17681`，status `exited`；bare download，无 overwrite/rebuild/--forms FY。
- 仓储 source count 35；discovered=35 / skipped=35 / downloaded=failed=rejected=uncertain=0；success/succeeded、failure=null。全部持有源 conversion started/completed=0。
- 实际 PDF GET attempts/wire：`{"1204545056": 1, "1209875597": 1, "1213161682": 1, "1223301999": 1}`（两表精确相等，每项各 1）；三目标与所有已持完整源 0 GET。
- `clean-fix-r1.verify.json` 和与原 `clean-01`、`clean-02` 的两份 compare 均 passed / differences=[]；完整 sources 逐值独立比较相等，company meta 相等。

### seeded-fix-r1

```json
["/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli", "--base", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/seeded", "--debug", "--log-file", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-code-fix-r1/seeded-fix-r1.log", "download", "--ticker", "601225.SH", "--start", "2018-01-01", "--end", "2026-10-12"]
```

- 原 CLI exit `0`，PID `17709`，status `exited`；bare download，无 overwrite/rebuild/--forms FY。
- 仓储 source count 37；discovered=35 / skipped=35 / downloaded=failed=rejected=uncertain=0；success/succeeded、failure=null。全部持有源 conversion started/completed=0。
- 实际 PDF GET attempts/wire：`{"1204545056": 1, "1209875597": 1}`（两表精确相等，每项各 1）；三目标与所有已持完整源 0 GET。
- `seeded-fix-r1.verify.json` 和与原 `seeded-01`、`seeded-02` 的两份 compare 均 passed / differences=[]；完整 sources 逐值独立比较相等，company meta 相等。

seeded 两摘要仍是原 source/ID/meta/revision/PDF 与 JSON SHA，与原 `seed.verify.json` 全记录完全相等；35 个候选来源身份不混入 2 个摘要。三目标全文 PDF/JSON、财年、原 locator、COMPLETE、fingerprint/model/origin/内容 sanity 经当前 verify 原样核验，完整 35/37 记录与原 first/repeat 完全相同。

`repeat-full-comparison.json` 汇总两真实 repeat 和独立全 source 比较；`protected-before.json` 实核 **366 个旧 artifact/evidence 文件 hash 全不变**，含原四 run/log/verify、原 compare/seed、官方 evidence、冻结计划、旧 review 与总控文档。`repeat-code-version.json` 确認真实 repeat 全程本轮六文件版本未变。

## README 决定

- 已读 Fins README 的 Agent更新约束与 tests README 的更新边界；只少量补充已实现的双命名空间占用契约、来源 repair intent/fresh 漂移/收口与实际 owner 回归事实。
- 根 README：本轮未改变公开命令、安装/初始化、日志位置、工作区或用户操作流程，已有 revision-conflict 排障投影沿原契约，无新增用户手册内容；不修改。
- `dayu/README.md` 与其它层 README：没有分层/装配/跨层边界变化，未触发；不修改。

## 风险分类、owner / destination 与未完成

| 项目 | Gateflow 类别 | owner / destination | 状态 |
| --- | --- | --- | --- |
| 两项 accepted finding、fix 验证 | fixed in current slice | fix owner / 本 artifact；总控与两独立 reviewer / 同版 re-review | 修复及验证已完成；尚未独立复审/放行 |
| 原 FILING_STARTED 本体未落盘、历史启动树/raw 缺失 | assigned to later work unit | 总控/观测与取证维护者 / 如需直接事件历史采集的独立可追溯任务；当前 re-review 核 direct-owner 同序证据 | 不补造；本轮 guard replay 明确投影证据边界 |
| open/read/close 全故障注入与 seeded-first 辅助 no-extra 断言 | assigned to later work unit | Fins source/验收维护者 / 总控既定资源失败回归与验收辅助任务 | 不顺手扩修；本次真实来源全集逐值比较无差异 |
| DS 外部 gate 取消回调注记、runtime 公共/后台失败投影 OQ | assigned to later work unit | Fins gate/runtime 维护者 / 总控既定真实 gate 装配与独立投影统一任务 | 按裁决保留；风格注记不处理 |
| 其它公司/公告、未知布局/OCR、一般日期、历史错年/未知身份自动恢复 | assigned to later work unit | Fins discovery/facts/date/integrity 维护者 / 已接受独立任务边界 | 未覆盖、不新增恢复承诺 |
| 落选全文/摘要 repeat GET 成本 | assigned to later work unit | Fins 维护者 / 按需性能任务 | 本次真实 clean4/seeded2 精确核验，不加缓存 |
| SDK 有损 origin binary_hash 与无持久 derived_from 的历史转换因果限制 | assigned to later work unit | Fins 审计维护者 / 按需独立来源审计 | 原实际转换证据与两资产 SHA/fingerprint/model/origin 继续使用，不扩 schema |

- 当前无正常 facts/selection/acquisition/conversion 路径变更，无外部网络/集合/依赖 blocker；没有降低验收或用 replay 代替真实 repeat。
- **未完成项**：总控实际退出/证据复核及双路同版 re-review、后续 accepted slice commit/gates。它们由总控负责，本 owner 不派发、不判断已复审或最终完成，不更新总控 state。
- 本 artifact：`docs/gateflow/601225-annual-fulltext-code-fix-r1.md`。
