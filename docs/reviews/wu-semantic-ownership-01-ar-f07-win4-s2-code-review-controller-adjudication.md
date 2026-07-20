# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S2 Code Review Controller Adjudication

## Gate 与 immutable target

- Active work unit：`WU-SEMANTIC-OWNERSHIP-01` umbrella overdesign remediation continuation。
- Gate：WIN4-S2 dual complete code review adjudication。
- Entry commit：`e34edfa39f244d736aeaf8b9ea82ff9152698b2b`（S1 accepted commit）。
- Implementation target：`dayu/cli/init_environment.py` 与 `tests/cli/test_init_environment.py` 相对 `HEAD` 的 working-tree diff。
- Code/test binary diff SHA-256：`939ad028fcad225f08f4efe0a116984a88abc421ef32b5e043c7d3a601ac9eea`。
- Production file SHA-256：`ee23856d43c70b714250429b81fbc000eb4d24c74d243c4dcedb175f6beee35e`。
- Test file SHA-256：`7b772ac1e465caad06dd1a3602b2ec019d8e96cf30fee6332595c5cd083cd4a2`。
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-implementation-codex.md`，SHA-256 `1e2a8a418d2375dc5ab10d81cbcc1ecba225806ef9ee98d9b6fa2f920d02187c`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-controller-validation.md`。

## Review evidence

- AgentMiMo：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-code-review-mimo.md`，SHA-256 `dfe93b67b8e0537bcd2109e7a77a0be407bf11ac7df1f61c5edd3f371bff27ae`，结论 `PASS / 0 material finding`。
- AgentDS：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s2-code-review-ds.md`，SHA-256 `ff3a1ff5e2b3a245b5c43f94844fe47704f10b2d48ed0c035f8f717a177ac6a5`，结论 `PASS_LOCAL_CODE_REVIEW / NO_BLOCKERS`，并提出两项 LOW candidate。

两路均确认 S2 production owner 已显式拥有 `setx` argv、三路 native `DEVNULL`、非 stdio handle 关闭、单次 30 秒 timeout 与 native outcome 到 names-only result 的投影；没有 retry、raw exception 格式化、value/argv 披露、提前环境注入、兼容 shim 或 deferred-scope 实现。

## Candidate adjudication

### DS S2-CR-F01：REJECTED / FACTUALLY CONTRADICTED

候选声称 Windows Python 3.11.0–3.11.3 在重定向标准句柄时使用 `close_fds=True` 会抛出 `ValueError`，并据此建议把项目最低版本收紧到 3.11.4。该前提与 CPython 官方真源直接矛盾：

- Python 3.11 `subprocess` 官方文档在 Windows `close_fds` 条目明确记录：自 Python 3.7 起，重定向标准句柄时可将 `close_fds` 设为 `True`：<https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen>。
- Python 3.7 What's New 同样记录该 Windows 行为从 3.7 起成立：<https://docs.python.org/3/whatsnew/3.7.html#subprocess>。

因此当前 `requires-python = ">=3.11"` 与 S2 实现没有候选所述的 patch-version contract 缺口。不得修改 `pyproject.toml`、README 或 S2 implementation，也不得把错误的版本收紧作为后续工作。

### DS S2-CR-F02：REJECTED / REDUNDANT CARTESIAN TEST MATRIX

候选承认当前 correctness 没有缺陷。直接代码证据是：

- `OSError` 与 `TimeoutExpired` 各自的精确 exception branch 已由 middle-index owner tests 直接执行；
- first-index 的 `FAILURE`、空 `written_names`、全量 `unwritten_names` 状态转换已由 nonzero-returncode owner test 直接执行；
- 三条 native failure 输入共同调用同一个 `_windows_failure_result`，exception type 与 index 的组合没有独立生产分支或额外业务语义；
- owner branch coverage 已为 93%，严格 recorder、no retry、no early injection 和 no-value-disclosure 均有直接断言。

再增加 `exception kind × first/middle index` 的笛卡尔积，只重复同一 helper contract，不关闭新的业务风险，反而会让 fixture 固化非语义组合。依照 umbrella 的 overdesign remediation 目标与 AGENTS.md 的 owner-level contract 原则，本候选不是 material finding，不修改测试。

### Open question：timeout 后 registry write

`setx` 在 timeout/terminate 竞争下可能已完成 registry write，accepted plan 与实现已明确“不声称 rollback”。这一事实不改变 typed names-only local observation，也没有可由 S2 owner 提供的原子 registry transaction。它不是当前 code finding；真实 Windows R12 仍按已接受计划验证 observable behavior，但不得把外部命令不具备的 rollback 语义加入当前实现。

## Final ledger

- Accepted code finding：`0`。
- Rejected reviewer candidate：`2`。
- Needs-evidence finding：`0`。
- Design contradiction：`0`。
- Local blocker：`0`。
- Current-slice product/test/README/workflow fix：`0`。
- Real Windows residual：`1`，分类仍为三 slice accepted 后由 Controller 执行的 `PENDING_RELEASE_BLOCKER`，不是本地 finding 或 waiver。

## Decision

`PASS / ACCEPTED_FINDING=0 / ZERO_CHANGE_FIX_CONFIRMATION_REQUIRED`

下一 gate 由 AgentCodex 对本裁决执行 zero-change fix confirmation，锁定 immutable code/test diff、review disposition、scope 与验证结果。Controller 独立复核后，由 AgentMiMo / AgentDS 并发完整 re-review；只有 re-review 关闭后才允许 S2 accepted local commit。
