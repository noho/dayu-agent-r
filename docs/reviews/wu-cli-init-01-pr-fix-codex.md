# WU-CLI-INIT-01 PR #188 Fix — Codex

## Gate metadata

- **Work unit**: `WU-CLI-INIT-01`
- **PR**: `#188`
- **Gate**: PR review `fix`
- **日期**: 2026-07-30
- **输入 artifacts**:
  - `docs/reviews/wu-cli-init-01-pr-review-mimo.md`
  - `docs/reviews/wu-cli-init-01-pr-review-ds.md`
- **Controller 裁决**:
  - 接受 blocking `PR-F3`；
  - 拒绝 `PR-F1`、`PR-F2` 两项要求在 PR body 逐文件点名的 informational 建议；
  - 只允许修改 7 个受影响测试文件并新增本 artifact；
  - 禁止生产代码、ConfigLoader 绕过、全局 `os.environ`、逐测试散补及 commit/push。

## First-principles judgment

`PR-F3` 动机成立且严重性正确。S3 有意把 package 默认 compactor 从
`deepseek-v4-flash` 迁移到 `mimo-v2.5-pro-plan`，因此真实 Host assembly
必须同时解析显式 DeepSeek 主 Run 与 package MiMo compactor。生产配置和
assembly 的 fail-closed 行为均正确；过时的是仍只提供
`DEEPSEEK_API_KEY` 的测试输入。

修复 owner 是 7 个测试模块中构造真实 assembly 输入的 fixture/helper
边界，不是生产 ConfigLoader、Service assembly 或进程全局环境。把
`MIMO_PLAN_API_KEY` 补到生产代码、绕过 ConfigLoader、修改全局
`os.environ`，或在每个测试节点分别补 key，都会把语义修在错误 owner
或造成重复真源。

## Root cause evidence

直接调用链为：

```text
prepare_entrypoint_runtime / _prepare_runtime_assembly
  -> compose_open_host_options
  -> _compose_options
  -> _runner_spec_from_model (package compactor)
  -> _render_headers
  -> ValueError: missing env MIMO_PLAN_API_KEY
```

直接配置证据：

- `dayu/config/execution_profiles.json` 的 4 个
  `compactor_baseline.model_id` 均为 `mimo-v2.5-pro-plan`；
- `dayu/config/prompts/manifests/conversation_compaction.json` 的
  `default_model_id` 为 `mimo-v2.5-pro-plan`；
- `dayu/config/models.json` 声明该模型的 `api_key_ref` 为
  `MIMO_PLAN_API_KEY`；
- 7 个测试模块的真实 assembly 输入仍只提供
  `DEEPSEEK_API_KEY`。

两份 review 的计数合并后，blocking 范围是 45 个失败节点、7 个文件：

| 测试文件 | PR-F3 失败节点 |
|---|---:|
| `tests/service/test_entrypoint_runtime.py` | 29 |
| `tests/service/test_entrypoint_runtime_interactive_path.py` | 3 |
| `tests/service/test_entrypoint_runtime_prompt_path.py` | 2 |
| `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | 4 |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | 5 |
| `tests/cli/test_transient_delivery_interruption_path.py` | 1 |
| `tests/tools/test_combined_tools_acceptance.py` | 1 |
| **合计** | **45** |

## Finding decisions

| Finding | Controller decision | Fix 状态 | 理由 |
|---|---|---|---|
| `PR-F3` | `accepted` | **已修复** | 45 个真实 assembly 节点因过时 credential fixture 失败，属于 blocking correctness finding。 |
| `PR-F1` | `rejected-with-reason` | **证据失效** | 要求 PR body 逐文件点名 `session_execution.py` 仅属 informational，不改变变更真实性、正确性或验证结论。 |
| `PR-F2` | `rejected-with-reason` | **证据失效** | 要求 PR body 逐文件点名控制文档修复仅属 informational；既有 artifact 已记录，不构成 fix gate 代码或文档缺口。 |

本 gate 未修改 PR body。

## Implementation

每个允许修改的测试模块建立一个 module-level
`_runtime_assembly_env() -> dict[str, str]` typed helper。helper 每次返回新
字典，只包含：

```text
DEEPSEEK_API_KEY
MIMO_PLAN_API_KEY
```

两个 ref 共用测试 credential 值；helper 均带完整中文 docstring，说明返回值
与异常语义。

真实完整 assembly 调用统一改用该 helper：

- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `tests/cli/test_transient_delivery_interruption_path.py`
- `tests/tools/test_combined_tools_acceptance.py`

两条在 compactor 装配前按既有 contract fail closed 的调用有意不扩散
`MIMO_PLAN_API_KEY`：

- prompt scene 缺 required context slot；
- workspace 存在同名非-smoke tool。

本实现没有：

- 修改任何生产代码、schema 或 public contract；
- 绕过真实 `ConfigLoader`；
- 写入全局 `os.environ` 或增加 autouse monkeypatch；
- 在 45 个失败节点逐测试散补；
- 给 mock-only / assembly 前置失败路径增加无关 credential。

## Validation

### 1. 收集 7 个目标文件

```bash
source .venv/bin/activate
python -m pytest --collect-only -q \
  tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_interactive_path.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/runtime/test_smoke_host_public_multiturn_assembly.py \
  tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py \
  tests/cli/test_transient_delivery_interruption_path.py \
  tests/tools/test_combined_tools_acceptance.py
```

结果：`105 tests collected`。

### 2. 运行 7 个目标文件

```bash
source .venv/bin/activate
python -m pytest -q \
  tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_interactive_path.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/runtime/test_smoke_host_public_multiturn_assembly.py \
  tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py \
  tests/cli/test_transient_delivery_interruption_path.py \
  tests/tools/test_combined_tools_acceptance.py
```

结果：`105 passed, 3 warnings in 6.58s`。

### 3. 运行全相关 suite

```bash
source .venv/bin/activate
python -m pytest -q \
  tests/cli \
  tests/runtime \
  tests/service \
  tests/tools/test_combined_tools_acceptance.py
```

结果：`1589 passed, 7 skipped, 3 warnings in 59.39s`。

三条 warning 均为既有 `edgar` deprecation warning，不属于本次变更。

### 4. 完整 pyright

```bash
source .venv/bin/activate
python -m pyright dayu tests utils
```

结果：`0 errors, 0 warnings, 0 informations`。

### 5. Diff validation

```bash
git diff --check
```

结果：通过，无输出。

## Docs decision

本次只修复既有测试 fixture，没有新增测试层级、运行方式、用户可见行为、
分层关系或公共契约，因此不触发 `tests/README.md` 或其他 README 的职责内
更新。新增本 fix artifact 记录 gate 的 root cause、Controller 裁决、实现和
验证证据。

## Residual risks and uncovered areas

- `PR-F3`：fixed in current PR fix gate；等待独立 PR re-review 确认。
- DS review 的既有低风险 `R4`（双 credential helper 缺少专门负向测试）：
  assigned to a later hardening work unit；不是本 blocking finding 的验收要求，
  且 Controller 本 gate 明确限制为 fixture 修复。
- provider 可用性快照与 Windows junction/reparse smoke：分别保持原 review
  中的 environment/provider owner 与 Issue `#184` owner；本 gate 未改变。
- 本 gate 没有新增未分类 residual risk。

## Completion

- **Gate status**: fix implementation、验证与最终 diff/range 审计全部完成。
- **PR-F3 status**: 已修复。
- **Production changes**: 0。
- **Commit/push**: 未执行。
- **Next entry point**: PR review `re-review`。
- **Artifact path**:
  `docs/reviews/wu-cli-init-01-pr-fix-codex.md`
