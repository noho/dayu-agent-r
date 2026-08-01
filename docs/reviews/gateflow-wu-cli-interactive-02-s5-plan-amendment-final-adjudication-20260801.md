# WU-CLI-INTERACTIVE-02 S5/F13 Plan Amendment Final Adjudication

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：accepted-plan premise invalidation / amendment final adjudication
- Branch：`codex/interactive-oracle`
- Base HEAD：`331d38dcaeebe3a929b7fa52d4e161a1c6504c55`
- Controller decision：`pass / create accepted plan-amendment commit`
- Next gate：S5/F13 implementation

## 1. Durable artifact chain

- Proposal：`docs/reviews/wu-cli-interactive-02-s5-f13-plan-amendment-proposal-codex.md`
- MiMo initial amendment review：`docs/reviews/plan-review-20260801-214709.md` — `pass`
- DS initial amendment review：`docs/reviews/plan-rereview-wu-cli-interactive-02-s5-amendment-ds-20260801.md` — `pass-with-minor-observations`
- Controller finding adjudication：`docs/reviews/gateflow-wu-cli-interactive-02-s5-plan-amendment-review-adjudication-20260801.md`
- MiMo re-review：`docs/reviews/plan-review-20260801-215640.md` — `pass`
- AgentDS re-review：`docs/reviews/plan-review-20260801-215957.md` — `pass`

Live discovery confirmed MiMo ran in pane `ai-0:1.1` with `mimo-v2.5-pro` and AgentDS ran in pane `ai-0:1.5` with `deepseek-v4-pro`. Both re-reviews independently recomputed the inventory and reviewed the accepted fix.

## 2. Controller decision

The premise invalidation is accepted: making `FinalAnswerData.response_identity` and `EngineRunOutcomeFinalAnswer.response_identity` required, and changing `ContextCompactor.compact()` to a typed proposal, necessarily affects direct test constructors and typed-return consumers outside the original S5 test list. The production owner/files remain unchanged.

The amended S5 boundary is accepted because it is the exact required-contract closure:

- 35 `FinalAnswerData(...)` test constructors in 19 files;
- 4 `EngineRunOutcomeFinalAnswer(...)` test constructors in 3 files;
- 7 `ContextCompactor` typed-return files;
- 25 unique files total, of which 5 were already allowed and 20 are newly enumerated mechanical test/test-support closure;
- no alias constructor, hidden factory, mock/autospec return, or additional production owner was found.

The amendment does not relax F13. Every constructor must provide a typed same-source identity; `FakeContextCompactor` owns its safe synthetic proposal identity; candidate-only helpers do not fabricate Engine identity; candidate-transforming fakes preserve the paired identity; no optional/default/compatibility seam is allowed.

## 3. Finding status

| Finding | Final status | Evidence |
|---|---|---|
| DS OBS-001 | `accepted / fixed / re-reviewed` | Plan §10.5 now explicitly states that `tests/host/fake_compaction.py` is verified through its listed consumers plus full pyright, while §9.3 remains the sole identity-rule owner. Both re-reviews passed. |
| DS OBS-002 | `rejected-invalid-premise / closed` | `tests/host/test_compaction_terminal.py` exists at the accepted S4 HEAD and has no FA/OA/CR hit; pre/post inventory remains fail-closed. |
| DS OBS-003 | `rejected-already-covered / closed` | `test_compaction_contract.py` is already a CR file; §9.1 and §9.3 already require proposal unwrapping and paired-identity preservation. |
| MiMo material findings | `none` | Initial review and re-review were both clean pass. |

No accepted finding remains open.

## 4. Validation and scope

- Controller and both reviewers independently confirmed `35/19`, `4/3`, `7`, and the 25-file union.
- `git diff --check` passed after the accepted fix.
- Only the S5 plan and review artifacts changed; no production code, test code, README, design, oracle, or scenario file changed in this amendment gate.
- No implementation pytest, pyright, coverage, or provider smoke was claimed in this plan-only gate; those remain mandatory in S5/S6.
- The erroneous first MiMo artifact that reviewed the whole F01-F13 plan instead of this amendment was excluded and removed before commit.

## 5. Residual risk and next gate

- Classified external risk：real successful compactor provider identity evidence remains for behavior item 29 / later G06 calibration; deterministic fake identity cannot close it.
- Implementation risk：HEAD drift or new constructor hits are fail-closed by the required pre/post inventory rescan.
- Unclassified residual risk：none.
- Next gate：create the accepted plan-amendment commit, then dispatch AgentCodex to implement only S5/F13 from that commit. No push or PR occurs at this gate.
