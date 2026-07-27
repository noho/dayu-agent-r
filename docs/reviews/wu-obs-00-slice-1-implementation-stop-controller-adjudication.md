# WU-OBS-00 Slice 1 Implementation Stop Adjudication

```text
status=pass-to-review-with-acceptance-blocked
work_unit=WU-OBS-00
slice=S1
implementation_artifact=docs/reviews/wu-obs-00-slice-1-implementation-codex.md
next=AgentMiMo + AgentDS dual code review
```

## Controller decision

AgentCodex 已完成 Slice 1 代码、白名单测试、逐文件覆盖率、targeted/full pyright、静态审计与只读
smoke，并以 `blocked` 停在 code review 前。Controller 将该状态拆为两个独立问题：

1. 当前 `workspace/.dayu/host/dayu_host.sqlite3` 的 `PRAGMA user_version=20`，而当前代码的
   fresh-schema owner 要求 `24`。这是 live validation environment blocker，不是允许通过
   compatibility reader、raw SQLite、跳过 schema validation、cold-only fallback 或修改
   producer/schema 语义修复的 Analyzer 缺陷。
2. `tests/host/test_package_exports.py` 未在 accepted Slice 1 allowlist 中，但新增三个
   `dayu.host` public exports 后，该 owner-level export contract test 必然需要同步。这是计划
   文件清单遗漏，不构成保留旧断言或增加兼容导出的理由。

Code review 是只读 gate，能够在不修改 live workspace、不绕过 strict schema 的前提下继续验证实现
正确性。因此 Controller 允许进入 AgentMiMo / AgentDS 双路 code review；Slice 1 acceptance、
保护提交与 Slice 2 仍冻结。

## Frozen boundaries for review

- 评审基线为 accepted plan commit `e1799abc3341872ba19ff609de15b236813a3533` 到当前
  worktree 的 Slice 1 diff。
- reviewer 必须核对 public Source 五字段、Host-internal lock owner、hot-first transaction、
  same-handle exact-prefix、strict parser/digest/ref/join/resolver、物理只读 SQLite 与
  fail-closed error taxonomy。
- reviewer 必须区分代码 finding、验证环境 blocker 与测试 allowlist 遗漏；禁止把 schema 20
  当成兼容读取需求。
- 若后续 fix gate 需要同步 public export 集合，Controller 预先允许只修改
  `tests/host/test_package_exports.py` 中对应 owner-level expected set；不得借此扩大 production
  scope。
- 当前真实 workspace 不执行 recreate、migration、bootstrap、DDL 或 write。若 Slice 1 最终
  acceptance 仍要求 schema 24 的 live success smoke，必须取得用户对该真实 workspace 的明确
  处置授权，或通过正式 plan amendment 改变验收条件。

## Evidence

- focused tests：`111 passed`。
- targeted pyright：`0 errors, 0 warnings, 0 informations`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- 8 个修改 production Python 文件的 branch coverage 均不低于 `81%`。
- 排除 allowlist 外旧 package-export test 后的 Host regression：
  `2281 passed, 2 skipped, 6 deselected`。
- live smoke fail-closed：
  `HostSchemaMismatchError(expected fresh schema 24, got 20)`。
- live smoke 前后 cold/DB hash、mtime、size、row count 与 schema version 均不变，
  `inputs_unchanged=True`。

## Stop / next

当前不是 implementation acceptance pass。下一 gate 仅为双路 code review；review 完成后由
Controller 合并 findings，并决定 fix/re-review 与 live validation blocker 的最终处理。
