# Gateflow Implementation: Conversation Memory Smoke S1

## Gate 与 Slice

- Gate：implementation。
- 角色：implementation worker。
- Slice：S1 public finance conversation memory smoke。
- Approved plan commit：`dbb9862`。
- Approved plan artifact：`docs/reviews/gateflow-plan-conversation-memory-smoke-20260526.md`。
- Plan re-review artifacts：
  - `docs/reviews/gateflow-plan-re-review-conversation-memory-smoke-mimo-20260526.md`
  - `docs/reviews/gateflow-plan-re-review-conversation-memory-smoke-ds-20260526.md`

## Changed Files

- 新增 `utils/smoke_host_public_conversation_memory.py`。
- 新增 `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json`。
- 新增 `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md`。
- 更新 `README.md` 手工 smoke 小节。
- 新增本 implementation artifact。

## Implemented Items

- 新增 public-API-only Host conversation memory smoke，运行期 Host 调用仅使用 `open_host`、`ensure_session`、`submit_followup`、`watch_session_events`、`get_session`，terminal failure 摘要才使用 `get_run`。
- 新增 `MockFinanceFactTool` 与 `get_mock_finance_facts` mock tool，返回确定性招商银行 2024H1 息差事实、marker、核对行与可选 pressure blob。
- 工具实例从 effective `ToolBundle` 中按类型恢复；计数限定为本次 fresh session，避免 Host recovery 旧 run 污染本次 smoke 断言。
- 实现四轮 smoke：
  - Round 1 调用工具确认事实。
  - Round 2 禁用工具、分组复述并加入 additive pressure。
  - Round 3 禁用工具、topic shift。
  - Round 4 禁用工具、硬断言 marker、`1.88%`、`-0.14pct` 与工具调用次数仍为 1。
- pressure 校准按当前 `ContextBudgetPolicy` 输出 soft/hard 摘要；实际 pressure token 使用 ASCII-heavy 稳定 padding，避免中文重复块导致 provider tokenizer 超预算。
- README 只补充稳定用户可运行 smoke 命令、用途、mock tool、硬断言与日志观察项。

## Controller/User Corrections

- 采纳 controller/user correction：被测公司不得通过 scene context slot 注入，否则会污染 conversation memory smoke 的验证边界。
- 新 smoke 不使用 context slot 传递公司或用户上下文；`ScenePrepareRequest.context_slot_values` 传空 mapping。
- 被测公司集中为 `_TARGET_COMPANY = "招商银行"`，仅用于用户 prompt、mock tool returned evidence、assertion line、README 说明与 expected values。
- 现有 `ScenePrepare` manifest schema 要求 `context_slots` 字段存在，因此 manifest 使用 `context_slots: []` 表示不声明任何 slot；没有 `fins_default_subject` / `base_user` slot，也没有对应 CLI 参数。

## Validation

1. `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/service/test_host_assembly.py -q`
   - Result：`58 passed in 0.79s`。

2. `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
   - Result：`0 errors, 0 warnings, 0 informations`。

3. `source .venv/bin/activate && python utils/smoke_host_public_conversation_memory.py --log-level VERBOSE`
   - Result：通过。
   - Key stdout：
     - `SMOKE TOOL_CALL_COUNT_AFTER_ROUND1 1`
     - `SMOKE ASSERT_MEMORY_VALUE label=round4-confirmed-fact-consistency status=pass marker=DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1 net_interest_margin=1.88% yoy=-0.14pct`
     - `SMOKE TOOL_CALL_COUNT 1`
     - `SMOKE COMPACT_ARTIFACT_FILE_COUNT 4`
     - `SMOKE PASS public Host conversation memory finance continuity`

## Docs Decision

- 更新根目录 `README.md` 的“手工 smoke”章节，因为新增的是项目级手工验证入口。
- 不更新 `dayu/config/README.md`：新增 scene manifest 使用既有 schema，不改变配置覆盖关系或 prompts 目录职责。
- 不更新 `tests/README.md`：未新增自动测试分类；验证仍通过 focused tests、pyright 与手工 smoke。

## Residual Risks / Uncovered Areas

- 该 smoke 不证明真实 Fins 工具、真实财报仓储或真实财报数值正确性。
- 不读取 durable store、EventLog、memory 表或 compact payload，因此不证明内部 pinned state / episode summary 的具体落点。
- compaction artifact count 只作为 public smoke 日志观察；核心 pass/fail 仍是禁用工具后的多轮事实一致性。
- 真实 provider 可用性、速率限制和模型格式遵循仍可能影响手工 smoke 运行时间或稳定性。

## Stop Status

- Implementation complete。
- Artifact written。
- No commit / push / PR performed。
