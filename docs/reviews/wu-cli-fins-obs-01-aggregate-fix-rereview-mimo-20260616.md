# WU-CLI-FINS-OBS-01 Aggregate Fix Re-Review (AgentMiMo)

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: aggregate fix re-review
- Reviewer: AgentMiMo
- Date: 2026-06-16
- Finding artifact: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260616.md`
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex-20260616.md`
- Scope: **仅 BF-1 修复**，不进入其它 gate。

## BF-1 回顾

| 字段 | 内容 |
|---|---|
| Finding ID | BF-1 |
| 文件 | `tests/service/test_import_boundary.py` |
| 问题 | `SERVICE_ALLOWED_IMPORTS` 缺少 `"dayu.fins.direct_events"`，导致 `dayu/service/fins_direct.py` 的 import 被误判为 violation |
| 根因 | Slice A/B 引入 `dayu.fins.direct_events` 作为 direct path typed public event contract，但 import boundary 白名单未同步更新 |

## 逐项核对

### 1. BF-1 是否真正关闭

**验证**：

```
pytest tests/service/test_import_boundary.py -q → 1 passed in 0.03s
```

**PASS**。`test_service_does_not_import_forbidden_layers` 通过，`dayu.fins.direct_events` 不再被误判为 forbidden import。

### 2. 是否只白名单了 `dayu.fins.direct_events`，没有放宽整个 `dayu.fins` 前缀

**Diff 证据**（`tests/service/test_import_boundary.py`）：

```diff
 SERVICE_ALLOWED_IMPORTS: tuple[str, ...] = (
+    "dayu.fins.direct_events",
     "dayu.fins.domain.enums",
     "dayu.fins.ingestion",
     "dayu.fins.ingestion_runtime",
     "dayu.fins.service_runtime",
 )
```

只添加了一个精确模块名 `"dayu.fins.direct_events"`。`SERVICE_FORBIDDEN_PREFIXES` 中的 `"dayu.fins"` 前缀未被移除或放宽。

**补充验证**：AST 扫描 `dayu/service/` 下所有 Python 文件，确认除白名单模块外无其它 `dayu.fins.*` import 违规。结果：0 violations。

**PASS**。

### 3. 白名单是否符合架构边界

**架构判断**：

`dayu.fins.direct_events` 定义 `FinsEvent`、`FinsEventType`、`FinsResultStatus`、`FinsOperationKind`、`FinsErrorKind`、`FinsProgress`、`FinsResultSummary`、`FinsEventDetail` 等类型。这些是 direct path 的 typed public event contract，模块 docstring 明确："本模块定义 CLI、Service 与 Fins runtime direct path 共享的业务事件形态"。

`dayu.service.fins_direct` 的 `FinsDirectIngestionRuntime` protocol 暴露 `download/preprocess/upload -> AsyncIterator[FinsEvent]`，Service 需要 `FinsEvent` 类型来表达该契约。这与已有白名单条目（`dayu.fins.ingestion_runtime`、`dayu.fins.service_runtime`、`dayu.fins.domain.enums`）同属 Service/Fins 显式 public boundary。

`direct_events` 不包含 job id、sidecar cursor、durable job record 或 storage path 语义；其 `_validate_safe_text` 主动禁止这些内容泄漏到事件中。

**PASS**。白名单符合架构边界：`direct_events` 是 direct path typed public event contract，不是 job/sidecar 回退。

### 4. `tests/README.md` 是否同步且没有引入错误说明

**Diff 证据**（`tests/README.md`）：

```diff
-- import boundary / weak typing guard：...以及 `dayu.service.fins_direct` 导入 Fins runtime / request / enum public boundary...
+- import boundary / weak typing guard：...以及 `dayu.service.fins_direct` 导入 Fins runtime / request / enum / direct event public boundary...
```

只在已有描述的枚举列表中追加了 "direct event"，未改变其它说明。

**PASS**。同步准确，无错误说明。

### 5. 是否有新 finding

**检查项**：

- Diff 只包含 `tests/service/test_import_boundary.py` 和 `tests/README.md`，无其它文件变更。✅
- `pyright tests/service/test_import_boundary.py`：0 errors。✅
- `git diff --check`：clean。✅
- 白名单条目按字母序排列（`direct_events` < `domain.enums` < `ingestion` < `ingestion_runtime` < `service_runtime`）。✅
- Fix artifact 的根因判断、修改范围和非目标均准确。✅

**无新 finding**。

## 验证命令

```
pytest tests/service/test_import_boundary.py -q → 1 passed in 0.03s
pyright tests/service/test_import_boundary.py → 0 errors
git diff --check → clean
AST scan dayu/service/ for non-whitelisted dayu.fins imports → 0 violations
```

## 结论

**PASS**。

BF-1 已正确关闭。`SERVICE_ALLOWED_IMPORTS` 精确添加 `"dayu.fins.direct_events"`，未放宽 `dayu.fins` 前缀。白名单符合架构边界：`direct_events` 是 direct path typed public event contract，Service direct 需要它表达 `AsyncIterator[FinsEvent]`。`tests/README.md` 同步准确。无新 finding。
