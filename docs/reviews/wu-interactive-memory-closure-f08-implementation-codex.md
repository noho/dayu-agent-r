# Interactive Conversation Memory closure F08：implementation artifact

## Gate identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Gate：implementation slice F08。
- Accepted plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
- 分支：`codex/interactive-oracle`。
- Artifact path：`docs/reviews/wu-interactive-memory-closure-f08-implementation-codex.md`。
- Completion status：`implementation-pass`；下一 gate 为 F08 code review。
- Git 边界：本 gate 未 commit、未 push，也未执行远端操作。

## Scope 与 owner 判定

F08 的问题真实存在：现有 prompt 只表达 nullable shape、cap 与 replacement，但没有自足要求模型在 cap 内只能输出完整、可独立理解的业务陈述。Host 只拥有 shape、cap、coverage 等确定性校验，不拥有任意自然语言意义判断；因此修复落在 conversation compaction user prompt，而不是 parser、Context Governance、Memory projector、CLI 或展示层。

本 slice 严格限于以下变更：

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `docs/cli_init_workspace_manifest_v1.json`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_memory_projection.py`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`
- 本 implementation artifact

没有修改 output v2 schema、Host semantic acceptance、Memory schema、三份 frozen baseline 或 frozen evidence。没有加入字符/词数阈值、词表、正则、占位符接受测试、兼容分支或下游 fallback。

## Implementation decisions 与改动

### LLM-facing summary 选择规则

`conversation_compaction_user.md` 现在自足要求：

- 非 null summary 至少包含一条完整、脱离原会话也可独立理解的业务陈述；
- 只覆盖材料中实际存在且后续需要的当前用户目标、已建立结论或进展、仍影响后续的关键约束或下一步，不为凑维度编造内容；
- 明确 cap 内无法形成至少一条完整陈述时输出 JSON `null`；
- 禁止占位符、孤立字符、孤立标点、无上下文缩写和截断片段；
- `null` 清除旧 summary，不表示保留旧值；其它四类业务语义项仍按本次材料独立输出。

prompt contract test 直接断言上述模型动作规则，同时保留 strict JSON、whole replacement、untrusted material 边界和现有 v2 schema 自足性断言。

### Memory replacement owner contract

扩展既有 owner test，以连续两个 accepted compact 先建立旧 summary，再接受 `session_summary=None` 且同时包含 fact、answer anchor、forward intent、reference continuity 的完整 replacement。测试断言旧 summary 及其 event identity 被清除，另外四类逐项保留，并经 canonical snapshot JSON 重读后保持完全一致。

### Publication digest 同源

- 最终 prompt raw SHA-256：`5f5a51519e11eae0f162e8623e3c55d3946e1613bd36bfe4c38cc3e61eb827c0`。
- manifest 仅更新该 prompt 的唯一 `content_sha256` entry。
- 最终 manifest raw SHA-256：`9ebdeab528bfcf953107a7d0e94d7aba63aab4fe8c56f7e612251dd1247af6a1`。
- init smoke test 仅同步唯一 `FROZEN_MANIFEST_SHA256` consumer。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

- Owner-level focused tests：prompt contract 与 Memory replacement test，`2 passed`。
- F08 focused/init manifest suite：
  `pytest tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/cli/test_smoke_cli_init_provider_matrix.py -q`，`158 passed`；仅有三条第三方 `edgar` deprecation warnings。
- 受影响范围 pyright：三个修改的 Python test 文件，`0 errors, 0 warnings, 0 informations`。
- Ruff lint：三个修改的 Python test 文件，`All checks passed`。
- Ruff format：三个实际修改行区间分别执行 `--check --range`，均为 `1 file already formatted`。整文件诊断会重排 accepted baseline 中大量未触及代码，因此没有执行超出 F08 的机械格式化。
- compileall：三个修改的 Python test 文件通过。
- JSON：`python -m json.tool docs/cli_init_workspace_manifest_v1.json` 通过。
- Diff：`git diff --check` 通过；变更路径只包含 approved F08 files 与本 artifact。
- 按用户约束未运行五条正式 CLI scenarios。

## README decision

已先读取 `dayu/config/README.md`、`tests/README.md` 与根 `README.md` 的写作/更新边界，判定均不修改：

- `dayu/config/README.md` 只拥有默认配置、workspace 覆盖关系与 prompts 目录职责；F08 只改变一个既有 scene prompt 的业务选择文本及派生 digest，不改变配置层级、加载、覆盖、schema 或目录职责。
- `tests/README.md` 只在测试层级、运行方式或维护规则变化时更新；F08 只扩展既有 prompt contract 与 Memory owner test，不改变这些文档事实。
- 根 `README.md` 面向最终用户；安装、初始化命令、CLI 参数、输出通道、工作区路径、用户工作流与排障方式均未变化。

## Frozen baseline verification

implementation 前与完成时的 SHA-256 均匹配 accepted-plan checkpoint：

- `docs/cli_ci_oracles.json`：`da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：`7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：`95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

只读 frozen evidence 也未改变：

- `workspace/tmp/interactive-memory-observed-behavior.md`：`ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263`
- `workspace/tmp/interactive-memory-report-freeze.json`：`7ba64926a22406f086a417ee269313a3b07dbc05b480463ff535007f72198f5b`

## Residual risks 与 uncovered areas

- 自然语言是否稳定遵守完整陈述规则仍取决于真实 provider；分类为 `assigned to later work unit`，由实现/review/deepreview 后的独立 real-provider evidence/readiness 场景验证。本 slice 按设计不以 Host heuristic 伪造确定性保证。
- 未覆盖正式 CLI 场景与远端 provider 行为；同样归入上述 later evidence/readiness work，不属于 F08 implementation gate。

没有 blocking open question，也没有未分类 residual risk。
