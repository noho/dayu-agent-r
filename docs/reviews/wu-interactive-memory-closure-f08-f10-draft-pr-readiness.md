# Interactive Conversation Memory Closure F08–F10：draft PR readiness

## Gate identity

- Gate：Gateflow `ready-to-open-draft-PR`。
- Work unit：修复 Interactive Conversation Memory closure 的 F08–F10。
- Branch：`codex/interactive-oracle`，不是 protected trunk。
- Local head：`0c6410420f9d702b1b7b189f0c4e4a8b575c614c`。
- Base：`github/main` / local `main` 均为 `113ea34d`，左右 divergence 为 `0/0`；base 是当前 branch ancestor。
- Existing PR：PR 190，`OPEN`、draft、base `main`、head `codex/interactive-oracle`，当前 remote head
  `2e7a01678677817aafd22603f03f17605aa9e39c`，URL：
  `https://github.com/noho/dayu-agent-r/pull/190`。
- Decision：**READY**。下一步 normal push accepted commits，然后将 existing PR 190 记录为 verified/reused draft artifact；
  不创建第二个 PR。

## Entry criteria

- Goal confirmation：用户已确认。
- Accepted plan checkpoint：`68ba403811fe98835ea93f8c715ca8ed7ba26164`。
- Accepted F08 slice：`47b6a2af`。
- Accepted F09 slice：`d04f7531`。
- Accepted F10 slice：`fd15b6601a985c538cdbe6a529af99d07c281a05`。
- Accepted aggregate deepreview：`0c6410420f9d702b1b7b189f0c4e4a8b575c614c`。
- 每个 slice 均已有 implementation、两路 code review、Codex fix/audit、两路 re-review 和 controller adjudication
  durable artifacts。
- Aggregate deepreview 已有两路独立 review、Codex fix/audit、两路 re-review 和 controller adjudication；没有 accepted
  finding、deferred finding、blocking open question 或 unclassified residual risk。
- 工作树在创建本 readiness artifact 前 clean；没有来源或 ownership 不明的 dirty change。

## Validation state

- focused owner：`489 passed, 1 skipped`。
- Host owner：`2385 passed, 1 skipped, 6 deselected`。
- focused coverage：`418 passed, 1 skipped`；六个 changed production owner 均 ≥80%，合计 85%。
- full pytest 最终绿色：`6639 passed, 10 skipped, 6 deselected`。
- full pyright：0 errors。
- changed Python Ruff、compileall、JSON validation、`git diff --check`：全部通过。
- active-cancel 首轮偶发时序观测已隔离通过并归属 work-unit 外 owner；没有在 F08–F10 中做 workaround。
- 五条正式 CLI scenarios 按 scope 禁止运行，明确由后续 Oracle 总控拥有。

## Frozen baseline

- `docs/cli_ci_oracles.json`：
  `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：
  `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：
  `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

三份 digest 与用户提供 baseline 精确一致。

## Docs and scope decision

- 已更新 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`、compaction prompt 与权威
  prompt manifest/hash consumer。
- `docs/engine/design.md`、`dayu/config/README.md`、根 `README.md`、`dayu/README.md` 未命中职责变化，保持不变。
- 不改变 v2 output schema、五类 Semantic Memory、provider/model、授权语义、fallback tiers 或其它 CLI command。
- 不运行正式 post-fix scenarios，不生成 observed-behavior/readiness proof。

## PR safety

- 只允许 normal push 到 `github/codex/interactive-oracle`。
- existing PR 190 必须复用；不新建 PR。
- 不 merge、approve、mark ready、request reviewers、close PR、delete branch、rebase、reset、rewrite history 或 force-push。
- push 后必须执行两路独立 PR deepreview、Codex fix/audit、两路 re-review、controller adjudication、accepted PR review
  checkpoint、final push、draft-PR-pass 和 final closeout。

## Residual risks

- 五条正式 CLI scenarios/readiness proof：`assigned to later approved work`，owner 为 Oracle 总控。
- active-cancel 非确定性时序若重复：`assigned to later work unit`，owner 为 `open_host` runtime/test。
- 没有 unclassified residual risk。

## Completion status

`ready-to-open-draft-PR` **PASS**。当前 next entry point：push accepted commits；随后验证并复用 existing draft PR 190。
