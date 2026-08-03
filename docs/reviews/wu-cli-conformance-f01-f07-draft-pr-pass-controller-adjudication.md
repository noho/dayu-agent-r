# WU-CLI-CONFORMANCE-F01-F07 — Draft PR Pass Controller Adjudication

## Scope

- Gate: `draft-PR-pass`
- Pull request: PR 190
- URL: `https://github.com/noho/dayu-agent-r/pull/190`
- Branch: `codex/interactive-oracle` -> `main`
- Accepted PR-review commit and exact implementation target:
  `58aeb7b377ef1857ad2a0a919c47556fdb3fa081`
- Exact-head evidence artifact:
  `docs/reviews/wu-cli-conformance-f01-f07-post-pr-fix-evidence-codex.md`
- Immutable evidence bundle:
  `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-post-pr-fix-20260803T041030Z-58aeb7b377ef/bundle`
- Bundle digest:
  `ab3f6ae5f4b5b76d768e0968d76ee83eca50d99fa8458b477e42d0c820a1e883`

Controller 逐项核验 entry criteria、review closure 与 bundle objective facts；不会以
Agent 自报、两路结论一致或单一 exit code 代替证据。

## Draft PR entry criteria

| Criterion | Direct evidence | Decision |
|---|---|---|
| Existing PR identity | GitHub readback：PR 190、OPEN、draft、base `main`、head `codex/interactive-oracle`、URL 正确 | PASS |
| Branch / remote identity | accepted PR-review commit `58aeb7b3` 已 push；本地 HEAD、`github/codex/interactive-oracle` 与 evidence detached target 三者一致 | PASS |
| Plan and slice chain | accepted plan、S1-S8、S3B-S3D 与 integration corrective commits/artifacts 均在 PR history | PASS |
| Dual review chain | plan review、每个 implementation slice review、aggregate deepreview 与 PR review 都有 MiMo/DeepSeek durable artifacts和 Controller 逐项裁决 | PASS |
| PR-review accepted findings | MiMo-01 canonical drop order、MiMo-02 attachment cleanup、DS-D-001 compact-input dual projector 均经 fix 和双 re-review标记 `已修复` | PASS |
| Accepted PR-review commit | `58aeb7b377ef1857ad2a0a919c47556fdb3fa081`，无 rebase、force-push 或历史重写 | PASS |
| Final push after PR review | remote-tracking ref 与 PR head OID 均为 `58aeb7b3` | PASS |
| Exact implementation evidence | 新 full-real bundle target 精确为 `58aeb7b3`，真实 Mimo / `mimo-v2.5-pro`，fake provider=false | PASS |
| Frozen truth | oracle、scenario、handbook SHA-256 分别为 `f9972d...`、`7f283b...`、`a24118...`，与冻结 baseline 一致 | PASS |
| Local quality gates | final full pytest `6605 passed, 10 skipped, 6 deselected`；full pyright 0；affected/owner 1132 passed；CLI coverage 87%，Host owner aggregate 84% | PASS |
| Bundle integrity | Controller 独立执行 743 项 checksum；`SHA256SUMS` digest 与 `bundle-digest.txt` 精确一致；742-index entries；writable paths=0 | PASS |
| Secret boundary | final scan 741 files，finding files=0，未持久化 secret value；raw credential carrier 在必要投影后按清单删除 | PASS |
| GitHub checks | `statusCheckRollup=[]`，只裁决为 zero/no checks，不称为 CI pass | PASS WITH EXPLICIT ABSENCE |

## Exact-head F01-F07 disposition

| Finding | Status | Semantic owner and accepted signal |
|---|---|---|
| F01 | PASS | CLI parser/public surface owner；81 actions 无全局 config、四份 help 零入口、七条 removed-option argv 均 exit 2、active source零入口。 |
| F02 | PASS | `dayu.cli.composer` external-editor/binding owner；missing/non-executable/spawn failure 均保留 draft、无 Run、回 REPL、terminal restored。 |
| F03 | PASS | CLI VT100/chord intent owner + Host Run lifecycle/canonical terminal owner；Escape、Ctrl+C、CSI、Alt、bracketed paste、provider/tool/closeout 和 terminal restoration 全部符合 frozen matrix。 |
| F04 | PASS | interactive attachment controller + stable pending mutation identity；READ_ONLY 不退出，close-before-fresh-attach，不原地升级，后续恰好提交一个 B Run。 |
| F05 | PASS | interactive scene manifest / effective tool assembly owner；effective set 无 preprocess，真实 download/list/read/section chain与生成物成功。 |
| F06 | PASS | typed runner-call trigger contract + canonical compaction terminal owner；四条 post-governance manifest 只用 `context_governance_resolved`，精确 outcome仍由唯一 terminal拥有。 |
| F07 | PASS | Host Context Governance accept barrier + committed accepted truth；真实 invalid repair/exhaust/fallback、三次 accepted compact、artifact/Memory/RunInput/EventLog/Tool Trace/terminal同源及跨轮 continuity 均通过。 |

## Controller bundle checks

- `shasum -a 256 -c SHA256SUMS`: 743/743 PASS。
- `shasum -a 256 SHA256SUMS`: `ab3f6ae5...a1e883`，与
  `bundle-digest.txt` 相等。
- `summary.json`: F01-F07 全 PASS，gate 为
  `EXACT-HEAD-EVIDENCE-PASS-READY-FOR-DRAFT-PR-PASS`。
- `f06-matrix.json`: 3 个 success terminal 与 1 个 failure terminal 后的 manifest
  全部使用 `context_governance_resolved`。
- `f07-matrix.json`: 真实 invalid 两次 rejection 后恰好一个 failure terminal；真实 success
  有 3 个 non-empty represented coverage 与 3 个 compact artifact，provider/model 均为
  Mimo / `mimo-v2.5-pro`。
- PR-review fix metadata：逆序 multi-drop round-trip、delayed join cleanup 和旧 projector
  active inventory三项均 PASS。

## Failed observations and residual owners

- 两个 init harness stdin 不完整的早期 run 已分别只读封存，未声称 scenario PASS，也未覆盖；
  主 bundle使用第三个全新 run id。
- F07 首次真实 success observation 未触发 compact，原样保留；后续 `-a2` stochastic
  observation产生 3 个 accepted compact，最终 F07 只从 accepted truth裁决。owner：真实
  provider/runtime nondeterminism；deterministic owner matrix与两套 observation共同降低风险。
- 首轮 full suite复现既有 public cancel test-order flake：1 failed / 6604 passed；隔离 1 passed，
  最终完整复跑 6605 passed。owner：Host public-smoke/test-runtime，独立 work unit稳定复现与定位。
- GitHub zero checks：repository CI/config owner；本 gate不伪称 GitHub CI pass。
- G01-G07 registry overall calibration：用户/Oracle controller；不改变 init/prompt/interactive
  command-level ready 或本次 implementation disposition。
- renderer target pin / formal scenario promotion：Oracle renderer/calibration owner。
- durable resolved Authorization projection：effective-execution durable projection owner；bundle只保留脱敏投影。

所有 residual risk 均有 owner；没有 blocking open question 或需要 implementation Agent重裁 frozen
behavior 的项目。

## Gate verdict

`DRAFT-PR-PASS — READY-FOR-FINAL-CLOSEOUT`

本 gate 没有 mark ready、approve、merge、request reviewers、创建新 PR 或删除 branch。

Next entry: 更新现有 PR 190 body为真实 review/evidence状态，提交并 push evidence/draft-pass
artifacts，然后执行 final closeout。
