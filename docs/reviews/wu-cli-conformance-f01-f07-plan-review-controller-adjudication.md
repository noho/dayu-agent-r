# WU-CLI-CONFORMANCE-F01-F07 Plan Review 总控裁决

## 0. Gate 元数据

- Gate：`plan review -> fix`
- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Reviewed plan：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md`
- 既有 PR：`190`
- 裁决结论：`FAIL — accepted findings require plan fix and independent re-review`
- 当前允许动作：只修计划与写 plan-fix/re-review artifacts；不得进入 implementation、commit、push 或 PR 操作。

## 1. 裁决原则与直接证据

本裁决不以两路 reviewer 是否一致为依据，而逐项回到 frozen oracle、Host/Engine design 和直接代码/数据证据：

- 用户明确要求两个 dirty registry baseline 最终提交进 PR 190；计划当前却在 §0.1、§13 全程禁止 stage，二者不能同时成立。
- `docs/host/design.md:3835-3843` 明确要求 reactive compact 保留同 operation 的 bounded multi-pass；invalid-response audit 第 17 行再次确认“全部 pass 通过后才能写一个 `CONTEXT_COMPACTED`”。计划 §9.6 删除 production `pass_queue` 与 multi-pass，属于未获授权的设计扩张。
- frozen nonzero-editor evidence 中 `VISUAL=/usr/bin/false`、`EDITOR=/usr/bin/false`，最终 CLI exit 0、stderr 为空、没有 Run；因此 editor 非零退出是保留草稿并回到 composer 的取消语义，不是 actionable launch/config error。计划 §4.2 把 nonzero 与 spawn failure 一并报错，违反 frozen 行为。
- 当前 prompt_toolkit 为 `3.0.52`。`Buffer.open_in_editor()` 的私有 `_open_file_in_editor()` 在显式命令 `OSError` 时继续尝试系统 editor，不能直接满足 F02；但 public `run_in_terminal(...)` 与 `Buffer.document` 足以实现 CLI-owner 的最小显式-command tempfile round trip，无需版本锁定私有 monkey patch。
- `Vt100Parser` 是同步增量 parser；真正缺口不是“只能 async”，而是计划未明确它与 `TtyRunningKeyMonitor` 的 thread-owned reader、ESC ambiguity timeout 和 `asyncio.Queue` handoff 如何组合。
- `MemoryProjectionPolicy` 与 `estimate_memory_size_units()` 都在 `dayu/host/memory.py`，该文件已经位于 S7 allowlist；不存在需要 implementation-time 再猜 owner 的理由。
- `dayu/service/README.md` 没有记录 `EntrypointRuntimeRequest`、`ServiceHostAdminRequest` 或其被删字段，因此按仓库 README 触发规则不需要更新。

## 2. MiMo findings 裁决

| Finding | 裁决 | 理由与要求 |
|---|---|---|
| M-F1 S1 `test_session_commands.py` 路径错误 | `accepted` | 实际路径是 `tests/cli/test_session_command.py`；allowlist 与命令全部修正。 |
| M-F2 S4 `test_session_attachment.py` 路径错误 | `accepted` | 实际 owner test 是 `tests/host/test_session_attachment_registry.py`；不得创建重复测试文件。 |
| M-F3 v2 schema 命名映射不清 | `accepted` | 在计划中增加旧 active symbol/literal 到 fresh v2 symbol/literal 的机械映射与零残留扫描；不增加 alias。 |
| M-F4 S7 原子范围缺少内部 checkpoints | `accepted` | 保持 S7 单一 outer slice/accepted commit，但为 schema、parser/accept、repair、projection/multi-pass 四个内部阶段给出 focused tests/pyright checkpoint；不得用 stash、新分支或中间兼容 commit。 |
| M-F5 需要旧 v1 durable data 兼容/迁移 | `rejected-with-reason` | 用户明确要求 fresh schema/全新起库且禁止旧库兼容读取/测试。不得新增旧 schema deterministic reader、migration 或 fallback；旧 schema active input严格拒绝只用于新 schema parser contract test，不承诺旧 DB 可继续打开。 |
| M-F6 shared closeout 令 prompt 过度耦合 | `rejected-with-reason` | acceptance/cancel/graceful-closeout 是 prompt/interactive 共享语义；共享最小 coordinator 可避免第二套取消真源。接受 DS-B4 的消费者映射要求，禁止携带 interactive-only attachment/composer 字段。 |
| M-F7 prompt_toolkit seam 风险 | `accepted/consolidated-into-DS-B3` | 风险成立；用总控固定的 public-seam explicit launcher 决策消除 implementation-time open question。 |
| M-O1 provider blocked 后 next entry point 缺失 | `accepted` | S8 环境 blocked 时不得 closeout pass；保留失败 bundle，current/next gate 仍为 S8 real-evidence acquisition，provider 恢复后用新 run id 重跑。 |
| M-O2 Memory policy owner 位置待确认 | `accepted-as-plan-clarification` | owner 已确认在 `dayu/host/memory.py`；计划直接记录该事实并删除 implementation-time 猜测。 |

## 3. DeepSeek findings 裁决

| Finding | 裁决 | 理由与要求 |
|---|---|---|
| DS-B1 Vt100Parser/thread bridge 未指定 | `accepted` | parser 在 reader thread 内唯一创建/调用；chunk read 后 feed，同一 thread 用 named ESC ambiguity deadline 调 `flush()`；callback 只通过 `loop.call_soon_threadsafe` 投递 typed action。完整序列不取消。 |
| DS-B2 registry 最终 disposition 缺失 | `accepted` | 在 accepted plan commit 单独按显式路径 stage 两个 baseline，与 plan/review/fix/re-review artifacts 一起提交；stage 前后校验固定 SHA-256。S1-S8 不再携带 dirty registry。 |
| DS-B3 editor adapter seam 不可直接实施 | `accepted` | 决策固定为：unset 时调用 prompt_toolkit 原 public fallback；显式时使用 CLI-owned minimal tempfile + public `run_in_terminal` + exact argv，成功才回填 `Buffer.document`，nonzero 为静默取消，`OSError` 为 actionable spawn failure；不触碰私有 method、不 fallback。 |
| DS-B4 closeout 现有消费者未映射 | `accepted` | 计划增加 `_PromptAcceptedRunState`、`_InteractiveAcceptedRunState`、prompt cancel helper、interactive acceptance/cancel sites 到新最小 coordinator 的逐点映射。 |
| DS-B5 S7 缺少实施缓解 | `accepted-in-part` | 接受内部 checkpoint；拒绝 `git stash`、新 branch、wall-clock 预算和中间 commit，因为它们不是 correctness contract，且会增加 dirty-baseline风险。 |
| DS-B6 service README 判定未验证 | `rejected-with-reason` | 直接 `rg` 已确认 service README 不列这些 request/字段；仓库根规则也没有机械触发。计划补充已检查证据即可，不修改该 README。 |
| DS-B7 code-generation-ready 仍保留 open stop checks | `accepted-in-part` | editor seam 与 Memory policy owner 在 plan fix 中收口；provider 可用性保留为 operational stop，不是实现设计问题。 |

## 4. 总控新增 findings

### C1-accepted-严重：S7 不得删除 reactive multi-pass

计划 §9.6、§14.3 和 contract scan 要求移除 `pass_queue` / `build_reactive_pass_queue_plan`，与 `docs/host/design.md:3835-3843` 和 invalid-response audit 直接冲突。修复必须：

- 保留 `CompactPipelinePassQueuePlan`、`build_reactive_pass_queue_plan` 与 operation-level bounded multi-pass。
- 每个 pass 的 immutable source boundary 上做 whole-candidate repair；rejected pass candidate 不 materialize。
- 全部 required passes accepted 后，Host operation owner 才合并 accepted pass truths，重新执行 operation-root coverage、duplicate、policy cap 与 budget validation，并形成唯一 `CompactAcceptedTruthV2`。
- 中间 pass truth 只在 operation 内存或受控 transient diagnostic artifact 中存在，不写 `CONTEXT_COMPACTED`、Memory 或 ordinary RunInput。
- 任一 pass exhaust 或 aggregate validation 无法在剩余 attempt budget 内收口时，只写一个 canonical `CONTEXT_COMPACTION_FAILED`，再走既有 fallback/fail-closed。
- rolling compact 与 late-result tests 同时覆盖 single-pass 和 reactive multi-pass。

### C2-accepted-严重：F02 必须保持 nonzero editor 的冻结取消语义

计划不得把 editor nonzero 与“配置不存在/不可执行/无法启动”合并：

- missing、non-executable、`OSError` spawn failure：actionable、无 traceback、原 draft/cursor、零 Run、REPL 继续。
- process return code nonzero：视为 editor cancel；无错误、原 draft/cursor、零 Run、REPL 继续。
- return code 0：读取编辑结果并回填；只有后续显式 submit 才创建 Run。

### C3-accepted-高：S1 allowlist 未覆盖 deleted request field 的全部 construction sites

删除 `EntrypointRuntimeRequest.explicit_config_dir` 与 `ServiceHostAdminRequest.config_overlay_dir` 时，至少还会机械影响：

- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/cli/test_transient_delivery_interruption_path.py`
- `tests/cli/test_session_command.py`
- 计划已列的 prompt/interactive/host-admin tests

计划必须用 `rg` 列出并纳入全部 typed construction sites；不得靠 default/兼容字段保留旧调用。

### C4-accepted-高：Memory 必须消费 committed canonical compact fact

`docs/host/design.md:3672` 禁止 Context Governance 直接写 Memory。计划需明确：Context Governance 产生 `CompactAcceptedTruthV2`，terminal owner 将其一次性写入 artifact 与 `CONTEXT_COMPACTED` payload；Memory projector 只从已提交 canonical event 的 strict v2 semantic projection恢复 accepted truth并更新 snapshot。不得把内存中的未提交 accepted object直接传给 Memory。

失败 fallback 也不能称作 accepted compact truth：精确 outcome 仍由 `CONTEXT_COMPACTION_FAILED`、typed fallback input refs 和 fallback manifest拥有；Memory 不得消费 rejected candidate。

### C5-accepted-中：清理 stale plan metadata 与完成声明

计划头仍写“后续合法入口：Phase B”；修复后应只写 `plan re-review`。所有临时 phase 叙事和与实际 Gate 状态冲突的文案必须删除或更新。

## 5. Required plan-fix completion signal

AgentCodex 的 plan fix 必须同时满足：

1. 修复所有 `accepted` / `accepted-in-part` finding；不得只修两路 reviewer 共同项。
2. plan 内所有允许路径真实存在，明确标为“将新增”的文件除外。
3. 保留 reactive multi-pass，且 whole-candidate repair、aggregate accepted truth、single terminal 三者不冲突。
4. F02 的 invalid/spawn/nonzero/success 四类语义与 frozen evidence一致。
5. accepted plan commit 明确包含两个 baseline registry，hash 不变。
6. editor 与 key parser方案不再留 implementation-time设计选择。
7. `git diff --check`、两个 JSON tool 与 baseline SHA-256 通过。
8. 写 durable plan-fix artifact，并停在 plan re-review；不实施、不 stage、不 commit。

## 6. Residual risk disposition

- S7 large atomic closure：`covered by current plan fix + later S7 internal checkpoints`。
- PTY/editor/key sequence dependency behavior：`covered by S2/S3 owner tests + S8 full-real evidence`。
- provider availability：`operational; S8 remains open until real evidence succeeds`。
- natural-language semantic fidelity：`accepted model risk; covered by deterministic minimum validity + real follow-up evidence, not schema overclaim`。
- registry accidental mutation/staging：`fixed by hash guard + accepted plan commit exact staged set`。
- 当前不存在 unclassified residual risk。
