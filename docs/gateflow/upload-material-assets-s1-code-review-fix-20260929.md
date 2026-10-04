# UM-O04/O23 S1 MiMo code review 裁决项修复记录

- 工作区：`/private/tmp/dayu-upload-assets`；分支：`codex/upload-material-assets`；HEAD：`1453a659a79d4c9a93838412dfdecfa7feeddf98`。
- 输入：`docs/reviews/code-review-20260929-114318.md`、`docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md`、accepted goal/plan、S1 实施记录与修复前 diff。修复前 `git status --short` 的 32 个 tracked 修改、6 个未跟踪生产/测试新文件及实施记录与 review 的路径清单一致；tracked stat 958 insertions / 1294 deletions 与 review 相同。未重新取得修复前 tracked diff 的 SHA-256；review 锁定值为 `837a486ef10f67e1e098457a1ef062302402c2768c0243add1a92767336c6ddf`，本修复后不再将该值用于当前 diff。
- 仅修裁决采纳的 F1–F5 与无身份漂移的 filing planner 双输入问题；未提交、推送、创建 PR、合并或进入下一 gate。

## 动机、根因与 owner

1. **F1**：`ValidatedFinsUploadMaterialRequest` 可直接构造矛盾的 raw request、selection、plan；runtime 对 validated 对象原样放行，SEC/CN 分别从 selection 与 plan 产生文件数量和发布事实。构造期 handoff 类型是唯一一致性 owner。新增 `__post_init__`：检查类型、source kind、material 无 filing primary、converter tuple 与 ordered tuple 同一对象、upsert raw 文件规范路径与 selection/plan 保序一致，以及 original/derived identity 与 planner 函数一致；delete 要求空 selection/plan。delete 的 raw `files` 继续按既有 admission 忽略，没有实施 O16 的拒绝规则。
2. **F2**：planner 的安全 basename 原本未进入 usage message；重复原件名 reason 甚至没有关联路径。`upload_asset_plan.py` 在发现第二个 exact 重名时携带该原件路径，由既有 canonical file label 生成安全标签；`upload_usage_contract.py` 是唯一新 reason 文案 owner，四种新增文件名错误嵌入该标签，仍用其既有 basename/长度边界检查。复用的 `MISSING_FILES`、`TOO_MANY_FILES`、`DUPLICATE_FILE_PATH` 文案和旧 CLI 缺失文件模板未改。
3. **F3**：`docling_upload_service.py` 的 material fingerprint payload 仅有原件的 `name`、`sha256`、`size`、`source`，`_can_skip_upload` 只比较该值；派生名不在公式内。已纠正 S1 实施记录和 `dayu/fins/README.md` 的一次性变化/重新发布断言，并保留路径规范化或末组件 symlink resolve 可能改变原件名的边界。
4. **F4**：SEC/CN workflow 的 `FinsUploadMaterialFiles` 仅有 import，旧构造调用已删除；移除两处死导入。
5. **F5**：补 handoff 构造期反例、material Service/runner `is` 身份、SEC/CN raw stream 与同步委托的单次 admission、usage 安全 basename、真实 CLI 同名错误、failure message 斜杠仅固定 `MISSING_FILES` 文案例外的测试；将陈旧的 tool 测试名改为实际“准入前格式拒绝”行为。测试只在既有函数边界计数，生产代码无测试 seam。

filing planner 的 `files` 与 `filing_selection.ordered_files` 原为双输入、只消费后者。两者当前唯一生产调用点保序相等。现在 planner 直接拒绝不一致输入，既有 filing SHA-256 identity、primary、指纹和合法输入结果未改；owner 测试覆盖逆序反例。此项可在本片无身份漂移地收敛，无需另交总控裁决。O16/O25/O34、存储发布、Docling 转换均未修改。

## 验证及原始输出

所有 Python 命令均先在本工作区执行 `source .venv/bin/activate`；解释器为 Python 3.11.15、`/private/tmp/dayu-upload-assets/.venv/bin/python`。

| 命令 | exit | 结果与原始输出 |
| --- | ---: | --- |
| `python -m pytest tests/fins/test_upload_usage_contract.py tests/fins/test_upload_asset_plan.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py tests/fins/test_fins_service_runtime.py -q` | 1 | 开发中 3 failed / 608 passed；`/private/tmp/dayu-upload-s1-fix-focused-1.log`。原因分别是旧 reason 测试给非文件 code 传 label、构造期测试创建了两个不同 tuple 导致先触发 converter 身份断言、重复 basename planner 没有 path 导致 CLI 走通用失败。随后在 owner/测试处修正。 |
| `python -m pytest tests/fins/test_upload_usage_contract.py::test_planner_reasons_share_usage_message_with_public_failure tests/fins/test_fins_ingestion_runtime.py::test_validated_material_handoff_rejects_cross_field_drift tests/cli/test_fins_commands.py::test_upload_material_cli_names_conflicting_basename_without_path -q` | 1 | 1 failed / 2 passed；`/private/tmp/dayu-upload-s1-fix-focused-2.log`。CLI exit 1、通用失败，直接 admission traceback 定位为重复 basename reason 缺少 file label；已在 planner 关联第二个重名路径。 |
| 下方完整矩阵命令 | 0 | 1443 passed、1 skipped、3 warnings；原始输出 `/private/tmp/dayu-upload-s1-fix-matrix.log`。3 个 warnings 为共享依赖 edgar 的弃用提示。 |
| `python -m pyright` | 0 | 0 errors、0 warnings、0 informations；`/private/tmp/dayu-upload-s1-fix-pyright.log`，另有版本更新提示。 |
| `python -m coverage report --include="$file" --fail-under=80`，逐一执行下列五个生产文件 | 各 0 | 逐项命令、exit、覆盖率原始输出：`/private/tmp/dayu-upload-s1-fix-file-coverage.log`。 |
| `git diff --check` | 0 | 无空白错误；空原始输出 `/private/tmp/dayu-upload-s1-fix-diff-check.log`。 |

另有一次定位命令 `source .venv/bin/activate && python -c 'from pathlib import Path; from dayu.fins.ingestion_runtime import FinsUploadMaterialRequest,admit_fins_upload_material_request; p=Path("/private/tmp/dayu-upload-s1-debug"); a=p/"one"/"deck.pdf"; b=p/"two"/"deck.pdf"; admit_fins_upload_material_request(FinsUploadMaterialRequest(ticker="AAPL", files=(a,b)))' 2>&1 | tail -25`，在修复重复 basename path 前输出 traceback，核心为 `ValueError: 文件 usage failure 必须提供不含路径的 basename`。该探索命令未重定向原始输出到文件，且管道末端 `tail` 的 shell exit 为 0；不能把它当作通过的 admission 验证，也不能补造原始输出路径。失败原因已由 `/private/tmp/dayu-upload-s1-fix-focused-2.log` 的真实失败回归以及后续 owner 修复确认。

完整矩阵原始命令：

```bash
source .venv/bin/activate && python -m pytest tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_service_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_fins_commands.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py --cov=dayu.fins --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins --cov-report=term-missing -q
```

逐文件覆盖率：`ingestion_runtime.py` 91%、`upload_asset_plan.py` 91%、`upload_usage_contract.py` 95%、`sec_upload_workflow.py` 94%、`cn_pipeline.py` 93%。聚焦最终回归另有 86 passed、exit 0，原始输出 `/private/tmp/dayu-upload-s1-fix-focused-3.log`。其原始命令为：

```bash
source .venv/bin/activate && python -m pytest tests/fins/test_upload_usage_contract.py tests/fins/test_upload_asset_plan.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py::test_validated_material_handoff_rejects_cross_field_drift tests/cli/test_fins_commands.py::test_upload_material_cli_names_conflicting_basename_without_path tests/fins/test_sec_pipeline_upload_material_stream.py::test_material_101_rejected_before_sec_pipeline_dependencies tests/fins/test_sec_pipeline_upload_material_stream.py::test_sec_material_sync_delegate_admits_once tests/fins/test_cn_pipeline.py::test_material_101_rejected_before_cn_hk_pipeline_dependencies tests/fins/test_cn_pipeline.py::test_cn_material_sync_delegate_admits_once tests/fins/test_fins_service_runtime.py::test_production_runner_preserves_material_handoff_identity tests/service/test_fins_direct.py -q
```

真实 CLI 回归命令：`python -m dayu.cli upload_material --base /private/tmp/dayu-upload-s1-fix-cli/workspace --ticker AAPL --action create --forms MATERIAL_OTHER --material-name Deck --company-name 'Apple Inc.' --files /private/tmp/dayu-upload-s1-fix-cli/one/deck.pdf /private/tmp/dayu-upload-s1-fix-cli/two/deck.pdf`。两个实际普通文件同 basename，exit 2；stdout 空，stderr 精确为 `dayu-cli upload_material: 原件文件名重复：deck.pdf；请重命名后重试`，无绝对路径；隔离 workspace 文件树为空。原始输出分别在 `/private/tmp/dayu-upload-s1-fix-real-cli.stdout`、`/private/tmp/dayu-upload-s1-fix-real-cli.stderr`。本次只改变前置拒绝和文本，未复跑真实 Docling 转换。

## 环境偏差与剩余风险

- `.venv/lib/python3.11/site-packages/dayu_shared_dependencies.pth` 仍在，本次验证复用主仓 site-packages；不代表独立依赖安装验证。pyright 运行时提示有新版本 v1.1.414，当前实际版本 v1.1.409。
- 本次测试证明手工构造的矛盾 handoff fail closed，但不改变 admission 后外部文件替换的 TOCTOU 边界；storage 完整性检查继续承担最终防线。保守 NFC/casefold/NFC 键、目标卷可能低于 255 字节的文件名上限、O25 primary、O34 company meta 时序及 O16 delete+files 规则仍按 accepted plan/裁决保留。
- 当前只有 MiMo 旧候选版 review 与本次裁决；修复后的精确 diff 尚未获得 Kimi/MiMo 同版 re-review，因此不宣称 code gate 通过。
