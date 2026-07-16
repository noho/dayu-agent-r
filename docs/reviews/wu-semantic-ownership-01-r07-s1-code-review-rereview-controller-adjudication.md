# WU-SEMANTIC-OWNERSHIP-01 R07-S1 code re-review Controller adjudication

## 1. 结论

- work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU `R07`，
  checkpoint `S1`；不是新 WU。
- AgentMiMo：
  `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-mimo.md`，**PASS**。
- AgentDS：
  `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-ds.md`，**PASS**。
- Controller verdict：**PASS / R07-S1 COMPLETE**。
- accepted finding ledger：`R07-S1-CR-F01`、`R07-S1-CR-F02`、`R07-S1-CR-F03`、
  `R07-S1-CR-CV-F01` 全部 CLOSED；new accepted finding `0`；blocker `0`。
- 按 accepted plan §7.2 / §10.2，S1 是累计 working-tree checkpoint，不创建 S1 accepted commit；
  下一 gate 是 AgentCodex `R07-S2 persisted published revision + atomic stable snapshot`
  implementation。

## 2. Accepted findings 最终状态

| finding | 最终状态 | 双路证据 |
|---|---|---|
| `R07-S1-CR-F01` complete destructive-cleanup preflight | CLOSED | filing/processed/rejected whole-candidate validation 均在首次 mutation 前完成；missing/corrupt/mismatch/symlink/unexpected evidence fail closed，无 partial delete |
| `R07-S1-CR-F02` `begin_batch` primary-error preservation | CLOSED | journal/descriptor/copy primary 不被 staging cleanup 或 writer release 替换；active maps 只在成功后发布；双失败只附加 typed/path-free note |
| `R07-S1-CR-F03` raw filesystem locator boundary | CLOSED | owner I/O helpers、batch/recovery/maintenance、typed inventory 与 runtime-lock adapter 均不把 workspace/private locator 投影到 public exception |
| `R07-S1-CR-CV-F01` complete exception graph leakage | CLOSED | raw cause/context 不再可达；path-free cause 保留 subclass/errno category；三个 terminal note 只含 action/type/errno；递归 graph/traceback smoke 通过 |

两路 reviewer 均完整检查了 Controller 初始 rejected ledger，并确认 11 项 rejected alternative
没有被误实现。S1 handoff contract 满足：source/processed/blob/rejected/maintenance/company/meta/
manifest/recovery 均由 descriptor + private locator owner 覆盖，未发现 raw external identity path join。

## 3. Reviewer observations 裁决

### MiMo OBS-1 — `_require_copyable_ticker_tree` 的 `rglob("*")`

- 裁决：`NO ACTION / NOT A FINDING`。
- 原因：该 I/O 位于 `begin_batch` 初始化 try 内，唯一 public exit 由同一 transaction owner 的
  outer `except` 捕获；`OSError` 随即通过 `_project_filesystem_error` 与
  `_raise_path_free_error` 投影。没有直接代码反例表明 raw locator 可跨 boundary，单独再包一层会
  重复 owner 而不改变 contract。

### MiMo OBS-2 — `_write_json(payload: Any)`

- 裁决：`NO ACTION / OUT OF ACCEPTED FINDING SCOPE`。
- 原因：签名是 transition base 前既有代码，本 S1 没有新增或改变该 public/internal typing
  contract；full pyright 为 0。用户明确禁止修改 accepted findings 无关的既有代码，当前 gate
  不借 private-locator fix 扩张 JSON typing refactor。若未来 owner 变更触及该 contract，仍受
  AGENTS.md 禁止 `Any` 的规则约束；本轮不创建新 WU 或 residual issue。

### DS residual observations

- `_ensure_identity_directory` TOCTOU、Unicode line separators 与 list duplicate detection：均为
  Reviewer 明确的低风险继承 observation，没有当前可达 correctness/security failure；production
  caller 受 writer/publication lock 约束，`pathlib` 不把这些 Unicode 字符解释为路径 separator。
- `edgar` 三个 deprecation warning 与 full Ruff 152：既有环境/仓库 baseline，S1 未扩散。
- plan §1.1 的 Service/Runtime full-suite ledger：由原 owner 与 umbrella control 继续追踪；当前
  exact validation matrix 没有新增 failure，不把它转成 R07 code finding。

以上均不进入 fix gate，不允许留一个“后续优化”式 accepted finding。

## 4. Controller 复核

Controller 与两路 reviewer 均独立执行四个 exact test files；Controller 结果为
`363 passed, 3 warnings`。Controller 另通过：

- 九个 production file 行覆盖率 `80.00%`–`96.08%`；
- full pyright `0 errors, 0 warnings, 0 informations`；
- changed-scope Ruff `All checks passed`；
- full Ruff 既有 `152` fingerprint，未扩散；
- `git diff --check`；
- raw projection/note、runtime lock adapter、identity/path/AST 与 deferred-scope scans；
- 真实 Unix-domain socket complete exception-graph smoke：`context_none=True`、
  `graph_leak=False`、`raw_node_reachable=False`。

安全行为保持：path containment、symlink rejection、filename/URI escape rejection、atomic
write/fsync、R06 writer mutex/publication guard/journal recovery/primary-cause ordering 均未删除；
本 S1 仅把 external identity 映射到 storage-owned private locator，并关闭 public error locator
泄漏。没有统一 tool authorization framework，也没有 Issue 142/151/175/177/178 实现。

## 5. 下一 gate 与授权边界

授权 AgentCodex 按 immutable accepted plan §7.2 实施累计 `R07-S2`：persisted published revision、
atomic stable snapshot、preprocess/SEC fiscal/active 6-K snapshot consumers及真实 filesystem
concurrency/cleanup tests。S2 exact cumulative allowlist 与 targeted nodes 以 plan §7.2 为准。

仍不授权：S1/S2 accepted commit、S3、R08+、README/design/control 的 agent 修改、deferred Issue、
统一 authorization、stage/commit/push/PR。S2 完成后必须由 Controller 验证并进入双路 complete
cumulative S1+S2 code review；只有 S3 final tree 通过后才可裁决 R07 accepted implementation
commit。
