# WU-SEMANTIC-OWNERSHIP-01 P3-I Plan Review (AgentDS)

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Gate: plan review
- Review target: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Review agent: AgentDS
- Timestamp: 2026-07-11T07:52:49+08:00

## Evidence Sources Reviewed

- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Design sources: `docs/host/design.md` (sections 1-3, terminal/Outbox facts), `docs/engine/design.md` (full)
- Control sources: `docs/host/issues-implementation-control.md` (slice policy lines 129-149), `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`, `docs/reviews/wu-semantic-ownership-01-p3-i-goal-confirmation.md`
- Code facts:
  - `pyproject.toml` (full)
  - `README.md` (full, especially §§1.2, 2.2, 2.3, 6)
  - `dayu/cli/session_execution.py` (full, 1180 lines)
  - `dayu/cli/session_terminal_cursor.py` (full, 374 lines)
  - `dayu/cli/output.py` (full, 499 lines)
  - `tests/cli/test_prompt_command.py` (full, 2292 lines)
  - `tests/cli/test_interactive_command.py` (full, 2210 lines)
- Directory inspection: `find dayu -maxdepth 2 -type d` — confirms no `dayu/web`, `dayu/wechat`, `dayu/render` exist
- Cross-reference: `grep -rn "dayu/web\|dayu/wechat\|dayu/render" --include="*.py"` — only hits in `tests/runtime/test_config_loader.py`, `tests/service/test_host_assembly.py`, `dayu/runtime/workspace_paths.py` (config loader references, not actual module imports)

## Assumptions Tested

1. **Restoring minimal entrypoints is safe and won't create false capability promises.** Partially supported. The plan correctly scopes to import/help smoke, but README narrowing guidance is underspecified (see M-F1).

2. **Terminal cursor advancement after render (not after success check) correctly prevents re-display without mutating Host facts.** Supported. The code facts confirm the current bug: cursor advances only on `render_exit_code == EXIT_SUCCESS`, leaving FAILED/CANCELLED/LOST terminals unwatermarked. The plan's fix (render → advance cursor → check exit code) preserves renderer exit-code ownership and doesn't touch Host/Service facts.

3. **Two slices are appropriate for this work unit.** Supported. S1 (packaging/README) and S2 (CLI cursor) have distinct owners and validation loops. Fits within the control doc's 1-3 slice default for small cross-module cleanup.

4. **Test coverage is sufficient to catch regressions.** Partially supported. Core paths are covered, but installed console-script smoke and cursor-write failure handling have gaps (see M-F3).

## Material Findings

### M-F1 - S1 README narrowing 执行面规格不足（中）

- **位置**: Slice S1, "Concrete Implementation Steps" step 9, "README Trigger Decision", target README §§1.2, 2.2, 2.3, 6
- **问题类型**: 不可直接实施
- **当前写法**: Plan 说 "Narrow root README command sections to the behavior actually implemented in this slice"，但未指定:
  - §1.2（验证安装）当前列出 `dayu-wechat --help`、`dayu-render --help`、`dayu-web --help`——如果 S1 只恢复 import/help smoke，§1.2 的验证命令不需改动，但 dayu-web 需要 `[web]` extras 的说明可能需要调整。
  - §2.2（Web 入口）当前描述 Streamlit server、`localhost:8501`、功能说明链接——如果 S1 只提供 `--help` + diagnostic，这一段必须大幅改写或标记为"当前不可用"。
  - §2.3（WeChat 入口）当前列出 9 个子命令、大量参数表格、多开示例——如果 S1 只提供 `--help` + diagnostic，这一段包含大量不可执行的工作流承诺。
  - §6（渲染输出）当前描述 pandoc/Chrome 依赖、`.docx`/`.html`/`.pdf` 输出——如果 S1 只提供 diagnostic，§6 需要说明当前无渲染能力。
- **反例/失败场景**: Implementation agent 可能:
  - 过度删除：把 README 中有用的未来能力占位信息全部移除，违反 README 自己的更新约束（允许简短说明当前限制）。
  - 保守保留：保留大段不可执行的工作流说明，形成"文档声称可用但实际只有 help"的虚假承诺。
- **为什么有问题**: README 是用户可见的产品契约。S1 恢复 entrypoint 后，README 的三个主要功能段（Web/WeChat/render）都包含当前无法执行的命令序列。如果 plan 不给 implementation agent 明确的 narrowing 边界，agent 必须自行做产品决策，这属于 plan 规格不足。
- **直接证据**:
  - README §2.2 第 328-342 行描述 `dayu-web` 启动 Streamlit server → 当前代码无此能力。
  - README §2.3 第 346-700 行描述 9 个 `dayu-wechat` 子命令 → 当前代码无此能力。
  - README §6 第 1083-1108 行描述 `dayu-render` 的 pandoc/Chrome 渲染链 → 当前代码无此能力。
  - Plan line 60: "README must then be narrowed to match that real behavior."
  - Plan line 62: "Do not leave README promising unavailable runtime workflows."
- **影响**: 实施 Agent 跑偏 / review 不可验收 / 后续返工
- **建议改法和验证点**:
  - 在 S1 implementation steps 中增加最小 narrowing 清单:
    1. §2.2: 保留 `dayu-web` 命令和 `--help` 说明，在"功能说明"前插入一句当前能力状态（例如 "当前 dayu-web 入口仅提供帮助信息；完整 Streamlit Web UI 尚未在本版本中提供"）。
    2. §2.3: 保留 `dayu-wechat` 入口声明和 `--help` 说明，将所有子命令详情表标记为当前不可用，或缩减为当前能力说明段落。
    3. §6: 保留渲染入口声明和 `--help` 说明，说明当前需要 pandoc/Chrome 且当前入口为诊断模式。
    4. 验证: `rg "dayu-web\|dayu-wechat\|dayu-render" README.md` 中的每一处，确认其描述的行为在 restored 模块中实际存在。
- **修复风险（低）**: 只需在 plan 中补充 narrowing 清单，不改变架构。
- **严重程度（中）**: 不影响代码正确性，但影响用户契约可信度。

### M-F2 - S1 未处理 `[tool.setuptools.package-data]` 中 `dayu.render` 的资源声明（低）

- **位置**: Slice S1, "Allowed Files / Modules", 对照 `pyproject.toml` lines 127-134
- **问题类型**: 契约缺失
- **当前写法**: Plan 在 first-principles 中注意到 `pyproject.toml` 有 `package-data` 条目声明 `dayu.render` 包含 `*.css`, `*.html`, `*.lua`, `*.docx`, `*.xlsx`, `*.mmd`，但 S1 的 allowed files 只列出 `dayu/render/__init__.py` 和 `dayu/render/render.py`，未说明是否需要创建或处理这些资源文件。
- **反例/失败场景**: 如果 future 实现需要这些资源文件（如 pandoc 模板、CSS），缺少它们会导致 package build 不完整。如果 S1 不处理这些资源文件且 future slices 也不处理，`dayu-render` 的 wheel 安装将缺失声明中的资源，可能导致渲染功能静默失败。
- **为什么有问题**: `pyproject.toml` 的 `package-data` 是 package 的公共契约声明。S1 恢复 `dayu.render` 模块但不处理 package-data 声明，等于部分恢复了包但留下了 dangling 资源引用。虽然 setuptools 对缺失的 glob 模式静默跳过（不会导致 build error），但 package-data 声明仍然是对用户的承诺。
- **直接证据**: `pyproject.toml` lines 127-134 声明 `"dayu.render" = ["*.css", "*.html", "*.lua", "*.docx", "*.xlsx", "*.mmd"]`
- **影响**: 风险后移——future slices 需要记得处理 package-data，否则安装的 `dayu-render` 包可能缺少声明的资源。
- **建议改法和验证点**:
  - 在 S1 的非目标中显式说明：S1 不创建 package-data 声明的资源文件；setuptools 的 `include` 策略对缺失 glob 静默跳过。
  - 或在 S1 residuals 中记录：`dayu.render` package-data 资源文件需要在后续渲染能力实现时补齐。
  - 验证：`python -m build` 或 `pip install -e .` 后检查 `dayu/render/` 下实际包含的文件。
- **修复风险（低）**: 只需在 plan 中做声明性补充。
- **严重程度（低）**: setuptools 容错，不影响 build；属于 deferred risk。

### M-F3 - S2 未指定 cursor 写入失败在 startup reconnect 循环中的传播行为（低）

- **位置**: Slice S2, "Concrete Implementation Steps" step 2, 对照 `dayu/cli/session_execution.py` lines 484-531
- **问题类型**: 状态机漏洞
- **当前写法**: Plan step 2 说 "For each terminal in startup.terminal_results, call render_interactive_terminal_result(terminal) and store render_exit_code. Advance cursor after render returns. Then, if render_exit_code != EXIT_SUCCESS, return it." Plan public contract 段说 "Cursor write failure handling must not mutate or reinterpret Host terminal status. If existing CLI command error handling treats local cursor persistence failure as fatal, keep that behavior explicit."
- **反例/失败场景**: 假设 `startup.terminal_results` 有 3 个 terminal（A=SUCCEEDED, B=FAILED, C=SUCCEEDED）。渲染 A 成功，推进 cursor 成功。渲染 B（FAILED），推进 cursor 时 `advance_cli_terminal_cursor` 因磁盘满抛出 `CliTerminalCursorError`。此时:
  - 如果 cursor error 向上传播（当前行为），B 的 FAILED 终端已渲染到 stderr 但 cursor 未推进，下次重连会重新显示 B。
  - 如果 cursor error 被 catch 然后继续返回 render_exit_code，B 不会被重新显示但 cursor 文件可能已损坏。
  - Plan 选的是"保持当前 fatal 行为"，这意味着 cursor 写入失败 = CLI 崩溃。这是可接受的（磁盘满属于极端情况），但 plan 应显式说明 startup reconnect 的 for 循环中 cursor error 会终止整个 startup 流程并向上传播。
- **为什么有问题**: Startup reconnect 是首次进入 interactive 前的屏障。如果 cursor error 发生在第三个 terminal 但前两个已成功推进，partial state 可能导致下次重连时只跳过前两个而重复显示第三个。这在极端情况下（磁盘恢复后重连）可能产生重复输出。
- **直接证据**: `dayu/cli/session_terminal_cursor.py` line 175-191: `_advance_cli_terminal_cursor_sync` 使用 file-lock + 原子写入（`os.replace`），所以 cursor 写入要么全部成功要么全部不写入。不存在部分写入的 corrupt state。但 cursor error 会导致已渲染的 terminal 在下次重连时被当做 unseen 重新显示。
- **影响**: review 不可验收——implementation agent 需要知道 cursor error 传播策略。
- **建议改法和验证点**:
  - 在 S2 step 2 中显式说明: "如果 cursor 推进抛出异常，该异常向上传播；已渲染的 terminal 不会被标记为 seen，下次重连会重新渲染。这是可接受的 trade-off，因为 cursor write 使用原子写入且磁盘满属于极端故障。"
  - 或在 residuals 中记录此 trade-off。
  - 验证: 无需专门测试（磁盘满测试成本过高），但 code review 时需确认 cursor error 不被静默吞掉。
- **修复风险（低）**: 只需在 plan 或 residuals 中做说明性补充。
- **严重程度（低）**: cursor write 使用原子写入，corrupt state 不可能；重复渲染仅在极端故障后发生。

## Architecture Boundary Review

- **分层方向**: S1 不涉及 Host/Engine/Service 修改，符合 `UI -> Service -> Host -> Engine` 方向。S2 只在 CLI 层修改 cursor 推进时机，不改 Host status truth。
- **Owner boundary**: Plan 正确识别了 packaging metadata/README → concrete modules → CLI display delivery → Host/Service terminal facts 的所有权边界。S2 fix 落在正确的 owner（CLI display delivery）。
- **依赖方向**: 新 `dayu.web`/`dayu.wechat`/`dayu.render` 模块不引入对 Host/Engine/Service 的反向依赖。CLI cursor 修改不改 Service/Host 接口。
- **不引入新公共契约**: S1 的 restored modules 使用标准 `argparse`，不创建新的内部协议。
- **结论**: 无架构边界违规。

## Overcoupling Review

- S1 和 S2 无耦合：S1 创建新模块不影响 CLI display；S2 只修改已有 CLI 路径。
- S1 内部: 三个 entrypoint 模块相互独立，各自有独立 help/smoke 行为。
- S2 内部: 三个调用点（prompt、interactive、startup reconnect）共享同一 fix pattern，但不互相依赖。
- **结论**: 无过度耦合。

## Overengineering Review

- Plan 明确拒绝实现完整 Web/WeChat/render 功能（Non-Goals）。S1 只有 minimal import/help。
- S2 只做 cursor 推进时机修正，不引入新抽象。
- Plan 不引入新 builder、factory、registry、protocol 或 migration。
- **结论**: 无过度设计。

## Best-Practice Review

- Plan 提供完整的 propagation audit（S1 和 S2 各一份），覆盖事实产生→校验→持久化→投影→用户可见输出路径。
- Plan 提供 stop conditions 防止 scope creep。
- Plan 提供 aggregate validation matrix 覆盖全部受影响测试。
- Plan 的 completion report format 与项目 convention 对齐。
- **结论**: 符合项目最佳实践。

## Optimal-Solution Review

- Restore vs remove: Plan 选择 restore，理由是 pyproject.toml + README 已经声明这些命令，且删除需要更多 README 重写。这个选择是合理的——删除三个已声明的 public entrypoints 会构成更大的用户可见 breaking change。
- Cursor fix 位置: Plan 选择在 CLI 层修改调用时机，而不是在下游（renderer）或上游（Service）添加条件。这符合"bug 落在 owner boundary"原则。
- **结论**: 方案最优。

## Open Questions

None. All review questions are resolved by direct code/design evidence or captured as material findings.

## Residual Risks

1. **README narrowing scope creep**: Implementation agent 可能过度删除 README 中合法的未来能力说明，或保守保留不可执行承诺。Mitigation: M-F1 建议的最小 narrowing 清单。
2. **`dayu.render` package-data resources**: S1 不创建资源文件，future render implementation 需要记得补齐。Mitigation: M-F2 建议的 residual 记录。
3. **Cursor write failure during startup reconnect**: 原子写入保证无 corrupt state，但重复渲染可能在极端故障后发生。Mitigation: M-F3 建议的显式 trade-off 说明。
4. **S1 `dayu-web` extras dependency**: `pyproject.toml` 的 `[web]` extras 包含 `streamlit>=1.49.0`。如果 S1 的 `dayu/web/__main__.py` 在 import 时尝试导入 streamlit，会在未安装 `[web]` extras 的环境中 crash。Plan 正确要求 "optional dependency failure must be a user-readable runtime diagnostic, not an import-time crash"，但 implementation agent 必须注意 lazy import。
5. **`RUN_LOST` outbox availability**: Plan risk 段正确指出 `RUN_LOST` 可能不产生产品级 outbox item。Terminal cursor 修正不影响该行为——只有 Service/CLI 实际收到的 terminal result 才会被渲染和 watermark。

## Verdict

**PASS-WITH-RISKS**

Plan 的动机成立、owner boundary 识别正确、slice 切分合理、terminal cursor fix 方向正确。三条 material findings 均为可低成本修复的规格补全问题，不影响 plan 可进入 implementation gate。

建议在进入 implementation 前补充 M-F1（README narrowing 清单），并将 M-F2 和 M-F3 作为 residuals 记录在案。

## Review Metadata

- Review artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-plan-review-ds.md`
- Verdict: pass-with-risks
- Material findings: 3 (M-F1 中, M-F2 低, M-F3 低)
- Open questions: none
