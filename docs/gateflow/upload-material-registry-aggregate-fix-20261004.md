# upload_material 独立 registry WU aggregate 集中修复记录

## Gate 与裁决

- Gate：既有 WU 的 `aggregate deepreview -> fix`；本记录只处理 root 已登记的 REG-AG01，属于 REG-C04 / REG-R01 同一 crash 真实事实合同。**候选待双 re-review，不宣称 aggregate pass**。
- 裁决依据：`docs/gateflow/upload-material-registry-aggregate-adjudication-20261004.md`；直接反例：`workspace/tmp/upload-material-registry-20261003/root-aggregate-counterexample-01.json`。其余五项旧 finding 的既有裁决不变。
- 工作区：`/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，HEAD `238b28980dcbdebc4b44005d75003f00a4a719da`；未改 main，未创建 slice、commit、PR 或外部写入。

## Owner、修法与差异

- 唯一 producer `validate_upload_material_registration` 调用 `_assignment_guard`。此前正式 cli802 行使用 `_crash_path_kind` 对原始 `process_outcome` 的 SIGKILL、wait=-9、非 harness deadline kill 事实校验；正式 focused 行已由 `_focused_terminal` 将六个原始测量限制为 exit=0/success 或 SIGINT=130/cancel，却没有检查 `scenario.path_kind='crash'`。这使单改标签的虚假 crash 取得 pass/proof。
- `utils/cli_ci_upload_material_registry.py`：让已有 `_crash_path_kind` 接受“无 process SIGKILL 事实”状态，并在 focused formal 分支核完原件终态后调用同一 guard。`None` 表示该来源没有 process 事实，不合成 signal、process_outcome 或新 public 字段；其它 path_kind 不新增自动分类。
- `tests/cli/test_cli_ci_upload_material_registry.py`：新增六个参数化 owner API 负例，分别仅把一个真实 focused scenario 的 `path_kind` 改成 `crash`；逐例断言带 case 定位的错误及 `proof is None`。原合法六例、两条真实 SIGKILL/error 与非 SIGKILL 反向拒绝由既有测试和 strict 路径继续覆盖。
- 本轮仅上述两个代码/测试文件有 diff；冻结差异见 `workspace/tmp/upload-material-registry-20261003/aggregate-fix-sol-01/frozen.diff`。

## 实际验证与身份

- 原指定 pytest argv 中 `tests/cli/test_cli_run_observation.py` 在工作树和 HEAD 均不存在；实际退出 4、0 tests ran，原 stdout/stderr 与退出记录完整保留。仓库对应文件为 `tests/cli/test_cli_ci_run_observation.py`，故仅纠正这一文件名后重新运行。
- 最终受影响两文件 pytest：**186 passed**、实际退出 0；完整 pyright：**0 errors、0 warnings、0 informations**、实际退出 0；批准的 `python -m utils.cli_ci_upload_material_registry ... --check --output <本轮独占路径>`：实际退出 0。三条命令的 argv、cwd、actual_wait、actual_exit、双流字节数/SHA 见本轮 `result.json` 和 `command-executions-recovered.json`。无输出截断或 traceback。pyright stdout 的版本提示不是诊断错误。
- 新 strict 输出与冻结 ready proof 逐字节同为 **129672 bytes / SHA256 `196d933a99a8503a5cf6ae9550114fdcc0dd3d5b41d8cf4f32a9c435595ad532`**。manifest 前 12 个冻结候选文件与五个 live measured source 均核对原 bytes/SHA 不变；strict 同时验证原双副本 public sources。未重跑产品 802 或改 Raw、登记数据、authority、assignment、旧 proof。
- `tests/README.md` 已将此测试文件定位为 focused 来源与 strict `--check` 负例合同；新增同 owner crash 负例落在该职责内，未改变测试分层或入口，故无需修改 README。根 README、`dayu/README.md` 和各业务层 README 的触发条件均未命中。

## Residual 分类与交接

| Gateflow 类别 | 本轮状态 |
| --- | --- |
| fixed in current slice | REG-AG01 的代码与六例反例已修；REG-C04/R01 同合同整体状态须由同版双 re-review 裁定。本项是 aggregate fix，未创建新 slice。 |
| covered by later approved slice | 无本轮新增项；不创建新 slice。 |
| assigned to later work unit | 无本轮新增项；既有 WU 以外事项沿用原控制记录。 |
| tracked by existing issue | 无本轮新增项；既有 PR/issue 治理不推进。 |
| requiring new issue or explicit user decision | 无本轮新增项。 |

下一入口仅为 root 对当前两文件精确 SHA 的必要双 re-review；本记录不替代复审裁决。所有详细身份、命令记录、失败恢复和 artifact 路径见 `workspace/tmp/upload-material-registry-20261003/aggregate-fix-sol-01/result.json`。
