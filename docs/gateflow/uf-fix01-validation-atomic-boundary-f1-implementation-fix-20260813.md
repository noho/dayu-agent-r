# UF-FIX01 focused-real F1 — Implementation Fix Artifact

## 1. Gate context

- work unit：`UF-FIX01 validation-atomic-boundary`
- gate：focused-real F1 `implementation fix`
- base HEAD：`7ea01244ddd234ca6bbc9593168b6f320bb890c8`
- finding owner：`docs/gateflow/uf-fix01-validation-atomic-boundary-focused-real-finding-20260813.md`
- scope：只修复 `_DoclingProcessTarget` child adapter 的 inherited public stderr 泄漏；不运行 UF-PF01 full，不 push、不创建 PR

## 2. First-principles judgment and root cause

F1 成立且严重性准确。typed content failure、exit `1` 与 publication atomicity 已经正确；错误事实只是在第三方 conversion 运行期间，child 继承调用方 stderr，而 child 内第三方/docling/Dayu logger 可通过 stdlib `lastResort` 或底层 fd 直接写公开 CLI stderr。既有 `except` 只把异常收敛为 closed descriptor，不能撤回已经发生的 stream 泄漏。

唯一语义 owner 是 `dayu.fins.pipelines.docling_process_converter._DoclingProcessTarget` 的第三方调用边界。CLI 不拥有第三方执行动态范围，不能通过过滤 traceback/path 字符串修复；failure kind/message owner、父进程轮询与 publication transaction 也都不是根因。

## 3. Changed files and exact decision

- `dayu/fins/pipelines/docling_process_converter.py`
  - 新增模块级 `_isolated_inherited_stderr()`，复制 child 当前 stderr descriptor，并在第三方 conversion 动态范围内把底层 fd 重定向到 `os.devnull`，退出时恢复原 descriptor。
  - 隔离覆盖 `sys.stderr`、stdlib logger/native dependency 和第三方创建的后代进程继承写入，不按内容分类、不解析 traceback、不修改公开投影。
  - `_DoclingProcessTarget` 仍通过原有两个 `except` 返回 exact construction/execution failure descriptor。
- `tests/fins/test_docling_process_converter.py`
  - owner test 同时从 conversion callback 和无 handler/不 propagate logger 写入 traceback/绝对路径，再失败；断言 fd 级 stderr exact empty，descriptor kind/message exact 不变。
- `tests/cli/test_fins_commands.py`
  - 使用固定 calibration `/Users/leo/workspace/.dayu-cli-ci/upload-filing-calibration-20260811-tF6OnN/inputs/corrupt.pdf` 运行真实 `.venv/bin/dayu-cli`；断言 exit `1`、content kind、固定 typed reason、stderr bounded 且无 traceback/repo/input 绝对路径、fresh workspace 根不存在。
- `dayu/fins/README.md`、`tests/README.md`
  - 仅记录当前已实现的 child stderr owner contract 与对应 owner/真实 CLI coverage。

## 4. Preserved invariants and scope audit

相对 base HEAD 的产品代码 diff 只有 `dayu/fins/pipelines/docling_process_converter.py`。未修改 failure kind/message、attempt chain、shared converter instance、multiprocessing handle、cancellation、terminate/kill/close、format allow-list、SEC/CN/HK workflow、storage 或 publication transaction。没有 CLI filtering、字符串分类、fallback、兼容分支、`hasattr/getattr` 或失败后补偿清理。

## 5. Tests-first evidence and validation

### Red phase

生产改动前只加入两条测试并运行：`2 failed`。

- owner test 捕获 callback traceback/path 与 logger path 泄漏，同时原 descriptor 已是 `converter_execution`。
- 真实 CLI exit 已是 `1` 且 typed reason 正确，但 stderr 为 `5527` 字符，超过 `1024` 上界并含 `Traceback` 与 repo 绝对路径。

### Green phase

- 两条 focused tests：`2 passed`，3 条既有 edgar deprecation warning。
- accepted UF-FIX01 受影响完整测试集合，额外包含 shared converter owner 文件：`630 passed`，3 条既有 edgar deprecation warning。
- `coverage report --include='dayu/fins/pipelines/docling_process_converter.py' --show-missing`：`350 statements / 18 missing / 95%`。
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- changed-file Ruff：`All checks passed!`。
- `git diff --check`：通过。

按用户明确边界未运行 UF-PF01 full；本 gate 只运行新增的单 case 真实 CLI integration。

## 6. README decision

- `dayu/fins/README.md`：更新。该 child adapter stderr 隔离是 Fins shared converter 当前稳定安全边界。
- `tests/README.md`：更新。新增 owner 与真实 CLI coverage 属于现有 Fins/UF-FIX01 测试分层。
- 根 README、`dayu/README.md`、Service/Host/Engine/config README：不更新；用户命令、公开 reason、exit code、分层与装配均未变化。

## 7. Findings, residual risks, and completion status

- F1：`accepted`，implementation fix 状态为 `已修复`，待 implementation fix re-review 独立确认。
- fixed in current slice：child inherited stderr public leakage、owner regression 与 calibration corrupt PDF 单 case CLI regression。
- assigned to existing next gate：UF-PF01 full 全矩阵重新生成；用户明确禁止本 gate 运行，owner 保持既有 focused-real evidence gate。
- uncovered area：Windows descriptor 行为未在当前 macOS validation 中实跑；实现使用 Python 3.11 跨平台 `os.devnull`/`dup`/`dup2`，归现有跨平台 CI owner，不构成本 gate 的未分类风险。

本 artifact 状态：`implementation fix complete`。下一 Gateflow entry point：implementation fix `re-review`；re-review 通过后才创建本地 accepted fix commit。PR/push 保持禁止。
