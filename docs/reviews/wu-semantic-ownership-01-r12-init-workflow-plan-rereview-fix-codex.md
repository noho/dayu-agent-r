# WU-SEMANTIC-OWNERSHIP-01 / R12 fixed-plan re-review finding fix — AgentCodex

## 1. Gate 身份与结论

- 工作类型：同一 umbrella WU 内的 plan-only re-review finding fix；未进入 implementation。
- 唯一修改目标：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`。
- 唯一新增 artifact：本文。
- 结论：Controller 接受的 `R12-RR-PF-01..05` 已全部写回 plan；AgentDS `R12-RR-04` 继续按 Controller 裁决拒绝，不改动既有 README scope。
- Controller follow-up：已用 CURRENT/OLD direct evidence 纠正第一轮 fix 中不可执行的 runtime-assembly prewarm，改为 exact-two-root import-only contract。
- implementation authority：`NONE`。下一步只能进入 Controller fixed-plan re-review-fix follow-up validation；不得进入 implementation。

## 2. Immutable before 与 authority evidence

### 2.1 Immutable before plan

- 路径：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
- 行数：558
- 字节数：56,459
- SHA-256：`37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`
- 用户给定 metrics 与本轮 `wc -l -c` / `shasum -a 256` 机械结果完全一致；修改前已完整读取 558 行。

### 2.2 Corrected re-reviews 与 Controller adjudication

| Artifact | 行数 / 字节 | SHA-256 | 本轮用途 |
|---|---:|---|---|
| corrected AgentMiMo re-review | 249 / 17,394 | `a1812b6f7539ee252de27d01ad4a40382163dd7c5955cafe029720370f2aaac5` | 接受 resolved ModelsConfig 措辞/测试 finding |
| corrected AgentDS re-review | 469 / 35,432 | `f08584c337d910663003ab8be39c42371b8b1cd27e02b19d3f1a9640711e9381` | 五个 candidate 的直接来源 |
| Controller adjudication | 133 / 9,055 | `1f5142be9a4e5468625719be760e90e93e48d9093c633901849b65ff76bcadc9` | 五组接受、一个拒绝以及精确修复边界 |

三份 artifact 均在修改 plan 前完整读取。Controller 明确裁决 `PLAN_FIX_REQUIRED / 5 ACCEPTED GROUPS / ZERO BLOCKER`，因此本轮没有重新发明方案或扩大实现范围。

## 3. CURRENT 直接证据

### 3.1 ModelsConfig extends owner

- `dayu/runtime/config_loader.py` 的 `_resolve_record_map(...)` / `_resolve_record(...)` 是当前单继承解析 owner，`ConfigLoader` 输出的 `ModelsConfig.models` 已是 resolved typed records。
- package `models.json` 的 13 个 thinking IDs 都以 `extends` 继承 ordinary parent；raw thinking child 不重复写 `provider` / `api_key_ref`。
- 因此 before plan 的“两个 record 字段精确匹配”存在 raw/resolved 歧义；正确校验面必须是现有 resolver 产出的 resolved records，不能在 init catalog 再实现一份 extends parser。

### 3.2 13/3 manifest 与 Service discovery boundary

对 16 个 package manifests 的 current JSON 逐文件提取 `tool_selection` 与 required `context_slots`，结果为：

- 13 个 production runtime manifests：`audit`、`confirm`、`conversation_compaction`、`decision`、`fix`、`infer`、`interactive`、`overview`、`prompt`、`regenerate`、`repair`、`wechat`、`write`；它们使用 `none` 或真实 product tags。
- 三个 exact test manifests：`smoke_host_public_conversation_memory`、`smoke_host_public_conversation_memory_scenarios`、`smoke_host_public_multiturn`；三者均 `select` `manual-smoke` 且 `allow_empty=false`。
- 全部 required slot 的并集精确为 `current_time` 与 `fins_default_subject`。
- `ScenePrepareRequest.available_tools` 必填；`SceneToolCatalog.from_tool_bundle(...)` 是从真实 `ToolBundle` 投影 scene catalog 的现有 owner。
- `dayu/service/entrypoint_runtime.py` 的当前 production 路径先用 staging/current `RuntimeConfig.tool_discovery.providers` 调用 `assemble_effective_tool_provider_configs(...)`，再调用 `discover_service_tools(...)`，最后调用 `SceneToolCatalog.from_tool_bundle(...)`。
- 现有 runtime test fixture 明确拥有 `manual-smoke` fake tool；该事实只能留在 test-owned catalog，不能进入 production discovery。

### 3.3 Lock contention coordination

- `dayu/runtime/filelock.py` 的 public signature 是 `file_lock(..., timeout_seconds: float | None = None, ...)`；`None` 映射当前无限等待语义。
- before plan 已要求 CLI 显示 waiting workspace/lock path，但旧 smoke 描述没有规定如何观察到 queued process，存在 timing-luck 分支。
- Controller 已把该用户可见 waiting notification 裁为现成 public coordination point；test harness 只需 parent-held real lock、一个/两个真实 `Popen`、pipe read/process wait 的 bounded test timeout，不需要 production sentinel、sleep、retry 或 finite production timeout。

### 3.4 Environment 与 prewarm — Controller follow-up correction

- POSIX/Windows 全批持久化成功后才注入当前进程、partial failure 不注入/不 publish 的 contract 仍成立；它是 environment owner 的跨平台成功语义，不再作为 prewarm 输入理由。
- Controller 完整读取后发现 CURRENT direct contradiction：`prepare_entrypoint_runtime` 会进入 `compose_open_host_options`；ordinary selection 可消费 scene model hints / ordinary override，但 compactor selection 唯一读取 `execution_profile.compactor_baseline.model_id`，不消费 scene hints 或 run override。
- current `ServiceAssemblyOverrides` 只有 `model_id` / `runner_option_hint_id` ordinary overrides，没有 compactor override；`execution_profiles.json` 四个 profiles 的 `compactor_baseline.model_id` 全部精确为 `deepseek-v4-flash`。
- 因此非 DeepSeek selected model pair 下，单一 selected-pair env mapping 必然无法同时满足 compactor header resolution。R12 又无权改 `execution_profiles.json`、Service 或 Host，不能用 optional/full environment 或额外 inferred ref 掩盖 owner contradiction。
- OLD SHA-locked `_run_init_prewarm` 只循环 `importlib.import_module(...)`，不调用 runtime assembly；正确 follow-up 是恢复这个 import-only semantic，使 prewarm 无 secret/env 需求。

### 3.5 Slice-local coverage 可执行性

- before workspace 中只有 `tests/cli/test_init_command.py` 与 `tests/cli/test_arg_parsing.py`；`test_init_catalog.py`、`test_init_environment.py`、`test_init_workspace.py`、`test_init_smoke.py` 均尚不存在。
- S1 计划新增前两个 owner tests，S2 才新增 workspace test 并修改现有 command/arg tests，S3 才新增 smoke。
- before §9.1 的 `commands/init.py` coverage 命令直接包含 S3 `test_init_smoke.py`，不能作为 S2 gate 执行；AGENTS.md 又要求每次修改当下即满足逐文件 `>=80%`，不能延期到 S3。

### 3.6 Rejected README candidate

- current `dayu/config/README.md` 开头明确拥有 package defaults、workspace config overlay 与 `dayu-cli init` 旧行为，并记录“已有文件默认失败 / `--overwrite` 替换”。
- R12 正在改变的正是该手册已拥有的用户可见 config lifecycle。Controller 因此正确拒绝把 README trigger 当成排他授权列表；本轮保留 S3 的 `dayu/config/README.md` scope，不新增理由分支或产品决策。

## 4. 五组 before → after 修复证据

### `R12-RR-PF-01` — resolved ModelsConfig truth

- Before：§4.1 写“两个 record 的 provider/api_key_ref 精确匹配”，可能被实现为 raw child field check；S1 测试也未要求继承成功与 resolved mismatch 失败。
- After：§4.1 明确 ordinary/thinking 两个 ID 只通过当前 `ConfigLoader` / `ModelsConfig` extends resolver 得到 resolved records 后比较；禁止 duplicate resolver。S1 测试新增 raw thinking child 仅写 extends 的成功例，以及 parent/child override 造成 resolved mismatch 的拒绝例。

### `R12-RR-PF-02` — exact real/test catalog boundary

- Before：§6.4 要求 16 个 manifests 全部 `prepare_scene`，却没有提供必填 `SceneToolCatalog` 和 context slots 的 owner 路径；空 catalog 会错误拒绝 tag-select manifests，synthetic product catalog 又会污染 production truth。
- After：§4.3 锁定 13 个 runtime / 三个 manual-smoke basename；§6.4 用真实 staging `RuntimeConfig`、既有 Service effective discovery、`SceneToolCatalog.from_tool_bundle(...)` 和两个锁定空 slot 装配 13 个 runtime manifests。三个 smoke 只用 test-owned explicit `manual-smoke` fixture 调用同一 current parser。全部 16 个 model projection 继续验证；空/合成 production catalog、synthetic provider、duplicate parser、跳过 tag selection、放宽 `allow_empty` 均被禁止；集合/tag/slot drift 是 Controller stop condition。

### `R12-RR-PF-03` — observable real-lock smoke

- Before：S3 只说“父进程持锁、子进程不发布、释放后成功”，缺少无 timing luck 的协调协议。
- After：§6.3 把既有 waiting notification 提升为 acquire 前必须输出的 public behavior；S3 分别规定 parent-held real lock + 一个真实 `Popen` 与 parent-held real lock + 两个真实 `Popen`。Harness 对每个 process 等待 public notification、确认零 publish 后才释放；bounded timeout 只用于 test fail-fast，production `timeout_seconds=None` 不变。显式禁止 sleep、flaky、成功率/retry、finite production timeout、process-kill 协调、production sentinel 和 test shim。

### `R12-RR-PF-04` — current-process visibility；prewarm 部分由 Controller follow-up 纠正

- Before：POSIX 成功后没有保证新值可供当前进程；prewarm contract 又错误进入需要 model secret 的 full runtime assembly。
- Corrected after：POSIX profile 和 Windows 全批持久化仍只有在全部成功后才注入当前 `os.environ`；partial failure 不注入、不 publish。§7 prewarm 完全不接受或读取 env/selection/secret，不构造 env mapping，不解析 ordinary/compactor refs，也不调用 assembly；optional/full env 均与 prewarm 无关。

### `R12-RR-PF-05` — every slice has executable per-file coverage

- Before：只有一个 final coverage block；`commands/init.py` 命令引用 S3 才存在的 smoke，S1/S2 没有自己的逐文件强制命令。
- After：S1 有两个当时存在测试驱动的逐文件命令；S2 累积五个逐文件命令且 `commands/init.py` 只引用 `test_init_command.py`；S3 重新运行累积五文件 final profile 并允许 command coverage 加入 smoke。三个 review gates 都要求各文件 `>=80%`，明确禁止把早期失败延期或追认到后续 slice。

## 5. 保留边界与 scope

### 5.1 保留的 rejected/no-fix boundary

- AgentDS `R12-RR-04` 继续拒绝；`dayu/config/README.md` 仍在 S3 allowlist，且只更新其已拥有的 current config/init lifecycle。
- 不清理或重分类 144 个历史 Ruff findings。
- 不固定 staging/backup 名称或 prefix 为 public protocol。
- 不引入 finite production lock timeout、Host lock/process discovery/kill、flaky/retry/sleep coordination。
- 不为 import-only prewarm 发明 lifecycle/cache/preload framework。
- 不引入空/合成 production tool catalog、manual-smoke product provider、duplicate parser、loose parsing、compat/fallback/shim、`hasattr/getattr` 补偿。

### 5.2 保留的 no-scope/security/deferred boundary

- Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 均保持 §1.3 的 no-scope。
- Secret value 仍不得进入 workspace、日志、异常、artifact、captured output 或 LLM-facing text；Windows partial `setx` 仍只报告 env names。
- managed roots 仍只有 `.dayu` / `config`；`assets` / `portfolio` 不被 reset 接管。
- active Host writer、multi-root 非单 syscall 原子、post-boundary cleanup warning、profile marker 损坏与 exact Ruff baseline 均保留原 owner / residual risk；prewarm 不再拥有本地 runtime/portfolio 初始化语义。

### 5.3 实际 workspace scope

- 本轮所有 write 都通过 path-specific patch 完成，只触碰 plan 与本文。
- 未修改 control、corrected rereviews、Controller adjudication、其它既有 artifacts、production、tests、README、design/workflow。
- 未 stage、未 commit。
- 工作区起始即存在的 `docs/host/issues-implementation-control.md` 修改和其它 R12 untracked artifacts 均视为用户/Controller 既有状态，本轮未覆盖。

## 6. After evidence 与验证

### 6.1 第一轮 fix 输出 / 本次 follow-up immutable before plan

- 行数：596
- 字节数：68,137
- SHA-256：`4982cb476d5346559540a73bc245fabd0878cddd173cac1c8a7072c9249ca830`
- 该 metrics 在 plan 内容关闭后由 `wc -l -c` / `shasum -a 256` 机械计算；完整 SHA 未写回 plan 自身。

### 6.2 已执行/终态验证 contract

```text
git diff --no-index --check /dev/null <plan>       -> exit 1, 无 whitespace 诊断（新增 diff 的预期状态）
git diff --check                                  -> exit 0, 无诊断
git diff --cached --name-only                     -> 空；staged empty
```

该轮本文关闭后已完成两文件 no-index、workspace diffcheck、staged-empty 与 metrics；随后 Controller 完整读取并提出本 follow-up。Plan-only 文档变更不运行 production tests、coverage、pyright 或 Ruff，避免越过用户禁止的 implementation gate。

## 7. 残余风险与下一 gate

- 本轮只消除了 plan ambiguity，没有实现或执行 R12；所有 implementation fault、跨平台 smoke 与 coverage 结果仍待各 cumulative slice 自己证明。
- `manual-smoke` 仍是 test-owned fact；若 package 13/3 manifests、tags 或两个 slots 漂移，必须停交 Controller，不能扩大 production catalog。
- Import-only roots/transitive graph 若开始需要 secret/network/Dayu runtime state，必须停交 Controller；不得恢复 runtime assembly、扩大 env 或新增 lifecycle/cache framework。
- Windows 多项 `setx` 仍无跨调用回滚；multi-root publish 仍靠逐 root rename + rollback；`.dayu-init.lock` 仍不排除 active Host writer。这些是已分类、owner 明确的既有 residuals。
- 下一 gate：本 follow-up 完成后停回 Controller fixed-plan re-review-fix follow-up validation，不进入 implementation。

## 8. Controller follow-up immutable before 与 root-cause evidence

### 8.1 本 follow-up immutable before

| 文件 | 行数 / 字节 | SHA-256 |
|---|---:|---|
| plan | 596 / 68,137 | `4982cb476d5346559540a73bc245fabd0878cddd173cac1c8a7072c9249ca830` |
| 本 artifact | 151 / 13,304 | `defefb9f0fc5cba4cf14cc39f42ad068afe484798b663d027aac9ddafc2c65fd` |

两文件在 follow-up 修改前已保持上述 first-fix 终态。Controller 只授权继续修改这两个文件。

### 8.2 CURRENT ordinary/compactor contradiction

- `dayu/service/host_assembly.py` SHA-256 `54559d2ea0446316b4ff82bf66594dfaa5d7b75067d495f5d3558d2ea94bbe52`：ordinary `select_runner_option_hint(...)` 接收 `scene_model_hints` 与 ordinary run override；compactor 调用显式传 `scene_model_hints=None` / `run_override=None`，model ID 只来自 `execution_profile.compactor_baseline.model_id`。
- `ServiceAssemblyOverrides` 精确字段只有 `host_runtime_id`、`execution_profile_id`、ordinary `model_id`、ordinary `runner_option_hint_id`；没有 compactor override。
- `dayu/config/execution_profiles.json` SHA-256 `ca827749876c29be8dc1808219a4082cfe06ebf7930939f30d2d6cf2a9340a31`：`standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m` 四个 profiles 的 run/compactor baseline model IDs 全部为 `deepseek-v4-flash`。
- 结论：第一轮 fix 让 prewarm 用 selected-pair-only env 进入 full assembly，在非 DeepSeek choice 下会确定性缺少 compactor 的 `DEEPSEEK_API_KEY`。扩大到 optional/full env、推断第二个 ref 或改 execution profile 都会越过 R12 owner boundary，不能作为修复。

### 8.3 OLD import-only truth 与 CURRENT exact roots

- OLD init SHA-256 `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e`：`_run_init_prewarm` 删除未使用的 workspace/config 参数后，只遍历 `_PREWARM_MODULES` 调用 `importlib.import_module`，捕获异常并返回；没有业务调用或 assembly。
- OLD tuple 中 `dayu.cli.dependency_setup`、`dayu.cli.interactive_ui`、`dayu.cli.commands.write` 在 CURRENT 均不存在；不得迁回或用 placeholder 代替。
- CURRENT `dayu.cli.commands.interactive`（SHA `6246eb5725fc60d11a5ce7ac0c4487db7a430dad03dc70d79843b47fdc33bbbc`）与 `dayu.cli.commands.prompt`（SHA `d3cdc4ea796126eb9ce367c728a35b253ea90441d032c8dc0500049d90a7e5c4`）是仅存真实用户入口 roots。按 OLD tuple 过滤后的稳定顺序是 interactive → prompt。
- 两个 command modules 都直接 import `dayu.cli.session_execution`（SHA `84fa0647672bef0aab0dd8fa649370e4d0d337678553e48657b2c1d01f82225a`）；该 module 直接 import `dayu.service.entrypoint_runtime`（SHA `014c5ea0cf16d3538793883277672d70764d5a812054028369c98c229c0115c6`）。这条 transitive graph 由真实模块自己拥有，init 不能复制成第二份列表。
- 最小 contract 因此只有 explicit roots `("dayu.cli.commands.interactive", "dayu.cli.commands.prompt")` 与标准 `importlib.import_module`。共享 assembly modules 只被正常 import，不调用函数、不实例化 request/result、不访问 env/secret/workspace。

## 9. Controller follow-up after evidence

### 9.1 After plan

- 行数：608
- 字节数：71,044
- SHA-256：`69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`
- §7、S3、tests、source scans、risks、stop conditions、implementation report 与 gate provenance 已同步到同一个 import-only truth。

### 9.2 删除的错误语义

- 删除 `prepare_entrypoint_runtime` prompt/interactive assembly、`asyncio.run`、HostAdmin、Fins registry 调用要求。
- 删除 prewarm selected-pair env mapping、resolved ordinary/compactor refs 必须一致及其 drift/fallback 分支。
- 删除 preparation result closable speculation、prewarm 本地 runtime/portfolio side-effect ownership。
- `prepare_entrypoint_runtime` / Host/Service/Fins names 只允许出现在 production source scan 的禁止模式或 contradiction evidence，不再是计划调用。

### 9.3 新的唯一 prewarm contract 与 tests

- 唯一 owner：`commands/init.py` 的 private immutable exact-root tuple 与 private sync helper；transitive graph 仍归真实 modules。
- Helper 无参数，只依次 `importlib.import_module` exact roots；不接受 workspace/config/env/selection，不调用任何 runtime function，不新增 lifecycle/cache framework。
- 仍只在 FIRST/RESET publication 后执行；PRESERVE/OVERWRITE 零次；失败 warning 不回滚。
- 隔离 subprocess 以 `PYTHONDONTWRITEBYTECODE=1`、network fail-fast、workspace tree hash、environment snapshot 证明零网络、零 secret、零 Dayu runtime/workspace/profile/env mutation；连续两次稳定并验证 transitive modules loaded、deleted roots absent。
- `portfolio` / `assets` sentinel 只保留为独立 reset boundary，不再解释为 prewarm side effect。

### 9.4 Scope、验证与残余风险

- Follow-up 只修改 plan 与本文；未改 control、其它 reviews/artifacts、production、tests、README、design/workflow，未 stage/commit。
- 当前 `dayu.cli.main` 可能已通过正常 runner registration 加载相同 roots，因此 contract 只承诺 OLD-aligned import availability/stability，不承诺跨进程性能收益；不为此新增 persistent cache。
- 若 roots/transitive graph 漂移并开始需要 secret/network/Dayu runtime state，必须停回 Controller；不得恢复 full assembly 或扩大 env/module list。
- 本文关闭后重算自身 metrics/SHA，并对 plan/本文分别运行 no-index whitespace check，再运行 workspace `git diff --check` 与 staged-empty；终态输出随 Controller handoff 报告。
- 下一 gate：`Controller fixed-plan re-review-fix follow-up validation`；禁止进入 implementation。
