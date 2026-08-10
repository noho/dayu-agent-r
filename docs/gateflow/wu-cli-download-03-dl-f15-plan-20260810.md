# `WU-CLI-DOWNLOAD-03-DL-F15` Gateflow Plan Gate

## 1. Artifact 状态

- Work unit：`WU-CLI-DOWNLOAD-03-DL-F15`
- Gate：`plan`
- 日期：2026-08-10
- 基线：`54dd750a2e300e943eb25d9e49c09d31145ef1fb`
- Goal Confirmation：`docs/gateflow/wu-cli-download-03-dl-f15-goal-confirmation-20260810.md`
- Design document：无；本计划只落实已确认 goal artifact，不引入新的设计目标。
- Artifact path：`docs/gateflow/wu-cli-download-03-dl-f15-plan-20260810.md`
- Plan review adjudication：`docs/gateflow/wu-cli-download-03-dl-f15-plan-review-adjudication-20260810.md`
- Plan review fix：`docs/gateflow/wu-cli-download-03-dl-f15-plan-review-fix-20260810.md`
- Decision：`plan-review-fix-complete`；动机与 semantic owner 不变，无 blocking open question。下一未完成 gate 是 MiMo/DS `re-review`。
- 本 artifact 只完成 plan review fix；不授权实施、测试执行、真实 CLI 重跑、stage、commit、push 或 PR。

## 2. Preflight 与冻结输入

| 项目 | 直接结果 | 约束 |
|---|---|---|
| branch | `codex/download-oracle` | 非保护分支 |
| HEAD | `54dd750a2e300e943eb25d9e49c09d31145ef1fb` | 与用户给定基线一致 |
| dirty input | `docs/cli_ci.md` | 只读；SHA-256 `edbdf7dd0865fcb5b92d693100074a49b2b0ce8cf9bc6bdccf3fd0cdc477f745` |
| dirty input | `docs/gateflow/wu-cli-download-01-post-fix-oracle-adjudication-20260810.md` | 只读；SHA-256 `4588bb6c58dd9513d4fad944b393068855e9edbad369adb4bc960721712ca127` |
| goal artifact | `docs/gateflow/wu-cli-download-03-dl-f15-goal-confirmation-20260810.md` | binding scope contract；SHA-256 `25efe4f4f18ad1dd837befc3f4ab3695cc6a1c56f9fac703105e988f73fe823c` |

本 fix 只修改当前 plan artifact并新增 plan-review-fix artifact。上述三项输入不得改写；plan review adjudication 与两份 review 也只读。后续 gate 若发现冻结输入 digest 变化或出现 ownership 不明的 dirty 文件，立即停止并交总控裁决。

## 3. Goal、动机、成功信号与 alignment

### 3.1 第一性原理判断

DL-F15 是确定的生命周期错误，不是 Docling 偶发失败。fallback 的含义是每个 backend/device attempt 都重新处理同一份 PDF；第三方 converter 是否关闭其输入是 attempt 内部行为，不能决定后续 attempt 是否还有输入。当前代码把一个可变、可关闭的 `BytesIO` 跨 attempt 共享，已经破坏 attempt 隔离。

唯一目标是：一次 `convert_pdf_bytes_with_docling(...)` 调用中的每个 attempt，都从同一份 immutable `raw_bytes` 与同一个 `stream_name` 新建独立、初始可读的 `DocumentStream`。

### 3.2 成功信号与计划映射

| 已确认 success signal | 本计划中的唯一落点 |
|---|---|
| 首 attempt 关闭独立 stream 后失败，第二 attempt 仍可读并成功 | Slice S1 的核心 owner test 1 |
| `auto` 三档 stream identity 全部独立 | Slice S1 的核心 owner test 2，精确覆盖 `docling-parse/auto -> pypdfium2/auto -> docling-parse/cpu` |
| 全链失败仍抛最后异常，首次失败仍是 `__cause__` | 同一个三档 owner test，以异常对象 identity 断言，不比较字符串 |
| production runner、取消、临时目录、size/digest、publication 不变 | production diff allowlist + 现有 `test_cn_docling_process.py` 全文件回归 |
| tests、单文件 coverage >=80%、Ruff/format、compileall、pyright/static 通过 | §8 的固定命令与通过条件 |
| 真实 CLI/Docling 成功且产物完整、后续 process 可消费 | §9 的独立 repaired-commit evidence run |
| 不扩展 DL-F12～F14、分类或其它设施 | §4.3、§6 allowed files 与 static scope guard |

### 3.3 Non-goals / scope boundary

- 不修改或重新裁决 DL-F12、DL-F13、DL-F14；不修改 CN/HK form policy、HK Q2/Q4/Q3 分类、provider discovery、source/document identity 或 accepted Oracle/readiness。
- 不修改 CLI/Service/Fins workflow、storage、download cache、process/upload、Host、Engine、SEC throttle、取消、性能、日志协议或 observation 基础设施。
- 不改变 backend/device attempt 顺序、日志文本、公开函数签名、异常聚合规则或 converter 配置。
- 不重开已关闭的对象，不 `seek(0)` 复用旧 stream，不吞异常，不加 loose fallback、factory/profile/schema、兼容 shim、mock hook、生产测试开关或 ticker/document 特例。
- 不为 coverage 修改未触及的 production 分支；coverage 只允许通过 owner tests 补足。
- 不回写旧真实 evidence bundle，也不改写两份用户裁决输入。

这是一处 owner-boundary 生命周期修复加对应 contract tests；没有新抽象、新状态、新 schema 或跨层迁移，因此没有过度设计和 goal drift。

## 4. Semantic owner 与直接证据

### 4.1 唯一 semantic owner

`dayu/documents/docling_runtime.py::convert_pdf_bytes_with_docling` 是 `immutable PDF bytes -> attempt-local DocumentStream` 的唯一装配 owner：

- `raw_bytes: bytes` 是所有 attempt 的唯一输入真源；
- `_build_docling_document_stream(...)` 已是 `bytes -> DocumentStream(BytesIO)` 的唯一构造 helper；
- `run_docling_pdf_conversion(...)` 继续唯一拥有 attempt 规划/顺序、converter 构造、回退日志、首次失败与末次异常；
- `ProcessCnDoclingConversionRunner` 继续唯一拥有子进程、operation cancellation、system-temp、输出 size/digest 校验与 cleanup；
- Fins workflow、storage publication、CLI summary、upload 与 Web caller 都只是消费者，不拥有 attempt stream 生命周期。

修复必须发生在该 owner callback 边界。把补偿放到 process runner、Fins、CLI 或某一 caller 会留下其它 caller 继续复用 closed stream，因此不接受。

### 4.2 生产代码同源证据

- `dayu/documents/docling_runtime.py:510-602`：`run_docling_pdf_conversion(...)` 为 `auto` 规划三档，并在循环内对每档调用一次同一个 `convert_operation(converter)`；全链结束时 `raise last_failure from first_failure`。
- `dayu/documents/docling_runtime.py:605-626`：每次调用 `_build_docling_document_stream(...)` 都会新建一个 `DocumentStream` 和一个 `BytesIO(raw_bytes)`。
- `dayu/documents/docling_runtime.py:660-662`：当前只在进入 attempt loop 前构造一次 `stream`，lambda 对每个 converter 重复执行 `converter.convert(stream)`。这是 shared closed stream 的直接根因。
- `dayu/fins/pipelines/cn_docling_process.py:66-80`：production child 从临时输入读取 bytes 后调用 `convert_pdf_bytes_with_docling(...)`，并只包装 conversion failure；它没有也不应拥有 attempt stream。
- `dayu/fins/pipelines/cn_docling_process.py:91-173`：production runner 的 process/取消/temp/close/validation/cleanup 与 DL-F15 owner 无关，应保持字节不变。
- 其它真实 callers 是 `dayu/fins/pipelines/docling_upload_service.py:783-814` 与 `dayu/tools/web/web_fetch_orchestrator.py:1502-1538`；两者都直接消费同一 owner，证明修 owner 可以统一生效，且 caller 无需修改。

### 4.3 真实 closed-file evidence

冻结报告：

- `/Users/leo/workspace/.dayu-cli-ci/wu-cli-download-02-postfix-20260810-A9vLZQ/evidence/observed-behavior.md`
- SHA-256：`7ca07d76a6d0d5ed37a5c4b54917f08262bd8a5203bf2d31cc7781da4fa2e666`

同一真实 production 链的直接终端证据：

- 0066：`evidence/scenarios/f14-hk-main-board-baseline-0066/stderr.txt:115-116`。attempt 1 `docling-parse/auto` 因 SSL/model resolution 失败；attempt 2 `pypdfium2/auto` 随即为 `ValueError: I/O operation on closed file.`。
- 0700：`evidence/scenarios/f14-hk-0700-four-material/stderr.txt:376-377`。出现同一 attempt 1 外部 SSL 失败、attempt 2 closed-file 链。
- 0700 失败文档：`public-summary.txt:6`，Q3 document ID 为 `fil_cn_54602897a720227b36458950300dffda20b5cd66`，disposition 为 failed；PDF 已进入 conversion，Docling JSON 未发布。
- 0066 失败文档：`public-summary.txt:4`，Q2 document ID 为 `fil_cn_16b441c52063506c3331e06f84cd884882402075`，disposition 为 failed。

真实 evidence 与上述代码行位于同一 `dayu-cli download -> ProcessCnDoclingConversionRunner -> convert_pdf_bytes_with_docling -> run_docling_pdf_conversion` 路径；不以 summary 的泛化 `filing_execution_failed` 代替根因。

## 5. Contract / schema / state-machine / public interface 决策

- Public signature：无变化。`convert_pdf_bytes_with_docling(...)`、`run_docling_pdf_conversion(...)` 及 callback 形态全部保持。
- Schema / durable state / LLM-facing 文本：无变化。
- Attempt state machine：顺序、成功短路、日志和异常聚合不变；只新增不变量——每次进入 convert callback 前构造一个 attempt-local stream。
- Data flow：`raw_bytes + stream_name -> callback invocation -> new DocumentStream/new BytesIO -> current converter`。不得把 stream 实例放回 callback 外。
- Error handling：stream 构造或 converter conversion 的异常仍由既有 attempt loop 捕获；不得新增 catch、重分类或默认成功。

## 6. Affected files 与只读边界

### 6.1 唯一 implementation slice 的 allowed files

- `dayu/documents/docling_runtime.py`
- `tests/documents/test_docling_runtime.py`（新增）
- `tests/README.md`（只做 §7 的一处测试覆盖说明）

### 6.2 明确只读

- `dayu/fins/pipelines/cn_docling_process.py`
- `tests/fins/test_cn_docling_process.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/tools/web/web_fetch_orchestrator.py`
- 所有 DL-F12～F14、CN/HK form/classification/discovery、storage、CLI、Service、Host、Engine、runtime infrastructure 文件
- `docs/cli_ci.md`
- `docs/gateflow/wu-cli-download-01-post-fix-oracle-adjudication-20260810.md`
- `docs/gateflow/wu-cli-download-03-dl-f15-goal-confirmation-20260810.md`

任何 implementation diff 超出 §6.1，先停止，不得以“顺手修复”、coverage、真实 evidence 或 README 同步为由扩 scope。

## 7. README 决策

`tests/` 会新增 owner test，触发检查 `tests/README.md`。该 README 开头声明它记录当前测试分层，且现有 Download owner coverage 段已经描述 CN/HK Docling process runner，因此需要在同一段最小追加一句：`tests/documents/test_docling_runtime.py` 覆盖 attempt-local stream identity、closed-first/success-second 与 auto 三档首因/末因 contract。不得改写其它段落。

不更新根 README、`dayu/README.md` 或 Fins/Host/Engine/Config README：本修复没有用户可见参数/工作流变化，没有分层或装配变化，Fins production runner 也不修改。

## 8. 单一行为 Slice S1 — attempt-local Docling stream

### 8.1 Objective / expected outcome

让每一档 conversion attempt 获得从同一 immutable PDF bytes 新建的独立 stream；第一档即使关闭输入并失败，也不影响第二/第三档。Slice 完成时核心 owner tests、runner 回归、coverage 与全部 static gates 通过。

### 8.2 Prerequisites

- HEAD 与 plan 接受时记录的 implementation baseline 一致；若已前移，先由总控确认新 baseline。
- §2 三项冻结输入 digest 不变，dirty ownership 清楚。
- Docling 依赖满足项目正式区间；当前检查到 `docling 2.90.0` / `docling-core 2.74.0`，`DocumentStream.stream` 是 `BytesIO`。

### 8.3 Exact production change

只改 `convert_pdf_bytes_with_docling(...)` 尾部：删除 callback 外的 `stream = _build_docling_document_stream(...)`，在既有 lambda 每次被 attempt loop 调用时先构造 stream，再交给当次 converter。目标形态固定为：

```python
return run_docling_pdf_conversion(
    lambda converter: converter.convert(
        _build_docling_document_stream(raw_bytes, stream_name=stream_name)
    ),
    # 既有 options 原样透传
)
```

同步扩充该函数中文 docstring，明确每个 fallback attempt 使用独立 stream；不新增 helper、factory、参数、类型、日志、异常分支或关闭逻辑。

### 8.4 Core owner tests

在新文件 `tests/documents/test_docling_runtime.py` 使用模块级、严格类型的 recording converter/factory；factory 只替换 `build_docling_pdf_converter`，使真实 `_plan_conversion_attempts -> _build_attempt_converter -> run_docling_pdf_conversion -> convert callback` 保持在测试路径中。测试固定删除 `DAYU_DOCLING_DEVICE` 并把平台探测钉为 non-Windows，确保 `auto` 链稳定。fake converter 在收到 `DocumentStream` 时依次记录 wrapper identity、底层 `BytesIO` identity、`closed` 初值、name 与完整 bytes，然后主动 close，再按预置异常或 success 返回；仅在第三方 `ConversionResult` test double 边界使用精确 `cast`，禁止 `Any`、`object`、`MagicMock` 或生产测试 hook。

1. `test_convert_pdf_bytes_rebuilds_stream_after_closed_first_attempt_and_second_succeeds`
   - first converter 读取原 bytes、关闭其底层 stream，并抛出预建的 `RuntimeError` 实例；
   - second converter 必须收到 `closed is False`、相同 name、相同完整 bytes，但 `DocumentStream` 与底层 `BytesIO` identity 均不同，然后成功；
   - 精确断言只构造两档：`(docling-parse, auto)`、`(pypdfium2, auto)`，第三档未触达；
   - 该测试在旧实现上必须因第二档读取 closed stream 失败，在新实现上通过。

2. `test_convert_pdf_bytes_auto_three_attempts_use_distinct_streams_and_preserve_failure_chain`
   - 三个 converter 各自读取、关闭 stream，并分别抛预建的 first/middle/last 异常对象；
   - 精确断言 attempt identity 为 `[(docling-parse, auto), (pypdfium2, auto), (docling-parse, cpu)]`；
   - 三个 wrapper identity 与三个底层 `BytesIO` identity 各自全唯一，三个初始状态均 open，name/bytes 全相同；
   - 捕获结果必须是同一个 last 异常对象，`caught.__cause__ is first_failure`；不把 middle failure 错当 cause，不用错误字符串替代 identity。

### 8.5 Coverage-supporting owner cases

为满足已确认的“修改生产文件单文件 coverage >=80%”，implementation 必须先只完成 §8.4 两个核心 tests，并立即按 §9.2 测量 `dayu/documents/docling_runtime.py` 的 coverage baseline 与 missing lines。若 baseline 已达到 80%，本节候选 case 一个也不新增并立即停止 coverage 补测；若不足，只能根据报告中的实际 missing lines，从下列有界候选集中选择能覆盖缺口的最小 case，一次补一个最小 case 或一个不可再拆的参数化 case，随即重测。达到 80% 后立即停止，不机械完成候选清单。

有界候选 inventory 如下；它们只是在 baseline 低于 80% 时可选择的 owner cases，不是全部强制项：

- `resolve_docling_device_name`：env 缺失为 auto；支持值空白/大小写 canonicalize；非法值抛 `DoclingRuntimeInitializationError`。
- `_plan_conversion_attempts` 参数化矩阵：non-Windows auto/cpu、Windows auto CUDA available/unavailable、Windows explicit accelerator，精确断言现有 backend/device 顺序与 auto 第三档。
- `build_docling_pdf_pipeline_options`：accurate/fast、OCR/table/cell/device 投影与非法 table mode；只断言正式 Docling 2.x contract。
- `build_docling_pdf_converter` / `_resolve_backend_class`：两个支持 backend 的现有映射、非法 backend、converter options 装配；不执行真实 PDF conversion。
- `_build_attempt_converter`：普通构造成功；非初始化异常被包装且 `__cause__` 保持；既有 `DoclingRuntimeInitializationError` identity 原样传播。
- `_build_docling_document_stream`：name、bytes、初始 open 与两次调用 identity 独立。

每次选择必须在 implementation artifact 记录“当前百分比、missing lines、所选候选与这些行的映射、重测后百分比”。候选优先覆盖实际 missing production lines，不得为提高数字测试与缺口无关的第三方细节。若有界候选全部用尽后仍低于 80%，或剩余 missing lines 只能通过 §6.1 之外 test/product 文件、修改 production、执行真实重型 conversion 或 coverage bypass 才能覆盖，立即停止并回总控；不得扩大产品 diff、放宽阈值、加 `pragma: no cover`、改 omit/source 配置或继续发明候选。

### 8.6 Runner/caller invariants 与 stop conditions

- `tests/fins/test_cn_docling_process.py` 不修改但必须整文件通过，继续证明 real spawn、取消 terminate→kill、handle close、temp cleanup、size/digest 和 pickle target contract。
- `cn_docling_process.py`、upload service、Web caller 必须相对 baseline 零 diff；不为这些 caller 新增 wrapper test。
- 若实现需要改 callback 签名、attempt runner、production process runner、分类/storage/CLI，或 deterministic test 无法在 owner boundary 复现旧失败，则 Slice 停止并返回 goal ownership 重审。

## 9. Validation 与真实 evidence 计划

所有本地命令先执行 `source .venv/bin/activate`。

### 9.1 Deterministic tests

```bash
pytest tests/documents/test_docling_runtime.py tests/fins/test_cn_docling_process.py -q
pytest tests/documents/test_import_boundary.py -q
```

通过条件：§8.4 两项旧失败/新通过 contract 全部成立；现有 production runner 测试零回归；Documents import boundary 通过。

### 9.2 单文件 coverage

先仅用 §8.4 两个核心 tests 建立 baseline；此时测试文件不得预先包含 §8.5 的 coverage-only cases：

```bash
COVERAGE_FILE=workspace/tmp/wu-cli-download-03-dl-f15.coverage coverage erase
COVERAGE_FILE=workspace/tmp/wu-cli-download-03-dl-f15.coverage coverage run --branch -m pytest \
  tests/documents/test_docling_runtime.py
COVERAGE_FILE=workspace/tmp/wu-cli-download-03-dl-f15.coverage coverage report \
  --include='dayu/documents/docling_runtime.py' --show-missing
```

若报告低于 80%，按 §8.5 从有界 inventory 只补一个最小候选，然后重复同一组 `erase -> run -> report --show-missing`；每轮用最新 missing lines 决定下一项，达到 80% 即停止。最后单独执行门禁：

```bash
COVERAGE_FILE=workspace/tmp/wu-cli-download-03-dl-f15.coverage coverage report \
  --include='dayu/documents/docling_runtime.py' --fail-under=80
```

通过条件：`dayu/documents/docling_runtime.py` 单文件 line coverage 不低于 80%；报告保留 baseline、每轮实际百分比与 missing lines，不用全仓 aggregate 替代。若有界候选无法达到阈值，状态是 stop/回总控，不得以 implementation complete 报告。

### 9.3 Types / lint / format / compile / diff/static

```bash
python -m pyright dayu/ tests/ utils/
ruff check dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py
ruff format --check dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py
python -m compileall -q dayu/documents/docling_runtime.py tests/documents/test_docling_runtime.py
git diff --check
git diff --exit-code 54dd750a -- dayu/fins/pipelines/cn_docling_process.py dayu/fins/pipelines/docling_upload_service.py dayu/tools/web/web_fetch_orchestrator.py
```

另人工/静态核对：production diff 只有 §8.3 的 stream 构造位置与 docstring；`run_docling_pdf_conversion` 签名/循环/log/raise 行零 diff；§2 两项用户裁决输入的 SHA-256 不变；`git diff --name-only 54dd750a --` 中除冻结 dirty inputs、Gateflow artifacts 外，implementation 文件只属于 §6.1。

### 9.4 独立 production CLI + 真实 Docling evidence

正式真实 run 只能在 **accepted implementation commit** 创建后执行：从该 commit 建立 detached HEAD 的独立 clean validation environment，运行前记录 `git rev-parse HEAD` 精确等于 accepted implementation commit，并确认 `git status --porcelain` 为空。不得把未提交工作树、plan/review 工作树、旧虚拟环境、旧 workspace 或旧 evidence 当作正式 target。环境固定 Python 3.11，记录 commit/dependency identity，使用 fresh workspace，并保留新的 immutable evidence bundle。首选复现先前失败的 0700 Q3：

```bash
dayu-cli download --base <fresh-workspace> --ticker 0700 --forms Q3 --start 2025-01-01 --end 2026-04-30 --log-level debug --log-file <new-run>/logs/0700-q3.log
dayu-cli process --base <fresh-workspace> --ticker 0700 --document-id fil_cn_54602897a720227b36458950300dffda20b5cd66 --log-level debug --log-file <new-run>/logs/0700-q3-process.log
```

若 production provider 已不再返回该冻结 Q3 material，记录 provider availability gap，才允许用同一新 run 的 0066 Q2 既有失败样本替代；不得同时把两者升级成分类验收：

```bash
dayu-cli download --base <fresh-workspace> --ticker 0066 --forms Q2 --start 2025-01-01 --end 2026-04-30 --log-level debug --log-file <new-run>/logs/0066-q2.log
dayu-cli process --base <fresh-workspace> --ticker 0066 --document-id fil_cn_16b441c52063506c3331e06f84cd884882402075 --log-level debug --log-file <new-run>/logs/0066-q2-process.log
```

新 evidence 至少冻结：argv/env/commit/dependency、stdout/stderr/PTY、debug log、public summary、目标 source identity、PDF/Docling JSON/meta/manifest 的存在性/size/SHA-256/相互关联，以及 process public summary/processed consumability。财报文档读取和关联必须经 production CLI 与 `dayu.fins.storage` repository/public contract，不写绕过 storage 的产品代码。

裁决规则只绑定本次选定的一个目标文档：首选 0700 Q3；仅在其 provider availability gap 时改用 0066 Q2。download 命令保留为 production `dayu-cli download`，但不把同一真实 run 中其它材料的行为并入 DL-F15 verdict：

- 目标通过条件：目标文档完成 conversion/publication，PDF、Docling JSON、source meta、manifest 同 identity 且完整，production `dayu-cli process` 精确消费该 document ID；目标对应的 download/process public evidence形成闭链。命令 exit code 是必须记录的 raw observation；若非目标 failure 单独导致命令非零，但目标闭链仍完整，不把该非零机械升级为 DL-F15 failure。
- 若真实首 attempt 自然失败，日志必须显示后续 attempt 成功，且整个新 evidence 中 `I/O operation on closed file` / closed-stream 错误为 0。
- 若首 attempt 直接成功，只能证明目标文档成功链；`real fallback 未观察` 必须保留为 `requiring explicit user decision` 的 evidence gap，不设置环境、网络或生产 hook 制造失败。
- 非目标文档 failure、分类差异或新的 provider/storage/runner observation 只登记直接证据与建议 owner，不进入修复、不扩大测试/产品 diff，也不改变目标 verdict。若这些非目标问题阻断目标文档形成上述 evidence 闭链，则本次正式补跑标为 `requiring explicit user decision` evidence gap，并停止扩修。
- 目标文档再次出现 closed-stream、后续 attempt 无法读取同一 PDF 或目标 publication/consume 因本 Slice 行为失败，才属于 DL-F15 target failure；provider 不再返回目标、外部依赖不可用或非目标错误阻断目标链按 external evidence gap 处理，不猜测分类根因。
- 新 run 不重做或裁决 DL-F12～F14、HK 分类、Oracle/readiness；旧 frozen report保持不变。

## 10. Risks、residual classification 与 open questions

| 风险 | 处理 / 分类 |
|---|---|
| 第三方 converter 未来继续关闭输入 | 当前 Slice 在 owner boundary 消除跨 attempt 共享；`fixed in current slice` |
| 真实网络/model cache 使首 attempt 直接成功 | deterministic owner test 已证明 contract；真实 fallback 缺口标为 `requiring explicit user decision`，不得伪造 |
| provider 不再返回冻结的 0700 Q3，或非目标问题阻断目标闭链 | 先使用既有 0066 Q2 作为同 root-cause 的替代样本；仍无法形成目标 evidence 时标为 `requiring explicit user decision` external evidence gap，不扩大分类/provider scope |
| 真实 run 出现不阻断目标闭链的非目标 failure/分类差异 | 只登记直接证据并分配建议 owner；不参与 DL-F15 target verdict，不在本 WU 修复 |
| 核心 tests 的 coverage baseline 低于 80% | 按 missing lines 从 §8.5 有界 inventory 逐个补最小 case，达到即停；若边界内不可达则 stop/回总控，不允许改 production、扩模块或绕过门禁 |

Blocking open questions：无。

## 11. Completion signal、stop condition 与完成报告格式

Slice S1 完成信号：allowed production diff 已实现 attempt-local stream；核心两项 owner contract、auto 三档 identity、首次 cause/末次异常、runner regression、按 baseline/missing-lines 增量达到的 coverage、全量 pyright、Ruff/format、compileall、diff/static 全通过；README 决策已落实；accepted implementation commit 的 detached clean environment 中真实 target-specific evidence 已按 §9.4 分类并有明确 gap 状态。

任一以下情况立即停止：owner 不再清楚；必须改 §6.1 之外产品文件；attempt/log/exception/public signature 需要变化；非目标真实 observation 诱发扩修；非目标问题阻断目标 evidence；冻结 dirty input digest 变化；§8.5 有界候选无法达到 coverage 80%；coverage 只能靠生产规避、扩边界或门禁绕过实现。

后续 implementation closeout 必须按以下格式报告：

1. 改了什么：列出唯一 owner 改动、tests 与 README，明确 production runner/callers 零 diff。
2. 验证了什么：逐条列 deterministic tests、coverage 实际百分比、pyright、Ruff/format、compileall、static/diff、真实 CLI/Docling/process evidence path 与结果。
3. 还有什么风险或未覆盖项：只报告 §10 已分类 residual risk，尤其区分“真实 fallback observed”与“首 attempt 直接成功”。
4. Gate 状态：artifact paths、finding 状态、当前 gate decision 与 Gate Order 中下一未完成 entry point。
