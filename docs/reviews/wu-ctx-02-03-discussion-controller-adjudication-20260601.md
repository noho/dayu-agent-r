# WU-CTX-02 + WU-CTX-03 Discussion Controller Adjudication

## 1. 裁决结论

`WU-CTX-02 + WU-CTX-03` 的 discussion / code inspection gate 通过，可以进入 plan gate。

基于 `docs/host/design.md` 的设计目标和第一性原理，当前最合适的做法是补齐已设计但尚未落地的 compact failure policy、deterministic recent-window fallback、默认配置一致性和 reactive overflow dispatch-loop E2E，而不是重写 Context Governance 或扩大到 provider tokenizer、Engine retry、memory projection redesign。

## 2. 直接证据

- `docs/reviews/wu-ctx-02-03-discussion-code-inspection-20260601.md` 已核对 `dayu/host/context_policy.py`、`dayu/config/execution_profiles.json`、`dayu/config/prompts/manifests/conversation_compaction.json`、`dayu/host/compaction_operation.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/context_events.py` 与相关 `tests/host` 覆盖。
- 当前代码已经覆盖 bounded repair loop、reactive attempt/execution identity 校验、reactive failure 不进入 `LOST`、ingest-level reactive compact 上限、multi-pass 不提交 partial compacted event。
- 当前仍存在的真实缺口包括默认 retry budget 未对齐设计的 5、execution profile 与 Host fallback 默认值不一致、scene manifest compactor 默认模型与 execution profile 不一致、deterministic recent-window fallback 未实现、`CONTEXT_COMPACTION_FAILED` payload 缺少 attempt count / exhausted / fallback 诊断，以及连续 reactive overflow dispatch-loop E2E 缺失。

## 3. Finding 裁决

| ID | 来源 | Finding | 裁决 | 理由 |
|---|---|---|---|---|
| DISC-01 | code inspection | 默认 `max_compaction_attempts_per_operation` 与设计默认 5 不一致 | accepted | 设计真源明确要求 packaged policy 与代码 fallback 默认值一致为 5；当前 Host fallback 为 2、profiles 为 3，会导致同一语义在不同装配路径下分裂。 |
| DISC-02 | code inspection | scene manifest compactor default 与 execution profile default 不一致 | accepted | 设计真源要求 packaged default 不互相矛盾；当前 scene high-spec default 与 profile flash-tier default 不一致，会削弱配置真源清晰度。 |
| DISC-03 | code inspection | deterministic recent-window fallback 未实现 | accepted | 设计真源明确 fallback 不是 compact 成功，但 compact failure 后可按 policy 构造 bounded input view 并记录 diagnostic；当前 proactive / reactive failure 直接 failed，缺少该治理路径。 |
| DISC-04 | code inspection | `CONTEXT_COMPACTION_FAILED` payload 诊断不足 | accepted | 设计真源要求 attempt count、retry / repair budget exhausted 与 fallback decision / budget result；当前 payload 无法完整解释 failure closeout。 |
| DISC-05 | code inspection | 连续 reactive overflow dispatch-loop E2E 缺失 | accepted | WU-CTX-03 的 success signal 要求观察 Attempt 数、compact events 与最终 terminal；当前 ingest 单点测试不能替代 scheduler dispatch-loop 行为闭环。 |
| DISC-06 | code inspection | provider tokenizer adapter 不应纳入当前 WU | rejected-with-reason | 设计真源已明确 provider-specific tokenizer adapter 是后续能力；纳入当前 WU 会扩大 scope 且不服务当前 success signal。 |
| DISC-07 | code inspection | fallback policy 具体参数是否需要 public contract | needs-more-evidence | 当前 evidence 只能证明 fallback 行为缺失，不能证明必须新增 public field；plan gate 需要优先尝试复用现有 policy / internal default，若确需 public contract 再回 design discussion。 |
| DISC-08 | code inspection | post-compact estimator failure 是否有独立代码路径 | needs-more-evidence | 现有 evidence 证明 hard-threshold-after-compact 有覆盖，但 estimator failure / fallback diagnostic 数据流需要 plan gate 进一步核对。 |

## 4. Plan Gate Scope

Plan 必须覆盖：

- 默认 compact retry budget 统一为 5，并补齐 Host fallback、execution profiles、Service assembly 或配置一致性测试。
- 默认 compact model 来源一致，packaged default 使用 flash-tier，且高规格模型只能由 profile 显式选择。
- `CONTEXT_COMPACTION_FAILED` payload / validator / tests 补足 attempt count、budget exhausted、fallback decision、fallback window / digest、fallback budget result。
- deterministic recent-window fallback 的 proactive 与 reactive 收口路径，确保 fallback 不写 `CONTEXT_COMPACTED`、不写 memory projection、不伪造 stable facts。
- fallback 后重新估算预算，预算通过才 dispatch，仍超预算必须 fail closed。
- 连续 reactive overflow dispatch-loop E2E，验证 compact 次数上限、Attempt 数、compact events 与最终 `FAILED` terminal。

Plan 不得覆盖：

- provider tokenizer adapter。
- Engine-owned overflow retry。
- recovery / positive orphan proof 重构。
- memory projection 或 evidence-backed fact 语义重写。
- 为旧 schema、旧 profile 或旧接口保留兼容路径。

## 5. Blocking Open Questions

none

## 6. Residual Risk

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| RR-CTX-PLAN-01 | open | WU-CTX-02 + WU-CTX-03 plan gate | 计划阶段确认 fallback policy 是否能用 Host 内部默认或现有 policy 派生；若必须新增 public field，先回 design doc。 |
| RR-CTX-PLAN-02 | open | WU-CTX-02 + WU-CTX-03 plan gate | 计划阶段进一步核对 post-compact estimator failure 是否有独立 failure path 和测试入口。 |
| RR-CTX-PLAN-03 | open | WU-CTX-03 implementation owner | 连续 overflow E2E 必须使用确定性 fake worker / scheduler helper，不得依赖不可控 sleep 或 race。 |

