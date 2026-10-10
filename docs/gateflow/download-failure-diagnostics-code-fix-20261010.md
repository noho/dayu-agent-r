RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6.1-sol

CANARY=gpt-6-sol-e2243375

# S1 code review fix

- Task label：dfdiag-code-fix-sol-20261010-01；work unit：download-failure-diagnostics-20261010。
- Gate：fix；完成后下一入口为总控双路 re-review，不宣布 gate pass。
- Branch：fix/download-failure-diagnostics-20261010；HEAD：a1df000835c61d1acfa383532488746e1487ed7b；原 base：c65c2aa28fae9c47ad947783d63f7559db7768c4。
- Canary 已由工具读取本轮 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.Ej6Mwr/canary.txt`，逐字如上。型号标签不作为物理后端证明，没有型号探针。
- 先读 AGENTS、gateflow fix、已确认 goal、approved plan、implementation/implementation-adjudication、code-adjudication 及 ds/mimo 两份报告。所有 dirty 已授权归本 unit；总控状态/裁决、历史实现和 review 只读，无其它实施 runner。
- 冻结核对：manifest SHA256 `08cc9c52e14210c2e8b2fed08000e50c37ed0750b471328df8c59d0966161aa6`，patch SHA256 `a4b86b790be4e3e58f7b0eff31ad18973620f520ac416a5dac8b4d995dec628a`；24/24 文件匹配，HEAD/branch 一致。证据 `workspace/tmp/download-failure-diagnostics-20261010/code-fix-input-check.json`。

## 实现前 owner 决策与最小状态转移

C1 动机成立：当前 `_emit_direct_result` 先不可逆 claim 再构造 RESULT，`FinsResultSummary.__post_init__` 首次 public 校验拒绝后 producer 无法再 claim；完整失败行又延迟到 CLI 校验，第 11 行可使 renderer 拒绝。根因是 owner 校验晚于终态受理，不是 CLI 容错不足。

完整候选/计数 owner 为 `FinsDownloadResultSummary`，公共安全投影 owner 为 `direct_events.FinsResultSummary` 和共享 `_download_public_document`，取消原子 owner 为 `_DirectStreamCancellationState`。唯一业务真源仍为 `download_result`。result 构造时从该 immutable 真源派生并保存 init=False 的只读 bounded summary 与完整 FAILED public tuple；这些是 owner 内部校验后的投影，不是调用者可提供的第二真源。`download` 与完整 JSON 只消费这些已校验投影，不再进行可能失败的行构造。

runtime 在 claim 前构造请求终态及可能获胜的 CANCELLED 事件。下载公共受理校验拒绝由同一受理边界以实际拒绝异常调用既有 `_download_public_failure_from_exception`，形成 request-scoped 空 FAILED 和安全 whole failure；记录原脱敏异常。不是过滤坏行、默认候选原因、CLI fallback 或重算已确认事实。连 typed abort 携带的拒绝快照也在此收口。非下载校验异常照旧传播。

两种事件都构造成功后才刷新取消检查并调用原 `claim_terminal`；返回 None 不投递，返回 CANCELLED 选择预构造取消事件，否则选请求事件。claim 后没有下载构造/投影。取消赢仍 CANCELLED/130、failure=null；claim 赢仍原请求终态，原算法和锁不变。合法正常/partial/all_failed/取消的 tuple、字段、原因和退出 policy 原样保留。

只改 direct_events/runtime 及必要批准 tests；C2 合并 root 22 项与 mimo 的真实 qualified controlled_claim，逐函数补中文参数/返回/异常，不修未改旧函数、不削弱断言。测试须先证明第 1/第 11 行在 public owner 被拒绝，再走真实 runtime→唯一 validated RESULT→CLI 主入口默认诊断；另覆盖取消竞争和 claim 后不再投影。

不改目标/来源策略/SEC 原因/schema/CLI policy，不增加持久库、分页、框架或网络；无需扩文件范围，owner 无阻塞问题。后续验证限 focus、exact A14、pyright dayu/tests/utils 和同 A 五文件 coverage，真实托管 exit，不跑 broad/baseline/生产来源。README 按已读职责判断，完成记录将在本文件追加。

## Changed paths 与实际实现

以下为相对本轮冻结输入的变化，不把之前 S1 的 dirty 当成本轮新增修改：

| 路径 | 本轮内容 |
| --- | --- |
| `dayu/fins/direct_events.py` | result 构造校验并保存 bounded summary 与完整 FAILED tuple；两个读取接口复用 owner 已校验投影。 |
| `dayu/fins/ingestion_runtime.py` | 受理失败安全收口、预构造两种可提交终态，claim 后只选择/入队；删除不再使用的 claim 后构造 helper。 |
| `tests/fins/test_download_failure_diagnostics.py` | 第一/第十一行的身份及原因字段 public 拒绝（4 case）；三种合法终态受理后禁止重新构造投影（3 case）；C2 doc。 |
| `tests/cli/test_fins_commands.py` | 真实 runtime→Service→validated stream→CLI 主入口：第一/第十一条 FAILED × 正常返回/typed 中止 × 无竞争/claim 前取消/claim 后取消（12 case）；C2 doc。 |
| `tests/fins/test_fins_ingestion_runtime.py` | C2 doc；更新 generic 受理的构造点 AST 断言，保留显式 warning、唯一 builder、必填实参及只读 warning 原断言，补同一两个 owner 的精确调用点。 |
| `tests/fins/test_cn_download_runtime.py` | 仅 C2 doc。 |
| `tests/fins/test_f5_result_contract.py` | 仅 C2 doc。 |
| `tests/cli/test_output.py` | 仅 C2 doc。 |
| `tests/service/test_fins_wait_adapter.py` | 仅 C2 doc。 |
| `dayu/fins/README.md` | 公共受理须完整校验、提交前准备合法诊断及取消原子边界。 |
| `tests/README.md` | public 拒绝真链、typed 快照和竞争回归说明。 |
| `docs/gateflow/download-failure-diagnostics-code-fix-20261010.md` | 本轮唯一新开发 artifact。 |

其余三个允许生产文件、其它批准测试、根 README、冻结历史 artifact、总控状态/裁决和双路报告保持本轮输入字节。生产修改没有落到 CLI、adapter、workflow 或来源仓储。

## Accepted findings 逐项状态

- C1：**已修复**（实施候选证据，待双路 re-review）。合法 typed 值仍可被更严格 public 守卫拒绝，拒绝发生在 result owner 构造及 claim 前。被拒绝快照没有已确认的 public 候选事实，整体公共受理失败沿既有异常 owner 安全映射为 EXECUTION，request-scoped 空 FAILED，不以 unsafe 文本伪造候选原因。typed 中止快照中的公共拒绝同样收口；本轮没有保留非法快照或过滤坏行。合法完整结果及原 cause 的既有安全策略不变。取消赢仍 130/null failure，claim 赢后取消无效；claim 后仅投递预构造事件。
- C2：**已修复**（实施候选证据，待双路 re-review）。root 22 项与 mimo qualified `test_download_cancel_preserves_downloaded_failed_prefix_and_claim.controlled_claim` 合并为 23 个函数。AST 核对这 23 项确为 S1 修改函数；每项显式中文参数/返回/异常，除 docstring 外原函数体和签名均保持一致，无旧函数顺手修补。临时清单和审核结果分别在 `code-fix-docstring-targets.json` / `code-fix-docstring-audit.json`。

新增反例先在冻结旧生产代码上取得 14 failed/2 passed：第十一行身份/原因负例未抛、真实链丢终态或 renderer 拒绝；第一行 owner 拒绝原本已成立。最终回归覆盖实际请求筛选条件、空已确认事实、唯一入队 RESULT、同源默认诊断、原通道与退出码、whole failure 六字段、无路径泄漏、无 MISSING_RESULT/通用命令失败。没有把非法“已确认事实”传给 CLI，也未注入生产新观测。

## 失败记录与必要复验

1. 首次临时 docstring helper 漏遍历 if 内嵌套函数，清单断言报 `AssertionError: 22`；此时 22 项 doc 已写入，未削弱任何测试断言。该 shell 顺序执行了 pyright，外层最终 exit 0 **不能证明 helper 通过**；不把它计入成功证据，未独立捕获该内部子命令退出码。修正 AST 遍历后单独执行 helper 实际 exit 0，23 项完整；最后独立 qualified audit exit 0，逐项参数/返回/异常和 body/signature 比对成立。
2. 首次 exact A+coverage 实际 exit **1**，**1496 passed/1 failed/0 skipped/3 warnings**。唯一失败为 `test_direct_result_builder_callsites_are_exact_and_never_rewrite_warnings`，原 AST 固定 2 callsite，当前 4 callsite；原 warning 的来源/必填/不可改写边界未变。按照受理边界迁移该断言并新增精确 owner 归属，而非保留 claim 后构造兼容 seam。修正后 focused 实际 exit 0，26 passed；因测试变动完整复跑 A 与 pyright。
3. 最终 pyright 托管 session 55334 已返回 exit 0 后误重复轮询，工具报告 `Unknown process id 55334`。没有重复运行或变更源码；前一次真实完成返回及最终日志保留，不以失败轮询证明命令结果。

旧 red、第一轮 A 及中间日志原样保留，不以后续成功抹除；三条 edgar deprecation warning 和 pyright 新版本提示单列，不是资源 skip 或类型错误。没有 broad 67 失败或原生产整批复跑。

## Docs decision

已实际读取根 README、Fins README 的 Agent 更新约束及 tests README 现有职责。根 README 的用户入口、参数、通道、JSON schema、退出码和日志操作没有本轮新变化，保持输入字节。Fins README 补当前稳定公共受理/原子提交边界；tests README 补已落地回归范围。不涉及新的分层/装配方式，无其它 README 触发；不重写历史 artifact。

## Residual（规范五类）

| 风险 / 未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| C1 公共校验晚于 claim、完整失败行延迟拒绝；C2 显式 doc 缺项；本轮 AST callsite 测试迁移 | fixed in current slice | 本 S1 fix 实施与验收证据；仍须总控双路 re-review，不作为 gate pass。 |
| 67 baseline 失败 | assigned to later work unit | Dayu CLI/Service 维护侧；沿 implementation-adjudication 与 baseline-validation 的六文件/装配/grammar/init/import owner 裁决。此次没有处理或复跑。 |
| 14 外部资源/平台 skip 的真实集成、SEC 原因治理、极端规模内存/输出/repr 压力 | assigned to later work unit | Dayu 集成验证与相应来源/性能维护侧。此轮 A 无 skip，但不消除既有 broad 资源限制，也没有压力测试。 |
| 旧 8 项原原因/日期/URL 未知、生产新观测、远端故障/下载/recovery、部署/合并验证、崩溃/SIGKILL/未捕获流后的历史追溯、外部 merge/approve/ready/comment | requiring new issue or explicit user decision | 巡检线/用户另定范围；沿既有证据和未知报告，不 query、补造原因或擅自执行。 |

`covered by later approved slice`：N/A（无其它已批准 slice）；`tracked by existing issue`：N/A（无指定 issue）。没有未分类 residual，也不借这两类隐藏 accepted finding。未覆盖的生产来源、真实远端与资源、历史恢复、极端规模均已如上分类，不宣称已验证。

## 实际验证：命令、真实 exit、计数、hash

全部 pytest/pyright/coverage 命令先激活 `.venv`；用托管 session 返回取得进程真实完成，标准流重定向到独占临时日志，无 tail/tee 管道。`tail`/`cat` 只在另一个只读命令读取日志，不用于证明 pytest exit。完整原始命令（含每次重定向）、session、exit、计数与日志 SHA256 在 `workspace/tmp/download-failure-diagnostics-20261010/code-fix-validation.json`，SHA256：`d0d39f761660f8c208ea7db3b0a3c552260bbeb6f66fdc2e16408f35d45b4d83`。

| 执行 | 真实 exit / 结果 | 托管 session / 原始日志 |
| --- | --- | --- |
| 冻结旧代码 red 反例 | 1；14 failed、2 passed、265 deselected、8 warnings | 90056 / `code-fix-red.txt` |
| 最初 focus | 0；22 passed、727 deselected、3 warnings | 21699 / `code-fix-focus.txt` |
| 补 owner 消费者后的 focus | 0；25 passed、727 deselected、3 warnings | 69077 / `code-fix-focus-final.txt` |
| 首次完整 exact A14 + coverage | 1；1496 passed、1 failed、0 skipped、3 warnings，125.05s | 90410 / `code-fix-A14-coverage.txt` |
| 修正旧调用点断言后的 focus | 0；26 passed、726 deselected、3 warnings | 27999 / `code-fix-focus-owner-final.txt` |
| **最终完整 exact A14 + 同 A coverage** | **0；1497 passed、0 failed、0 skipped、3 warnings，142.33s** | **2359 / `code-fix-A14-coverage-final.txt`** |
| 最终状态 `python -m pyright dayu/ tests/ utils/` | 0；0 errors、0 warnings、0 informations | 55334 / `code-fix-pyright-final-state.txt` |
| 同 A 数据 `python -m coverage report --include=... --fail-under=80 --precision=2` | 0；仅证明 coverage 阈值，不代替 pytest exit | `code-fix-coverage-report.txt` |
| 逐文件 coverage JSON 严格断言 | 0；五文件分别 >=80%，无额外排除或计算修改 | `code-fix-coverage-per-file.json` |
| qualified AST doc/body/signature 核对 | 0；23/23 仅 doc 变化且显式契约完整 | `code-fix-docstring-audit.json` |
| `git diff --check` | 0 | 工具直接返回 |

最终 exact A 命令（14 文件与 implementation artifact 一致；只在必要测试变动后复跑）：

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/download-failure-diagnostics-20261010/code-fix-final.coverage python -m pytest \
  tests/fins/test_download_failure_diagnostics.py \
  tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_direct_stream.py \
  tests/fins/test_f5_result_contract.py tests/fins/test_fins_ingestion_tools.py \
  tests/cli/test_output.py tests/cli/test_fins_commands.py \
  tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py \
  tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_f5_workflow_rebuild.py -q --tb=short \
  --cov=dayu.fins.download_contract --cov=dayu.fins.direct_events \
  --cov=dayu.fins.ingestion_runtime --cov=dayu.fins.pipelines.cn_pipeline \
  --cov=dayu.cli.output --cov-report=term-missing \
  --cov-report=json:workspace/tmp/download-failure-diagnostics-20261010/code-fix-coverage-final.json \
  > workspace/tmp/download-failure-diagnostics-20261010/code-fix-A14-coverage-final.txt 2>&1
python -m pyright dayu/ tests/ utils/ \
  > workspace/tmp/download-failure-diagnostics-20261010/code-fix-pyright-final-state.txt 2>&1
COVERAGE_FILE=workspace/tmp/download-failure-diagnostics-20261010/code-fix-final.coverage python -m coverage report \
  --include='dayu/fins/download_contract.py,dayu/fins/direct_events.py,dayu/fins/ingestion_runtime.py,dayu/fins/pipelines/cn_pipeline.py,dayu/cli/output.py' \
  --fail-under=80 --precision=2 \
  > workspace/tmp/download-failure-diagnostics-20261010/code-fix-coverage-report.txt 2>&1
```

上述三条在工具中分别托管并取得 exit，不用最终 shell 命令覆盖前一命令的返回码。最终 focused 为：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_download_failure_diagnostics.py tests/cli/test_fins_commands.py \
  -k 'direct_result_builder_callsites_are_exact or rejects_unsafe_complete_failed_projection or accepted_result_consumers_reuse_validated_projection or real_runtime_public_rejection or download_cancel_preserves_downloaded_failed_prefix_and_claim or download_runtime_full_result_and_durable_budget_same_source' \
  -q --tb=short > workspace/tmp/download-failure-diagnostics-20261010/code-fix-focus-owner-final.txt 2>&1
```

同一最终 A 集合逐文件覆盖率（4131 statements，432 miss；总计 89.54%，不替代单文件门槛）：

| 文件 | Stmts | Miss | Coverage |
| --- | ---: | ---: | ---: |
| `dayu/cli/output.py` | 208 | 30 | 85.58% |
| `dayu/fins/direct_events.py` | 481 | 47 | 90.23% |
| `dayu/fins/download_contract.py` | 475 | 55 | 88.42% |
| `dayu/fins/ingestion_runtime.py` | 2509 | 220 | 91.23% |
| `dayu/fins/pipelines/cn_pipeline.py` | 458 | 80 | 82.53% |

固定绝对 `.venv/bin/dayu-cli`、fresh 空根、仓库外 cwd 的 `test_fixed_cli_download_diagnostics_on_empty_rebuild` 随最终 A 通过；保留实际 subprocess returncode、唯一 stdout 诊断、stderr 无诊断、空 rows/counts 和 succeeded 的原断言。未另跑 fixed binary、真实远端或生产来源，不将空 rebuild 冒充远端获取或旧 8 项恢复。

| 证据 | SHA256 |
| --- | --- |
| 最终 A 日志 | `36dec5a0b4d99a3ade0051ce8a18242dcaf6a9871624eb4e014a6a33c0918adf` |
| 最终 pyright 日志 | `46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb` |
| 最终同 A coverage JSON | `40b8ffe21ee8fd4530b222c7ed586792f7668daf166f4eed52c612e5ede98ebc` |
| coverage report | `cae6bd03a0f8192c282bb3dc7f9f6d98cb62c13e55c35c06b0eae4ccb7ef5c4b` |
| coverage 逐文件 | `fac8059a1eff484947f318563a3a1993ffbdd1c0bedad1d750555fab9f565fee` |
| 最终 focused | `1dec8a380f3239072428012569695e2599ec84e61c3ace2e51b09b322b3bb2d6` |
| 首次 A 失败日志 | `ec8756ab4865c84a593716c2177e2f84ed88ba479cc7810edfbc1ee0da0b7834` |
| red 失败日志 | `c9112dcb08e4cc31186dc530ea98704af53976b610e386c6b5c7956a7cf0c748` |
| qualified doc 审核 | `ff97687a53765232a7629b72643c7fb1f98b1d6d556c9c09f0a2a11386f7a1ef` |
| 本轮输入核对 JSON | `19655ec1ec09eeef346e10cdadb028dfa840c250251421bd9077575b0f780828` |
| 所有冻结/owned 路径前后 hash JSON | `a5fd13efc1c97f84588f1dcb19f43a7bbbdc2ab8bfa73de1322a7139ea92bf16` |
| 本轮相对冻结输入 11 文件 delta patch | `7af4d9f3c4ab1c3cf1ebc47cda2bc11bb0fc309f17a7a728c6740417e7dabdc5` |

后两项证据分别为 `code-fix-output-hashes.json` / `code-fix-delta.patch`；新 fix artifact 独立列出，不对自身作循环 hash 承诺。冻结输入文件仅上述 11 个批准已有文件变化，另外新增本报告；其它冻结文件、state/code-adjudication、两份报告字节未变。HEAD/branch、原 manifest/patch 不变。

## Completion 与交接

本轮 **C1/C2 fix 实施及验证完成**。两个 accepted finding 的实施状态均为已修复，尚待总控及独立双路 re-review 验证；没有 blocking open question 或待完成验证 session。完整 evidence、失败记录、owner 决策、docs decision 和五类 residual 已记录。

下一未完成 gate / entry point：**总控发起 ds-flash 与 mimo 双路 re-review**，审阅本轮最终源码、测试、职责内 README、fix artifact 和冻结/验证证据；由总控裁决，不自行宣布 code review、slice 或 work unit pass。

遵守停止边界：未派子 Agent；未改 goal/plan/总控或历史 artifact；未生产 query、新来源/网络/下载/overwrite/recovery；未处理 baseline67；未 stage/commit/push/PR/merge/approve/ready/comment，未进入后续 gate。本实施者到此停止。
