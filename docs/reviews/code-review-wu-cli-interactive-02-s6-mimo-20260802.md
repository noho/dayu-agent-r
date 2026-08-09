# Code Review — S6 Uncommitted Diff Independent Review

## Scope

- Mode: current changes（uncommitted workspace diff against base `9ad45cf7`）
- Branch: `codex/interactive-oracle`
- Base: `9ad45cf717f192b12f411d03332b971f30aff472`
- Output file: `docs/reviews/code-review-wu-cli-interactive-02-s6-mimo-20260802.md`
- Included scope: 9 modified files + 1 untracked implementation artifact（见 §1 Exact files）
- Excluded scope: production code、tests、utils、`docs/cli_ci_oracles.json`（verified byte-identical）、frozen calibration adjudication review artifact
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Validation Summary

### 1. 10-file exact scope

S6 implementation artifact 声明的精确修改文件为：

1. `README.md` ✅
2. `dayu/README.md` ✅
3. `dayu/host/README.md` ✅
4. `dayu/engine/README.md` ✅
5. `tests/README.md` ✅
6. `docs/host/design.md` ✅
7. `docs/engine/design.md` ✅
8. `docs/cli_ci.md` ✅
9. `docs/cli_ci_scenarios.json` ✅
10. `docs/reviews/gateflow-wu-cli-interactive-02-s6-implementation-codex-20260802.md`（untracked，新增 implementation artifact）✅

`git diff 9ad45cf7 --name-only` 精确输出 9 个文件，与 9 个 modified 文件一致。untracked artifact 不出现在 `git diff` 中，由 `git status` 确认。无额外文件被修改。

### 2. 17 deletions / 5 preserved / P37 / mechanical readiness

**17 条场景删除**：直接 Python JSON 解析验证：

- `docs/cli_ci_scenarios.json` 工作树解析为 442 条场景（prompt 383 / init 59）。
- 459 - 17 = 442，数学正确。
- 17 条计划删除的 scenario_id（`P25`、`P26`、`P35`、`P35R`、`PC-PW-R2-01/-02/-05/-07/-09/-11/-12/-13/-14/-15/-16/-17/-18`）全部不在最终文件中。

**5 条保留**：`PC-PW-R2-03/-04/-06/-08/-10` 全部存在，且各自 `command_parameter_ids` 与 `raw_stable_claims` 中的 `parameter:config:default` 已移除（10 处，5 × 2）。

**P37 claim 纠正**：`cross_command_assertion_ids` 与 `raw_stable_claims` 均从 `cross-command:label-session-reuse` 改为 `same-command:prompt-label-session-reuse`。

**机械 readiness**：
- prompt inventory version 从 1 升至 2，source_commit 更新为 `9ad45cf7`，canonical SHA-256 更新。
- mandatory/covered/accepted 为 `383/383/383`，gap 0。
- `implementation_findings_do_not_reduce_readiness` 清空为 `[]`。
- `registry_status` 保持 `calibration`（全局未翻转 ready）。

**prompt argv 无 `--config`**：JSON 解析确认所有 prompt 场景 argv 不含 `--config`，`command_parameter_ids` 和 `raw_stable_claims` 中无 `parameter:config` 相关 claim（`precondition` 中的 `init-deepseek-config-explicit` 保留）。

### 3. Oracle byte-identical

- `docs/cli_ci_oracles.json` SHA-256：`99c0d1aea2fdfea922c73d1a5b88b6c7e275d79a5589d07f904fe39c6d1802c9`
- base `9ad45cf7` SHA-256：`99c0d1aea2fdfea922c73d1a5b88b6c7e275d79a5589d07f904fe39c6d1802c9`
- `git diff 9ad45cf7 -- docs/cli_ci_oracles.json` 行数：0
- ✅ 完全一致，predicate 语义未被修改。

### 4. G01-G07 不被误裁决

S6 artifact 明确声明："G06 与 G01-G07 均未裁决"、"registry_status 均保持 calibration，没有手工翻转 ready"、"implementation_findings_do_not_reduce_readiness=[]"。readiness_proof 中 global `validation_result` 仍为 `calibration`。G01-G07 未在任何文档或 registry 中被标为 accepted 或 ready。

### 5. 行为项 29 raw evidence

S6 artifact 声明的 raw evidence refs/digests 与外部 evidence root `/Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt` 中的实际文件 SHA-256 完全一致：

| 文件 | 声明 SHA-256 | 实际 SHA-256 | 匹配 |
|---|---|---|---|
| `command.json` | `94d4f168...` | `94d4f168b2006e8b859c4415648b5f412266a9abf3debbc962717421f21ab8be` | ✅ |
| `sqlite-after.json` | `af839974...` | `af839974ddfabb917179b07553162403a6440a58000349e77b843bbf29900c61` | ✅ |
| `stdout.txt` | `c60aba7d...` | `c60aba7da49e012c6cf61ac62930b93c5700263eec56f3ca28488242d3f1d6f3` | ✅ |

artifact 声称 identity 已从 durable snapshot 实际读取并脱敏核对：effective provider=`deepseek`、effective model=`deepseek-v4-flash`、provider request id availability=`present`、RunnerRequestIdentity 字段均存在。敏感字段输出计数为零。声明为 raw candidate/evidence，不越权登记 accepted scenario。

### 6. README / design 是否准确对应代码 owner

逐文件核验：

| 文档 | 更新内容 | 与 S1-S5 实现一致性 |
|---|---|---|
| `README.md` | `--config` 描述、interactive 无 `--ticker`、shared `cli.agent` label、TTY/non-TTY 行为、session resume 变化 | ✅ 准确 |
| `dayu/README.md` | stable boundary 增加 label sharing/composer/identity 描述；startup recovery 增加 delayed reclassification | ✅ 准确 |
| `dayu/host/README.md` | compaction terminal owner、pre-start single-flight、response identity | ✅ 准确 |
| `dayu/engine/README.md` | `SuccessfulRunnerResponseIdentity` 公共契约、RunnerDoneData 成功 final 组合 | ✅ 准确 |
| `tests/README.md` | 移除旧 ticker/config/monitor 陈述，替换为新 suite 事实 | ✅ 准确 |
| `docs/host/design.md` | F10 delayed reclassification 措辞精确化、F11 terminal guard、F12 single-flight、F13 identity payload | ✅ 准确 |
| `docs/engine/design.md` | 成功终态 identity contract | ✅ 准确 |
| `docs/cli_ci.md` | parser inventory 规则、evidence-before-registration 规则 | ✅ 准确 |

各 README 均只写已实现事实，未写入未验证的成功 scenario。

### 7. Baseline failures 分类

S6 artifact 报告 6 条 baseline failure，全部在 `test_phase5_local_execution_integration.py` 中，节点为 `scheduler.drain_once()` 得到 `dispatched == 0`。与 S5 clean-base 裁决一致。S6 未修改相关代码、测试或时序。

完整 pytest 回归：`2957 passed, 1 skipped, 6 deselected, 6 failed`——6 条均为已知 baseline race。

pyright：`0 errors, 0 warnings, 0 informations`。

### 8. External evidence root 结构

`/Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt/` 存在，包含：
- `evidence/`：两个 candidate 目录（`interactive.I0543-memory-compaction-trigger`、`interactive.S6-compaction-provider-identity-attempt-02`），各有完整 evidence 文件集
- `homes/`、`workspaces/`、`seeds/`：CI 运行时结构

### 9. Secret / proof checks

- S6 artifact 声称对 38 个文件扫描 16 个已知 secret value，raw hits 0，token/Bearer shape hits 0。
- durable success identity key set 精确为 effective model/provider、provider request id/value availability 与 RunnerRequestIdentity。
- scenario registry SHA-256（artifact 写入前）为 `cf913441e8c192bc7b7c96f2aa939cd1240a15bd9ace54c5a86d34be6c8ac393`。

## Open Questions

无。

## Residual Risk

1. **scenario registry reordering**：`docs/cli_ci_scenarios.json` 的 diff 因场景重排导致 unified diff 呈现复杂（28 行 `-"scenario_id"` 包含 11 条重排场景），但最终 JSON 对象级验证正确。未来若需精确审计，建议以 Python JSON 对象级比较而非文本 diff 为准。

2. **行为项 29 formal scenario 登记**：raw evidence 已采集，但 formal scenario/ref/readiness 登记仍待授权 campaign/report owner。这不在 S6 范围内，已由 artifact 明确声明。

3. **awaiting entrypoint smoke drift**：callback execution port drift 仍未关闭，S6 按要求复现并记录，未修改 utils 或生产代码。

4. **interactive_calibration_plan.py harness gap**：generator 仍硬编码已删除的 config/ticker runtime obligations。S6 fail closed 未改，属于 harness owner gap。

5. **Phase5 baseline race**：6 条 test_phase5_local_execution_integration failure 未在本次修复，属于既有 scheduler/test race，与 S6 修改无关。

## Conclusion

S6 uncommitted diff 严格限于 §10.1 允许的 9 个 modified 文件 + 1 个新增 implementation artifact，未触及生产代码、测试或 utils。17 条含 `--config` 的 prompt 场景已精确删除，5 条保留 pairwise row 的 `parameter:config:default` 已移除，P37 claim 已从 cross-command 纠正为 same-command。oracle 文件 byte-identical，G01-G07 未被误裁决。行为项 29 的 raw evidence SHA-256 与外部 evidence root 完全一致且已脱敏。所有 README / design 更新准确反映已实现现状。baseline failures 分类与 S5 clean-base 裁决一致。pyright 零错误。未发现实质性问题。
