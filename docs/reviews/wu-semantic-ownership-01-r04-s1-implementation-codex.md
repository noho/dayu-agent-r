# WU-SEMANTIC-OWNERSHIP-01 / R04-S1 Implementation — awaiting provider resolution composition

## 1. Gate 身份、结论与不可变基线

- umbrella WU：既有 `WU-SEMANTIC-OWNERSHIP-01`；本次不是新 WU、feature 或 issue。
- remediation：R04 `awaiting provider resolution composition`。
- gate：accepted plan 的唯一原子 S1 implementation；下一入口仅为 Controller validation。
- accepted plan commit：`983070dd1d56490d23529970960349a3df3e9787`。
- workspace base：`a4ffd7641c8f114e987972d77572c2c2b4a8202f`，实施前为 clean。
- implementation HEAD：`a4ffd7641c8f114e987972d77572c2c2b4a8202f`；HEAD 未移动，全部实现仍是未提交工作树 diff。
- artifact：`docs/reviews/wu-semantic-ownership-01-r04-s1-implementation-codex.md`。
- 结论：provider-owned typed mode、config-owned 完整 policy snapshot、Host 显式执行 policy、Service typed composition、入口同路径、测试、README、scans 与真实 public assembly smoke 已在同一次 implementation pass 中共同完成。没有中间 commit、checkpoint、stash、push 或 PR 动作。

动机成立。修前 provider 的恢复语义被 Service 硬编码成 `POLL`，poller 部署值同时存在于代码默认和配置路径，scene 又参与决定 Host 是否装配 poller。这会让同一业务事实产生 provider、Service、Host 和 entrypoint 多个 owner，导致 prompt/interactive、disabled provider 与直接 provider discovery 得出不一致行为。修复必须落在各自 owner boundary，不能由下游 fallback 或 scene 特例补偿。

## 2. Owner 结构与单一数据流

### 2.1 Provider mode owner

- `dayu.fins.tools._ingestion_tool_helpers` 定义闭集 `AwaitingResolutionMode(StrEnum)` 与唯一严格 parser。
- parser 只接受精确字符串 `poll`、`callback`、`manual`；缺失、null、非字符串、Python bool、空串、大小写变体、前后空白和未知值都失败，不做默认、trim 或宽松转换。
- download/preprocess/upload 三个直接 provider 在构造 runtime/tool definition 前调用同一 parser；packaged provider config 均显式声明 `poll`。
- Service 只通过既有 provider identity 识别三个 Fins awaiting provider，并在 active filtering 前把 raw provider config 交给该唯一 parser。disabled provider 因而也先严格 parse；合法 disabled provider 不进入 active metadata。
- Service 已认识的 Fins read/Web non-awaiting provider只做字段是否存在的 misuse rejection，不读取、规范化或解析 raw value；未知第三方 provider 保持 opaque，不为其发明 R04 语义。

### 2.2 用户提醒所要求的并行私有 typed projection

实现没有把 typed mode 或 metadata 写回 `ToolDiscoveryProviderConfig.config`，没有放入 extra payload，也没有给 ConfigLoader 增加 generic Fins/runtime metadata 字段。

`dayu.service.host_assembly` 使用并行的 Service 私有 frozen typed projection `_FinsAwaitingProviderMetadata`。它携带 provider id、source、version、tool name、absolute workspace root 与已经由 Fins owner parser 产生的 `AwaitingResolutionMode`；`ServiceDiscoveredTools` 将该私有 collection 与原始 `effective_provider_configs` 分开保存。后续 activation、binding、poll registry 与 composition 只复用这一 typed collection，不再读取 raw mode，也不存在第二 enum、parser 或 owner。

直接 provider discovery 与 Service packaged discovery 是两条互斥执行路径：前者由 provider 自身调用同一 owner parser；后者由 Service 在绕过默认 provider callable、建立共享 runtime 前调用同一 owner parser。任一路径对一个 effective provider 都只 parse 一次。

### 2.3 Runtime policy 与 Host owner

- `host_runtime.json` 显式持有 12 个全部 required 的 packaged snapshot：`true, 1, 60, 100, 30, 2, 300, 1, 5, 30, 5, 8`。
- ConfigLoader 新增 frozen/slots、全字段必填的 layer-neutral `WaitPollerRuntimePolicyConfig`，只做 exact-shape 与数值 contract parse；它不 import Fins/Host/Service/Engine，也不理解 provider mode。
- duration、multiplier 与 count 均须有限正数；整数位显式拒绝 Python bool。owner-level negative tests 覆盖每个整数位的 bool、零、负数、缺失、多余和非法数值。
- Host `WaitPollerRuntimePolicy`、`WaitPoller`、`WaitPollerSupervisor` 的部署常量、dataclass defaults、无参构造和 `None` fallback 全部删除；Host 只执行 Service 显式传入的完整 policy。
- `OpenHostOptions.wait_poller_policy=None` 仅表示 Service 判定没有 active poll provider，不是部署默认。

### 2.4 Service composition

- `_binding_for_tool_name` 依据 typed mode 精确映射 `POLL/CALLBACK/MANUAL`；tool name 到 `FinsOperationKind` 的稳定 handle 结构映射保留，未被误作 resolution policy。
- activation registry包含全部 active awaiting provider；poll registry只包含 typed mode=`poll` 的 provider。manual/callback 不进入 poll registry。
- 有 active poll 时，Service 把 ConfigLoader 的 12 个字段一对一构造成 Host policy；无 active poll 时不传 policy。
- runtime policy disabled 仍显式传给 Host，由 Host 不启动后台 poller；enabled 且 registry 缺失/空时在调用 `open_host` 前失败。
- 任意 active callback 因仓库中不存在对应 transport owner，在 `open_host` 前 fail-closed；没有新增 marker、协议、facade 或 callable 绕过入口。
- 删除 `ServiceAssemblyOverrides.wait_poller_policy`、旧 entrypoint policy helper 与 scene 推断 helper。scene 只控制单次 run tool exposure；prompt/interactive 共用同一 Service composition path。

## 3. Umbrella 原 S1/S2/S3 mandatory baseline 对照

| umbrella 原项 | 唯一原子 R04-S1 实际处置 | 证据 |
|---|---|---|
| 原 S1 provider-owned `poll/callback/manual` | 完整落地；Fins 单一 enum/parser、三个 packaged provider 显式 poll、direct discovery 前置校验、disabled 前置校验、typed binding、recognized misuse 与 unknown opaque 边界共同完成 | Fins owner tests、Service metadata/negative tests、mode propagation scan |
| 原 S2 config-owned 完整 runtime policy | 完整落地；JSON 12 字段 required snapshot、layer-neutral typed projection、bool/int 严格边界、Host defaults/fallback 删除、一对一 projection 同步完成 | ConfigLoader/Host tests、12 字段 smoke handoff、default deletion scans |
| 原 S3 Service-only composition | 完整落地；private parallel typed collection、activation/poll registry 分流、callback pre-open failure、override/scene authority 删除、prompt/interactive 同路径同步完成 | Service composition matrix、entrypoint tests、public Host smoke |

三项没有被拆成可提交或可 review 的中间状态；工作树只形成当前一次完整原子终态。

## 4. Actual changed-files

相对实施 base `a4ffd764`，最终工作树只包含 accepted plan §4.1 allowlist 中的下列文件及唯一 handoff artifact：

### 4.1 Production / config

1. `dayu/config/host_runtime.json`
2. `dayu/config/tool_discovery.json`
3. `dayu/fins/tools/_ingestion_tool_helpers.py`
4. `dayu/fins/tools/download_provider.py`
5. `dayu/fins/tools/preprocess_provider.py`
6. `dayu/fins/tools/upload_provider.py`
7. `dayu/host/wait_adapter.py`
8. `dayu/runtime/config_loader.py`
9. `dayu/service/entrypoint_runtime.py`
10. `dayu/service/fins_wait_adapter.py`
11. `dayu/service/host_assembly.py`

### 4.2 Tests / smoke

1. `tests/fins/test_fins_ingestion_tools.py`
2. `tests/host/test_open_host_runtime.py`
3. `tests/host/test_wait_adapter_polling.py`
4. `tests/host/test_wait_observation_runner.py`
5. `tests/host/test_wait_poller_runtime.py`
6. `tests/runtime/test_config_loader.py`
7. `tests/service/test_entrypoint_runtime_prompt_path.py`
8. `tests/service/test_fins_wait_adapter.py`
9. `tests/service/test_host_assembly.py`
10. `utils/smoke_host_public_awaiting_entrypoint.py`
11. `utils/smoke_host_public_r03_semantic_ownership.py`

### 4.3 README / artifact

1. `dayu/config/README.md`
2. `dayu/fins/README.md`
3. `dayu/host/README.md`
4. `dayu/service/README.md`
5. `tests/README.md`
6. `docs/reviews/wu-semantic-ownership-01-r04-s1-implementation-codex.md`

未修改 control/design、public Host API/open_host、Engine、prompt assets、execution profiles、callback transport、后续状态机或其它 deferred owner。相对 `f7006a80` 的历史 diff 还包含 accepted-plan/control/review ancestry；implementation allowlist 的判定基线是本 gate 指定的 clean `a4ffd764`。

## 5. Composition matrix owner-level 结果

| active modes / runtime | owner-level 结果 | 验证结果 |
|---|---|---|
| 无 active awaiting provider | activation/poll registry不创建，Host options 不携带 policy | tests + public smoke pass |
| 仅 manual | binding=`MANUAL`；activation存在；poll registry与Host policy不存在 | tests + public smoke pass；无后台 poller |
| 仅 poll，policy enabled | binding=`POLL`；poll registry非空；12字段一对一传入；Host启动 | tests + public smoke pass |
| poll + manual，policy enabled | activation含两者；poll registry仅含poll tool；manual不被claim/observe | owner composition tests pass |
| active poll，policy disabled | disabled policy仍一对一传入；Host不启动，不回退代码默认 | Host/Service tests + public smoke pass |
| active poll，policy enabled，registry缺失/空 | Service在`open_host`前 composition error | negative test pass |
| 任意 callback，单独或混合 | 所有 active callback 无条件走同一 owner 分支，在`open_host`前 fail-closed，不降级 | negative test + public smoke pass |
| callback + 伪 marker/普通 callable | 当前 Service/public contract 不存在 callback transport、marker、字段或 callable 输入位，因而不存在可绕过输入面；本行由上一行相同 owner 分支覆盖 | source-boundary audit + callback negative test pass |
| mode缺失/null/非字符串/空串/未知/大小写/空白变体 | Fins owner parser失败，不进入 composition | parameterized owner tests pass |
| recognized non-awaiting provider误用字段 | Service只检查字段存在，不读取 raw value；包含非字符串 opaque object 的用例仍按 misuse 失败 | negative test pass |
| unknown third-party provider携带 opaque config | 不读取、不解析、不发明新语义 | negative test pass |
| disabled provider，合法 mode | 先parse，后过滤；不创建binding，不影响poller | tests + public smoke pass |
| disabled provider，非法 mode | active filtering前由Fins parser失败 | negative test pass |
| scene all/select/none | 同一 provider/runtime owner inputs 得到相同 opener policy；scene只影响run exposure | comparison tests pass |

## 6. Tests、coverage 与静态验证

### 6.1 Accepted-plan affected pytest 单一 coverage session

按 plan §7 的完整 17 组 target，在同一个 `--cov=dayu` session 运行并输出 JSON：

```text
508 passed, 3 warnings in 21.46s
```

warnings 均来自既有第三方 edgar dependency 的 deprecation 提示，没有产品 failure、skip 或 xfail 被用来获得绿灯。coverage artifact：`workspace/tmp/r04-awaiting-provider-resolution-composition-coverage.json`。

### 6.2 每个修改 production Python 文件的精确 coverage

| production Python file | percent covered | gate |
|---|---:|---|
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.5421686746988% | pass |
| `dayu/fins/tools/download_provider.py` | 100.0% | pass |
| `dayu/fins/tools/preprocess_provider.py` | 100.0% | pass |
| `dayu/fins/tools/upload_provider.py` | 100.0% | pass |
| `dayu/host/wait_adapter.py` | 90.4054054054054% | pass |
| `dayu/runtime/config_loader.py` | 96.3126843657817% | pass |
| `dayu/service/entrypoint_runtime.py` | 88.2661996497373% | pass |
| `dayu/service/fins_wait_adapter.py` | 94.56521739130434% | pass |
| `dayu/service/host_assembly.py` | 95.02664298401422% | pass |

全部逐文件 `>=80%`；没有 coverage pragma、omit 或总覆盖率替代。

### 6.3 Type / lint / diff

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 对全部修改 Python/test/smoke 文件运行 `ruff check --select F401,F841`：`All checks passed!`。
- `git diff --check`：exit `0`，无输出。
- 对未跟踪的唯一 artifact 单独运行 `git diff --no-index --check /dev/null <artifact>`：无 whitespace error 输出；exit `1` 仅表示两端内容不同。

## 7. Source、propagation、security scans

| scan | result | classification |
|---|---|---|
| 旧 entrypoint policy helper、scene helper、`WaitPollerRuntimePolicy()` 无参构造 | exit `1`，零命中 | pass |
| Host/Service/runtime 十个旧部署默认常量 | exit `1`，零命中 | pass |
| `awaiting_resolution_mode` propagation | 命中仅位于 packaged config、Fins 唯一 parser/direct-provider调用、Service唯一 parse/presence boundary 与 owner tests | pass |
| prompt assets / execution profile 的 policy 或 mode 污染 | exit `1`，零命中 | pass |
| runtime 真实反向 import 语句 | 锚定 import 语句的 scan exit `1`，零命中 | pass |
| deferred-scope added-line scan | exit `1`，零命中 | pass |
| changed-files allowlist | 最终 28 个路径全部位于 §4.1 或唯一 artifact | pass |
| diff whitespace | tracked diff exit `0`；未跟踪 artifact 的独立 check 无 whitespace error | pass |

计划原样的 runtime reverse-import 正则命中 `dayu/runtime/__init__.py:15` 的架构说明文字；该行在 base `a4ffd764` 已存在，不是 import 语句或本次 diff。使用锚定 Python import 语句的等价 scan 后零命中。因此这是 scan 文本假阳性，不登记为产品或 baseline failure。

## 8. README trigger decision

先完整读取各 README 的 Agent 更新约束，再按职责更新：

| README | decision |
|---|---|
| `dayu/config/README.md` | 更新完整 required 12字段、数值/bool边界、packaged snapshot 与Fins mode配置contract |
| `dayu/host/README.md` | 更新config-owned显式policy与Host无deployment defaults/None fallback |
| `dayu/service/README.md` | 更新Service私有并行typed projection、raw config分离、typed composition与scene independence |
| `dayu/fins/README.md` | 更新provider-owned唯一parser、三模式及registry行为，不描述未来transport正向能力 |
| `tests/README.md` | 更新ConfigLoader/Fins/Service/Host矩阵和真实smoke边界 |
| 根 `README.md` | 不触发；用户入口、命令、工作流与排障面未变 |
| `dayu/README.md` | 不触发；既有分层关系未变，只纠正层内语义owner |

## 9. Packaged real assembly smoke

运行：

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r04-awaiting-provider-resolution-composition-smoke-final
```

结果：pass，约 7.4 秒。smoke 使用 packaged `ConfigLoader -> provider discovery -> Service composition -> public Host`：

- 输出 typed modes `poll/manual/callback` 与完整 12字段 runtime snapshot；未输出 secret 或 raw credential。
- interactive 与 prompt 均通过 `prepare_entrypoint_runtime` 进入同一 provider discovery/Service composition，opener decision一致。
- poll enabled 保留生产 Service 生成的 binding、registry与policy，public Host真正启动生产background poller；本地 deterministic tool/observation driver先产生 `not_ready`，放行后产生 `ready`，最终 public run由waiting进入`succeeded`。
- worker accept=`2`、not_ready=`1`、ready=`1`，outbox terminal事实与成功结果一致。
- manual、no-provider、provider-disabled、runtime-disabled 均通过public Host证明不启动poller；callback在public Host打开前失败。
- deterministic driver只替代会触发外部执行/观察的边界，不替代Service composition、Host opener、poller lifecycle或durable waiting路径；全过程未访问真实外部LLM或网络。

既有 `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py` 也包含在508-test session并通过。其外部live runner按本任务明确禁网约束未执行；R04本地真实assembly smoke已经覆盖本slice所需public路径。

## 10. Baseline failure 六项指纹

本 implementation 没有可登记 baseline failure，故六项指纹均不适用：

| command | test/node | error type | first stable frame/rule | text fingerprint | baseline SHA |
|---|---|---|---|---|---|
| N/A | N/A | N/A | N/A | N/A | N/A |

`508 passed`、full pyright与全部产品扫描没有失败。上节 runtime 文档文字命中是正则假阳性，既非执行失败也非产品失败，因此不伪造六项 inherited 记录。

## 11. Residual risks 与明确 deferred boundary

| residual / uncovered area | classification / owner |
|---|---|
| callback 正向 transport 尚不存在 | 既有 WU-WAIT-01 / #89 owner；R04正确行为是pre-open fail-closed，不造假实现 |
| deterministic smoke不访问真实外部LLM/网络 | 本任务显式要求；本地smoke已真实覆盖packaged config、discovery、Service composition与public Host/poller/durable waiting |
| Host重启后的跨进程observation恢复与后续timeout/LOST行为 | 后续既有owner；R04未改变状态机或扩大范围 |

没有未归属的当前 R04 residual，没有需要扩张 allowlist或改变owner的open question。

## 12. Completion signal

R04唯一原子S1已达到implementation-pass：实现、owner tests、完整affected pytest、逐文件coverage、full pyright、README、source/propagation/security scans和真实public assembly smoke均通过。确认未创建任何中间commit/checkpoint，未commit、push或创建PR。

本次在此停止，状态为 `READY_FOR_CONTROLLER_VALIDATION`；不进入code review、fix、accepted commit或后续sub-WU。
