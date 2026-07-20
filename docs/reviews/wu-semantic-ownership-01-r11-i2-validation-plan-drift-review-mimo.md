# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 validation plan-drift corrected plan — AgentMiMo adversarial review

## 1. Review scope

完整审查 925-line corrected plan
`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`（SHA-256
`20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd`），同时核对：

- Controller adjudication
  `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-controller-adjudication.md`
- AgentCodex fix artifact
  `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-fix-codex.md`（SHA-256
  `32d7080da9ada17fb5c56dbfb4bffa1eb82ec29acb91532ba46d15e5b2989acb`）
- Controller validation
  `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-fix-controller-validation.md`
- 总控 `docs/host/issues-implementation-control.md` current state
- 当前 working tree 代码事实与 hash 锁

重点核验用户指定的六项：R11-I2-VAL-PD-F01 关闭状态、22/8/15 path count、唯一 shared path 分配、batch-only
infer/no JSON/executable script test contract、其它 I1 owner 保护、stopped product diff、后续
review/commit/Windows release-blocker sequence。

## 2. Verified locks

| Lock | Claim | Actual | Result |
|---|---|---|---|
| Plan SHA-256 | `20f35e55...31dd` | `20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd` | MATCH |
| Plan lines | 925 | 925 | MATCH |
| Stopped product diff | `718846cd...8332` | `718846cdd5ce3ad8d9d789b3b7b47e18df8943ac541f63a925dd696b06fe8332` | MATCH |
| Shared test before-lock | `7cdc4c1d...ece6` | `7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6` | MATCH |
| Codex fix artifact | `32d7080d...89acb` | `32d7080da9ada17fb5c56dbfb4bffa1eb82ec29acb91532ba46d15e5b2989acb` | MATCH |
| HEAD | `a527ec03` | `a527ec03` | MATCH |
| Staged set | empty | empty | MATCH |
| Untracked renderer | `dfe0508d...aea65` | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` | MATCH |
| Untracked workflow | `4026da55...0953` | `4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953` | MATCH |
| Controller validation verdict | PASS | PASS | MATCH |

## 3. R11-I2-VAL-PD-F01 关闭状态

**结论：CLOSED。**

Controller 接受的唯一 finding `R11-I2-VAL-PD-F01`（HIGH）在 corrected plan 中形成可执行、fail-closed 的单节点修复：

1. §4 slice allocation：`tests/cli/test_arg_parsing.py` 加入 I2，仅限
   `test_root_readme_matches_current_cli_public_contract`。cumulative unique path count 固定 `22`，I1
   固定 `8`，I2 从 `14` 修正为 `15`。**已验证：** §4 第 197—216 行精确描述了此分配。
2. §7.1 exact allowlist：15 paths，shared path 只开放一个函数。**已验证：** §7.1 第 549—560 行列出完整 15
   paths。
3. Test contract：旧全局 `--infer` 禁止、`"schema_version": 1` / `"commands"` 必须存在、"不生成 shell"必须存在
   三组断言被替换为 batch-only `--infer` + `FMP_API_KEY`、executable `.sh` / `.cmd` current contract。
   **已验证：** §7.1 第 572—576 行与 §5 fix-codex 第 75—85 行。
4. Protected-I1 wording：mutation 前匹配 before-lock，mutation 后 7 个非共享 I1 paths hash 不变。
   **已验证：** §4 第 213—216 行、§9.1 第 850—853 行。
5. §7.2/§7.3/§8/§9.1/§10 同步 22/8/15 count、checkpoint、scan、state machine、checklist。
   **已验证：** 各节均有明确命中。

finding 从 OPEN → FIXED_IN_PLAN → CONTROLLER_VALIDATED → 本轮 PENDING_DUAL_REVIEW。plan
fix 结构正确，不创建第三 slice、不重开 I1 producer/consumer、不改 production/README/workflow scope。

## 4. 22/8/15 path count 核验

**结论：CONSISTENT。**

### 4.1 Cumulative 22 unique paths

逐项从 §4 cumulative closed allowlist 计数：

| # | Path | Type |
|---|---|---|
| 1 | `dayu/fins/upload_batch.py` | changed production |
| 2 | `dayu/cli/commands/fins.py` | changed production |
| 3 | `dayu/cli/arg_parsing.py` | changed production |
| 4 | `dayu/cli/upload_script.py` | new production |
| 5 | `pyproject.toml` | packaging |
| 6 | `requirements.txt` | packaging |
| 7 | `.github/workflows/r11-upload-script-windows.yml` | new CI |
| 8 | `dayu/web/__init__.py` | deletion |
| 9 | `dayu/web/__main__.py` | deletion |
| 10 | `dayu/wechat/__init__.py` | deletion |
| 11 | `dayu/wechat/main.py` | deletion |
| 12 | `dayu/render/__init__.py` | deletion |
| 13 | `dayu/render/render.py` | deletion |
| 14 | `tests/fins/test_upload_batch.py` | test |
| 15 | `tests/cli/test_upload_filings_from_command.py` | test |
| 16 | `tests/cli/test_fins_commands.py` | test |
| 17 | `tests/cli/test_arg_parsing.py` | test (shared) |
| 18 | `tests/cli/test_public_package_entrypoints.py` | test |
| 19 | `README.md` | README |
| 20 | `dayu/README.md` | README |
| 21 | `dayu/fins/README.md` | README |
| 22 | `tests/README.md` | README |

实际 `git diff --name-only 2b14b2fb...` 列出 20 tracked changed paths；加上 2 个 untracked new files
（`upload_script.py`、Windows workflow）= 22。**MATCH。**

### 4.2 I1 = 8 paths

§4 第 201—206 行列出：`upload_batch.py`、`test_upload_batch.py`、`fins.py`、`arg_parsing.py`、
`upload_script.py`（new）、`test_upload_filings_from_command.py`、`test_fins_commands.py`、
`test_arg_parsing.py`。计数 = 8。**MATCH。**

### 4.3 I2 = 15 paths

§7.1 第 549—560 行列出：`pyproject.toml`、`requirements.txt`、Windows workflow（new）、6 deletions、
`test_public_package_entrypoints.py`、`test_arg_parsing.py`（shared）、4 READMEs。计数 = 1+1+1+6+1+1+4
= 15。**MATCH。**

### 4.4 Overlap accounting

- I1 ∩ I2 = `{tests/cli/test_arg_parsing.py}`，count = 1
- I1 unique = 8 − 1 = 7
- I2 unique = 15 − 1 = 14
- Cumulative = 7 + 14 + 1 = 22。**MATCH。**
- §7.2 workflow trigger paths = 22 cumulative unique。**MATCH。**
- §9.1 "mutation 后 7 个非共享 I1 paths" = 8 − 1 shared = 7。**MATCH。**

## 5. 唯一 shared path 分配

**结论：CORRECT。**

`tests/cli/test_arg_parsing.py` 是唯一跨 slice path。I2 只允许修改
`test_root_readme_matches_current_cli_public_contract`（line 358）；同文件其它 parser/help owner tests
属于 I1。

§4 第 204—205 行："后者除 `test_root_readme_matches_current_cli_public_contract` 外的所有 parser/help
owner tests 均只属于 I1"。§7.1 第 556 行："仅限 `test_root_readme_matches_current_cli_public_contract`"。

代码事实验证：该函数位于 line 358，同文件其它 I1-owned tests 包括
`test_upload_actions_default_to_auto_and_batch_rejects_delete`（line 278）、
`test_upload_filings_from_infer_and_overwrite_are_explicit_booleans`（line 311）、
`test_session_action_help_contains_fixed_parser_shape`（line 384）等。I2 修改范围限于一个函数节点，不触及
其它 parser/help tests。

I1 parser 测试已覆盖命令级 flag 结构：`upload_filing`/`upload_material` 的 allowed flags 不含 `--infer`
（lines 57—73），`upload_filings_from` 含 `--infer`（line 82），默认值 `False`（line 293），显式传入 `True`
（line 326）。

## 6. Batch-only infer / no JSON / executable script test contract

**结论：PLAN CONTRACT CORRECT，但 IMPLEMENTATION GAP 存在。**

见 Finding 1 和 Finding 2。

## 7. 其它 I1 owner 保护

**结论：ADEQUATE。**

1. **I2 不回改 I1 production/test scope：** §7.1 第 569—570 行明确 "不把 producer、consumer、其它 parser
   tests、Service/storage/runtime、其它 README 或新产品能力带入该 slice"。
2. **I1 paths hash lock：** §4 第 213—216 行要求 I2 mutation 前匹配 before-lock，mutation 后 7 个非共享 I1
   paths hash 不变。§7.3 第 633—636 行要求 I2 checkpoint 做 node-level diff review。
3. **I2 不扩大 allowlist：** §7.1 精确列出 15 paths；§9.1 禁止创建第三 slice/checkpoint/commit。
4. **I1 producer-consumer cutover 不重开：** §4 第 218—220 行禁止 old/new dual surface、compatibility
   seam、CLI fallback/重算。
5. **`tests/fins/test_fmp_company_info_resolver.py` 仍为只读验证输入：** §4 第 206 行明确不在修改
   allowlist。

## 8. Stopped product diff 与 state machine

**结论：CONSISTENT。**

1. **Stopped diff hash：** `718846cd...8332`，使用 exact command `git diff --binary HEAD -- README.md dayu
   tests pyproject.toml requirements.txt .github`。已验证匹配。
2. **State machine：** §9.1 第 808—853 行固定两个 implementation slices：I1 atomic cutover → I2
   packaging/README/Windows。code review 只在两个 slices 全部完成后对完整 cumulative diff 执行一次。
3. **I1 → I2 transition：** I1 cumulative validation 全通过 → Controller atomic checkpoint → I2
   implementation。I2 checkpoint 后 → cumulative code review → accepted implementation commit。
4. **Windows release-blocker sequence：** §9.4 第 886—898 行固定 `PENDING_RELEASE_BLOCKER` → GitHub
   Actions run → artifact verification → `CLOSED`。任何未执行/skipped/failed/artifact 缺失阻止 umbrella
   aggregate acceptance。

## 9. Findings

### F01-未修复-中-§7.1 test contract 描述的 direct upload `--infer` 负向断言未进入 implementation steps

- **位置**: §7.1 第 572—576 行（test contract）vs 第 572—576 行 implementation steps
- **问题类型**: 契约缺失 / plan 与 implementation steps 不一致
- **当前写法**: §7.1 第 575 行描述 "负向断言 direct upload 未获得 `--infer`"；第 576 行描述 "旧 JSON argv
  `schema_version=1` / `commands` 公共协议和'不生成 shell'文案均不存在"。
- **反例/失败场景**: I2 implementation agent 按 implementation steps 执行：从 `removed_contract` 集合移除
  `"--infer"`，删除旧正向断言，添加 batch 正向断言。但不添加 direct upload `--infer` 负向断言。此时若
  README 在 `upload_filing`/`upload_material` 文档中意外暴露 `--infer`，test 仍通过。
- **为什么有问题**: plan contract 明确要求 "负向断言 direct upload 未获得 `--infer`"，但 implementation steps
  只添加正向断言，不添加此负向断言。implementation agent 严格按 steps 执行会遗漏此 coverage。I1 parser
  tests 已在命令级覆盖 flag 结构（lines 57—84 确认 `upload_filing`/`upload_material` 不含 `--infer`），
  但 `test_root_readme_matches_current_cli_public_contract` 作为 README public-contract test 应独立验证
  README 不在 direct upload 上下文中承诺 `--infer`。
- **直接证据**: §7.1 第 575 行 "负向断言 direct upload 未获得 `--infer`"；implementation steps（第 572—576
  行）只描述删除旧禁止、添加正向断言，无 "添加 direct upload `--infer` 负向断言" 步骤。当前 test（line
  366—375）的 `removed_contract` 集合包含 `"--infer"` 是全局禁止，修正后移除该禁止但无替代负向检查。
- **影响**: implementation agent 生成的 test 缺少 direct upload `--infer` 负向断言；README 在 direct upload
  上下文中意外暴露 `--infer` 时不被 test 捕获。风险为中等，因 I1 parser tests 已在命令级覆盖。
- **建议改法和验证点**: 在 §7.1 implementation steps 中增加一步：添加 `assert "--infer" not in
  capture_help(capsys, ("upload_filing",))` 与 `assert "--infer" not in capture_help(capsys,
  ("upload_material",))`，或等价的 README-section 级负向断言。验证：`pytest
  tests/cli/test_arg_parsing.py::test_root_readme_matches_current_cli_public_contract -v` 通过，且
  test 文件 I2 delta 仅限该函数。
- **修复风险**: 低
- **严重程度**: 中

### F02-未修复-中-§7.1 test contract 描述的 JSON protocol 负向断言未进入 implementation steps

- **位置**: §7.1 第 575—576 行
- **问题类型**: 契约缺失 / plan 与 implementation steps 不一致
- **当前写法**: §7.1 第 576 行描述 "旧 JSON argv `schema_version=1` / `commands` 公共协议和'不生成
  shell'文案均不存在"。
- **反例/失败场景**: I2 implementation agent 删除旧正向断言 `'"schema_version": 1' in readme` 与
  `'"commands"' in readme`（当前 test lines 378—379），但不添加等价负向断言。若 README 意外恢复 JSON
  schema 描述，test 不捕获。
- **为什么有问题**: 与 F01 同一根因——plan contract 描述负向断言，implementation steps 只删除旧正向断言，
  不显式添加新负向断言。当前 test 的正向断言被删除后，JSON protocol 在 README 中的存在不再被
  `test_root_readme_matches_current_cli_public_contract` 检查。
- **直接证据**: 当前 test lines 378—380 有正向断言 `'"schema_version": 1' in readme`、`'"commands"' in
  readme`、`"不生成 shell" in readme`。§7.1 第 572—576 行要求 "删除" 这些并 "改为" 新 contract，但
  implementation steps 未显式添加 `assert "schema_version" not in readme` 或等价负向断言。
- **影响**: implementation agent 生成的 test 缺少 JSON protocol / "不生成 shell" 负向断言；README 意外恢复
  旧协议时不被捕获。风险为中等，因 §8 scans 的 `rg` 命令已覆盖 `schema_version.{0,160}commands` 等模式。
- **建议改法和验证点**: 在 §7.1 implementation steps 中增加一步：添加 `assert '"schema_version": 1' not in
  readme`、`assert '"commands"' not in readme`、`assert "不生成 shell" not in readme`（或等价精确
  负向断言）。验证同 F01。
- **修复风险**: 低
- **严重程度**: 中

## 10. Open questions

无。

## 11. Residual risks

| Risk | Severity | Tracking |
|---|---|---|
| Windows real-run release blocker | HIGH | umbrella §7.3/§9.4；PENDING_RELEASE_BLOCKER 直到 GitHub Actions run 通过 |
| stopped focused validation `1 failed, 152 passed, 2 skipped` | N/A | 历史 evidence；本轮未重跑 |
| F01/F02 test contract gap | MEDIUM | plan §7.1 implementation steps；需在 implementation 前修正 |

## 12. Conclusion

**PASS-WITH-RISKS。**

925-line corrected plan 在以下方面通过 adversarial review：

- R11-I2-VAL-PD-F01 已在 plan owner 中形成可执行、fail-closed 的单节点修复，finding 从 OPEN → FIXED →
  CONTROLLER-VALIDATED → 本轮 dual review。
- 22/8/15 path count 内部一致，与 §4/§7.1/§7.2/§9.1 逐项匹配，overlap accounting 正确。
- 唯一 shared path `tests/cli/test_arg_parsing.py` 只开放
  `test_root_readme_matches_current_cli_public_contract`，I1 parser/help tests 不被 I2 触及。
- batch-only `--infer`、no JSON、executable `.sh`/`.cmd` contract 在 plan 层正确描述。
- I1 owner 保护机制（before-lock hash、node-level diff review、allowlist 不扩大、不重开 producer/consumer）
  充分。
- Stopped product diff、staged set、HEAD、renderer/workflow locks 全部匹配。
- State machine 固定两个 slices、一次 cumulative code review、一次 accepted commit；Windows release-blocker
  sequence 正确。
- 唯一风险是 §7.1 test contract 的两条负向断言（direct upload `--infer`、JSON protocol）在 implementation
  steps 中未显式列出，可能导致 implementation agent 遗漏。修复风险低，需在 implementation 前补充。

Review artifact：`docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-review-mimo.md`。

PASS-WITH-RISKS；2 findings，0 open questions，1 residual risk。
