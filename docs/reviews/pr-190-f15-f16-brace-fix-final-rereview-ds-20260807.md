# F16 P3-02 Brace Fix — 最终独立 Rereview

## Scope

- **Mode**: current changes（未提交 working tree）
- **Branch**: `codex/interactive-oracle`
- **Base**: `1a339fd9e046b959a96d290297930279204790f4`（F15/F16 implementation gate merge）
- **Reviewer**: AgentDS（最终独立复验，只读）
- **Output file**: `docs/reviews/pr-190-f15-f16-brace-fix-final-rereview-ds-20260807.md`
- **Included scope**:
  - `utils/cli_ci_run_observation.py` — tracked production helper（唯一 typed raw DB path classifier + final scanner）
  - `tests/cli/test_cli_ci_run_observation.py` — owner contract tests（含 brace/WAL/SHM/sanitized bundle 新增矩阵）
  - `workspace/tmp/prompt_observe_calibration.py` — ignored prompt harness snapshot producer
  - `workspace/tmp/f14_real_cli_observation.py` — ignored F14 harness cold JSONL collector
  - `docs/cli_ci.md`、`docs/gateflow/*.md`、`tests/README.md` — 文档/digest 一致性
- **Excluded scope**: 无

---

## 复验背景

本 rereview 是 AgentDS 初次 rereview（P3-01/P3-02）→ AgentCodex 最小 P3-02 fix → AgentMiMo rereview（PASS）之后的**最终独立复验**。重点验证：

1. P3-02 最小 fix：唯一 regex boundary 新增 `{`/`}`，覆盖非 JSON stdout/stderr 文本中的花括号包围 raw DB 路径
2. main/WAL/SHM 非 JSON 文本命中，普通反例不误判
3. scanner/snapshot 仍复用同一 owner，fail-closed 无漂移
4. P3-01 Controller 拒绝理由、Host WAL 范围、tests/docs/digests、ignored harness 与 formal Oracle 零漂移

---

## 复验证据

### E1: SHA-256 三向对账

| 文件 | 记录 SHA-256（implementation artifact） | 实际 SHA-256（AgentDS 独立计算） | 对账 |
|---|---|---|---|
| `utils/cli_ci_run_observation.py` | `92047be5...` | `92047be5098f312c962f76f339d41f45d685d7790556d326cdbba0c017176869` | ✅ |
| `workspace/tmp/prompt_observe_calibration.py` | `7e326374...` | `7e32637439c8625b6ee78ec65484f5b4e54e98cf199f65dd50d965a1739b1223` | ✅ |
| `workspace/tmp/f14_real_cli_observation.py` | `236251ca...` | `236251ca3a035c435080ccb9f91b3be21faaa2b24e31003b041d207327b4636d` | ✅ |

### E2: 测试执行

- Owner suite：**55 passed**（`pytest tests/cli/test_cli_ci_run_observation.py -q`）
- Focused aggregate：**150 passed**（`pytest tests/cli/test_cli_ci_run_observation.py tests/host/test_event_log_store.py tests/host/test_run_attempt_transitions.py tests/host/test_wait_cancel_late_result.py -q`）
- pyright：**0 errors, 0 warnings**（`pyright utils/cli_ci_run_observation.py tests/cli/test_cli_ci_run_observation.py`）

---

## 逐项复验

### Item 1: P3-02 最小 fix — Regex boundary 新增花括号

**入口**: `_RAW_DATABASE_PATH_PATTERN` — `utils/cli_ci_run_observation.py:43-46`

**当前 regex**（P3-02 fix 后）:
```python
r"(?i)(?:^|[\s\"'=:(\[\{])[^\s\"'<>]*\.(?:sqlite|sqlite3|db)"
r"(?:-(?:wal|shm))?(?:$|[/\\?#\s\"',;)\]\}])"
```

**P3-02 fix 变更点**（相对 AgentDS 初次 rereview 时的版本）:
- Opening boundary：`[\s\"'=:(\[]` → `[\s\"'=:(\[\{]`（新增 `\{`）
- Closing boundary：`[/\\?#\s\"',;)\]]` → `[/\\?#\s\"',;)\]\}]`（新增 `\}`）

**Regex 逐字符结构验证**:

| 组件 | 模式 | 覆盖 |
|---|---|---|
| 大小写 | `(?i)` | 大小写不敏感 |
| 左边界 | `(?:^|[\s\"'=:(\[\{])` | 行首、空白、`"'=:([{` |
| 路径体 | `[^\s\"'<>]*` | 非空白/引号/尖括号的任意字符 |
| DB 后缀 | `\.(?:sqlite\|sqlite3\|db)` | 三类主库扩展名 |
| WAL/SHM | `(?:-(?:wal\|shm))?` | 可选 `-wal`/`-shm` sidecar |
| 右边界 | `(?:$\|[/\\?#\s\"',;)\]\}])` | 行尾、`/\?#`、空白、`"',;)]}` |

**花括号命中 trace**（AgentDS 手动 regex trace）:

| 输入 | `{` 命中左边界 | `[^\s\"'<>]*` | `.sqlite\|.sqlite3\|.db` | `-wal\|-shm` | `}` 命中右边界 | 分类 |
|---|---|---|---|---|---|---|
| `stdout: {/private/ci/.dayu/host/dayu_host.sqlite}` | ✅ | `/private/ci/.dayu/host/dayu_host` | `.sqlite` | — | ✅ | RAW_DATABASE |
| `stderr: {.dayu/host/dayu_host.sqlite3-wal}` | ✅ | `.dayu/host/dayu_host` | `.sqlite3` | `-wal` | ✅ | RAW_DATABASE |
| `trace: {C:\dayu\runtime\runtime_lanes.db-shm}` | ✅ | `C:\dayu\runtime\runtime_lanes` | `.db` | `-shm` | ✅ | RAW_DATABASE |

**普通路径反例 trace**（验证不误判）:

| 输入 | 匹配尝试 | 结果 |
|---|---|---|
| `reports/sqlite-summary.json` | `sqlite` 不是完整 `.sqlite` 后缀 | PUBLISHABLE |
| `database/report.json` | 无 DB 后缀 | PUBLISHABLE |
| `archives/report.db.backup` | `.db` 命中但 `.backup` 的 `.` 不在右边界集 | PUBLISHABLE |
| `notes/report.sqlite3.txt` | `.sqlite3` 命中但 `.txt` 的 `.` 不在右边界集 | PUBLISHABLE |
| `.dayu/artifacts/tool-trace/tool-trace-cold.jsonl` | 无 DB 后缀 | PUBLISHABLE |

**结论**: ✅ **PASS** — P3-02 最小 fix（仅 `{`/`}` 两字符）已正确应用。花括号包围的 main/WAL/SHM 路径全部命中，普通反例无一误判。

---

### Item 2: Scanner/snapshot 同源复用且 fail-closed 无漂移

**唯一 owner 验证**:

`classify_public_evidence_path()`（`:245-263`）是唯一 typed 分类入口。所有调用方均通过该函数：

| 调用方 | 位置 | 用途 |
|---|---|---|
| `scan_public_evidence_files()` 文件名 | `:785-792` | 文件路径分类 |
| `scan_public_evidence_files()` 文件内容 | `:832-838` | 文本内容扫描 |
| `prompt_observe_calibration._filesystem_snapshot()` | harness `:737-741` | snapshot 文件名过滤 |
| `prompt_observe_calibration._filesystem_snapshot()` | harness `:744-748` | symlink target 过滤 |

- 旧 `_RAW_DATABASE_SUFFIXES` frozenset 已删除，无第二套后缀集合 ✅
- `__all__` 导出 `PublicEvidencePathClassification` 和 `classify_public_evidence_path` ✅

**Fail-closed 链验证**:

`write_final_publication_scan_report()`（`:849-939`）的 fail-closed 链完整且未修改：
1. `evidence_root.is_symlink()` → `RunObservationError`
2. `".." in report_path.parts` → `ValueError`
3. `absolute_report.relative_to(root)` → `ValueError`
4. `resolved_report.relative_to(root)` → `ValueError`
5. ancestor symlink check → `RunObservationError`
6. stale report check → `RunObservationError`
7. TOCTOU re-check → `RunObservationError`
8. `open("x")` 独占创建 → `FileExistsError` → `RunObservationError`

**结论**: ✅ **PASS** — scanner/snapshot 均复用同一 `classify_public_evidence_path()` 真源，fail-closed 链无放宽无漂移。

---

### Item 3: P3-01 Controller 拒绝理由验证

**AgentDS 初次 rereview P3-01 finding**: symlink 链中间节点审计可见性降低（snapshot 中 `link1 → link2` 但 `link2` 因 target 命中 raw DB 被排除）。

**Controller 裁决**（`pr-190-f15-f16-review-fixes-20260807.md`）:
> `rejected-with-reason / 不修` — snapshot解析chain会把已排除target的语义反向发布到public evidence；final bundle已对任意symlink fail closed，本finding仅涉及审计表现，不成立为本gate correctness修复。

**AgentDS 独立验证**:
- Final scanner（`scan_public_evidence_files`）对所有 symlink 无条件 `symlink_forbidden`（`:773-777`），先于 raw DB 检查（`:785-792`）✅
- `write_final_publication_scan_report()` 的 ancestor symlink check 拒绝 symlink 祖先（`:900-904`）✅
- 即 snapshot 中即使出现 symlink 记录，final scanner 也会拒绝 symlink 本身进入 public evidence ✅
- defense-in-depth 两层：snapshot producer 过滤 target → final scanner 拒绝 symlink leaf ✅

**结论**: ✅ **PASS** — Controller P3-01 拒绝理由成立。defense-in-depth 已覆盖安全性，审计清晰度不属于本 gate correctness 阻塞项。

---

### Item 4: Host WAL 范围与 `-journal` 拒绝

**Controller 裁决**（`pr-190-f15-f16-review-fixes-20260807.md`）:
> `rejected-with-reason / 不扩` — Host durable强制WAL，且本目标显式限定main/WAL/SHM；扩展journal会改变已确认scope，不属于P3-02 owner boundary修复。

**AgentDS 独立验证**:
- Host durable 配置强制 WAL journal mode（`dayu/host/durable/connection.py` pragma）✅
- `-journal` 文件在 WAL mode 下瞬态存在，crash 后残留理论上可能被 `rglob` 捕获，但：
  - 当前 regex 覆盖 `-wal`/`-shm`，不覆盖 `-journal`，这是显式 scope 决策 ✅
  - Host durable 强制 WAL 路径，正常运行不产生 `-journal` sidecar；crash 残留属极端边缘场景，本 gate 显式未扩 scope ✅
- 扩展 scope 会导致新的测试/验证/边界分析，属于 scope creep 而非 correctness gap ✅

**结论**: ✅ **PASS** — WAL 范围显式限定 main/WAL/SHM，`-journal` 排除是审慎的 scope 决策，不构成 residual correctness risk。

---

### Item 5: Ignored harness 零漂移

**Prompt harness**（`workspace/tmp/prompt_observe_calibration.py`）:
- `_filesystem_snapshot()` 通过 `run_observation.classify_public_evidence_path()` 过滤 raw DB 路径 ✅
- Symlink target 过滤使用同一 classifier ✅
- 独立只读 SQLite 投影（`_sqlite_snapshot`、`_runtime_lane_snapshot`）不发布 DB 文件路径 ✅
- `filesystem-diff.json` 从已过滤 snapshot 派生（纯 set 运算），无字符串替换 ✅

**F14 harness**（`workspace/tmp/f14_real_cli_observation.py`）:
- Cold JSONL 输入（`.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`）驱动 production `dayu-cli tool_trace analyze` ✅
- 未修改产品 analyzer/schema ✅
- `hot_db_path=null`，`capabilities.hot=false` ✅
- Context compact 通过独立 EventLog projection（`_context_compaction_observation`），与 EventLog 同源 ✅
- Oracle `"unadjudicated"` 保持 ✅

**结论**: ✅ **PASS** — 两个 ignored harness 均通过 `classify_public_evidence_path()` 复用同一真源，无下游字符串删除、无第二真源、无 Oracle 漂移。

---

### Item 6: Tests/docs/digests 完整性

**新增测试矩阵**:

| 测试 | 覆盖 | 参数数 |
|---|---|---|
| `test_public_evidence_path_classifier_rejects_sqlite_main_and_sidecars` | 三类主库 + WAL/SHM + JSON 嵌入文本 | 9 |
| `test_public_evidence_path_classifier_rejects_brace_wrapped_database_paths` | 花括号包围的 main/WAL/SHM 非 JSON 嵌入文本 | 3 |
| `test_public_evidence_path_classifier_keeps_ordinary_paths` | 普通路径反例（中间非后缀、额外扩展名、cold JSONL） | 5 |
| `test_public_path_hygiene_detects_raw_database_sidecar_files` | final scanner 对 WAL/SHM sidecar 文件+嵌入文本的拒绝 | 6 |
| `test_final_publication_scan_completes_for_owner_sanitized_bundle` | owner 产出 sanitized bundle 后 final scan complete | 1 |

**文档同步**:
- `docs/cli_ci.md`：同步 snapshot/cold Tool Trace owner、WAL/SHM sidecar、唯一 typed classifier、formal `unadjudicated` ✅
- `tests/README.md`：同步 raw DB path owner 矩阵描述 ✅
- `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`：同步 fresh real-evidence correction、更新 SHA-256 ✅
- `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`：同步 fresh review-fix findings、Controller P3 adjudication、更新 SHA-256 ✅

**结论**: ✅ **PASS** — 新增测试矩阵 24 个参数化 case，覆盖 brace/WAL/SHM/main、普通反例与 complete bundle 闭环。文档同步一致，digest 三向对账一致。

---

## Findings

未发现实质性问题。

### 说明

本次复验对 P3-02 最小 fix（regex 左右 boundary 各增一字 `{` / `}`）做了完整的 regex trace、测试矩阵逐 case 验证、scanner/snapshot 同源复用确认、fail-closed 链审计、P3-01 Controller 拒绝理由独立验证、Host WAL scope 确认、ignored harness 零漂移审计与 formal Oracle 禁改面审计。

唯一值得注意的边界情况是 regex 右边界集中的 `\\` 可能在 Windows 路径中导致 `.db` 子目录名被误判为 raw database（如 `C:\dayu\data.db\report.json`），但：
- 运行环境为 macOS（darwin），public evidence 使用 POSIX 路径分隔符 ✅
- 即使误判也为 fail-safe（多拒绝而非少拒绝）✅
- 此行为在 P3-02 fix 前即存在，非本次 brace fix 引入 ✅

不构成 P3 级 finding。

---

## Open Questions

无。

---

## Residual Risk

1. **`assigned to subsequent accepted clean-target validation gate / Controller`**：本 gate 基于 deterministic 代码审查闭环；尚未对 post-fix 修复执行新的 provider/AAPL real rerun。accepted plan 要求 real rerun 只针对 clean committed target。
2. **`-journal` sidecar**（已由 Controller 明确拒绝扩展）：rollback journal 可含原始 DB 页，但当前 Host durable 强制 WAL 路径，正常运行不产生该 sidecar；本 gate 显式未扩 scope，不纳入 correctness 阻塞项。
3. **Post-fix real rerun 入口**：implementation artifact 已记录命令模板（`f15-f16-postfix-rerun-XXXXXXXX`），待 clean committed target 通过后执行。

---

## Overall Verdict

**PASS** — P3-02 最小 fix（regex 新增 `{`/`}` boundary）正确且最小，花括号包围的 main/WAL/SHM 路径全部命中，普通反例无一误判。`classify_public_evidence_path()` 保持唯一 typed owner，scanner 与 snapshot 同源复用，fail-closed 无漂移。P3-01 Controller 拒绝理由成立，Host WAL 范围显式限定，ignored harness 与 formal Oracle 零漂移。55 owner tests + 150 focused aggregate 全部通过，pyright 零错误。三向 SHA-256 对账一致。

无阻断项。可进入 commit。
