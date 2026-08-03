# PR 190 Compactor LLM-facing Draft PR Pass

## Decision

- Gate：draft-PR-pass。
- Existing PR：[PR 190](https://github.com/noho/dayu-agent-r/pull/190)。
- Remote head：`670902f0f16c217e0646f922678482392a8ebc79`。
- Base/head：`main` ← `codex/interactive-oracle`。
- State：OPEN，`isDraft=true`，`mergeable=MERGEABLE`，`mergeStateStatus=CLEAN`。
- Verdict：`DRAFT-PR-PASS`，允许进入 final closeout。

该 verdict 只表示 Gateflow 的 plan、slice review、aggregate deepreview、existing PR review/fix/re-review、推送与精确状态核验均已完成；不宣告真实模型 behavior/formal conformance pass，不 mark ready、不 approve、不 merge。

## Accepted gate chain

- Plan：`a9383ee6`。
- S1 prompt trust/schema/example：`64aade07`。
- S2 internal feedback / minimal repair projector / exact caps：`e7db9474`。
- S3 deterministic/public smoke 与 immutable evidence：`69ab297b`。
- S4 docs 与 aggregate validation：`212f22af`。
- Aggregate deepreview：`0f7dc591`。
- Existing PR review/fix/re-review：`670902f0`。

两路独立 review 均形成 durable artifact；controller 对每项 finding/observation 单独裁决。最终 PR review 没有 accepted production finding，因此 fix gate 为 no-code-fix；两路 re-review 均为 pass。

## Exact-state evidence

- 本地 HEAD = remote-tracking head = GitHub PR head = `670902f0f16c217e0646f922678482392a8ebc79`。
- 当前工作树 clean。
- `main...HEAD` 左右计数：`0 44`。
- PR base OID：`113ea34d47b95812d79aa31705949bbb46bc6061`。
- GitHub checks：`no checks reported`；没有将其表述为 CI pass。
- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 与 `docs/cli_ci.md` 在 `7cf1027c..670902f0` 中零 diff。

## Final validation at accepted PR-review head

- Affected aggregate pytest：`365 passed, 1 skipped, 3 warnings`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- 两份 frozen JSON：`python -m json.tool` pass。
- `git diff --check`：pass。
- Prompt evidence bundle：`sha256sum -c SHA256SUMS` 13/13 OK。
- Evidence bundle：`/Users/leo/workspace/.dayu-cli-ci/pr190-compactor-llm-facing-20260803-182956/`。
- Evidence index digest：`sha256:dc7836bd631dc59a6665953fa988bce43228560c48a28a9ba6df9f419726d9a2`。

## Residual truth

- 本 follow-up 的真实 provider behavior 是 `not_observed`：Mimo 与 DeepSeek 均为 `network_unavailable`，没有非空 candidate。
- 因此真实 strict parse、governance accept、cap compliance、injection resistance 与 whole-candidate repair 不能写成 pass；deterministic matrix 只证明 owner contract。
- Formal conformance 与最终 PR 决策 owner：user / Oracle controller。
