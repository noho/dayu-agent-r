# WU-CLI-DOWNLOAD-03-DL-F15 Slice S1 Implementation

## 1. Artifact 状态与边界

- Work unit：`WU-CLI-DOWNLOAD-03-DL-F15`。
- Gate：唯一 Slice `S1` implementation。
- 日期：2026-08-10。
- Implementation baseline：`715b25a6105651fe21ddb454b1c378459cea1d9a`。
- 起点：branch `codex/download-oracle`，HEAD 与 baseline 精确一致，worktree clean。
- Accepted plan：`docs/gateflow/wu-cli-download-03-dl-f15-plan-20260810.md`。
- Artifact path：`docs/gateflow/wu-cli-download-03-dl-f15-s1-implementation-20260810.md`。
- Decision：`implementation-pass`；未进入 code review、stage、commit 或真实 CLI evidence gate。
- 下一未完成 Gate Order entry：`code review`。

本 gate 只实现 attempt-local Docling stream。未修改 DL-F12～F14、分类、CLI、Fins runner、
上传调用方、Web 调用方、storage、Service、Host、Engine 或其它 README / tests。

## 2. 第一性原理判断与 semantic owner

问题真实存在且严重性判断成立。baseline 中
`convert_pdf_bytes_with_docling(...)` 在回退循环外只构造一次可关闭的
`DocumentStream`；`run_docling_pdf_conversion(...)` 则会把同一转换回调调用至多三次。
核心测试在 production 修改前直接复现：首档转换器关闭底层 `BytesIO` 后失败，第二档读取同一流即抛
`ValueError: I/O operation on closed file.`。

唯一 semantic owner 是
`dayu/documents/docling_runtime.py::convert_pdf_bytes_with_docling(...)` 的
`immutable raw bytes -> per-attempt DocumentStream` 装配边界。修复放在该 owner 内；没有在
Fins runner、调用方、测试夹具或异常处理层添加补偿、重开、`seek(0)`、兼容分支或生产测试钩子。

## 3. 实现结果

### 3.1 Production owner

- 删除回退回调外共享的 `DocumentStream`。
- 既有转换回调每次被 attempt loop 调用时，都从相同 `raw_bytes` 和 `stream_name` 新建
  `DocumentStream` 与底层 `BytesIO`。
- 扩充函数中文 docstring，声明每次回退尝试使用独立输入流。
- `run_docling_pdf_conversion(...)` 的签名、循环、日志、成功短路与
  `raise last_failure from first_failure` 均相对 baseline 零 diff。
- 为满足用户要求的 changed-files Ruff/format，删除 baseline 中已存在但未使用的
  `Callable` import，并接受 formatter 在同一 allowed production 文件内的纯排版整理；这些整理无运行时语义。

### 3.2 Owner tests

新增 `tests/documents/test_docling_runtime.py`，使用模块级、严格类型的记录型转换器与工厂，只替换
`build_docling_pdf_converter`，保留真实尝试规划、转换器装配、attempt loop 与转换回调路径：

- 首档读取、关闭并抛预建异常；第二档断言初始 open、name/bytes 同源、wrapper 与底层流 identity
  均不同，然后成功，且第三档未触达。
- auto 三档分别读取、关闭并抛预建异常；断言精确
  `docling-parse/auto -> pypdfium2/auto -> docling-parse/cpu` 顺序、三组流 identity 全唯一，
  最终抛出的对象是预建末次异常，`__cause__` 是预建首次异常而不是中间异常。
- coverage 仅在实际 missing lines 指引下追加尝试链矩阵、pipeline options 投影与设备解析 owner cases；
  达到 80% 后立即停止，未继续实现其它候选。
- 测试代码没有 `Any`、`object`、无类型签名、`MagicMock`、生产 hook 或 loose parsing。

### 3.3 Docs

按 `tests/README.md` 的职责边界，只在既有 Download owner coverage 段追加一句，记录
attempt-local stream identity、closed-first/success-second 与 auto 三档首因/末因 contract。
未更新根 README、`dayu/README.md` 或其它分层 README，因为用户入口、工作流、分层与 Fins runner 均未变化。

## 4. Coverage 轮次与 missing-lines 映射

所有轮次只统计 `dayu/documents/docling_runtime.py`，使用 branch coverage；未使用 omit、pragma、
配置修改或阈值豁免。

| 轮次 | 测试增量 | 覆盖率 | 当轮 missing lines | 选择与缺口映射 |
|---|---|---:|---|---|
| baseline | 仅两项核心 stream tests | 59% | `129-136, 152-159, 178-186, 208, 226, 242, 262-267, 283-285, 311, 332->339, 369-385, 420-461, 501-504, 602` | 尚未选择 coverage-only case |
| 1 | `_plan_conversion_attempts` 不可再拆的平台/设备参数化矩阵 | 65% | `129-136, 152-159, 178-186, 208, 262-267, 369-385, 420-461, 501-504, 602` | 覆盖原缺口 `226, 242, 283-285, 311, 332->339`，锁定非 Windows auto/cpu、Windows auto CUDA 可用/不可用与显式加速器顺序 |
| 2 | `build_docling_pdf_pipeline_options` 投影与非法 table mode | 78% | `131-132, 152-159, 178-186, 208, 262-267, 369-385, 501-504, 602` | 覆盖原缺口 `420-461`，验证 accurate/fast、OCR、table、cell 与 device 正式 Docling 2.x contract |
| 3 | `resolve_docling_device_name` 缺失/空白/大小写/非法配置 | 81% | `152-159, 178-186, 262-267, 369-385, 501-504, 602` | 覆盖原缺口 `131-132, 208` 及同一非法值分支；达到阈值后立即停止 |

Ruff formatter 使最终文件行号前移；最终独立门禁仍为 81%，最终 missing lines 为
`148-154, 173-181, 257-262, 364-380, 490-493, 591`。

## 5. Validation

所有命令均先执行 `source .venv/bin/activate`。

- 旧实现负证据：两项核心测试 `2 failed`，直接观察到第二档 closed-file 读取失败。
- 核心修复后首次验证：`2 passed`。
- focused union：
  `pytest tests/documents/test_docling_runtime.py tests/fins/test_cn_docling_process.py -q`，
  `21 passed`。
- 最终 owner 整文件：`pytest tests/documents/test_docling_runtime.py -q`，`15 passed`。
- 最终 CN Docling runner 整文件：`pytest tests/fins/test_cn_docling_process.py -q`，`6 passed`。
- Documents import boundary：`pytest tests/documents/test_import_boundary.py -q`，`3 passed`。
- 最终 coverage：15 tests 全通过，line coverage `81%`；独立 `--fail-under=80` 门禁通过。
- 完整 pyright：`python -m pyright dayu/ tests/ utils/`，
  `0 errors, 0 warnings, 0 informations`。
- changed-files Ruff check：通过。
- changed-files Ruff format check：通过。
- `compileall`：两份 changed Python files 通过。
- `git diff --check`：通过。
- import/read-only diff guard：
  `cn_docling_process.py`、`docling_upload_service.py`、`web_fetch_orchestrator.py` 相对
  implementation baseline 零 diff。
- scope guard：最终 planned files 只有
  `dayu/documents/docling_runtime.py`、`tests/documents/test_docling_runtime.py`、
  `tests/README.md` 与本 artifact。
- frozen input SHA-256 均未变化：
  - `docs/cli_ci.md`：`edbdf7dd0865fcb5b92d693100074a49b2b0ce8cf9bc6bdccf3fd0cdc477f745`；
  - `docs/gateflow/wu-cli-download-01-post-fix-oracle-adjudication-20260810.md`：
    `4588bb6c58dd9513d4fad944b393068855e9edbad369adb4bc960721712ca127`；
  - goal artifact：`25efe4f4f18ad1dd837befc3f4ab3695cc6a1c56f9fac703105e988f73fe823c`。

未执行真实 CLI 或真实 Docling production evidence：accepted implementation commit 尚不存在，且用户明确要求
本 gate 不 stage/commit，符合 accepted plan 的 evidence 前置条件。

## 6. Residual risks 与 uncovered areas

- 第三方转换器关闭输入导致后续 attempt 无输入：`fixed in current slice`；两项核心 owner tests 已锁定。
- 真实环境可能首 attempt 直接成功，因而无法自然观察真实 fallback：
  `requiring explicit user decision`；只能在 accepted implementation commit 后按 plan 建立 detached clean
  evidence run，本 implementation gate 不伪造失败。
- provider 不再返回冻结目标或外部依赖阻断目标闭链：`requiring explicit user decision`；本 gate 未运行真实 CLI，
  也未扩展 provider、分类或 runner scope。
- 最终未覆盖行属于 backend 非法映射/依赖缺失、真实 CUDA 探测、真实 converter 装配、初始化异常包装和
  单次全失败分支；它们不是 DL-F15 的 attempt-local stream 行为，且 accepted plan 要求达到 80% 后停止。
  本 Slice 不把这些 uncovered areas 升级为新目标或新增风险。

## 7. Completion status

Slice S1 implementation 已完成，当前工作树未 stage、未 commit。所有行为、coverage、类型、格式、编译、
import boundary 与只读 diff guards 均通过；真实 CLI evidence 按约束留待 accepted implementation commit 之后。
下一入口为 `code review`。
