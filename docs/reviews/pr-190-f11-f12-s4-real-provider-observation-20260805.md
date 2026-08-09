# PR 190 F11/F12 S4 real-provider observation（2026-08-05）

## Gate 状态

| 维度 | 状态 | 结论 |
| --- | --- | --- |
| Implementation | PASS | 观察基线为已 push HEAD `d9f044f944dd44e0d369f9d93e0533d2b725e413`；本轮未修改生产代码。 |
| Real-provider observation | PASS | 按 Mimo `capability=none`、DeepSeek `capability=json_object` 顺序完成全部可执行 fresh observations；未复现旧 bundle 的 production blocker，也未发现新 production bug。 |
| Formal oracle | PENDING | 按 S4 边界未运行 frozen formal CLI scenarios，未修改 oracle/scenario/registry；不得把 observation PASS 投影成 oracle PASS。 |

双路 evidence review 已完成，总控裁决见 `docs/reviews/pr-190-f11-f12-s4-evidence-review-adjudication-20260806.md`；本次勘误只处理裁决接受的 MiMo-02，并补充不改变 observation 结论的 owner 边界说明。下一 gate 是总控双路 re-review；本轮未调用 reviewer、未 commit、未 push。

## Evidence identity

- 基线 HEAD：`d9f044f944dd44e0d369f9d93e0533d2b725e413`
- fresh immutable evidence root：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`
- root manifest：`digest.json`，排除自身并覆盖其余 `159` 个文件
- `digest.json` SHA-256：`38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`
- human-readable report：`observed-report.md`
- command/screen inventory：`metadata/command-inventory.json` 与 `screen/00` 至 `screen/09`
- 旧 superseded root：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-final-k5hWK9`，只读，未回写

## Observation verdicts

| Requirement | 状态 | 直接 evidence |
| --- | --- | --- |
| Mimo baseline | PASS | `evidence/01-mimo-baseline`：真实 provider/model=`mimo/mimo-v2.5-pro`，capability=`none`，structured-output request 与 outbound response format 均为 `null`；首个 attempt accepted。 |
| Mimo initial caps / no repair protocol | PASS | initial compactor prompt 明示实际 caps，无 repair feedback/action 段；repair 内容只可能出现在后续 attempt。 |
| Mimo no transport / no downgrade | PASS | 所有 Mimo attempt 的 requested/effective capability 为 `none`，outbound response format 为 `null`；不存在从 structured output downgrade 的路径。 |
| Mimo bounded exhaustion / single failure / fallback | PASS | `evidence/03-mimo-exhausted-fallback`：2 次真实 response rejected、1 个 failed terminal、0 compacted、0 artifact；canonical `CONTEXT_COMPACTION_FAILED.payload.fallback_input_window`（失败 terminal 的 input boundary）记录 fallback=`deterministic_recent_window`、selected=9、dropped=2。dispatch 完成后的 `memory.json.snapshot.trace_memory.selected_recent_window` 为 8 items，是另一投影，不是该 selection ledger，也不拥有 `dropped_block_ids`。 |
| DeepSeek first-pass compact | PASS | `evidence/04-deepseek-baseline`：真实 provider/model=`deepseek/deepseek-v4-flash`，`json_object` 实际装配到 outbound request，首个 attempt accepted。 |
| 五类 persistence 与 accepted evidence fact | PASS | baseline candidate/Memory 覆盖 session summary、accepted evidence fact、answer anchors、forward intent、reference continuity；事实引用 accepted evidence ref。 |
| `session_summary:null` clear | PASS | `evidence/05-deepseek-replacement-constrained`：candidate 为 `session_summary:null`，Memory owner 清除 summary。 |
| Rolling current replacement / Host omitted labels | PASS | 当前 21.7% 事实替换旧结论；Host omission 覆盖旧 summary、旧 answer anchor、prior bank anchor、旧 forward intent；旧标签不进入活动 semantic projection。 |
| Artifact / Memory / post-compact RunInput / reconnect | PASS | accepted artifact、Memory 与 ordinary system projection 都保留当前事实；`evidence/07-deepseek-reconnect` 在新进程复用同一 session，未恢复旧结论。原始 source boundary 中保留的历史文本仅用于 audit。 |
| Cap-constrained replacement / usage audit | PASS | constrained replacement：evidence `1/1, 28/160`、answer `1/1, 36/160`、reference `1/1, 3/160`、summary `0/160`；所有实际 usage 均在 owner cap 内。 |
| Same-boundary bounded repair | PASS | `evidence/06-deepseek-bounded-repair`：attempt 1 为有效 JSON，但 answer anchor 按 owner 规则计为 title 7 + newline 1 + detail 28 = 36 chars，因 `36 > 30` 而 rejected；attempt 2 绑定同一 canonical operation/input boundary 后 accepted。 |
| Prompt-injection material boundary | PASS | system prompt digest 在 attempts 间保持一致；业务 marker/pressure text 只在 delimiter 包围的不可信 material 中，未进入 instruction owner。 |
| Failed compact does not pollute Memory | PASS | `evidence/08-deepseek-exhausted-fallback`：2 rejected + single failed、无 compact artifact、latest compaction ref 为 null、semantic Memory 为空；只执行确定性 fallback。 |
| F11 successful compact identity | PASS | 各 evidence 下 public Tool Trace JSON/Markdown 包含 provider/model/request id availability/value、manifest/input/response binding 与 terminal identity。 |
| F11 successful-response-then-rejected identity | PASS | Mimo 与 DeepSeek exhaustion、DeepSeek repair attempt 1 都保留 response identity 并绑定 rejected terminal。 |
| Public/canonical equality | PASS | 所有导出的 response equality 均 exact match，`finding_count=0`；F11 证据来自 public Tool Trace resolver，未读取 private SQLite 冒充 public。 |

## Provider request 与 attempt binding 摘要

- Mimo provider request id：provider 未提供，public availability=`unavailable`、value=`null`；该缺失被原样记录，没有伪造替代 id。
- DeepSeek baseline request id：`6d77593ad5062e3574fb12fc16e3a2a0`。
- DeepSeek replacement request id：`c9d4f3af36ad5da2cb56db62b6a0d270`。
- DeepSeek repair request ids：attempt 1 `4a4380b02cbee4a0bd65d30442942191`，attempt 2 `212d4b6b36f08d21eb80468e26d68204`。
- DeepSeek exhausted request ids：attempt 1 `b4dda4a29787ce5145a895986600a038`，attempt 2 `2d71236573874246e2ddeb3bbe40be04`。
- DeepSeek repair 的 canonical request owner 是 `CONTEXT_COMPACTION_REQUESTED` operation `event-context-compact-requested-7aea6b1297414d9fb79656dd80b254ff`，其 `payload.frozen_material_list_digest=sha256:b798e8e51bb7e3a9f16c5f27a2e55cf11ec3e43c2a4c3a55de873a786bfe25ee`；attempt 1 与 attempt 2 均绑定该 operation，repair 只改变 self-contained feedback 与 whole-candidate replay。每个 attempt 的完整 manifest ref/digest、input identity、response identity 与 terminal event id/sequence 均保存在 public JSON/Markdown，不以本摘要取代 canonical evidence。
- `SMOKE ASSEMBLY compactor_model_id=mimo-v2.5-pro-plan` 是 assembly 配置 selector；DeepSeek workspace 的 `config/models.json` 令该 selector `extends=deepseek-v4-flash`。actual provider/model truth 由 `provider-identity.json`、`compactor-attempts.json`、public Tool Trace 与 canonical terminal 共同给出，为 `deepseek/deepseek-v4-flash`；不能从 selector 字符串反推真实调用身份。
- immutable bundle 内的 `observed-report.md` 已由 root `digest.json` 封存，不得回写；本 repo artifact 修正与 `docs/reviews/pr-190-f11-f12-s4-evidence-fix-20260806.md` 共同构成可审计勘误。

## Secret scan 与 workspace publication boundary

- 最终发布 evidence tree：`160` 个文件（含 self-excluded `digest.json`）。
- credential source：`2` 个，即 `MIMO_PLAN_API_KEY` 与 `DEEPSEEK_API_KEY` 的运行时值；报告不记录其值。
- exact credential findings：`0`。
- Authorization/Bearer/API-key pattern findings：`0`。
- 机器可读报告：`metadata/secret-scan.json`。
- 四个 task-created private Host SQLite 含 resolved credential snapshot，且不是 F11 public evidence。它们在 size/SHA-256 落盘后移至同级受限 quarantine：`/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY-private-sqlite-quarantine`。审计映射位于 `metadata/workspace-private-db-exclusion.json`，quarantine 不属于发布 root/digest。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`：`36 passed, 3 warnings`。
- `source .venv/bin/activate && pyright`：`0 errors, 0 warnings, 0 informations`。
- Mimo 与 DeepSeek 本轮均真实可用；无 provider unavailable、timeout 或 API rejection。观察中的 rejected 均是预期的 owner semantic/cap rejection。
- repo diff 仅应包含本 observation artifact 的勘误、双路 review/裁决输入和 durable fix artifact；没有生产代码、oracle、scenario、registry、README 或测试变更。

## Residual risk / pending decision

- Formal oracle 仍为 PENDING，必须由后续 gate 独立执行和裁决。
- reconnect 中旧数值仅以“已失效历史值”出现在回答与 raw source audit 中；它没有成为活动 Memory/RunInput 结论。双路 review 应区分 raw history preservation 与 semantic reintroduction。
- DeepSeek repair 覆盖的是计划允许的 valid-JSON cap rejection → repair accept 分支；bounded exhaustion + fallback 由独立 DeepSeek fresh workspace 覆盖。
- evidence root 的 private SQLite 被明确排除以满足零凭据发布约束；其哈希映射可审计，但 quarantine 本身不是 public evidence，也不在 root digest 内。

本 artifact 到此停止在总控双路 re-review gate，不推进 oracle，不调用 reviewer，不 commit 或 push。
