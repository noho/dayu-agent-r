# WU-CM-01 Slice C Plan Fix

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan fix/reslice |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-c-blocker-controller-adjudication.md` |
| author | AgentCodex |
| date | 2026-06-04 |

## 动机判断

动机成立。Host 设计真源第 24/25 章要求 Conversation Memory 是 EventLog read model，`ConversationMemorySnapshotVNext` 和 per-semantic `MemoryProjectionPolicy` 是 accepted compact、projection、prompt assembly 与 fallback 的同一生产契约。Slice C blocker 的根因不是实现困难，而是原 Slice C 只覆盖 memory durable/projection 局部，却要删除已经被生产路径直接消费的旧 snapshot/policy shape。

严重性没有被高估。直接证据显示旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` consumer 分布在 `run_input.py`、`compact_material.py`、`dispatch.py`、`service/host_assembly.py`、`runtime/config_loader.py` 以及多份 host/service/runtime tests。若仍按原 allowed files 删除旧字段，全量 pyright 必然在禁止修改的 consumer 上失败；若保留旧字段 alias、compat wrapper 或旧 snapshot -> vNext bridge helper，又违反 no-compat/no bridge/no old-field alias。

## 修订内容

本次选择扩大 Slice C 成 pyright-clean vertical slice，而不是拆成双轨子 slice。

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 将 Slice C 改为 `Memory Contract, Projection, Assembly And Config Closure`。
- 将原 Slice D 的 prompt / fallback closure 合并进 Slice C。
- 将原 Slice E 改为 Slice D public smoke / docs closure。
- 将 `dayu/host/run_input.py`、`dayu/host/compact_material.py`、`dayu/host/dispatch.py`、`dayu/service/host_assembly.py`、`dayu/runtime/config_loader.py` 纳入 Slice C allowed files。
- 将 `tests/service/test_host_assembly.py`、`tests/runtime/test_config_loader.py`、`tests/host/test_admission_queue.py`、`tests/host/test_toolruntime_accept_barrier.py`、`tests/host/test_resolve_wait_command.py` 等旧 snapshot/policy direct consumer tests 纳入 Slice C 测试边界。
- 明确 Runtime config loader 不接受旧 `max_evidence_backed_facts`、`max_working_assumptions`、`history_pool_*`、`stable_layer_*` 等旧字段。
- 明确 Service assembly 只能把 runtime typed config view 显式映射为 vNext Host `MemoryProjectionPolicy`。
- 明确禁止旧 policy field alias、旧 config field alias、旧 snapshot bridge、compat facade、re-export、extra payload、lazy import seam。
- 更新 Issue-80 / Design 24.7 映射、allowed files summary、测试矩阵和最终验证命令。

已更新 `docs/host/issues-implementation-control.md`：

- `implementation status` 改为 `slice-c-plan-fix-complete`。
- `next entry point` 改为 `WU-CM-01 Slice C implementation gate`。
- review artifacts 索引加入本 artifact。
- WU-CM-01 状态段落补充 Slice C plan fix/reslice 完成记录。

## 为什么能避免 Blocker

新 Slice C 把旧 snapshot/policy shape 的删除与所有直接 production consumers 迁移放进同一个 closure：

- `memory.py` / `durable/memory.py` 删除旧 snapshot 顶层字段后，`run_input.py`、`compact_material.py` 和 `dispatch.py` 会在同 slice 改为消费 vNext section。
- `MemoryProjectionPolicy` 字段迁移后，`service/host_assembly.py` 与 `runtime/config_loader.py` 会在同 slice 改为 vNext config schema 和显式 assembly。
- 旧 shape consumer tests 会在同 slice 更新，因此 `python -m pyright dayu/ tests/ utils/` 不需要依赖旧字段 alias 才能通过。
- 后续 Slice D 只做 public smoke / README 收口，不再承担删除旧 production contract 的风险。

这不是兼容策略。plan 明确要求旧字段 fail fast / 删除，不允许 wrapper、re-export、old-field alias、旧库兼容读取或旧 snapshot 到 vNext 的 bridge helper。

## 未触碰代码

本 gate 未修改 production code 或 tests。修改范围仅限：

- `docs/host/wu-cm-01-conversation-memory-plan.md`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-cm-01-slice-c-plan-fix-codex.md`

## 验证

已做文档核对：

- 对齐 `docs/host/design.md` 第 24 章 `ConversationMemorySnapshotVNext`、第 24.6 章 prompt assembly 固定顺序，以及第 3 章 `memory_projection_policy` vNext字段。
- 对齐 `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` 与 Controller adjudication 中列出的 blocker evidence。
- 核对 plan 中 Slice C allowed files、testing commands、allowed files summary、residual risks 与 control doc next entry point 已同步。

未运行测试或 pyright，因为本 gate 只修改文档，不修改生产代码或 tests。

## Residual Risks

- Slice C 范围扩大后 implementation / review 复杂度上升。该风险接受并留在 plan 中，原因是这是当前 consumer graph 下避免 pyright blocker 与兼容桥的最小闭环。
- Slice C implementation 仍可能发现 vNext public contract 或 durable schema 在 design source 中不够具体；若发生，必须回到 design gate，不得在生产代码中发明局部兼容分支。
- Public smoke、README 同步与最终 Issue-80 映射复核仍归 Slice D。
- 完整 Conversation Memory eval benchmark 仍 deferred-with-owner，owner 是 WU-CM-10 / GitHub Issue #80。
