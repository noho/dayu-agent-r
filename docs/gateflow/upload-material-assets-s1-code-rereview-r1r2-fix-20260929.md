# UM-O04/O23 S1 MiMo re-review R1/R2 owner 测试修复

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-a6078e2d

## 基线与范围

- 工作区：`/private/tmp/dayu-upload-assets`；HEAD：`1453a659a79d4c9a93838412dfdecfa7feeddf98`。
- 修改前 tracked `git diff --binary` SHA-256：`07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`，与任务锁定值相同。
- 已读 `AGENTS.md`、`docs/gateflow/upload-material-assets-plan-20260929.md`、`docs/reviews/code-rereview-assets-s1-mimo-20260929.md`、`docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` 最新节。R1/R2 是现行行为正确、但 owner 回归锚缺失的低风险测试问题，动机成立。语义 owner 分别为 material `plan_upload_assets` 的整批 reason 分类、Fins usage 的完整文案投影。
- 只修改 `tests/fins/test_upload_asset_plan.py`、`tests/fins/test_upload_usage_contract.py`，并新增本记录；未修改产品代码、其它测试、README 或裁决。`tests/README.md` 已按其更新约束核查：未新增测试层级、运行方式或维护规则，故不更新。

## R1/R2 修复

- R1：在规划 owner 现有参数矩阵加入 `a.txt`、`a.txt_docling.json`、`META.JSON` 的正序与逆序。两序均通过公开 `plan_upload_assets` 路径断言 typed `RESERVED_CONTROL_NAME`，并沿现有测试检查异常不含绝对路径；这直接锁住控制名优先于业务资产互撞的输入顺序无关性。
- R2：新增长多字节 basename 与 Cc 文件名两组。均从公开 `plan_upload_assets` 取得 typed error，再经 `fins_upload_asset_plan_usage_failure` 和 `fins_upload_failure_from_exception` 检查 closed reason/code、同源完整文案与 retry hint。长 `"名" * 230 + ".txt"` 被规划为 `INVALID_ASSET_NAME`，usage 恰为 240 个 Python 字符，省略号前有首部、后有 `.txt` 与可修正提示；两个目录中同名 `"隐\x01藏.txt"` 被规划为 `DUPLICATE_ORIGINAL_BASENAME`，完整文案包含 `输入文件（文件名已隐藏）`。两组均检查长度不超过 240、不含绝对路径；typed 异常和成功完成的投影也锁住裸抛回归。
- 两项测试走真实公开 owner 调用路径；没有复制私有裁剪算法或修改 fixture 来制造结果。

## 命令与退出状态

以下命令均在本 checkout 运行；非零命令保留原样，不用后续绿测抵消。

| 命令 | exit | 结果 |
| --- | ---: | --- |
| `git rev-parse HEAD` | 0 | 与锁定 HEAD 一致。 |
| `git diff --binary \| shasum -a 256`（修改前） | 0 | 与锁定 tracked SHA 一致。 |
| `cat AGENTS.md; cat docs/gateflow/upload-material-assets-s1-plan.md` | 1 | `cat: docs/gateflow/upload-material-assets-s1-plan.md: No such file or directory`；后以实际文件名 `upload-material-assets-plan-20260929.md` 读取。 |
| `test -f .venv/bin/activate && test -x .venv/bin/python && test -x .venv/bin/pyright` | 1 | 误假设 pyright 可执行文件在 `.venv/bin`；激活后的 `pyright` 实际为 `/opt/homebrew/bin/pyright`，本 checkout 的 Python 为 `.venv/bin/python`。 |
| `sed -n '1,80p' docs/gateflow/upload-material-assets-code-review-fix-20260929.md` | 1 | `sed: docs/gateflow/upload-material-assets-code-review-fix-20260929.md: No such file or directory`；误用路径，非验证命令。 |
| `source .venv/bin/activate; command -v python; command -v pytest; command -v pyright; python --version; pyright --version` | 0 | Python 为本 checkout `.venv/bin/python`，版本 3.11.15；pyright 1.1.408。 |
| `source .venv/bin/activate; python -m pytest tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py -q` | 0 | 26 passed。 |
| `source .venv/bin/activate; pyright` | 0 | 0 errors、0 warnings、0 informations。 |
| `source .venv/bin/activate; python -m pytest tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py -q` | 0 | 571 passed；3 条第三方 `edgar` deprecation warnings。 |
| `source .venv/bin/activate; python -m pytest tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py -q --cov=dayu.fins.upload_asset_plan --cov=dayu.fins.upload_usage_contract --cov-report=term` | 0 | 571 passed；`upload_asset_plan.py` 90%、`upload_usage_contract.py` 94%；同样 3 条第三方 warning。 |
| `git diff --check` | 0 | tracked 工作树无空白错误。 |

## 指纹、验证界限与残余

- 修改后 tracked `git diff --binary` SHA-256 仍为 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`。原因是本次两份测试在修改前后均为未跟踪文件；此 tracked SHA 不覆盖它们，也不覆盖本记录。供后续 review 锁定内容的 SHA-256：`tests/fins/test_upload_asset_plan.py` 为 `0e4fc501016f8eac9105542e6e907089aee6e8db9d69373b6a829a70d54f0143`；`tests/fins/test_upload_usage_contract.py` 为 `2ff264cd6c75372dfd9cef58bcef9e15549718c00ec968a3ebd1489f748d7116`。
- 本轮未修改生产文件，故未重跑先前 19 个生产文件的逐文件 coverage；只对两项相关 owner 取 90%/94% 覆盖。未重跑真实 converter、完整发布或全部测试矩阵；本轮是 owner 测试增量，不把既往真实 CLI 证据升格为当前候选的新运行结果。
- 本 checkout 的 `.venv` Python 可用，但 site-packages 复用主仓路径；这不是独立依赖安装验证。MiMo 旧 re-review 与本轮测试变更不是同一内容指纹，仍需总控按新候选安排有效复审；code gate 未由本记录宣告通过。
