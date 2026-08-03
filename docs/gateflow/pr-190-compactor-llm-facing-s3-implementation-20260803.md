# PR 190 Compactor LLM-facing S3 implementation

## Gate metadata

- Gate: `implementation`
- Slice: `S3 — Real provider adversarial smoke and publication oracle`
- Accepted base / current base: `e7db947470551de5e3dca4fc06caf0c35f31901e`
- Branch: `codex/interactive-oracle`
- Decision: implementation complete；未进入 code review、未 commit。
- Artifact path: `docs/gateflow/pr-190-compactor-llm-facing-s3-implementation-20260803.md`
- Evidence bundle: `/Users/leo/workspace/.dayu-cli-ci/pr190-compactor-llm-facing-20260803-182956/`
- Evidence index digest: `sha256:dc7836bd631dc59a6665953fa988bce43228560c48a28a9ba6df9f419726d9a2`

## Scope and ownership decision

动机成立。直接代码证据显示旧 real-compactor smoke 固定选择 `PROVIDER_CASES[1]` DeepSeek，未构造 current/trace/evidence/answer 四位置 injection input，也未从 production Context Governance reject 生成 repair feedback。既有 provider failure helper 又直接使用 `pytest.skip` 控制流，不能在不解析 skip 文本的前提下实现 Mimo-first selector。

本 slice 只修改测试基础设施 owner、real smoke 和 publication oracle：

- `tests/host/public_smoke_support.py` 拥有 credential/network/transient/explicit-unavailable/quota-rate-limit 的结构化环境分类；旧 skip helper 与新 selector 共用同一 marker 真源。
- `tests/host/test_public_compact_smoke.py` 拥有 Mimo-first、DeepSeek-only fallback、四位置 canary、owner-level repair setup 和真实行为 oracle。
- production provider routing、prompt renderer、strict parser、Context Governance、schema、filter/verifier 和 operation loop 均未修改。

## Changed files

- `tests/host/public_smoke_support.py`
  - 新增 typed `ProviderEnvironmentUnavailable` 与闭集分类 enum。
  - 新增 credential lookup/classification helper；既有 skip helper 改为消费同一结构化分类结果。
- `tests/host/test_public_compact_smoke.py`
  - real smoke 改为 `PROVIDER_CASES[0]` Mimo-first；只有结构化环境不可用时进入 `PROVIDER_CASES[1]` DeepSeek；绝不访问 Gemini/Qwen。
  - 构造单一 typed request，在 current、trace、evidence、answer 放置四个不同 canary，同时保留收入、经营现金流、毛利率等业务语义。
  - 使用 production governance 对 deterministic evidence item/char 双超限 candidate 生成 repair feedback，再通过 production `LLMContextCompactor` 发起真实 proposal。
  - 成功 raw final 只能经 production strict parser 形成 proposal，并由同一个 test policy instance 验收；行为 oracle 排除 diagnostics，只拒绝 schema attack、虚假动作和虚假财报事实进入业务区。
  - 默认 deterministic tests 覆盖 cap feedback 同源、四 canary 入 typed material、四类 marker classification、缺 credential 与未知失败 fail-closed。
- `docs/cli_init_workspace_manifest_v1.json`
  - 更新两份 prompt asset SHA-256。
- `tests/cli/test_smoke_cli_init_provider_matrix.py`
  - 更新 frozen manifest SHA-256。
- 本 implementation artifact。

`docs/cli_ci_oracles.json` 与 `docs/cli_ci_scenarios.json` 未修改。

## Real-provider observations

### Final exact command

命令：

```text
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py -q -k 'real_compactor'
```

结果：`1 passed, 1 skipped, 29 deselected`。

- Mimo actual attempt: `network_unavailable`，允许 fallback。
- DeepSeek actual attempt: `network_unavailable`，两路环境均不可用后精确 skip。
- Gemini/Qwen: 未尝试。
- 因两路都没有返回非空 raw final，本次没有可进入 strict parser/governance 的真实 proposal；真实 injection/cap 行为 oracle 未观测，不能声称 behavior pass。
- 完整脱敏日志：`real-provider-pytest-final.log`。

### Retained non-environment failure evidence

追加 `-rs` 证据运行曾得到 Mimo `runner_empty_final_content`。该错误不属于允许的环境不可用闭集；selector 按约束直接 fail，没有 fallback DeepSeek。此证据原样保留在 `real-provider-pytest-with-skip-reasons.log`，没有用后续 skip 覆盖。

该失败没有表明 prompt contract 不自足，也没有表明需要 production filter/verifier/schema；它发生在 raw final 为空、strict parser 尚未进入之前。测试因此正确 fail-closed。

## Publication truth

- `conversation_compaction.md`: `sha256:4bd476db45f17bebaa7eb951c8354d10189df1faadb9c1c530619d9f3352f60a`
- `conversation_compaction_user.md`: `sha256:bed77319ee960059ac65119f28a3c6005f53f44ffeb8b7c00c8d1df1e93dc3a5`
- `docs/cli_init_workspace_manifest_v1.json`: `sha256:d63fb2ca415e914c9aaa3959b0b88be2072d1997b70799c9a2ac7de91fce2408`

## Validation

- `pytest tests/host/test_public_compact_smoke.py -q`: `30 passed, 1 skipped`。
- `pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/cli/test_smoke_cli_init_provider_matrix.py tests/service/test_host_assembly.py -q`: `287 passed, 3 warnings`；warnings 均为既有 `edgar` deprecation。
- final exact real-provider command: `1 passed, 1 skipped, 29 deselected`；Mimo/DeepSeek 均精确记录为 `network_unavailable`。
- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`。
- `git diff --check`: pass。
- evidence `SHA256SUMS`: 全部 `OK`。

## Direct evidence

- `deterministic-public-smoke-final.log`: 最新 deterministic owner/setup 与默认 opt-in 边界。
- `publication-validation.log`: frozen publication/config/assembly 验证。
- `real-provider-pytest-final.log`: final Mimo→DeepSeek 分类与精确 skip。
- `real-provider-pytest-with-skip-reasons.log`: Mimo 非环境空 final fail-closed。
- `provider-fallback-classification.json`: provider 顺序、fallback/skip 分类与禁止 provider。
- `redacted-observations.json`: raw/parsed/accepted 的脱敏状态摘要。
- `publication-hashes.json`: publication SHA-256 真值。
- `pyright-final.log`: 最新全量类型验证。
- `diff-check.log`: 最新 whitespace validation（空日志表示 pass）。
- `SHA256SUMS`: immutable bundle 文件 digest 清单。

所有 evidence 均未保存 credential、Authorization header 或 raw provider payload。

## Residual risks and uncovered areas

- 真实 provider injection/cap behavior oracle 未取得：final exact run 的两路 provider 均为 `network_unavailable`，属于 accepted plan 明确允许的精确 skip。分类为 `requiring explicit environment evidence at later rerun`；owner 是 S3 real-provider smoke 环境。
- Mimo 曾返回一次 `runner_empty_final_content`：测试已按非环境失败 fail-closed 且禁止 fallback；该外部 provider 非确定性保留为 code review 必须裁决的 residual，不在本 slice 扩大环境分类。
- deterministic tests 不能替代真实自然语言行为证据；完整 Conversation Memory eval 仍由既有 Issue 80 owner。
- 没有发现 prompt contract 不自足、需要 production filter/verifier/schema 扩张或需要新增 operation loop 的证据。

## Completion status

S3 implementation 与 deterministic/publication/type validation 已完成；final exact real-provider validation 满足“两路精确环境不可用后 skip”的计划路径，但没有取得真实 proposal 行为证据。前一次 Mimo 非环境空 final 证据保留，下一 Gateflow entry point 是独立 S3 code review，由 review 裁决该 residual；本轮不 commit。
