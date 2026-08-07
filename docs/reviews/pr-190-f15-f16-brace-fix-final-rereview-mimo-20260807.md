# Code Review

## Scope

- Mode: current changes
- Branch: codex/interactive-oracle
- Base: 1a339fd9e046b959a96d290297930279204790f4
- Output file: docs/reviews/pr-190-f15-f16-brace-fix-final-rereview-mimo-20260807.md
- Included scope: `utils/cli_ci_run_observation.py`, `tests/cli/test_cli_ci_run_observation.py`, `docs/cli_ci.md`, `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`, `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`, `tests/README.md`
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

### P0-P3 Finding Summary

**未发现实质性问题。**

本次改动是针对 DeepSeek P3-02 finding 的最小修复，改动范围精确、测试覆盖完整、semantic ownership 无漂移。

---

### P3-02 Regex Boundary Fix 复验

#### 1. 唯一 regex boundary 新增花括号

**入口/函数**: `utils/cli_ci_run_observation.py:_RAW_DATABASE_PATH_PATTERN` (line 43-46)

**文件(行号)**: `utils/cli_ci_run_observation.py:43-46`

**输入场景**: 任意可能嵌入 raw SQLite 路径的文本

**实际分支**: regex 左边界新增 `[\[\{]`，右边界新增 `[\]\}]`

**预期行为**: 覆盖非 JSON stdout/stderr 文本中由花括号包围的 main/WAL/SHM 路径

**实际行为**: regex 正确匹配花括号包围的路径，同时保持对普通路径的不误判

**直接证据**:
- 旧 regex: `r"(?i)(?:^|[\s\"'=:(])[^\s\"'<>]*\.(?:sqlite|sqlite3|db)(?:$|[\s\"',;)])"`
- 新 regex: `r"(?i)(?:^|[\s\"'=:(\[\{])[^\s\"'<>]*\.(?:sqlite|sqlite3|db)(?:-(?:wal|shm))?(?:$|[/\\?#\s\"',;)\]\}])"`
- 左边界: `[\s\"'=:(]` → `[\s\"'=:(\[\{]`
- 右边界: `[\s\"',;)]` → `[/\\?#\s\"',;)\]\}]`
- 新增可选组: `(?:-(?:wal|shm))?`

**影响**: 修复了 final scanner 扫描非 JSON stdout/stderr 文本时遗漏花括号包围路径的问题

**建议改法和验证点**: 已修复，无需额外改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

#### 2. main/WAL/SHM 非JSON文本命中

**入口/函数**: `utils/cli_ci_run_observation.py:classify_public_evidence_path()` (line 245-263)

**文件(行号)**: `utils/cli_ci_run_observation.py:245-263`

**输入场景**: 包含 raw SQLite 路径的文本，包括花括号包围的 stdout/stderr 风格

**实际分支**: `_RAW_DATABASE_PATH_PATTERN.search(value)` 匹配成功时返回 `RAW_DATABASE`

**预期行为**: 花括号包围的 main/WAL/SHM 路径必须被拒绝

**实际行为**: 测试 `test_public_evidence_path_classifier_rejects_brace_wrapped_database_paths` 覆盖三种场景：
- `"stdout: {/private/ci/.dayu/host/dayu_host.sqlite}"`
- `"stderr: {.dayu/host/dayu_host.sqlite3-wal}"`
- `"trace: {C:\\dayu\\runtime\\runtime_lanes.db-shm}"`

全部返回 `PublicEvidencePathClassification.RAW_DATABASE`

**直接证据**: 测试 line 88-109

**影响**: 确保 final scanner 能正确识别非 JSON 文本中的 raw DB 路径

**建议改法和验证点**: 已验证，无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

#### 3. 普通反例不误判

**入口/函数**: `utils/cli_ci_run_observation.py:classify_public_evidence_path()` (line 245-263)

**文件(行号)**: `utils/cli_ci_run_observation.py:245-263`

**输入场景**: 包含 SQLite 相关词汇但不是 raw DB 路径的普通路径

**实际分支**: `_RAW_DATABASE_PATH_PATTERN.search(value)` 不匹配时返回 `PUBLISHABLE`

**预期行为**: 普通路径不得因 SQLite 相关词汇或中间后缀被误排除

**实际行为**: 测试 `test_public_evidence_path_classifier_keeps_ordinary_paths` 覆盖五种反例：
- `"reports/sqlite-summary.json"`
- `"database/report.json"`
- `"archives/report.db.backup"`
- `"notes/report.sqlite3.txt"`
- `".dayu/artifacts/tool-trace/tool-trace-cold.jsonl"`

全部返回 `PublicEvidencePathClassification.PUBLISHABLE`

**直接证据**: 测试 line 112-135

**影响**: 确保 regex 不会过度匹配导致普通路径被误判

**建议改法和验证点**: 已验证，无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

#### 4. scanner/snapshot 复用同一 owner 且 fail-closed 无漂移

**入口/函数**: `utils/cli_ci_run_observation.py:scan_public_evidence_files()` (line 785-788, 832-835)

**文件(行号)**: `utils/cli_ci_run_observation.py:785-788, 832-835`

**输入场景**: final scanner 扫描 public evidence 文件

**实际分支**: 文件路径和文件内容都通过 `classify_public_evidence_path()` 分类

**预期行为**: scanner 与 filesystem snapshot producer 复用同一 typed classifier，不得复制 regex 或 suffix

**实际行为**:
- 文件路径检查 (line 785-788): `classify_public_evidence_path(relative_text) is PublicEvidencePathClassification.RAW_DATABASE`
- 文件内容检查 (line 832-835): `classify_public_evidence_path(text) is PublicEvidencePathClassification.RAW_DATABASE`
- 两处都调用同一个 `classify_public_evidence_path()` 函数
- 旧的 `_RAW_DATABASE_SUFFIXES` frozenset 已被删除 (line 40-42)

**直接证据**:
- 删除了 `_RAW_DATABASE_SUFFIXES: Final[frozenset[str]] = frozenset((".sqlite", ".sqlite3", ".db"))`
- 文件路径检查从 `candidate.suffix.lower() in _RAW_DATABASE_SUFFIXES` 改为 `classify_public_evidence_path(relative_text) is PublicEvidencePathClassification.RAW_DATABASE`
- 文件内容检查从 `_RAW_DATABASE_PATH_PATTERN.search(text) is not None` 改为 `classify_public_evidence_path(text) is PublicEvidencePathClassification.RAW_DATABASE`

**影响**: 确保 semantic ownership 无漂移，单一真源分类

**建议改法和验证点**: 已验证，无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

### P3-01 Controller 拒绝理由复验

#### 5. P3-01 symlink chain 解析被拒绝

**入口/函数**: Controller 裁决

**文件(行号)**: `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md:101`

**输入场景**: DeepSeek P3-01 建议解析 symlink chain

**实际分支**: Controller 拒绝，理由是 "snapshot 解析 chain 会把已排除 target 的语义反向发布到 public evidence"

**预期行为**: final bundle 已对任意 symlink fail closed，本 finding 仅涉及审计表现，不成立为本 gate correctness 修复

**实际行为**: 既有 final-tree symlink owner tests 保持通过，未修改 ignored harness 控制流

**直接证据**: 文档 line 101

**影响**: 无 correctness 影响

**建议改法和验证点**: 按 Controller 边界不修

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

#### 6. SQLite `-journal` 扩展被拒绝

**入口/函数**: Controller 裁决

**文件(行号)**: `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md:102`

**输入场景**: 建议扩展 `-journal` 支持

**实际分支**: Controller 拒绝，理由是 "Host durable 强制 WAL，且本目标显式限定 main/WAL/SHM"

**预期行为**: 扩展会改变已确认 scope，不属于 P3-02 owner boundary 修复

**实际行为**: Host/F14 frontier、formal Oracle 与 scanner 其他分类均 zero semantic change

**直接证据**: 文档 line 102

**影响**: 无 correctness 影响

**建议改法和验证点**: 按 Controller 边界不扩

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

### Host WAL 范围复验

#### 7. Host durable 强制 WAL

**入口/函数**: Host durable store

**文件(行号)**: N/A

**输入场景**: Host SQLite 数据库

**实际分支**: Host durable 强制使用 WAL 模式

**预期行为**: 只需要覆盖 main/WAL/SHM，不需要覆盖 `-journal`

**实际行为**: 本次改动只覆盖 `.sqlite/.sqlite3/.db` 主库及 `-wal/-shm` sidecar，符合 Host WAL 范围

**直接证据**: regex `(?:-(?:wal|shm))?` 只匹配 WAL/SHM，不匹配 journal

**影响**: 无

**建议改法和验证点**: 无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

### Tests/Docs/Digests 复验

#### 8. 测试覆盖完整

**入口/函数**: `tests/cli/test_cli_ci_run_observation.py`

**文件(行号)**: `tests/cli/test_cli_ci_run_observation.py:53-135, 795-837, 960-1061`

**输入场景**: 各种 raw DB 路径、花括号包围路径、普通路径、sidecar 文件

**实际分支**: 24 个新增测试全部通过

**预期行为**: 覆盖三类主库、全部 WAL/SHM、花括号包围的非 JSON 嵌入文本、普通路径反例、sidecar 文件、完整 bundle

**实际行为**:
- `test_public_evidence_path_classifier_rejects_sqlite_main_and_sidecars`: 9 个参数化用例
- `test_public_evidence_path_classifier_rejects_brace_wrapped_database_paths`: 3 个参数化用例
- `test_public_evidence_path_classifier_keeps_ordinary_paths`: 5 个参数化用例
- `test_public_path_hygiene_detects_raw_database_sidecar_files`: 6 个参数化用例
- `test_final_publication_scan_completes_for_owner_sanitized_bundle`: 1 个完整 bundle 测试
- 总计 55 passed

**直接证据**: pytest 输出 `55 passed in 0.48s`

**影响**: 确保改动行为正确

**建议改法和验证点**: 无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

#### 9. 文档同步完整

**入口/函数**: 文档更新

**文件(行号)**: `docs/cli_ci.md:1399-1416`, `docs/gateflow/pr-190-f15-f16-implementation-20260807.md:100-128`, `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md:82-132`, `tests/README.md:407`

**输入场景**: 文档更新

**实际分支**: 文档正确描述了改动

**预期行为**: 同步 index 三态、safe-stop、session/shared projector、唯一 final-tree scan 时序、report containment、snapshot/cold Tool Trace owner 与 `unadjudicated`

**实际行为**: 文档已同步，包括：
- `docs/cli_ci.md`: 更新了 path hygiene 要求，添加了 WAL/SHM、snapshot producer、cold Tool Trace 说明
- `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`: 添加了 Fresh real-evidence producer correction 章节
- `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`: 添加了 Fresh real-evidence review-fix follow-up 和 Controller minimal P3 adjudication 章节
- `tests/README.md`: 更新了 CLI CI Run observation 测试描述

**直接证据**: 文档 diff

**影响**: 确保文档与代码一致

**建议改法和验证点**: 无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

#### 10. Digests 更新

**入口/函数**: `docs/gateflow/pr-190-f15-f16-implementation-20260807.md:126-130`

**文件(行号)**: `docs/gateflow/pr-190-f15-f16-implementation-20260807.md:126-130`

**输入场景**: SHA-256 digests

**实际分支**: digests 已更新

**预期行为**: 记录新的 SHA-256

**实际行为**:
- tracked helper: `92047be5098f312c962f76f339d41f45d685d7790556d326cdbba0c017176869`
- temporary prompt harness: `7e32637439c8625b6ee78ec65484f5b4e54e98cf199f65dd50d965a1739b1223`
- temporary F14 harness: `236251ca3a035c435080ccb9f91b3be21faaa2b24e31003b041d207327b4636d`

**直接证据**: 文档 diff

**影响**: 确保可追溯性

**建议改法和验证点**: 无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

### Ignored Harness 与 Formal Oracle 复验

#### 11. Ignored harness 零漂移

**入口/函数**: `workspace/tmp/prompt_observe_calibration.py`, `workspace/tmp/f14_real_cli_observation.py`

**文件(行号)**: N/A

**输入场景**: ignored harness 文件

**实际分支**: 未修改 ignored harness 控制流

**预期行为**: `py_compile` 通过、pyright 通过、Ruff 通过

**实际行为**:
- `python -m py_compile workspace/tmp/prompt_observe_calibration.py workspace/tmp/f14_real_cli_observation.py`: 通过
- `python -m pyright workspace/tmp/prompt_observe_calibration.py workspace/tmp/f14_real_cli_observation.py`: `0 errors, 0 warnings`
- `ruff check utils/cli_ci_run_observation.py tests/cli/test_cli_ci_run_observation.py`: All checks passed

**直接证据**: validation 章节

**影响**: 确保 ignored harness 无回归

**建议改法和验证点**: 无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

#### 12. Formal Oracle 零漂移

**入口/函数**: formal oracle

**文件(行号)**: N/A

**输入场景**: formal oracle

**实际分支**: formal oracle 保持 `unadjudicated`

**预期行为**: 不包含 `scenario_success`、综合 `success/passed` 或由 exit 0 推导的 scenario verdict

**实际行为**: 文档明确说明 "formal oracle 继续为 `unadjudicated`"

**直接证据**: `docs/cli_ci.md:1408`

**影响**: 确保 formal oracle 无漂移

**建议改法和验证点**: 无需改动

**修复风险（低/中/高）**: 低

**严重程度（低/中/高/严重）**: 低

---

## Open Questions

无

## Residual Risk

- `assigned to subsequent accepted clean-target validation gate / Controller`：本 gate 审计了 Controller 提供的 pre-fix fresh provider/AAPL 实例并以其 22 个 path violations 定位 owner；尚未对当前未提交修复执行新的 provider/AAPL rerun。accepted plan 仍要求正式复跑只针对 clean committed target，因此本 gate 只提供 deterministic final-bundle 与同一 cold JSONL production analyzer 闭环，不把它表述成 post-fix real-evidence completion。
- `assigned to independent final re-review gate / Controller`：本轮双路结果待Controller合并裁决。
- `covered by current deterministic suite`：F15 strict pair、accepted tool exact path、durable reopen、ordinary candidate freeze/dispatch、terminal producer reason、evidence 三态与 safe-stop pure control。
- `rejected-with-reason / no scope expansion`：P3-01 不解析 symlink chain；SQLite `-journal` 不进入显式 main/WAL/SHM 目标。两项均不作为本 gate residual correctness risk。
- 没有 unclassified residual risk；formal financial/business Oracle 保持 `unadjudicated`。

---

## Conclusion

**PASS**

本次改动是针对 DeepSeek P3-02 finding 的最小修复，改动范围精确、测试覆盖完整、semantic ownership 无漂移：

1. **Regex boundary fix**: 唯一 `_RAW_DATABASE_PATH_PATTERN` 的左右 boundary 补入 `{`/`}`，覆盖 final scanner 会读取的非 JSON stdout/stderr 文本
2. **Typed classifier**: 新增 `PublicEvidencePathClassification` StrEnum 和 `classify_public_evidence_path()` 函数作为唯一分类真源
3. **Scanner 复用**: 文件路径检查和文件内容检查都调用同一个 `classify_public_evidence_path()` 函数，删除了旧的 `_RAW_DATABASE_SUFFIXES`
4. **测试覆盖**: 55 passed，覆盖三类主库、全部 WAL/SHM、花括号包围的非 JSON 嵌入文本、普通路径反例、sidecar 文件、完整 bundle
5. **文档同步**: `docs/cli_ci.md`、`docs/gateflow/`、`tests/README.md` 均已同步
6. **Controller 拒绝理由**: P3-01 symlink chain 和 `-journal` 扩展均按 Controller 边界明确不修
7. **Host WAL 范围**: 只覆盖 main/WAL/SHM，符合 Host durable 强制 WAL 的范围
8. **Ignored harness**: `py_compile`、pyright、Ruff 均通过
9. **Formal Oracle**: 保持 `unadjudicated`，无漂移

**未发现阻断性问题，明确 PASS。**
