# WU-CLI-SMOKE-01 Tool Trace Plaintext Controller Adjudication

## 范围

- Work unit: WU-CLI-SMOKE-01 context slot / real-environment validation follow-up
- 问题来源：用户发现 `{{current_time}}` 与 `{{fins_default_subject}}` 只能从运行结果间接推断，Tool Trace 无法直接恢复 LLM 实际看到的明文上下文。
- 裁决目标：Tool Trace 必须能支持 #70 / #71 所需的 runner input reconstruction、tool schema snapshot、tool args/result payload 与 terminal answer 审计，不把大明文塞入 hot/cold trace，也不扩大 secret 持久化面。

## Agent 产物

- Gap 分析：`docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-gap-codex.md`
- 实现 / 修复：`docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-fix-codex.md`
- 初审：
  - `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-review-ds.md`
- 复审：
  - `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-rereview-mimo-20260707-210515.md`
  - `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-rereview-ds.md`

## Findings 裁决

- DS-F1: 双端 projection payload 写入策略重复。已关闭：`run_input.py` 与 `engine_ingest.py` 通过 durable payload helper 统一写入策略。
- DS-F2: projection payload 未按 inline 阈值冷热分离。已关闭：小 payload 写 SQLite，大 payload 写 artifact descriptor，hot/cold trace 只保留 ref / digest / size。
- DS-F3: complete manifest hot diagnostic 不自解释。已关闭：complete hot payload 显式写入 `status="complete"` diagnostic object。
- DS-F4: resolver 只支持 SQLite payload。已关闭：resolver 支持 SQLite payload 与 artifact JSON payload，并做路径 containment、size、digest、JSON object 校验。

MiMo 与 DS 复审均为 Pass，未发现阻断问题。

## Controller 验证

- `pytest tests/host/test_run_input_builder.py tests/host/test_tool_trace_queries.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_durable_transaction.py`
  - 结果：`232 passed`
- `pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：pass
- `python workspace/tmp/verify_tool_trace_resolver.py`
  - 结果：`projection_checks=ok`, `payload_checks=ok`
- 真实环境 smoke：
  - 命令：`dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-controller-tooltrace/prompt.log prompt ... --label wu-cli-smoke-controller-tooltrace --ticker V`
  - run id: `run-275bbf5371f84cbf82c40049cdb72703`
  - provider/model: `mimo` / `mimo-v2.5-pro`
  - HTTP: 200
  - tool: `get_current_time`
- 新 run resolver 断言：
  - runner input projection 明文包含 `# 当前时间`
  - runner input projection 明文包含 `# 当前分析对象`
  - runner input projection 明文包含 `V（Visa Inc.）`
  - selected tool schema snapshot 包含 `get_current_time`
  - 两个 runner-call reconstruction signal 均为 `complete`
  - tool trace payload 可恢复 `Asia/Shanghai`
  - 结果：`projection_plaintext=ok`, `tool_payloads=ok`

## 结论

Tool Trace 明文可审计性 gap 已闭环。当前实现满足本轮验证需求，也为 #70 / #71 后续实施提供了可恢复的 runner input projection、selected tool schema snapshot、tool args / result payload 和 terminal payload 查询基础。

## Residual Risk

- 既有 durable payload 中 provider header secret retention 是本轮前已存在风险，不属于本次 Tool Trace projection 修复范围，需要另行归属 owner。
- projection artifact 的批量 retention / purge 仍依赖后续 durable retention work unit 统一处理。
- cold JSONL 新增可选字段的外部 consumer schema evolution 需要后续 consumer 接入时显式处理。
