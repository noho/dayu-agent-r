# WU-SEMANTIC-OWNERSHIP-01 P3-I Plan Re-Review (AgentDS)

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Gate: plan re-review
- Review target: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`（plan-fix 后版本）
- Fix report: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-fix-codex.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-ds.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-mimo.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-controller-adjudication.md`
- Review agent: AgentDS
- Timestamp: 2026-07-11T08:00:45+08:00

## Re-Review Objective

只验证 plan-fix 是否关闭 controller adjudication 中 accepted 的四条 findings，不实施，不修改文件，不 commit。若全部关闭且无新增 material plan blocker，verdict 为 pass。

## Accepted Findings Verification

### 1. MiMo F1 / DS M-F3 — Cursor Write Failure Policy

**Controller 要求**: propagate cursor write exception as local delivery persistence failure; do not catch and return render exit code.

**Plan 现状**:

- Public Contract 段（lines 99-101）明确写死：`advance_cli_terminal_cursor(...)` 异常必须传播为 local CLI delivery persistence failure，不得吞掉、不得返回 render exit code、不得转换为 Host terminal status。
- Public Contract 段（lines 100-101）记录了 trade-off：cursor 写入失败后已渲染 terminal 可能在下一次重连时重复显示，但重复显示优于静默隐藏本地持久化失败；cursor store 使用原子写入，corruption 不可预期。
- S2 step 1（lines 286-289）：prompt 路径 render 后 advance cursor，若 cursor 抛异常则 propagate。
- S2 step 2（lines 291-293）：startup reconnect 路径 for 循环中若 cursor 抛异常，"stop the startup reconnect path by propagating that local persistence exception"。
- S2 step 3（lines 297-299）：interactive repl 路径若 cursor 抛异常则 propagate。
- Risks 段（line 401）再次强调：不得 disguise、不得 swallow、不得 convert。

**判定**: ✅ CLOSED。Controller 的显式 propagate 策略已落实到 plan 的 Public Contract、三个调用点 implementation steps 和 Risks 段，语义一致，无歧义。MiMo 建议的 catch-and-return 方案已被 controller 明确拒绝，plan 未采纳该方案，与 controller 裁决一致。

### 2. MiMo F2 / DS M-F1 — README Narrowing Per-Command Checklist

**Controller 要求**: add concrete README target specification per command, including which user workflows must be removed or narrowed.

**Plan 现状**:

- S1 step 9（lines 177-180）新增三条 per-command target checklist：
  - `dayu-web`: 只保留真实 command/help 事实和真实 extras 安装事实；若 S1 未实现 Streamlit server / localhost workflow / Web UI task workflow，删除或显式标记为当前不可用。
  - `dayu-wechat`: 只保留 command/help 事实和 current-capability diagnostic；若 S1 未实现 login / run / daemon / service management / multi-instance workflow，删除或显式标记为当前不可用。
  - `dayu-render`: 只保留 command/help 事实和 current-capability diagnostic；若 S1 未实现真实 DOCX / HTML / PDF / Pandoc / browser conversion，删除或显式标记为当前不可用。
- S1 step 9（line 180）新增 README 审计要求：`rg "dayu-web|dayu-wechat|dayu-render" README.md` 后逐条审计，每一处 hit 必须与 restored module 行为一致，不得描述不存在的 workflow 除非显式标记为不可用。

**判定**: ✅ CLOSED。三个命令的 narrowing 边界已具体到 workflow 粒度，implementation agent 不需要自行做产品决策。审计步骤确保 README 与 restored module 行为一致。

### 3. MiMo F3 — Terminal Is None Negative Cursor Test

**Controller 要求**: at minimum, add one negative regression test proving local interrupt / terminal is None does not advance cursor.

**Plan 现状**:

- S2 step 7（line 307）："At least one negative local-exit test must prove no cursor advancement happens when `terminal is None`; extend or add a prompt SIGINT-before-run-id or equivalent local interrupt test that asserts the cursor record remains empty."
- S2 Tests / Validation Commands（line 327）：`test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor` 列入 targeted cursor regression 测试名。

**判定**: ✅ CLOSED。Plan 明确要求至少一个 negative test，给出了具体测试名和断言目标（cursor record remains empty）。

### 4. DS M-F2 — dayu.render Package-Data Non-Goal / Residual

**Controller 要求**: explicitly record that S1 does not create render resource files; package-data globs remain deferred render-capability risk.

**Plan 现状**:

- Non-Goals（line 66）："S1 must not create fake `dayu.render` CSS, HTML, Lua, DOCX, XLSX, Mermaid, or template resource files only to satisfy package-data globs. If a real renderer is not implemented in S1, package-data resource completion remains deferred render-capability work."
- S1 Propagation Audit（line 244）："Deferred render resources: if S1 does not implement real render behavior, `dayu.render` package-data resource files are not fabricated and remain a named render-capability residual for the future renderer owner."
- Risks（line 399）："S1 does not create fake `dayu.render` package-data resources. If real render behavior is not restored, completing CSS/HTML/Lua/template and conversion resource files remains deferred render-capability work."

**判定**: ✅ CLOSED。Package-data non-goal 在 Non-Goals、Propagation Audit 和 Risks 三处一致记录，implementation agent 不会误解为需要创建资源文件。

## New Material Issues Scan

对 plan-fix 后的完整 plan 做一次快速 adversarial scan，检查 fix 本身是否引入新问题：

- **Cursor write failure policy 一致性**: Public Contract 段写 propagate、S2 三个调用点都写 propagate、Risks 段写不得 swallow——全文一致，无矛盾。
- **README narrowing 边界**: per-command checklist 覆盖三个命令的主要 workflow 类别，审计步骤确保覆盖率。未发现过度删除或保守保留的歧义。
- **Terminal is None test**: 测试名和断言目标明确，与 S2 step 1 的 `terminal is None -> EXIT_KEYBOARD_INTERRUPT` 逻辑一致。
- **Package-data non-goal**: 三处记录措辞一致，不与其他 non-goal 冲突。
- **无新增 scope creep**: fix 未扩大 plan scope，未引入新文件、新依赖或新架构变更。
- **无新增 ambiguity**: 所有 fix 均使用确定性措辞（"must not", "propagate", "delete or mark explicitly unavailable"）。

**结论**: 无新增 material plan blocker。

## Verdict

**PASS**

四条 accepted findings 全部关闭，plan 现已 code-generation-ready。无新增 material findings。

## Review Metadata

- Review artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-rereview-ds.md`
- Verdict: pass
- Accepted findings verified closed: 4/4
- Open findings: 0
- New findings: 0
