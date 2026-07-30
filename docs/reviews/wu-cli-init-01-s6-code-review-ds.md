# Code Review — WU-CLI-INIT-01 S6（Re-review）

## 裁决

**PASS** — 无 blocking finding。第一轮 review 的两个 finding（F1 双 credential 模式、F2 根 README 跨 family 边界）已被 Codex 以最小改动关闭。所有四个重点审查项均通过。

## Scope

- Mode: current changes（re-review）
- Branch: `ci/pr-179-first-ci-readiness`
- Base: `48567008`
- Review date: 2026-07-30T22:27:01+08:00
- Previous review: `docs/reviews/wu-cli-init-01-s6-code-review-ds.md`（已被本文件覆盖）
- Re-review focus:
  1. 根 README 跨 provider-family 单次 `--model` 与 compactor 边界描述
  2. 两个 helper docstring 的 fixture 使用边界风险关闭
  3. mock credential 与 production 零扩散
  4. implementation artifact 裁决证据链
- Included scope（Codex 改动）:

  ```
  README.md（--model 说明新增两句）
  tests/cli/test_prompt_command.py（_runtime_assembly_env docstring 增强）
  tests/cli/test_interactive_command.py（同）
  ```
- Unchanged from original S6: `dayu/config/README.md`、`dayu/service/README.md`、`tests/README.md`、`docs/reviews/wu-cli-init-01-s6-implementation-codex.md`
- Production diff: **empty**（Codex 未修改 production 代码）

## 重点审查项

### (1) 根 README 跨 provider-family `--model` 与 compactor 边界

Codex 在 `README.md:203-206` 将原始说明从：

```
- `--model ID` / `-m ID`：只覆盖本次主 Run 的模型配置；不写入 workspace，也不改变
  会话压缩模型。
```

扩展为：

```
- `--model ID` / `-m ID`：只覆盖本次主 Run 的模型配置；不写入 workspace，也不改变
  会话压缩模型。即使本次主 Run 显式选择不同的 provider family，会话压缩仍使用
  `init` 选择的 family；未执行 `init` 时使用包内默认 family，不跟随单次 override。
  `interactive` 与 `session resume` 使用相同参数。
```

逐句代码验证：

| 声明 | 代码证据 | 判定 |
|---|---|---|
| 只覆盖本次主 Run | `ordinary_selection` 在 `host_assembly.py:612-617` 消费 `run_override=_model_runner_override_from_overrides(request.overrides)` | ✓ |
| 不写入 workspace | `ServiceAssemblyOverrides.model_id` 只影响当前 invocation，不持久化 | ✓ |
| 不改变会话压缩模型 | `compactor_selection` 在 `host_assembly.py:619-627` 传入 `run_override=None`，不消费 `ServiceAssemblyOverrides` | ✓ |
| 跨 family 主 Run 合法但 compactor 不跟随 | `_require_matching_model_families`（`host_assembly.py:637-640`）只校验 `primary_default_selection` vs `compactor_selection`，不校验 `ordinary_selection` vs `compactor_selection` | ✓ |
| `init` 选择的 family | `compactor_baseline.model_id` 来自 execution profile（package default = `mimo-v2.5-pro-plan`），由 `init` 写入 workspace overlay | ✓ |
| 未 `init` 时使用包内默认 family | `ConfigLoader` 无 workspace overlay 时加载 package execution profiles，四个 profile 的 `compactor_baseline.model_id` 均为 `mimo-v2.5-pro-plan` | ✓ |
| `interactive` 与 `session resume` 使用相同参数 | `_add_agent_execution_arguments`（含 `--model/-m`）同时注册给 `prompt`（`arg_parsing.py:467`）、`interactive`（`:491`）、`session resume`（`:655`）三个命令；`session resume` 内部通过 `prepare_prompt_session_execution` / `prepare_interactive_session_execution` 复用同一 `args.model` → `ServiceAssemblyOverrides` 路径 | ✓ |

**判定**：完整且准确。新文本覆盖了第一轮 review Finding 2 的全部三个缺失维度：跨 family 合法性、compactor 不跟随、以及无 init 时的默认行为。

### (2) 两个 helper docstring 的 fixture 使用边界

Codex 在两个 `_runtime_assembly_env()` 的 docstring 中新增同一行：

```python
本 helper 仅供经过完整 ``prepare_entrypoint_runtime -> Service assembly ->
compactor`` 装配路径的测试使用；mock-assembly 测试继续只声明自身消费的输入。
```

边界评估：

| 维度 | 分析 |
|---|---|
| 精确性 | 点名了三个关键调用节点：`prepare_entrypoint_runtime` → `Service assembly` → `compactor`。这条链直接对应 `_render_headers` 在 compactor runner spec 构造时消费 `MIMO_PLAN_API_KEY` 的执行路径 |
| 可发现性 | docstring 位于函数定义正上方，IDE hover、`help()`、`pytest --co` 均可发现 |
| 负向约束 | "mock-assembly 测试继续只声明自身消费的输入" 明确禁止了"为了保险顺便加上 MIMO_PLAN_API_KEY"的防御性扩散 |
| 与现有 mock 测试的关系 | mock-assembly 测试（17 prompt + 18 interactive）当前不消费 compactor credential，docstring 将其固化为显式设计决策，而非偶然行为 |

**判定**：docstring 边界声明充分。虽然没有编译期强制，但在 Python 测试代码中，docstring 是最强的合约声明手段。与第一轮 review 相比，风险从"开发者可能误复制错误模式"降级为"开发者必须主动忽略 docstring 才会出错"。

### (3) mock credential 与 production 零扩散

扩散检查矩阵：

| 检查项 | 结果 | 证据 |
|---|---|---|
| `_runtime_assembly_env()` 是否被 production 代码 import | 否 | 两个函数均为测试文件模块级私有函数，`dayu/` 目录下无任何文件 import |
| fake value 是否进入 production config/state/artifact | 否 | `_API_KEY = "test-provider-key"` 仅存在于测试模块，不写入 workspace、environment 或 Host SQLite |
| 双 key 同值是否掩盖 credential ref 错误 | 否 | `_render_headers`（`host_assembly.py:1826-1829`）对每个 `api_key_ref` 做独立 `env.get(api_key_ref)` 非空检查；compactor model 的 `api_key_ref="MIMO_PLAN_API_KEY"` 被独立验证 |
| mock-assembly 测试是否意外获得 MIMO_PLAN_API_KEY | 否 | 35 个 mock-assembly 测试仅使用 `monkeypatch.setenv("DEEPSEEK_API_KEY", _API_KEY)`，不设置 `MIMO_PLAN_API_KEY`。如果它们错误地走了 compactor 路径，会以 `missing env MIMO_PLAN_API_KEY` 失败 |
| 是否有 production fallback 被引入 | 否 | Codex 仅修改文档和 docstring，production diff 仍然 empty |
| 是否有 ConfigLoader 绕过 | 否 | 无 production 变更 |
| 是否有 Service assembly 特例 | 否 | 无 production 变更 |

**判定**：零扩散。mock credential 严格限定在测试边界内，不进入 production 任何层级。

### (4) implementation artifact 裁决证据

S6 implementation artifact 的 completion 裁决为 `pass`。支撑证据已在第一轮 review 中独立复核：

| 证据项 | 独立复核结果 |
|---|---|
| focused suite 740 passed | 原始 724 + 16 修复 = 740，与首次失败 16 的 root cause 一致 |
| coverage ≥80% on all owner files | 8 文件覆盖 80%–100%，aggregate 88% |
| pyright 0 errors | 独立执行确认 |
| stale surface scan 零命中 | 独立 grep 复核 `--model-name`、旧 PRESERVE 描述、DeepSeek package default 描述 |
| retained report SHA-256 | `b3eb7a1a...` 独立计算匹配 |
| 15/15 internal contract valid | 独立解析 report JSON 确认 |
| 15/15 no-fallback valid | 独立解析 report JSON 确认 |
| Host SQLite observation classification | 10 rows 中 20 个 exact-byte match 全部归类为 `host_sqlite_credential_value` 的 `accepted_observation`，0 violation |
| 0 `internal_product_bug` rows | 独立解析确认 |
| overall exit 0 | 独立解析确认 |

**判定**：artifact 裁决有完整证据链支撑。Codex 本次的三文件改动（README + docstrings）不影响 artifact 中的任何生产性声明。

## Findings

### 第一轮 review findings 处理状态

| # | 原始 severity | 简述 | 状态 |
|---|---|---|---|
| F1 | 中 | 双 credential 模式并存，重构风险 | **已关闭** — docstring 明确了 helper 的适用边界与 mock-assembly 测试的独立路径，从"隐式双模式"变为"显式设计决策" |
| F2 | 低 | 根 README `--model` 未说明跨 family 边界 | **已关闭** — Codex 新增两句完整描述了跨 family 合法性、compactor 不跟随、无 init 时的默认行为 |

### 当前未修复 findings

**无**。所有 actionable findings 已由 Codex 处理并验证关闭。

## Residual Risk

1. **Provider availability 环境依赖**（未变）：retained report 的 provider 分类是该次真实 run 的快照，S6 未重跑。内部正确性不依赖 provider availability（15/15 internal contract valid + no-fallback valid）。

2. **Windows junction/reparse 与 `setx` 路径**（未变）：本地 Darwin 无法验证。tracked by GitHub Issue #184。

3. **双 credential 模式的编译期强制缺失**（已降级）：docstring 提供了明确的边界合约，但 Python 无编译期机制阻止开发者绕过。这是 Python 测试代码的固有约束，不是 S6 引入的新风险。当前 docstring 是 Python 生态中最强的合约声明手段。

4. **缺少 "仅 DEEPSEEK key 无 MIMO key 时 assembly 应 fail fast" 的负向测试**（未变）：如果 package compactor baseline 的 credential ref 被意外修改（如从 `MIMO_PLAN_API_KEY` 改为 `DEEPSEEK_API_KEY`），已有测试不会发现。frozen manifest 的 SHA-256 提供一定检测能力，但建议后续补充一个显式的 `test_compactor_assembly_fails_without_mimo_credential`。

## Open Questions

- 无。

## Completion

- Review verdict: **PASS** — 无 blocking finding
- Previous findings closed: 2/2（F1 docstring 边界 + F2 README 跨 family）
- New findings: 0
- Production diff: empty
- Mock credential diffusion: zero
- All four re-review focus items: **PASS**
