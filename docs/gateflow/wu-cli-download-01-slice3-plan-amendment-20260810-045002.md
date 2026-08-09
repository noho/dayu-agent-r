# `WU-CLI-DOWNLOAD-01` Slice 3 Plan Amendment

## 1. Gate 状态

- Work unit：`WU-CLI-DOWNLOAD-01`。
- Gate：Slice 3 plan-amendment，仅修订测试 allowlist；尚未进入 implementation。
- 对应目标：DL-F09 canonical cancellation 与 DL-F11 conversion completion。
- 基础计划：`docs/gateflow/wu-cli-download-01-plan-20260809.md`，保持不修改。
- 基线 HEAD：`5c09609946d7e5628ce8dbc1ea856439668a82a9`。
- 分支：`codex/download-oracle`。
- Preflight：`git status --short` 无输出，worktree 在本 artifact 创建前干净。
- 本 gate 唯一允许写入：当前 standalone amendment artifact。
- 独立 review：AgentMiMo `docs/reviews/plan-review-20260810-045643.md`（PASS，3 low）；
  AgentDS `docs/reviews/plan-review-20260810-slice3-amendment-ds.md`（PASS，2 low）。
- 完成状态：`plan-amendment fix ready for two independent re-review`；两路 finding re-review
  均确认已修复前不得恢复 Slice 3 implementation。

## 2. 第一性原理判断

本 amendment 动机成立，且只需扩大一个测试文件的 allowlist，不需要扩大 production scope。

基础计划 §5.5 已把 conversion dependency 的语义 owner 从裸 callable 收敛为
`CnDoclingConversionRunner` Protocol，并要求 `CnPipeline` 构造函数注入 typed runner；
Slice 3 同时要求新增 `CONVERSION_COMPLETED`，形成
`PDF_READY -> CONVERSION_STARTED -> CONVERSION_COMPLETED -> PUBLICATION_ELIGIBLE`
状态顺序。任何直接断言 `CnPipeline` 构造依赖或 `download_stream` 完整事件序列的测试，
都必须随 owner contract 迁移。否则完整 pyright 或 affected union 必然失败。

原 Slice 3 测试 allowlist 已覆盖 workflow/runtime owner tests，但遗漏了
`tests/fins/test_cn_pipeline.py`。该遗漏不能通过 production callable compatibility shim、
wrapper、双参数或隐藏 `CONVERSION_COMPLETED` 修补，因为这些做法会恢复第二套语义真源，
违反基础计划和项目的 semantic ownership / no-compat 约束。

## 3. 穷举方法与直接代码证据

### 3.1 执行的穷举

使用仓库级 `rg` 与 Python AST 只读扫描交叉核验以下集合：

1. `dayu/`、`tests/`、`utils/` 下所有 `CnPipeline(...)` 直接构造；
2. 所有 `CnPipeline` 子类及 `super().__init__(...)`；
3. 所有 `convert_pdf_to_docling_json`、`PdfToDoclingJsonBytes` 与
   `CnDoclingConversionRunner` 文本和注入点；
4. tests 下所有 `DownloadEventType` 断言、完整事件序列断言；
5. 所有 `CONVERSION_STARTED`、`conversion_started`、
   `docling_conversion_started` production/test call sites；
6. 所有 `CnPipeline` import，排除别名构造或间接 import 漏检。

关键只读命令：

```bash
rg -n --glob '*.py' '\bCnPipeline\s*\(' dayu tests utils
rg -n --glob '*.py' '\bclass\s+\w+\s*\([^)]*CnPipeline[^)]*\)' dayu tests utils
rg -n --glob '*.py' 'convert_pdf_to_docling_json|PdfToDoclingJsonBytes|CnDoclingConversionRunner' dayu tests utils
rg -n --glob '*.py' 'DownloadEventType\.' tests
rg -n --glob '*.py' 'CONVERSION_STARTED|conversion_started|docling_conversion_started' dayu tests utils
rg -n --glob '*.py' 'import .*CnPipeline|from .*cn_pipeline import' dayu tests utils
```

已执行的 AST 扫描按文件、行号、所属测试函数列出 constructor keyword、旧 conversion
injection 和包含 `DownloadEventType` / `CONVERSION_STARTED` 的 assert；以下命令可直接复现，
只读源码、不写文件：

```bash
python - <<'PY'
import ast
from pathlib import Path

roots = (Path("dayu"), Path("tests"), Path("utils"))
for root in roots:
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }

        def owner_name(node: ast.AST) -> str:
            while node in parents:
                node = parents[node]
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return node.name
            return "<module>"

        def belongs_to_cn_pipeline_subclass(node: ast.AST) -> bool:
            while node in parents:
                node = parents[node]
                if isinstance(node, ast.ClassDef):
                    return any(
                        isinstance(base, ast.Name) and base.id == "CnPipeline"
                        for base in node.bases
                    )
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                is_cn_pipeline = isinstance(node.func, ast.Name) and node.func.id == "CnPipeline"
                is_super_init = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "__init__"
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Name)
                    and node.func.value.func.id == "super"
                    and belongs_to_cn_pipeline_subclass(node)
                )
                if is_cn_pipeline or is_super_init:
                    keywords = [keyword.arg for keyword in node.keywords]
                    print(f"CONSTRUCTOR {path}:{node.lineno} {owner_name(node)} {keywords}")
                if any(
                    keyword.arg == "convert_pdf_to_docling_json"
                    for keyword in node.keywords
                ):
                    print(f"OLD_INJECTION {path}:{node.lineno} {owner_name(node)}")
            if isinstance(node, ast.Assert):
                expression = ast.unparse(node.test)
                if "DownloadEventType" in expression or "CONVERSION_STARTED" in expression:
                    print(f"EVENT_ASSERT {path}:{node.lineno} {owner_name(node)} {expression}")
PY
```

该输出与前述 `rg` 集合一致。

### 3.2 `CnPipeline` 构造穷举

共发现 15 个直接 `CnPipeline(...)` 构造和 1 个子类 `super().__init__(...)`：

| 文件与位置 | 数量 | conversion 注入 | 结论 |
| --- | ---: | --- | --- |
| `dayu/fins/service_runtime.py:519` | 1 | 无 | production 默认 runner 构造；调用点无需修改 |
| `dayu/fins/pipelines/cn_pipeline.py:1868,1917` | 2 | 无 | Slice 3 production allowlist 内的 adapter factory；无需额外文件 |
| `tests/fins/test_cn_download_runtime.py` 的 `_RecordingPipeline.__init__` 与 `_build_runtime_with_cn_hk_adapters` | 2 | 旧 callable | 已在原 Slice 3 allowlist，必须迁为 typed deterministic runner |
| `tests/fins/test_cn_download_workflow.py:731` | 1 | 旧 callable | 已在原 Slice 3 allowlist，builder 必须迁为 typed deterministic runner |
| `tests/fins/test_cn_pipeline.py` 的 CN sync、HK sync、CN stream、non-explicit start 四个 download tests | 4 | 旧 callable | 原 allowlist 外，必须新增到 test allowlist；以测试函数和 constructor keyword 定位，不绑定易漂移行号 |
| `tests/fins/test_cn_pipeline.py:376,559,618,668,721,777` | 6 | 无 | 默认构造；仅验证 download default 或 upload，原则上无需修改 |

所有 `CnPipeline` import 都使用原名；未发现 alias、factory indirection 或动态名称构造。

### 3.3 conversion dependency 穷举

Production owner/call chain 的直接证据如下：

1. `dayu/fins/pipelines/cn_download_protocols.py:44,203` 当前把 conversion 定义为
   `Callable[[bytes, str], bytes]`，并由 `CnDownloadWorkflowHost` 暴露裸 callable property；
2. `dayu/fins/pipelines/cn_pipeline.py:343-350,426,577-590` 当前由 facade 构造函数接收、
   持有并返回该 callable；
3. `dayu/fins/pipelines/cn_download_workflow.py:257` 把 host property 传给 single-filing owner；
4. `dayu/fins/pipelines/cn_download_filing_workflow.py:113,315-332` 当前接收裸 callable，
   发出 `CONVERSION_STARTED` 后通过 `asyncio.to_thread` 执行；
5. 基础计划 §5.5 与 Slice 3 将上述唯一链路替换为 typed runner，并把 process lifecycle
   收口到新 production owner `ProcessCnDoclingConversionRunner`。production filing workflow
   必须从当前同步调用：

   ```python
   await asyncio.to_thread(convert_pdf_to_docling_json, pdf_bytes, pdf_filename)
   ```

   改为直接等待 typed runner：

   ```python
   docling_json_bytes = await docling_conversion_runner.convert_pdf_to_docling_json(
       pdf_bytes,
       pdf_filename,
       cancellation_checker=conversion_cancellation_checker,
   )
   ```

   其中 `conversion_cancellation_checker` 是 workflow 在进入 conversion 前收敛出的非可选
   operation checker；production 不得继续用 `asyncio.to_thread` 包裹 async runner，也不得
   用 callable compatibility adapter 保留旧链路。

Test injection 完整集合：

| 文件与位置 | 原 allowlist 状态 | 处理 |
| --- | --- | --- |
| `tests/fins/test_cn_download_runtime.py` 的 `_RecordingPipeline.__init__` 与 `_build_runtime_with_cn_hk_adapters` | 已允许 | 迁为 typed deterministic runner，并纳入 constructor checklist |
| `tests/fins/test_cn_download_workflow.py:747,890,2128` | 已允许 | builder、host property 与 direct single-filing call 全部迁移 |
| `tests/fins/test_cn_pipeline.py` 的 `test_download_runs_cn_workflow_with_injected_discovery_client`、`test_download_runs_hk_workflow_with_injected_discovery_client`、`test_download_stream_runs_cn_workflow_with_injected_discovery_client`、`test_download_non_explicit_nonempty_start_keeps_default_business_limit` | 遗漏 | 新增文件 allowlist 后迁移四个 constructor injection；implementation 前以 keyword AST scan 重定位 |

未发现其它 production 或 test 文件注入旧 conversion callable。

### 3.4 下载事件序列与 `CONVERSION_STARTED` 穷举

完整 CN download 成功事件序列只有两处精确断言：

- `tests/fins/test_cn_download_workflow.py:944-952`：single workflow owner，已在原 allowlist；
- `tests/fins/test_cn_pipeline.py::test_download_stream_runs_cn_workflow_with_injected_discovery_client`：真实 `CnPipeline.download_stream` facade contract，
  原 allowlist 遗漏。

两处当前顺序都为 `... FILE_DOWNLOADED -> CONVERSION_STARTED -> FILING_COMPLETED ...`，
均须在 `CONVERSION_STARTED` 与 `FILING_COMPLETED` 之间加入
`DownloadEventType.CONVERSION_COMPLETED`。

交叉引用基础计划 §5.5：production single-filing owner 只有在 child 正常返回、handle close、
child output size/digest 验证以及 conversion-completion cancel checkpoint 全部通过后，才可发出
`CONVERSION_COMPLETED`；事件发出后、取得 `PUBLICATION_ELIGIBLE` 前必须再执行 cancel
checkpoint。精确顺序为：

`child output -> close -> size/digest validation -> cancel checkpoint -> CONVERSION_COMPLETED -> cancel checkpoint -> PUBLICATION_ELIGIBLE -> publication batch`。

因此 completion 既不能表示“child 已启动/已退出但未验证”，也不能直接授予 publication
资格；completed 后到 publication 前的 checkpoint 是取消时无半发布的 owner contract。

其它命中点分类如下：

- `tests/fins/test_cn_download_workflow.py` 中 conversion 前取消、failure、commit/rollback 与
  filing terminal 的正反断言属于原 allowlist，Slice 3 可在 owner boundary 更新或扩充；
- `tests/fins/test_fins_ingestion_runtime.py:765,1949` 断言 adapter 投影的
  `download.conversion_started`，已在原 allowlist；是否新增 completed public progress 只由
  Slice 3 production projection 决定，不要求额外测试文件；
- `tests/fins/test_cn_pipeline.py:581-588,686-693` 使用的是
  `UploadFilingEventType.CONVERSION_STARTED` / `UploadMaterialEventType.CONVERSION_STARTED`，
  属于 upload contract，不是 `DownloadEventType`，本 amendment 明确禁止修改；
- SEC download tests 只引用共享 `DownloadEventType` 的 filing terminal，不执行 CN conversion，
  新增 enum member不会改变其序列；
- `tests/fins/test_docling_upload_service.py` 与 SEC upload tests 同属 upload conversion，
  与 Slice 3 download runner 无关，不需要加入 allowlist。

因此，原 allowlist 外没有第二个必须迁移的文件。

## 4. Semantic owner 与测试所有权裁决

### 4.1 Contract owners

- `CnDoclingConversionRunner` 的签名 owner：
  `dayu/fins/pipelines/cn_download_protocols.py`。
- production child process、temp tree、size/digest、terminate/kill/close owner：
  新文件 `dayu/fins/pipelines/cn_docling_process.py`。
- runner dependency assembly 与 facade 构造 contract owner：
  `dayu/fins/pipelines/cn_pipeline.py`。
- conversion/publication 状态顺序 owner：
  `dayu/fins/pipelines/cn_download_filing_workflow.py` 与
  `dayu/fins/pipelines/download_events.py`。
- 完整 CN/HK workflow 转发 owner：
  `dayu/fins/pipelines/cn_download_workflow.py`。

### 4.2 为什么 `tests/fins/test_cn_pipeline.py` 是 owner-level contract test

该文件不是为共享 fixture 提供默认值，也不是下游用旧行为反推新语义：

- 模块职责就是 `CnPipeline download facade 行为测试`；
- 四个命中测试直接构造真实 `CnPipeline`，验证 CN、HK、async stream 与
  `start_is_explicit=False` facade 行为；
- 本地 `_PipelineDownloadFakeConverter` 是 facade conversion dependency 的确定性替身，
  其签名必须与 `CnPipeline` 的 typed injection contract 一致；
- `test_download_stream_runs_cn_workflow_with_injected_discovery_client` 直接消费真实
  `download_stream` 并断言完整公开事件顺序，正是新增 `CONVERSION_COMPLETED` 的 facade 级
  contract proof；
- 若不迁移该文件，production 只能保留旧 callable 参数/property 或兼容 adapter，
  这会把错误测试预期变成 production contract，属于明确禁止的 fixture workaround。

裁决：将该文件加入 Slice 3 test allowlist 是 owner test 随 contract 迁移，不是扩大业务目标，
也不是为保旧测试增加兼容代码。

## 5. 精确 allowlist amendment

### 5.1 新增 test allowlist

在基础计划 Slice 3 的 **Allowed test files / owner tests** 中仅新增：

- `tests/fins/test_cn_pipeline.py`：`CnPipeline` typed conversion runner injection 与
  CN download facade 事件顺序 owner test。

没有其它新增 production、test、README 或 runtime helper 文件。

### 5.2 `tests/fins/test_cn_pipeline.py` 精确允许修改内容

仅允许以下变更：

1. 当前 `_PipelineDownloadFakeConverter.__call__` 是由 production
   `asyncio.to_thread(sync_callable)` 调用的同步方法；把它迁为实现
   `CnDoclingConversionRunner` 的 typed deterministic fake runner，删除同步 `__call__`，
   改为
   `async convert_pdf_to_docling_json(pdf_bytes: bytes, stream_name: str, *, cancellation_checker: Callable[[], bool]) -> bytes`，
   保留明确类型、中文 docstring 与可观测调用计数，不引入 sleep、真实 Docling、真实进程或 timing hook；
2. 在 `test_download_runs_cn_workflow_with_injected_discovery_client`、
   `test_download_runs_hk_workflow_with_injected_discovery_client`、
   `test_download_stream_runs_cn_workflow_with_injected_discovery_client` 与
   `test_download_non_explicit_nonempty_start_keeps_default_business_limit` 四个函数的
   `CnPipeline(...)` constructor 中，从旧 `convert_pdf_to_docling_json=converter` 迁为唯一
   typed runner 参数 `docling_conversion_runner=runner`，并同步局部变量/调用计数断言；
3. 在 `test_download_stream_runs_cn_workflow_with_injected_discovery_client` 的旧下载事件序列中，
   仅在 `CONVERSION_STARTED` 后加入 `DownloadEventType.CONVERSION_COMPLETED`；
4. 不修改本文件的 upload fake、upload event sequence、默认 `CnPipeline` upload 构造、
   storage/assertion 或其它非 Slice 3 行为。

`CONVERSION_COMPLETED` 后仍有 cancellation checkpoint 的 owner proof 继续放在原已允许的
`tests/fins/test_cn_download_workflow.py`：使用 deterministic cancellation state，在 consumer
观察到 `CONVERSION_COMPLETED` 后请求取消；下一次推进必须在进入 publication batch 前取消，
断言 cancelled terminal、无 `FILING_COMPLETED`、无 source/blob 半发布。不得把该语义塞进
facade fake 或用 fixture side effect 猜时序。

原已允许的 `tests/fins/test_cn_download_runtime.py::_RecordingPipeline` 子类也必须纳入
constructor migration/checklist：其 `super().__init__` 删除旧
`convert_pdf_to_docling_json=_RuntimeFakeConverter()`，改为 typed deterministic runner 注入。
这是原 Slice 3 allowlist 内的既有工作，不新增 amendment allowlist。

### 5.3 保持不变的范围

- 基础计划列出的全部 production allowlist 原样保持，不新增 production 文件；
- `dayu/runtime/interruptible_process.py` 仍为 read-only baseline，禁止修改；
- 不新增 spawn wrapper、callable compatibility adapter、双构造参数、re-export、fallback、
  `hasattr/getattr`、production timing hook 或 sleep；
- 不修改真实 CLI/provider、README、Oracle、registry、Host、Engine、Service、upload contract；
- 不修改 `docs/gateflow/wu-cli-download-01-plan-20260809.md`；
- 本 gate 不修改任何产品或测试，不 commit、不 push、不创建 PR。

## 6. Implementation 后验证要求

### 6.1 Owner tests 与 affected union

激活 Python 3.11 venv 后，先运行 Slice 3 owner tests：

```bash
source .venv/bin/activate
pytest tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_cn_docling_process.py -q
```

随后运行基础计划 §9 的完整 affected union，包括 read-only
`tests/runtime/test_interruptible_process.py`。为排除 process/cancellation flaky，至少连续 5 次运行
下列 deterministic owner set；每次均使用 Event/barrier 与 bounded deadline，不使用 sleep 猜时序：

```bash
pytest tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_docling_process.py -q
```

### 6.2 类型、lint、格式、编译与 coverage

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
python -m ruff check <本 WU 全部 changed Python files>
python -m ruff format --check <本 WU 全部 changed Python files>
python -m compileall dayu tests
git diff --check
```

affected union 使用同一 coverage data；每个修改 production 文件分别执行：

```bash
coverage report --include=<modified-production-file> --fail-under=80
```

不得以 union 总覆盖率替代单文件 statement coverage。新增/修改 test 文件不承担 production
80% 阈值，但必须为相应 owner contract 提供直接断言。

### 6.3 AST / static scans

implementation review 前必须提供以下静态证据：

1. 仓库级 AST 穷举全部 `CnPipeline` 构造与子类 `super().__init__`；所有 download conversion
   注入均为 `docling_conversion_runner=`，不存在旧 constructor keyword；
2. `rg` 穷举 `convert_pdf_to_docling_json`，只允许 typed Protocol method、runner method 与
   workflow 调用；不得残留裸 callable TypeAlias/property/constructor injection；
3. production CN download path不存在 `asyncio.to_thread(convert_pdf...)`；
4. AST 证明 `ProcessCnDoclingConversionRunner` 调用真实
   `InterruptibleProcessHandle.start()`，且 production 无 `.spawn()` wrapper/call；
5. `git diff --exit-code -- dayu/runtime/interruptible_process.py` 证明 helper 未修改；
6. 成功事件顺序同时由 workflow owner 与 `CnPipeline` facade owner 断言
   `CONVERSION_STARTED -> CONVERSION_COMPLETED -> FILING_COMPLETED`；
7. deterministic owner test 证明 consumer 在 `CONVERSION_COMPLETED` 后请求取消时，
   publication checkpoint 仍阻止 batch/publication；
8. `rg`/AST 再次穷举 `CONVERSION_STARTED`，确认 upload event tests 未被误改；
9. production/test 中不存在 callable compatibility shim、双参数 fallback、`hasattr/getattr`、
   production sleep/timing hook；
10. public/log 文本不含绝对 temp 路径、PDF 内容、provider raw payload 或 contact canary。

上述 implementation-time AST gate 使用以下可执行命令；实现前按预期报告旧 injection，
实现后必须零错误退出：

```bash
python - <<'PY'
import ast
from pathlib import Path

violations: list[str] = []
constructors: list[str] = []
for root in (Path("dayu"), Path("tests"), Path("utils")):
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }

        def belongs_to_cn_pipeline_subclass(node: ast.AST) -> bool:
            while node in parents:
                node = parents[node]
                if isinstance(node, ast.ClassDef):
                    return any(
                        isinstance(base, ast.Name) and base.id == "CnPipeline"
                        for base in node.bases
                    )
            return False

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            is_cn_pipeline = isinstance(node.func, ast.Name) and node.func.id == "CnPipeline"
            is_super_init = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "__init__"
                and isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Name)
                and node.func.value.func.id == "super"
                and belongs_to_cn_pipeline_subclass(node)
            )
            if is_cn_pipeline or is_super_init:
                constructors.append(f"{path}:{node.lineno}")
            for keyword in node.keywords:
                if keyword.arg == "convert_pdf_to_docling_json":
                    violations.append(
                        f"{path}:{node.lineno}: legacy conversion injection keyword"
                    )

if len(constructors) != 16:
    violations.append(f"expected 16 CnPipeline/direct-super constructors, got {len(constructors)}")
if violations:
    raise SystemExit("\n".join(violations))
print("constructor scan passed:", len(constructors))
PY

python - <<'PY'
import ast
from pathlib import Path

path = Path("dayu/fins/pipelines/cn_download_filing_workflow.py")
tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
runner_awaits = [
    node
    for node in ast.walk(tree)
    if isinstance(node, ast.Await)
    and isinstance(node.value, ast.Call)
    and isinstance(node.value.func, ast.Attribute)
    and node.value.func.attr == "convert_pdf_to_docling_json"
]
to_thread_conversion = [
    node
    for node in ast.walk(tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and isinstance(node.func.value, ast.Name)
    and node.func.value.id == "asyncio"
    and node.func.attr == "to_thread"
    and any("convert_pdf" in ast.unparse(argument) for argument in node.args)
]
if len(runner_awaits) != 1 or to_thread_conversion:
    raise SystemExit(
        f"runner awaits={len(runner_awaits)} to_thread conversions={len(to_thread_conversion)}"
    )
print("typed runner await scan passed")
PY
```

## 7. Stop conditions

出现任一情况立即停止，不做 workaround，并返回 plan-amendment/re-review：

- implementation 后穷举发现除本 amendment 与原 Slice 3 allowlist外还必须修改其它文件；
- `tests/fins/test_cn_pipeline.py` 的迁移要求 production 保留旧 callable contract、兼容 wrapper
  或双参数入口；
- typed target 不可 pickle，或必须修改 `dayu/runtime/interruptible_process.py` 才能完成；
- `CONVERSION_COMPLETED` 只能在取消 checkpoint 前发出，或 completed 后取消仍进入 publication；
- success/failure/cancel/aclose 任一路径遗留 child PID、nested process group、temp tree、
  producer thread、late result 或半发布；
- tests 依赖 sleep/timing guess，重复运行 flaky，或 bounded deadline 无法证明 cleanup；
- 完整 pyright、changed-file Ruff/format、compileall、diff check、AST scans 或任一修改
  production 文件 80% statement coverage 失败。

## 8. Review adjudication

两份 review 均为 PASS；以下低严重度 findings 全部接受并在本 artifact 内最小修复，
不改变新增 test allowlist、semantic owner、production allowlist、validation threshold 或
§7 stop conditions。

| Review finding | 裁决 | 修复位置与证据 | 最终状态 |
| --- | --- | --- | --- |
| MiMo F1：同步 fake 到 async runner 的 production 联动未显式说明 | accepted | §3.3 明示 production 从 `asyncio.to_thread(sync callable)` 改为直接 `await docling_conversion_runner.convert_pdf_to_docling_json(...)`；§5.2 明示 test fake 删除同步 `__call__` 并迁为同签名 async method；§6.3 增加 AST gate | 已修复 |
| MiMo F2：四处 `test_cn_pipeline.py` 行号偏移且易漂移 | accepted | §3.2、§3.3、§5.2 全部改以四个测试函数名与 constructor keyword 为主定位；implementation-time AST 负责重新定位 | 已修复 |
| MiMo F3：已执行 AST 扫描缺少可复现命令 | accepted | §3.1 写入已执行只读 AST 扫描的完整可执行命令；§6.3 写入 implementation-time fail/pass gate | 已修复 |
| DS NB1：`CONVERSION_COMPLETED` production 精确插入位置未重申 | accepted | §3.4 交叉引用基础计划 §5.5，固定 `close -> size/digest -> cancel checkpoint -> completed -> cancel checkpoint -> publication eligibility`；§6.3 保留事件与 AST/static scans | 已修复 |
| DS NB2：`_RecordingPipeline` 子类未具名列入 checklist | accepted | §3.2、§3.3 与 §5.2 具名 `tests/fins/test_cn_download_runtime.py::_RecordingPipeline`，明确其原 allowlist 内 `super().__init__` migration | 已修复 |

没有 rejected、deferred 或 needs-more-evidence finding。下一 gate 是两路原 reviewer re-review；
在其确认上述状态前不进入 implementation。

## 9. Residual risks 与分类

| Residual risk | 分类 | Owner / disposition |
| --- | --- | --- |
| 两路初审均 PASS，五项 low finding 的修复尚待原 reviewer确认 | requiring explicit review | 本 artifact 完成后停止，等待两路独立 re-review |
| parent 被 SIGKILL 时 system-temp 可能残留 | covered by accepted base plan | 维持 §5.5 已记录 residual；本 amendment 不新增 scavenger |
| 非 POSIX 平台的 nested process-group 能力不同 | fixed/verified in current Slice 3 implementation | 由 helper read-only baseline 与 runner owner tests按 capability 断言，不修改 helper |
| 动态/别名 `CnPipeline` 构造漏检 | fixed in this amendment evidence | `rg` import 穷举与 AST direct/super call 双扫描未发现别名或动态构造 |
| upload `CONVERSION_STARTED` 被误当作 download contract 修改 | fixed by explicit scope | 本文件 upload event types 与 upload tests明确禁止修改 |
| future code 在 review 后新增旧 callable call site | requiring implementation-time verification | implementation/review 前重复仓库级 AST/`rg` 扫描 |

当前没有未分类 residual risk，也没有 blocking open question；下一 entry point 是两路独立
Slice 3 plan-amendment re-review，不是 implementation。

## 10. Docs 与完成报告决定

- 本 gate 仅新增当前 amendment artifact；不触发 README 更新。
- implementation artifact 必须引用本 amendment、两路 planreview artifact 与最终裁决，记录
  精确命令结果、PID/temp/thread 证据、重复运行、单文件 coverage、风险和未覆盖项。
- 本 gate 完成后停止，等待两路原 reviewer re-review；不 commit。
