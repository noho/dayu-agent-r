# Code Review — F08 slice：summary null 的 LLM-facing 选择规则与 replacement contract

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `main`
- Output file: `docs/reviews/wu-interactive-memory-closure-f08-code-review-mimo.md`
- Included scope:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - `docs/cli_init_workspace_manifest_v1.json`
  - `tests/cli/test_smoke_cli_init_provider_matrix.py`
  - `tests/host/test_llm_compaction.py`
  - `tests/host/test_memory_projection.py`
  - `docs/reviews/wu-interactive-memory-closure-f08-implementation-codex.md`（implementation artifact，只读参照）
- Excluded scope: v2 parser、Context Governance、Memory schema、三份 frozen baseline、frozen evidence、Engine 层
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Evidence-Based Verification Summary

### 1. LLM-facing prompt 自足性与低认知负担

`conversation_compaction_user.md` 新增的三条 bullet（行 35–37）直接面向模型，使用业务可读语言：

- "完整、脱离原会话也可独立理解的业务陈述" — 自足定义，无内部术语
- "当前用户目标、已经建立的结论或进展、仍影响后续的关键约束或下一步" — 业务维度枚举
- "明确 cap 内无法形成至少一条上述完整业务陈述" — 条件与动作直接关联
- "禁止用占位符、孤立字符、孤立标点、无上下文缩写或任何截断片段" — 禁止项穷举

无字符数/词数阈值、无正则、无语言检测、无 Host heuristic、无内部 Python 类型名。prompt 中不含任何 `Compact*`、`compaction.py`、`context_governance` 等内部术语（grep 验证均为 0）。v2 schema 自足定义未改变。

### 2. null replacement 语义准确性

新增规则准确表达了三个语义维度：

| 维度 | prompt 表达 | 与 plan 对齐 |
|---|---|---|
| null 清除旧 summary | "candidate 被接受后，当前会话摘要变为空，包括清除先前已接受的摘要，不表示保留旧 summary" | ✓ 与 plan §5.4 不变量 1 一致 |
| 其它四类独立保留 | "其它四类业务语义项仍须根据本次材料各自独立输出，不得因 summary 为 null 而一并清空" | ✓ 与 plan §6.F08 步骤 1.e 一致 |
| 非 null 质量要求 | "至少一条完整、脱离原会话也可独立理解的业务陈述" | ✓ 与 plan §6.F08 步骤 1.a 一致 |

### 3. Prompt raw SHA → manifest asset SHA → manifest raw FROZEN 常量同源验证

| 环节 | 计算值 | 声明值 | 一致 |
|---|---|---|---|
| prompt raw SHA-256 | `5f5a5151...eb827c0`（`sha256sum`） | implementation artifact 行声明 | ✓ |
| manifest `content_sha256` entry | `5f5a5151...eb827c0`（diff 行） | prompt raw SHA-256 | ✓ |
| manifest raw SHA-256 | `9ebdeab5...47af6a1`（`sha256sum`） | implementation artifact 行声明 | ✓ |
| smoke test `FROZEN_MANIFEST_SHA256` | `9ebdeab5...47af6a1`（行 95） | manifest raw SHA-256 | ✓ |

三级链路同源，无中间重算或断点。

### 4. 测试断言是否为 owner contract

**prompt contract test**（`test_prompt_assets_are_self_contained_for_fresh_v2_contract`）：

- 断言新增业务维度语句存在于 prompt（"至少一条完整、脱离原会话也可独立理解的业务陈述"等 10 项新增）
- 断言 null 条件与禁止项
- 断言 replacement 语义（"不表示保留旧 summary"、"不得因 summary 为 null 而一并清空"）
- 同时保留现有 strict JSON、whole replacement、untrusted material 边界断言
- 无"Host 接受占位符/句点"的 negative acceptance test（符合 plan adversarial checklist）

**Memory replacement owner test**（`test_accepted_compact_without_summary_clears_prior_session_summary`）：

- 建立含旧 summary 的 snapshot → 接受 `session_summary=None` 且包含全部四类其它 memory 的 replacement
- 断言 `summary_text is None`、`event_id is None`（旧 summary 确实清除）
- 断言 facts 逐项保留、answer anchors 保留、forward intents 保留、reference continuity 保留
- 断言 canonical snapshot JSON round-trip 后相等（`reloaded_snapshot == snapshot`）
- 测试 fixture 使用 `_accepted_compact_payload` 构造全部五类 semantic memory，不依赖默认值或特例

不是字符串偶然匹配测试；断言直接绑定 owner 级 contract 行为。

### 5. README 不改判定

- `dayu/config/README.md`：不触发（F08 只改变 prompt 业务文本与派生 digest，不改变配置层级/加载/schema）
- `tests/README.md`：不触发（F08 只扩展既有 prompt contract 与 Memory owner test，不改变测试层级/运行方式）
- 根 `README.md`：不触发（用户可见安装、CLI 参数、入口、输出通道均未变化）

### 6. 三份 frozen baseline digest

| 文件 | SHA-256 | 与 implementation artifact 声明一致 |
|---|---|---|
| `docs/cli_ci_oracles.json` | `da04923193a04c0e...07261201` | ✓ |
| `docs/cli_ci_scenarios.json` | `7c991d14ebc79f9f...cbca2093` | ✓ |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a...d14b1b08` | ✓ |

FROZEN evidence 也未改变：

| 文件 | SHA-256 |
|---|---|
| `workspace/tmp/interactive-memory-observed-behavior.md` | `ad64315116c3940d...5658263` |
| `workspace/tmp/interactive-memory-report-freeze.json` | `7ba64926a22406f0...98f5b` |

### 7. Allowed files 边界

`git diff --name_only` 精确列出 5 个修改文件 + 1 个 implementation artifact，与 plan §6 F08 allowed files 完全一致。无超出边界的变更。

## Open Questions

无。

## Residual Risk

- 自然语言是否稳定遵守完整陈述规则仍取决于真实 provider；分类为 `assigned to later work unit`，由后续 `interactive.g06.summary-null` scenario 验证。本 slice 按设计不以 Host heuristic 伪造确定性保证。
- 未覆盖正式 CLI 场景与远端 provider 行为；同归入 later evidence/readiness work。

## Conclusion

**PASS**

F08 slice 实现正确：prompt 新增规则自足、低认知负担、无内部术语依赖与 heuristic；null replacement 语义准确且其它四类保留；prompt raw SHA → manifest asset SHA → manifest raw FROZEN 常量三级同源；测试断言 owner contract 而非字符串偶然；README 不改判定正确；三份 frozen baseline digest 未改变。PR 190 的 F08 实现可进入下一 gate。
