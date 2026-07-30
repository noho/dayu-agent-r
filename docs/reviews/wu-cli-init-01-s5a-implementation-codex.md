# WU-CLI-INIT-01 S5-A Implementation

## Gate

- work unit：`WU-CLI-INIT-01`
- slice：`S5-A deterministic implementation`
- gate：`implementation`
- implementer：`AgentCodex`
- status：`pass`
- code review：双路 review 均为 `PASS`
- artifact：
  `docs/reviews/wu-cli-init-01-s5a-implementation-codex.md`

## 目标与边界

本 slice 为 `cli.init.workspace-initialization@1` 建立确定性的 workspace
publication oracle 与 provider matrix 纯函数基础。冻结 manifest 必须独立于 actual
tree，严格比较目录、文件路径、内容摘要和 16 个模型投影 owner；classifier、
redaction、bounded summary、secret scan 与 no-fallback verdict 必须可在默认 pytest
中离线验证。

本 slice 不运行公网 provider，不启动 live subprocess，不读取或推演 Host
tool-trace，也不签发真实 provider matrix pass。上述 live 行为属于后续 S5-B。

## Scope

实现只修改以下三个文件：

1. `docs/cli_init_workspace_manifest_v1.json`
2. `utils/smoke_cli_init_provider_matrix.py`
3. `tests/cli/test_smoke_cli_init_provider_matrix.py`

本文件只记录 implementation evidence。reviewer artifacts 未修改。

## 第一性原理与直接证据

冻结对象是 init 完成后的 workspace publication，不是 package `config` source
directory。第 43 个文件是 workspace 根下持久存在的 `.dayu-init.lock`：

- `dayu/cli/commands/init.py` 定义固定 lock 名 `.dayu-init.lock`，在 workspace root
  建立 lock path，并通过 production `file_lock` acquire/release；
- acquire 后 production 明确校验 lock 为普通非 symlink 文件，成功 publication
  不删除该文件；
- `tests/cli/test_init_command.py::test_first_cli_flow_uses_real_lock_discovery_and_current_config`
  的真实 CLI FIRST flow 明确断言
  `(workspace_root / ".dayu-init.lock").is_file()`；
- S5-A positive fixture 直接组合 production `file_lock`、
  `prepare_workspace_transaction(...)` 与
  `publish_workspace_transaction(...)` 构造 FIRST workspace，并断言 lock 持久存在且
  内容为空；
- 空 lock 的 content SHA-256 为
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

因此 frozen manifest 的 workspace publication contract 是精确 5 个受管目录、
43 个受管文件，其中路径只允许根级 `.dayu-init.lock` 与 `config` 受管集合。
portfolio、assets、`.dayu` 和其它 workspace sibling 不属于本 manifest。

## 三文件变更

### Frozen manifest

`docs/cli_init_workspace_manifest_v1.json`：

- `publication_root` 从错误的 package-config 语义改为 `workspace`；
- 文件集合加入根级空 `.dayu-init.lock`，总数固定为 43；
- 目录集合仍精确为 5；
- digest 字段从不准确的 `package_sha256` 改为 `content_sha256`；
- 修正 `config/prompts/scenes/prompt.md` 的真实 64 位 SHA-256；
- 保留并严格记录 16 个 `/model/default_model_id` projection owner；
- 文件路径使用确定性排序，manifest 自身 digest 由测试冻结。

### Deterministic implementation

`utils/smoke_cli_init_provider_matrix.py`：

- 提供严格 typed frozen manifest loader；
- 独立枚举实际 workspace publication，不从 expected paths 生成 actual；
- 精确比较 5 个目录、43 个文件、content digest 和 16 个 model pointer；
- 路径 schema 只允许根级 `.dayu-init.lock` 与 `config` 受管集合；
- 提供 enum/dataclass report schema；
- 提供纯函数 preflight/availability classifier；
- 提供 endpoint userinfo/query/fragment redaction、bounded text summary、
  authorization/credential/canary secret scan；
- 提供同 run、同 effective identity、observed identity set 与 alternate terminal
  联合约束的 no-fallback verdict；
- argparse 只建立 deterministic/live 后续入口骨架；live 路径明确抛出
  `NotImplementedError`。

### Deterministic tests

`tests/cli/test_smoke_cli_init_provider_matrix.py`：

- positive fixture 通过 production lock 与 transaction owner 构造真实 FIRST
  workspace，再为各 mutation test 建立 fresh copy；
- 覆盖 frozen manifest 正向匹配；
- 覆盖 actual 新增、删除、内容篡改和 model pointer mismatch；
- 覆盖 checked-in manifest digest 在 validation 前后不变；
- 覆盖严格 loader schema 错误；
- 覆盖 preflight 与 availability 的全部 enum 分支；
- 覆盖 endpoint redaction、bounded summary、secret/authorization/canary scan；
- 覆盖 no-fallback 正反例；
- 覆盖 argparse live 入口当前明确 `NotImplementedError`。

## Validation

所有命令均在 `source .venv/bin/activate` 后运行。

- deterministic pytest：
  `pytest tests/cli/test_smoke_cli_init_provider_matrix.py -q`
  - 结果：`42 passed`
  - 附带 3 条既有第三方 `edgar` deprecation warnings
- utils 单文件 coverage：
  `coverage report --include='utils/smoke_cli_init_provider_matrix.py'`
  - 结果：`92%`（401 statements，33 missing）
  - 高于本 slice `>=80%` 目标
- full pyright：
  `python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- ruff：
  `ruff check utils/smoke_cli_init_provider_matrix.py tests/cli/test_smoke_cli_init_provider_matrix.py`
  - 结果：`All checks passed`
- diff check：
  `git diff --check`
  - 结果：通过

未运行 S5-B live provider matrix。

## Docs decision

本 slice 新增 frozen manifest 和本 implementation artifact。README、真实 matrix
运行说明及 aggregate 文档同步属于后续已批准 slice，不在 S5-A 修改。

## Residual risks

1. **Live provider request、subprocess、Host trace 与 runner-input evidence 尚未实现**
   - 分类：`covered by later approved slice`
   - owner/destination：`WU-CLI-INIT-01 S5-B`
   - 当前影响：不影响 S5-A deterministic pass；S5-A 不得被表述为 real matrix pass。

2. **真实 credential、endpoint、限流、provider rejection 与 transport failure 尚未在
   当前环境分类**
   - 分类：`covered by later approved slice`
   - owner/destination：`WU-CLI-INIT-01 S5-B`
   - 当前影响：classifier contract 已离线覆盖，真实 evidence 仍需 S5-B。

3. **测试导入链产生 3 条第三方 `edgar` deprecation warnings**
   - 分类：`assigned to later work unit`
   - owner/destination：dependency maintenance
   - 当前影响：不属于本 slice 变更，未造成测试、类型检查或 lint failure。

当前不存在未分类 residual risk 或 blocking open question。

## Completion status

- S5-A implementation：`pass`
- 双路 code review：`PASS`
- required validation：全部通过
- live S5-B：未进入
- commit：未创建；当前改动保持未提交
- Gateflow next entry point：由 Controller 执行 accepted-slice handling
