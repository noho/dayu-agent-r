RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-ddbd854a

# PR197 F6 SEC 计划修订交付报告

Label：`pr197-f6-plan-sec-fix-sol-20261001-01`。Gate：仅 plan/fix。状态：修订 proposal 已交付，等待 root 核收；没有 accepted plan、实现、code review 或产品验收。下一入口：root 核收本版及取证 → 同版 MiMo/Kimi planreview。本作者到此停止，不派发、不推进 gate。

## 合同与修订内容

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，实测分支 `codex/upload-material-oracle`。绑定 `docs/gateflow/pr-197-r1-f6-goal-20260930.md`、新 root 裁决 `docs/gateflow/pr-197-r1-f6-plan-delivery-adjudication-20261001.md`、ownerpreflight，design_doc=N/A。已读 AGENTS、gateflow、旧计划全文与 SEC 真源码/两真实测试。root 已裁 F6-P1/OQ-1 **accepted / 未修复**；本轮落实其计划补齐，没有重新裁上传行为、增目标、defer 或重问用户。

仅修改 `docs/gateflow/pr-197-r1-f6-plan-20261001.md`：开头新增当前执行合同，原计划全文逐字置于历史审计区。最新计划 SHA256：`27e898b51f7273896e0a280e191e032f0fa83cefc90883b30eacc61e98b58d4a`。本报告是唯一新增正式 artifact，写前工具确认不存在。

计划补齐：

- SEC 原 postrepair `SelectedSourceRepairRequired` 假抛 RevisionConflict 改由真实产生层使用新 typed RepairRequired；storage 原 identity 分类/三轮预算不改，runtime 唯一闭合两个 public reason/message/hint。
- SEC workflow 拥有 `SecDownloadIntegrityAbort` 与已确认 `filing_results` 快照；同一原八键摘要构造供 normal/abort 使用，保留 SEC 原 result 形状和默认 status，不套 CN integrity_failed 字典，不新增 status/schema/extra。
- 精确列出新类/函数签名、参数/throws、typed catch、terminal append/log/yield 和立即 abort 顺序；midfiling 耗尽当前无终态才发一条安全 FILING_FAILED；postrepair 在首确认成功事件后异常不伪造失败行/成功完成事件，后续 candidate 不执行。
- 原 success、6k_filtered rejected、registry-only/SC13 deferred facts、company 独立提交和 manifest 保全；未执行 tail 不进入 rows/counts。普通逐文档失败、cancel、repair gate 与已有 publication indeterminate 边界保留。
- `SecDownloadAdapter(*, pipeline=...)` 只 catch SEC typed abort，复用原 strict `_summary_from_pipeline_result`，包装原 cause 与 typed summary；不复制结果状态/业务分类真源，不解析异常字符串或补默认字段。
- 同一 F6-S1：精确 8 production 文件、10 个既有可改 test 文件、SEC 新增 node/参数矩阵、真实 Fs/合成字节损坏及真实 identity writer 耗尽、direct/job/CLI/wait 安全同源、先前 success/rejected 守恒；明确逐 changed file ≥80% 和现有 config full pyright 实际命令。
- 已读三个 README 职责后只规划随实施更新，本轮全部只读。wait 读 process observation；job 仍现有 message+result_summary，message 同 public safe_message。完整 structured reason 持久化仍独立待 goal；RepairBlocked 无真实下载专用 repair 调用，不造 fake 生产路径。

实际来源 enum 只有 SEC/CNINFO/HKEXNEWS，计划穷尽三真实来源，同时覆盖四 PreflightReason 与四公共入口 direct/job/CLI/wait；没有为“第四来源”编造值。F4 已同版双审/root code pass/accepted slice75fec并推送，F3 两代码 review 对五 utils只读，无 source writer；它们不替 F6 提供验收。

## 本轮新增 SEC owner 证据

临时目录：`workspace/tmp/pr197-f6-plan-sec-fix-sol-20261001-01/`。只用真实 Fs/真实 workflow/adapter 与合成 HTML bytes；网络 downloader 被具体 typed subclass 替代，无网络/PDF/OCR/私人语料。

| 探针 node | 直接结果与证据边界 |
| --- | --- |
| `test_sec_old_postrepair_cause_after_confirmed_success` | 首 repair 的 FILING_COMPLETED 后第二次真实 inventory 前损坏第二来源；首=COMPLETE、第二=REPAIR_REQUIRED，却旧抛RevisionConflict，只有首确认行，tail没请求。使用同真实 terminal 原行和 SEC 现成 builder 的受控快照验证现成 strict projection 可保 downloaded=1、ID与locator；这是临时最小设计探针，不是新workflow快照已实现 |
| `test_sec_old_adapter_loses_confirmed_summary` | 真实 SecDownloadAdapter 裸抛RevisionConflict，未携FinsSourceDownloadAdapterFailure/persisted_summary，而首已发布来源仍COMPLETE；证明丢摘要链 |
| `test_sec_old_real_identity_exhaustion_preserves_event_prefix` | 第二 target 在每轮 prefetch 与Phase B间由独立writer真实 replace_source_meta/commit改identity；3次耗尽原RevisionConflict，首成功终态可见、当前第二无终态、第三未请求；没有fake抛异常 |

最终命令（已激活 .venv，独立双流与exit记录）：

```bash
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -s \
  -o cache_dir=workspace/tmp/pr197-f6-plan-sec-fix-sol-20261001-01/pytest-cache \
  --basetemp=workspace/tmp/pr197-f6-plan-sec-fix-sol-20261001-01/probe-fs-design \
  workspace/tmp/pr197-f6-plan-sec-fix-sol-20261001-01/test_sec_owner_probe.py
python -m pyright \
  workspace/tmp/pr197-f6-plan-sec-fix-sol-20261001-01/test_sec_owner_probe.py \
  workspace/tmp/pr197-f6-plan-sec-fix-sol-20261001-01/evidence_runner.py
```

`sec-owner-design-probe`：3 passed、3既有edgar deprecation warnings、exit0、stderr空；`probe-design-pyright`：0 errors/0 warnings/0 informations、exit0、stderr空，stdout有既有pyright新版通知，未安装/改依赖。此前恢复版 `sec-owner-probe-final` 与 `probe-pyright` 同样通过。这些是旧路径和最小设计的受控证据；未重跑旧4probe，没有新产品代码、product coverage/fullpyright或新代码已验收的声明。

## 全部非零、恢复与影响

| 命令日志前缀 / 子命令exit | 真实原因 | 恢复与影响 |
| --- | --- | --- |
| `sec-owner-probe` / 1（3failed） | 探针替换整个source仓储却未共享batch core导致非法token；adapter错传位置参数；churn重复seed用create导致FileExistsError | 只修临时probe：替换全树扫描观察点，生产source仓储留原共享core；adapter用keyword；独立writer显式shared core真实replace/commit。没有据装配失败裁产品finding；失败双流保存 |
| `sec-owner-probe-recovered` / 1（2passed/1failed） | SEC现有collection日期升序，探针给反序日期，第三candidate先成功，tail断言错误；真实3次churn已达 | 只把合成日期排列改为FIRST/SECOND/THIRD升序；最终3passed，首成功/第二耗尽/第三未请求；没有改生产排序规则 |

本轮没有不存在路径读取/rg无匹配引发的命令失败。早期只读工具命令及canary在本轮完整JSONL/tool transcript；不冒称它们各自有另存双流。`read-doc-contracts` 初次多文件sed只显示首文件，已独立读 fins/test README 真实约束恢复，未将漏读当已读。记录runner外层exit0不是内层pytest通过；上表明确保留两个内层exit1，未只报总退出绿。

逐命令 `*.command.json` 保存argv/真实exit，`*.stdout.log`/`*.stderr.log` 分开；已有命令前缀包括：sec-adapter、sec-tests-owner、sec-real-locations、sec-catch、read-doc-contracts、auxiliary-contracts、retained-boundaries、sec-source-baseline、checkpoint-readback、preedit-freeze、上述四次probe、两次probe-pyright、delivery-git、delivery-refs、last-checkpoint。计划产品验收命令在当前计划E1，未在本轮执行；没有stage/commit/push/PR/merge、子Agent、新branch/worktree或main修改。

## 首末保全与生命周期

- 首HEAD=`75fec034d8993f300c2f2e2c8b9c574e243f8538`。root文档checkpoint先`a821da03911d76796e7ca53de2f9a813a56d595a`（8 docs），交付读到`4a3a28c5174d0f678146fd480dd8432cd2bd8611`（5 docs），分别实读git show；没有本作者Git mutation。main始终`fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- freeze SHA=`7cf6c5bc8e67d2481502b316ef05a5b29cb789f639d3dc68b05e055dfc0a870f`；实件41，不以口述件数代替。`start-hashes.json`/`end-hashes.json` 含每件 path/expected/current/original/match；41原件保全，40只读current仍原SHA，plan current仅授权新增前缀，历史全文与原件字节相等，freeze/originals未改。
- 12件必要辅助合同/skill/canary逐件首末SHA相同，`extra-start-hashes.json`/`extra-end-hashes.json`；未造另freeze。含正常storage export、SEC event/collection/state、shared Fs factory、JSON契约、测试package/conftest、gateflow与本轮canary。新读取仅记录，不修改。
- 读取本轮canary文件 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.sxqQ6h/canary.txt`，内容逐字为本报告CANARY。当前run JSONL只有thread/turn事件，无独立actual model metadata；指定provider/model label与canary不足以证明actual model，故unknown。旧轮canary只在历史审计区，不作本轮证明。
- F3 readonly review新增artifact与文档checkpoint属于允许并发观察；相关冻结source/test/README/config逐件稳定，不把外部产物算本作者改动或F6pass。

## 风险、状态与交 root

F6原CN/HK/runtime缺口及F6-P1/OQ-1产品仍accepted/未修复，计划补齐在同F6-S1，须root核收及同版planreview后才实施。真实SEC prefix中success/rejected组合、四preflight postrepair、真实direct/job/CLI/wait、changedfile coverage与fullpyright仍是未来实施验证，当前没有把它们写成已通过。

完整structured reason durable归既有独立job contract/store WU待goal；当前safe_message+summary与wait读者边界是已确认合同，非阻塞但未声称重启后完整reason/hint可读。publication indeterminate归storage原独立WU；#198日志、cancel和逐文档manifest旧完成项不重开。RepairBlocked下载新mapping动机未成立，保现有upload owner。没有未分类的新风险、没有新schema/业务规则/owner不清或冻结漂移停止条件。

本轮完成信号：指定计划修订和报告已交付、必要SEC旧路径/最小设计证据与首末保全完整。root负责核收及findings裁决，下一gate待root同版MiMo/Kimi planreview；本作者停止。
