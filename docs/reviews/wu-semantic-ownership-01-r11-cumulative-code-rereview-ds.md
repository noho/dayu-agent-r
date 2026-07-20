# WU-SEMANTIC-OWNERSHIP-01 / R11 累计修复第二路完整深度重审

## 1. Scope、输入与授权边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- gate：R11 cumulative code-review fix 后的完整累计树第二路 complete re-review（AgentDS）。
- 不是新 WU、新 feature/issue 或 R12。

### 1.1 输入

| 输入 | 路径 | SHA-256 / 行数 |
|---|---|---|
| AGENTS.md | `AGENTS.md` | 128 行（已完整读取） |
| accepted plan | `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md` | `f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd` / 942 行 / 81,592 bytes |
| 初轮 AgentDS review | `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-ds.md` | `df6e61c3e947fca3450163eed4b6b2315f3e3cdf09a4736d6d3321fb56b8ccbf` / 126 行 |
| 初轮 AgentMiMo review | `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-mimo.md` | `e28a5473b34e2bacb26800aef22eb6efc1b6f8de8bec8070a36a621a29cdf18d` / 46 行 |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-controller-adjudication.md` | `87d27acd7d8af2db6079957914bebaa8a6c844a59aad2ab09e08bc77ec3e042e` / 100 行 |
| AgentCodex fix evidence | `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md` | `c6e24041994a61afca3208e6f869807da29b8c7a91cb57c3bcfb9d5d34f7b753` / 250 行 |
| Controller validation | `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-controller-validation.md` | `d514e74bc47e8c9c13a9bbdf1a529e7d2c5924d270d2dcc6e2ff05a1853e841e` / 95 行 / 4,939 bytes |

### 1.2 审查目标

以 immutable fix-evidence binary diff lock `6065289ee2a2da8d475de29fcd8b5d719ca1f0448e357e885a5ac0156fb6f424` 为 after-fix truth baseline，对完整 22-path product/test/README/packaging/workflow 累计树做**逐文件完整走读**。

### 1.3 累计 22-path tree manifest

| Status | Path | After-fix SHA-256 |
|---|---|---|
| A | `.github/workflows/r11-upload-script-windows.yml` | `8eae09d59e69413adbb2c49dc60c3c431834bab7f230c410b9e981100d3f84c5` |
| M | `README.md` | `b6e1bcfc...8733`（与 I2 evidence 一致） |
| M | `dayu/README.md` | `8b89eec6...994e`（与 I2 evidence 一致） |
| M | `dayu/cli/arg_parsing.py` | `d8442bc6...1b0e`（与 I2 evidence 一致） |
| M | `dayu/cli/commands/fins.py` | `2b022641e2d19daaf73b8787e3240a6c4e041b7b36fd66965f466275d9a1797f` |
| A | `dayu/cli/upload_script.py` | `dfe0508d...ea65`（与 I2 evidence 一致） |
| M | `dayu/fins/README.md` | `f93daf5b...218`（与 I2 evidence 一致） |
| M | `dayu/fins/upload_batch.py` | `95c543801a75c4428b8d2022000d23be644c3a706ca12c06568a8f3e1eda74f0` |
| D | `dayu/render/__init__.py` | working tree absent |
| D | `dayu/render/render.py` | working tree absent |
| D | `dayu/web/__init__.py` | working tree absent |
| D | `dayu/web/__main__.py` | working tree absent |
| D | `dayu/wechat/__init__.py` | working tree absent |
| D | `dayu/wechat/main.py` | working tree absent |
| M | `pyproject.toml` | `b71fd9ff...081e`（与 I2 evidence 一致） |
| M | `requirements.txt` | `de025c19...f63`（与 I2 evidence 一致） |
| M | `tests/README.md` | `478efffc...4c1`（与 I2 evidence 一致） |
| M | `tests/cli/test_arg_parsing.py` | `d3a4abcc...2658`（与 I2 evidence 一致） |
| M | `tests/cli/test_fins_commands.py` | `297ecc54...faaa`（与 I2 evidence 一致） |
| M | `tests/cli/test_public_package_entrypoints.py` | `e08d195e...0e0a`（与 I2 evidence 一致） |
| M | `tests/cli/test_upload_filings_from_command.py` | `758e4e3db093e456c62d872c74046c17357214e9dbeacd133d0d8d914f728fd7` |
| M | `tests/fins/test_upload_batch.py` | `1e3967ecadd77c8688640f02783b9283390a32e1a01b316ac88f83323bc2a1cf` |

- 22 unique paths：14 M + 6 D + 2 A = 22。staged 集合为空。
- Controller-owned dirty file `docs/host/issues-implementation-control.md` 不在 22-path product manifest 中，本轮仅读取且未修改。

### 1.4 重点审查面

1. **R11-DS-F02** 是否真实关闭（CLI material form 值域重复）
2. **R11-DS-F03** 是否真实关闭（Windows workflow `%TEMP%` locator）
3. **R11-DS-F01** no-fix boundary 是否保持（runtime extraction 拒绝）
4. CLI/Fins 唯一语义 owner（field-level propagation）
5. Windows exact evidence（renderer unit oracles、real-cmd test contract、workflow 确定性）
6. argv quoting / secret containment / atomic publish
7. placeholder 删除（6 package files + pyproject/requirements/wheel 零残留）
8. README/packaging（4 README 合同正确性、wheel metadata/entrypoint/archive 负向 oracle）
9. deferred Issue 142/151/175/177/178 与 Topic 8/9 未越界
10. 组合行为/回归（22 paths 整体一致性、无跨 owner 泄漏）

## 2. 历史 Finding Closure 审查

### 2.1 `R11-DS-F02` — CLOSED

**原始 claim**：CLI `_single_batch_material_form` 硬编码 `FINANCIAL_STATEMENTS` / `EARNINGS_CALL` / `EARNINGS_PRESENTATION`，重复了 Fins owner 的三个 material-form 值域。

**修复路径**（Controller 裁决：在 Fins request boundary 做唯一 owner validation，不在 CLI 公开常量）：

| 证据项 | 位置 | 直接证据 |
|---|---|---|
| `UploadBatchPlanRequest.material_form` 现在是 `str \| None` | `dayu/fins/upload_batch.py:214` | `material_form: str \| None = None` — 诚实表达为尚未验证的候选 |
| CLI `_single_batch_material_form` 不再拥有业务值域 | `dayu/cli/commands/fins.py:1166-1181` | 仅做 uppercase normalization（line 1181: `return normalized[0].upper()`），零业务值域判断 |
| Fins `_validated_material_form` 是唯一域值 owner | `dayu/fins/upload_batch.py:817-832` | `if normalized not in _MATERIAL_FORM_TYPES: raise UploadBatchPlanUsageError(...)` |
| CLI 三个业务字面量扫描 | `rg -n 'FINANCIAL_STATEMENTS\|EARNINGS_CALL\|EARNINGS_PRESENTATION' dayu/cli/commands/fins.py` | exit 1 / zero output |
| Fins owner invalid-value test | `tests/fins/test_upload_batch.py:176-195` | `test_invalid_material_form_is_rejected_by_fins_owner` 传入 `ESG_REPORT`，断言唯一 owner 抛出 `UploadBatchPlanUsageError("unsupported material form: ESG_REPORT")` |
| CLI propagation test | `tests/cli/test_upload_filings_from_command.py:180-220` | `test_material_form_candidate_reaches_fins_owner_and_maps_usage_exit` 传入 ` esg_report `，断言 CLI 传播 `ESG_REPORT` 候选、Fins owner 拒绝后返回 `EXIT_USAGE_ERROR`、workspace 未创建 |

**Verdict**：`CLOSED`。Fins 现在是 material form 值域的唯一 owner；CLI 只做输入规范化；没有 public constant、compatibility alias、fallback 或下游第二套值域校验。

### 2.2 `R11-DS-F03` — CLOSED（real Windows run = `PENDING_RELEASE_BLOCKER`）

**原始 claim**：Windows workflow 递归扫描整个 `%TEMP%` 寻找 pytest artifacts，依赖 tmp-path 实现并可能误取同名文件。

**修复路径**（Controller 裁决：在现有 test/workflow owner 内建立确定性 artifact locator）：

| 证据项 | 位置 | 直接证据 |
|---|---|---|
| Workflow `%TEMP%` / generic `-Filter` / `Copy-Item` 扫描 | `rg -n '%TEMP%\|Get-ChildItem.*-Filter\|Copy-Item' .github/workflows/r11-upload-script-windows.yml` | exit 1 / zero output |
| Tests 发布 exact 4 required files | `tests/cli/test_upload_filings_from_command.py:714-828` | recorder: `generated-upload.cmd` + `recorder-oracle.jsonl`；CLI: `cli-generated-upload.cmd` + `cli-grammar-oracle.json`；均写入显式 `DAYU_R11_WINDOWS_ARTIFACT_DIR` 子目录 |
| Workflow 只读取确定性路径 | `.github/workflows/r11-upload-script-windows.yml:83-123` | 精确路径：`cmd-recorder/generated-upload.cmd`、`recorder-oracle.jsonl`、`cli-storage/cli-generated-upload.cmd`、`cli-grammar-oracle.json`；含 SHA-256 hash 比对 |
| Workflow `pull_request.paths` 精确 22 | `python3` YAML parse | 22 unique，0 duplicate |
| No repo-local fallback | workflow lines 83-123 | 固定子目录，无 glob/wildcard/file-search fallback |
| `@pytest.mark.skipif(os.name != "nt")` | `tests/cli/test_upload_filings_from_command.py:714,759` | 两个 Windows test 仍保持真实 `cmd.exe /d /c`，无 unit 替代 |

**Verdict**：`CLOSED`。locator 不确定性已消除；workflow 和 tests 共同建立确定性证据发布-消费合约。**但真实 GitHub `windows-latest` / `cmd.exe` run 尚未发生，release gate 必须保持 `PENDING_RELEASE_BLOCKER`。** macOS 本地 skip、renderer unit oracle、YAML parse 均不能关闭或 waive 该 gate。

### 2.3 `R11-DS-F01` — REJECTED / NO FIX / boundary preserved

**Claim**：把三个 containment helper 提取到 `dayu.runtime`。

**No-fix boundary 验证**：

| 证据项 | 直接证据 |
|---|---|
| Fins source containment owner | `dayu/fins/upload_batch.py:877-892`（`_has_internal_symlink`）、`895-908`（`_is_within`）、`866-874`（`_lexical_absolute`）— 仅服务 source scanning |
| CLI output containment owner | `dayu/cli/upload_script.py:312-320`（`_lexical_absolute`）、`323-338`（`_has_internal_symlink`）、`341-354`（`_is_within`）— 仅服务 output publishing |
| `dayu.runtime` diff | git diff zero |
| New shared abstraction | 零 |
| Fins reverse import scan | exit 1 / zero output（`dayu.cli`/`dayu.service`/`dayu.host`/`dayu.engine`/`dayu.ui` 均不在 Fins imports） |
| `dayu.runtime` 唯一合法 import | `dayu/cli/commands/fins.py:21` (`import dayu.runtime.log as runtime_log`) — 既有日志基础设施，不是新增 runtime surface |

**Verdict**：`MAINTAINED`。两个 containment policy 继续由各自独立 owner 拥有；没有 runtime 公共 surface 扩张、没有跨包 abstraction、没有 drift。

### 2.4 AgentMiMo 初轮 review — PASS / 0 finding

初轮 AgentMiMo review 结论为 zero material finding。本轮重审未发现应推翻该结论的新证据。

## 3. CLI/Fins 唯一语义 Owner（field-level propagation）

沿 plan §5.3 producer-consumer mapping checklist 逐字段走读 `_upload_batch_command_argv` → `UploadBatchPlanRequest` → `generate_upload_batch_plan` 全链：

| Fins typed fact | CLI projection (`_upload_batch_command_argv`) | direct evidence |
|---|---|---|
| `UploadBatchFilingEntry` / `UploadBatchMaterialEntry` 分别映射到 `COMMAND_UPLOAD_FILING` / `COMMAND_UPLOAD_MATERIAL` | line 389-393 (`isinstance` dispatch) | entry type 是唯一 command discriminator；renderer 不再判型 |
| `ticker` + `aliases` → `--ticker` CSV | line 400-402 (`",".join((entry.ticker, *entry.aliases))`) | canonical 在首位，alias 按 tuple 顺序 |
| `action` → `--action` | line 404-405（非 auto 时显式写入） | `auto` 省略，`create`/`update` 显式；batch 无 delete |
| `file` → `--files` | line 409 | 每 entry 精确一个 path |
| `fiscal_year` / `fiscal_period` → `--fiscal-year` / `--fiscal-period` | lines 427-430 (`_append_optional_entry_metadata`) | 非 None 时写入；filing atomic checkpoint 必须二者都有值（Fins 已在 `generate_upload_batch_plan:333` 检查 `final_year is None or final_period is None` 则 skip） |
| `amended` → `--amended` | line 431-432 | `True` 时写入；`False` 时不写 |
| `filing_date` / `report_date` / `company_name` → 对应 flag | lines 433-438 | 非 None 时写入 |
| `overwrite` → `--overwrite` | line 439-440 | `True` 时写入；只表示 storage overwrite |
| `form_type` / `material_name` → `--forms` / `--material-name` | lines 407-408 | 仅属于 material entry |
| skipped `path` / reason_code / reason → summary only | `_render_upload_batch_summary:522-525` | 只进入 stdout human summary，不生成 argv |

**结论**：CLI 对文件名、raw fields、fiscal/material 规则零业务推断；所有 typed fact 从 Fins owner entry 机械投影，propagation contract 完整。

## 4. Windows Exact Evidence

### 4.1 Renderer unit oracles

| 验证面 | 位置 | 证据 |
|---|---|---|
| CRT 参数解析 | `tests/cli/test_upload_filings_from_command.py:449-476` | `test_windows_renderer_round_trips_fixed_argument_oracles`：空格、中文、单引号、双引号、反斜杠尾随、`%PATH% ! & \| ^ ( ) < >` 均 round-trip 恢复 |
| `_parse_single_windows_crt_argument` | lines 851-881 | 独立解析 production `_quote_windows_batch_argument` 的 CRT 双引号参数，逐元素比对 |
| Batch 安全头 | line 470-476 | `@echo off`、`chcp 65001 >nul`、`setlocal DisableDelayedExpansion` 精确匹配；`setlocal EnableDelayedExpansion` 零命中 |
| `%*` passthrough | line 473 | `%*\r\n` 在 content 中命中 |

### 4.2 Real `cmd.exe` test contract

| 验证面 | 位置 | 证据 |
|---|---|---|
| `test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` | lines 714-756 | `@pytest.mark.skipif(os.name != "nt")` — 真实 `cmd.exe /d /c`；fixed + adversarial + appended argv JSONL exact 比对；injection marker 不存在 |
| `test_windows_generated_script_runs_real_cli_into_temp_storage` | lines 759-828 | 真实 `cmd.exe /d /c` → CLI → Service → Fins → temp storage；exit 0 + portfolio artifacts 存在；`cli-grammar-oracle.json` 含 test node/result/hash/count/cmd invocation |
| deterministic artifact subdirectory | lines 63-89 (`_windows_test_artifact_directory`) | `DAYU_R11_WINDOWS_ARTIFACT_DIR` 存在时使用显式子目录，不存在时回退 `tmp_path`；无跨-TEMP 扫描 |

### 4.3 Workflow 确定性验证

| 验证面 | 证据 |
|---|---|
| `%TEMP%` / `-Filter` / `Copy-Item` 残留 | exit 1 / zero output |
| fix evidence path 强制存在性检查 | workflow line 90-94：四个 exact 文件必须存在；缺失即 throw |
| recorder oracle 单行检查 | line 97-99 |
| CLI oracle 字段对照 | lines 101-107 |
| hash 比对 | lines 109-111 |
| portfolio artifact count 交叉验证 | lines 113-122 |

### 4.4 Windows 算法特性

`_quote_windows_batch_argument`（`upload_script.py:198-223`）：

- percent doubling (`%%`) 应用于整个 argument，防止 `%VAR%` expansion
- 双引号字符前累计反斜杠按 `backslash_count * 2 + 1` 输出，同时满足 batch percent parsing 和 CRT 反斜杠-引号规则
- 尾随反斜杠在闭合引号前按 `backslash_count * 2` 输出
- `_escape_windows_comment`（lines 226-242）：percent 加倍 + metacharacter caret escaping

零 `subprocess.list2cmdline`、零 `shell=True`、零 `setlocal EnableDelayedExpansion`。

## 5. argv Quoting / Secret / Containment / Atomic Publish

### 5.1 POSIX quoting

| 验证面 | 位置 | 证据 |
|---|---|---|
| `shlex.join` 渲染 | `upload_script.py:168` | 唯一 POSIX renderer；builder 不做 `replace`/`escape` |
| `"$@"` passthrough | `upload_script.py:168` | 每行末尾，caller 追加参数逐元素传播 |
| Real `/bin/sh` recorder | `test_upload_filings_from_command.py:396-446` | 空字符串、空格、中文、单引号、双引号、尾随反斜杠、`$(touch marker)` injection, `& \| ^ ( ) < > %PATH% !` 逐元素恢复；marker 不存在 |

### 5.2 Secret containment

| 验证面 | 证据 |
|---|---|
| FMP_API_KEY env 读取 | `commands/fins.py:304` — 仅从环境读取；不写入 request/plan/script |
| 脚本 body 零 `--infer` | `test_infer_resolves_once...:315` — `--infer` 只在 regenerate comment 出现（line 318: `--infer` in `content.splitlines()[2]`），body 不含 |
| API key 零入脚本 | `test_infer_resolves_once...:319` — `secret not in content` |
| provider URL 零入脚本 | `test_infer_resolves_once...:320` — `"financialmodelingprep.com" not in content` |
| API key 零入 stdout | `test_infer_resolves_once...:321` — `secret not in capsys.readouterr().out` |
| POSIX generated script scan | fix evidence §5.4 — zero hits |
| Windows generated `.cmd` scan | fix evidence §5.4 — zero hits |

### 5.3 Containment

| 验证面 | Fins source | CLI output | evidence |
|---|---|---|---|
| lexical root self-symlink 拒绝 | `upload_batch.py:290-291` | `upload_script.py:264-267` | 两个 owner 独立实现相同策略 |
| 内部 component/candidate symlink 拒绝 | `upload_batch.py:408-416` | `upload_script.py:289-292` | 独立 `_has_internal_symlink` |
| resolved escape 拒绝 | `upload_batch.py:418-425` | `upload_script.py:298-308` | 独立 `_is_within` |
| external ancestor symlink 允许 | `tests/fins/test_upload_batch.py:392-405` | `tests/cli/test_upload_filings_from_command.py:553-571` | 独立测试；independent policy owner |

### 5.4 Atomic publish

| 验证面 | 位置 | 证据 |
|---|---|---|
| mkstemp in target directory | `upload_script.py:125-130` | `dir=target.parent` — same-directory temp |
| flush + fsync | lines 140-141 | write → flush → fsync |
| POSIX chmod 0o755 | line 143-144 | 仅 POSIX |
| os.replace | line 145 | 原子替换 |
| temp cleanup on failure | lines 146-150 | close fd + unlink(missing_ok=True) |
| old target preservation | `test_publisher_preserves_old_target...:479-512` | replace 失败后 `target.read_bytes() == b"old-target\n"`，零 `.tmp` 残留 |

## 6. Placeholder 删除与 Packaging

### 6.1 Source tree 删除

| 验证面 | 证据 |
|---|---|
| 6 package files working tree | 全部 absent（`exists()=False`） |
| git index tracking | `git ls-files` 仍列出 6 个 D 状态路径（预期行为—未 commit） |
| old placeholder public surface scan | exit 1 / zero output（`dayu-web`/`dayu-wechat`/`dayu-render`/`dayu.(web\|wechat\|render)` 零命中） |
| `[web]` extra scan | exit 1 / zero output |

### 6.2 pyproject.toml

| 验证面 | 证据 |
|---|---|
| `[project.scripts]` | 仅 `dayu-cli = "dayu.cli.main:main"`（line 96） |
| placeholder scripts | `dayu-web`/`dayu-wechat`/`dayu-render` 均在 scripts 中缺席 |
| `web` optional dependency | 已删除（原 line 74-78 区域） |
| `dayu.render` package-data | 已删除（原 mapping 区域） |

### 6.3 requirements.txt

| 验证面 | 证据 |
|---|---|
| `[web]` extra 消费 | 已删除 — line 11 为 `-e .[test,dev,browser]`，无 `[web]` |
| Streamlit stale 承诺 | 已删除 |

### 6.4 Wheel gates（来自 fix evidence §5.2）

| 验证面 | 证据 |
|---|---|
| METADATA `Provides-Extra: web` | 0 |
| METADATA Streamlit requirement | 0 |
| entry_points.txt placeholder scripts | 0 |
| extracted `dayu/web/` / `dayu/wechat/` / `dayu/render/` | 0 |
| RECORD placeholder paths | 0 |
| fresh venv constrained install | PASS — `pip check`: `No broken requirements found.` |
| `dayu-cli --help` | exit 0 |
| `dayu-cli upload_filings_from --help` | exit 0 |
| `dayu.web` / `dayu.wechat` / `dayu.render` importability | 0（全部 `find_spec is None`） |

### 6.5 负向 import-boundary sentinels

| sentinel | 位置 | 命中 |
|---|---|---|
| `"dayu.web"` | `tests/tools/web/test_web_tools_provider.py` | 1 |
| `"dayu.web"` | `tests/tools/web/test_diagnose_web_access.py` | 2 |

两个 sentinel 文件无 diff（不在 22-path allowlist 中），精确保持既有 contract。

## 7. README 合同正确性

### 7.1 根 `README.md`

`test_root_readme_matches_current_cli_public_contract`（`tests/cli/test_arg_parsing.py:358-397`）覆盖：

- **正向 assertions**：`upload_filings_from` batch-only `--infer` + `FMP_API_KEY`、`upload_filings_<TICKER>.sh` / `.cmd`、`/bin/sh` / `cmd.exe /d /c`
- **负向 assertions**：direct upload section 无 `--infer`、旧 `"schema_version": 1` / `"commands"` / "不生成 shell" 均不存在
- **removed flags**：`write`、`--ci`、`--web-provider`、`--new-session` 等已删除参数均不在 README 中
- manual 走读确认：批量上传章节含 default/output/ticker CSV/infer/recursive/overwrite、脚本执行入口、追回参数说明、symlink 约束、skip reason 排障

### 7.2 `dayu/README.md`

- 旧 Web/WeChat/render placeholder 写成当前稳定 package boundary 的 stale 承诺已删除
- 当前只说明真实 package
- 分层、装配、future capability 未改变

### 7.3 `dayu/fins/README.md`

- §"Batch upload plan"（lines 184-199）完整描述 typed scan/classification owner、OLD 规则/caps/skip contract、CLI consumer boundary
- 不写 workflow/review 过程

### 7.4 `tests/README.md`

- Windows gate 命令精确列出两个 real `cmd.exe` test nodes + 一个 parser node
- 注明非 Windows 本地 skip 不能替代 workflow 真实 runner 证据

四份 README diff 精确匹配 allowlist；正向 scan 覆盖最终用户 command/output/infer/auto contract。

## 8. Deferred Boundary 审查

### 8.1 Production diff（Service/Host/Engine/runtime/config/tool/UI/constraints/design）

- `git diff 2b14b2fbc89654267e3d33daa2ae410ceff45e68 -- dayu/service dayu/host dayu/engine dayu/runtime dayu/config dayu/tool dayu/ui constraints docs/host/design.md docs/engine/design.md docs/tool/design.md docs/fins/design.md docs/ui/design.md`：零 diff（仅 Controller-owned `docs/host/issues-implementation-control.md` 和 `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md` 出现在 docs/ diff 中，均为 plan/control 自变更）

### 8.2 Issue 142/151/175/177/178

| 验证面 | 证据 |
|---|---|
| production code added-line scan | exit 1 / zero output（无生产代码新增包含这些 issue 号） |
| 功能实现 | 无 — 仅 README 删除 placeholder 与明确 no-touch 说明 |

### 8.3 Topic 8/9

| 验证面 | 证据 |
|---|---|
| Engine 240-char projection | 无 diff |
| unified authorization | 无 diff |
| workspace trust / shell sandbox | 无 diff |
| 本轮安全结论 | 仅覆盖 source/output containment、symlink、atomic write、argv injection、secret non-persistence |

### 8.4 R12 / init

| 验证面 | 证据 |
|---|---|
| init grammar mutation | 无 |
| workspace mutation | 无 |
| provider/model/API-key setup | 无 |
| prewarm | 无 |

## 9. 组合行为与回归

### 9.1 POSIX real smoke

- `test_posix_script_round_trips_adversarial_argv_with_real_sh`：真实 `/bin/sh` 执行，逐元素比对 9+ 对抗参数 + 3 appended 参数；injection marker 不存在 — PASS
- `test_posix_generated_script_runs_real_cli_into_temp_storage`：真实 `python -m dayu.cli` → `/bin/sh` → parser → Service → Fins → temp storage；exit 0、两条 `Fins succeeded`、portfolio 含 `filing` + `material` source_kinds — PASS

### 9.2 Layer boundaries

- Fins → CLI/Service/Host/Engine/UI reverse import：零
- CLI → Host/Engine/storage reverse import：零
- Renderer → filename/fiscal/material classifier：零
- `list2cmdline` / `shell=True` / `setlocal EnableDelayedExpansion`：零
- `hasattr` / `getattr` / `Any` / `object` seams：零
- `type: ignore` / `noqa` / coverage pragma：零

### 9.3 Related suites

- 两项既有 Service baseline failures：精确保持 same two tests、same owner blobs 无 diff
- 无第三项 / new R11 failure

### 9.4 Coverage

| Changed production file | Whole-file line coverage |
|---|---|
| `dayu/fins/upload_batch.py` | `95.57%` |
| `dayu/cli/commands/fins.py` | `90.87%` |
| `dayu/cli/arg_parsing.py` | `99.66%` |
| `dayu/cli/upload_script.py` | `91.37%` |

四文件均 `>= 80.00%`。

### 9.5 Full pyright

`0 errors, 0 warnings, 0 informations` — 覆盖 `dayu/ tests/ utils/`。

### 9.6 Ruff

- scoped：`All checks passed!`
- full：baseline/current 均为 144 findings；`current_only=0`；version oracle `ruff 0.15.11` 精确匹配

## 10. Findings

### 本轮新 material findings

**0**（未发现新的实质性缺陷、边界违反或回归）。

### 历史 finding closure ledger

| Finding | 状态 | 审查结论 |
|---|---|---|
| `R11-DS-F01` | `REJECTED / NO FIX` | boundary maintained — Fins source containment 与 CLI output containment 继续由两个独立 policy owner 拥有；`dayu.runtime` 无新增 surface |
| `R11-DS-F02` | `CLOSED` | Fins 是 material form 值域唯一 owner；CLI 零值域副本；Fins owner test + CLI propagation test 通过 |
| `R11-DS-F03` | `CLOSED` | workflow 确定性 locator 合约成立；test/workflow 发布-消费 exact 4 files + hash 比对；real Windows run 仍是 `PENDING_RELEASE_BLOCKER` |
| AgentMiMo 初轮 | `NONE` | zero material finding，无新证据推翻 |

### accepted/open

`0`

### blocker

`0` local fix blocker；real Windows `cmd.exe` / `windows-latest` run 仍是 `PENDING_RELEASE_BLOCKER`（不能用 macOS skip、YAML parse、renderer unit 关闭）

## 11. Open Questions

无。

## 12. Residual Risk

1. **Windows real run** (`PENDING_RELEASE_BLOCKER`)：真实 GitHub `windows-latest` / `cmd.exe` 尚未执行。本地 macOS skip 已验证 test contract 和 workflow 确定性，但真实 `cmd.exe` parsing、CRT backslash-quote 算法、UTF-8/CRLF 编码在 Windows 文件系统上的行为尚未被真实 runner 证明。该 gate 必须在 umbrella aggregate acceptance / draft PR check 触发并通过；任何未执行、skip、失败、artifact 缺失或 oracle 不相等都阻止 acceptance。

2. **两项既有 Service baseline failures**：保持 HEAD-existing 分类，不属于 R11 fix scope。在 Windows real run 中若因 test ordering 或 `cmd.exe` subprocess handling 意外触发新 failure，需按既有 owner 分类裁决。

## 13. Verdict

```
PASS / READY_FOR_CONTROLLER_R11_REREVIEW_CHECKPOINT
```

- 22-path cumulative tree 完整走读完成；无新增 material finding
- `R11-DS-F02` / `R11-DS-F03` closed，`R11-DS-F01` no-fix boundary maintained
- CLI/Fins 唯一语义 owner contract 完整；field-level propagation 无 gap
- argv quoting / secret containment / atomic publish contract 全部成立
- placeholder 删除完整（6 package files absent + wheel 4 项负向 oracle + pyproject/requirements 更新）
- 4 README 合同正确，测试断言与当前 public contract 一致
- deferred Issue 142/151/175/177/178 与 Topic 8/9 无越界
- 组合行为/回归无异常
- real Windows run = `PENDING_RELEASE_BLOCKER`
- accepted/open local finding = `0`；blocker = `0`
- R11 accepted implementation commit、R12、stage/commit、push、PR 仍未授权

**Controller checkpoint reached.**
