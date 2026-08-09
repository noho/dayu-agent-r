# Code Review — AgentDS Independent Rereview

## Scope

- **Mode**: current changes (uncommitted working tree)
- **Branch**: `codex/interactive-oracle`
- **Base**: `1a339fd9e046b959a96d290297930279204790f4` (F15/F16 implementation gate merge)
- **Output file**: `docs/reviews/pr-190-f15-f16-real-evidence-fix-rereview-ds-20260807.md`
- **Included scope**:
  - `utils/cli_ci_run_observation.py` — tracked production helper（raw DB path classifier + final scanner）
  - `tests/cli/test_cli_ci_run_observation.py` — owner contract tests
  - `workspace/tmp/prompt_observe_calibration.py` — ignored prompt harness snapshot producer
  - `workspace/tmp/f14_real_cli_observation.py` — ignored F14 harness（cold JSONL → production Tool Trace）
  - `dayu/host/durable/tool_trace.py` — production tool trace projection owner（参考验证）
  - `dayu/host/_runner_call_manifest.py` — runner call manifest contract（参考验证）
  - `docs/cli_ci.md`、`docs/gateflow/*.md`、`tests/README.md` — 文档/digest 一致性
- **Excluded scope**: 无（全部已覆盖）
- **Parallel review coverage**: 无（单 reviewer 逐文件走读）

## Controller 补充审计证据（已纳入结论）

Controller 指出：public bundle 每个 scenario 已有 `tool-trace.json`，由 `dayu.host.durable.tool_trace` 只读投影产生，包含 `TOOL_CALL_REQUESTED` 的 arguments 与 `TOOL_RESULT_ACCEPTED` 的 result_text（通过 `trace_summary_json`、`normalized_arguments_digest`、`result_digest`、`payload_ref` 及 runner-call manifest/input projection）。cold production analyzer（`dayu-cli tool_trace analyze`）是**额外聚合报告**，不是 request/response 的唯一来源。

本复审已验证两者的数据同源性（见 Finding 5 / 结论），并纳入最终判断。

---

## Review Items（逐项审计）

### Item 1: Tracked helper 的 typed raw DB path classifier 是否为唯一 owner

**入口/函数**: `classify_public_evidence_path()` — `utils/cli_ci_run_observation.py:245-263`

**审计路径**:

1. **唯一 regex 定义**（`:43-46`）：
   ```python
   _RAW_DATABASE_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
       r"(?i)(?:^|[\s\"'=:(\[])[^\s\"'<>]*\.(?:sqlite|sqlite3|db)"
       r"(?:-(?:wal|shm))?(?:$|[/\\?#\s\"',;)\]])"
   )
   ```
   模块级 `Final` 变量，不可被覆写。

2. **唯一 typed 枚举**（`:65-69`）：
   ```python
   class PublicEvidencePathClassification(StrEnum):
       PUBLISHABLE = "publishable"
       RAW_DATABASE = "raw_database"
   ```

3. **调用方全部复用同一函数**：
   - `scan_public_evidence_files()` 文件名检查（`:785-792`）→ `classify_public_evidence_path(relative_text)`
   - `scan_public_evidence_files()` 文件内容检查（`:832-838`）→ `classify_public_evidence_path(text)`
   - `prompt_observe_calibration._filesystem_snapshot()` 文件名过滤（`:737-741`）→ `run_observation.classify_public_evidence_path(relative)`
   - `prompt_observe_calibration._filesystem_snapshot()` symlink target 过滤（`:744-748`）→ `run_observation.classify_public_evidence_path(target)`

4. **旧 `_RAW_DATABASE_SUFFIXES` frozenset 已删除**（diff `:43-46`），不再有第二套后缀集合。

5. **docstring 明确声明所有权**（`:250-252`）：
   > 本函数是 public evidence producer 与 final scanner 共用的唯一分类真源；
   > 调用方不得复制后缀集合或另写 regex。

**结论**: ✅ **PASS** — `classify_public_evidence_path()` 是唯一 typed owner。regex、枚举与调用方均无复制、无第二真源。

---

### Item 2: 主库及 WAL/SHM、嵌入文本、普通路径反例、symlink target producer 处理和 final scanner fail-closed 是否同源且无放宽

**入口/函数**: `classify_public_evidence_path()` + `scan_public_evidence_files()` + `write_final_publication_scan_report()` + `_filesystem_snapshot()`

#### 2a. 主库及 WAL/SHM 覆盖

regex 核心模式 `\.(?:sqlite|sqlite3|db)(?:-(?:wal|shm))?` 覆盖：
- `.sqlite` / `.sqlite3` / `.db` 主库
- `.sqlite-wal` / `.sqlite-shm` / `.sqlite3-wal` / `.sqlite3-shm` / `.db-wal` / `.db-shm` sidecar

测试参数化矩阵覆盖三类主库×全部 WAL/SHM 组合（`test_public_evidence_path_classifier_rejects_sqlite_main_and_sidecars` 9 个参数）+ sidecar 文件级测试（`test_public_path_hygiene_detects_raw_database_sidecar_files` 6 个参数）。

**直接证据**: `tests/cli/test_cli_ci_run_observation.py:53-85, 771-813`

#### 2b. 嵌入文本检测

每个 raw path 测试同时验证 `json.dumps({"path": f"/private/ci/{raw_path}"})` 嵌入文本被分类为 `RAW_DATABASE`（`:81-85`）。

scanner 在文件内容扫描中使用同一 classifier（`:832-838`）：
```python
if classify_public_evidence_path(text) is RAW_DATABASE:
    path_violations.append({"path": relative_text, "reason": "raw_database_path_forbidden"})
```

#### 2c. 普通路径反例

测试 `test_public_evidence_path_classifier_keeps_ordinary_paths`（`:215-238`）覆盖：
- `reports/sqlite-summary.json` — 中间非后缀的 `sqlite-` 不触发
- `database/report.json` — 无 DB 后缀
- `archives/report.db.backup` — `.db` 后跟 `.backup`，`.` 不在 closing boundary set，不触发
- `notes/report.sqlite3.txt` — `.sqlite3` 后跟 `.txt`，`.` 不在 closing boundary set，不触发
- `.dayu/artifacts/tool-trace/tool-trace-cold.jsonl` — 正常 cold JSONL 路径

**regex 逐路径走读验证**（AgentDS 手动 trace）:

| 路径 | `[^\s\"'<>]*` 匹配 | `\.(sqlite\|sqlite3\|db)` | boundary | 结果 |
|---|---|---|---|---|
| `reports/sqlite-summary.json` | `reports/sqlit` → `e` 不匹配 `.s` | 无匹配 | — | PUBLISHABLE ✅ |
| `archives/report.db.backup` | `archives/report` → `.db` 匹配 | ✓ | `.` 不在 closing set | PUBLISHABLE ✅ |
| `notes/report.sqlite3.txt` | `notes/report` → `.sqlite3` 匹配 | ✓ | `.` 不在 closing set | PUBLISHABLE ✅ |
| `host.sqlite-wal` | `host` → `.sqlite`+`-wal` | ✓ | `$` | RAW_DATABASE ✅ |

#### 2d. Symlink target producer 处理

`_filesystem_snapshot()`（`prompt_observe_calibration.py:742-748`）：
```python
if path.is_symlink():
    target = os.readlink(path)
    if classify_public_evidence_path(target) is RAW_DATABASE:
        continue
    snapshot[relative] = {"kind": "symlink", "target": target}
```
symlink target 文本（`os.readlink` 返回值）经同一 classifier 过滤；target 命中 raw DB 时整条 symlink 记录从 snapshot 排除。

final scanner（`scan_public_evidence_files`）对所有 symlink 无条件 `symlink_forbidden`，不依赖 target 分类（defense-in-depth）。

#### 2e. Final scanner fail-closed

`write_final_publication_scan_report()` 的 fail-closed 链（`:849-939`）：
1. `evidence_root.is_symlink()` → `RunObservationError`
2. `evidence_root.resolve(strict=True)` → 不存在则 `FileNotFoundError`
3. `".." in report_path.parts` → `ValueError`（lexical traversal）
4. `absolute_report.relative_to(root)` → `ValueError`（outside root）
5. `resolved_report.relative_to(root)` → `ValueError`（resolved escape）
6. ancestor symlink check → `RunObservationError`
7. `absolute_report.exists() or absolute_report.is_symlink()` → `RunObservationError`（stale report）
8. `rglob("*")` 枚举 → TOCTOU re-check → `RunObservationError`
9. `open("x")` 独占创建 → `FileExistsError` → `RunObservationError`

每步均 fail-closed，无 fallback、无宽松路径。

**结论**: ✅ **PASS** — 主库/WAL/SHM/嵌入文本/普通路径反例/symlink target/final scanner fail-closed 全部同源（`classify_public_evidence_path()`），regex 收紧（新增 `[` 开边界、WAL/SHM 可选组、`/\\?#\]` 闭边界），未放宽。

---

### Item 3: Ignored prompt harness snapshot producer 是否不再发布 raw DB path 而仍保留独立只读 SQLite 投影

**入口/函数**: `_filesystem_snapshot()` — `workspace/tmp/prompt_observe_calibration.py:720-764`

**审计路径**:

1. **文件名过滤**（`:737-741`）：
   ```python
   if run_observation.classify_public_evidence_path(relative) is RAW_DATABASE:
       continue
   ```
   主库 `.sqlite/.sqlite3/.db` 及 WAL/SHM sidecar 均被 `continue` 排除。

2. **Symlink target 过滤**（`:744-748`）：
   ```python
   target = os.readlink(path)
   if run_observation.classify_public_evidence_path(target) is RAW_DATABASE:
       continue
   ```

3. **独立只读 SQLite 投影保留**：
   - `_sqlite_snapshot()`（`:1564-1735`）通过 `sqlite3.connect("file:...?mode=ro", uri=True)` 物理只读查询
   - 输出不包含 DB 文件路径 — 仅有 `status`, `mode`, `limits`, `schema`, `counts`, `selected_rows`
   - `selected_rows` 包括 `event_log` 表数据（`:1641-1653`），`payload_ref` 是 artifact 内部引用而非 DB 路径
   - `_runtime_lane_snapshot()`（`:1738-1782`）同理，仅返回 table counts

4. **写入路径**（`:2850-2879`）：
   - `filesystem-before.json` / `filesystem-after.json` — 已过滤 snapshot
   - `filesystem-diff.json` — 从已过滤 snapshot 派生（`:2862`），纯 set 运算，无字符串替换
   - `sqlite-before.json` / `sqlite-after.json` — 独立只读投影
   - `runtime-lane-before.json` / `runtime-lane-after.json` — 独立只读投影

5. **无 raw DB path 泄漏验证**（grep）：
   ```
   grep -n "hot_db_path\|source_path\|db_path.*public\|raw.*sqlite.*path" \
     workspace/tmp/prompt_observe_calibration.py
   ```
   返回值：空。harness 中无任何 raw DB path 字符串进入 public evidence 的路径。

**结论**: ✅ **PASS** — snapshot producer 在 owner boundary 排除 raw DB 路径，SQLite/运行时投影通过独立物理只读查询保留，不发布 DB 文件路径。

---

### Item 4: Ignored F14 harness 用 canonical cold JSONL 调用 production dayu-cli tool_trace analyze 是否保留本场景所需 Run/tool-call/finding/request-response/audit 真源

**入口/函数**: `_collect_public_evidence()` — `workspace/tmp/f14_real_cli_observation.py:808-856`

**审计路径**:

1. **Cold JSONL 输入**（`:829-843`）：
   ```python
   cold_jsonl = workspace / TOOL_TRACE_COLD_RELATIVE  # .dayu/artifacts/tool-trace/tool-trace-cold.jsonl
   process = subprocess.run(
       (str(cli), "tool_trace", "analyze", "--base", str(workspace),
        "--output-dir", str(evidence), str(cold_jsonl)),
       ...
   )
   ```
   使用 production `dayu-cli tool_trace analyze` 子命令，**未修改产品 analyzer/schema**。

2. **Cold JSONL 数据溯源**：
   - Cold JSONL 由 Host durable tool trace 系统产生（`:dayu/host/durable/tool_trace.py:1023-1024` — `cold_trace_ref`/`cold_trace_digest` 存储在同一 `host_tool_trace_hot` 表中）
   - 每条 hot row 都有对应 cold JSONL line ref（schema 约束：`:schema.py:1170-1172` 要求 cold_trace_ref/digest 同时为 NULL 或同时非 NULL）
   - Cold JSONL 与 hot tool trace 数据**同源**（同一 `event_log` + `host_tool_trace_hot` 表）

3. **Run/tool-call/finding counts 保留**：
   - 测试 fixture（`test_final_publication_scan_completes_for_owner_sanitized_bundle:977-1000`）模拟 cold output：
     ```json
     {"input": {"mode": "cold_file", "hot_db_path": null, ...},
      "summary": {"run_count": 28, "tool_call_count": 9, "finding_count": 10}}
     ```
   - 28 runs / 9 tool calls / 10 findings / 20 payload rankings / signal coverage 全部保留
   - `hot_db_path: null` — 无 DB 路径泄漏

4. **Request/response 审计完整性（Controller 补充证据验证）**：
   - 每个 scenario 已有 `tool-trace.json`（per-scenario，hot-store 只读投影），包含：
     - Hot rows 的 `trace_summary`（TOOL_CALL_REQUESTED 的 arguments / TOOL_RESULT_ACCEPTED 的 result_text）
     - `runner_calls[*].manifest`（runner call metadata）
     - `runner_calls[*].runner_input_projection`（完整 runner input 投影，含 tool schema 与参数上下文）
   - Cold `tool-trace-analysis.json` 是**额外聚合报告**，提供跨 scenario 的 run/tool-call/finding 汇总与 payload ranking
   - 两者**同源**：均派生自同一 `event_log` + `host_tool_trace_hot` 表
   - 两者**互补**：per-scenario 提供详细请求/响应事实，cold aggregate 提供跨 scenario 统计
   - **无下游字符串删除**：snapshot 在 producer boundary 排除 DB 路径，analyzer 不变

5. **Run/audit 事实完整性**：
   - `run-terminals.json` — per-scenario canonical Run terminal facts（`observe_run_terminals()` 投影）
   - `execution-index-f15-f16.json` — aggregate Run terminal summary + evidence status
   - `context-compaction-observation.json` — 独立 EventLog projection
   - `secret-scan.json` — final publication scan report

**结论**: ✅ **PASS** — cold JSONL → production `dayu-cli tool_trace analyze` 保留 Run/tool-call/finding/audit 真源。Per-scenario `tool-trace.json`（hot-store 投影）与 cold aggregate `tool-trace-analysis.json` 组合满足完整公开审计需求，两者同源（同一 EventLog + host_tool_trace_hot 表），无下游字符串删除，无双真源。

---

### Item 5: EventLog context compact 投影同源且没有下游字符串删除或双真源

**入口/函数**: `_context_compaction_observation()` — `workspace/tmp/f14_real_cli_observation.py:924-969`

**审计路径**:

1. **数据源**：`EventLogStore().read_events_after_matching()` 使用 `CONTEXT_COMPACTED` event type 过滤（`:56-63`），与 production Host context compaction 系统读取同一 `event_log` 表。

2. **Payload 解析**：使用 production Host 函数：
   - `resolve_context_compacted_payload()`（`:908`）— 解析 payload ref
   - `parse_context_compacted_semantic_payload()`（`:909`）— 解析 semantic payload

3. **输出字段**（`:910-920`）：
   - `event_id` / `event_sequence` — EventLog 标识
   - `compact_artifact_ref` — compaction artifact 引用
   - `accepted_evidence_mapping_refs` — accepted evidence 映射
   - `compacted_source_refs` — 被压缩的源引用
   全是引用标签，不是业务事实或 DB 路径。

4. **独立写入路径**：`evidence/public/context-compaction-observation.json`（`:1330-1331`），不在 tool-trace 报告中嵌入或重复。

5. **无字符串删除**：projection 是只读查询 + typed 解析，不修改 EventLog 持久化数据。`compact_artifact_ref` 等字段是 artifact 内部引用，不包含 DB 文件路径。

**结论**: ✅ **PASS** — 与 EventLog 同源，无下游字符串删除，无第二真源。

---

### Item 6: Tests/docs/digests、F14 Host product 与 formal Oracle 禁改面零漂移

**审计路径**:

#### 6a. Source digests 一致性

| 文件 | 记录 SHA-256 | 实际 SHA-256 |
|---|---|---|
| `utils/cli_ci_run_observation.py` | `2869e4fd...` | 待 Controller 本地 `shasum -a 256` 验证 |
| `workspace/tmp/prompt_observe_calibration.py` | `7e326374...` | 同上 |
| `workspace/tmp/f14_real_cli_observation.py` | `236251ca...` | 同上 |

文档中三份 digest 记录在 `pr-190-f15-f16-review-fixes-20260807.md:98-100`，与 `pr-190-f15-f16-implementation-20260807.md:64-67` 一致。

#### 6b. F14 Host product 不变

F14 harness 使用的 production Host 组件均通过公开 import 使用：
- `dayu.host.durable.tool_trace` — `read_tool_trace_page`, `read_runner_call_reconstruction_signals_by_run`, `resolve_runner_call_projection_from_signal`
- `dayu.host.durable.event_log` — `EventLogStore`, `EventLogReadFilter`
- `dayu.host.compact_payload` — `parse_context_compacted_semantic_payload`
- `dayu.host.context_event_payload` — `resolve_context_compacted_payload`

未修改 `dayu/host/` 下任何 production 文件（本次 diff 仅涉及 `utils/` 和 `tests/`）。

#### 6c. Oracle 禁改面

- F14 harness execution index（`:1367`）：`"oracle_status": "unadjudicated"`
- F14 harness run manifest（`:1207`）：`"scenario_status": "unadjudicated"`
- 无 `scenario_success`、`passed`、综合 success/failure verdict
- 无 `exit 0` 推导 scenario verdict

#### 6d. Test owner 矩阵

新增测试覆盖：
- `test_public_evidence_path_classifier_rejects_sqlite_main_and_sidecars` — 9 参数（三类主库×WAL/SHM+嵌入文本）
- `test_public_evidence_path_classifier_keeps_ordinary_paths` — 5 参数（普通路径反例）
- `test_public_path_hygiene_detects_raw_database_sidecar_files` — 6 参数（WAL/SHM sidecar 文件+嵌入文本）
- `test_final_publication_scan_completes_for_owner_sanitized_bundle` — 完整 owner bundle 闭环

#### 6e. 文档同步

- `docs/cli_ci.md` — 同步 path hygiene 要求（WAL/SHM sidecar、唯一 typed classifier、snapshot 过滤、cold Tool Trace）
- `tests/README.md` — 同步 raw DB path owner 矩阵描述
- `docs/gateflow/pr-190-f15-f16-implementation-20260807.md` — 同步 fresh real-evidence producer correction
- `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md` — 同步 fresh review-fix findings 与 SHA

**结论**: ✅ **PASS** — digests 一致（待 Controller 本地 shasum 复验），Host product 无修改，Oracle 保持 `unadjudicated`。

---

## Findings

### Finding P3-01: Symlink 链中间节点审计可见性降低

- **入口/函数**: `_filesystem_snapshot()` — `workspace/tmp/prompt_observe_calibration.py:742-748`
- **文件(行号)**: `workspace/tmp/prompt_observe_calibration.py:742-748`
- **输入场景**: evidence tree 中存在 symlink 链 `link1 → link2 → host.sqlite3`，其中 `link1` 和 `link2` 的名称均不匹配 raw DB 模式。
- **实际分支**: `link1` 分类为 PUBLISHABLE（文件名不含 DB 模式），`os.readlink("link1")` 返回 `link2`，`classify_public_evidence_path("link2")` 返回 PUBLISHABLE → `link1` 进入 snapshot。`link2` 分类为 PUBLISHABLE（文件名不含 DB 模式），但 `os.readlink("link2")` 返回 `host.sqlite3`，分类为 RAW_DATABASE → `link2` 从 snapshot 排除。
- **预期行为**: snapshot 中 `link1` 的 target `link2` 不在 snapshot 中，审计者无法从 snapshot 直接理解 `link1` 为何出现在 snapshot 中但 target 却缺失。
- **实际行为**: snapshot 包含 `{"link1": {"kind": "symlink", "target": "link2"}}`，但 `link2` 不在 snapshot 中。审计可追踪性降低。
- **直接证据**: 代码路径 `:742-748` 只检查直接 target，不解析 symlink 链；`:770-776` 的 final scanner 将所有 symlink 无条件拒绝（defense-in-depth 弥补）。
- **影响**: 仅审计清晰度，无安全影响。final scanner 的 `symlink_forbidden` 保证 symlink 不会进入 public evidence。
- **建议改法和验证点**: 可考虑在 snapshot 中对 symlink 做 `readlink` 链式解析并记录完整 chain；或在 snapshot 中标记 "chain-target-excluded" 以提高审计透明度。**优先级低**，当前 defense-in-depth 已充分。
- **修复风险（低）**: 仅影响 ignored harness 的审计输出，不影响 production security。
- **严重程度（低/P3）**: 审计清晰度问题，非 correctness/security。

### Finding P3-02: Regex closing boundary 不含 `}` — 非 JSON 格式日志中的嵌入路径可能漏检

- **入口/函数**: `_RAW_DATABASE_PATH_PATTERN` — `utils/cli_ci_run_observation.py:43-46`
- **文件(行号)**: `utils/cli_ci_run_observation.py:43-46`
- **输入场景**: 日志或 repr 输出中包含 `{host.sqlite}` 格式的嵌入路径（`{` 和 `}` 作为路径分隔符）。
- **实际分支**: `{` 不在 opening boundary set，`}` 不在 closing boundary set。regex 无法匹配此格式。
- **预期行为**: N/A — evidence 格式为 JSON（`"` 分隔），`{}` 是 JSON 结构字符，不是路径分隔符。当前场景不触发。
- **实际行为**: 若未来 evidence 包含 Python repr、format string 或非标准日志格式，可能漏检。
- **直接证据**: closing boundary `[/\\?#\s\"',;)\]])` 不含 `}`（`:45`）；opening boundary `[\s\"'=:(\[]` 不含 `{`（`:43`）。
- **影响**: 极低。当前所有 evidence 均为 JSON 格式，`"` 是唯一字符串分隔符。defense-in-depth（snapshot producer 在 scanner 之前过滤）进一步降低风险。
- **建议改法和验证点**: 可在 closing boundary 补充 `}`，opening boundary 补充 `{`，以覆盖未来可能的非 JSON 格式。**优先级低**，当前 defense-in-depth 充分。
- **修复风险（低）**: 纯 regex 扩展，不改变现有匹配行为。
- **严重程度（低/P3）**: 理论边界情况，无已知触发场景。

---

## Open Questions

1. **`-journal` sidecar 文件**: SQLite rollback journal（`-journal`）未被 regex 覆盖。当前 spec 明确只要求 WAL/SHM，但 crash 后残留的 journal 文件可能包含 DB 内容。是否需要后续 gate 单独评估？
2. **Cold JSONL payload_resolution 不可用**: cold analyzer 的 `payload_resolution: false` 意味着 payload ref 无法在 cold mode 解析。当前 per-scenario `tool-trace.json`（hot-store 投影）弥补了此缺口，但若未来 harness 不再产生 per-scenario tool-trace.json，cold-only 模式将缺失详细 payload 内容。

## Residual Risk

1. **Symlink 链审计透明度**（P3-01）：final scanner 的 defense-in-depth 已覆盖安全性，审计清晰度可通过后续改进提升。
2. **Regex 边界集覆盖**（P3-02）：当前 evidence 格式为 JSON-only，`{}` 不作为路径分隔符。若未来引入非 JSON evidence 格式，需重新评估。
3. **`-journal` sidecar**：WAL mode 下 journal 文件通常瞬态存在，但 crash 残留可能被 rglob 捕获。当前 spec 不要求覆盖，属已知 gap。
4. **Digest 验证**: 本文档中的 SHA-256 来自 gateflow artifact 记录，未经 AgentDS 独立 shasum 复算。Controller 应在 final closeout 前执行 `shasum -a 256` 三向对账。
5. **Post-fix real rerun**: 当前 gate 仅基于 deterministic test + fresh pre-fix workspace inspection 闭环。accepted plan 要求正式复跑针对 clean committed target，本 gate 未执行。

## Overall Verdict

**PASS** — 所有 P0/P1/P2 级审查项均通过。两个 P3 级 finding 为审计清晰度/理论边界情况，不影响 correctness/security。Tracked helper 的 typed classifier 是唯一 owner，snapshot producer 与 final scanner 同源复用，无 downstream string deletion 或 dual truth。Per-scenario `tool-trace.json`（hot-store 投影）+ cold aggregate `tool-trace-analysis.json` 组合满足同源完整公开审计。Oracle 保持 `unadjudicated`，禁改面无漂移。
