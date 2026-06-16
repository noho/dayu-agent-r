# WU-CLI-FINS-OBS-01 Aggregate Fix Re-Review (AgentDS)

## 范围

- **Gate**：aggregate fix re-review
- **Review 目标**：仅审 BF-1 修复，不进入其它 gate
- **Finding artifact**：`docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260616.md`（BF-1）
- **Fix artifact**：`docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex-20260616.md`

## BF-1 修复验证

### Finding 回顾

MiMo aggregate deepreview BF-1：`dayu.fins.direct_events` 未在 `tests/service/test_import_boundary.py` 的 `SERVICE_ALLOWED_IMPORTS` 白名单中，导致 `test_service_does_not_import_forbidden_layers` 误判 `dayu/service/fins_direct.py` 的 `import dayu.fins.direct_events` 为 import boundary violation。

### 修复内容

| 文件 | 修改 |
|---|---|
| `tests/service/test_import_boundary.py` line 16 | `SERVICE_ALLOWED_IMPORTS` 新增 `"dayu.fins.direct_events"` |
| `tests/README.md` line 142 | Service import boundary 说明追加 "direct event" |

### 审查要点

#### 1. BF-1 是否真正关闭

```
$ pytest tests/service/test_import_boundary.py -q
1 passed in 0.03s
```

**通过**。import boundary 测试不再误判 `dayu.fins.direct_events` 为 violation。

WU targeted 全量：
```
$ pytest tests/service/test_import_boundary.py tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py \
  tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py \
  tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
  tests/cli/test_arg_parsing.py -q
282 passed, 3 warnings in 6.72s
```

#### 2. 是否只白名单了 `dayu.fins.direct_events`，没有放宽整个 `dayu.fins` 前缀

**证据**（`tests/service/test_import_boundary.py`）：

```python
SERVICE_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "dayu.config",
    "dayu.ui",
    "dayu.fins",          # ← 仍然禁止整个 dayu.fins 前缀
)
SERVICE_ALLOWED_IMPORTS: tuple[str, ...] = (
    "dayu.fins.direct_events",    # ← 仅新增这一条
    "dayu.fins.domain.enums",
    "dayu.fins.ingestion",
    "dayu.fins.ingestion_runtime",
    "dayu.fins.service_runtime",
)
```

白名单是 `SERVICE_ALLOWED_IMPORTS` tuple 中的显式精确条目，不是前缀放宽。`SERVICE_FORBIDDEN_PREFIXES` 仍包含 `"dayu.fins"`，阻止其它 `dayu.fins.*` 子模块被 Service 导入。`_matches_prefix` 逻辑先检查 allowlist 再检查 forbidden list。

**通过**。

#### 3. 白名单是否符合架构边界

**证据**：

`dayu.fins.direct_events` 的模块 docstring（`dayu/fins/direct_events.py` line 1-6）：

> 本模块定义 CLI、Service 与 Fins runtime direct path 共享的业务事件形态。事件只表达当前财报 direct 操作的进度与终态结果，不表达后台 job、sidecar、游标、仓储路径或 Host / Engine 治理状态。

该模块承载：
- `FinsEvent`、`FinsEventType`（`PROGRESS`/`RESULT`）
- `FinsResultSummary`、`FinsResultStatus`、`FinsOperationKind`、`FinsErrorKind`
- `FinsProgress`、`FinsEventDetail`
- Exit code 常量

这些是 CLI/Service/Fins runtime direct path 的共享 typed public event contract。

`dayu/service/fins_direct.py` 的导入（lines 21-31）：

```python
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_CANCELLED,
    FINS_RESULT_EXIT_FAILURE,
    FINS_RESULT_EXIT_SUCCESS,
    FinsErrorKind,
    FinsEvent,
    FinsEventType,
    FinsOperationKind,
    FinsResultStatus,
    FinsResultSummary,
)
```

Service 需要这些类型来表达 `FinsDirectIngestionRuntime` protocol 返回的 `AsyncIterator[FinsEvent]`，以及构造 direct command 的 exit code 映射。这是正确的依赖方向——Service 消费 Fins public contract，不绕过 architecture boundary。

该白名单与同文件中已有的 `dayu.fins.domain.enums`、`dayu.fins.ingestion_runtime`、`dayu.fins.service_runtime` 属于同一类显式 public boundary：都是 Service/Fins assembly 与 typed request/event contract 边界。

**通过**。

#### 4. tests/README 是否同步

**证据**（`tests/README.md` line 142 diff）：

```diff
-- import boundary / weak typing guard：...dayu.service.fins_direct 导入 Fins runtime / request / enum public boundary...
+- import boundary / weak typing guard：...dayu.service.fins_direct 导入 Fins runtime / request / enum / direct event public boundary...
```

修改精准：在已有 "runtime / request / enum" 后追加 "direct event"，与白名单新增的 `dayu.fins.direct_events` 一致。未引入额外描述、错误说明或无关模块名。

**通过**。

#### 5. 新 finding 检查

Diff 仅包含：

```
tests/README.md                       | 2 +-
tests/service/test_import_boundary.py | 1 +
2 files changed, 2 insertions(+), 1 deletion(-)
```

修改范围与 fix artifact 描述完全一致。无额外文件、无无关修改、无重构成分。

全量 pyright：

```
0 errors, 0 warnings, 0 informations
```

全量 git diff --check：clean。

**无新 finding**。

## 裁决

**PASS**。BF-1 修复完全关闭，无新 finding。

| 审查要点 | 结果 |
|---|---|
| BF-1 import boundary 测试通过 | ✅ `1 passed` |
| 仅白名单 `dayu.fins.direct_events`，未放宽 `dayu.fins` 前缀 | ✅ |
| 白名单符合架构边界（direct typed public event contract） | ✅ |
| tests/README 同步说明 | ✅ |
| 无新 finding | ✅ |

## 验证命令

```bash
pytest tests/service/test_import_boundary.py -q          # 1 passed
pytest <WU targeted matrix> -q                            # 282 passed
pyright dayu/ tests/ utils/                               # 0 errors
git diff --check                                           # clean
```
