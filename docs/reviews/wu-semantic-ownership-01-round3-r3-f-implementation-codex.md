# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-F Implementation — AgentCodex

## 结论

R3-F 的 plan、implementation、fix 与验证已完成。本轮只修改 CLI / Config /
Packaging / Public Documentation / Runtime Numeric Contracts 及其测试，没有进入
R3-A～R3-E，没有修改 Host lifecycle、Engine provider、Fins storage/read、Web 或
Documents owner，也没有 commit、push、创建 PR 或 merge。

计划真源：
`docs/host/wu-semantic-ownership-01-round3-r3-f-cli-config-public-contract-plan.md`。

## 第一性原理复核与最终裁决

| Finding | 最终状态 | 直接证据与处理 |
|---|---|---|
| DR-005 init symlink write escape | `fixed` | 普通复制路径原先会沿 `workspace/config` symlink 写入外部目录。init 现在由统一 destination guard 校验 lexical/resolved containment 与现存树 symlink，先在 workspace 私有 staging tree 完成复制，再做顶层安装；已有 config 先移入私有 backup，安装失败恢复旧树。normal、overwrite、嵌套 symlink、reset fail-fast、用户自管文件保留和 rollback 均有 owner 级测试。 |
| DR-018 Python 3.11 / Docling dependency | `fixed` | 最低约束原先组合 `torch==2.2.2` 与 `transformers==5.5.4`，而已有 macOS x64 lock 已承认该组合不可运行。package metadata 现在显式约束 `transformers>=4.57.6,<5.0.0`；minimum 与四个平台 Python 3.11 locks 统一为 `transformers==4.57.6`、`huggingface_hub==0.36.2`。未在 Docling 调用点增加伪兼容 gate。 |
| DR-026 interactive ticker context | `fixed` | `interactive` 与 `session resume --mode interactive` 现在和 `prompt` 一样调用 `dayu.service.scene_context.build_entrypoint_context_slot_values()`；interactive manifest 声明并在 scene contract 后渲染 required `fins_default_subject`。ticker 不再只存在于 invocation metadata。 |
| DR-027 Windows-unsafe upload batch text | `fixed` | 删除 POSIX `shlex.join()` command renderer。stdout / `--output` 固定输出 `{schema_version: 1, commands: [[argv...]]}` JSON；包含空格、引号、`&`、`%` 的路径保持单个 argv item，不再承诺 Bash/cmd dialect。 |
| DR-028 README / CLI drift | `fixed` | 删除 parser 中必然被下游拒绝的旧 Agent flags、Fins `--infer` / `--ci` 与对应 unsupported shim；根 README 按实际 help/runner 重写，不实现历史 `write`、init wizard、`--new-session` 或 shell batch 承诺。新增 README public-contract smoke。 |
| DR-030 non-finite numeric boundaries | `fixed` | 新增层中立 `dayu.runtime.numeric` 真源。ConfigLoader JSON decoder 在 parse boundary 拒绝 `NaN`、`±Infinity` 和 `1e400`；typed float、runtime assembly、Service override、cancellation timeout/poll、lane timeout/TTL/heartbeat/busy wait、filelock timeout、process wait/grace 都复用 finite/range predicate，并保留各 owner 的错误类型。 |
| DR-037 contracts whitelist | `fixed` | 测试 whitelist 纳入生产包已公开并记录的 `AgentFallbackMode` / `AGENT_FALLBACK_MODES`，不删除生产契约。 |
| DR-037 audit preview fixture | `fixed` | fixture 改用 `HostPreviewEventType.REASONING_DELTA` 与 `serialize_host_event_type()`；未放宽 EventLog event-type registry。 |
| DR-037 filelock pyright | `rejected-with-reason` + type correction | baseline 的单文件与全仓 pyright 已是 0 error，因此“当前红”证据失效；同 owner 将平台别名 `FileLock` 的属性/构造参数收窄为稳定 `BaseFileLock`，全仓 pyright 再验证。 |
| DR-037 runner-call stress payload | `deferred-with-owner: R3-A` | controller 已将 runner-call hot payload failure 分配给 R3-A。本轮没有改 Host payload、降低 stress 断言或增加 fallback；默认 pytest 按配置排除 stress。 |
| MiMo config overlay deep replacement | `rejected-with-reason` | 当前契约就是 map-by-id merge、同 id 完整记录替换、非 map 完整替换和显式 `extends`；缺字段由 typed parser 失败，并不存在静默成功的数据丢失路径。`dayu/config/README.md` 补充 object 型非 map 也不 deep merge。 |
| MiMo/DS duplicated SIGINT monitor | `fixed` | 删除 `_FinsSigintMonitor`，Fins direct path 复用 `CliSigintMonitor`；共享类文档扩展为 Host Run / direct operation 共用语义。 |
| DS default temp log leak | `fixed` | 默认日志从持久 `mkstemp` 文件改为 close 时自动删除的 `TemporaryFile`；只有显式 `--log-file` 承诺持久化。 |
| MiMo/DS public parser/doc mismatch | `fixed` | 和 DR-028 同一 public-contract owner 闭环；help、parser、README 与 tests 现在同源。 |

## 实现内容

### 1. Init write destination owner

- `dayu/cli/commands/init.py`
  - normal / overwrite / reset 共用 workspace containment 与 symlink guard；
  - 拒绝 `config` 顶层或已有后代 symlink；
  - 复制到 workspace 内私有 staging tree 后整体安装；
  - backup/rollback/cleanup 不跟随最终 symlink；
  - overwrite 保留非 init 管理的用户文件。
- `tests/cli/test_init_command.py`
  - 覆盖 config symlink、嵌套 symlink、外部目录零写入、用户文件保留、安装失败回滚和 SIGINT cleanup。

### 2. CLI / scene / public projection owner

- `dayu/cli/commands/interactive.py`、`dayu/cli/commands/session.py`、
  `dayu/config/prompts/manifests/interactive.json`、
  `dayu/config/prompts/scenes/interactive.md`
  - interactive ticker 经 shared subject slot owner 进入 LLM-facing system prompt。
- `dayu/cli/commands/fins.py`
  - batch output 改为 versioned JSON argv；
  - Fins direct 复用共享 SIGINT monitor。
- `dayu/cli/arg_parsing.py`、`dayu/cli/agent_entrypoint.py`、
  `dayu/cli/session_execution.py`
  - 删除无 public implementation 的旧 flags、字段和 downstream reject seam。
- `dayu/cli/main.py`
  - 默认日志使用 auto-delete 临时流。

### 3. Packaging owner

- `pyproject.toml`
  - Docling 模型栈显式限制在 Transformers 4.x。
- `constraints/min-py311.txt` 与
  `constraints/lock-{linux-x64,macos-arm64,macos-x64,windows-x64}-py311.txt`
  - 统一 Transformers / Hugging Face Hub 版本。
- `tests/cli/test_public_package_entrypoints.py`
  - 断言 metadata 与全部 Python 3.11 constraints 不再漂移到 Transformers 5.x。

### 4. Finite-number owner

- 新增 `dayu/runtime/numeric.py`：finite、positive finite、non-negative finite 三个层中立 predicate。
- `dayu/runtime/config_loader.py`：strict JSON numeric parser 与所有 float field finite guard。
- `dayu/runtime/cancellation.py`、`dayu/runtime/lane.py`、
  `dayu/runtime/filelock.py`、`dayu/runtime/interruptible_process.py`：
  在各自 public/runtime boundary 拒绝非有限 timeout、interval、TTL、heartbeat 与 grace。
- `dayu/runtime/assembly.py`、`dayu/runtime/scene_prepare.py`、
  `dayu/service/host_assembly.py`、`dayu/service/entrypoint_runtime.py`、
  `dayu/service/scene_context.py`：移除各自重复的 `math.isfinite` 规则并复用真源。

### 5. Release gates 与文档

- `tests/contracts/test_package_exports.py`：更新当前 contract whitelist。
- `tests/host/test_audit_sink.py`：使用合法 preview event type fixture。
- 新增 `tests/runtime/test_numeric.py`；更新相邻 CLI/runtime/service tests。
- 根 `README.md`：重写为当前用户可用 CLI contract。
- `dayu/config/README.md`：补充 strict numeric、overlay complete replacement、interactive subject slot 与 init symlink safety。
- `tests/README.md`：同步当前测试事实。

## 改动文件

生产与公共资产：

- `README.md`
- `pyproject.toml`
- `constraints/min-py311.txt`
- `constraints/lock-linux-x64-py311.txt`
- `constraints/lock-macos-arm64-py311.txt`
- `constraints/lock-macos-x64-py311.txt`
- `constraints/lock-windows-x64-py311.txt`
- `dayu/cli/agent_entrypoint.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/commands/init.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `dayu/cli/main.py`
- `dayu/cli/session_execution.py`
- `dayu/config/README.md`
- `dayu/config/prompts/manifests/interactive.json`
- `dayu/config/prompts/scenes/interactive.md`
- `dayu/runtime/assembly.py`
- `dayu/runtime/cancellation.py`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/filelock.py`
- `dayu/runtime/interruptible_process.py`
- `dayu/runtime/lane.py`
- `dayu/runtime/numeric.py`
- `dayu/runtime/scene_prepare.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/service/host_assembly.py`
- `dayu/service/scene_context.py`

测试与 artifact：

- `tests/README.md`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_init_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_public_package_entrypoints.py`
- `tests/cli/test_upload_filings_from_command.py`
- `tests/contracts/test_package_exports.py`
- `tests/host/test_audit_sink.py`
- `tests/runtime/test_cancellation.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_filelock.py`
- `tests/runtime/test_import_boundary.py`
- `tests/runtime/test_interruptible_process.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_numeric.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_host_assembly.py`
- `docs/host/wu-semantic-ownership-01-round3-r3-f-cli-config-public-contract-plan.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-f-implementation-codex.md`

`docs/host/issues-implementation-control.md` 与本轮开始时已存在的 untracked controller/review
artifacts 均由 controller/其它 Agent 持有；AgentCodex 未修改、删除或纳入本实现。

## Propagation audit

- ticker 事实：CLI 仍把 ticker 投影为 invocation metadata，但 LLM-facing subject 只由
  shared Service scene-context builder 生成；prompt、interactive、interactive resume
  使用同一真源，没有在 manifest、adapter 或测试 fixture 重算公司名文本。
- batch command：Fins planner 仍拥有文件识别与 plan entry；CLI 只把 entry 投影为
  argv JSON。README 与 tests 消费同一 `schema_version=1 / commands` contract。
- numeric semantics：predicate 只拥有有限性与符号判断；ConfigLoader、lane、filelock、
  cancellation 等 owner 继续产生各自错误类型和字段语义，没有下游 fallback。
- release fixtures：contracts export 与 lifecycle event type 均引用生产 public contract，
  不用 loose string 或 mock 绕过 owner validation。

## 验证结果

实现期间已执行：

```text
pytest tests/cli/test_init_command.py -q
16 passed

受影响 CLI / runtime / service / contracts / audit 测试合集
637 passed

python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

pytest -q
3930 passed, 3 skipped, 5 deselected, exit 0

git diff --check
passed
```

默认 pytest 的 `5 deselected` 包含项目配置排除的 stress tests；R3-F 没有运行或修改
R3-A runner-call payload stress。

## README 决策

- 根 `README.md`：已更新。用户可见安装、init、parser、interactive ticker、batch
  output、日志生命周期与 Session 工作流均发生修正。
- `dayu/config/README.md`：已更新。属于 ConfigLoader / prompt asset 读者范围。
- `tests/README.md`：已更新。测试事实发生变化。
- `dayu/README.md`：不更新；分层关系和装配方向未变化。
- Host / Engine / Fins README：不更新；本轮没有修改其生产 owner contract。

## 残余风险与未覆盖项

1. init 使用同一 workspace 内 staging + rename + rollback，但不引入跨进程 init 锁；
   两个进程同时修改同一 config tree 不在本轮承诺内。owner：CLI init；若产品要求并发
   init，再进入独立 WU 设计进程间互斥。
2. 本轮通过 metadata/constraints contract test 验证 Docling 依赖对齐，没有重建全新的
   Python 3.11 minimum environment 做离线 Docling model initialization probe。现有开发 venv
   是变更前已安装环境，不能替代 fresh-lock 证据。owner：packaging/release pipeline。
3. JSON argv 是明确 breaking public output change；旧 shell script consumer 必须改为逐条
   process argv 调用，不提供 compatibility renderer。owner：CLI public contract。
4. runner-call hot payload stress 仍归 R3-A；R3-F 未运行该 stress gate，也未声称关闭。
5. 测试输出仍有 3 条来自 edgartools 的 deprecation warnings；不是 R3-F correctness failure，
   本轮未修改第三方文档处理依赖。

## Stop condition

R3-F plan、implementation、tests、pyright、默认 pytest、README decision 与本 artifact
均已完成。AgentCodex 在此停止，不进入其它 sub WU，不执行 commit、push、PR 或 merge。

## Code-review fix update

Controller code-review adjudication accepted `R3-F-CR-01` after initial implementation review.
Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-f-code-review-fix-codex.md`.
Final controller validation after the fix:

```text
pytest tests/cli/test_init_command.py -q
17 passed

python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

pytest -q
3930 passed, 3 skipped, 5 deselected

git diff --check
passed
```
