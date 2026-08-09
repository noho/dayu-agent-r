# WU-CLI-CONFORMANCE-F01-F07 — accepted PR-review exact-head evidence refresh

## 1. 结论

- PR：190
- Branch：`codex/interactive-oracle`
- 唯一 target：`58aeb7b377ef1857ad2a0a919c47556fdb3fa081`
- Target state：controller HEAD、detached validation worktree 与本地 remote-tracking ref `github/codex/interactive-oracle` 三者均精确等于 target；启动时 controller worktree clean。
- Run id：`pr190-wu-cli-conformance-f01-f07-post-pr-fix-20260803T041030Z-58aeb7b377ef`
- Profile：`full-real`
- Provider/model：真实 Mimo / `mimo-v2.5-pro`；未使用 fake provider；Mimo 可用，因此未切换 DeepSeek。
- Primary verdict：`full-real-pass`
- Bundle：`/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-post-pr-fix-20260803T041030Z-58aeb7b377ef/bundle`
- Bundle SHA-256 digest：`ab3f6ae5f4b5b76d768e0968d76ee83eca50d99fa8458b477e42d0c820a1e883`

本轮只新增本 artifact 与 repo 外 evidence bundle；没有修改 production、tests、frozen registry/oracle/scenario/design 或既有 evidence bundle，没有 stage、commit、push，也没有执行 GitHub mutation 或读取 GitHub 新状态。

## 2. 冻结输入与 entry criteria

本轮先读取并复用以下语义真源，不重新裁决：

- `docs/cli_ci.md`
- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json` 的 `readiness_proof.init`、`prompt`、`interactive`、`post_fix_conformance_refresh`
- `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`
- `docs/reviews/wu-cli-conformance-f01-f07-s8-code-review-controller-adjudication.md`
- `docs/reviews/wu-cli-conformance-f01-f07-pr-review-controller-adjudication.md`
- 既有成功 bundle `pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle`

冻结 SHA-256：

| Input | SHA-256 |
|---|---|
| `docs/cli_ci.md` | `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82` |
| `docs/cli_ci_oracles.json` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` |
| `docs/cli_ci_scenarios.json` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` |

三份 readiness proof 均为 ready，post-fix refresh 明确要求 F01-F07。本轮没有把 implementation finding 改写成 oracle gap，也没有修改 frozen input。既有成功 bundle digest 复核仍为 `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`。

## 3. 执行身份与 objective evidence

`dayu-cli init` 真实选择 Mimo Token Plan 并成功生成 fresh template。所有 Python 命令先 `source .venv/bin/activate`，再把 `PYTHONPATH` 固定到 detached exact-head worktree；runtime identity 中 `dayu.__file__` 指向该 worktree。run-root `.venv` 复用 controller `.venv`，而 controller 在整个被测阶段 clean 且 HEAD 与 target 相同。

每条真实 lane 保留 terminal raw/text、command result 和 fresh workspace；裁决使用脱敏后的 Host/EventLog、Run/Attempt、Tool Trace、Conversation Memory、RunInput/runner-call manifest、SQLite payload projection与真实生成物，不使用 CLI 自报、单 exit code 或 mock runner替代。必要原始 durable carrier 在投影和核验后因含 resolved Authorization 被删除；删除清单和脱敏占位保留在 bundle。

完整命令与结果见 `bundle/metadata/command-manifest.md`；主要 validation 为：

| Validation | Result |
|---|---|
| PR fix focused owner tests | `2 passed` |
| PR fix 10-file affected suite | `453 passed` |
| Full affected/owner union | `1132 passed` |
| CLI affected coverage | composer 89%、run_keys 93%、session_execution 85%、aggregate 87% |
| Host owner coverage | compact_material 85%、compaction 84%、context_governance 89%、open_host 82%、aggregate 84% |
| Full pytest first run | `1 failed, 6604 passed, 10 skipped, 6 deselected`；如实复现既有 public cancel test-order flake |
| Flake isolated rerun | `1 passed` |
| Full pytest final run | `6605 passed, 10 skipped, 6 deselected` |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| Changed Python Ruff | `All checks passed!` |
| Compileall | PASS |
| JSON tool | 两份 registry 均 PASS |
| `git diff --check` / accepted HEAD diff check | PASS / PASS |

首轮 full suite 的唯一失败是 `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled`，观察值为 token cancel thread 记录两次而非一次。它没有被写成 pass；bundle 同时保存首轮失败、隔离通过和最终完整 suite 通过三个日志。最终 full-suite verdict 仅来自最终完整复跑。

## 4. F01-F07 disposition

| Finding | Disposition | Objective facts |
|---|---|---|
| F01 remove global config | PASS | root/init/prompt/interactive 共 81 个 scoped parser actions 中 `--config`/旧 config option occurrence 为 0；四份 help 0 命中；七个前/后置 argv 均 exit 2；active CLI/Service source scan 0。 |
| F02 explicit invalid editor | PASS | missing、non-executable、spawn failure 三类真实 PTY lane 都返回清晰错误、保留原 draft、回到 REPL；各 workspace Run/Attempt/Tool Trace 均为 0；退出码 0且 terminal flags 恢复。 |
| F03 graceful cancel and sequences | PASS | prompt/interactive 共 7 条 CSI/Alt/bracketed-paste sequence lane 成功且未误取消；4 条 pre-accept Escape/double Ctrl+C lane符合 0/130 语义；provider-wait、tool-execution、closeout 三条双 POSIX SIGINT lane各只有一个 `CANCEL_REQUESTED` 和一个 `RUN_CANCELLED`，exit 130；single Ctrl+C graceful closeout exit 0；全部 terminal restoration 通过。 |
| F04 READ_ONLY submit | PASS | B 在 A 存活时两次 READ_ONLY rejection，两个时点 Run count 均为 0且 B 仍在 REPL；A 成功并退出后，B 关闭旧 attachment、fresh attach 后创建恰好一个自己的 Run；最终总计两个 succeeded Run、两个稳定且互异的 attachment request identity，两个终端均恢复。 |
| F05 effective tools and real chain | PASS | Host effective tool schema 共 13 项且不含 `start_fins_preprocess`；真实 Mimo 三轮 succeeded，实际 durable request 包含 `start_fins_download`、`list_documents`、`read_section`（并观察到 `get_document_sections`）；下载/list/read 生成物清单和 SHA-256 已固化。 |
| F06 resolved trigger / terminal owner | PASS | successful workspace 有 3 个唯一 `CONTEXT_COMPACTED` terminal，failure workspace 有 1 个唯一 `CONTEXT_COMPACTION_FAILED` terminal；四个 terminal 后的 runner-call manifest 全部且只使用 `context_governance_resolved`；精确 outcome 仍由 canonical Context Governance terminal owner持有。 |
| F07 invalid/success/memory/tool continuity | PASS | 真实 invalid proposal 经 attempt 1、2 两次 accept-barrier rejection后形成唯一 failure terminal，`retry_repair_budget_exhausted=true`、fallback=`dispatch`，普通 Run最终 succeeded；真实 success chain形成 3 个 accepted compact、3 个真实 compact artifact，accepted coverage非空，provider/model identity为 Mimo/`mimo-v2.5-pro`。compact 后旧事实仍为 AAPL FY2025 net sales `$416,161 million`；新 scope follow-up 真实调用 `list_documents`、`get_financial_statement` 等工具并得到 operating margin `31.97%`。EventLog、Memory snapshot/items、RunInput/manifest、artifact和 terminal 同源交叉核对通过。deterministic malformed variants由 1132-test owner matrix覆盖。 |

真实 successful-chain 第一次 observation 的所有普通 Run虽成功，但没有产生 compact；该 observation 原样保留，未据 exit code报 PASS。随后按既有 accepted harness 的 `-a2` stochastic observation 得到 3 个 accepted compact；首轮和 `-a2` 两套 terminal/durable facts均在 bundle 内，最终 F07只依据 `-a2` 的 accepted truth 与 failure-cap workspace裁决。

## 5. PR-review 三项 Host fix

| Fix | Exact-head evidence | Result |
|---|---|---|
| PR-M01 reverse multi-drop | `test_accept_owner_canonicalizes_reverse_drops_for_committed_round_trip` 验证逆序 `T1,E1` 经 accept 后按 immutable root order成为 `E1,T1`，committed payload build/strict parse round-trip 后 candidate 与 dropped coverage 仍同源。 | PASS |
| PR-M02 delayed join failure cleanup | `test_managed_attachment_close_releases_resource_when_recovery_join_fails` 验证固定 join `RuntimeError` 下 native attachment `aclose()` 恰好调用一次且同一 join failure继续传播。 | PASS |
| PR-D01 single projector owner | active Python inventory 对 `conversation_compact_input_vnext_from_material_pack`、`_source_boundary_v2`、`_previous_source_kind_v2` 为 0 命中。 | PASS |

F05、F06、F07 的真实 provider/tool/frozen scenario行为与 frozen oracle一致，因此这三项 deterministic Host owner修复没有改变 provider identity、effective tool set、trigger/terminal owner或 accepted scenario语义。直接结构化证据见 `bundle/metadata/pr-review-fix-evidence.json`。

## 6. Secret、checksum 与 immutable seal

- Raw security inventory在删除前识别真实 Mimo Authorization；所有必要 durable facts先按字段投影并按 credential ref脱敏。
- Final secret scan：741 个 seal 前文件，exact credential 0、unredacted bearer 0、structured secret assignment 0、finding files 0；保留 73 个 `<redacted:...>` 审计占位。
- `bundle-index.json`：742 entries。
- `SHA256SUMS`：独立 `shasum -a 256 -c` 验证 743 entries 全部通过。
- `SHA256SUMS` 自身 SHA-256 与 `bundle-digest.txt` 都等于 `ab3f6ae5f4b5b76d768e0968d76ee83eca50d99fa8458b477e42d0c820a1e883`。
- bundle root、目录和文件 writable paths：0。

两份 init stdin 不完整的早期 run 已分别封存，未覆盖：

| Failed run bundle | Digest | Verdict |
|---|---|---|
| `...T040816Z-58aeb7b377ef/bundle` | `72ad0950bed00983a1cab361b6779a53019a62f5a366cfd109ad9ebb2721bc6e` | FAIL；未提交模型选择 |
| `...T040953Z-58aeb7b377ef/bundle` | `7e98bd28de828f5d1a68b63da9b99c0ca09b620b783b4bd1ff6d64d7bb41e1f5` | FAIL；Mimo已选，但可选 secret stdin提前结束 |

## 7. GitHub、README 与 residual risks

- GitHub checks：既有 accepted PR-review evidence记录为 zero/no checks；本轮遵守禁止操作 GitHub，没有重新查询或改变状态。`zero checks` 只表示没有 checks，明确不称为 CI pass。本 artifact 的 PASS是本地 exact-head full-real evidence verdict。
- README：本轮不修改 production/tests/config/入口或分层，只新增 review artifact；各 README 已由 accepted HEAD 的 PR-review fix更新，本 refresh 无新的 README 职责变化。
- 真实 provider输出具有通常的非确定性；owner为 provider/runtime。本轮以保留的首轮 no-compact observation、`-a2` accepted compact objective facts和 deterministic owner matrix共同约束，没有用重写 oracle、mock或丢弃失败 observation消除该风险。
- public cancel test-order flake仍归 Host test-runtime owner；首轮已复现，隔离与最终完整 suite通过。它不是本次三项 Host fix 的 PASS证据，也没有被隐藏。
- run-root解释器依赖复用 controller `.venv`，但被测 `dayu` module通过 `PYTHONPATH`固定到 detached exact-head worktree，且 controller HEAD/remote-tracking ref/validation HEAD三者一致；runtime identity已固化。未重新解析第三方 dependency lock是既有 CLI CI harness owner的环境限制，不改变本轮 exact source HEAD事实。

没有未分类、deferred 或 blocking residual risk。

## Final marker

`EXACT-HEAD-EVIDENCE-PASS-READY-FOR-DRAFT-PR-PASS`

`READY-FOR-CONTROLLER-DRAFT-PR-PASS-ADJUDICATION`
