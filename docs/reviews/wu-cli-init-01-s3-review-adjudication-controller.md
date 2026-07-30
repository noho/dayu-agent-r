# WU-CLI-INIT-01 S3 Review Adjudication

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- Slice：`S3 — Package defaults 与 Service compactor assembly`
- Gate：双路 code review 裁决
- Controller：AgentController
- 日期：2026-07-30
- Base：`9e6cde82`

## Inputs

- `docs/reviews/wu-cli-init-01-s3-implementation-codex.md`
- `docs/reviews/wu-cli-init-01-s3-code-review-mimo.md`
- `docs/reviews/wu-cli-init-01-s3-code-review-ds.md`
- 基于 `9e6cde82` 的实际 production/test/config diff

## Independent verdicts

- MiMo：`PASS`，未发现实质性问题。
- DS：`PASS`，确认冻结语义、selection 顺序、secret resolution 边界、
  单 credential 证明与 context-window 均成立。

## Finding adjudication

### DS Finding 1：非 finding

`test_explicit_1m_profile_with_256k_model_fails_fast` 的唯一 owner contract 是
低于 profile minimum 的模型必须在 Host options 构造前失败。它没有同时覆盖
family mismatch 的义务，也没有把 family-check 顺序写入测试名或断言。

Family mismatch 已由
`test_compactor_family_mismatch_fails_before_host_options_without_secret_leak`
以两个均通过 context-window 校验的模型独立覆盖。因此该测试先触发
context-window failure 是预期分支，不是不可达产品路径或 coverage defect。

裁决：驳回，不修改实现或测试。

### DS Findings 2–3：非 blocking enhancement / 已覆盖

- `primary_default_selection` 只承担 runtime drift 校验，不是 effective execution
  diagnostics；accepted plan 明确不新增 public/durable schema。
- DeepSeek compactor hint 已由 workspace DeepSeek-only assembly 测试直接断言
  `temperature == 0.4`，不是未覆盖 contract。

裁决：不进入 S3 fix cycle。

## Controller verification

```text
pytest tests/runtime/test_config_loader.py \
  tests/service/test_host_assembly.py tests/cli/test_init_catalog.py -q
244 passed, 3 warnings in 2.70s

python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check 9e6cde82
PASS
```

三条 warning 均来自 `.venv` 中 `edgar` 依赖的既有 deprecation warning，与本
slice 无关。

## Final verdict

`PASS`

S3 可以进入 accepted-slice commit：

- package 默认 scene/profile 已统一为 Mimo Token Plan family；
- Service 分离 durable primary、invocation effective ordinary 与 durable
  compactor 三个 selection；
- compactor 保留自己的 thinking/temperature/top-p/stream/hint；
- family drift 在 secret resolution 与 Host options 构造前脱敏失败；
- package Mimo-only 与 workspace DeepSeek-only 均以单 credential 完成 assembly；
- `--model/-m` 只改变本次主 Run，不改变 compactor。
