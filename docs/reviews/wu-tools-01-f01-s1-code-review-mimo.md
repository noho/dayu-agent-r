# Code Review

## Scope

- Mode: current changes
- Branch: `host-wu-tools-01-f01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f01-s1-code-review-mimo.md`
- Included scope:
  - `dayu/fins/ingestion_runtime.py` (new, 1167 lines)
  - `dayu/fins/service_runtime.py` (modified diff, 58 lines changed)
  - `tests/fins/test_fins_ingestion_runtime.py` (new, 240 lines)
  - `docs/reviews/wu-tools-01-f01-s1-implementation-codex.md` (new, implementation artifact)
  - `docs/host/issues-implementation-control.md` (modified diff, gate bookkeeping only)
- Excluded scope: Host/Engine/Service/config/provider/README changes, real download/preprocess pipelines, tool providers, wait adapter, CLI, upload
- Parallel review coverage: subagent 验证了 `FinsToolService` lazy import 的循环依赖链；subagent 验证了 `_write_record_locked` 的 temp file cleanup 行为

## Findings

### 001-未修复-中-atomic write 失败时 temp file 泄漏

- **入口/函数**: `FsFinsIngestionJobStore._write_record_locked`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:532-539`
- **输入场景**: 任何触发 `_write_record_locked` 的写操作（`create_job`、`save_job`、`request_cancel`），当 `stream.write` / `stream.flush` / `os.fsync` / `os.replace` 抛出异常时
- **实际分支**: `with tmp_path.open("w") as stream:` 的 context manager 只关闭 file handle，不删除文件；异常向上传播，`tmp_path` 永远不会被清理
- **预期行为**: atomic write 模式在任何失败路径都应清理 temp file，不留孤儿文件
- **实际行为**: 每次写入失败都会在 `self.root_dir` 下留下一个 `.finsjob_xxx.{uuid}.tmp` 文件。磁盘满、I/O 错误、权限错误等场景下会持续累积孤儿 temp 文件
- **直接证据**:
  - 第 532-538 行：`tmp_path = self.root_dir / f".{record.job_id}.{uuid.uuid4().hex}.tmp"` 后直接 `with tmp_path.open(...)` 写入，无 `try/finally` 包裹
  - UUID hex 保证每次生成唯一文件名，失败后不会被后续操作覆盖
- **影响**: 磁盘空间泄漏；极端情况下（反复 I/O 失败）可能积累大量孤儿文件
- **建议改法和验证点**: 在 `with tmp_path.open(...)` 和 `os.replace` 外层加 `try/except BaseException` 并在 except 中执行 `tmp_path.unlink(missing_ok=True)` 后 re-raise。验证点：模拟 `os.fsync` 抛 `OSError` 后确认 temp file 已被清理
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-低-market/exchange 反序列化硬编码重复 ticker_normalization 的合法值集合

- **入口/函数**: `_market_from_text` / `_exchange_from_optional_text`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1088-1131`
- **输入场景**: 从 JSON 文件反序列化 `FinsIngestionJobRecord` 时
- **实际分支**: `_market_from_text` 逐个 if 比较 `"US"` / `"HK"` / `"CN"`；`_exchange_from_optional_text` 逐个 if 比较 `"HKEX"` / `"SSE"` / `"SZSE"`
- **预期行为**: 反序列化边界应有明确的合法值白名单；但这些值与 `ticker_normalization.Market` / `ticker_normalization.Exchange` Literal 类型的定义是同一份知识
- **实际行为**: 如果 `ticker_normalization` 新增 market 或 exchange（例如 `"SG"` / `"JPSE"`），这两个函数需要同步更新，否则合法的 job record 无法反序列化。两处维护同一份知识
- **直接证据**:
  - `ticker_normalization.py:25-26`: `Market = Literal["US", "HK", "CN"]` / `Exchange = Literal["HKEX", "SSE", "SZSE"]`
  - `ingestion_runtime.py:1088-1131`: 硬编码相同的字符串集合
- **影响**: 新增市场/交易所时需要两处同步修改，否则 job record 反序列化失败。当前 S1 scope 下影响有限（只有三个市场）
- **建议改法和验证点**: 可保持当前实现（反序列化边界做白名单是合理防御），但应在 `_market_from_text` / `_exchange_from_optional_text` 的 docstring 中注明它们与 `ticker_normalization.Market` / `Exchange` 的对应关系，方便后续维护者同步。或者改为从 Literal 类型提取合法值。验证点：如果 ticker_normalization 新增 market，确认反序列化不会静默丢失
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-read_job 获取文件锁导致并发读序列化

- **入口/函数**: `FsFinsIngestionJobStore.read_job`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:443`
- **输入场景**: 多个线程/进程同时读取不同 job record
- **实际分支**: `with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):` 对所有读操作加独占锁
- **预期行为**: 读不同 job record 之间不应互相阻塞
- **实际行为**: 所有 `read_job` 调用都竞争同一把全局文件锁，不同 job 的读操作被序列化
- **直接证据**:
  - 第 443 行：`with _StoreFileLock(self.root_dir / _LOCK_FILE_NAME):`
  - `_StoreFileLock` 使用 `fcntl.LOCK_EX`（独占锁）
- **影响**: S1 scope 下无真实并发，影响可忽略。但如果后续 S2/S3 引入并发 pipeline，读吞吐会成为瓶颈
- **建议改法和验证点**: 当前可接受。后续如需并发读，可改为 per-file `fcntl.LOCK_SH` 共享读锁，或对 read 操作完全不加锁（依赖 `os.replace` 的原子性保证读到完整文件）。验证点：确认 `os.replace` 在当前平台是原子的
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。所有 finding 均有直接代码证据支撑，不影响 S1 整体 ship 决策。

## Residual Risk

- **Fixed in current slice**:
  - Fins-owned typed request/result/job shapes ✓
  - FinsIngestionJobStatus / operation kind / durable job record / job start ✓
  - Fins job store protocol + filesystem implementation ✓
  - workspace_root/.dayu/fins_ingestion/jobs path ✓
  - atomic/locked writes, no module singleton ✓
  - DefaultFinsRuntime assembly root with get_ingestion_runtime() ✓
  - Ticker normalization through dayu.fins.ticker_normalization only ✓
  - No financial document payload/raw provider payload/raw filesystem path leakage ✓
  - Focused tests covering S1 success signals ✓

- **Covered by later approved slice**:
  - `start_download` / `start_preprocess` 只创建 queued record，不启动真实 pipeline → F01 S2/S3
  - 无 tool provider 或 Host waiting adapter → F01 S4/S5

- **Assigned to later work unit**:
  - 真实 SEC/CN/HK 网络下载 adapter → 不在 F01 scope 内

- **Tracked by existing issue**:
  - `WU-TOOLS-01-S4-R1` residual owner: F01

- **Requiring user decision**:
  - 无

## Gate Bookkeeping Check

`docs/host/issues-implementation-control.md` 的 diff 只更新了：
- status table 中 `WU-TOOLS-01-F01` 的 gate 从 `pending` 改为 `implementation`
- `WU-TOOLS-01-F01` section 从 `Pending` 改为 `Implementation` 并记录 accepted plan commit

未涉及实现 finding。gate bookkeeping 更新合理，未越界。
