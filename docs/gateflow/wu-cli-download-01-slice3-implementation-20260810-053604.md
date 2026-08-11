# `WU-CLI-DOWNLOAD-01` Slice 3 Implementation

## 1. Gate 状态与基线

- Work unit：`WU-CLI-DOWNLOAD-01`。
- Slice：Slice 3，DL-F09 canonical cancellation + DL-F11 conversion。
- 实施时间：2026-08-10 05:36:04 CST。
- 分支：`codex/download-oracle`。
- 实施基线 HEAD：`54309c597b71ca0f7ce581500e6272970588dec2`（接受后的 plan amendment commit）。
- Preflight：开始实施前 `git status --short` 无输出，worktree 干净。
- 基础计划：`docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.5、Slice 3 与 §9。
- Amendment：`docs/gateflow/wu-cli-download-01-slice3-plan-amendment-20260810-045002.md`。
- Amendment 初审：`docs/reviews/plan-review-20260810-045643.md`（MiMo，PASS）与
  `docs/reviews/plan-review-20260810-slice3-amendment-ds.md`（DS，PASS）；两路原 reviewer
  re-review 均为 PASS，后续由 accepted commit 固定。
- 本轮未 commit、push 或创建 PR；完成后停在两路独立 code review 入口。

## 2. 第一性原理与 semantic owner 裁决

实施动机成立。旧路径的两个根因都是 owner 错位：CLI 把 SIGINT 本地解释成
synthetic terminal，runtime 则没有拥有 producer thread 的完整 cleanup lifecycle；另一边，CN
filing workflow 把不可协作取消的 Docling conversion 留在普通 sync callable / thread
boundary，无法在业务 owner 内证明 child/process-group/temp cleanup。

实施后 owner 唯一性如下：

- CLI 只拥有 SIGINT -> operation token request 的 UI 投影；不拥有 terminal、130、timeout
  或 child kill。
- `FinsIngestionRuntime` 的 `_DirectStreamCancellationState` 拥有业务取消、consumer abort
  fence 与唯一 terminal claim；私有 operation task 唯一拥有 non-daemon producer thread
  及 bounded sync queue pump。
- `CnDoclingConversionRunner` 是 conversion 注入 contract owner；
  `ProcessCnDoclingConversionRunner` 拥有 spawned child、process group interrupt、handle close、
  system-temp tree 与 size/digest validation。
- `run_cn_download_single_filing_stream` 拥有
  `CONVERSION_STARTED -> CONVERSION_COMPLETED -> publication eligibility` 顺序与两个 cancel
  checkpoint。

### 2.1 Consumer abort 补充裁决

实施期间复核发现，若 `request_consumer_abort()` 直接写入
`cancellation_requested`，producer 可能在 queue fence 丢弃事件前仍尝试 claim/build canonical
cancelled RESULT。这与基础计划 §5.5“owner-initiated cancel 只收回资源，不创造业务
RESULT”相违，不能以 consumer 看不到 queue item 作为替代证明。

修正位于 cancellation state owner：consumer abort 只设 resource-reclamation fence，使
downstream checker 返回停止，但 `claim_terminal()` 明确返回 `None`，不写入
`_terminal_status`。`aclose()` 与 cancelled consumer task 两条真实路径均捕获同一 state
owner，在 downstream 完成、operation task 回收且具体 `Thread.is_alive()` 为 `False`
后，直接断言 `_terminal_status is None`。

## 3. 实现摘要

### 3.1 Canonical runtime cancellation 与 CLI

- CLI 删除 `_CliDirectLocalExit`、local cancel render 与 SIGINT 分支的 `event_task.cancel()`；
  首次 SIGINT 幂等 request token/渲染 cancelling，重复 SIGINT 不重复 request，始终等待
  同一 validated consumer clean exhaustion，exit code 只取自 canonical terminal。
- Runtime 新增私有 operation task，在 task 内创建 bounded sync queue 与
  `daemon=False` producer thread；task pump 完 producer done 后先 `thread.join()`，再向 raw
  async source 交付 clean-exhaustion marker。
- 原子 terminal gate 使先生效的业务取消压过迟到 provider/child failure；已提交
  success/failure 不被晚到取消改写；duplicate terminal 无法二次 claim。
- Normal completion、business cancellation、consumer `aclose()` 与 consumer task cancellation 都等待
  provider/downstream、producer thread 和 operation task cleanup；consumer abort 不创造业务 RESULT。

### 3.2 Typed Docling child process

- 删除旧 `PdfToDoclingJsonBytes` / sync callable property/constructor，10 处 injection（production
  pass-through、`_RecordingPipeline`、workflow tests 与 4 个 facade tests）全部迁移到
  `docling_conversion_runner=`，不保留 compatibility shim。
- Production filing workflow 直接 `await runner.convert_pdf_to_docling_json(...)`，不再通过
  `asyncio.to_thread(sync callable)` conversion。
- 新 process runner 每次在 system temp 创建唯一 tree；parent 写 input，可 pickle top-level
  target 调用真实 Docling 并写 output，queue 只返回 size/SHA-256。
- Parent 真实调用 `InterruptibleProcessHandle.start()/wait()/terminate()/kill()/close()`；
  success/failure/cancel 均先 close，然后读取并验证 output，最后 cleanup temp tree。既定
  primary outcome 不被 cleanup failure 改写，warning 不包含 path/PDF/provider raw data。
- 取消路径以 50ms poll 观察 checker，依次 terminate 2.0s、必要时 kill 1.0s，
  然后无条件 close。测试通过 test-only 常量 monkeypatch 缩短 grace，production 未增加
  timing hook 或 sleep。

### 3.3 Conversion completion 与 publication fence

实际顺序为：

`child return -> handle close -> size/digest validation -> cancel checkpoint -> CONVERSION_COMPLETED -> cancel checkpoint -> publication eligibility -> batch/publication`。

Workflow owner 与 `CnPipeline.download_stream` facade owner 都断言 success 顺序。Consumer 在
`CONVERSION_COMPLETED` yield boundary 请求取消的 deterministic test 证明下一 checkpoint
返回 cancelled terminal，无 `FILING_COMPLETED`、source meta 或 blob 半发布。Upload event contract
未修改。

## 4. 修改文件

Production（全部位于 Slice 3 allowlist）：

- `dayu/cli/commands/fins.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/download_events.py`
- `dayu/fins/pipelines/cn_docling_process.py`（new）
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`

Tests（全部位于基础计划/amendment allowlist）：

- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_cn_docling_process.py`（new）

本 implementation artifact 是唯一新增文档。`dayu/runtime/interruptible_process.py`、基础计划、
README、Oracle、真实 CLI/provider、upload contract 均未修改。

## 5. Deterministic lifecycle 证据

### 5.1 Process/PID/temp

`tests/fins/test_cn_docling_process.py` 中 success、failure 与 cancellation 都使用真实
`InterruptibleProcessHandle.start()`；test wrapper 只记录同一真实 handle 的 API 顺序。

- Success：记录 `start -> wait... -> close`，并在 size/digest validator 入口直接断言
  最后一个 handle call 是 `close`。
- Failure：spawned child 真实抛异常，parent 收到 typed failed result，仍以 `close` 收口。
- Cancellation/nested group：outer target 和 nested Python child 分别把实际 PID 写入
  bounded marker barrier；两者都忽略 SIGTERM，迫使真实调用顺序为
  `terminate -> kill -> close`。Runner 返回后逐个 PID 使用 `os.kill(pid, 0)` 在 5s
  bounded deadline 内断言不存在。PID 是每次 OS 动态值，不写入持久 artifact；
  证据是测试从 marker 解析实际值并对该值完成存活性断言。
- 每条路径通过包装真实 `tempfile.mkdtemp(prefix="dayu-cn-docling-")` 捕获每 run
  system-temp path；return/raise 后逐个断言 `Path.exists() is False`。Kill 后 target 不可能
  再写 late output，temp tree 也已删除。
- Production target 另行执行 `pickle.dumps/loads` round-trip，并直接验证 queue descriptor
  只有 `size`/`sha256`。

### 5.2 Runtime thread/queue/terminal

- Very-early business cancel：adapter 调用 0 次，唯一 RESULT 为 cancelled，clean exhaustion 后
  无 `fins-direct-download` thread。
- Cancel vs late provider failure：Event barrier 先让 provider 进入，再 request token，最后释放
  provider 抛迟到异常；唯一 RESULT 仍为 cancelled。测试保存具体 `Thread`
  对象，clean exhaustion 后断言 `is_alive() is False`。
- `aclose()` 与 cancelled consumer task：两条路径都让 downstream 在 barrier 上观察
  checker，断言 task/close 只在 downstream finished 且具体 producer `Thread.is_alive()` 为
  `False` 后返回；cancellation owner state 均为 `is_consumer_aborted() == True` 且
  `_terminal_status is None`，直接证明未创建业务 RESULT。
- CLI 测试用 async Event/Queue barriers 分别证明首个与第二个 SIGINT 已被 owner
  消费；token `request_count == 1`，terminal 释放前 wait task 未完成，最终 exit 130
  来自 validated cancelled summary。

## 6. 验证命令与结果

### 6.1 Owner tests、repeat 与 affected union

| 命令 | 结果 |
| --- | --- |
| `pytest -q tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_direct_stream.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py tests/fins/test_cn_docling_process.py` | PASS，最终复核 245 passed，3 个既有 edgar deprecation warnings，5.80s；先前 owner/coverage 运行为 5.72s/7.15s。 |
| `for run_index in 1 2 3 4 5; do pytest -q tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_direct_stream.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_docling_process.py; done` | 5/5 PASS；每次 170 passed，耗时 4.39s–5.00s。 |
| 上述 late-provider-failure test 独立连续 10 次 | 10/10 PASS；每次 1 passed，0.82s–0.93s。 |
| 基础计划 §9 完整 21-file affected union | PASS，1367 passed，3 warnings，43.24s。 |
| `pytest -q tests/runtime/test_interruptible_process.py` | PASS，37 passed，1.09s；文件 read-only。 |

首次 coverage union 中出现 1 个测试假阳性：测试以退出 thread 的数字 `ident`
断言存活，该整数随后被 `asyncio.to_thread` worker 复用。根因为测试证据不稳定，
非 runtime join 失败。修正为保存实际 `Thread` 对象并断言 `is_alive()`，随后通过
10 次独立重复、5 次 owner set 与完整 union。

### 6.2 Coverage（同一 245-test coverage data）

| 修改的 production 文件 | Statement coverage | `--fail-under=80` |
| --- | ---: | --- |
| `dayu/cli/commands/fins.py` | 85% | PASS |
| `dayu/fins/ingestion_runtime.py` | 90% | PASS |
| `dayu/fins/pipelines/download_events.py` | 100% | PASS |
| `dayu/fins/pipelines/cn_docling_process.py` | 82% | PASS |
| `dayu/fins/pipelines/cn_download_protocols.py` | 100% | PASS |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 89% | PASS |
| `dayu/fins/pipelines/cn_download_workflow.py` | 93% | PASS |
| `dayu/fins/pipelines/cn_pipeline.py` | 89% | PASS |

每个文件都单独执行
`coverage report --include=<production-file> --fail-under=80`，全部 exit 0；未以 union 总覆盖率
89% 替代单文件门。

### 6.3 Types、lint、format、compile 与 diff

| 命令 | 结果 |
| --- | --- |
| `python -m pyright dayu/ tests/ utils/` | PASS，0 errors / 0 warnings / 0 informations。 |
| `python -m ruff check <14 changed Python files>` | PASS，`All checks passed!`。 |
| `python -m ruff format --check <14 changed Python files>` | PASS，14 files already formatted（最终复核）。 |
| `python -m compileall dayu tests` | PASS。 |
| `git diff --check` | PASS，无输出。 |
| `git diff --exit-code -- dayu/runtime/interruptible_process.py` | PASS，无输出。 |

### 6.4 AST / static gates

- Amendment 可执行 constructor AST gate：PASS，16 个 `CnPipeline(...)`/子类
  `super().__init__` constructor，0 个旧 `convert_pdf_to_docling_json=` keyword。
- Typed runner injection AST gate：PASS，精确 10 个 `docling_conversion_runner=` injection。
- Filing workflow AST gate：PASS，精确 1 个 awaited runner method，0 个
  `asyncio.to_thread(convert_pdf...)`。
- Process AST gate：PASS，production 精确 1 个 `.start()` call，0 个 `.spawn()`
  wrapper/call。
- CLI AST gate：PASS，`_wait_for_terminal_handling_sigint` 中 0 个
  `event_task.cancel()`、0 个 timeout/wait-for 与 0 个 `_CliDirectLocalExit`。
- Repository-wide `rg` 穷举：production/test 仅剩 typed Protocol/runner/fake method 及直接
  workflow await；无 `PdfToDoclingJsonBytes`、callable compatibility injection、production
  `hasattr/getattr`、production timing hook/sleep 或 process spawn wrapper。
- `CONVERSION_STARTED` 穷举区分 download 与 upload enums；download owner/facade 已加
  completed，upload assertions/delivery 未改。
- Process logging/static review：warning 只包含固定 stage、exception type 与 exit code；不包含
  absolute temp path、PDF bytes、provider raw payload 或 contact canary。

## 7. README / forbidden boundary 裁决

本 Slice 按 accepted 计划明确禁止 README/Oracle/真实 CLI/provider 修改，且本轮仅改内部
canonical lifecycle、typed injection 与测试契约，因此未修改 README。未修改
`dayu/runtime/interruptible_process.py`；read-only 37-test baseline 证明现有 helper 能满足 Slice 3，
没有触发 helper-defect stop condition。

## 8. Residual risks 与未覆盖项

| Risk | 分类 | Disposition |
| --- | --- | --- |
| Parent 被 SIGKILL 时 system-temp 可能残留 | accepted base-plan residual | 不在 workspace 增加 scavenger。 |
| 非 POSIX 平台无同等 process-group signal 能力 | platform residual | Nested group integration test 在 non-POSIX capability skip；helper read-only tests覆盖 capability 诊断。 |
| 底层文件系统或网络 I/O 永久不返回 | accepted base-plan residual | 依赖现有 bounded provider timeout/checkpoint；CLI 不伪造 timeout terminal。 |
| 本 Slice 未执行真实 CLI/provider/Docling 高成本业务运行 | explicitly deferred | 按基础计划，只有全部 slices/reviews/deepreview 后才进入 DL-G01～G05。 |
| 本地修改尚未经两路 Slice 3 code review | requiring explicit review | 本 artifact 后立即停止，不 commit/push/PR。 |

无未分类 risk，无新 stop condition，无超出 allowlist 的 helper/pickle/type/scope 需求。

## 9. 下一 gate

Implementation 与本 artifact 已就绪。下一合法入口是两路独立 Slice 3 code review；
在 review 结果与 finding adjudication 前不继续修改、不 commit、不 push、不创建 PR。
