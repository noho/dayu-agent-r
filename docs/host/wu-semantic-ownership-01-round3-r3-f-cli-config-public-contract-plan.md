# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-F CLI / Config / Public Contract Plan

## Gate 与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-F`
- 类型：生产安全、公共契约与发布门修复
- 当前 gate：AgentCodex `plan -> implementation -> fix`
- 风险级别：`production-high`
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`
- 控制真源：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`
- accepted finding 真源：`docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`
- 实现产物：`docs/reviews/wu-semantic-ownership-01-round3-r3-f-implementation-codex.md`

本计划只覆盖 R3-F。不会修改 R3-A Host lifecycle / runner-call hot payload、R3-B Engine provider、R3-C Fins storage / download / upload、R3-D financial/read semantics、R3-E Web/Documents，也不会 commit、push、创建 PR 或进入 review gate。

## 目标、动机与成功信号

目标是让 CLI、配置、包依赖、用户文档和层中立数值边界重新由各自 owner 产生并承诺唯一语义，同时恢复默认发布验证门。

成功信号：

1. `dayu-cli init` 的普通复制、覆盖和 reset 路径都不会沿 workspace 内 symlink 写出或删出工作区；失败发生在任何外部写入前。
2. Python 3.11 安装依赖不会再组合出 `torch==2.2.2` 与 Transformers 5.x 的已知不可运行 Docling 环境。
3. `interactive --ticker` 与 `session resume --mode interactive --ticker` 通过 Service 的 shared scene-context owner 生成 `fins_default_subject`，最终进入 LLM-facing system prompt。
4. `upload_filings_from` 输出结构化 argv JSON，不再产生需要 shell dialect 解释的命令文本。
5. parser、help、根 README 只描述当前真实可用命令和参数；旧 `write`、`--new-session`、必然被拒绝的旧 Agent flags、`--infer` / `--ci` 不再作为可用能力出现。
6. JSON 配置与 runtime timeout / interval / TTL / filelock / lane 边界拒绝 NaN、正负无穷和不符合各自范围的数值。
7. 默认 pytest 中 R3-F 的 contracts whitelist 与 audit preview fixture 恢复通过；全量 pyright 和 `git diff --check` 通过。已知 runner-call stress 失败只记录为 R3-A dependency。

## 第一性原理核验与 finding 裁决

| Finding | 当前直接证据 | 语义 owner 与裁决 |
|---|---|---|
| DR-005 | `dayu/cli/commands/init.py::_copy_current_config_assets()` 只检查冲突后直接 `mkdir/copy2/os.replace`；普通路径没有 reset 已有的 containment/symlink 检查。`workspace/config` 指向外部目录时所有目标路径都随链接解析。 | `accepted`。owner 是 init 的整棵写入目标，而不是某一次 `_copy_file_atomic()` 调用。使用统一 destination guard、私有 staging tree 与顶层安装边界；reset 复用同一 containment/symlink 规则。 |
| DR-018 | `constraints/min-py311.txt` 同时锁 `torch==2.2.2` 与 `transformers==5.5.4`；macOS x64 lock 已因同一冲突降到 Transformers 4.57.6。 | `accepted`。owner 是 package metadata + platform/minimum locks。把 Docling 所需 Transformers 明确限制在已验证的 4.57.6+、5.0 以下，并统一 locks；不在 Docling 调用点伪装兼容。 |
| DR-026 | `interactive.py` 把 ticker 传给 invocation metadata，却只构造 `current_time` slot；interactive manifest 也只声明该 slot。`prompt.py` 已通过 `build_entrypoint_context_slot_values()` 走唯一 Service owner。 | `accepted`。interactive 与 resume 复用 `EntrypointContextSlotRequest`，manifest / scene 同时声明并渲染 subject slot；metadata 不再充当 LLM context 替代品。 |
| DR-027 | `fins.py::_render_upload_batch_command()` 无条件使用 `shlex.join()`；Windows cmd 不解释 POSIX 单引号。 | `accepted`。公共输出改为 `schema_version=1`、`commands=[argv, ...]` 的 JSON；参数边界由 JSON array 保留，不存在 Bash/cmd quoting owner。 |
| DR-028 | parser 明确排除 `write` / `--new-session`，但 README 仍承诺；多个旧 Agent flags、Fins `--infer` / `--ci` 被 parser 暴露后又由 runner 必然拒绝；init、interactive session 与 batch upload 文档也和代码相反。 | `accepted`。删除旧 parser surface 和下游 unsupported shim，README 只保留当前行为，不实现旧文档承诺。 |
| DR-030 | `json.loads` 默认接受 `NaN/Infinity`；ConfigLoader 多数 float helper 只比较大小；`RuntimeFileLockOptions`、`LaneConfig`、lane acquire timeout、cancellation wait 和 process wait 只做符号比较或不校验。 | `accepted`，收窄到 R3-F 的 config loader、`dayu.runtime` 与本轮 Service entrypoint 数值边界。新增层中立 finite-number predicate 真源；JSON parse boundary 同时拒绝非标准常量和 float overflow。Engine provider 专属 retry 语义不在本 sub WU 修改。 |
| DR-037 / contracts | 当前命令稳定复现 `dayu.contracts.__all__` 比测试 whitelist 多 `AgentFallbackMode`、`AGENT_FALLBACK_MODES`；生产包 docstring 与导出表已明确二者是当前公共契约。 | `accepted`。更新测试 owner contract，不删除生产导出，也不加兼容分支。 |
| DR-037 / audit fixture | 当前命令稳定复现测试写入未注册的 `PREVIEW_DELTA`，被 EventLog owner 正确拒绝。 | `accepted`。fixture 使用 `HostPreviewEventType.REASONING_DELTA` 的生产真源，不放宽 EventLog。 |
| DR-037 / filelock pyright | 当前 venv pyright 1.1.409 对全仓与单文件均为 0 error；“当前红”证据已失效。第三方 `FileLock` 是运行期平台别名，而 `BaseFileLock` 是稳定基类。 | 当前红项为 `rejected-with-reason`；`BaseFileLock` 属性/构造参数类型收窄作为同 owner 类型边界修正 `accepted`，由全量 pyright 验证。 |
| DR-037 / stress | controller 已将 runner-call hot payload stress 失败分配给 R3-A。 | `deferred-with-owner`：R3-A。R3-F 不改 Host runner-call payload；显式 stress 若仍失败只记录 dependency。 |
| MiMo config overlay | `_overlay_roots()` 的 map 按 id 合并、同 id record 整条替换和非 map 覆盖已经由测试与 `dayu/config/README.md` 明确承诺；唯一 object 型非 map `coordinator` 缺字段时 typed parser 会显式失败。 | `rejected-with-reason`。没有静默成功/数据丢失路径；改成 implicit deep merge 反而破坏显式 `extends` owner。补文档澄清 complete-replacement 语义即可。 |
| MiMo/DS SIGINT duplication | `_FinsSigintMonitor` 与 `CliSigintMonitor` 字段、安装、关闭、计数和等待逻辑逐行等价。 | `accepted`，与本轮 CLI owner 同改闭环：删除私有复制，Fins direct path 复用共享 monitor。 |
| DS temp log cleanup | 每次未传 `--log-file` 的真实命令都会 `mkstemp`，关闭后文件永久保留；CLI 不输出该精确路径，用户无法利用这些文件排障。 | `accepted`。默认日志改为 close 时自动删除的进程内临时流；需要持久日志必须显式传 `--log-file`。 |
| MiMo/DS parser/doc mismatch | 当前 help、runner 拒绝分支与 README 可复现相互冲突。 | `accepted`，并入 DR-028 同一 public-contract closure。 |

## 设计对齐与所有权

- `docs/host/design.md` §3 把 `dayu.runtime` 定义为层中立公共运行期能力；finite-number predicate 放在这里，不能承载 Host lifecycle 或业务状态。
- `docs/host/design.md` §23 / §24.6 要求 runner-call 输入由准备后的 scene/system message 真源产生。ticker 必须通过 scene context slot 进入 system prompt，不能只留在 CLI/Host metadata。
- `docs/engine/design.md` 的 Engine / Runner 边界保持不变；R3-F 不修改 provider parsing、retry state machine 或 Engine event contract。
- CLI 仍是 UI adapter，Service 的 `scene_context` 仍是 entrypoint LLM-facing subject 文本唯一 owner；Fins batch planner 仍只产生结构化 plan entry，CLI 只负责 public argv projection。
- ConfigLoader 仍承诺顶层 map 合并、record 完整替换和显式单继承；本轮只强化 JSON/number validation，不引入 deep merge 或 compatibility alias。

## 公共契约变更

### Init destination contract

- workspace root 必须是已解析的真实目录。
- `config` 及其已存在后代不得包含 symlink；检测到 symlink、containment 逃逸或非目录 parent 时，init 在复制前失败。
- 当前配置树先复制到 workspace 内私有 staging tree，再把包内资产覆盖到 staging；`--overwrite` 保留非生成文件，但替换当前生成资产。
- staging 完成后在 workspace 顶层安装；已有 config 先移到私有 backup，安装失败时回滚。清理 staging / backup 时不得跟随 symlink。
- reset whitelist 在批量删除前和每次删除前都执行同一 workspace containment / symlink 校验。

### Upload batch JSON contract

stdout 或 `--output` 文件固定输出：

```json
{
  "schema_version": 1,
  "commands": [
    ["dayu-cli", "upload_filing", "--ticker", "AAPL", "--files", "/path/report.pdf"]
  ]
}
```

每个 `commands` item 是可直接传给 process API 的 argv array；不承诺 shell script、扩展名、header、额外参数转发或任何 shell dialect。

### Finite-number contract

- shared predicate 只判断严格数值是否 finite / positive finite / non-negative finite；各 owner 继续产生自己的领域错误类型与字段名。
- ConfigLoader 的 JSON decoder 拒绝 `NaN`、`Infinity`、`-Infinity` 和溢出为 infinity 的 float literal；所有 typed float fields 额外做 finite 防御。
- timeout `None` 的既有“无限等待”语义不变；显式 timeout 必须 finite 且非负，正 interval / TTL / heartbeat / busy timeout 必须 finite 且大于零。
- `0` 仍只在原 contract 已允许 non-blocking / immediate timeout 的入口保留。

## 影响文件与模块

预计允许修改：

- 生产：`dayu/cli/commands/init.py`、`dayu/cli/commands/interactive.py`、`dayu/cli/commands/session.py`、`dayu/cli/commands/fins.py`、`dayu/cli/agent_entrypoint.py`、`dayu/cli/session_execution.py`、`dayu/cli/arg_parsing.py`、`dayu/cli/main.py`、`dayu/runtime/numeric.py`、`dayu/runtime/config_loader.py`、`dayu/runtime/cancellation.py`、`dayu/runtime/filelock.py`、`dayu/runtime/lane.py`、`dayu/runtime/interruptible_process.py`、相邻 runtime/Service finite validator consumer、interactive prompt manifest / scene。
- packaging：`pyproject.toml`、`constraints/min-py311.txt`、四个平台 Python 3.11 lock 文件。
- 测试：对应 `tests/cli/`、`tests/runtime/`、`tests/contracts/test_package_exports.py`、`tests/host/test_audit_sink.py`、必要的 package/import boundary 测试。
- 文档：根 `README.md`、`dayu/config/README.md`、`tests/README.md`、本 plan 与 implementation artifact。

禁止修改 R3-A～R3-E owner 文件来顺手关闭其它 finding；若验证暴露这些区域失败，只分类 residual。

## Implementation slices

本轮采用 3 个 slices，符合 control doc 的小型跨模块 cleanup 上限。拆分依据分别是 filesystem authority、CLI/public projection、runtime numeric/release validation，三者有不同 failure blast radius 和验证矩阵；不是按文件或 finding 数切分。用户已授权 plan 后直接实现，因此 AgentCodex 可在同一 implementation pass 中按 S1 -> S2 -> S3 连续完成，并用一个 implementation artifact 汇总。

### S1 - Init Write Destination Safety

- Objective：把 normal/overwrite/reset 的工作区路径安全收敛到 init destination owner。
- Allowed changes：`dayu/cli/commands/init.py`、`tests/cli/test_init_command.py`，以及最终 docs/test docs 同步。
- Exact behavior：实现 staging/install/rollback；拒绝顶层、生成目标和中间目录 symlink；覆盖 normal、overwrite、intermediate symlink、destination symlink、reset preflight 和零外部写入断言。
- Non-goal：不实现配置 wizard、migration、secret 写入，不扩大 reset whitelist。
- Completion：focused init tests 全绿，复现外部目录保持空或原内容不变。

### S2 - CLI Scene / Batch / Packaging / Public Documentation

- Objective：关闭 ticker scene context、shell quoting、旧 parser surface、临时日志、SIGINT duplication、Docling dependency 和 README truth drift。
- Allowed changes：上述 CLI / Service scene files、interactive prompt assets、packaging/constraints、CLI/package tests、根与 config README。
- Exact behavior：interactive 复用 shared slot builder；batch 输出 argv JSON；删除必然拒绝的 parser flags 与 unsupported shim；Fins 复用 `CliSigintMonitor`；默认日志自动删除；package metadata 限制 Transformers 4.x；README 删除旧承诺。
- Non-goal：不实现 write/new-session/web-provider/infer/ci，不执行 batch commands，不增加 Bash/cmd renderer，不修改 Fins ingestion/storage。
- Completion：CLI/scene/package/README contract tests 全绿，特殊字符路径在 JSON 中保持单个 argv item。

### S3 - Config / Runtime Finite Numbers And Release Gate

- Objective：建立层中立 finite predicate，补齐 config/runtime public boundaries，并修复当前默认测试红项。
- Allowed changes：`dayu/runtime` 数值 consumer、同轮触及的 Service finite consumer、对应 runtime tests、contracts export test、audit fixture、tests README。
- Exact behavior：strict JSON decoder；finite/range validation；BaseFileLock 稳定类型；当前 exports whitelist；registered preview type fixture。
- Non-goal：不修改 Engine provider retry、Host runner-call payload、Host lifecycle/state machine 或 stress expectation。
- Completion：focused runtime/contracts/audit tests、默认 pytest、全量 pyright、diff check 达到预期；stress failure 若存在明确归属 R3-A。

## 测试与验证

实现中先按 slice 运行：

```bash
source .venv/bin/activate
pytest tests/cli/test_init_command.py -q
pytest tests/cli/test_arg_parsing.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py tests/cli/test_public_package_entrypoints.py -q
pytest tests/runtime/test_numeric.py tests/runtime/test_config_loader.py tests/runtime/test_cancellation.py tests/runtime/test_filelock.py tests/runtime/test_lane.py tests/runtime/test_interruptible_process.py tests/runtime/test_import_boundary.py -q
pytest tests/contracts/test_package_exports.py tests/host/test_audit_sink.py -q
```

最终必须运行：

```bash
source .venv/bin/activate
pytest -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

为记录已知 dependency，可显式运行：

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

stress 的 runner-call payload failure 不在 R3-F 修复，implementation artifact 必须记录为 `assigned to later work unit: R3-A`。

## README 决策

- 根 `README.md`：必须更新。CLI 安装/init/命令/参数/日志/interactive/upload batch 的用户可见 contract 均变化或被纠正；删除未实现 `write` 与旧 flags，不补实现。
- `dayu/config/README.md`：必须更新。interactive required subject slot、strict finite JSON 和 overlay complete-replacement 语义属于其读者范围。
- `tests/README.md`：必须更新。CLI batch JSON、ephemeral default log、parser deletion、init symlink、runtime finite 和 release-gate tests 改变当前测试事实。
- `dayu/README.md`：不更新。分层关系、装配方向和包职责未改变；finite predicate 只是既有 `dayu.runtime` 职责内的基础能力。
- Host / Engine / Fins README：不更新；本轮不修改其生产 owner contract。

## 风险、开放问题与不过度设计说明

无 blocking open question。

主要风险：

- directory swap 在不同平台上的失败/回滚行为不同；测试必须覆盖 normal、overwrite 和 rollback，不承诺跨进程事务锁。
- batch 输出从 shell 文本变为 JSON 是明确 breaking public-contract change；按项目“全新设计、无兼容 wrapper”执行。
- 全量 README 删除旧能力可能暴露其它历史描述；只修有当前 parser/behavior 直接证据的段落，不重写全仓文档风格。
- full stress 仍可能因 R3-A hot payload 失败；不得在 R3-F 下调断言或增加 Host fallback。

方案没有引入新的 Host/Engine/Fins abstraction、schema migration、shell dialect framework 或兼容层。共享 finite predicate、staging destination owner 和 structured argv 是关闭当前真实失败路径所需的最小稳定边界。

## Completion report format

implementation artifact 与最终报告必须列出：

1. changed files；
2. 每个 accepted / rejected / deferred finding 的最终状态；
3. 验证命令、通过数或失败详情；
4. README 更新/no-update 决策；
5. propagation audit；
6. residual risks、owner 与 destination；
7. 明确停止在 R3-F implementation/validation artifact，不 commit、push、PR、merge。
