# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `9ad45cf7`
- Output file: `docs/reviews/code-review-wu-cli-interactive-02-s6-ds-20260802.md`
- Review date: 2026-08-02T03:03:19+08:00
- Included scope: exact 10-file S6 uncommitted diff（9 modified + 1 new implementation artifact）
- Excluded scope: production code、tests、utils、committed S1-S5 changes；MiMo review artifact（未读取）；frozen calibration adjudication
- Parallel review coverage: 无
- External evidence root: `/Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt`

### 10-file exact scope verification

```
README.md                     (modified)
dayu/README.md                (modified)
dayu/engine/README.md         (modified)
dayu/host/README.md           (modified)
tests/README.md               (modified)
docs/cli_ci.md                (modified)
docs/cli_ci_scenarios.json    (modified)
docs/engine/design.md         (modified)
docs/host/design.md           (modified)
docs/reviews/gateflow-wu-cli-interactive-02-s6-implementation-codex-20260802.md  (new)
```

`docs/cli_ci_oracles.json` — byte-identical，SHA-256 `99c0d1aea2fdfea922c73d1a5b88b6c7e275d79a5589d07f904fe39c6d1802c9`，diff 为零。其余 §10.1 allowed files 未触及。

## Findings

### F-001-未修复-中-readiness_proof 的 `implementation_findings_do_not_reduce_readiness` 清空无法由 S6 diff 独立验证

- **入口/函数**: `docs/cli_ci_scenarios.json` 的 `readiness_proof.prompt.implementation_findings_do_not_reduce_readiness`
- **文件(行号)**: `docs/cli_ci_scenarios.json` readiness_proof 段（diff 行 43097-43103）
- **输入场景**: S6 将所有 6 条 implementation findings 清空为 `[]`
- **实际分支**: readiness_proof 的 prompt validation_result 保持 `ready`
- **预期行为**: 清空 readiness 阻降项意味着 S1-S5 生产代码变更已解决全部 6 条 finding。S6 本身未修改生产代码，因此该清空的正确性完全依赖 S1-S5 的已提交代码。
- **实际行为**: readiness_proof 的 `implementation_findings_do_not_reduce_readiness` 变为空数组 `[]`
- **直接证据**:
  - diff 显示 6 条 finding 被删除：`prompt.cancel-closeout-reason-ui-leak`、`prompt.repeated-ctrl-c-not-graceful`、`prompt.startup-ctrl-c-traceback-or-signal-exit`、`prompt.logging-selector-and-debug-stream-contract`、`prompt.log-file-missing-parent-exit-code`、`prompt.invalid-utf8-owner-and-exit-code`
  - S6 validation 显示全部 focused tests 通过（605 CLI + 13 Service + 116 recovery + 367 compaction + 173 Engine + 883 S5 closure），为清空提供了间接证据
  - 但 S6 未运行 readiness proof validator 的独立输出作为直接证据；implementation artifact §6 中的 validator 结果只覆盖 dangling ref/oracle check，未证明 6 条 finding 均已被 owner-level 代码变更关闭
- **影响**: 若任一 finding 未在 S1-S5 完全解决，readiness_proof 会错误标记为无阻降项，registry_status 保持 `ready` 可能误导后续 calibration campaign
- **建议改法和验证点**: 在 S6 closeout 前运行 readiness proof validator 的完整 validation（包含 implementation_findings check），将 validator 输出或等效人工逐条确认作为独立 evidence 写入 artifact。不改变 registry 内容，只补充验证闭合证据
- **修复风险**: 低 — 只增加验证步骤，不修改任何文件内容
- **严重程度**: 中 — readiness_proof 清空是正确方向（S1-S5 已关闭这些 finding），但当前 S6 artifact 缺少直接验证该清空正确性的独立 evidence；无法从 diff 本身反推 S1-S5 的闭合程度

### F-002-未修复-低-dimension counts 变更缺少机械重算的直接证据

- **入口/函数**: `docs/cli_ci_scenarios.json` 的 `readiness_proof.prompt.coverage_dimension_scenario_counts`
- **文件(行号)**: readiness_proof 段 dimension counts（diff 行 43058-43069）
- **输入场景**: 17 条 scenario 删除 + 5 条 pairwise row 的 `parameter:config:default` 移除后，dimension counts 从 `50/400/16/10/332/5` 变为 `33/383/16/8/319/5`
- **实际分支**: 新 counts 写死在 registry 中
- **预期行为**: counts 应由 scenario registry 的机械统计算法派生，不应手工调整
- **实际行为**: 手工验证 `accepted_scenario_count` 383 正确（`400 - 17 = 383`）；`precondition_state_ids` count 383 与 scenario 总数一致（每条 scenario 恰好一个 precondition）；`command_parameter_ids` 从 50 降到 33（差 17）说明被删除的 17 条 scenario 各自贡献了 command_parameter coverage；`combination_high_risk_ids` 从 332 降到 319（差 13）与 17 条删除中 13 条有 pairwise combination 的观察一致；`input_class_ids` 从 10 降到 8 因 P30（有 stdin:EOF input class）被重新编号。所有 counts 变化方向正确，但无机械 validator proof 直接输出
- **影响**: 手工验证的 counts 值与 diff 一致，不存在已知错误；但若后续修改 registry 时手工改 counts 而非机械重算，会引入漂移风险
- **建议改法和验证点**: implementation artifact 中已记录 validator 通过结果（"registry object/ref/readiness validator 通过"），建议把 validator 对 dimension counts 的机械输出显式引用到 artifact，与当前手工核验形成交叉验证
- **修复风险**: 低 — 仅增强文档透明度
- **严重程度**: 低 — 手工核验证实 counts 变化方向与幅度均合理，且 implementation artifact §6 记录 validator 通过；无已知数据错误

### F-003-未修复-低-parser inventory 字段顺序变更导致 canonical SHA-256 不可比

- **入口/函数**: `readiness_proof.prompt.parser_inventory.parameters[]` 各元素的字段顺序
- **文件(行号)**: readiness_proof parser inventory 段（diff 行 42747-43057）
- **输入场景**: 从 `build_parser()` 重新生成 parser inventory 时，JSON 序列化改变了每个 parameter 对象内部字段顺序（旧：`dest, option_strings, required, nargs, choices, type`；新：`choices, dest, nargs, option_strings, required, type`）
- **实际分支**: 字段顺序是 dict 序列化的实现细节，不影响语义
- **预期行为**: 若使用同一 canonical serializer，同一 parser 应产生 byte-identical inventory
- **实际行为**: 新 SHA-256 `e83f3d12ab5eba99cdfb586e5b15cd99e01451c23b66ec2f9d7dd7ce94f1b9b3`（旧 `ca66b4e2755f763253c9b475ed3b1374c64d111acc32a5c71fa36ffe306d57f1`）。字段顺序差异使新旧 digest 无法直接 diff 验证参数集的等价性
- **直接证据**: diff 中每个 parameter 对象的字段顺序均发生变化（例如 `dest` 从首位移到 `choices` 之后）
- **影响**: 无法仅通过 SHA-256 比较来确认"除 --config 删除外，其余参数集合不变"；必须逐字段人工核对。当前 implementation artifact §4.2 已正确记录了新旧 SHA-256 与 inventory version 变更
- **建议改法和验证点**: 若 canonical serializer 支持稳定字段顺序，固定输出格式使 future inventory 更新只反映实际参数变化。当前 S6 已通过 `removed option / namespace static scan` 验证生产 parser 不接受旧参数，间接关闭参数等价性风险
- **修复风险**: 低 — serializer 固定属 tooling 改进，不影响当前 diff 正确性
- **严重程度**: 低 — 不影响正确性，只是 digest comparability 的 tooling 问题

### F-004-未修复-低-`docs/cli_ci.md` 新增的 parser/source-of-truth 规则未引用准确的 section 锚点

- **入口/函数**: `docs/cli_ci.md` 新增段（`Registry-level readiness proof` 之后）
- **文件(行号)**: `docs/cli_ci.md` diff 行 178-198（新增段落）
- **输入场景**: 新增了 parser inventory 规则段，描述 `build_parser()` 导出、参数删除后旧 argv 场景必须删除等规则
- **实际分支**: 新增文本嵌在现有 `Registry-level readiness proof` 段与 `parser leaf` 定义之间
- **预期行为**: 新规则应明确引用其适用的 section 或作为独立 subsection
- **实际行为**: 规则正确描述了 S6 的实际行为（17 条 config argv 场景被删除而不是改写成 unknown-option oracle），但段落结构上无独立 heading，可能被读者误认为是上一段的延续
- **直接证据**: diff 中新增段没有 `###` heading，直接跟在 readiness proof 段落后
- **影响**: 文档导航性略降，不影响正确性
- **建议改法和验证点**: 考虑为新增规则增加 subsection heading（如 `### Parser inventory 与 evidence-before-registration 规则`）
- **修复风险**: 低 — 纯文档结构调整
- **严重程度**: 低 — 不影响正确性，仅文档结构可读性

## Validation

### 直接验证项

| 验证项 | 方法 | 结果 |
|---|---|---|
| 10-file exact scope | `git diff 9ad45cf7 --name-only` | 9 modified + 1 new = 10，与 artifact §2 一致 |
| Oracle byte-identical | `shasum -a 256` base vs workspace | SHA-256 `99c0d1aea2fdfea922c73d1a5b88b6c7e275d79a5589d07f904fe39c6d1802c9` 双端一致 |
| 17 条删除 | 逐 scenario_id 搜索剩余 registry | 全部消失，prompt argv 中 `--config` 为零 |
| 5 条保留 pairwise row | 按 scenario_id 搜索并检查 claim/argv | 全部存在，`parameter:config:default` 已从两处 claim 数组删除，`init-deepseek-config-explicit` precondition 保留 |
| P37 claim 纠正 | 检查 cross_command_assertion_ids 与 raw_stable_claims | `cross-command:label-session-reuse` → `same-command:prompt-label-session-reuse`，无残余 cross-command claim |
| 外部 evidence compaction identity | 读取 sqlite-after.json event_log[6] CONTEXT_COMPACTED | effective_provider=deepseek, effective_model=deepseek-v4-flash, availability=present, provider_request_id 非 None, runner_call_index=1, attempt_id/execution_id=None, 零敏感字段 |
| I0543 分类正确性 | 读取 sqlite-after.json | 无 CONTEXT_COMPACTED 事件（仅有 CONTEXT_COMPACTION_REQUESTED），与 artifact 所述 `hard_threshold_before_dispatch` → `RUN_FAILED` 一致 |
| 行为项 29 raw evidence 真实同源 | external evidence root 的 command.json + sqlite-after.json | 真实 argv（pipe stdin，`--label`），真实 provider（deepseek-v4-flash），provider_request_id present，非 fake/deterministic |
| 行为项 29 脱敏 | 扫描 identity payload 全字段 | effective_provider/model、provider_request_id_availability/value、RunnerRequestIdentity 字段均在；endpoint/credential/api_key/secret/header/token/bearer 零命中 |
| Scenario 总数 | python 统计 `command == "prompt"` | 383（= 400 - 17），与 artifact §4.1 一致 |
| No production/test code changes | `git diff 9ad45cf7 --name-only` | 仅 markdown + JSON，零 `.py` 文件 |

### S6 validation results（来自 implementation artifact §6，未独立重跑）

- CLI focused 六文件：605 passed, 3 warnings
- Service prompt/interactive focused：13 passed, 3 warnings
- S3 recovery focused 六文件：116 passed
- S4 compaction terminal focused：367 passed
- Engine identity focused 七文件：173 passed
- S5 26-file focused closure：883 passed, 1 skipped, 6 failed（六条均为已知 phase5 baseline race）
- Full `pytest tests/engine tests/host -q`：2957 passed, 1 skipped, 6 deselected, 6 failed（同六条 baseline）
- I0554 三条 owner proof：3 passed
- `python -m pyright dayu/ tests/ utils/`：0 errors, 0 warnings, 0 informations
- `python -m json.tool` 两个 registry：通过
- registry object/ref/readiness validator：通过；dangling 均为 0
- removed option / namespace static scan：七组生产查询零命中

### Baseline failures 分类验证

六条 phase5 local execution failure 在 S5 clean accepted base 已独立复现（`dispatched == 0`），Controller 裁为既有 scheduler/test race。S6 未修改相关代码、测试或时序。分类正确。

## Open Questions

1. **Readiness proof validator 的完整输出**：implementation artifact §6 记录 "registry object/ref/readiness validator 通过"，但未提供 validator 对 dimension counts 重算、implementation_findings 逐条检查的原始输出。这些输出可作为 F-001 与 F-002 的独立闭合证据。非阻塞 — validator 已通过。

2. **`docs/cli_ci.md` 新增段中 "当前实现的动态 owner boundary" 所列项目**（TTY composer、non-TTY whole UTF-8、Escape/CSI/Alt/paste 分流、Ctrl+C cancel/exit-after-cancel、type-ahead/QUEUE、delayed orphan recovery）是否全部在 S1-S5 生产代码中实现并通过 owner-level tests 验证？Implementation artifact §6 的 test results 提供了间接证据（全部 focused suites 通过），但 S6 本身不修改生产代码，因此不构成 S6 defect。非阻塞 — 属于 S1-S5 review 范围。

## Residual Risk

1. **Formal report renderer 硬编码旧 target commit**：implementation artifact §5 与 §8 明确记录，S6 未生成可供 accepted registry 引用的当前 target formal observed-behavior report。所有 P27R-P34 及保留 scenario 的 `observed_evidence` 仍引用旧 bundle（`prompt-20260731T011247Z` 或 `prompt-coverage-20260731TYgqzXg`）。此为已知 harness owner gap，S6 fail closed 未伪造 ready。

2. **G01-G07 全部未裁决**：行为项 29 已有真实 successful compactor durable identity raw evidence（F-004 validation 直接核验），但正式 scenario/ref/readiness 登记仍待授权 campaign/report owner。G06 及全部 G01-G07 保持冻结。

3. **Awaiting entrypoint smoke 的 callback execution port drift**：implementation artifact §6.1 记录 "仍在 `run_accepted` 前断于既有 `callback_execution_port is required when callbacks are set`"，属于 S1-S5 范围，S6 只复现并记录，未修复。

4. **`interactive_calibration_plan.py` 的 removed option obligations**：generator 仍硬编码已删除的 config/ticker runtime obligations。S6 未修改该文件（不在 §10.1 allowed files），fail closed 未使用其输出登记 accepted scenario。

5. **Parser inventory 字段顺序不确定性**：若后续重新生成 inventory 时 serializer 行为不变，则 digest 稳定；若 serializer 实现变更，digest 可能再次漂移而参数集实际未变。建议固定 canonical serializer 输出格式。

## 结论

S6 uncommitted diff 在 10-file exact scope 内准确执行了计划 §10 规定的职责：

- **17 条删除、5 条保留/P37 纠正**：逐条核验通过，registry 内零 `--config` argv
- **Oracle byte-identical**：SHA-256 双端一致
- **External evidence 行为项 29**：真实 provider successful compaction identity raw evidence 存在且脱敏正确（effective provider/model + present provider_request_id + 零敏感字段）
- **README/design**：七份文档变更准确反映 S1-S5 已接受的 F01-F13 owner contract，未写入未验证的 success scenario 或 G01-G07 裁决
- **Baseline failures**：六条 phase5 race 正确分类为既有 scheduler/test race，S6 未修改相关代码
- **Readiness proof**：counts 变化方向与幅度合理，`implementation_findings_do_not_reduce_readiness` 清空需补充 validator 独立输出作为闭合证据（F-001）

四个 findings 均为低-中 severity，无阻塞性 defect。三个 open questions 均为非阻塞。Residual risks 均为已知、已分类、已由 implementation artifact 透明记录的 gap。

建议 S6 closeout 前关闭 F-001（补充 readiness proof validator 完整输出或等效逐条确认），其余 findings 与 open questions 不阻塞 merge。
