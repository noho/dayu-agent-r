# Code Review — Slice 6 README 同步（第二路独立 DS review）

## Scope

- Mode: current changes (unstaged)
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: implicit (review unstaged workspace diff)
- Output file: `docs/reviews/host-owned-compactor-code-review-ds-slice6.md`
- Included scope:
  - `README.md`（根用户手册 §5.1 Host public smoke）
  - `dayu/host/README.md`（Host 开发手册：public contract、包根导出、Context Governance Boundary）
  - `tests/README.md`（测试手册：public-path smoke 描述）
- Excluded scope:
  - `docs/reviews/host-owned-compactor-implementation-slice6-codex.md`（第一路 Codex review，只作为交叉对比参照）
  - `docs/host/design.md`、`docs/host/*-plan.md`（设计真源与历史 plan，非本次同步目标）
  - 生产代码 / 测试代码（本 slice 只做文档同步，不做代码变更）
- Parallel review coverage: 无（单 reviewer 独立全量走读）

## 验证方法

本 review 对每个 README 修改点执行了"文档声称 → 代码证据"逐条对照：

| # | 文档声称 | 代码证据 | 结论 |
|---|---------|---------|------|
| 1 | Service-facing public contract 使用 `CompactorRunnerBaseline` | `dayu/host/api.py:921` 定义 `CompactorRunnerBaseline`，`api.py:1022` 字段为 `compactor_runner_baseline: CompactorRunnerBaseline \| None` | 一致 |
| 2 | `open_host` 内部构造 `LLMContextCompactor` | `dayu/host/open_host.py:610-617` 从 `CompactorRunnerBaseline` 构造 `LLMContextCompactor(runner_spec=..., runner_options=...)` | 一致 |
| 3 | `CompactorRunnerBaseline` 不含 `ContextCompactor`、`policy_ref` | `api.py:930-933` 字段仅 `compactor_runner_spec` / `compactor_runner_options` / `compact_artifact_root` / `compact_artifact_create_parent_dirs`；`test_public_open_host_options.py:283-285` 断言无 `compactor_policy_ref` | 一致 |
| 4 | 普通调用方不能传入 compact prompt、candidate builder | `llm_compaction.py:62-67` `_SYSTEM_PROMPT` 模块级硬编码；`llm_compaction.py:345` `_candidate_from_summary` 模块级私有函数 | 一致 |
| 5 | LLM compactor 使用禁用工具的 Engine request | `llm_compaction.py:202-221` 构造 `disable_tools=True`, `allow_tool_calls=False`, `tool_schemas=()`, `_RejectingToolExecutor()` | 一致 |
| 6 | Smoke 脚本使用 `CompactorRunnerBaseline` | `smoke_host_public_multiturn.py:45` 从 `dayu.host` import `CompactorRunnerBaseline`；`smoke_host_public_multiturn.py:348` 传入 `compactor_runner_baseline=CompactorRunnerBaseline(...)` | 一致 |
| 7 | Smoke 脚本不输出 "DeepSeek compactor 调用次数" | `smoke_host_public_multiturn.py` 只输出 `SMOKE TOOL_CALL_COUNT`、`SMOKE COMPACT_ARTIFACT_*`，无 compactor 调用计数 | 一致 |
| 8 | `test_public_compact_smoke.py` 使用 `CompactorRunnerBaseline` | `test_public_compact_smoke.py:15` import `CompactorRunnerBaseline`；`:100` 传入 `compactor_runner_baseline=CompactorRunnerBaseline(...)` | 一致 |
| 9 | 包根不导出 `CompactorExecutionBaseline` | `test_package_exports.py:191` 断言 `"CompactorExecutionBaseline" not in package_symbols`；`dayu/host/` 下生产代码无 `CompactorExecutionBaseline` | 一致 |
| 10 | 包根导出 `CompactorRunnerBaseline` | `dayu/host/__init__.py:58,154` 导入并列入 `__all__`；`test_package_exports.py:63` 列入 expected exports | 一致 |
| 11 | `ContextCompactor` 作为 Host 内部 / 低层测试 seam | `dayu/host/compaction.py:870` 定义为 `Protocol`，只在 `dayu.host.compaction` `__all__`；不进入 `dayu.host` 包根 `__all__` | 一致 |

## Findings

未发现实质性问题。

## 残留旧术语扫描

对当前 workspace 下 `README.md`、`dayu/host/README.md`、`tests/README.md` 执行了以下模式扫描：

```
CompactorExecutionBaseline
compactor_baseline
caller-owned compactor
Service 注入 ContextCompactor
显式注入的 compactor
DeepSeek compactor 调用次数
```

三个 README 中均无命中。`CompactorExecutionBaseline` / `compactor_baseline` 仅存在于历史 plan 文档（`docs/host/*-plan.md`）与历史 review artifact（`docs/reviews/*`），这些是设计过程的 frozen record，不在本 slice 清理范围。

## README 职责边界检查

- **`dayu/host/README.md` Context Governance Boundary 段**：描述了 `CompactorRunnerBaseline` 的 public contract、`LLMContextCompactor` 的内部构造位置、调用方不能传入的内容、以及 `ContextCompactor` Protocol 的 seam 定位。这些属于架构边界与契约说明（"当前怎么工作"），符合 `dayu/host/README.md` 的职责范围（接口、公共契约、架构、边界、关键机制）。没有照搬 `docs/host/design.md` 的完整设计推导、slice 计划或未来设计。
- **`README.md` §5.1**：描述 smoke 脚本的用途、构造方式与输出，属于用户手册的"手工 smoke"使用说明，符合根 README 职责范围。没有越界写入 Host 架构细节。
- **`tests/README.md` public-path smoke 行**：将 `test_public_compact_smoke.py` 的描述更新为 `CompactorRunnerBaseline` + public opener 内部构造 Host-owned compactor，与当前测试代码的实际行为一致。

## 是否需要同步 dayu/README.md 或根 README 其它段落

- **`dayu/README.md`**：当前术语与层边界描述中，`Context Governance`、`compact events`、`Host` 拥有治理语义的表述不涉及具体 compactor 类型名称（`CompactorExecutionBaseline` / `CompactorRunnerBaseline` / `ContextCompactor`），不包含本 slice 要清理的旧 public contract 术语。无需修改。
- **根 `README.md` 其他段落**：§4（CLI 命令）、§5.2（Engine provider smoke）、§6（渲染输出）均不涉及 Host compactor contract。无需修改。

## Open Questions

无。

## Residual Risk

- 无。本 slice 仅做稳定文档同步，未修改生产代码或测试代码，不引入行为回归风险。
- 第一路 Codex review（`docs/reviews/host-owned-compactor-implementation-slice6-codex.md`）与本 review 结论一致：文档修改准确反映当前代码状态，无残留旧术语，无职责越界。

## 结论

**PASS**
