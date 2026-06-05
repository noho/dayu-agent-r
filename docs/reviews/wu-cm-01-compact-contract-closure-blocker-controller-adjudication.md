# WU-CM-01 Compact Contract Closure Implementation Blocker Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure implementation blocker adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| implementation artifact | `docs/reviews/wu-cm-01-compact-contract-closure-implementation-codex.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`blocker-accepted`。

AgentCodex 的 blocker 成立，严重性评估正确。当前 Pre-Slice C plan 要求删除旧 production compact contract public symbols，并且要求 `tests/host/test_compact_artifact_store.py` 必跑；但 allowed production files 没有纳入仍直接承载旧 artifact writer 的 `dayu/host/compact_artifact.py`，也没有处理删除旧 public symbols 会牵连的 `dayu/host/memory.py` 与 `dayu/host/run_input.py` 旧依赖。继续 implementation 只能保留旧 public contract 或越过 allowed files，二者都违反当前 plan 与 AGENTS.md。

## Direct Evidence

| 证据 | 裁决 |
|---|---|
| `dayu/host/compaction.py` 仍定义并导出旧 `CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`PreservationEvidence`、`MinimumPreserveItemCandidate`、旧 `CompactQualityCheckResult` / `CompactQualityIssue` 等 public symbols。 | accepted |
| `dayu/host/llm_compaction.py` 同时保留旧 `compact()` 返回 `CompactionCandidate` 和 vNext `compact_request_vnext()` / `compact_vnext()`，形成 plan 禁止的双 public method closeout。 | accepted |
| `dayu/host/context_governance.py` 仍导出 `check_compaction_candidate`，旧 checker 仍依赖旧 candidate / quality issue。 | accepted |
| `dayu/host/compact_artifact.py` 仍以旧 `CompactionCandidate` 与旧 `CompactQualityCheckResult` 作为 artifact writer production request 类型，但该文件不在 Pre-Slice C allowed production files 内。 | accepted |
| `tests/host/test_compact_artifact_store.py` 是 Pre-Slice C 必跑测试；若不迁移 `compact_artifact.py`，artifact store closure 无法真实切到 vNext。 | accepted |
| `dayu/host/memory.py` 与 `dayu/host/run_input.py` 仍直接 import / 使用旧 minimum preserve 与旧 material block kind。删除旧 public symbols 会导致这些未授权文件无法 pyright-clean。 | accepted |

## Finding Adjudication

| finding | 裁决 | 理由 | plan fix 要求 |
|---|---|---|---|
| `dayu/host/compact_artifact.py` owner 缺失 | accepted | artifact store 测试已纳入本 gate，但对应 production writer 未纳入，形成直接 owner / test mismatch。 | Plan fix 必须把 `dayu/host/compact_artifact.py` 纳入 compact contract closure allowed production files，或重新裁决 artifact store 测试是否不属于本 gate；若保留测试，必须纳入 production writer。 |
| 删除旧 public compact symbols 会牵连 `memory.py` / `run_input.py` | accepted | `memory.py` 与 `run_input.py` 当前仍直接依赖旧 symbols；仅删除 `compaction.py` 旧 definitions 会破坏 pyright。 | Plan fix 必须明确这些依赖的 owner：要么把必要的最小迁移纳入 compact contract closure，要么降低本 gate 的旧 symbol 删除退出信号并说明为何不违反 design / AGENTS。不得通过 wrapper、alias、re-export 或旧 snapshot bridge 维持编译。 |
| `ContextCompactor` 双 public method closeout 仍受旧 callers 牵制 | accepted | `compact()` 旧返回值、`compact_request_vnext()` / `compact_vnext()` 并存不是测试 fixture 问题，而是 protocol 与 caller owner 未闭合。 | Plan fix 必须列出所有仓库内 production implementor / caller owner，并给出同 gate 收敛边界。 |

## Next Gate

进入 `WU-CM-01 compact contract closure plan blocker fix gate`。

AgentCodex 只应修改 plan / control doc / fix artifact，不进入 implementation。Plan fix 必须基于直接代码证据重新裁决 Pre-Slice C 的 allowed files、退出信号和测试矩阵，避免再出现 allowed files 与 pyright-clean closure 不一致。
