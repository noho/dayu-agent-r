# WU-SEMANTIC-OWNERSHIP-01 / R11 cumulative code review — AgentDS

## Scope

- Mode: current changes（immutable uncommitted tree review）
- Branch: `phaseflow/host-issues-control`
- Base: `7972c3c0ba8628173fc91c362b9394655f60678e`（R11 I2 wheel smoke plan correction，HEAD）
- Output file: `docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-ds.md`
- Review timestamp: 2026-07-18T05:20:18+08:00
- Included scope: 22 unique product/test/README/packaging/workflow paths — I1 `8` + I2 `15`，shared `1` (`tests/cli/test_arg_parsing.py`)
- Tracked diff binary SHA-256: `6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`
- Staged: empty
- Artifact lock: AgentCodex evidence `57fb654d...a3ba` matched; Controller validation `7023a718...8902d1` matched
- Excluded scope: Controller-owned control/plan/authorization/adjudication artifacts（只读）; `tests/fins/test_fmp_company_info_resolver.py`（只读 sentinel）; two HEAD-existing Service failures（owner 不在 R11）
- Parallel review coverage: 无。本 review 由 AgentDS 单路完整走读全部 22 文件。

## Review method summary

完整阅读了全部 22 个 changed/current files 的完整内容（不是摘要），沿途走读了关键调用链：
`parse_cli_args → _run_upload_filings_from → generate_upload_batch_plan → _upload_batch_command_argv → render_upload_script → publish_upload_script → _render_upload_batch_summary`，
并反向验证了 `upload_batch.py` 零 CLI/Service/Host/Engine/UI import、`upload_script.py` 零 filename regex/fiscal/material classifier、`fins.py` 零 Host/Engine/storage import。

对 adversarial failure pass 检查了：空字符串、Unicode、引号/反斜杠、batch percent/CRT metacharacter、cmd.exe delayed expansion、containment/symlink/atomic replace/rollback、secret non-persistence、JSON 零残留、placeholder 零残留、deferred Issue/Topic 零 diff。

对 semantic ownership drift pass 检查了：Fins 是否唯一产生 fiscal/material/cap/skip；CLI builder 是否零业务推断；renderer 是否只消费 `tuple[str, ...]`；test fixtures 是否断言 owner contract 而非偶然值。

## Findings

### R11-DS-F01-[中]-三个 containment/symlink helper 在 `upload_batch.py` 与 `upload_script.py` 中重复实现

- **入口/函数**: `_lexical_absolute`、`_is_within`、`_has_internal_symlink`
- **文件(行号)**:
  - `dayu/fins/upload_batch.py:866-874` (`_lexical_absolute`)、`877-892` (`_has_internal_symlink`)、`895-908` (`_is_within`)
  - `dayu/cli/upload_script.py:312-320` (`_lexical_absolute`)、`323-338` (`_has_internal_symlink`)、`341-354` (`_is_within`)
- **输入场景**: Fins 扫描 source files 和 publisher 解析 output target 时各自独立执行 containment/symlink 判定。
- **实际分支**: 两个模块中的三个函数体逻辑完全一致（仅参数名 `candidate`↔`target` 和 docstring 不同）。Fins 的 `_has_internal_symlink` 使用 `candidate.relative_to(root)`，publisher 的 `_has_internal_symlink` 使用 `target.relative_to(root)`——逻辑等价。
- **预期行为**: 按 `CLAUDE.md` "重复逻辑必须抽取"约束，这些纯 `pathlib`/`os` 工具函数不依赖 Fins 或 CLI 业务语义，应放入 `dayu.runtime`（层中立基础设施）或一个共享私有 helper 模块，由两方复用同一真源。
- **实际行为**: 两个模块各自拥有独立副本。当前行为正确，但约 60 行安全关键代码需要双维护：任何 containment/symlink 判定逻辑的 bug fix 或增强（例如新增 `junction`/`mount point` 判定、Windows `\\?\` prefix 处理）必须同时在两个模块中一致修改，否则会产生安全语义漂移——例如 Fins 允许的路径被 publisher 拒绝，或反之。
- **直接证据**:
  - `_lexical_absolute`: 两处均 `return Path(os.path.abspath(path.expanduser()))`（upload_batch.py:874, upload_script.py:320）
  - `_is_within`: 两处均 `try: path.relative_to(root); except ValueError: return False; return True`（upload_batch.py:904-907, upload_script.py:350-353）
  - `_has_internal_symlink`: 两处均遍历 `relative.parts` 逐组件 `is_symlink()`（upload_batch.py:886-891, upload_script.py:332-337）
- **影响**: 维护风险——安全关键逻辑的修复可能在两个边界之间漂移。当前阶段无实际错误，但属于 `CLAUDE.md` 明确禁止的"在各层自行实现语义不一致的重复 runtime helper"模式。
- **建议改法和验证点**: 将三个函数提取到 `dayu.runtime.path_containment`（或等价层中立模块），Fins 和 publisher 改为 import 同一实现。验证点：1) 两处 `_lexical_absolute` 调用方的行为不变；2) Fins source containment 判定不变；3) publisher output containment 判定不变；4) 现有 focused tests 全绿；5) `dayu.runtime` import boundary 不引入 Fins/CLI/Service/Host/Engine 依赖。
- **修复风险（低）**: 纯重构，不改变逻辑。风险仅在于未发现的路径解析平台差异（macOS 与 Windows `os.path.abspath` / `Path.resolve` 的细微差异已在现有测试中覆盖）。
- **严重程度（中）**: 影响 maintainability，security-relevant 代码的双维护风险属于结构性缺陷。当前无 correctness 影响。

### R11-DS-F02-[低]-CLI `_single_batch_material_form` 硬编码 Fins owner 的 material form 枚举值

- **入口/函数**: `_single_batch_material_form`
- **文件(行号)**: `dayu/cli/commands/fins.py:1167-1189`，具体为第 1183-1187 行
- **输入场景**: 用户通过 `--material-forms` 传入 CLI 字符串，CLI 在调用 Fins 前做前置输入校验。
- **实际分支**: 第 1183-1187 行硬编码了 `("FINANCIAL_STATEMENTS", "EARNINGS_CALL", "EARNINGS_PRESENTATION")` 进行 `not in` 判定。而 Fins owner `upload_batch.py:830` 使用 `_MATERIAL_FORM_TYPES` frozenset（从 `_MATERIAL_ROUTING_TABLE` 第 100-109 行自动派生）作为同一枚举的真源。
- **预期行为**: CLI 对用户输入做前置校验是合理的 input boundary 行为（plan §4 允许 CLI 拥有 `explicit 与 inferred company/aliases merge` 所有权），但校验所用枚举值应从 Fins owner 导入或至少与 `_MATERIAL_FORM_TYPES` 保持自动同步，而非独立硬编码。
- **实际行为**: CLI 硬编码值与 Fins `_MATERIAL_FORM_TYPES` 当前一致，行为正确。若 Fins 新增 material form 类型（如 `ESG_REPORT`），CLI 硬编码可能滞后导致 CLI 先行拒绝合法输入——但 Fins 的 `_validated_material_form` 是最终防线，CLI 滞后只会导致错误消息时机不同，不会漏过非法值。
- **直接证据**: `fins.py:1183-1187` 的 `form_type not in ("FINANCIAL_STATEMENTS", "EARNINGS_CALL", "EARNINGS_PRESENTATION")` vs `upload_batch.py:830` 的 `normalized not in _MATERIAL_FORM_TYPES`（`_MATERIAL_FORM_TYPES` 是由 `_MATERIAL_ROUTING_TABLE` 第 107-109 行自动派生的 frozenset）。
- **影响**: 低。Fins owner 是最终校验者；CLI 硬编码滞后不影响 correctness，仅影响用户体验（命令行阶段拒绝 vs Fins boundary 拒绝的错误消息差异）。
- **建议改法和验证点**: 从 `dayu.fins.upload_batch` 导入 `MaterialFormType` 的合法值集合（可以新增一个公开常量或直接使用 `_MATERIAL_FORM_TYPES` 改为 public），用于 CLI 输入校验。验证点：1) `_single_batch_material_form` 的接受/拒绝行为不变；2) 新增 material form 时仅需修改 Fins owner 一处；3) focused tests 全绿。
- **修复风险（低）**: 将 `_MATERIAL_FORM_TYPES` 从模块私有提升为 public 常量（或新增 public alias），属于可控的 contract surface 微调。
- **严重程度（低）**: 不影响当前 correctness，属于代码演进 hygiene 问题。

### R11-DS-F03-[低]-Windows workflow 以 `Get-ChildItem -Recurse $env:TEMP` 搜索 pytest 产物，依赖内部实现细节

- **入口/函数**: Windows gate workflow 的 "Run real cmd recorder and CLI storage gates" step
- **文件(行号)**: `.github/workflows/r11-upload-script-windows.yml:82-84`
- **输入场景**: GitHub Actions `windows-latest` runner 上 pytest 使用 `tmp_path` 在系统临时目录创建测试文件，workflow 通过 `Get-ChildItem -Path $env:TEMP -Filter generated-upload.cmd -File -Recurse` 查找。
- **实际分支**: `Get-ChildItem` 递归扫描整个 `%TEMP%` 目录树，查找 `generated-upload.cmd`、`recorded.jsonl`、`upload_filings_AAPL.cmd` 三个文件。
- **预期行为**: 测试应将产物路径写入确定位置（如 `$env:DAYU_R11_WINDOWS_ARTIFACT_DIR`），workflow 从确定位置读取，不依赖 `tmp_path` 的内部实现细节（`tmp_path` 的基目录由 `tmp_path_factory.getbasetemp()` 决定，当前恰好位于 `%TEMP%` 下，但 pytest 不承诺此行为永远不变）。
- **实际行为**: 当前可工作（clean runner 上 `%TEMP%` 中文件少、搜索快），但存在三个脆弱点：
  1. pytest 未来版本可能改变 `tmp_path` 的基目录，使其不在 `%TEMP%` 下（例如使用 `XDG_RUNTIME_DIR` 或项目本地 `.pytest_temp`），导致 `Get-ChildItem` 零命中 → `throw` 触发 workflow failure；
  2. 若 runner 上 `%TEMP%` 包含大量文件（其他 tool/action 残留），递归扫描可能耗时较长（30-minute timeout 应足够，但浪费预算）；
  3. 文件名 `generated-upload.cmd` 和 `recorded.jsonl` 是通用名，若同 runner 上有其他 job 恰好生成同名文件（极低概率但非零），会被误识别。
- **直接证据**: workflow line 82 `$recorderScripts = @(Get-ChildItem -Path $env:TEMP -Filter generated-upload.cmd -File -Recurse)`，line 83 同理搜索 `recorded.jsonl`，line 84 搜索 `upload_filings_AAPL.cmd`。
- **影响**: 低——当前 PENDING_RELEASE_BLOCKER 状态表明 Windows gate 尚未在真实 runner 上通过，此脆弱性在首次真实 run 中可能暴露。即使通过，未来 pytest 版本升级可能导致 workflow 静默断裂。
- **建议改法和验证点**: 让测试（`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` 和 `test_windows_generated_script_runs_real_cli_into_temp_storage`）将产物路径写入 `os.environ.get("DAYU_R11_WINDOWS_ARTIFACT_DIR")`（若已设置），workflow 直接从该目录读取，不再扫描 `%TEMP%`。验证点：1) 本地 macOS `skip` 行为不变；2) 未来真实 Windows run 时产物路径确定可读；3) workflow 无需 `-Recurse $env:TEMP`。
- **修复风险（低）**: 仅在测试中添加条件写入逻辑，不改变 production code 或 test assertions。
- **严重程度（低）**: 不影响产品代码 correctness，属于 CI/CD pipeline robustness 问题。可在首次真实 Windows run 前修复，也可作为 Windows gate 首次运行后的 follow-up。

## Open Questions

1. **为何 `_lexical_absolute` / `_is_within` / `_has_internal_symlink` 未放入 `dayu.runtime`？** plan §4 的 semantic owner map 将 source containment 分配给 Fins、output containment 分配给 publisher，这可能被理解为两层应各自拥有 containment 逻辑（即使实现相同）。若这是有意的 architecture decision（两层独立演进 containment policy），则 R11-DS-F01 不成立。建议 Controller 裁决：是"两层有意独立 ownership"（reject 此 finding）还是"重复代码应抽取到 runtime"（accept 此 finding）。

2. **`_single_batch_material_form` 硬编码是否是故意的 defense-in-depth？** 若 CLI 有意不依赖 Fins import 来做输入校验（避免 CLI import Fins 只是为了拿到枚举值），则 R11-DS-F02 是合理的 trade-off。此时可考虑将 `MaterialFormType` 的字面量集合提升为 `dayu.fins.upload_batch` 的公开常量，CLI 显式 import 该常量——既不复用私有 `_MATERIAL_FORM_TYPES`，也不硬编码。

3. **`_optional_stripped_text`（CLI）与 `_optional_text`（Fins）的语义差异是否记录在案？** 两函数逻辑等价但分别属于 CLI input boundary 和 Fins field normalization。当前行为一致，但若未来一方的 strip 策略变化（例如 CLI 增加 `\x00` 剔除），另一方不会自动同步。是否需要显式 contract 说明"CLI 和 Fins 各自独立拥有自己的 optional-text normalization"？

## Residual Risk

1. **真实 Windows `cmd.exe` run 未执行**：两个 Windows-only test nodes (`test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`、`test_windows_generated_script_runs_real_cli_into_temp_storage`) 在本地 macOS 明确 `skip`。Windows quoting 算法的正确性仅由平台无关的 unit oracle（`_parse_single_windows_crt_argument` 模拟 CRT 解析）证明，真实 `cmd.exe /d /c` 的 adversarial argv round-trip 尚未发生。Controller validation 已将此项标记为 `PENDING_RELEASE_BLOCKER`——本 review 确认此状态无误，Windows gate 在 GitHub Actions 真实通过前不能关闭。

2. **两项 HEAD-existing Service failures**：`test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` 与 `test_service_does_not_import_forbidden_layers` 是两个稳定复现的 repository baseline failure。已验证六个直接 owner blob（`dayu/service/`、`dayu/runtime/config_loader.py`、两个 test files）的 working blob 均等于 `HEAD:<path>` blob，R11 零 diff 于这些路径。这两个 failure 不是 R11 引入的，但意味着 repository test suite 并非全绿——任何依赖 `pytest tests -q` 全绿的 downstream gate 应显式处理这两项 expected failure。

3. **`dayu.runtime` import boundary 未因新增三个 duplicated helpers 而扩大**：若 accept R11-DS-F01，需确保 `dayu.runtime` 在引入新 helper 模块后仍满足"零 `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins` import"约束。当前 `dayu.runtime` 仅依赖标准库与 `dayu.contracts`，新增纯 `pathlib`/`os` helper 不应破坏此边界。

4. **Coverage 在 macOS 与 Windows 之间不可直接比较**：四个 changed production files 的 coverage 值（95.25%、90.04%、99.66%、91.37%）均在 macOS arm64 Python 3.11 上采集。Windows `cmd.exe` 相关的 production code path（`_render_windows_script`、`_escape_windows_comment`、`_quote_windows_batch_argument`）的 coverage 来自平台无关 unit tests。真实 `cmd.exe` 集成测试不在 coverage 统计中，覆盖率数字不能完全代表 Windows 路径的测试充分性。

## Verdict

**PASS — 无阻塞性 finding。** 22-path immutable cumulative tree 可进入 Controller adjudication。

三个 findings 均为 MEDIUM 或 LOW 严重程度，不影响当前 correctness。R11-DS-F01（代码重复）是其中最值得修复的结构性问题，但当前无行为错误；R11-DS-F02（枚举硬编码）是 hygiene 问题；R11-DS-F03（workflow 脆弱性）在真实 Windows run 前修复即可。

实施质量亮点（非 findings，但值得记录以说明 review depth）：
- Fins `upload_batch.py` 严格实现了全部 OLD 分类规则（Q4/FY/material/caps/skip），零 CLI/Service reverse import，零 `hasattr`/`getattr`/`Any`。
- CLI `_upload_batch_command_argv` 纯机械投影 typed entry 到 `tuple[str, ...]`，零 filename regex/fiscal/material 重算。
- POSIX renderer 正确使用 `shlex.join` + `"$@"`，Windows renderer 正确实现 batch-percent + CRT quoting 且有 `setlocal DisableDelayedExpansion`。
- Publisher 正确实现 same-directory temp + flush/fsync + atomic `os.replace` + old-target preservation + temp cleanup + POSIX `chmod 0o755`。
- 测试断言 owner contract 行为（Q4/FY oracles、material routing precedence、caps、同期优先级、containment/symlink boundary），非偶然 fixture 固化。
- Secret scan（FMP_API_KEY provider URL）针对 generated script executable body 和 regeneration comment 分别验证，确保 body 零 secret。placeholder 零残留由 wheel archive/METADATA/entrypoints/RECORD 四重负向 oracle 证明。
- Six placeholder package files working-tree absent，index 中 `D` status 正确。

## Finding Ledger

| ID | Severity | Category | Status |
|---|---|---|---|
| R11-DS-F01 | 中 | maintainability — 代码重复 | open → Controller adjudicate |
| R11-DS-F02 | 低 | maintainability — 枚举硬编码 | open → Controller adjudicate |
| R11-DS-F03 | 低 | CI robustness — workflow 脆弱性 | open → Controller adjudicate |

## Residual Risks Summary

| Risk | Category | Mitigation |
|---|---|---|
| 真实 Windows `cmd.exe` run 未发生 | release blocker | PENDING_RELEASE_BLOCKER；GitHub Actions 真实 run 通过前不关闭 |
| 两项 HEAD-existing Service failures | repository baseline | R11 owner 无权修复；downstream gate 需显式处理 |
| macOS coverage 不代表 Windows path | coverage | Windows code path 在平台无关 unit tests 中有覆盖，但无真实 `cmd.exe` integration coverage |
