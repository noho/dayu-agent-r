# WU-CM-01 Slice C Plan Fix/Reslice 复审

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan fix/reslice re-review |
| reviewed target | `docs/reviews/wu-cm-01-slice-c-plan-fix-codex.md` + `docs/host/wu-cm-01-conversation-memory-plan.md` Slice C 章节 |
| design source | `docs/host/design.md` 第 24/25 章 |
| control doc | `docs/host/issues-implementation-control.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-c-blocker-controller-adjudication.md` |
| reviewer | AgentMiMo |
| review date | 2026-06-04 |
| review posture | adversarial plan review |

## Assumptions Tested

1. 旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` 的所有直接 production consumers 已被纳入 Slice C。
2. Slice C 扩大后仍保持 `UI -> Service -> Host -> Engine` 分层与 `dayu.runtime` 层中立。
3. `MemoryProjectionPolicy` vNext 字段与设计真源第 3 章 / 第 24 章一致。
4. 测试矩阵覆盖直接 consumer、fail-fast config、prompt/fallback、durable/checkpoint、public smoke 边界。
5. 严格禁止旧 alias、compat wrapper/facade/re-export、旧 snapshot bridge、旧库兼容读取。
6. Slice D/E 重映射、Issue #80 映射、residual risks 与 control doc next gate 一致。

## Findings

### 01-未修复-低-CompactMaterialPack dataclass 字段迁移映射未显式指定

- **位置**: `docs/host/wu-cm-01-conversation-memory-plan.md` Slice C 实现边界
- **问题类型**: 契约缺失
- **当前写法**: plan 引用了旧 `CompactMaterialBlockKind` 到 vNext section 的映射表（`PINNED_STATE` / `WORKING_ASSUMPTION` 删除，`EVIDENCE_BACKED_FACT` 进入 `previous_compacted_view.evidence_backed_facts` 等），但未显式指定 `CompactMaterialPack` dataclass 本身的字段重命名：`stable_input` -> ?、`history_input` -> ?、`evidence_input` -> ?。同时 `CompactMaterialBlockKind` 的完整旧枚举（`PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY`、`ACCEPTED_TOOL_EVIDENCE`、`RAW_USER_TURN`、`RAW_ASSISTANT_TURN`、`CURRENT_INPUT_ANCHOR`）到 vNext `CompactMaterialSection` 的映射只有部分覆盖。
- **反例/失败场景**: implementation agent 可能把 `stable_input` 映射为 `previous_compacted_view` 而非 `trace_material` + `answer_material`，或保留 `CompactMaterialBlockKind.OPEN_QUESTION` 作为 vNext section。
- **为什么有问题**: `CompactMaterialPack` 是 Slice A 已实现的 dataclass，Slice C 需要修改其字段结构；若映射不明确，implementation agent 需要自行推断。
- **直接证据**: 代码 `dayu/host/compaction.py:1813` 仍有 `stable_input`、`history_input`、`evidence_input`；plan Slice A migration 表只列了部分 kind 映射。
- **影响**: implementation agent 可能在字段重命名上产生分歧，导致 review 返工。
- **建议改法**: 在 Slice C 实现边界补充 `CompactMaterialPack` 字段重命名表：`stable_input` -> 按内容拆分为 `trace_material` + `answer_material`（参考 design 24.3 material mapping），`history_input` -> `trace_material`，`evidence_input` -> `evidence_material`；补充 `CompactMaterialBlockKind` 全量枚举到 vNext section 的映射。
- **修复风险**: 低
- **严重程度**: 低

### 02-未修复-低-workspace config JSON 文件迁移未显式覆盖

- **位置**: `docs/host/wu-cm-01-conversation-memory-plan.md` Slice C 实现边界 / 测试命令
- **问题类型**: 契约缺失
- **当前写法**: plan 明确 `config_loader.py` 不接受旧 `max_evidence_backed_facts`、`max_working_assumptions`、`history_pool_*`、`stable_layer_*` 字段，且 `execution_profiles.json.memory_projection_policy` 使用 `_require_exact_fields` 验证。但 plan 未显式说明 `workspace/config/execution_profiles.json`（或等效 config 文件）需要同步更新为 vNext 字段集。
- **反例/失败场景**: implementation agent 迁移 `config_loader.py` schema 后，现有 workspace config JSON 仍含旧字段，`_require_exact_fields` 在运行时或测试中 reject 旧字段，但 plan 未将 config JSON 列入 allowed files 或 migration 步骤。
- **为什么有问题**: `execution_profiles.json` 是 workspace config 而非 source code，不在 Slice C allowed files 表中；但它的字段必须与新 schema 一致才能通过测试。
- **直接证据**: `dayu/runtime/config_loader.py` 的 `_parse_memory_projection` 函数使用 `_require_exact_fields` 验证字段集（代码 lines 1506-1556）。
- **影响**: 测试可能因 config JSON 字段不匹配而失败；implementation agent 可能遗漏 config 文件更新或在 plan 中找不到依据。
- **建议改法**: 在 Slice C 实现边界或测试命令前补充一条说明：`workspace/config/execution_profiles.json`（或测试 fixture 中的等效 config）的 `memory_projection_policy` 字段必须同步更新为 vNext 字段集。这不需要列入 allowed files（config 文件不是 source code），但需要作为 migration 前置步骤显式说明。
- **修复风险**: 低
- **严重程度**: 低

## Architecture Boundary Review

**结论**: 分层约束保持完整。

- `dayu/runtime/config_loader.py` 当前只 import `dayu.contracts` 和 `dayu.runtime._agent_policy_constants`，不 import Host / Service / Engine / UI / Fins。Slice C 只修改其 `MemoryProjectionConfig` dataclass 和 `_parse_memory_projection` 函数，不引入新的跨层依赖。
- `dayu/service/host_assembly.py` 当前 import `dayu.host.memory.MemoryProjectionPolicy` 和 `dayu.runtime.config_loader.RuntimeConfig`。这是正确的 Service -> Host + Service -> Runtime 方向。Slice C 只修改 `_memory_projection_policy_from_config` 的字段映射，不引入反向依赖。
- plan 明确要求 "Service / Runtime 迁移是旧 policy shape 的直接 consumer closure，不改变 `UI -> Service -> Host -> Engine` 分层，不允许 `dayu.runtime` import Host / Service / Engine / UI / Fins"。

## Overcoupling Review

**结论**: 扩大后的 Slice C 虽然涉及 ~10 个 production 模块和 ~20 个测试文件，但这些模块通过旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` shape 形成紧耦合 consumer graph。拆成双轨子 slice 需要兼容 wrapper，违反项目 no-compat 硬约束。当前切分是 pyright-clean vertical closure 的最小边界。

验证了所有 blocker 列出的直接 consumers 均已纳入：

| blocker 中的 consumer | Slice C allowed file | 验证 |
|---|---|---|
| `dayu/host/run_input.py` | `dayu/host/run_input.py` | 已纳入 |
| `dayu/host/compact_material.py` | `dayu/host/compact_material.py` | 已纳入 |
| `dayu/host/dispatch.py` | `dayu/host/dispatch.py` | 已纳入 |
| `dayu/service/host_assembly.py` | `dayu/service/host_assembly.py` | 已纳入 |
| `dayu/runtime/config_loader.py` | `dayu/runtime/config_loader.py` | 已纳入 |
| `tests/host/test_run_input_builder.py` | Slice C test list | 已纳入 |
| `tests/host/test_compact_material.py` | Slice C test list | 已纳入 |
| `tests/service/test_host_assembly.py` | Slice C test list | 已纳入 |
| `tests/runtime/test_config_loader.py` | Slice C test list | 已纳入 |
| `tests/host/test_admission_queue.py` | Slice C test list | 已纳入 |
| `tests/host/test_toolruntime_accept_barrier.py` | Slice C test list | 已纳入 |
| `tests/host/test_resolve_wait_command.py` | Slice C test list | 已纳入 |

## Optimal-Solution Review

**结论**: Controller adjudication 给出两条路径——扩大 Slice C 或拆双轨子 slice。plan 选择扩大 Slice C。该选择在项目 no-compat 硬约束下是唯一可行路径：双轨方案需要 "先引 vNext memory contract、后迁移 consumer"，但中间状态必然保留旧 production shape 的直接 consumers，导致 pyright 失败或需要兼容 wrapper。扩大 Slice C 虽然增加了单 slice 复杂度，但避免了兼容路径的风险。

## Overengineering Review

**结论**: 未发现过度设计。Slice C 的扩展是被 consumer graph 推动的最小闭包，不是主动抽象。

## Open Questions

无。

## Residual Risks

| 风险 | 严重程度 | owner / destination | 说明 |
|---|---|---|---|
| Slice C 范围扩大后 implementation / review 复杂度上升 | 中 | 当前 slice | 接受理由：旧 snapshot/policy consumer graph 已跨 Host prompt、dispatch、Service assembly 与 Runtime config，只有同 slice 迁移才能避免 pyright blocker 和兼容桥。 |
| vNext public contract 或 durable schema 在 design source 中不够具体 | 低 | design gate | 若 implementation 发现 design 第 24/25 章不足以裁决某个具体契约，必须回到 design gate，不得在生产代码中发明局部兼容分支。 |
| 完整 Conversation Memory eval benchmark | deferred | WU-CM-10 / GitHub Issue #80 | WU-CM-01 只保证可断言入口和初步 smoke。 |
| Cross-session User Profile Memory | deferred | WU-CM-11 / GitHub Issue #115 | WU-CM-01 只固定不混入 session memory 的边界。 |
| Deep historical recall / semantic search | deferred | GitHub Issue #39 | 第一阶段不做 prompt-conditioned recall、vector recall、LLM reranker 或 recall tool。 |

## Conclusion

**pass-with-findings**

2 条非阻塞 finding（均为低严重程度）：

1. `CompactMaterialPack` dataclass 字段重命名映射未显式指定——implementation agent 可从 design 24.3 和 Slice A migration table 推断，但显式补充可减少 review 返工。
2. workspace config JSON 文件迁移未显式覆盖——`_require_exact_fields` 的 fail-fast 行为会在测试中暴露此问题，但显式说明可避免 implementation agent 困惑。

无 blocking finding。Slice C plan fix/reslice 的核心判断——扩大 Slice C 为 pyright-clean vertical closure 是避免 pyright blocker 和兼容桥的唯一可行路径——经 code facts 验证成立。所有 blocker 列出的直接 production consumers 均已纳入 Slice C allowed files。分层约束保持完整。Slice D/E 重映射、Issue #80 映射与 control doc next gate 一致。
