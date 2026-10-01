RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-d1471261

# PR197 F6 计划探针类型证据窄 fix 报告

Label：`pr197-f6-probe-type-fix-sol-20261001-02`。Gate：F6 plan 取证窄 fix。设计文档：N/A。F6-PV01 已由 root 裁为低 / accepted / 未修复；本次仅交付其修复证据，等待 root 核收和最终修复状态裁决。没有 accepted plan、产品实现、产品验收或新业务 goal。下一入口：root 核收本报告及同版计划 → 由 root 安排同版 MiMo/Kimi planreview；本作者完成后停止，不派审查、不推进其它 gate。

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，首末分支 `codex/upload-material-oracle`，首 HEAD `4a3a28c5174d0f678146fd480dd8432cd2bd8611`，交付末检 HEAD `0060be3edf69455e8bb2583d646aa932873ba3c4`，main 始终 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。最后核对期间新增 root 文档 checkpoint `0060be3e`：已实读 git show，12个文档、470 insertions/14 deletions，无source变化；相关冻结与额外只读SHA全部匹配。该变化只记录，不以非冻结HEAD判身份失效，亦非本作者commit。root-checkpoint-readback 的双流/commandJSON/exit保存在新目录；内层与父wrapper均0。已有 F3 五 utils/其它 root 文档的 dirty 状态不是本作者变更，不作 F6 通过证明。

已读取 AGENTS.md、Gateflow skill、root `docs/gateflow/pr-197-r1-f6-probe-type-evidence-adjudication-20261001.md`、旧 F6 plan（包括历史审计区）、只读 SEC 补充报告 `docs/gateflow/pr-197-r1-f6-plan-sec-amendment-20261001.md`、旧两个脚本及相关日志；之后才复制和修复。旧业务目标、两 public reason、typed 原因、SEC owner、G1–G5 和 durable 无新增字段边界均未重裁。

## 动机、直接根因与实际修改

动机成立且仅限取证：旧命令向默认项目 pyright 直接传 workspace/tmp 文件，但仓库默认配置排除 workspace，0 errors/exit0 实际为 filesAnalyzed=0。新复制文件在相同默认配置下也复现 0 files。该结果不能视为有效类型 pass，也不属于产品类型问题。

日期范围语义 owner 是 `dayu/fins/download_contract.py` 的 `FinsDownloadDateRange`：start_bound/end_bound 明确要求 `date | None`，start_text/end_text 从日期实例生成 canonical ISO 文本。旧 probe 在第184行 request 构造处传两个字符串，新显式配置实测 filesAnalyzed=2 / errorCount=2，均为 reportArgumentType。修复位于临时调用输入处，不更改 owner signature，不在 adapter 或消费者补偿。

实际文件变化：

- 复制旧 `test_sec_owner_probe.py` 到 `workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/test_sec_owner_probe.py`；仅增加 `from datetime import date`，将 request 日期参数写成 `date.fromisoformat('2024-01-01')` 和 `date.fromisoformat('2025-12-31')`。原日期文本、filters、全部断言、合成申报排序、请求过滤、真实 Fs 场景与独立 writer 身份保持；同样的 canonical 日期由 contract 产生。复制版行号因 import 增为185。
- 复制旧 `evidence_runner.py` 到新目录，仅把 RUN 路径指向新 label；旧脚本、旧日志、旧报告均未覆盖。
- 新目录创建显式 `pyrightconfig.json`；只检查两复制文件，采用既有项目默认规则，没有 strict mode、规则关闭或依赖升级。
- 唯一正式修改为 `docs/gateflow/pr-197-r1-f6-plan-20261001.md` 当前前缀：将旧临时类型声明明确更正为 0 files 非有效 pass，记录新真实 2-file/3-owner 证据、最近状态及引用。B–E 技术设计块和历史审计全文均与 frozen original 逐字节相同。产品 full pyright、逐 changed production file ≥80% 和产品测试义务没有被缩减。
- 本报告是唯一新增正式 artifact，首查与写前均确认不存在；其它新增证据仅在本 label tmp。

禁止路径均未使用：没有 Any/object/cast/type-ignore、删被检文件、放宽 signature/config、兼容分支或 fallback。没有修改 source、正式 tests、README、goal、registry、root 控制文档、handoff、仓库 config、依赖、freeze/originals，也没有改 F3/F4/F7。

## 非空配置与实际命令

新配置内容如下，include 为相对配置文件的两个复制文件，exclude 显式为空；唯一 checkout 的 extraPaths/venvPath 为绝对路径，venv=.venv，Python3.11：

```json
{
  "include": ["test_sec_owner_probe.py", "evidence_runner.py"],
  "exclude": [],
  "extraPaths": ["/Users/leo/workspace/dayu-agent-r"],
  "pythonVersion": "3.11",
  "venvPath": "/Users/leo/workspace/dayu-agent-r",
  "venv": ".venv"
}
```

下列为本轮真实执行命令。每次先 `source .venv/bin/activate`；所有脚本及日志路由新目录，`PYTHONDONTWRITEBYTECODE=1` 传递给子命令。copied runner 保存内层 argv/真实 exit，父 wrapper 退出码另见 execution-ledger.json，不把父0当子0。

```bash
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/evidence_runner.py start
PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/evidence_runner.py pyright-default-empty-before python -m pyright --outputjson workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/test_sec_owner_probe.py workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/evidence_runner.py
PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/evidence_runner.py pyright-explicit-before python -m pyright --project workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/pyrightconfig.json --outputjson
# 此处仅修复制 probe 的 request 日期类型。
PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/evidence_runner.py pyright-explicit-after python -m pyright --project workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/pyrightconfig.json --outputjson
PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/evidence_runner.py sec-owner-probes-after python -m pytest -q -s -o cache_dir=workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/pytest-cache --basetemp=workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/probe-fs-design workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/test_sec_owner_probe.py
PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/evidence_runner.py end
```

| 新日志前缀 | 父 wrapper / 内层 exit | 真实结果 |
| --- | --- | --- |
| pyright-default-empty-before | 0 / 0 | filesAnalyzed=0、0 errors/0 warnings；非有效类型 pass |
| pyright-explicit-before | 0 / 1 | filesAnalyzed=2、2 errors/0 warnings；两个日期字符串参数错误 |
| pyright-explicit-after | 0 / 0 | filesAnalyzed=2、0 errors/0 warnings/0 informations；generalDiagnostics=[] |
| sec-owner-probes-after | 0 / 0 | 3 passed、3既有edgar deprecation warnings，1.23s |

四条子命令的 stderr 均为空。实际 pyright 版本1.1.409，未升级。`pyright-explicit-after.stdout.log` 保存完整合法 JSON，其 summary 的 filesAnalyzed=2、errorCount=0、warningCount=0 已独立读取核对。每条子命令分别保留 `*.stdout.log` / `*.stderr.log` / `*.exit.txt` / `*.command.json`；`execution-ledger.json` 保存 cwd、激活动作、环境和真实父/子退出码。配置、diff 与 SHA 记录均在同目录。

首末 hash 由 copied runner 保存 `start-hashes.json` / `end-hashes.json`；最初额外首查为 `freeze-before-check.json`。Git 首末命令独立保存 initial/final-git 前缀双流、exit 和 commandJSON。早期读取/复制/文档编辑/末检的工具命令保留本轮 tool transcript，不冒称这些工具命令全部有另存双流。

## 三个 SEC owner 探针的实际范围

| 实跑 node | 直接证据 |
| --- | --- |
| test_sec_old_postrepair_cause_after_confirmed_success | 首 repair terminal 成功后，第二次真实 inventory 前损坏第二 source：首 COMPLETE、第二 REPAIR_REQUIRED，却旧抛 RevisionConflict；只有首确认行、tail 未请求。现成 SEC builder/strict projection 对真实原行的受控快照仍保 downloaded=1、同document_id 和 artifact_locator |
| test_sec_old_adapter_loses_confirmed_summary | 真实 SecDownloadAdapter 裸抛 RevisionConflict，没有 FinsSourceDownloadAdapterFailure/persisted_summary；首已发布来源仍 COMPLETE |
| test_sec_old_real_identity_exhaustion_preserves_event_prefix | 第二 target 的 Phase A/B 间独立 Fs writer 真实 replace_source_meta/commit，三次真实 identity 变化耗尽；首成功终态保留，第二无终态，第三未请求 |

使用真实 Fs 仓储、真实 workflow/adapter、既有 typed 合成 downloader；seed 为 `<html>seed</html>`，prefetch 为 `<html>payload</html>` 等合成 bytes，新 probe-fs-design 中保存实际 source/meta/manifest。没有网络请求、PDF解析或 OCR；没有 fake 抛异常替代真实 identity writer。受控 builder/projection 仍是最小设计取证，不声称新 workflow abort/adapter 包装已实现。

## 所有非零与恢复，不抹原历史

本轮唯一新增内层非零是 `pyright-explicit-before` exit1；父 wrapper exit0，真实两错误已完整保存。修复仅为复制 request 的真实 date 参数，after 非空两文件类型0与三个 owner node 全部恢复，无未恢复失败。其余本轮工具/子命令均未出现非零退出。

历史原件继续只读并保留原终态：

- SEC 补充轮 `sec-owner-probe` 内层 pytest1/3failed（shared batch core、adapter keyword-only、重复 seed create 装配错误）；`sec-owner-probe-recovered` 内层 pytest1/1failed（探针合成日期反序，真实 collection 日期升序）。原轮在临时 probe 修装配和日期输入后3passed；本轮不重改这些场景，复制最终字节并复跑3passed。原父 wrapper0不掩盖两个子pytest1。
- 旧 `probe-pyright` / `probe-design-pyright` exit0保留，但判为0files非有效类型pass；本轮默认项目命令在新复制文件上再次直接复现0files。旧报告不可改写，当前 plan 前缀和本报告作纠正入口。
- root 首次绝对 include 配置失败，误扫 controller 并命中 F7预期 negative，继而有效相对 include 才得到 F6真实2错误。原失败配置 `workspace/tmp/pr197-controller-collection-20261001/f6-sec-plan-probe-invalid-absolute-include.json`、有效配置及整个 `f7-type-probes/` 均只读，不修改/删除任何 negative；root 失败退出码以其原始证据为准，不臆造。本轮新 config 使用正确相对 include。
- 旧 plan 历史审计区仍逐字保留早轮取证的 rg 非零：误带不存在 dayu/ui（rg2而父shell0）、查询无匹配（exit1、后续读取未执行）、猜 sec_download_adapter.py 不存在（exit2）、猜 cn_download_summary.py 不存在（exit2）；其真实路径恢复记录和旧日志仍保留。未将这些历史读取失败改作通过。

## 首末 SHA 与原件保全

freeze 唯一且未修改：`workspace/tmp/pr197-f6-probe-type-fix-sol-20261001-02/freeze.json`，SHA256 `acd7daf3bee8bcdc854a3b84568238a497007cc22afc7c92cfd21465227006ab`。实际45 files/44 readonly；首查45 current/original全匹配。末查45 originals全保留原SHA、44 readonly current全匹配，唯一 plan current按授权修改。逐件 expected/current/original/match见 start/end-hashes.json；末检查没有未授权漂移。

额外只读保全275文件：旧 SEC label全目录（含旧日志/脚本、合成Fs字节、freeze/originals）、root两个配置、F7 negative目录、Gateflow skill与本轮canary；首末 SHA逐件匹配，见 readonly-extra-before.json / readonly-extra-after.json，mismatches=[]。这不是第二份freeze，也不扩大产品scope。

| 文件 | 原件或 before SHA256 | 复制或 after SHA256 |
| --- | --- | --- |
| test_sec_owner_probe.py | 6cc121320fd0b6772115efa48791769f45b823b3a8ffe8b9a8b749e2ad686219 | 2ee4f6a4ebe4f1d34b48fb08fd410cf8e7f2a5d290cd6ee0c63ab138a00685bc |
| evidence_runner.py | a10a903d49f9ebebed42e781675132f7328f80623758574db5d522d02959b25a | 92c2100cc9a7f9e56687c56d1d7cbac49bd4fff803521cda5fd0670b49c7fbd6 |
| plan | 27e898b51f7273896e0a280e191e032f0fa83cefc90883b30eacc61e98b58d4a | c59787460262b7706f6d5312da61d693474d02403b493e2484ad2c053cd6e566 |

probe 复制前SHA等于原件；runner复制后仅改输出路由，修日期前后SHA均为92c2100c…，其精确差异见 evidence_runner.py.diff。新 pyrightconfig SHA=`83402e4b86b5535d4523d2dc277ca11e94073421da79b711c27602f7393fe129`。before/after复制SHA见 copy-before-sha.json / copy-after-sha.json，不以缩写代替完整记录。

最终 plan-preservation-checkpoint.json（保留此前 plan-preservation.json）证明 B–E 技术设计块逐字相等（SHA=`22afcd4df5d02570cc84785c221f08417e0b62c1d194225431897a85f4ab77f5`），历史审计tail逐字相等（SHA=`fc1c91b9b3a4dd2d5e02f3c773a16e6b0ad16512f47fb2757383d95c9c1cce24`）；最终 plan-prefix-checkpoint.diff仅为当前证据/状态/引用修订（此前plan-prefix.diff保留）。已核查新增行无尾随空白。

CANARY从本轮实际文件 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.1hPDPT/canary.txt` 工具读取，并逐字写入开头。本轮可用信息没有独立 actual model metadata，任务label/provider/canary不能证明actual model，故unknown；旧轮canary不是本轮证明。

## 未覆盖、风险 owner 与停止交 root

- F6-PV01取证类型问题：本次窄fix已完成且证据恢复，等待 root核收修复状态；不由作者接受plan。
- F6产品 typed cause/公共reason/SEC摘要守恒仍未实施，归现有F6-S1；G1–G5、真实direct/job/CLI/wait、逐changedfile覆盖率和原项目fullpyright仍由以后批准的产品implementation验证。本轮没有跑全量产品类型或coverage，不把临时green当产品pass。
- 完整structured reason durable归既有独立job contract/store WU待goal；没有新增字段。publication indeterminate及其它F3/F4/F5/F7归root现有序列，不顺手修复。
- 用户总目标仍为修已裁决项后重跑upload_material真实CLI CI、确定oracle/scenarios/readiness；现有registry仅download和upload完成，本窄fix不是新产品goal或CI通过。owner/root在后续既有任务验收；本轮没有改oracle、registry、readiness或成功标准。
- 3条edgar警告为既有依赖deprecation；无新增类型warning，不升级依赖抹警告。本轮没有新未分类风险、owner不可读、冻结漂移或未恢复类型/owner场景失败。

README未触发本轮修改：source、正式tests、用户入口、架构和产品行为均未变，且本轮授权明确README只读。没有stage/commit/push/PR/merge/branch/worktree、子Agent或其它gate操作。

交付状态：本次窄fix和指定报告完成，停止交root。中间 delivery-final-check.json 保留最初交付末检结果，发现该root checkpoint后更新当前状态与引用；最终以 delivery-final-check-02.json 为准，不覆盖旧检查。next entry唯一为root核收本次证据及同版plan后同版MiMo/Kimi planreview；本作者不自动派发或接受计划。
