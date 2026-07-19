# WU-SEMANTIC-OWNERSHIP-01 Umbrella Aggregate Regression Accepted-Finding Fix Plan

## 0. Gate identity / verdict

- 状态：`PLAN_ONLY / S3_STOP_F02_SECOND_PLAN_REVIEW_FIX_COMPLETE / CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW_PENDING / IMPLEMENTATION_NOT_AUTHORIZED`。
- umbrella：`WU-SEMANTIC-OWNERSHIP-01`。本计划只处理既有 umbrella aggregate regression 的 Controller accepted findings，不创建新 WU，不改变原 WU 的目标、设计真源或 residual destination。
- 当前第二次 S3 plan-review-fix gate 基线：branch `phaseflow/host-issues-control`；accepted corrected-plan base / HEAD `48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe`；parent `9e7a4e9d4796b9c382d44494bb10efa64787b199`；tree `b4904404c43dd0c36132433af74dd6740d24c713`；aggregate parent仍为`3410d7422655c56bdf13c643f77c27f40b9d4550`。
- 本次最高 plan-review-fix authority 是 `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-controller-adjudication.md`（SHA-256=`725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb`）。它接受并合并四组 plan-only fix：`S3-P2-PF01`—`S3-P2-PF04`；immutable reviewed plan SHA-256=`466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`。MiMo review SHA-256=`6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc`，DS review SHA-256=`6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822`。
- 本次plan-only fix gate只允许修改本文件，并新建`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-codex.md`。production、tests、utility、README、workflow、control、既有continuation/correction/validation/Controller/review artifacts全部禁止修改；不得继续implementation或coverage、运行implementation tests、执行review、stage、commit、push、开PR、进入code review / aggregate / closeout或启动subagent/reviewer。
- Slice 3已完成的Docling delta与六个测试路径现存delta必须按 entry SHA-256 原样保护：`dayu/documents/processors/docling_processor.py`=`e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649`，`tests/documents/test_processors.py`=`6aba755cdb920f2f427f8f0375886ce14eb7b32f521f2d5ecde3c20d58be8f0b`，`tests/fins/test_sec_pipeline_download.py`=`f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21`，`tests/fins/test_processor_read_consistency.py`=`e3aec818f1a397b46c004de1e6dc2b58bd1eb334d8c9cc142f97baecdea09489`，`tests/fins/test_fins_ingestion_tools.py`=`6ece9288834ab3953be8880276079a003f58a02629a2230459d728b95ff2f747`，`tests/host/test_effective_execution_config.py`=`e3a85caded7bda956e95d5ebd336cd60815ec1d227c134f46a9678d6a96c6acf`，`tests/runtime/test_argparse_exit.py`=`3aa607842a96b7425b964f3c030dc2b427e5bba0dd89abc65e20ed7306ce3f3d`。
- 当前Controller-owned/protected artifacts必须保持本plan-review-fix gate实际entry hash：S3 continuation=`3432724515aff3d1591a0c91ad83b31b7085fd01b39d7fe418ef68839951aaa7`；`docs/host/issues-implementation-control.md`=`7bcbacccf14b2b0d1fb73d935453709403a5887c1ed20e03dd475fc93659430b`；second-defect Controller=`9a7f640fad66a8e26edf86e8fea72d09dbadf1c8e80f7d12e6a14106a8a67fa8`；correction artifact=`15b53e8223883e572653eb4d26aa54390d2081ba84d986f10523722926da86a6`；correction validation=`36df4cedf04e01746446de96d92b1b5e6f035d9b601e54ea8b084cdd456d836f`；MiMo review=`6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc`；DS review=`6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822`；plan-review Controller adjudication=`725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb`；corrected-plan accepted-commit validation=`4d0b7b64544584be9dca8a57301cf3d27343130fad5664c9635681e45c88eba5`；resumed implementation authorization=`a21eaabc88885a5134f000a94e965e495fbcd9f79a9b080abb857ea31967eb3c`。Immutable reviewed plan entry SHA-256=`466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`。
- 本计划固定三个 implementation slices，精确关闭 `AR-F01`—`AR-F05`。`AR-F06` 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，`AR-F07` 保持 `PENDING_RELEASE_BLOCKER`。
- `S1-SEC-F01` 按 2026-07-19 用户产品裁决关闭为 no-code blocker：本地 Config 与 Host SQLite / EventLog 是同一受信任产品域，内部持久化 resolved provider headers / API key 不要求 production redesign；Tool Trace、audit、public / LLM-facing projection、日志、diff 与 review surface 仍要求 secret 明文为零。
- MiMo/DS双路完整plan review与Controller逐条裁决已经完成；本次只修`S3-P2-PF01`—`S3-P2-PF04`。唯一next gate是Controller validation与AgentMiMo/AgentDS对完整修订版及本次fix artifact的双路完整re-review；只有两路均通过且Controller明确重新授权后，才可恢复Slice 3 implementation。恢复入口必须先关闭`S3-STOP-F02`；已完成的`S3-STOP-F01` Docling delta与8-node caption matrix保持review-pending、不得回滚、重写、单独review或单独commit。

## 1. Source of truth 与已核对证据

本计划原始 accepted 版本已读取下列真源；本次 correction 又严格按用户指定顺序完整重读 `AGENTS.md`、两份 control、overdesign discussion、Host / Engine / Tool / Fins / UI 五份 design，随后完整读取 user-decision record、prior evidence / adjudication、两路 corrected design-truth reviews、accepted aggregate plan与其 commit validation、Slice 1 authorization / implementation artifact及五份 stop adjudication。精确读取清单与 SHA-256 记录在本 gate artifact。裁决优先级如下：

1. `AGENTS.md`。
2. `docs/host/issues-implementation-control.md` 当前工作区状态，尤其 current gate、aggregate adjudication 与 next-entry condition。
3. `docs/phaseflow-umbrella-optimization-control.md`。
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`。
5. 五份永久 design 真源：
   - `docs/host/design.md`
   - `docs/engine/design.md`
   - `docs/tool/design.md`
   - `docs/fins/design.md`
   - `docs/ui/design.md`
6. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`，尤其 aggregate regression、security、deferred/no-code 与 closeout gates。
7. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` 的 fresh command/evidence ledger。
8. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` 的最终 finding disposition。
9. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md` 对 `AR-PLAN-PF01..02` 的唯一本轮 plan-fix 授权；该文档已完整读取，SHA-256 为 `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06`。
10. 当前 HEAD 代码、测试、配置与 import graph。历史 artifact 只能证明历史运行；与当前代码冲突时，以当前代码和 Controller adjudication 为准。

11. 本次最高优先级 correction authority：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-user-decision-controller-record.md`，SHA-256=`4a75899fbdb8244d93f1633b0be3f36e65d2ae211a3211f57f326289f6c3f12b`。它 supersede 旧的“Host 不接收 API key 明文 / EventLog 必须零 headers”设计冲突与 `S1-SEC-F01` production redesign 建议，但不 supersede Tool Trace、audit、public / LLM-facing projection 与日志的零明文要求。

12. Slice 3 correction authority：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-production-defect-controller-adjudication.md`。Controller已独立用真实Docling serialize/load与public `DoclingProcessor.list_tables()`复现caption丢失，并确认当前`docling-core==2.74.0`的`TableItem.captions: list[RefItem]`与`RefItem.resolve(doc)`是唯一第三方公共契约。该裁决只 supersede Slice 3“九production owners零diff”的旧假设，精确开放Docling table projection owner；其它owner、slice、security与deferred裁决不变。

13. Slice 3 plan-review-fix authority：MiMo review SHA-256=`f3d59d0ac7e6f5528fd90f3ab6104f504b08242093d2f658bd505371a620c1fa`、DS review SHA-256=`c606f94e9353862ec30600360dfce2b21662cfbb13137d5c0b4422d0ed02fa3b`与Controller adjudication SHA-256=`c83e76d7c2d95a1df3d4f969d39c4ca907183947a977b2150672e9e6f19ee450`。本轮只实施Controller接受的`CF01`—`CF05`计划修正；warning/import统一、NaN `ValueError`、NBSP特例、`text_utils`抽取、context fallback及其它rejected/no-action提案不进入计划或实现。

14. Slice 3 second production defect correction authority：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md`记录同源stop evidence；`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md`作唯一owner裁决。该裁决只新增开放`dayu/fins/processors/sec_form_section_common.py`的虚拟章节构建/刷新/table ownership state machine；保持DocumentProcessor marker contract、`SecProcessor`空marker实现、已完成Docling delta、六测试路径、security、quota、deferred与219/219门禁不变。

15. Slice 3 second production defect plan-review-fix authority：immutable plan SHA-256=`466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`；MiMo review SHA-256=`6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc`；DS review SHA-256=`6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822`；Controller adjudication SHA-256=`725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb`。本轮只实施Controller接受的`S3-P2-PF01`—`S3-P2-PF04`；MiMo 05作为独立finding `rejected-as-duplicate`，其有效guard精确化已归入`S3-P2-PF01`；DS-F03的“空列表行为未知”事实判断`rejected-as-evidence-invalid`，但其zero-diff guard证据与public re-entry验证已归入`S3-P2-PF03`。不得新增第五组fix、public schema、production/test路径或allowlist。

当前 correction 的 owner 结论是：ConfigLoader 仍只产生 typed config；Service / execution environment 解析 secret 并构造 resolved typed `RunnerSpec`；Host admission 持久化 exact effective execution canonical fact，dispatch / retry / replay / recovery 恢复该内部 truth；每个 Tool Trace、audit、HostEvent、memory / compact、runner-input / observation 与 log projection owner分别做显式安全字段选择。禁止 Host-safe / Engine-only split、header descriptor、secret resolver callback、secret manager或统一 tool authorization framework；本计划不扩张 CLI init secret 存储，也不进入 Issues 142、151、175、177、178。

以下清单是原始 plan-fix gate 的历史 protection baseline，不替代本次 correction artifact 记录的 fresh workspace baseline；其中所有 Controller-owned / pre-existing changes 继续不得被修改或 stage：

```text
 M  93dd662e755b0f7bbfc8ad82045bc54ed61b94d7bf3df22f14c385b242e56100  docs/host/issues-implementation-control.md
??  eb6528c2c1e59d4791a62b5cbb5f90fe84d517db368cd2cae4e51da253cacb11  docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md
??  73dfecd1aed86ca59c44d6b40c012add309b261539b8f25d129a728ae2942539  docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md
??  bddc028b58eda529a295e70fa6652613265c55b32af511fb7e446db16037a4d4  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md
??  a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md
??  94f315701dfe2d4ff432c60615dfd5f93c2615699462c59607c2a1bcafb6e615  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-ds.md
??  2cab2ad9d1348a9f934f86857e3442895a3442149f343d29a4dc2d34aeaedb36  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo-cleanroom.md
??  2cb0496819ac6709d3d53d85fb27f468b3ce790a0628f9b29d8645713de1cf20  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md
??  03c41be0313394b2c8cf3e8ab2309a09665668545d4b7e7a1682ffa201a498ea  docs/reviews/wu-semantic-ownership-01-r12-accepted-implementation-commit-controller-validation.md
```

## 2. 第一性原理判断与 owner adjudication

### 2.1 动机成立

Aggregate regression 不是重复验证。R01—R12 的 accepted evidence 只证明各自当时的 slice tree，不能证明最终整合树的全量测试顺序、跨层 import、当前 artifact schema、逐文件 coverage 或真实 Windows runner。当前 direct evidence 已稳定复现五组本地 actionable defects，因此不能用历史 sub-WU PASS 覆盖本轮失败，也不能提前进入 aggregate deepreview。

### 2.2 Findings closure matrix

| ID | 当前代码直接证据与唯一 owner | 本计划 disposition |
| --- | --- | --- |
| AR-F01 | `tests/service/test_host_admin.py::_write_host_runtime` 写出的 current host runtime profile 缺少 `ConfigLoader` 已要求的 `wait_poller_policy`；这是 test fixture schema owner 缺陷，不是 product loader 容错缺陷 | Slice 1 只修 test fixture；禁止给 production 加默认值/fallback |
| AR-F02 | Service 直接 import `dayu.fins.direct_stream` 与 `dayu.fins.tools._ingestion_tool_helpers`；现有 Service allowlist 已允许 `dayu.fins.direct_events` 与 `dayu.fins.ingestion`，故问题是 Fins public contract owner 放错边界，不是 allowlist 太窄 | Slice 2 做一次物理 owner migration；禁止扩大 allowlist、兼容 re-export、lazy import、duplicate enum/protocol |
| AR-F03 | `utils/smoke_web_ci.py::main` 的 standalone `configure_root=True` 是 operator logging 语义；同进程测试直接调用 `main` 后未恢复全局 logger state，导致后续两个 node 顺序依赖失败 | Slice 1 只在 `tests/tools/web/test_smoke_web_ci.py` 增加 in-process harness isolation；standalone product logging 零改动 |
| AR-F04 | current compactor 成功发布 `context_compaction` schema v3 artifact；测试仍猜 `accepted_candidate.candidate_id == llm-compact:{run_id}`。Current runner-call manifest 已发布 `host_run_id`、`runner_call_kind=compactor_proposal` 及 `compactor_identity.compaction_request_digest`，compact artifact 发布同一 `compaction_request_digest` | Slice 1 用 manifest run identity -> request digest -> compact artifact digest equality 的唯一关联；禁止恢复 candidate_id、raw guess、fallback 或 loose scan |
| AR-F05 | aggregate parent 到当前树的219个changed production Python仍有九个owner待fresh达到80%；`S3-STOP-F01`已在Docling table projection owner完成implementation。继续coverage时，真实public `TenKFormProcessor`暴露`S3-STOP-F02`：marker contract允许空字符串安全降级，但refresh又强制base/virtual table refs全等，合法SecProcessor-backed 10-K含表即构造失败 | Slice 3先在`sec_form_section_common.py`唯一owner实现原子virtual/base发布并关闭`S3-STOP-F02`；保留Docling delta，随后继续九owner coverage；其余七个production owner零diff，最终仍要求219/219 >=80% |
| AR-F06 | coverage instrumentation 下同一 R05 scheduler close/promotion node复现；R05 已把真实 bug裁决给未来独立 Host scheduler/lifecycle work item | 不写代码、不 waiver、不标 resolved；canonical non-coverage 不排除，coverage 仅精确排除这一个 node |
| AR-F07 | 当前远端无可用 Actions workflow/run/artifact，Darwin skip 不能证明 cmd.exe / Windows init | 本地 slices 不改 workflow、不伪造 PASS；最终 release 继续被真实 `windows-latest` evidence 阻塞 |
| S1-SEC-F01 | fresh configured-secret scan 的唯一命中 owner 是 Host internal `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers`；Service 解析 secret，Host 冻结 exact execution truth。Tool Trace event filter 不消费该 event；audit、HostEvent、run-input / memory / compact 与日志 owner都没有透传该字段，fresh projection / output / review / diff scan 为零 | `CLOSED_AS_NO_CODE_BLOCKER`；内部 Config / Host durable 命中做 accepted classification，Slice 1 只补 owner-level negative tests与分 surface scan，不改 production、不增加 slice |

### 2.2.1 Local trust / projection owner adjudication

`S1-SEC-F01` 的 production redesign 动机不成立。用户已明确裁决本地 Config 与 Host SQLite / EventLog 属于同一受信任产品域；为了让 dispatch、retry、replay、recovery使用同一份 exact effective execution truth，Host 持久化 resolved `RunnerSpec.headers` 是 owner-correct 行为，不是新增泄露面。当前代码与 real output 的直接证据也只证明该内部路径有值，不能把它外推成 Tool Trace、audit 或 LLM-facing leak。

本次只读 owner evidence 的 disposition 固定为：

| Surface | 唯一 projection owner / direct boundary | 当前 verdict | Slice 1 validation |
| --- | --- | --- | --- |
| Host internal effective execution | `dayu/service/host_assembly.py::_render_headers` -> Host admission -> `dayu/host/_execution_config_projection.py::runner_spec_json` -> `USER_INPUT_ACCEPTED` -> dispatch / replay restore | `ACCEPTED_TRUSTED_INTERNAL`；允许 exact Config / Host internal owner path 命中 | 用 real configured-value scan做逻辑 row/path分类；不要求清零，不改 production |
| Tool Trace hot / cold / query | `dayu/host/tool_trace.py::ToolTraceProjectionConsumer.event_filter` 与 typed extract / render helpers | `NO_CURRENT_LEAK`：filter 不包含 `USER_INPUT_ACCEPTED`，extract 不复制 effective execution config；fresh Tool Trace output scan为零 | synthetic sentinel canonical fact必须被filter跳过，hot / cold / query均零 sentinel |
| Audit JSONL / query | `dayu/host/audit.py::build_audit_json_line` | `NO_CURRENT_LEAK`：固定字段只含refs / digests / summaries，不复制 payload；fresh audit scan为零 | source event payload含sentinel时，整行序列化仍为零 sentinel并保持exact key contract |
| Public HostEvent / read API | `dayu/host/read_api.py::_host_event_from_row` / `_activity_from_row` | `NO_CURRENT_LEAK`：`USER_INPUT_ACCEPTED` 只成为无 activity 的typed progress，raw payload不进入DTO | public DTO / serialization零 sentinel |
| LLM-facing run input / memory / compact | `dayu/host/run_input.py`、`dayu/host/memory.py`、`dayu/host/compact_material.py` 的 user-input field selectors | `NO_CURRENT_LEAK`：只读取 `display_text`；resolved `RunnerSpec` 仍可作为 Engine执行参数，但不是LLM message/material | 只扫描 `messages`、memory / compact material与runner-call observation，不得错误要求 Engine执行所需 `request.runner_spec.headers` 清零 |
| Operator logs | 各 Host / Service / Engine logger callsite与既有 Engine diagnostic redaction owner | `NO_CURRENT_LEAK`：调用点记录ids / counts / refs / error classes，fresh log output scan为零；Topic 8现有redaction tests继续有效 | resolved runner header sentinel不进入caplog；不改变Engine exception redaction/truncation行为 |

上述 verdict 来自当前代码与实物扫描，不是按字段名猜测。若 Slice 1 owner test 暴露真实 projection leak，必须立即停止并提交同一 umbrella 内的最小复现：修复边界只能是该行对应的唯一 source projection owner或其直接 typed input validation，不得在下游UI、adapter、scan脚本或测试fixture中做黑名单、字符串替换、fallback或兼容 repair。本 plan当前没有发现真实 leak，因此 production allowlist保持为空。

### 2.3 AR-F02 唯一 public Fins contract owner

当前 `ValidatedFinsEventStream` 与 `FinsEvent`、`FinsDirectStreamProtocolError`、`FinsOperationKind` 是同一个 direct event/terminal contract。把 validator 单独放在 `dayu.fins.direct_stream` 迫使 Service 越出既有 public boundary。正确修复不是放宽 Service，而是把 validator 实现物理迁入现有 public owner `dayu/fins/direct_events.py`：

- `dayu/fins/direct_events.py` 成为 direct event、terminal protocol error、validated stream state machine 的唯一真源。
- 删除 `dayu/fins/direct_stream.py`；所有 production/test consumers 直接 import `dayu.fins.direct_events.ValidatedFinsEventStream`。
- 不在 `dayu/fins/__init__.py`、旧模块、其他模块或 `TYPE_CHECKING` 分支 re-export；不保留 wrapper/facade；不使用 importlib/lazy import。
- validator state machine、原异常身份、close-at-most-once、terminal result identity 和 public error contract保持不变；本轮只迁 owner，不重设计 protocol。

Awaiting resolution mode 是 Fins ingestion provider 与 Service host assembly 共享的 public closed contract，不属于 tools 私有 helper：

- 新建 `dayu/fins/ingestion/awaiting_resolution.py`，唯一拥有 `AWAITING_RESOLUTION_MODE_CONFIG_FIELD`、`AwaitingResolutionMode` 与 `parse_awaiting_resolution_mode`。
- 从 `dayu/fins/tools/_ingestion_tool_helpers.py` 物理删除上述定义；providers、Service 与 tests 直接 import 新 owner。
- `dayu/fins/ingestion/__init__.py` 不 re-export；Service 已允许 `dayu.fins.ingestion`，`tests/service/test_import_boundary.py::SERVICE_ALLOWED_IMPORTS` 不增加任何项。
- 不在 Service 重建枚举、Protocol、parser、字符串闭集或配置字段名；Fins owner 继续产生/校验该语义，Service 只消费 typed contract。

### 2.4 AR-F04 current run/artifact association

测试 oracle 必须按当前发布事实执行以下精确链路：

1. 在 runner-call artifact 集合中，以 current schema version、`host_run_id == run_id`、`runner_call_kind == "compactor_proposal"` 精确定位唯一 manifest；缺失或重复立即失败。
2. 从该 manifest 的 typed `compactor_identity.compaction_request_digest` 读取非空 SHA-256 digest；同时断言 `parent_host_run_id == host_run_id`。不得把 run id 拼接成 candidate id 或从文件名/顺序/mtime 反推。
3. 在 compact artifact 集合中，以 `artifact_kind == "context_compaction"` 且 top-level `compaction_request_digest` 与 manifest 完全相等，精确定位唯一 artifact；缺失、重复、schema/type 不符立即失败。
4. 对定位后的 artifact 继续执行 existing current-schema、continuity、accepted candidate 内容断言。删除 `_CANDIDATE_ID_FIELD` 与所有 `llm-compact:{run_id}` 逻辑。

这里的 raw JSON 读取只负责进入 current schema oracle；关联事实只能来自 owner-published exact fields，并通过严格 mapping/text/digest/uniqueness checks 消费。禁止 unknown-field probing、`dict.get` 猜测链、候选回退、扫描第一个匹配项或历史 schema 兼容。

### 2.5 AR-F03 in-process logging boundary

`utils/smoke_web_ci.py` 的 standalone CLI 确实需要 root logger 输出第三方诊断，因此不能把 `configure_root=True` 删除或改为默认。唯一缺陷是 pytest 在同一个解释器内多次调用 `main`，却没有隔离进程全局 logging registry。

Slice 1 的 test-only harness 必须：

- 在每一次 in-process `smoke.main(...)` 调用外层统一包装，而不是只修一个 case。
- 调用前 snapshot root 及当前 logging registry 中所有 concrete `logging.Logger` 的 level、handlers、filters、propagate、disabled；记录 registry identity。
- 在 `finally` 中恢复原 handler identity/order 与全部 logger fields，卸载并只关闭本次调用新增的 handlers，清除本次调用新建的 logger entries；成功、返回错误码、`SystemExit` 或被测异常都必须恢复。
- 不复制 `_DEFAULT_THIRD_PARTY_SUPPRESSIONS` 等 production 列表，不针对两个失败 logger写特例，不修改 `tests/conftest.py` 的全局 fixture。
- 增加 harness contract test：预置 root 与至少一个 named logger 的非默认状态，分别覆盖成功和失败调用，断言调用后 registry/logger/handler identity 与状态完全一致。

### 2.6 S3-STOP-F02 virtual-section projection owner

问题动机与严重性成立，且root cause由同一公开调用链与同一数据事实直接闭合：`DocumentProcessor.get_full_text_with_table_markers()`约定不支持marker注入时返回空字符串并由上层安全降级；`SecProcessor`正确返回`""`；`_assign_tables_to_virtual_sections()`因此不产生mapping；同一次`_refresh_virtual_section_state()`却要求全部base table refs等于virtual table refs。任何“合法虚拟章节 + 至少一张base表格 + marker capability不可用”的SecProcessor-backed表单都必然在构造期失败，不是测试夹具、日志或coverage间接推断。

唯一owner是`dayu/fins/processors/sec_form_section_common.py`内虚拟章节构建、刷新与table ownership state machine。修复语义固定如下：

- 定义owner-private typed enum/state，成员名固定为`BUILDING`、`VIRTUAL_PUBLISHED`、`BASE_FALLBACK_PUBLISHED`。`_initialize_virtual_sections()`只负责把新实例初始化为`BUILDING`并建立候选；`_refresh_virtual_section_state()`是唯一terminal transition owner，只允许`BUILDING -> VIRTUAL_PUBLISHED | BASE_FALLBACK_PUBLISHED`、`VIRTUAL_PUBLISHED -> VIRTUAL_PUBLISHED`受约束刷新与`BASE_FALLBACK_PUBLISHED -> BASE_FALLBACK_PUBLISHED`幂等no-op。不得从`_virtual_sections`、空dict/list、异常、时间、日志或偶然顺序反推状态。
- 虚拟章节projection是单一原子发布状态。refresh必须先在owner-local候选中完成section tree、base tables、raw marker material、table→section与section→tables全部校验；校验结束前不得清空、局部写入或向public consumer暴露`_virtual_sections`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`的半套组合。
- 五个public consumers逐一使用同一mode guard：`list_sections()`、`list_tables()`、`get_section_title()`、`read_section()`、`search()`在`mode != VIRTUAL_PUBLISHED`时都直接委托base processor对应public contract；只有`VIRTUAL_PUBLISHED`可消费virtual sections/index/mapping。当前consumer数量固定为五个，不沿用reviewer“六个”的错误计数。
- base tables为空时，空mapping本身就是完整证明，合法虚拟章节发布`VIRTUAL_PUBLISHED`；不得因marker unsupported无意义地回退。base tables非空且marker缺失，或无矛盾raw marker proof无法为**每一个**public base table证明唯一virtual-section ownership时，整体发布`BASE_FALLBACK_PUBLISHED`：清空/禁用全部candidate virtual projection，五个public consumers统一消费底层processor同一套sections/tables/title/read/search contract。
- 删除`_filter_table_refs_by_availability()`及其全部调用，不再静默过滤raw marker refs；删除`_assign_unmapped_tables_by_position()`及其调用，不再按最近前驱/第一个section补齐。候选构建必须保留raw marker refs与出现次数/范围归属证据，禁止在完整性与矛盾校验前丢弃信息。
- 校验顺序固定为：先要求每张public base table具有非空、唯一`table_ref`，缺失或重复都`ValueError` fail-closed；再判定raw marker ref不在base refs中的dangling；再判定同一marker ref重复出现、落入多个section、section tree悬挂或table→section/section→tables双向矛盾。任一矛盾先`ValueError`，不得进入fallback；只有这些检查全部通过后，`base_refs - mapped_refs`非空才是incomplete proof并整体base fallback。incomplete与dangling同时存在时dangling优先fail-closed；无dangling但marker range/title不能唯一归属时属于incomplete，必须whole-base fallback。只有集合完全且双向一致才一次发布`VIRTUAL_PUBLISHED`。
- virtual `list_tables()`只按已发布全量exact mapping重写每一张base table的`section_ref`；删除`fallback_ref`、`last_known_ref`与“底层已有virtual ref即保留”等下游补偿。base mode完全透传base tables，禁止用标题相似度、底层偶然`section_ref`、表格顺序、日志或其它启发式补缺。
- `_initialize_virtual_sections()`内第一次`_refresh_virtual_section_state()`既是首次publication decision，也是当前public构造失败的真实入口；它与10-K/10-Q subclass第二次`_postprocess_virtual_sections()`/refresh复用同一typed终态。首次fallback必须清空candidate并发布`BASE_FALLBACK_PUBLISHED`，之后refresh不再读marker/base、不重建candidate、不抛第二次失败；virtual已成功发布时仍允许现有postprocess按identity约束刷新。当前`expand_ten_k_virtual_sections_content()`与`expand_ten_q_virtual_sections_content()`均由现有`if not full_text or not virtual_sections: return`保证空candidate zero-diff；plan锁定该直接证据并用public 10-K/10-Q re-entry验证，guard漂移才STOP，不扩form-common或subclass allowlist。
- `DocumentProcessor` marker contract与`SecProcessor.get_full_text_with_table_markers() -> ""`保持零diff；不修改`sec_processor.py`，不新增DOM/raw HTML marker、capability schema、兼容分支或第二套table-owner resolver。

该方案优于“把表格塞入第一/最近章节”或扩展SecProcessor marker能力：前者把未知业务归属伪装成事实，后者在已有同源base contract可安全复用时扩大了技术与schema边界。正确最小修复是在owner state machine内原子选择完整virtual projection或完整base projection。

## 3. Global scope lock

### 3.1 Implementation mutable production allowlist

三个slices合计只允许下列production paths；Slice 1 production allowlist为空，Slice 3的整体production allowlist精确包含已完成`S3-STOP-F01` owner与本次新增`S3-STOP-F02` owner：

```text
# Slice 2 only
M dayu/cli/commands/fins.py
M dayu/fins/direct_events.py
D dayu/fins/direct_stream.py
A dayu/fins/ingestion/awaiting_resolution.py
M dayu/fins/ingestion_runtime.py
M dayu/fins/tools/_ingestion_tool_helpers.py
M dayu/fins/tools/download_provider.py
M dayu/fins/tools/preprocess_provider.py
M dayu/fins/tools/upload_provider.py
M dayu/service/fins_direct.py
M dayu/service/fins_wait_adapter.py
M dayu/service/host_assembly.py

# Slice 3 correction only
M dayu/documents/processors/docling_processor.py
M dayu/fins/processors/sec_form_section_common.py
```

本次第二次correction恢复implementation后只允许新增`sec_form_section_common.py` delta；现存Docling delta按§0 hash受保护，不得继续修改、回滚或重写。任何第三个Slice 3 production path都是stop condition，不能以pyright、Ruff、coverage、import cycle、测试便利或README同步为由自行扩域。

### 3.2 Implementation mutable test allowlist

```text
# Slice 1 only
M tests/service/test_host_admin.py
M tests/tools/web/test_smoke_web_ci.py
M tests/host/test_public_compact_smoke.py
M tests/host/test_audit_sink.py
M tests/host/test_tool_trace_projection.py
M tests/host/test_host_activity_event_projection.py
M tests/host/test_run_input_builder.py
M tests/host/test_logging.py

# Slice 2 only
M tests/cli/test_fins_commands.py
M tests/fins/test_fins_direct_stream.py
M tests/fins/test_fins_ingestion_tools.py
M tests/service/test_fins_direct.py
M tests/service/test_fins_wait_adapter.py
M tests/service/test_host_assembly.py

# Slice 3 only
M tests/documents/test_processors.py
M tests/fins/test_sec_pipeline_download.py
M tests/fins/test_processor_read_consistency.py
M tests/fins/test_fins_ingestion_tools.py
M tests/host/test_effective_execution_config.py
A tests/runtime/test_argparse_exit.py
```

Slice 1 后五个新增 allowlist path 只允许加入 §2.2.1 / §4.1 定义的 configured-secret projection sentinel tests；不得借此修改 projection contract、重写现有测试或触碰 production。correction entry 已有 delta 的前三个 Slice 1 tests必须在 plan review与恢复 implementation entry前保持上述 SHA-256 不变；后续 implementation只能在 Controller重新授权后继续其既有 Slice 1 delta。同一路径 `tests/fins/test_fins_ingestion_tools.py` 可在 Slice 2 迁移 public owner import，并在 Slice 3 补 preprocess owner cases；每个 slice 的 diff 与 review 必须只包含该 slice 新增的语义。第二次plan-correction entry的六个Slice 3路径按§0 exact hash受保护；重新授权后只能保留已有cases并在同一六路径内增量补owner/public反例，不得删除、改写或弱化已完成Docling caption matrix、preprocess/Host/runtime coverage与`S3-STOP-F02`最小复现。`tests/service/test_import_boundary.py` 是验证 oracle，不在 mutable allowlist，必须零 diff。

### 3.3 Slice 2 mutable validation-utility allowlist

```text
# Slice 2 only
M utils/smoke_host_public_awaiting_entrypoint.py
```

该独立 allowlist 只允许把 `AwaitingResolutionMode` 的 import 从 `dayu.fins.tools._ingestion_tool_helpers` 迁到唯一 public owner `dayu.fins.ingestion.awaiting_resolution`。九个业务/类型使用位置与其它行必须保持不变；不得复制 enum、parser 或 config field，不得新增 fallback、兼容路径或其它 utility 改动。该路径在 Slice 1 与 Slice 3 必须零 diff。

### 3.4 README allowlist / decision

- 当前 plan-only gate 不修改任何 README。
- Slice 1：读取 `tests/README.md` 的更新约束并记录 `NO_UPDATE`；test fixture/harness/oracle不改变测试入口或最终用户工作流。
- Slice 2：只允许按现有职责更新 `dayu/fins/README.md`，把文件树和 direct/awaiting public owner描述迁到新真源；这是代码路径变化后的必需同步。读取并裁决 `dayu/service/README.md`、`tests/README.md`、根 `README.md` 与 `dayu/README.md`，预期均 `NO_UPDATE`，因为没有用户可见命令、层级关系或 Service 行为变化。
- Slice 3：只允许按`dayu/fins/README.md`现有开发者手册职责更新Processors/关键机制中的稳定语义，说明virtual-section state machine只在marker完整证明全部base table ownership时发布virtual projection，否则整体消费base processor同源section/table/read contract，且不猜首/最近章节；不得写WU、测试清单或未来计划。根`README.md`=`NO_UPDATE`（无安装、CLI、工作区、输出或排障变化），`dayu/README.md`=`NO_UPDATE`（无跨包分层变化），`tests/README.md`=`NO_UPDATE`（仍在既有测试层级/运行方式内）。恢复implementation后fresh复核这些约束；若实现事实要求其它README，立即STOP请Controller扩充精确allowlist，不得先改后解释。
- `dayu/fins/README.md`是Slice 2与Slice 3分别允许的同一路径；每个slice review必须区分本slice语义。除该路径外，任何README被判定必须修改时先STOP，请Controller扩充精确allowlist；不得机械同步。

### 3.5 Protected zero-diff paths

以下路径/集合在全部 slices、fix rounds、reviews 与 aggregate regression 中必须零 diff：

1. AR-F06 owner 与 scheduler evidence：

```text
dayu/host/dispatch.py
dayu/host/engine_ingest.py
dayu/host/_execution_health.py
tests/host/test_dispatch_scheduler.py
```

以及任何 scheduler/lifecycle/health-gate product 或 owner test。不得加入 retry、sleep、xfail、skip、timeout 放宽或 test-order 特例。

2. AR-F03 standalone product logging：

```text
utils/smoke_web_ci.py
dayu/runtime/log.py
tests/conftest.py
```

3. AR-F01 production config owner：

```text
dayu/runtime/config_loader.py
dayu/config/host_runtime.json
```

4. AR-F04 production compact/manifest owners：

```text
dayu/host/compact_payload.py
dayu/host/compact_artifact.py
dayu/host/compaction_operation.py
dayu/host/_runner_call_manifest.py
dayu/host/llm_compaction.py
dayu/host/context_events.py
```

5. AR-F02 boundary/compatibility traps：

```text
tests/service/test_import_boundary.py
dayu/fins/__init__.py
dayu/fins/ingestion/__init__.py
```

除 §3.3 在 Slice 2 允许的单行 import 迁移外，所有其它 `utils/**` 路径在全部 slices、fix rounds、reviews 与 aggregate regression 中必须零 diff；`utils/smoke_host_public_awaiting_entrypoint.py` 的其它行也必须零 diff。

6. AR-F05 production owners：`dayu/documents/processors/docling_processor.py`与`dayu/fins/processors/sec_form_section_common.py`只在Slice 3按§4.3精确开放；其它slice、plan-only gate、review-only gate中仍零diff。第二次correction entry的Docling delta受保护，恢复implementation只新增`sec_form_section_common.py`实现。其余七个owners在全部gate继续零diff：

```text
dayu/fins/pipelines/sec_6k_rules.py
dayu/fins/processors/sec_report_form_common.py
dayu/fins/processors/sec_section_build.py
dayu/fins/processors/sec_table_extraction.py
dayu/fins/tools/preprocess_tools.py
dayu/host/_execution_config_projection.py
dayu/runtime/argparse_exit.py
```

7. AR-F07 workflow truth：

```text
.github/workflows/r11-upload-script-windows.yml
.github/workflows/r12-init-windows.yml
```

8. 所有design docs、control docs、既有plan-review/correction/validation/completion/continuation/Controller artifacts、除Slice 2/3共同精确README allowlist `dayu/fins/README.md`外的全部README，以及开始时已有Controller-owned worktree changes。本次S3第二次plan-review-fix gate只对本plan与固定新`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-codex.md`例外；该artifact例外不延续成implementation allowlist。

每个 slice 开始记录 `SLICE_BASE=$(git rev-parse HEAD)`、完整 `git status --short`、pre-existing tracked diff清单及每个pre-existing tracked/untracked path的SHA-256。implementation、fix、review结束均重新采集 `git diff --name-status "$SLICE_BASE"` 和untracked列表：先验证pre-existing集合的path/status/hash完全不变，再把该集合从当前工作树清单中扣除，剩余delta才允许与本节 production/test/validation-utility/README allowlists精确比对。本次S3第二次plan-review-fix gate必须以§0 entry status/hash保护集合做同样校验，只允许本plan被修改并新增固定plan-review-fix artifact；Docling delta、六个Slice 3 test路径、continuation及全部correction/validation/review/Controller-owned protected artifacts hash必须不变。发现额外路径立即停止，不先清理、不覆盖用户改动。

## 4. Dependency order 与三个 implementation slices

依赖顺序固定为 Slice 1 -> Slice 2 -> Slice 3：先恢复 current schema/test oracle 和 in-process isolation，再迁 public Fins owner并让 canonical suite全绿，最后在稳定整合树补齐九路径 coverage。不得并行实现或把 AR-F05 测试混入前两个 slices。

### 4.1 Slice 1 — current-schema / test-oracle closure + local-trust projection verification（AR-F01、AR-F03、AR-F04、S1-SEC-F01 no-code closure）

#### Implementation

1. `tests/service/test_host_admin.py`
   - 让 `_write_host_runtime` 写出 current required `wait_poller_policy` 全量 12 字段：`enabled=true`、`poll_interval_seconds=1.0`、`claim_ttl_seconds=60.0`、`claim_batch_size=100`、`backoff_initial_delay_seconds=30.0`、`backoff_multiplier=2.0`、`backoff_max_delay_seconds=300.0`、`not_ready_observe_interval_seconds=1.0`、`idle_poll_interval_seconds=5.0`、`adapter_call_timeout_seconds=30.0`、`close_drain_timeout_seconds=5.0`、`max_outstanding_adapter_calls=8`。
   - fixture继续表达“只加载 host runtime，不需要 models/secrets”；不得 import另一测试模块的 helper，不得给 production loader加兼容或默认值。
   - 增补/收紧断言，证明 fixture current schema加载成功且测试目标未漂移。
2. `tests/tools/web/test_smoke_web_ci.py`
   - 增加模块级私有、typed、带中文 docstring 的 logger snapshot/invocation helper，按 §2.5 统一包裹当前六个 `smoke.main(...)` in-process calls。
   - success/failure 两路都断言 root/named logger state与 handler identity恢复；测试不得依赖执行顺序才能通过。
3. `tests/host/test_public_compact_smoke.py`
   - 删除 candidate-id 常量、拼接和匹配；把 `_runner_call_manifest_for_run` 改为严格唯一定位，并从 `compactor_identity.compaction_request_digest` 取得关联 digest。
   - `_compact_artifact_for_run` 接收该 digest，以 current artifact kind/schema/digest严格唯一定位；保持 existing first/second run continuity assertions。
   - 新增 deterministic cases：正确 run/digest 成功；missing manifest、duplicate manifest、missing compact artifact、duplicate matching compact artifact、wrong/missing digest 均 fail closed。不得加 historical schema fixture。
4. `S1-SEC-F01` 只做 owner-boundary verification，不修改任何 production path：
   - 用一个不来自真实环境的 synthetic configured-secret sentinel 构造含 resolved `RunnerSpec.headers` 的 `USER_INPUT_ACCEPTED.effective_execution_config`，先断言 internal durable round-trip保留 exact value，证明测试没有把 accepted owner path误清零。
   - `tests/host/test_tool_trace_projection.py` 必须通过 projection runner / consumer filter证明该 event不产生 hot row、cold JSONL或query material；不得只对最终字符串做字段名黑名单断言。
   - `tests/host/test_audit_sink.py` 必须把同一 source event交给 `build_audit_json_line` / sink owner，断言 exact audit key contract保持且完整序列化零 sentinel。
   - `tests/host/test_host_activity_event_projection.py` 必须通过 public HostEvent owner投影同一 event，断言 typed DTO / serialization零 sentinel，且未知/不可展示payload不被拼进activity。
   - `tests/host/test_run_input_builder.py` 必须分别断言 LLM-facing `messages`、memory / compact material与runner-call observation零 sentinel；`AgentRunRequest.runner_spec.headers` 是 Engine执行所需的受信任 typed input，必须保留 sentinel，不得把它误判成LLM projection。
   - `tests/host/test_logging.py` 必须让resolved runner header sentinel经过Host接受/dispatch或等价owner callsite，断言caplog零 sentinel。Engine已有exception diagnostic redaction / diagnostic payload tests只重跑，不修改Topic 8行为。
   - 这些测试只允许source-owner白名单投影与完整serialization断言；禁止按 `Authorization`、`api_key` 等字段名列黑名单，禁止下游repair、mock-only bypass或改变accepted内部持久化。

#### Focused tests / real smoke

```bash
source .venv/bin/activate
pytest tests/service/test_host_admin.py -q
pytest tests/tools/web/test_smoke_web_ci.py -q
pytest tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
pytest tests/host/test_public_compact_smoke.py -q
pytest \
  tests/host/test_audit_sink.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_host_activity_event_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_logging.py -q
pytest \
  tests/engine/test_agent_phase2.py \
  tests/engine/runners/openai/test_diagnostic_payload.py -q
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest \
  tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity \
  --basetemp=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor -q -rs
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-web \
  --include-playwright --external-limit 0 \
  --run-label wu-semantic-ownership-01-ar-fix-s1
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-awaiting \
  --keep-workspace
```

Standalone Web smoke必须仍输出 `status=passed`、11 local required、4 diagnostic-only、0 failure、0 skip；real compactor不得 skip且两轮 terminal/continuity/artifact oracle全绿。

#### Slice exit

- AR-F01、AR-F03、AR-F04 全部 closed。
- `S1-SEC-F01=CLOSED_AS_NO_CODE_BLOCKER`：internal Config / Host effective-execution命中按 §6.7 accepted classification记录；Tool Trace、audit、public HostEvent、LLM-facing material、日志、review与diff surface的owner tests / scans全部零 sentinel或零configured-value match。不得用“全局所有outputs零命中”重新打开已裁决的internal durable blocker。
- Canonical non-coverage full suite必须运行；在 AR-F02 尚未实施的顺序点，只允许 `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` 保持已知失败，原三个 F01/F03 failures及其他 node必须全绿。这个临时预期不是 waiver，Slice 2 exit后不得再存在。
- Fresh aggregate coverage按 §6.2 exact scheduler exclusion运行；同样只允许 AR-F02 import-boundary失败，九个 AR-F05 paths继续登记 `OPEN_BY_SEQUENCE`，不得把中间数值签为最终 coverage PASS。

### 4.2 Slice 2 — public Fins contract / Service boundary closure（AR-F02）

#### Implementation

1. 按 §2.3 把 `ValidatedFinsEventStream` 的实现与私有 state/constants物理迁入 `dayu/fins/direct_events.py`，删除 `dayu/fins/direct_stream.py`，直接迁移四类 consumers：Fins runtime、CLI、Service、tests。其中 `tests/cli/test_fins_commands.py` 只把 `ValidatedFinsEventStream` import 迁到 `dayu.fins.direct_events`，不改 CLI 行为或 test oracle。
2. 新建 `dayu/fins/ingestion/awaiting_resolution.py` 作为 awaiting mode唯一 public owner；从 tools私有 helper删除三项语义，迁移三个 provider、两个 Service modules、host assembly与测试 imports。按 §3.3 只把 `utils/smoke_host_public_awaiting_entrypoint.py` 的 `AwaitingResolutionMode` import 迁到新 owner，utility 的九个业务/类型使用位置与其它行零 diff。
3. `tests/service/test_import_boundary.py` 零 diff并必须自然通过。新增 public module不能促使 allowlist扩张。
4. 保持所有 public业务行为：stream对象 identity、恰好一个且最后一个 RESULT、缺失/重复/RESULT 后事件 typed error、clean exhaustion 后 terminal identity、close-at-most-once、原异常/取消 identity、provider mode闭集与错误文本语义均不变。
5. 更新 `dayu/fins/README.md` 的现行文件树和 owner说明；不保留旧路径或兼容承诺。

#### Focused tests / import-owner scans / real smoke

```bash
source .venv/bin/activate
pytest tests/cli/test_fins_commands.py \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/service/test_fins_direct.py \
  tests/service/test_fins_wait_adapter.py \
  tests/service/test_host_assembly.py \
  tests/service/test_import_boundary.py -q
pytest tests/fins -q
rg -n 'dayu\.fins\.direct_stream' dayu tests utils
rg -n 'from dayu\.fins\.direct_events import ValidatedFinsEventStream' dayu tests utils
rg -n '^(AWAITING_RESOLUTION_MODE_CONFIG_FIELD(?::[^=]+)?[[:space:]]*=|class AwaitingResolutionMode|def parse_awaiting_resolution_mode)' dayu tests utils
rg -n -U 'from dayu\.fins\.ingestion\.awaiting_resolution import (?:\([^)]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b[^)]*\)|[^\n]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b)' dayu tests utils
rg -n '^(AWAITING_RESOLUTION_MODE_CONFIG_FIELD(?::[^=]+)?[[:space:]]*=|class AwaitingResolutionMode|def parse_awaiting_resolution_mode)' dayu/fins/tools/_ingestion_tool_helpers.py
rg -n -U 'from dayu\.fins\.tools\._ingestion_tool_helpers import (?:\([^)]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b[^)]*\)|[^\n]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b)' dayu tests utils
```

第一个 direct-stream stale scan 必须在 `dayu tests utils` 零命中；第二个 consumer scan 必须精确命中三个 production 与三个 test consumers，并显式包含 `tests/cli/test_fins_commands.py`。Awaiting definition scan 必须在 `dayu tests utils` 精确命中新 owner `dayu/fins/ingestion/awaiting_resolution.py` 中的三个唯一定义；新 owner import scan 的每个命中都必须是 §3.1—§3.3 中的合法 consumer。最后两个旧 private owner definition/import scans必须都在 `dayu tests utils` 零命中；执行证据必须记录 `rg` 的 zero-match exit 1，不得把 scan error 冒充零命中。还必须静态检查 diff 中无 `__getattr__`、importlib、lazy import、try/except import、duplicate enum/protocol、package-root re-export或 Service字符串重算。

真实 Fins / Host smoke：

```bash
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-r03 \
  upload_filing --ticker AAPL --action create \
  --files tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm \
  --fiscal-year 2024 --fiscal-period FY --filing-date 2024-11-01 \
  --report-date 2024-09-28 --company-name 'Apple Inc.'
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-download \
  download --ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-download \
  process --ticker AAPL
python utils/smoke_host_public_r03_semantic_ownership.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-r03 \
  --doc-file tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/meta.json \
  --web-query 'Apple annual report 2024 revenue' --fins-ticker AAPL \
  --fins-document-id fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283 \
  --keep-workspace
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-awaiting \
  --keep-workspace
```

每个 direct operation必须有唯一 success terminal；不得从 summary、文件名或日志重建 progress/terminal；external provider不可用时保留完整 failure evidence并由 Controller裁决，不能改成 mock PASS。

#### Slice exit

- AR-F02 closed；Service boundary oracle在零改动下通过。
- Owner migration 后的 public-awaiting smoke 必须在 Slice 2 fresh 通过；不得沿用 Slice 1 在迁移前的结果。Direct-stream/awaiting definition、consumer 与 stale-private scans 必须覆盖 `dayu tests utils`，旧 `dayu.fins.direct_stream` 与 awaiting 三项语义的旧 private import/definition均为零命中。
- Canonical non-coverage full suite必须 0 failed；AR-F06 scheduler node在非 coverage模式不得排除且必须通过。
- Exact-exclusion aggregate coverage test run必须 0 failed；除明确留给 Slice 3 的九路径外，全部 aggregate-range production paths（含 Slice 2新 owner）line coverage `>=80%`，不得出现新的低覆盖路径。

### 4.3 Slice 3 — S3-STOP-F01 protected delta + S3-STOP-F02 atomic projection correction + nine-path owner-test coverage closure（AR-F05）

#### Correction implementation order / exact owner change

恢复implementation后必须先关闭`S3-STOP-F02`的owner/public matrix，其最小public复现与六类反例全部变绿前不得继续其它coverage cases。Slice 3整体production allowlist精确且只有：

```text
M dayu/documents/processors/docling_processor.py
M dayu/fins/processors/sec_form_section_common.py
```

其中Docling path是已完成、review-pending且受§0 entry hash保护的`S3-STOP-F01` delta；本次恢复implementation只允许在`sec_form_section_common.py`新增代码diff。实现顺序固定为：

1. 在owner内定义private typed enum/state，成员精确为`BUILDING`、`VIRTUAL_PUBLISHED`、`BASE_FALLBACK_PUBLISHED`。`_initialize_virtual_sections()`只初始化`BUILDING`并建立candidate；只有`_refresh_virtual_section_state()`可提交terminal transition：首次从`BUILDING`选择virtual或base fallback，已发布virtual只允许在现有identity约束下刷新并保持`VIRTUAL_PUBLISHED`，已发布base fallback只允许幂等保持`BASE_FALLBACK_PUBLISHED`。不得用空dict/list、时间、日志、异常或偶然顺序反推mode。
2. 显式把`_initialize_virtual_sections()`内首次`_refresh_virtual_section_state()`锁定为首次publication decision与当前公开构造失败入口。该调用必须在owner-local候选中完成section ref/parent-child、base table snapshot、raw marker与候选双向mapping验证，验证通过或作出fallback决定前不提前清空/写入published dict/list。它与10-K/10-Q subclass第二次postprocess/refresh共用同一typed终态，不得把修复误写成只处理第二次refresh。
3. base tables为空时，以空table mapping发布合法`VIRTUAL_PUBLISHED`。base tables非空时只从`get_full_text_with_table_markers()`同源raw marker material建立proof；每张public base table必须有非空且唯一`table_ref`，candidate必须保留所有raw marker refs、出现次数与range/title归属证据，不调用、扩展或替代marker producer contract。
4. validation order固定且不可交换：先对base table ref缺失/重复fail-closed；再对raw marker ref不在base refs中的dangling fail-closed；再对同一marker ref重复出现、落入多个section、section tree悬挂及table→section/section→tables矛盾fail-closed。上述矛盾检查全部通过后，才计算`base_refs - mapped_refs`：非空表示incomplete proof并whole-base fallback；为空且两集合完全、双向一致才允许virtual publication。incomplete + dangling优先fail-closed；无dangling但range/title不能唯一归属属于incomplete fallback，不得退回位置猜测或旧集合不等异常。
5. base fallback必须清空/禁用`_virtual_sections`、`_virtual_section_by_ref`、`_table_ref_to_virtual_ref`全部candidate并最后发布`BASE_FALLBACK_PUBLISHED`；不得保留partial virtual sections/mapping。完整proof才在全部验证后更新每个section的`table_refs`，一次提交三个projection字段与`VIRTUAL_PUBLISHED`。
6. `_assign_tables_to_virtual_sections()`改成只产生可验证的owner-local raw proof/candidate mapping或等价typed结果，不能在证明完整前就地污染published state。物理删除`_filter_table_refs_by_availability()`及其调用，禁止静默丢弃dangling marker证据；物理删除`_assign_unmapped_tables_by_position()`及其调用，禁止最近前驱/第一个section猜测。
7. 当前public consumers精确为五个，并逐一使用`mode != VIRTUAL_PUBLISHED -> base processor`guard：`list_sections()`委托base sections；`list_tables()`委托base tables；`get_section_title(ref)`委托base title；`read_section(ref)`委托base read；`search(query, within_ref)`委托base search。只有`VIRTUAL_PUBLISHED`可消费virtual projection。virtual `list_tables()`对每张base table只使用已发布exact mapping，删除`fallback_ref`、`last_known_ref`及“底层已有virtual ref即保留”等补偿。
8. 首次fallback清空candidate并发布terminal mode后，后续refresh必须在读取marker/base、identity计算或mapping构建前幂等no-op。当前`expand_ten_k_virtual_sections_content()`与`expand_ten_q_virtual_sections_content()`均以现有`if not full_text or not virtual_sections: return`开头，直接证明空candidate安全；锁定该zero-diff guard并用public 10-K/10-Q re-entry cases验证。若guard或行为漂移才STOP，不修改`ten_k_processor.py`、`ten_q_processor.py`、BS同族subclass、`ten_k_form_common.py`或`ten_q_form_common.py`，也不扩production/test allowlist。首次virtual发布成功时保留现有10-K refresh与10-Q object/ref identity约束。

禁止修改`dayu/documents/processors/base.py`、`dayu/fins/processors/sec_processor.py`或新增capability/schema/raw DOM marker。`SecProcessor.get_full_text_with_table_markers() -> ""`继续是合法unsupported声明；base fallback复用它已经拥有的同源sections/tables/read_section，不新增compatibility wrapper或第二resolver。

已完成的Docling production call path保持如下，只作为protected review scope，不在本次implementation继续编辑：

```text
DoclingProcessor.__init__
  -> _build_tables(document, linear_items)
  -> _extract_table_caption(table_item, document)
  -> for caption_ref in table_item.captions
  -> caption_ref.cref == _DOCLING_DOCUMENT_ROOT_REF: skip
  -> otherwise caption_ref.resolve(document) exactly once
  -> TextItem.text
  -> normalized unique ordered caption
  -> _TableBlock.caption
  -> list_tables / read_table / get_page_content.tables
```

实现决定固定如下，不得在implementation时重新设计：

1. `_build_tables()`必须把它已经持有、且用于同一table dimensions / headers / records的同一个`DoclingDocument`直接传给caption resolver；不得重新加载source、从raw JSON查路径、复制document collections或构造第二个document view。
2. `_extract_table_caption()`签名改为接收typed `TableItem`与同源`DoclingDocument`。模块级定义命名常量`_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`；resolver只遍历当前public `table_item.captions`，先从typed `RefItem.cref`读取Python字段并做精确相等判断，命中root sentinel时直接跳过且**不得调用**`resolve()`，其它ref才各调用一次public `resolve(document)`。`cref`是Python typed field，serialized JSON中的alias才是`$ref`；production只能使用typed `cref`，不得读取serialized dict / `$ref`。不得调用旧单数`caption`、`getattr(table_item, "caption", ...)`、`FloatingItem.caption_text()`、下游猜测、兼容fallback、独立JSON-pointer parser或第二套resolver。
3. 为runtime type narrowing在模块级从Docling public types导入`TextItem`；`docling-core>=2.74.0,<3.0.0`是项目必需依赖，因此不增加lazy import、`hasattr/getattr`、`Any/object`、cast逃逸或弱类型Protocol。resolved item只有`isinstance(item, TextItem)`时才读取其typed `text`；`SectionHeaderItem`、`TitleItem`等TextItem子类自然符合，TableItem/PictureItem等非文本item不符合。
4. 多caption public语义：严格保留`table_item.captions`作者顺序；每个resolved text用现有`_normalize_whitespace()`做strip并把连续空白规范为单空格；规范化为空的文本忽略；按**规范化后的完整字符串精确相等、大小写敏感**去重，保留第一次出现。大小写敏感是必要保真边界：大小写不同的原文可能承载不同业务含义，owner不得用casefold或其它近似规则擅自折叠。最后用单个ASCII空格连接所有剩余文本，形成唯一`str` caption；选择单空格是因为`captions`只有有序ref列表、不携带ref间原始分隔符或标点元数据，owner只做最小确定性连接，不猜标点。无剩余文本时返回`None`。不得新增标点推断、casefold、Unicode normalization framework或第二套text semantics；这份投影规则由resolver唯一拥有，tests不得复制实现算法。
5. Fail-safe边界只覆盖可选caption引用的已知数据完整性问题：`captions=[]`直接返回`None`；schema-valid的document-root ref `#`按第2项在resolve前静默跳过；未知document collection由单次public `resolve()`抛出的`AttributeError`，以及已知collection越界index由该单次调用抛出的`IndexError`，只在**该次**`caption_ref.resolve(document)`周围精确捕获并跳过该ref；不得产生warning/log副作用。其它合法ref继续处理。resolve到非`TextItem`或resolved `TextItem.text`规范化为空时跳过；如果全部ref都被跳过，返回`None`。
6. 语法非法、不能被Docling `RefItem`模型接受的ref不是caption resolver的fail-safe输入：固定以项目`.venv`真实失败值`not-a-valid-cref`在`DoclingDocument.load_from_json()`边界验证，并按现有Docling/Pydantic JSON parsing error对外暴露。resolver禁止捕获`RuntimeError`或`except Exception`，禁止匹配异常文本，也禁止包住type narrowing/text读取/规范化/去重/连接的宽catch；`TypeError`、`ValueError`、`RuntimeError`及任何不属于第5项dangling-reference数据边界的异常必须继续暴露，显示真实contract或编程错误。不得为了“更稳”增加warning/log后忽略、默认空字符串或降级到context/header。
7. `_TableBlock.caption`仍是唯一缓存投影，现有`list_tables()`、`read_table()`与`get_page_content().tables`继续直接消费同一值；不得在三个consumer各自解析、重算或修补。`TableSummary.caption`与`TableContent.caption`的`str | None` public schema不变，不做schema migration或兼容alias。

`S3-STOP-F01`上述owner correction与8-node caption matrix已经implementation完成，本计划不把它标为reviewed/accepted，但必须按§0 hash原样保留。除Docling与本次`sec_form_section_common.py`两个owner外，其余七个AR-F05 production owners及所有其它production路径严格零diff。只在§3.2既有六个测试文件中从owner/public contract继续补齐分支；不得直接复制production算法到期望值，不得只调用private helper而没有业务可观察断言。

下表coverage数字来自continuation停止前六文件focused feedback run，不是final aggregate签署，也不替代fresh运行。`sec_form_section_common.py`因focused suite选择变化显示36.61%，更证明不能沿用旧aggregate百分比宣称接近80%；恢复后仍以§6.2 fresh changed-production ledger为唯一exit证据：

| Production owner | Continuation focused line coverage | Test owner / required behavior families |
| --- | ---: | --- |
| `dayu/documents/processors/docling_processor.py` | 71.19% | `tests/documents/test_processors.py`：保留已通过的S3-STOP-F01真实Docling serialize/load caption matrix；继续补payload sniff/support、section/table/page/search/full-text、records/markdown fallback、header/context、noise/default/dedup header、malformed/missing metadata fail-safe，全部只断言public processor结果 |
| `dayu/fins/pipelines/sec_6k_rules.py` | 67.56% | `tests/fins/test_sec_pipeline_download.py`：candidate filename/type/rank、quarter/half-year/XBRL signals、current result与未来/会议/管理变化/资本动作/演示/运营更新等正负分类，最终断言选取/拒绝业务结果 |
| `dayu/fins/processors/sec_form_section_common.py` | 36.61% | `tests/fins/test_processor_read_consistency.py`：先关闭S3-STOP-F02六类owner/public反例与fallback重入；再覆盖virtual section构建/展开、structured/fallback headings、TOC/reference-guide抑制、完整table映射、boundary search、short/empty section与public read/search一致性 |
| `dayu/fins/processors/sec_report_form_common.py` | 22.12% | 同上：line-preserving HTML、edgartools rebuild、statement dataframe、TOC cutoff、item marker order/refinement、inline reference与候选优先级，断言public report section/statement结果 |
| `dayu/fins/processors/sec_section_build.py` | 18.48% | 同上：fast/full/single-section paths、body anchor、TOC cutoff、duplicate occurrence、table fingerprint与安全 text extraction，断言稳定 section顺序/范围/table ownership |
| `dayu/fins/processors/sec_table_extraction.py` | 12.51% | 同上：dataframe/dict/object/HTML/Markdown sources、section消歧、headers/row headers、financial classification、records recovery、MultiIndex/ghost columns、numeric/footnote normalization，断言public table content与section ref |
| `dayu/fins/tools/preprocess_tools.py` | 91.94% | `tests/fins/test_fins_ingestion_tools.py`：保留已通过delta；仅在fresh 219 ledger仍不足时补missing/invalid/valid `source_kind`、optional tuple/bool、start/cancel/failure/awaiting outcomes与schema contract |
| `dayu/host/_execution_config_projection.py` | 92.99% | `tests/host/test_effective_execution_config.py`：保留已通过optional/required JSON scalar、RunnerSpec/options/provider request/AgentPolicy round-trip与fail-closed delta；final fresh ledger复核 |
| `dayu/runtime/argparse_exit.py` | 100.00% | `tests/runtime/test_argparse_exit.py`：保留已通过int codes与usage error 2 owner contract；不改helper，final fresh ledger复核 |

以上是测试选择优先级，不授权为了命中行而构造不可能状态、mock-only hook、dead branch、production seam、`pragma: no cover`、coverage omit、动态 import或实现镜像。测试必须具备完整中文模块/类/函数 docstring与严格类型。当前Slice 3六路径test delta全部保留；重新授权后先在`tests/fins/test_processor_read_consistency.py`增量完成S3-STOP-F02 matrix，不重写已通过Docling/runtime/Host/preprocess cases，再按fresh coverage missing lines继续同一allowlist内高价值public cases。

#### S3-STOP-F02 owner/public counterexample matrix

以下六类反例必须全部进入`tests/fins/test_processor_read_consistency.py`，先于其余coverage cases执行。真实表单case从public constructor与public methods观察；owner harness只提供typed base processor/marker输入并最终断言public list/read结果，不暴露新production seam、不复制mapping算法：

1. **Public 10-K + unsupported marker + base table**：保留现有`test_ten_k_public_processor_assigns_tables_without_marker_capability`最小合法HTML，不删除或改弱`supports(...) is True`前提。用同一source的public `SecProcessor`取得base oracle；逐值比较base/form的完整section ref序列、完整table ref序列、每张table的`section_ref`与每个base section的`read_section(ref)["tables"]`。再用每个base ref调用form的`get_section_title(ref)`、`read_section(ref)`与`search(..., within_ref=ref)`并与base结果逐值比较，证明ref命名空间、内容、搜索范围与table ownership全部同源。不得只比较长度、非空、内容摘要或“不抛异常”，也不得把表格塞进任意virtual ref。
2. **Marker supported + complete mapping**：typed owner harness提供两virtual sections、唯一base table与包含该ref的完整marker material；refresh后public `list_sections()`发布virtual refs，`list_tables()`只按exact mapping重写到唯一virtual ref，`read_section(ref)["tables"]`包含同一ref，反向map/section map完整唯一。再次refresh应保持同一业务结果与10-Q identity contract。
3. **Marker supported + incomplete proof**：至少覆盖两种无矛盾incomplete：(a) base有至少两表而marker只证明其中一表；(b) raw marker refs都属于base且无重复/dangling，但marker range/title不能把某个ref唯一归属到section。两者都不得发布半套virtual state或退回位置猜测/旧集合不等异常，必须whole-base fallback。fallback后按case 1同一oracle逐值比较section refs、table refs、table `section_ref`、`read_section(ref)["tables"]`，并通过base refs逐值验证title/read/search。
4. **Duplicate / dangling / contradictory fail-closed**：分别覆盖缺失/重复base `table_ref`、marker出现非base dangling ref、同一marker ref重复/归属多个section、section parent/child或双向map矛盾；每类都必须在atomic commit前抛`ValueError`，不能留下半更新public state。另固定混合case：base refs含未映射项且raw marker同时含dangling ref时，dangling/contradiction检查必须优先fail-closed，不能被incomplete fallback吞掉。expected只断言稳定错误类别/业务片段，不复制内部遍历顺序。
5. **Zero-table document**：public或typed owner case形成合法virtual sections、base `list_tables()==[]`且marker unsupported；必须继续发布virtual sections与空双向mapping，public list/read/search一致，证明“空marker”不是无条件fallback信号。
6. **10-K/10-Q second postprocess idempotence / no re-entry**：至少覆盖public SecProcessor-backed `TenKFormProcessor`与`TenQFormProcessor`，并用既有四路径postprocess probe复核shared owner对BS同族没有行为漂移。先锁定两个form-common expand函数现有`if not full_text or not virtual_sections: return` zero-diff guard；首次refresh因unsupported/incomplete marker清candidate并发布base fallback后，subclass构造器第二次postprocess/refresh必须保持base section refs、table refs、table `section_ref`、title/read/search与`read_section(...)["tables"]`逐值不变，marker/base mapping call count不增加，无异常、无virtual/partial state重生；10-Q空identity multiset不得触发重建。完整mapping的既有10-K/10-Q virtual refresh与10-Q object/ref identity约束继续通过。

矩阵必须同时证明“fallback是同源base publication”与“contradiction仍fail closed”。禁止以`try/except`只看构造成功、private字段单断言、首/最近章节expected、标题/顺序推断或mock-only hook替代public contract。

#### S3-STOP-F01 protected public test oracle

以下caption cases已经完成并通过；它们必须构造真实`DoclingDocument` / `TableItem.captions` / `TextItem`，调用`save_as_json()`，再经`DoclingProcessor`真实load。后续review把它们纳入完整Slice 3 diff，但本次恢复implementation不得直接调用`_extract_table_caption()`、修改`_tables`、monkeypatch `RefItem.resolve`、伪造private block或重写既有cases：

1. **单caption与传播**：一个`TextItem(label=CAPTION)`经一个ref引用，断言`list_tables()[0]["caption"]`与`read_table("t_0001")["caption"]`相同；page fixture必须用current public `ProvenanceItem(page_no=1, bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0), charspan=(0, 1))`构造table provenance，经真实serialize/load后断言`get_page_content(1)["tables"][0]["caption"]`相同；禁止写private state或伪造page cache。
2. **多caption顺序/规范化/去重/连接**：至少三个refs，输入包含首尾空白、换行/制表/连续空格、一个规范化后完全重复值与一个不同值；只断言业务结果如`"Consolidated Results Unaudited"`，并通过反向排列的独立case证明顺序来自refs而非document text数组/集合排序。大小写不同的合法caption必须分别保留；测试不加入NBSP特例、casefold或Unicode normalization framework。
3. **空语义**：`captions=[]`与只指向空白`TextItem`分别返回`None`，不得返回`""`、空格或context/header替代值。
4. **ref边界**：用typed `RefItem(cref="#")`构造schema-valid root-ref public case，经真实serialize/load后断言该ref不产出caption；与有效caption并存时有效值仍传播，只有root refs时为`None`。用typed `RefItem(cref="#/missing/0")`与`RefItem(cref="#/texts/999")`分别覆盖未知collection与越界；它们与有效caption并存时只跳过坏ref且保留有效caption，全部为坏ref时public caption为`None`。model-invalid case必须先由真实`DoclingDocument.save_as_json()`生成其余完整payload，**仅在loader-boundary test**把serialized `captions[*].$ref`替换为项目`.venv`已证实失败的`not-a-valid-cref`，再从public processor构造入口断言现有Docling/Pydantic load failure；该case只验证第三方load boundary，不得成为production raw-JSON resolver。Python构造和production判断统一使用字段`cref`，`$ref`只出现在上述serialized loader-boundary edit。
5. **非文本ref fail-safe**：caption ref解析到真实`TableItem`或`PictureItem`时忽略该ref；与有效TextItem并存时仍投影有效caption，全部非文本时为`None`。不得访问非文本item的偶然`text`属性或字符串表示。
6. **公开一致性**：上述核心matrix至少对`list_tables`与`read_table`同时断言；page fixture再断言page table summary，证明三个consumer共享`_TableBlock.caption`，不是只让一个展示路径“看起来正确”。

测试不复制normalizer/deduper函数；expected strings必须是固定、业务可读的public contract值。

建议直接落成下列owner-contract nodes；可抽取模块级typed Docling fixture builder减少机械单元格样板，但builder只构造public models，不计算expected caption：

```text
test_docling_json_processor_projects_referenced_table_caption
test_docling_json_processor_preserves_normalized_unique_caption_order
test_docling_json_processor_returns_none_for_empty_or_blank_captions
test_docling_json_processor_skips_dangling_caption_references
test_docling_json_processor_skips_document_root_caption_reference
test_docling_json_processor_rejects_model_invalid_caption_reference
test_docling_json_processor_skips_non_text_caption_references
test_docling_json_processor_propagates_caption_to_public_table_views
```

#### Unchanged trust / quota / deferred boundaries

- Config与Host internal SQLite/EventLog仍是`ACCEPTED_TRUSTED_INTERNAL`；只允许§2.2.1的exact Config / Host effective-execution owner命中。Tool Trace、audit、public、LLM-facing、logs、其它outputs、diff/reviews仍逐surface `ZERO_REQUIRED`，两项Slice 3 owner correction都不得改变或绕过该裁决。
- Gemini低预算测试账号仍固定为`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`；不得因恢复Slice 3追加真实provider调用，或修改config/model/key/retry/quota/budget。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；canonical non-coverage必须真实运行scheduler node，coverage仍只允许§6.2精确一个deselect。`AR-F07 = PENDING_RELEASE_BLOCKER`，Darwin skip不能代替真实Windows evidence。
- Issues 142/151/175/177/178、Topic 8/9与既有deferred/no-code destination不变；不得引入secret infrastructure、统一tool authorization framework、TruncationManager wiring、storage-state lifecycle或Fins hard-kill/process isolation。

#### Stop condition

已接受的`S3-STOP-F01`与`S3-STOP-F02`是本corrected slice仅有的两个production例外。出现任一情况立即停止并交Controller：需要第三个production path；需要修改DocumentProcessor/SecProcessor marker contract、增加DOM/raw HTML marker或capability schema；需要首/最近章节、标题/顺序/相似度猜测、兼容分支、下游fallback、第二owner resolver或broad exception swallow；无法在单一atomic refresh owner区分incomplete fallback与duplicate/dangling/contradictory fail-closed；10-K/10-Q二次postprocess必须改subclass才能避免重入；需要README扩到`dayu/fins/README.md`之外。若六类matrix或其余owner cases再暴露新的production correctness/type/security defect，或只有修改其它production/直接耦合不稳定private实现才能达到80%，保存最小复现、预期/实际、stack与coverage missing-line证据后停止；不得顺手扩域或降低threshold。

#### Focused tests / coverage / real smoke

```bash
source .venv/bin/activate
pytest tests/fins/test_processor_read_consistency.py::test_ten_k_public_processor_assigns_tables_without_marker_capability -q
pytest tests/fins/test_processor_read_consistency.py -k 'virtual_section and (fallback or mapping or refresh or postprocess)' -q
pytest tests/documents/test_processors.py::test_docling_json_processor_projects_referenced_table_caption -q
pytest tests/documents/test_processors.py -k 'docling and caption' -q
pytest tests/documents/test_processors.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/host/test_effective_execution_config.py \
  tests/runtime/test_argparse_exit.py -q
```

前两条先关闭S3-STOP-F02并验证六类matrix；Docling两条是受保护delta的fresh回归，不授权继续修改。Focused coverage只作快速反馈，最终签署只采用§6.2 fresh aggregate coverage。Slice 3还必须重跑真实affected-owner paths：

```bash
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-download \
  download --ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-download \
  process --ticker AAPL
python utils/smoke_host_public_r03_semantic_ownership.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-r03 \
  --doc-file tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/meta.json \
  --web-query 'Apple annual report 2024 revenue' --fins-ticker AAPL \
  --fins-document-id fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283 \
  --keep-workspace
```

#### Slice exit

- `S3-STOP-F01`全部public caption oraclefresh通过，protected Docling/test delta相对第二次correction entry语义未漂移；旧单数caption读取、fallback与第二resolver为零。
- `S3-STOP-F02`六类owner/public反例全部通过：unsupported/incomplete marker原子base fallback、complete marker原子virtual publication、zero-table virtual publication、incomplete+dangling及其它duplicate/dangling/contradictory fail-closed、无dangling但range/title不能唯一归属的whole-base fallback，以及10-K/10-Q二次postprocess fallback幂等不重入。五个public consumers只消费同一typed mode；`_filter_table_refs_by_availability()`静默过滤、`list_tables()`首/最近章节补偿与`_assign_unmapped_tables_by_position()`均为零，DocumentProcessor/SecProcessor marker contract与两个form-common guard零diff。
- Slice 3 production diff只含§3.1两个路径；相对本次entry的新production hunk只在`sec_form_section_common.py`。`dayu/fins/README.md`只同步已实现的稳定owner/fallback语义。
- 九路径每个 fresh line coverage `>=80.00%`，AR-F05 closed。
- Final aggregate-range ledger必须精确为 `219/219 >=80%`。预期集合变化是原 219 中删除 `dayu/fins/direct_stream.py`、新增 `dayu/fins/ingestion/awaiting_resolution.py`，总数仍为 219；任何其他增删都是 scope failure。
- Canonical non-coverage suite、exact-exclusion coverage suite、full pyright、Ruff delta、build、scans、smokes全部满足 §6，不得仅凭 focused tests接受。

## 5. Per-slice mandatory review / fix / re-review state machine

本次S3第二次corrected plan必须重新完成独立plan gate，且不得把第一次correction的review/re-review结论复用为本次通过，也不得与implementation/code review合并：

1. AgentMiMo与AgentDS对immutable第二次corrected plan的双路完整plan review已经完成，artifact SHA-256分别为`6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc`与`6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822`；不得把它们误记为对本次fix后plan的re-review。
2. Controller已在SHA-256=`725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb`的adjudication中合并接受`S3-P2-PF01`—`S3-P2-PF04`，reject MiMo 05独立finding并否定DS-F03“空列表未知”的事实判断；有效guard与测试证据已分别归入PF01/PF03。
3. 本次AgentCodex只在本plan与固定`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-codex.md`内修复四组accepted findings；production/test/README/utility/control与其它artifact保持zero-write。
4. **唯一next gate**：Controller validation，以及AgentMiMo与AgentDS分别对fix后的**完整plan与本次fix artifact**做双路完整re-review；只看fix diff不算re-review。两路必须逐组确认`S3-P2-PF01`—`S3-P2-PF04`已修复、rejected/narrowed候选未复活且没有新blocking finding。
5. Controller在validation与双路完整re-review均通过后明确接受plan并发布新的Slice 3 implementation authorization，才能修改`sec_form_section_common.py`或继续测试。Docling与现存test delta继续受保护；plan fix/validation/re-review本身不授权stage/commit。

每个 slice 都必须独立完成以下顺序，前一 slice未接受不得开始下一 slice：

1. AgentCodex implementation仅修改该 slice production/test/validation-utility/README allowlists；Controller先验证 path/status/staged/semantic-owner/test evidence。
2. AgentMiMo与AgentDS分别对从 immutable slice base 到完整当前 tree的全部 product/test/validation-utility/README diff做完整 code review。不得只看摘要、selected hunks或另一路 finding；两路都必须覆盖 correctness、stability、maintainability、architecture boundary、semantic ownership、over-coupling、security、tests/coverage和protected paths。
3. Controller逐条裁决两路 findings。AgentCodex只修 accepted findings；若修复需要扩 allowlist或触发本计划 stop condition，先停，不自行实施。
4. 修复后重跑该 slice的 focused tests、真实 smoke以及 §6全门禁；不得用旧运行结果补签。
5. AgentMiMo与AgentDS再次对完整修订后 slice tree做双路完整 re-review，确认 accepted findings真正关闭且无新 finding。只 review fix hunk不算 re-review。
6. Controller做最终 slice validation并明确接受后，才可按当时授权处理 slice commit/control transition。计划本身不授权 stage/commit/push。

## 6. 每个 slice 的统一验证门禁

### 6.1 Canonical non-coverage full suite

每个 slice implementation及每轮 accepted-finding fix后都运行无 PTY canonical command：

```bash
source .venv/bin/activate
pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli
```

- Slice 1只允许 §4.1 已声明的单个 AR-F02 import-boundary中间失败；不能把该运行标为全绿。
- Slice 2、Slice 3及最终 aggregate必须 exit 0、0 failed。AR-F06 scheduler node不 deselect、不 skip、不 retry。
- pass count不得低于基线已通过 tests加本计划新增 cases；10 skips与5 deselected必须逐项保持现有平台/测试配置分类，不能新增未裁决 skip/deselect。
- Slice 3不得把continuation中`204 passed` focused run或S3-STOP-F02的预期失败当作final evidence；owner修复后六测试路径、canonical suite与AR-F06 non-coverage node均须fresh重跑。已完成Docling 8-node matrix也必须fresh回归，但其entry delta不得为通过回归而重写。

### 6.2 Coverage 与 exact scheduler node exclusion

Coverage measurement只能排除下面这一个已裁决 R05 node：

```text
tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
```

每次coverage运行前必须先执行精确collection preflight：

```bash
source .venv/bin/activate
pytest --collect-only -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
```

只有该命令exit 0、输出唯一该完整node id且summary为`1 test collected`时才能继续coverage；node不存在、重命名、collect error、0个或多于1个结果均立即STOP。不得因为exact deselect对不存在node也可能返回成功而跳过这项fail-closed检查。

命令：

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage erase
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage run --branch -m pytest \
  tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli \
  --deselect=tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage json \
  -o workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate-coverage.json
```

禁止任何额外 `--deselect`、`--ignore`、omit、xfail、skip、retry、parallel race掩盖或 coverage config修改。这个 exclusion只使219文件 coverage可测，不表示 AR-F06已修复/waived；canonical non-coverage仍必须运行该 node并通过。

最终 ledger生成规则：

- 从 `git diff --name-only --diff-filter=ACMR 3410d7422655c56bdf13c643f77c27f40b9d4550..FINAL_ACCEPTED_HEAD -- 'dayu/**/*.py'` 得到现存 changed production Python，排序、去重，必须恰好219个。
- 对 coverage JSON 的每个路径按 `covered_lines / num_statements * 100` 计算 fresh **line** coverage；不得使用含 branch的 combined `percent_covered` 冒充 line coverage，不在 JSON即按0处理。
- Slice 1/2必须输出 cumulative ledger；Slice 1只保留 AR-F02中间失败，Slice 1/2可把九个 AR-F05 paths标为 `OPEN_BY_SEQUENCE`，但不得出现其他 `<80%`。
- Slice 3与最终 aggregate必须 `219/219 >=80.00%`；九路径及 Slice 2新增 public owner都单列 statements/covered/missing/percent。Docling与`sec_form_section_common.py`本来就在219集合中，本次两个owner的内容修改不得改变成员总数；任何额外增删均STOP。
- `sec_form_section_common.py` ledger必须与S3-STOP-F02六类matrix的fresh通过结果同时报告；coverage到线不代表原子fallback contract已关闭。不得沿用continuation focused `36.61%`或stop-node `30.145719%`作为exit数据。

### 6.3 Full pyright / Ruff

```bash
source .venv/bin/activate
pyright
ruff check dayu tests utils --output-format json
```

- pyright必须 0 errors / 0 warnings / 0 informations；不得加 ignore、cast逃逸、`Any`、`object`、无类型签名或 `hasattr/getattr` fallback。
- 当前 full Ruff immutable baseline是144 findings。每个 slice开始与结束都把 JSON规范化为 `(filename,row,column,code,message)` 集合：完整集合相对 slice base不得新增；所有本 slice mutable paths必须0 finding。不得改 Ruff config、加 `# noqa`、删除无关代码或把 pipeline exit 0冒充 Ruff本身通过。
- 最终 aggregate同样要求 full Ruff baseline set无增量、全部本计划 mutable paths零 finding；若基线被外部提交合法改变，Controller必须先记录新 immutable set，不能只比较数字。

### 6.4 Diff / allowlist / staged state

每个 checkpoint运行：

```bash
git status --short
git diff --name-status "$SLICE_BASE"
git diff --check
git diff --cached --name-status
```

- `git diff --check`必须 exit 0。
- `git diff --cached --name-status`必须为空，除非后续 Controller在独立 gate明确授权 stage。
- 扣除开始时pre-existing protected集合后，剩余name/status必须与当前slice production/test/validation-utility/README allowlists精确相等或为其子集；delete/add status也必须匹配。Slice 2 的 validation-utility delta 必须只有 `M utils/smoke_host_public_awaiting_entrypoint.py`，且只有 §3.3 授权的 import 行迁移。既有Controller-owned modified/untracked paths不得被扣除后遗忘：必须以开始/结束SHA-256证明内容未变，mtime不作为语义证据。
- 不得删除、格式化、恢复或纳入既有工作区 changes。
- 本次第二次plan-review-fix entry及后续re-review前必须逐项复核§0全部protected hashes；恢复implementation entry还须把Docling与六测试路径视为pre-existing accepted delta，只允许`sec_form_section_common.py`新增production hunk与六测试路径内的增量cases。continuation/correction/validation/review/Controller artifacts始终zero-write。

### 6.5 Build

每个 slice及最终 aggregate均运行：

```bash
source .venv/bin/activate
python -m build --outdir workspace/tmp/wu-semantic-ownership-01-ar-fix-<gate>-build
```

必须同时生成 wheel与sdist、exit 0，记录文件名/bytes/SHA-256；输出只进入 gitignored `workspace/tmp`与build工具既有临时目录，visible worktree不新增路径。PyPA build已是本地验证前置，不得为了本计划修改 project runtime/dev dependencies。

### 6.6 Six canonical scans

每个 slice和最终 aggregate都重跑，不沿用旧结果：

```bash
rg -n 'DocResourceBudget|SourceBudgetExceeded|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' dayu tests README.md
rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|_INTERNAL_SOURCE_REF_KINDS' dayu tests
rg -n 'stage_source_document|ingest_complete.*false|owner_scope_id|owner_token|_BATCH_OWNER_CONTEXT|_execute_with_auto_batch' dayu/fins tests/fins
rg -n 'statement_locator|statement_method_missing|raw_total|deduped_count' dayu/fins/tools dayu/fins/domain tests/fins
rg -n '\btotal\b|raw_total' dayu/fins/domain/xbrl_result_contract.py dayu/fins/processors tests/fins
rg -n 'schema_version.*commands|JSON argv|dayu-web|dayu-wechat|dayu-render' pyproject.toml dayu tests README.md
```

前四组必须零命中；S5/S6按 aggregate accepted classification逐项比对，允许 immutable fixture/财务术语/operational label既有命中，但不允许新 stale public semantic、raw total projection、removed entrypoint或JSON argv contract。

Slice 2 与最终 aggregate 还必须 fresh 重跑 §4.2 的 direct-stream/awaiting owner scans：扫描根固定为 `dayu tests utils`，新 owner definitions 各唯一、consumer imports 只落在精确 allowlists，旧 `dayu.fins.direct_stream` 与 awaiting 三项语义的旧 private definition/import 均必须零命中。

Slice 3与最终aggregate还必须fresh执行virtual-section owner scans：

```bash
rg -n '_filter_table_refs_by_availability|_assign_unmapped_tables_by_position|fallback_ref|last_known_ref' \
  dayu/fins/processors/sec_form_section_common.py
git diff --exit-code 48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe -- \
  dayu/documents/processors/base.py \
  dayu/fins/processors/sec_processor.py \
  dayu/fins/processors/ten_k_processor.py \
  dayu/fins/processors/ten_q_processor.py \
  dayu/fins/processors/bs_ten_k_processor.py \
  dayu/fins/processors/bs_ten_q_processor.py
```

第一条必须零命中，证明silent raw-ref filter、最近/首章节补偿函数与consumer状态已删除；不得用改名保留同义过滤/猜测。第二条必须exit 0，证明marker producer contract和10-K/10-Q subclass没有被下游绕修。另对`sec_form_section_common.py`新增diff做语义scan，确认无标题相似度/顺序fallback、`hasattr/getattr`、`except Exception`或新warning/log分支；既有无关代码命中按entry diff分类，不得用全文件旧命中伪报新增。

### 6.7 README / security / deferred / no-code ledger

每个 slice必须形成明确 ledger：

- README：按 §3.4 读取目标 README约束、记录`UPDATE`或`NO_UPDATE`及直接理由。Slice 2/3分别只允许`dayu/fins/README.md`内属于该slice已实现稳定语义的更新；Slice 3必须说明atomic virtual publication / whole-base fallback / no guessing，并证明根README、`dayu/README.md`、`tests/README.md`为`NO_UPDATE`。其它README不允许先改后解释。
- Security：重跑 Doc path containment/output truncation、Web DNS/private/proxy/redirect/diagnostic、Host digest/EventLog/opaque ref、wait late-publication fence、Fins transaction/atomic swap/path/opaque id/direct validator、CLI POSIX quoting/init containment/process fencing相关既有矩阵。AR-F07 Windows项只能记 `PENDING_RELEASE_BLOCKER`。
- Configured-secret scan 必须按 semantic owner分类，不能继续用跨全部surface的单一零命中规则：
  - secret集合只从current typed model config的 `api_key_ref` 解析当前环境中非空values；只输出 configured value count、各surface match count / matched path count与Host logical row count，不输出value、ref名称、header名称或命中正文。
  - `ACCEPTED_TRUSTED_INTERNAL` 只允许两个精确owner：ConfigLoader管理的本地 Config source，以及Host internal SQLite / EventLog中 `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers` 的exact effective-execution canonical fact。SQLite物理file命中必须再以只读logical row / JSON path核对；所有logical命中必须是该event / path，logical other count必须为0。非零internal count不阻断release，也不要求清理、redact或production redesign。这个classification不授权改变`dayu-cli init` secret source storage。
  - `ZERO_REQUIRED` surfaces固定为Tool Trace hot/cold/query、audit JSONL/query、public HostEvent / read model / outbox、memory / compact / evidence / runner-call observation等LLM-facing material、operator logs、其它smoke输出、git diff与review artifacts。每一类必须分别输出0 match / 0 matched path；不得把它们与internal SQLite合并计数后waive。
  - 每个slice扫描本slice全部 `workspace/tmp/wu-semantic-ownership-01-ar-fix*` outputs、该slice artifact、当前git diff与相关review artifacts；final aggregate重新扫描三slice全部outputs与完整diff/reviews。binary SQLite只进入trusted-internal物理分类；audit / tool-trace文件、log、public / LLM artifacts与其余outputs进入各自zero-required分类。
  - owner-level synthetic sentinel tests与real configured-value surface scan必须同时通过：synthetic值证明投影owner明确排除，real scan证明实际assembly输出没有旁路。测试数据中的疑似token必须是显式synthetic值，不能把真实configured value写进test、artifact、diff或review。
  - 任一zero-required surface非零，或internal logical命中不在上述exact event / JSON path，立即按§9停止；不得按文件名、字段名黑名单、删除smoke output、改synthetic key或缩小scan root来“修复”结果。
- Deferred：Issue 177、178、175、142/151仍由各自 owner保留；本计划不得引入 TruncationManager wiring、storage-state lifecycle output/TTL/retention/refresh、Fins hard-kill/process isolation或assets migration。
- No-code：Topic 8与Codex F-13的 `dayu/engine/agent.py`、`dayu/engine/contracts/error_codes.py`零 diff；Topic 9不得引入统一 authorization框架、capability token、policy DSL或role model。
- AR-F06：持续写作 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，不得用coverage exclusion改状态。

### 6.8 Per-slice real-smoke completeness

除各 slice列出的 real smokes外，Slice 2、Slice 3和最终 aggregate至少重跑：

```bash
DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest \
  tests/tools/web/test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants -q -rs
pytest \
  tests/cli/test_upload_filings_from_command.py::test_upload_filings_from_default_output_generates_posix_script_and_summary \
  tests/cli/test_upload_filings_from_command.py::test_posix_script_round_trips_adversarial_argv_with_real_sh \
  tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage \
  tests/cli/test_init_smoke.py -q
```

Darwin上的Windows nodes继续记真实 skip，不能算成功。HKEX external official GET不在本 fix无条件重发；必须重新校验 accepted immutable R10 raw evidence三份文件存在且SHA-256不变，并运行full Fins deterministic HKEX tests。若 evidence缺失/hash漂移，STOP交 Controller，不伪造本轮外部 success。

## 7. All-slices aggregate regression / deepreview gate

三个 slices各自经过双路完整 review/fix/re-review并由 Controller接受后，AgentCodex必须从最终整合树重新执行一轮 aggregate regression；不得拼接各 slice旧结果。至少包括：

1. §6.1 canonical non-coverage full suite，0 failed；AR-F06 node真实执行并通过。
2. §6.2 exact single-node exclusion coverage，coverage pytest 0 failed，final ledger `219/219 >=80%`。
3. full pyright、full Ruff exact baseline delta、diff-check、allowlist/protected path hashes、staged state。
4. wheel/sdist build及artifact hashes。
5. 六组 scans、Slice 2 direct-stream/awaiting owner/stale scans、README/security/configured-secret semantic-classification/deferred/no-code ledger；所有 owner/stale scans 都覆盖 `dayu tests utils`并证明旧 private import零命中，configured-secret scan必须把exact trusted internal owner与每个zero-required projection surface分开报告。
6. Real Web、public awaiting、R03 semantic ownership、real compactor、Fins upload/download/process、live browser cleanup、POSIX generated script/CLI/init，及accepted immutable HKEX evidence复核。
7. AR-F01—AR-F05逐项以当前命令和当前 tree标 `CLOSED`；AR-F06保持 no-code residual；AR-F07保持 pending external gate。

Aggregate regression全部本地门禁通过后，才进入 AgentMiMo与AgentDS双路 **aggregate deepreview**：

- 两路独立审查从 aggregate parent到最终 accepted HEAD的完整umbrella tree与本 fix，不复用per-slice review结论替代aggregate review。
- Controller裁决两路 findings；AgentCodex修复全部 accepted findings，每轮修复后重跑受影响测试和整套aggregate regression。
- AgentMiMo与AgentDS对最终完整aggregate tree做双路完整 re-review；两路都无未解决accepted finding后，Controller才能宣告aggregate deepreview local pass。
- 若aggregate fix触及本计划allowlist外路径或改变219集合，STOP并先修订/重审计划；不得以deepreview名义扩域。

## 8. AR-F07 Windows evidence gate

Local aggregate pass和MiMo/DS aggregate deepreview pass都不能关闭AR-F07。只有后续 Controller明确授权把包含最终accepted fix commit的分支推到真实remote后，才可触发/读取：

- `.github/workflows/r12-init-windows.yml`（优先；always step同时覆盖R11两个真实cmd nodes）。
- 必要时独立 `.github/workflows/r11-upload-script-windows.yml`。

必须验证：

1. run checkout commit包含 `ed9bfa9...` 与本 fix最终accepted commits；runner=`windows-latest`、Python 3.11、locked constraints安装成功，job非 skipped/cancelled，所有pytest node exit 0。
2. R11 artifact `r11-windows-upload-script-{run_id}` 包含environment/cmd help、pytest stdout/stderr/junit、cmd-recorder/generated script、单行 recorder oracle、CLI storage/generated script、grammar oracle；`cmd_invocation`精确为`cmd.exe /d /c`，script hash和portfolio artifact count一致。
3. R12 artifact `r12-init-windows-{run_id}` 包含`versions.txt`、`environment-names.txt`、`source-hashes.json`、`init-pytest-junit.xml`、`r11-pytest-junit.xml`；五个Windows init nodes、platform capability、rollback/race与两个R11 cmd nodes全绿。
4. workflow files相对本计划基线零 diff；不得为获得PASS改workflow、改测试skip或用Darwin/模拟cmd代签。

在这些真实run/artifact evidence被Controller接受前，状态始终是：

```text
AR-F07 = PENDING_RELEASE_BLOCKER
push / PR / final closeout = NOT AUTHORIZED
```

## 9. Stop conditions / residual risk

任一条件出现立即停止当前 slice并交 Controller：

- 正确语义 owner与本计划判断不一致，或需要新增allowlist外production/test/validation-utility/README/workflow path。
- `S3-STOP-F01`修复无法只在Docling table projection boundary完成，或需要旧单数caption fallback、raw JSON/path parser、第二resolver、下游补偿、broad catch、private implementation mirroring/mock-only hook。
- caption ref的当前Docling public contract与§4.3直接证据不一致；未知collection/越界不能在精确`resolve()`调用边界分类；非文本item无法用public `TextItem`类型判定；多caption public结果需要新的schema/consumer协商。
- schema-valid root ref `#`不能在typed `RefItem.cref`边界以命名常量静默跳过，或需要调用`resolve()`、捕获`RuntimeError`、匹配异常文本、warning/log、raw parser/fallback/第二resolver才能处理。
- `S3-STOP-F02`无法只在`sec_form_section_common.py`的virtual-section publication owner关闭，或需要修改DocumentProcessor/SecProcessor marker contract、SEC/BS subclass、增加DOM/raw marker/capability schema、compatibility wrapper、第二resolver或第三个production path。
- marker缺失/不完整时只能用首章节、最近章节、标题/顺序/相似度或底层偶然ref猜ownership；duplicate/dangling/contradictory不能与incomplete proof稳定区分并fail closed；zero-table不能保留合法virtual projection；10-K/10-Q二次postprocess在fallback后不能由同一owner幂等短路。
- 当前Docling delta、六个Slice 3 test路径、continuation或Controller-owned/protected artifact任一entry hash漂移；plan-only gate出现production/test/README/utility diff；staged state非空。
- AR-F05再暴露`S3-STOP-F01/F02`以外production defect，或只有private implementation mirroring/mock-only hook才能达到80%。
- Service boundary必须扩大allowlist才可通过；出现import cycle并诱发lazy import/re-export/facade方案；`tests/cli/test_fins_commands.py` 或 public-awaiting utility 需要超出精确 import 迁移的改动。
- Current compact artifact没有唯一manifest digest关联、出现重复owner-published association或schema与本计划直接证据不一致。
- Logger state无法在test harness内完整恢复而必须改变standalone logging行为。
- Canonical full suite在Slice 2后非零、public-awaiting smoke在owner迁移后非零、direct-stream/awaiting stale-private scans在 `dayu tests utils` 有命中、coverage除精确R05 node外还需排除任何node、219集合不是精确219或任何文件<80%。
- 任一coverage运行前的AR-F06 exact `pytest --collect-only`未唯一收集该完整node id。
- Full pyright新增错误、Ruff baseline set扩散、protected zero-diff path变化、staged state非空或Controller-owned worktree hash漂移。
- Security/deferred/no-code scan出现新命中；configured-secret scan在任一Tool Trace、audit、public / LLM-facing、log、其它output、diff或review surface非零，或trusted-internal logical match超出exact Config / Host effective-execution owner；build失败；真实smoke只有mock/skip才能通过。
- 任一§2.2.1 owner-level sentinel test失败，视为真实projection leak候选并立即停止。证据必须指出唯一失败owner（Tool Trace filter/extract、audit line builder、HostEvent projection、run-input / memory / compact selector或具体logger callsite）及最小输入/输出；不得新建sub-WU或额外slice。Controller若接受为真实leak，只能在同一umbrella内扩充该唯一source owner及其直接owner test的精确allowlist，再重审本三-slice plan；禁止字段名黑名单、下游UI / adapter repair、兼容分支或统一authorization框架。
- Windows evidence缺失、artifact不完整或run未checkout最终accepted commit。

已知 residual：

- `AR-F06` 是真实 scheduler/lifecycle bug，不因本计划消失；本轮只保持其owner/destination，不修、不waive。
- `AR-F07` 依赖真实remote Windows runner，不能在本地关闭。
- `S3-STOP-F01` implementation与8-node matrix已完成但仍是review-pending protected delta；本plan-only gate不把它标为reviewed/accepted，也不允许单独review/commit。
- `S3-STOP-F02`是当前blocking production correctness defect；双路完整plan review与Controller裁决已完成，本次plan-only fix后仍须完成Controller validation、MiMo/DS双路完整re-review并获Controller重新授权，之前不得实施。
- AR-F05大型SEC/Docling owner的80%门槛需要较多高价值边界cases；若测试揭示真实缺陷，进度可以停止，但不能牺牲owner boundary或测试质量。

## 10. Plan acceptance checklist

- [ ] 本S3第二次plan-review fix只修改本plan并新增固定second-production-defect plan-review-fix artifact；production/test/README/utility/workflow/control、既有correction/validation/review/continuation/Controller artifacts零变化，Docling delta、六个Slice 3 test路径与全部protected dirty artifact SHA-256逐项不变，staged为空。
- [ ] 三个slices且顺序固定，AR-F01—F05均有唯一closure owner与test oracle。
- [ ] `S1-SEC-F01`关闭为no-code blocker；exact Config / Host internal effective-execution命中是accepted classification，Tool Trace、audit、public / LLM-facing、log、其它output、diff与review surface分别要求零明文。
- [ ] Slice 1追加五个精确owner-test allowlist path与synthetic sentinel contract，不增加production path、不增加slice；测试明确保留Engine执行所需`RunnerSpec.headers`，只对projection做zero断言。
- [ ] AR-F02不扩大Service allowlist，无compat re-export/lazy import/duplicate enum/protocol；Slice 2 test allowlist、focused tests 与direct consumer scan均覆盖 `tests/cli/test_fins_commands.py`。
- [ ] Slice 2 的独立 validation-utility allowlist 只含 `M utils/smoke_host_public_awaiting_entrypoint.py`，只迁移 `AwaitingResolutionMode` import；owner迁移后fresh运行 public-awaiting smoke。
- [ ] Direct-stream/awaiting definition、consumer 与stale-private scans在 Slice 2 与final aggregate均覆盖 `dayu tests utils`，旧 private import/definition零命中。
- [ ] AR-F04只用current runner manifest + compaction request digest关联，无candidate_id/raw guess/fallback。
- [ ] AR-F03只做in-process test harness isolation，standalone product logging零 diff。
- [ ] Slice 3 production allowlist精确为`M dayu/documents/processors/docling_processor.py`与`M dayu/fins/processors/sec_form_section_common.py`；本次恢复只新增后者diff，Docling受保护，其余七个AR-F05 owners零diff，219 changed-production集合不变。
- [ ] Caption resolver只消费`TableItem.captions`并用每个`RefItem.resolve(document)`读取同一DoclingDocument；旧单数caption `getattr`、`caption_text()`、raw JSON/private path、fallback与第二resolver为零。
- [ ] Schema-valid root ref `#`只以命名模块常量和typed `RefItem.cref`在resolve前跳过；unknown collection/out-of-range只在单次resolve周围捕获`AttributeError`/`IndexError`且无warning/log；model-invalid loader test固定`not-a-valid-cref`，production不读取JSON alias `$ref`。
- [ ] 多caption按refs顺序、现有whitespace normalizer、大小写敏感精确去重、首次保留、单空格连接形成唯一public caption；空/全空白/未知collection/越界/非文本边界与非数据异常传播规则完整。
- [ ] Public tests全部经真实Docling serialize/load并断言`list_tables`、`read_table`与page table结果；不只测private helper。
- [ ] `S3-STOP-F02`由`sec_form_section_common.py`唯一owner以private typed `BUILDING / VIRTUAL_PUBLISHED / BASE_FALLBACK_PUBLISHED`原子选择完整virtual projection或完整base fallback；`_refresh_virtual_section_state()`是唯一terminal transition owner，DocumentProcessor/SecProcessor marker contract、两个form-common空candidate guard与10-K/10-Q subclass零diff。
- [ ] 六类owner/public反例完整：public TenK unsupported marker/base table、complete marker、无矛盾incomplete（含range/title无法唯一归属）、duplicate/dangling/contradictory（含incomplete+dangling优先fail-closed）、zero table、10-K/10-Q二次postprocess fallback幂等不重入；fallback逐值验证base/form section refs、table refs、table `section_ref`、title/read/search及`read_section.tables`。
- [ ] 五个且只有五个public consumers `list_sections/list_tables/get_section_title/read_section/search`只消费同一typed mode；`_filter_table_refs_by_availability`静默过滤、`list_tables`首/最近章节补偿与`_assign_unmapped_tables_by_position`均为零。
- [ ] 现有Docling与Slice 3 test delta完整保留；恢复implementation后先关闭S3-STOP-F02，再继续九owner coverage cases。
- [ ] Production/test/validation-utility/README allowlists与protected paths精确列出。
- [ ] 每slice含focused tests、canonical suite、coverage、pyright、Ruff、diff、build、scans、README/security/deferred/no-code和真实smoke。
- [ ] Slice 3按现有职责更新`dayu/fins/README.md`的atomic virtual/base publication稳定语义；根README、`dayu/README.md`与`tests/README.md`保持NO_UPDATE。
- [ ] 每次coverage前exact `pytest --collect-only`唯一收集AR-F06完整node id；coverage只排除该精确单node；最终要求219/219 line coverage >=80%。
- [ ] 每slice要求MiMo/DS完整code review、fix、完整re-review；全部slice后重新aggregate regression，再进入MiMo/DS aggregate deepreview。
- [ ] AR-F06保持no-code residual，AR-F07保持Windows pending release blocker。
- [ ] Config/Host SQLite/EventLog trusted internal与Tool Trace/audit/public/LLM/log zero-required不变；Gemini quota保持non-blocking no-code且无额外真实调用/配置变化；Issues 142/151/175/177/178、Topic 8/9与统一tool authorization不实施。
- [ ] Immutable第二次corrected plan已经MiMo/DS双路完整plan review与Controller裁决；本次AgentCodex只修`S3-P2-PF01`—`PF04`。唯一next gate是Controller validation与MiMo/DS对完整fix后plan及fix artifact的双路完整re-review；Controller新授权前不实施。
