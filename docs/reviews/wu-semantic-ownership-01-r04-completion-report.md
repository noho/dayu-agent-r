# WU-SEMANTIC-OWNERSHIP-01 R04 Completion Report

## 1. 状态、身份与 completion verdict

- 状态：`READY_FOR_CONTROLLER_COMPLETION_VALIDATION`。
- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation sub-WU：R04 `awaiting provider resolution composition`；不是新 WU。
- 当前 gate：R04 completion report；本报告是 completion evidence，不是 Controller completion acceptance。
- 当前 HEAD：`2254eb3e4800fe323fe2e8567a00b54c562a0478`（`phaseflow: enter R04 completion`）。
- accepted plan commit：`983070dd1d56490d23529970960349a3df3e9787`。
- accepted product commit：`9e349ac42cf43b89bb025f66a405bdae9d9a8eaa`。
- accepted aggregate evidence commit：`68a31dc96dccc3853a5e56402a1ce9e5603baae5`。
- 本 gate 唯一写入：本文件 `docs/reviews/wu-semantic-ownership-01-r04-completion-report.md`。
- 本 gate 明确未做：未修改产品代码、配置、测试、README、plan、control 或任何既有 artifact；未 commit、stash、push、创建 PR；未进入或实施 R05。

结论：R04 的 accepted plan、唯一原子 S1、Controller validation finding 修复、双路 code review、accepted product commit、accepted-commit aggregate validation、双路 aggregate deepreview 与 Controller adjudication 已形成完整、相互一致的 evidence chain；所有当前 R04 accepted findings 均已关闭。因此本报告支持 R04 **进入 Controller completion validation**。

本报告不自行宣布 R04 complete，不关闭 umbrella，也不授权 R05。尤其是 code-review `DS-F01` 指向的 observation-timeout -> `LOST` 行为仍与已裁决设计冲突，必须由 R05 修复；它不是 umbrella-final acceptable behavior，不能因 R04 product/aggregate commit 已接受而被视为正确终态。

## 2. 第一性原理判断与 root cause

R04 动机成立。修复前，同一个 awaiting provider 恢复事实被拆散在多个 owner：Fins binding 硬编码 `POLL`，Host poller 部署值同时存在于代码默认与运行配置，Service 又从 scene/tool exposure 推导是否启动 poller。选中工具因此既改变模型可见能力，又隐式改变 Host 后台运行时；provider mode、部署 policy、composition 与执行语义没有唯一真源。

正确修复不是在 Host、entrypoint 或测试中增加 fallback，而是把事实放回其 owner：provider config 拥有恢复 mode，`host_runtime.json` 拥有完整部署 snapshot，Service 只组合 typed inputs，Host 只执行显式 policy。最终代码与 accepted evidence 证明修复发生在这些 owner boundary，没有通过 raw-config 重解析、scene 特例、兼容字段、无参默认或下游补偿隐藏 root cause。

## 3. 提交链与 immutable evidence target

| gate / commit | SHA | 含义 |
| --- | --- | --- |
| R03 accepted base | `f7006a80` | R04 产品语义基线 |
| R04 plan transition control | `dc565d8c` | 关闭 R03 completion、进入 R04 plan；control-only |
| R04 accepted plan | `983070dd` | 接受最终 212 行 R04 plan 与完整 plan review/fix/re-review 链 |
| R04 implementation transition control | `a4ffd764` | 进入唯一原子 S1 implementation；也是最终 S1 diff base |
| R04 accepted product | `9e349ac4` | 接受唯一原子 S1、F01 fix、双路 code review 与 Controller adjudication |
| R04 aggregate transition control | `c2a40929` | 进入 accepted-commit aggregate validation；control-only |
| R04 accepted aggregate evidence | `68a31dc9` | 接受 aggregate validation、双路 aggregate deepreview、Controller adjudication与当时 control state |
| R04 completion transition control / current HEAD | `2254eb3e` | 只修改 current control state，进入本 completion report gate |

`9e349ac4` 的 parent 是 `a4ffd764`；`68a31dc9` 的 parent 是 `c2a40929`；`2254eb3e` 的 parent 是 `68a31dc9`。本报告以 accepted product tree `9e349ac4`、accepted aggregate evidence `68a31dc9` 和当前 control truth `2254eb3e` 为最终取证对象，不把 implementation 期间的未提交 HEAD 描述误当作当前提交状态。

## 4. Accepted plan owner / contract matrix 对照

| 语义 | accepted owner / contract | 最终代码与证据 | 状态 |
| --- | --- | --- | --- |
| provider 恢复方式 | Fins awaiting provider config + Fins 唯一严格 parser；闭集 `poll/callback/manual`，无默认、trim 或 loose parse | `AwaitingResolutionMode(StrEnum)` 与 `parse_awaiting_resolution_mode(...)` 位于 `_ingestion_tool_helpers.py`；download/preprocess/upload direct provider 均在 runtime 创建前调用；packaged 三 provider 均显式为 `poll` | 满足 |
| provider mode 装配校验 | Service 只用既有 provider identity 路由到 Fins parser；recognized non-awaiting provider 只做字段存在性 misuse rejection | disabled Fins provider 在 active filtering 前也解析；disabled+illegal fail；disabled+legal 不 active；Fins read/Web 误配失败；未知第三方 config 保持 opaque | 满足 |
| poller 部署参数 | `host_runtime.json` 唯一拥有完整 required snapshot；ConfigLoader 只做层中立 exact typed parse | packaged snapshot 为 `true,1,60,100,30,2,300,1,5,30,5,8`；`WaitPollerRuntimePolicyConfig` frozen/required；缺失、多余、bool 冒充数值、非有限、零、负值均失败；`dayu.runtime` 无反向 import | 满足 |
| Host policy 值对象 | `WaitPollerRuntimePolicy` 只承载显式值；12 字段 required，无模块部署默认、无无参构造或 `None` fallback | 十个旧部署常量、dataclass defaults、`WaitPoller`/`WaitPollerSupervisor` fallback 均删除；最终只接收显式 `policy` | 满足 |
| 是否装配 poller | Service 只依据 active typed modes、runtime snapshot、poll registry 与显式 callback transport；scene 不拥有 authority | `_FinsAwaitingProviderMetadata` 是私有 frozen typed source；activation=全部 active awaiting，poll registry=`poll` only；prompt/interactive 共用同一 composition；旧 override/scene helpers 删除 | 满足 |
| typed discovery 派生传播 | discovery owner 产生的 Fins awaiting runtime/metadata 必须作为 required state，无 silent empty default | `ServiceDiscoveredTools` 两个 Fins state fields required；全仓唯一直接 constructor 位于 discovery owner；四个 derived consumers 用 `dataclasses.replace(...)` 保留状态 | 满足；`R04-S1-CV-F01` closed |
| poller 生命周期与执行 | Host 只执行 Service 显式传入的 policy；`None` 表示不装配；disabled 不启动；enabled + missing registry fail closed | Host public API/open_host 无 diff；Service 在 open 前验证 registry；public Host smoke 覆盖 enabled/disabled/no-provider/manual/callback | 满足 |
| callback transport | 只有未来 authenticated transport owner 可提供正向路径；当前必须在 Host open 前失败 | 当前不存在 marker/protocol/facade/callable 绕过入口；任意 active callback composition error，不降级 poll/manual | 满足当前 fail-closed contract；正向能力未实现 |
| operation-kind 结构映射 | 保留 observation handle 恢复所需 `tool name -> FinsOperationKind`；只禁止用 tool name 发明 resolution policy | `_operation_kind_from_tool_name` 保留；`_binding_for_tool_name` 另以 typed mode 映射 `WaitResumePolicy` | 满足 |

本实现采用一个原子 S1，同时落地 umbrella 原 R04-S1 provider mode、原 R04-S2 runtime policy 与原 R04-S3 composition。实施 artifact 与 commit graph 均证明原子 implementation pass 期间没有中间 commit/checkpoint、compatibility seam 或 broken intermediate state；最终只在完整闭环后形成 accepted product commit。

## 5. Product diff、删除的 contract 与 handoff artifact

### 5.1 Accepted product commit exact scope

`git show --name-status 9e349ac4` 证明 product/config 只修改 accepted plan allowlist 中的 11 个文件：

- `dayu/config/host_runtime.json`
- `dayu/config/tool_discovery.json`
- `dayu/fins/tools/_ingestion_tool_helpers.py`
- `dayu/fins/tools/download_provider.py`
- `dayu/fins/tools/preprocess_provider.py`
- `dayu/fins/tools/upload_provider.py`
- `dayu/host/wait_adapter.py`
- `dayu/runtime/config_loader.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/service/fins_wait_adapter.py`
- `dayu/service/host_assembly.py`

测试/烟测变更为 10 个 tests 与 5 个 utils smoke；其中 F01 correction 额外授权的四个 derived consumers 是 `tests/tools/test_combined_tools_acceptance.py`、`utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py`。README 只修改 config/Fins/Host/Service/tests 五份责任文档。其余变更是 R04 implementation/validation/review artifacts 与 control gate state。

### 5.2 删除的错误或多 owner contract

- 删除 `_binding_for_tool_name` 对 `WaitResumePolicy.POLL` 的无条件硬编码，由 Fins typed mode 精确映射。
- 删除 `ServiceAssemblyOverrides.wait_poller_policy` 这一第二 policy 输入。
- 删除 `with_entrypoint_wait_poller_policy`、`_scene_selects_fins_awaiting_tools` 与 entrypoint scene-derived auto-enable 路径。
- 删除 Host 十个部署值模块常量、`WaitPollerRuntimePolicy` 全部字段 defaults、无参构造与 `WaitPoller`/`WaitPollerSupervisor` 的 `None` fallback。
- 删除从 raw provider config 重建 registry input 的旧路径；binding、activation、poll registry 与 policy decision 共用 owner-produced typed metadata。
- 收紧 `ServiceDiscoveredTools` required construction invariant，消除“owner 确认 empty”和“调用方漏传”共享空 tuple default 的歧义。

未增加兼容 alias、wrapper、facade、extra payload、旧 schema 读取、scene bridge、callback marker、generic provider framework 或第二 enum/parser。

## 6. Composition matrix 逐项 closure

| active modes / runtime | registry / transport | accepted contract | 最终证据 |
| --- | --- | --- | --- |
| 无 active awaiting provider | 无 poll registry | 不传 policy，不启动 | owner tests + public smoke pass |
| 仅 manual | activation 有、poll registry 无 | binding=`MANUAL`，不传 policy，不启动 | owner tests + public smoke pass |
| 仅 poll，policy enabled | poll registry 非空 | 12 字段一对一传入，Host 启动 | owner tests + public smoke pass |
| poll + manual，policy enabled | activation 含两者，poll registry 仅 poll | 只 claim/observe `POLL` wait | owner composition tests pass |
| active poll，policy disabled | poll registry 可构造 | disabled snapshot 仍显式传入，Host 不启动且不回退默认 | Host/Service tests + public smoke pass |
| active poll，policy enabled，registry 缺失/空 | registry 缺失/空 | Service 在 `open_host` 前 composition error | negative test pass |
| 任意 callback，单独或混合 | 无 authenticated transport | Service 在 `open_host` 前 error，不降级 | negative test + public smoke pass |
| callback + 伪 marker/普通 callable | 当前无此 public/Service input surface | 不存在绕过入口，仍 fail closed | source/public-boundary audit pass |
| mode 缺失/null/非字符串/空串/未知/大小写/空白变体 | 任意 | Fins owner parser 失败，不进入 composition | parameterized owner tests pass |
| recognized non-awaiting provider 声明该字段 | 任意 | Service 仅按字段存在性报告 owner misuse，不 loose parse | negative test pass |
| unknown third-party provider 声明同名 opaque field | 任意 | 保持 opaque，不发明 R04 语义 | negative test pass |
| disabled provider，合法 mode | 不 active | 不创建 binding，不影响 poller | tests + public smoke pass |
| disabled provider，非法 mode | 任意 | active filtering 前 fail fast | negative test pass |
| scene all/select/none | provider/runtime inputs 相同 | Host opener policy 不变；scene 只控制单次 run tool exposure | propagation comparison tests pass |

## 7. Tests、coverage、pyright 与质量 gate

本 completion gate 按用户要求未重复运行完整 509-test matrix；以下数字来自 accepted implementation、Controller re-validation 和 accepted-commit aggregate validation，并已与 artifact、commit 和当前 source 交叉核对。

| evidence gate | 结果 | 含义 |
| --- | --- | --- |
| plan-entry baseline | `325 passed, 3 warnings` | 变更前 R04 相关基线；不是完成验收 |
| initial implementation / Controller validation | `508 passed, 3 warnings` | 原子实现完整 affected matrix；随后发现 propagation F01 |
| F01 focused fix / Controller re-validation | `36 passed, 3 warnings` | required constructor、四个 derived consumer 与 public-composition regression |
| final accepted-plan matrix / Controller re-validation | `509 passed, 3 warnings` | F01 新 regression 纳入完整 17-target matrix |
| DS independent code-review subset | `419 passed, 3 warnings` | reviewer 独立子集；不替代 Controller 509 matrix |
| accepted-commit aggregate validation | `509 passed, 3 warnings` | 在 `9e349ac4` accepted product state 重新执行的 canonical completion evidence |

三条 warning 均为既有 edgar dependency deprecation warning；没有产品 failure、skip/xfail 规避或 baseline failure 六元组。Baseline failure registry delta 为零。

### 7.1 Final changed production file coverage

| changed production Python file | accepted-commit coverage | gate |
| --- | ---: | --- |
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.54% | PASS |
| `dayu/fins/tools/download_provider.py` | 100% | PASS |
| `dayu/fins/tools/preprocess_provider.py` | 100% | PASS |
| `dayu/fins/tools/upload_provider.py` | 100% | PASS |
| `dayu/host/wait_adapter.py` | 90.41% | PASS |
| `dayu/runtime/config_loader.py` | 96.31% | PASS |
| `dayu/service/entrypoint_runtime.py` | 88.27% | PASS |
| `dayu/service/fins_wait_adapter.py` | 94.57% | PASS |
| `dayu/service/host_assembly.py` | 95.03% | PASS |

全部修改的生产 Python 文件逐文件 `>=80%`；没有以总覆盖率、pragma 或 omit 掩盖缺口。

### 7.2 Type、lint 与 whitespace history

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- changed Python/test/smoke 的 Ruff `F401,F841`：PASS。
- implementation、Controller re-validation 与 aggregate validation 的 `git diff --check`：PASS。
- F01 收紧 required signature 后、修正 derived consumers 前，pyright 精确暴露四个 `reportCallIssue`；最终 full pyright clean，证明 owner state 丢失已从静默行为变成开发期失败。

## 8. README decision

实施前已按各 README 的 Agent 更新约束核对职责。最终 decision：

| README | 最终内容 / decision |
| --- | --- |
| `dayu/config/README.md` | 更新完整 required 12 字段、数值/bool边界、packaged snapshot 与 Fins provider mode contract |
| `dayu/host/README.md` | 更新 config-owned 显式 policy、Host 无 deployment defaults/None fallback |
| `dayu/service/README.md` | 删除 scene-selected auto policy 描述，记录 private typed projection 与 composition |
| `dayu/fins/README.md` | 记录 provider-owned 唯一 parser、三模式及 registry 行为；不宣称 callback 正向 transport |
| `tests/README.md` | 记录 ConfigLoader/Fins/Service/Host matrix、public smoke 与 derived discovery invariant |
| 根 `README.md` | 不触发；用户入口、命令、工作流与排障面未变 |
| `dayu/README.md` | 不触发；分层关系未变，只把层内语义放回 owner |

## 9. Source、propagation、scope 与 smoke evidence

### 9.1 Source / propagation scans

Accepted evidence及本 completion gate 的只读复核均得到：

- `with_entrypoint_wait_poller_policy`、`_scene_selects_fins_awaiting_tools`、`WaitPollerRuntimePolicy()` 无参构造：production 零命中。
- 十个旧 Host deployment-default 常量：production 零命中。
- `awaiting_resolution_mode` 只存在于 packaged config、Fins 唯一 parser/direct providers、Service owner routing/presence rejection 与 owner tests；下游不重读 raw mode。
- prompt assets 与 `execution_profiles.json` 中的 `wait_poller_policy|awaiting_resolution_mode`：零命中。
- `dayu.runtime` 对 Engine/Host/Service/UI/Fins 的锚定 import：零命中。
- `f7006a80..9e349ac4` 产品/tests/smoke added-line 对 `authorization|permission|process_backed|subprocess|observation_timeout|ResolveWaitLostOutcome`：零新增命中。
- `dayu/host/api.py`、`dayu/host/open_host.py`、`dayu/engine/`、prompt assets、`execution_profiles.json` 在 R04 product range 无 diff。
- 全仓 Python 只有 Service discovery owner 一处直接 `ServiceDiscoveredTools(...)`；四个 authorized derived consumers 均使用 `dataclasses.replace(...)`，不访问 private metadata 或 reparse raw config。

### 9.2 Packaged public Host smoke

Controller 在 implementation validation、re-validation 与 accepted-commit aggregate validation 分别独立运行 `utils/smoke_host_public_awaiting_entrypoint.py`。最终 aggregate smoke 使用真实 packaged：

```text
ConfigLoader
  -> provider discovery
  -> Service typed composition
  -> public Host / production poller / durable wait
```

结果为：typed modes `poll/manual/callback`、完整 12 字段 snapshot、prompt/interactive opener decision 一致；manual/no-provider/provider-disabled/runtime-disabled 不启动 poller；callback 在 Host open 前失败；poll enabled 实际得到 `observed_waiting=true`、`not_ready=1`、`ready=1`、`terminal=SUCCEEDED`、`outbox_terminal_match=true`。

smoke 只以本地 deterministic execution/observation boundary 替代外部任务，不替代 ConfigLoader、discovery、Service composition、Host opener、poller lifecycle 或 durable wait；未访问外部 LLM、网络、secret 或 raw credential-bearing config。按本任务边界未执行外网 smoke，不构成 R04 product failure。

### 9.3 R05 handoff evidence

R05 的输入事实已经完整、不可依赖 scene/name heuristic：

- effective packaged modes：download/preprocess/upload 三个 provider 均为 typed `POLL`；manual 与 callback owner paths已有 negative/composition proof。
- effective runtime snapshot：`enabled=true`、`poll_interval_seconds=1`、`claim_ttl_seconds=60`、`claim_batch_size=100`、`backoff_initial_delay_seconds=30`、`backoff_multiplier=2`、`backoff_max_delay_seconds=300`、`not_ready_observe_interval_seconds=1`、`idle_poll_interval_seconds=5`、`adapter_call_timeout_seconds=30`、`close_drain_timeout_seconds=5`、`max_outstanding_adapter_calls=8`。
- registry composition：activation registry覆盖全部 active awaiting provider；poll registry只覆盖 typed `POLL`；manual/callback不进入 poll registry。
- public behavior proof：enabled poll path真实经历 not-ready -> ready -> succeeded；outbox terminal与 public terminal一致。
- R05 唯一允许消费以上 typed/config-owned facts，不得恢复 scene/tool-name policy heuristic，不得复制部署数值或重解析 raw mode。

这些 handoff facts 只证明 R04 为 R05 准备了稳定输入；本报告不授权 R05 plan 或 implementation。

## 10. Findings 最终 ledger

### 10.1 Plan review / validation / re-review

| finding | 最终状态 | closure / rejection reason |
| --- | --- | --- |
| `R04-PLAN-F01` | closed | typed resolution-policy 映射与 retained operation-kind 结构映射已明确分离 |
| `R04-PLAN-F02` | closed | provider/policy/scene-composition 共享节点合并为唯一原子 S1，无 broken intermediate state 或兼容 seam |
| `R04-PLAN-F03` | closed | disabled Fins 与 recognized non-awaiting misuse 的 Service/Fins owner、顺序与 tests 已固定 |
| `R04-PLAN-F04` | closed | 旧 override/scene/Host/provider tests 已按 owner contract 迁移，不机械删测 |
| `R04-PLAN-CV-F05` | closed | manual/callback typed contract 与旧 scene authority 不再跨 slice 并存；唯一原子 S1 同时删除旧 authority |
| `R04-PLAN-RR-F01` | rejected-with-reason | plan 已固定 typed source-of-truth contract；预设私有 dataclass/helper 精确签名会过度约束实现 |
| `R04-PLAN-RR-F02` | rejected-as-duplicate | bool/int rejection 与 mandatory negative tests 已在 plan 明确 |
| `R04-PLAN-RR-F03` | rejected-with-reason | owner与执行顺序已固定；预设 helper 拆分会诱发重复遍历/双真源 |
| `R04-PLAN-RR-F04` | observation / no-fix | `test_import_boundary.py` 属于必须运行的 validation target，不属于可修改 allowlist，二者无冲突 |

Initial plan review 的其余 no-fix/rejected 项也已最终分类：MiMo 01（字面 default scan）、03（Host API/open_host stop wording）、05（callback+poll 整体失败）、08（scan 时序）、09（325 baseline）、10（fresh schema atomicity）、11（单一 `--cov=dayu`）、12（identity helper不读mode）均为已有 contract / no-fix；MiMo 06 为 callback transport deferred capability；DS F-04 要求部署常量 scan 预留宽松例外被 rejected；DS F-06 scene `None=all` 因整个 helper 删除而 no-fix；DS Q2 packaged values 与 Q3 structural Protocol 均 answered/no-fix；callback error type沿 Service 既有异常惯例，不新增 public contract。

Plan 最终 ledger：accepted plan findings `R04-PLAN-F01..F04` 与 `CV-F05` 全部 closed；re-review accepted finding `0`；blocking question `0`。

### 10.2 Implementation / code review

| finding / observation | 最终状态 | 证据 / disposition |
| --- | --- | --- |
| `R04-S1-CV-F01` | **closed** | 两个 Fins discovery state fields required；唯一 direct constructor；四个 `dataclasses.replace(...)`；public binding/activation/poll/policy regression；full pyright clean |
| code-review `DS-F01` | **deferred-to-R05 / mandatory** | 当前 observation timeout 仍 terminalize 为 `LOST`；R05 必须改为 invalidate late publication、transient diagnostic、release claim、policy backoff、保持 `WAITING` |
| code-review `DS-F02` | rejected-with-reason | 依赖未来 provider 复用 built-in identity fragment 的假设；当前无 config/contract/fixture 证据；改三字段 conjunctive framework会破坏已接受 alternative-identity contract |
| MiMo NaN/Infinity test observation | observation / no-fix | shared ConfigLoader JSON owner已有 non-finite tests，policy parser也调用同一 finite validator；无需重复 literal test |
| MiMo spec-id index observation | observation / no-fix | typed tuple是真源；小闭集 helper重建不重解析 raw config，无 correctness/ownership/performance defect |

Code-review final ledger：current accepted finding `0`；deferred mandatory owner `1`；rejected `1`；no-fix observations `2`；blocker `0`。因此没有空 fix/re-review gate。

### 10.3 Aggregate validation / deepreview

| finding | 最终状态 | evidence / reason |
| --- | --- | --- |
| aggregate validation finding | none | accepted-commit validation PASS；F01保持closed；无新 current finding |
| `DS-AGG-F01` | rejected-with-reason | 第一次 index构造在 Fins runtime/storage initialization 前做 fail-fast duplicate validation；第二次由后续 binding owner建立 lookup。复用会扩宽 owner contract形成 tuple+dict双表示；set check会复制错误语义；小闭集O(n)无可测缺陷 |
| prior `DS-F01` | deferred-to-R05 / mandatory | aggregate revalidation确认code/design差距仍在且R04未偷带修复 |
| prior `DS-F02` | rejected-with-reason | aggregate composite chain 无新证据，原裁决保持 |

Aggregate final ledger：current accepted aggregate finding `0`；deferred mandatory owner `1`；rejected-with-reason `2`；blocking question `0`。MiMo aggregate verdict为 `PASS / ZERO ACCEPTED CURRENT FINDINGS`；DS aggregate verdict为 PASS 且只有上述低严重度 observation；Controller adjudication不要求 fix/re-review。

## 11. 保留的安全机制与未实现统一 authorization

### 11.1 Retained safety / security mechanisms

R04 没有以“未来统一 authorization 尚未设计”为理由删除实际 I/O boundary 防御。最终 product diff 与 security scans证明以下机制保留：

- Doc `allowed_paths`、resolved path containment、directory/file symlink边界、output truncation与cooperative cancellation。
- Web configurable private/local network与custom-port authority、逐跳DNS/redirect重检、numeric pin/peer proof、proxy/peer冲突fail-closed、HTTP/browser/diagnostic resource budgets、browser capability独立开关、challenge detection/fallback、diagnostics v2与credential/error redaction。
- Fins storage path containment、symlink防御、transaction lock/journal recovery、staging/atomic publish/atomic write边界。
- Host canonical arguments digest、EventLog/audit完整性、opaque provenance仅内部可见、durable wait claim/lease与late-publication fencing。
- ToolRuntime/process cancellation与late result fencing、Host close/drain边界、atomic artifact publish与containment-guarded durable storage。
- 现有 identity、allowed-path、network、storage、cancel、durable wait与process fencing contracts均未被放宽；`wait_adapter.py` 的R04 diff只删除部署默认/fallback并加强显式policy，不改 observation-timeout状态机。

### 11.2 Unified authorization 明确未实现

仓库仍没有 repository-wide unified tool authorization framework：没有按 principal/Run/Attempt 决定工具读写位置、资源scope或side-effect capability的统一 Host authority；现有 generic `authorization_claims` 也没有映射成 effective tool resource authority。R04没有引入角色模型、permission schema/DSL、capability token、credential broker、sandbox或兼容迁移层。

最终设计意图仍是未来由 Host ToolRuntime 或等价 Host governance boundary 拥有最大授权scope，具体 filesystem/network/process/storage owner继续在实际I/O边界执行containment、DNS/redirect、TOCTOU、resource与protocol防御。当前 `allowed_paths` 与Web policy config继续有效；未来独立design WU若建立统一authority，应迁移到一个真源并删除重复permission truth，而不是给R04增加临时framework。

## 12. Residual owner / deferred Issue 与无偷带证明

| residual / deferred boundary | owner / destination | R04 final state |
| --- | --- | --- |
| observation timeout当前被错误terminalize为`LOST` | **R05 mandatory owner**：Host `WaitObservationRunner`/wait adapter/state store；Engine只拥有pre-awaiting handshake timeout | 未修；必须在umbrella final closeout前修；**不是 umbrella-final acceptable** |
| Fins awaiting长事务/Docling物理进程隔离 | GitHub Issue #175 | 未触碰；R05也不得迁移其executor ownership |
| authenticated callback正向transport | accepted plan记录的WU-WAIT-01 / Issue #89 owner lineage；当前已完成范围只含typed/framework-neutral mapper，不含真实HTTP route/auth verifier | 未实现；当前pre-open fail-closed正确，R04不造fake transport |
| workspace migration framework | GitHub Issue #142 | 未触碰 |
| future write/product assets | GitHub Issue #151 | 未触碰 |
| Doc `TruncationManager`/`fetch_more`完整接入 | GitHub Issue #177 | 未触碰 |
| Web browser storage-state lifecycle | GitHub Issue #178 | 未触碰；R04不恢复TTL/naming/publish/cleanup lifecycle |
| unified tool authorization | Topic 9 后续独立design WU / user decision | 未设计、未实现；保留局部permission与I/O防御 |
| 外部LLM/网络smoke | 本任务明确不要求；本地packaged public Host smoke为当前R04验收owner | 未执行且不构成current finding；若未来产品要求live provider验证需由对应provider/smoke owner立项 |

`DS-F02` 与 `DS-AGG-F01` 已被 Controller 以直接理由 rejected，不保留为 active residual，也不建立 speculative future framework。除上述有明确 destination 的 deferred boundaries 外，没有 unowned current R04 residual。

R04 product range 的 direct diff/source checks同时确认：

- 没有 R05 observation timeout/retry/LOST新增代码；既有错误分支保持原样等待R05。
- 没有Issue #175的`process_backed`/`subprocess`实施。
- 没有Issue #142/#151/#177/#178能力、schema、assets或lifecycle实施。
- 没有callback transport、marker、facade或auth verifier。
- `dayu/host/api.py`与`dayu/host/open_host.py`无diff；Host public API未改变。
- `dayu/engine/`无diff；Engine handshake未改变。
- prompt assets、`execution_profiles.json`无diff；scene与execution profile没有获得poller authority。
- 没有unified authorization、permission schema/DSL或capability framework。

R05、R06-R12和最终umbrella aggregate/final closeout均仍是后续gate；本报告没有把它们作为R04产品scope实施或宣布完成。

## 13. Completion gate decision 与下一入口

R04 accepted plan要求的 owner、contract、composition matrix、tests、逐文件coverage、pyright、README、source/propagation/security scans、packaged public smoke与R05 handoff已全部有accepted evidence；plan/code/aggregate findings也均处于closed、deferred-with-mandatory-owner、rejected-with-reason或observation/no-fix终态，没有current accepted finding、blocking question或unowned residual。

因此本报告的判定是：**R04可以进入Controller completion validation。**

下一且唯一允许入口是Controller对本completion report做独立validation并裁决R04 completion。只有Controller通过并另行写入transition/control commit后，才可进入R05 plan gate。本报告不自行宣布R04 complete、不宣布umbrella complete、不进入R05，也不授权commit、push或PR。

## 14. Completion artifact self-check

本文件初次写入后的最终自检口径如下；完成最后一处 whitespace 修正后会对同一最终内容再运行一次：

- `git rev-parse HEAD`：仍为 `2254eb3e4800fe323fe2e8567a00b54c562a0478`。
- `git status --short` 与 `git ls-files --others --exclude-standard`：唯一新增路径是本 completion report；没有 tracked file 修改。
- `git diff --check`：exit `0`，无输出。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r04-completion-report.md`：以“内容不同”的预期 non-zero 退出；最终要求为零 whitespace diagnostic。
- 本 completion gate 只做 source/commit/evidence read-only checks，没有重复 509 tests、pyright、smoke或任何会改变既有artifact的命令。
