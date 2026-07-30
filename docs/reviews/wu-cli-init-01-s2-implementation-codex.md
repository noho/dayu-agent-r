# WU-CLI-INIT-01 S2 Implementation

## Gate metadata

- Gate：`implementation`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S2 — Model family owner 与 init interaction state machine`
- 日期：2026-07-30
- Scope：建立四字段 resolved model family identity；让 init 的可恢复输入在原步骤
  retry；按锁内 target mode 单次 typed load 默认 execution profile minimum，并固定
  reset / required persistence confirmation 的 Enter、EOF、SIGINT 退出语义。
- Artifact path：
  `docs/reviews/wu-cli-init-01-s2-implementation-codex.md`

## Semantic owner decisions

- resolved model family identity 的唯一 owner 是
  `dayu.runtime.assembly.ModelFamilyIdentity` 与
  `model_family_identity(ModelConfig)`。四字段只来自 typed `ModelConfig`：
  `provider`、provider model、`endpoint`、credential ref；model id、provider
  extension 与 runner hints 不属于 family identity。
- ordinary/thinking choice 同源校验的 owner 是 `dayu.cli.init_catalog`。静态 choice
  与 package Ollama template 在 catalog validation 时校验；package 中按 contract
  不存在的 Custom record 在动态 materialization 并经真实 `ConfigLoader` 重载后，
  进入同一个 pair validator。15 个 choice 最终都消费同一个 runtime identity helper。
- 动态 model name / endpoint 语法 owner 是 `dayu.cli.init_catalog` 的公开 field
  validators；settings dataclass 与 CLI 交互步骤复用同一 validator，不在 UI
  重写 URL 或 whitespace 规则。
- target effective profile minimum 的真源是
  `ConfigLoader.load_execution_profiles(...)` 返回的 typed default profile。
  `dayu.cli.commands.init` 只拥有锁内 mode 到 loader source 的选择和显式下传：
  FIRST / OVERWRITE / confirmed RESET 使用 package-only，PRESERVE 使用真实 workspace
  layered source。
- 交互步骤、confirmation 与 exit mapping 的 owner 是
  `dayu.cli.commands.init`。环境值本身的合法性继续由
  `EnvironmentPersistenceEntry` 校验；init 只在该明确 owner exception 上原步骤
  retry。

## Changed files

- `dayu/runtime/assembly.py`
- `dayu/cli/init_catalog.py`
- `dayu/cli/commands/init.py`
- `tests/runtime/test_assembly_helpers.py`
- `tests/cli/test_init_catalog.py`
- `tests/cli/test_init_command.py`
- `docs/reviews/wu-cli-init-01-s2-implementation-codex.md`

## Implemented contract and state transitions

1. 新增 immutable、slots-backed 的四字段 `ModelFamilyIdentity` 和唯一 typed
   constructor。catalog family mismatch 只报告 ordinary/thinking model ids 与
   `mismatched_fields`，不回显 endpoint 或 credential material。
2. 15 个 choice 的 ordinary/thinking resolved pair 经过同一个 family helper；
   provider/model/endpoint/ref 任一 owned fact 漂移都会 fail closed，extension /
   runner hint 差异不影响 identity。
3. choice、动态 model name、endpoint、context、required/optional secret 与
   confirmation 都使用明确 loop；只捕获当前字段 owner 的 validation exception，
   EOF、`KeyboardInterrupt`、`OSError` 与编程错误不被当成 recoverable field error。
4. `_confirm(...)` 不再把 EOF 改写为默认 No：
   - reset No/Enter -> 0，EOF -> 1，SIGINT -> 130；
   - required persistence No/Enter -> 1，EOF -> 1，SIGINT -> 130；
   - invalid yes/no 在同一 confirmation prompt retry。
5. 获锁、复核 locked snapshot、确定 locked mode 后，在首个 model prompt 前单次调用
   typed execution profile loader：
   - FIRST / OVERWRITE / RESET：`workspace_config_dir=None`；
   - PRESERVE：`workspace_config_dir=<real workspace>/config`；
   - workspace profile 缺失：由 loader 的 package layer 取得 minimum；
   - workspace profile 已存在但 malformed/schema/default-id-invalid：exit 1，提示
     `--overwrite`，不执行 package-only fallback；
   - package profile 缺失/非法/default-id-invalid：exit 1，给出 repair/reinstall
     动作；
   - 两类诊断只包含 exception type，不拼接原异常、原始值或完整配置路径。
6. minimum 以普通显式参数下传给 model selection/context reader。Custom 默认值直接
   使用 target minimum；Ollama 保留 template default，但低于 target minimum 的默认
   或显式输入均在 context 步骤 retry。生产代码不含 `262144` fallback。
7. profile load failure 发生在 model/secret prompt、transaction prepare、环境写入与
   managed-root publication 之前；相关 tests 断言 config / `.dayu` absent 或逐字节
   保持。

## Tests and validation

- S2 focused tests：

  ```text
  source .venv/bin/activate
  pytest tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py -q
  ```

  结果：`116 passed`。覆盖四字段 identity、extension/hint 非 identity、15-choice
  family、动态字段/choice retry、required/optional secret retry、confirmation
  矩阵、四态 loader source、PRESERVE higher minimum 的 Custom/Ollama 低值原步骤
  retry、workspace/package profile fail-closed 与零 publication。

- 单文件 coverage：

  ```text
  coverage erase
  coverage run -m pytest tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py -q
  coverage report \
    --include='dayu/runtime/assembly.py,dayu/cli/init_catalog.py,dayu/cli/commands/init.py'
  ```

  结果：
  - `dayu/runtime/assembly.py`：`92%`
  - `dayu/cli/init_catalog.py`：`90%`
  - `dayu/cli/commands/init.py`：`95%`
  - 合计：`92%`

- Affected-scope pyright：

  ```text
  python -m pyright dayu/runtime/assembly.py dayu/cli/init_catalog.py \
    dayu/cli/commands/init.py tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py
  ```

  结果：`0 errors, 0 warnings, 0 informations`。

- Ruff：

  ```text
  python -m ruff check dayu/runtime/assembly.py dayu/cli/init_catalog.py \
    dayu/cli/commands/init.py tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py
  ```

  结果：`All checks passed!`。

- `git diff --check`：通过。

## Docs decision

- README：本 slice 不更新。用户明确限制 S2 只修改 approved files，并禁止修改
  README；accepted plan 已把 work-unit 级最终用户说明和 tests 手册同步分配给 S6。
- accepted oracle、goal artifact、accepted plan、S1 artifacts：未修改。
- 本 slice 只新增要求的 implementation artifact。

## Findings fixed

- Controller A01：reset Enter/No=0、EOF=1、SIGINT=130，`已修复`。
- Controller A02：required persistence No/Enter/EOF=1、SIGINT=130 且环境和 managed
  roots 零写入，`已修复`。
- Controller A04：唯一 typed profile API、锁内加载时点、脱敏 fail-closed 与零
  publication，`已修复`。
- Controller R03：FIRST/OVERWRITE/RESET package source、PRESERVE layered source、
  missing package layering、invalid workspace fail-closed 与 higher minimum 原步骤
  retry，`已修复`。

## Residual risks

- S3 的 package defaults 与 Service primary/compactor runtime family comparison
  尚未实施。
  - classification：`covered by later approved slice`
- S4 的 workspace transaction repair/PRESERVE managed-file 补齐不属于本 slice。
  - classification：`covered by later approved slice`
- S5/S6 的真实 provider matrix、跨平台 aggregate validation 与 README 同步尚未执行。
  - classification：`covered by later approved slice`
- 当前 S2 owner boundary 内无未分类 residual risk。

## Completion

- Completion signal：`pass`
- Stop condition：`none`
- 严格只修改 S2 approved files 与本 artifact。
- 未修改 S3 package defaults/Service、workspace transaction、README、oracle 或 plan。
- 未提交。
