# Code Review — WU-TOOLS-01-F01 S1

## Scope

- Mode: current changes (unstaged + untracked vs committed HEAD)
- Branch: `host-wu-tools-01-f01`
- Base: N/A (reviewing uncommitted diff only; branch diverges from `main` at `8aac7881`)
- Output file: `docs/reviews/wu-tools-01-f01-s1-code-review-ds.md`
- Included scope:
  - `dayu/fins/ingestion_runtime.py` (new, untracked)
  - `dayu/fins/service_runtime.py` (modified, unstaged)
  - `tests/fins/test_fins_ingestion_runtime.py` (new, untracked)
  - `docs/reviews/wu-tools-01-f01-s1-implementation-codex.md` (implementation artifact, new)
  - `docs/host/issues-implementation-control.md` (gate bookkeeping only, unstaged)
- Excluded scope:
  - All other changed/untracked files outside S1 scope
  - Host/Engine/Service/config/provider/README — not in S1 scope
- Parallel review coverage: 无

## Findings

### 01-未修复-中-`_bounded_text` 拒绝路径分隔符会阻止合法 SEC 财报表单类型

- **入口/函数**: `_bounded_text` → 被 `_bounded_text_tuple` 调用 → 被 `FinsIngestionRuntime.start_download()` 的 `request_summary["form_types"]` 及 `FinsIngestionRuntime.start_preprocess()` 的 `request_summary["form_types"]` / `request_summary["document_ids"]` 消费
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:864-871`
- **输入场景**: 用户调用 `FinsDownloadRequest(ticker="AAPL", form_types=("10-K/A",))` 指定修正年报（amended 10-K）
- **实际分支**: `_bounded_text` 第 869 行检测到 `"10-K/A"` 包含 `/`，走 `raise ValueError(f"{field_name} 不得包含路径分隔符")` 分支
- **预期行为**: `"10-K/A"` 是 SEC 合法的财报表单类型（amended annual report），应在 form_type 过滤中合法使用；路径注入防御不应拒绝业务合法标识符
- **实际行为**: `ValueError` 被抛出，job 创建失败
- **直接证据**: 第 869 行 `if "/" in text or "\\" in text: raise ValueError(...)` 对 form_type 元素（第 599 行、第 633 行）和 document_ids 元素（第 632 行）无差别生效；而 `/` 在 SEC 表单修正标识中为合法字符
- **影响**: S3 实现真实下载 pipeline 时，修正年报/季报过滤将静默失败（`10-K/A`、`10-Q/A` 等）；当前 S1 不触发，但校验逻辑的语义边界已确定，S3 需要改此函数
- **建议改法和验证点**: 将路径分隔符检查从 `_bounded_text` 移出，或增加参数 `reject_path_separators: bool = True`，对 `source` 字段保持拒绝，对 `form_types` / `document_ids` 传 `False`；或新建 `_bounded_identifier` 不做分隔符检查，保留 `_bounded_text` 仅用于 `source`。验证点：`FinsDownloadRequest(ticker="AAPL", form_types=("10-K/A",))` 应成功创建 job
- **修复风险（低）**: 仅调整校验边界，不改变持久化或原子写入逻辑；需同步更新相关测试覆盖 form_type 含 `/` 场景
- **严重程度（中）**

### 02-未修复-中-`_market_from_text` 与 `_exchange_from_optional_text` 用硬编码字面量而非 `typing.get_args()` 做运行时校验

- **入口/函数**: `_record_from_json` → `_market_from_text` / `_exchange_from_optional_text`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1088-1131`
- **输入场景**: `ticker_normalization` 模块未来新增 market（如 `"JP"`）或 exchange（如 `"TSE"`），合法值范围扩展后，反序列化旧 job record 或新 market 的 job record
- **实际分支**: `_market_from_text` 中 `if value == "US": ... if value == "HK": ... if value == "CN": ... raise ValueError(...)`（第 1101-1107 行），新值走不到任何匹配分支，落入 `raise ValueError`
- **预期行为**: 反序列化应自动接受 `Market` Literal 类型定义的所有合法值；新增 market/exchange 时不需要同步修改此函数
- **实际行为**: 当 `Market` / `Exchange` Literal 类型新增合法值时，硬编码分支不会自动感知，`ValueError` 被静默抛出
- **直接证据**: `ticker_normalization.Market = Literal["US", "HK", "CN"]`（`ticker_normalization.py:25`），`typing.get_args(Market)` 在运行时返回 `('US', 'HK', 'CN')`（已通过命令行实测验证）——但 `_market_from_text` 并未调用 `get_args()`，而是逐字比较。同理 `Exchange = Literal["HKEX", "SSE", "SZSE"]`，`_exchange_from_optional_text` 亦然
- **影响**: 市场/交易所类型扩展时，job record 反序列化静默失败；历史 job record 在新版本代码中不可读；是维护性隐患而非当前功能缺陷
- **建议改法和验证点**: 用 `frozenset(typing.get_args(Market))` / `frozenset(typing.get_args(Exchange))` 替代硬编码字面量；或从 `ticker_normalization` 模块导出 `VALID_MARKETS` / `VALID_EXCHANGES` 常量作为唯一真源。验证点：新增市场字面量后，旧测试仍通过；非法 market 字符串仍正确拒绝
- **修复风险（低）**: 行为等价替换，不影响持久化格式；`get_args()` 在 Python 3.11 中为标准库函数，无需额外依赖
- **严重程度（中）**

### 03-未修复-低-`_write_record_locked` 写入失败后残留临时文件无清理

- **入口/函数**: `_write_record_locked` → 被 `create_job` / `save_job` / `request_cancel` 调用
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:513-539`
- **输入场景**: `os.fsync(stream.fileno())` 在第 537 行抛 `OSError`（磁盘满、权限变更），或 `os.replace(tmp_path, path)` 在第 538 行抛 `OSError`（跨文件系统 rename、目标目录权限变更）
- **实际分支**: 异常从 `with tmp_path.open(...)` 上下文或 `os.replace` 向上传播；临时文件 `.{job_id}.{uuid}.tmp` 已写入磁盘但未被 `os.replace` 消费，留在 job store 目录中
- **预期行为**: 原子写入失败后应清理临时文件，或至少确保临时文件不会无限制累积
- **实际行为**: 临时文件成为孤儿文件，占用磁盘空间且无自动回收机制；累积足够多后可能影响 job store 目录的 inode 使用和 `listdir` 性能
- **直接证据**: 第 532 行 `tmp_path = self.root_dir / f".{record.job_id}.{uuid.uuid4().hex}.tmp"` 创建临时文件，第 533-537 行写入+fsync，第 538 行 `os.replace(tmp_path, path)` —— 若 537 或 538 行异常，无 `finally` 或无 `except` 块清理 `tmp_path`
- **影响**: 写入失败场景下磁盘空间浪费；累积性风险，需大量连续写入失败才会成为实际运维问题
- **建议改法和验证点**: 在 `os.replace` 前后加 `try/finally` 或 `try/except`，失败时 `tmp_path.unlink(missing_ok=True)` 清理临时文件；或提供一个 store 级 `cleanup_orphan_tmp()` 方法供运维调用。验证点：mock `os.replace` 抛异常，断言临时文件已被删除
- **修复风险（低）**: 仅增加 cleanup 逻辑，不动写入核心路径
- **严重程度（低）**

### 04-未修复-低-`_StoreFileLock.__enter__` 加锁失败时文件句柄无显式关闭

- **入口/函数**: `_StoreFileLock.__enter__`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:753-769`
- **输入场景**: `fcntl.flock(stream.fileno(), fcntl.LOCK_EX)` 在第 768 行抛 `OSError`（例如竞争进程持有锁且内核锁超时或信号中断）
- **实际分支**: `__enter__` 方法异常退出，Python 的 context manager 协议不会调用 `__exit__`；局部变量 `stream` 持有的已打开文件句柄在当前帧销毁前仅依赖 CPython 引用计数回收
- **预期行为**: 加锁失败时应显式关闭已打开的文件句柄再传播异常，避免依赖 GC 行为
- **实际行为**: 依赖 CPython 引用计数立即关闭文件（行为正确但未显式保证）；在其他 Python 实现（PyPy、Jython）上可能延迟关闭
- **直接证据**: 第 767 行 `stream = self._path.open("a+", encoding="utf-8")` 创建句柄，第 768 行 `fcntl.flock(...)` 可能失败，此时 `self._stream` 仍为 `None`（第 751 行初始值），`__exit__` 不会被调用
- **影响**: 极低；CPython 引用计数保证文件立即关闭；仅在理论上的非 CPython 实现中可能出现文件描述符泄漏
- **建议改法和验证点**: 将 `stream = self._path.open(...)` 和 `fcntl.flock(...)` 包在 `try/except` 中，异常时显式 `stream.close()` 再 `raise`。或使用 `ExitStack` 管理资源
- **修复风险（低）**: 局部改动，不改变锁语义
- **严重程度（低）**

## Gate Bookkeeping 检查

`docs/host/issues-implementation-control.md` 中的 gate bookkeeping 更新（第 140-146 行、第 723-724 行）正确反映了当前 gate 从 `implementation` 推进到 `code-review`，状态更新为"Slice S1 implementation completed; focused tests and pyright passed; awaiting code review"。无越界：未声明 Slice S1 已通过 review、未标记后续 gate、未修改 WU-TOOLS-01-F01 的目标/非目标/验收信号。

## `service_runtime.py` Lazy Import 审查

`dayu/fins/service_runtime.py:133-135` 的 `FinsToolService` 懒导入已有充分理由且经实体验证：

- 实体验证的循环链：`service_runtime.py` → `dayu.fins.tools.service` → `dayu.fins.tools.__init__`（package）→ `dayu.fins.tools.provider` → `service_runtime.py`
- `dayu/fins/tools/__init__.py:6` 直接导入 `from .provider import discover_tools`
- `dayu/fins/tools/provider.py:25` 直接导入 `from dayu.fins.service_runtime import DefaultFinsRuntime`
- 若 `service_runtime.py` 在模块级导入 `from dayu.fins.tools.service import FinsToolService`，将在 `DefaultFinsRuntime` 定义前触发循环导入
- `from __future__ import annotations` 使 `_tool_service: FinsToolService | None` 注解惰性求值，避免运行时类型求值
- 懒导入采用与现有 `get_tool_service()` 一致的双重检查加锁模式，未引入新并发语义

结论：懒导入充分合理，不构成 finding。

## Open Questions

- 无。

## Residual Risk

| Risk | Classification |
|---|---|
| `_bounded_text` 对 `/` 的过严校验阻止修正表单类型（如 "10-K/A"）| 需在当前 slice 修复（S3 前），或明确记录为 S3 范围 |
| `_market_from_text` / `_exchange_from_optional_text` 硬编码字面量 | 需在当前 slice 修复（低风险，维护性改进） |
| `_write_record_locked` 失败后残留临时文件 | 建议在当前 slice 修复（极低影响） |
| `_StoreFileLock.__enter__` 异常时句柄无显式关闭 | 可在后续 slice 修复（影响极低，CPython 行为正确） |
| 真实下载/预处理 pipeline 未实现 | covered by later approved slice: S2, S3 |
| Tool provider 不存在 | covered by later approved slice: S4 |
| Host wait adapter 不存在 | covered by later approved slice: S5 |
| 真实 SEC/CN/HK 网络下载适配器不存在 | assigned to later work unit |
| Upload、CLI 不存在 | assigned to later work unit (WU-TOOLS-01-F09, future CLI owner) |
| `ingestion_job_store` 字段类型为具体类 `FsFinsIngestionJobStore` 而非协议 `FinsIngestionJobStore` | 有意为之：`DefaultFinsRuntime` 是具体装配根，应知悉具体实现；`FinsIngestionRuntime` 已使用协议类型。不构成风险 |
| `NormalizedTickerMarket` / `NormalizedTickerExchange` 是 `ticker_normalization.Market` / `Exchange` 的类型别名 | 正确；原始名 `Market` / `Exchange` 在 fins 上下文语义不足，别名增强可读性 |

## Validation Run

```text
$ pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -v
17 passed, 3 warnings in 1.02s

$ pyright
0 errors, 0 warnings, 0 informations
```

所有测试通过，pyright 零错误。额外验证：

- `Market` / `Exchange` 的 `Literal` 类型值已通过运行时 `get_args()` 确认
- `FinsIngestionJobRecord` 中 `source_kind=None` 的 JSON round-trip 已验证通过
- 循环导入依赖链已通过源码搜索确认

## Overall Verdict

S1 实现在 scope 内正确、严格、类型安全。核心机制（原子写入+文件锁+双重检查惰性初始化）设计正确，测试覆盖了 S1 声明的主成功路径和关键边界（无 singleton、ticker 归一化、job record 无载荷泄漏、取消状态转换、终态不退化）。发现 4 个 findings：2 个中（`_bounded_text` 路径分隔符过严、market/exchange 硬编码字面量）、2 个低（临时文件清理、文件句柄异常路径）。其中 `_bounded_text` 的 `/` 拒绝会在 S3 下载 pipeline 中阻止合法 SEC 修正表单类型（"10-K/A" 等），建议当前 slice 修复。无阻塞性 correctness 缺陷。
