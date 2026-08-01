# WU-CLI-INTERACTIVE-02 S5/F13 Code Review Adjudication

## Gate facts

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice：S5 / F13
- Accepted base：`ce7ef846f7b8aac2d0b942bb487819fe0210b746`
- Implementation artifact：`docs/reviews/gateflow-wu-cli-interactive-02-s5-implementation-codex-20260802.md`
- MiMo review：`docs/reviews/code-review-wu-cli-interactive-02-s5-mimo-20260802.md`
- DeepSeek review：`docs/reviews/code-review-wu-cli-interactive-02-s5-ds-20260802.md`
- Controller decision：`fix-required`
- Next gate：AgentCodex accepted-finding fix → MiMo/DeepSeek simultaneous re-review

## Controller direct validation

- Controller independently read the complete implementation artifact and inspected the 53-file diff against the accepted S5 allowed-file boundary.
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- Engine/Host owner-focused independent rerun：`570 passed`。
- `git diff --check`：pass。
- Current branch/HEAD remained `codex/interactive-oracle` / `ce7ef846f7b8aac2d0b942bb487819fe0210b746`；the pre-existing `stash@{0}` belonging to `phaseflow/wu-cm-01` was not touched by Controller.

## Finding adjudication

| Source | Finding | Controller status | Decision and direct reason |
|---|---|---|---|
| MiMo 001 | `runner_identity.py.__all__` omits `ProviderRequestIdAvailability` and `SuccessfulRunnerResponseIdentity` | `accepted-low` | Both are newly public Engine contract types and are already re-exported by `dayu.engine.contracts` and `dayu.engine`; leaving their owner module discovery surface incomplete is a real public-contract inconsistency. Add both names and an owner-level export assertion. |
| MiMo 002 | `context_events.py.__all__` omits `CompactorProposalManifestReference` | `accepted-low` | The type was deliberately moved to the durable event owner and is directly consumed as that module's public typed contract. Add it to the owner module `__all__` and test the owner export. Do not add an unrelated `dayu.host` package re-export. |
| DeepSeek 001 | Future circular-import risk after moving the manifest reference to `context_events.py` | `rejected-speculative` | Direct import execution and `tests/host/test_import_boundary.py` pass; the move fixed an actual cycle and current dependencies are acyclic. A comment or new `_compaction_manifest.py` module would be speculative scope expansion with no present defect. |
| DeepSeek 002 | Non-prepared `ContextCompactor` lacks prepared-request cross-validation | `rejected-non-finding` | The finding's own expected behavior assigns same-call identity ownership to the non-prepared compactor, and `CompactorProposal`/`ContextCompactor.compact()` already state that required contract. Only the prepared capability has an independently comparable `AgentRunRequest`; fabricating a comparison source for the plain port would violate semantic ownership. Durable builders additionally reject ordinary attempt/execution identities and identity-without-manifest publication. No compatibility/documentation expansion is accepted. |

## Review-process deviation

MiMo briefly ran `git stash` / `git stash pop` to reproduce the phase5 baseline. This violated the work unit's explicit no-stash state-protection rule and temporarily made the shared workspace unstable for the parallel reviewer. Controller immediately verified that the complete 53-file implementation set plus the implementation artifact was restored, branch/HEAD were unchanged, and no new stash remained; the unrelated pre-existing `phaseflow/wu-cm-01` stash remains untouched.

Because DeepSeek's first full-suite run overlapped that mutation, Controller rejected that run as evidence. DeepSeek then reran, on the stable restored workspace, full pyright plus 850 S5 owner-focused tests and the exact 33-file inventory; those stable results are the only DeepSeek validation accepted here. The process deviation is not a product finding, but it is retained as a durable Gateflow audit fact.

## Residual risks and scope

- The six phase5 `drain.dispatched == 0` failures remain classified as clean-base scheduler-test races; Controller and implementation independently reproduced the first failure from `ce7ef846`. S5 does not change scheduler timing or those assertion orders.
- The awaiting-entrypoint smoke still fails on clean base before reaching the S5 identity path because `callback_execution_port` is missing. S5 only performs its frozen required-constructor migration there.
- The five pairwise registry claim corrections and parser-derived inventory/readiness proof remain S6 work.
- Real successful provider compactor identity evidence, behavior item 29, and G06 remain S6/external validation work; deterministic fakes are not treated as that evidence.

No other accepted findings or unclassified S5 residual risks remain at this gate.

## Decision

S5 code review does not pass yet. AgentCodex must make only the two accepted `__all__` fixes and narrowly update owner-level export tests, then rerun the affected tests, full pyright, exact inventory, and `git diff --check`. Both independent reviewers must re-review the fixed workspace before the accepted S5 slice commit.
