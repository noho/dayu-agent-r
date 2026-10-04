# UM-O04/O23 S1 code review F8 修复记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-730be507

## 预检、动机与 owner

- 工作区 `/private/tmp/dayu-upload-assets`，HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`。实施前 tracked `git diff --binary` SHA-256 为 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`；`tests/fins/test_upload_asset_plan.py` 原文 SHA-256 为 `0e4fc501016f8eac9105542e6e907089aee6e8db9d69373b6a829a70d54f0143`。三项均与任务锁定值一致。
- 已读 `AGENTS.md`、accepted plan `docs/gateflow/upload-material-assets-plan-20260929.md`、总控裁决 `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md`、MiMo review `docs/reviews/code-review-20260929-130410.md`、planner 及 owner 测试。F8 动机成立但严重度低：同批长非法名与 `META.JSON` 的 reason 随顺序翻转，违反已接受的控制名分类顺序无关承诺；两序原本均在转换前拒绝，未见发布损坏证据。
- 控制名集合和保守比较键的真源在 storage 纯契约；**整批规划失败 reason 的唯一 owner** 是 `dayu/fins/upload_asset_plan.py`。裁决优先级：现有数量、规范路径、重复 basename 前置检查不变；随后整批可判定控制名优先；其后非法资产名；最后业务资产碰撞。没有改公开 reason、storage、filing、CLI/tool 或 action 语义。

## 修改

- planner 在单次 material 规划内保存第一个非法名，继续扫描其余可判定的控制名。控制名命中立即报封闭 `RESERVED_CONTROL_NAME`；扫完后若有非法名才报 `INVALID_ASSET_NAME`；仅在这两类都没有时检查业务资产碰撞。非法组件无法安全生成 storage 比较键时不猜测其控制名，记录为非法并继续扫描其它名字；若没有其它控制名，仍 fail closed。UTF-8 编码失败也走封闭非法名原因，不透传异常。
- `tests/fins/test_upload_asset_plan.py` 的 owner 矩阵加入 `("a" * 243 + ".pdf", "META.JSON")` 正逆序，两序均断言 `RESERVED_CONTROL_NAME`、异常不含绝对路径，且规划拒绝后隔离工作区为空。planner 是纯规划函数，不持有 converter 或仓储发布接口；拒绝不返回 selection/plan，故两序均在转换与发布前结束。原有单独超长名仍断言 `INVALID_ASSET_NAME`，R1 的 RESERVED×业务碰撞正逆序仍保留。
- 仅编辑上述生产文件与 owner 测试，并新增本记录。按 `dayu/fins/README.md` 的 Agent 更新约束和 `tests/README.md` 的测试层级职责核查：本修复未改变公开能力、稳定边界、测试层级、运行方式或维护约定，因此未改 README。

## 验证命令与结果

所有命令均在该 checkout 运行，均 exit 0；没有失败命令。虚拟环境 Python 为 3.11.15，site-packages 复用主仓路径，未进行独立依赖安装验证。

| 命令 | exit | 结果 |
| --- | ---: | --- |
| `git rev-parse HEAD` | 0 | 预检 HEAD 匹配。 |
| `git diff --binary \| shasum -a 256` | 0 | 修改前及修改后均为 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`；两个编辑文件仍未跟踪，此摘要不覆盖它们。 |
| `shasum -a 256 tests/fins/test_upload_asset_plan.py` | 0 | 修改前 `0e4fc501016f8eac9105542e6e907089aee6e8db9d69373b6a829a70d54f0143`。 |
| `source .venv/bin/activate` 后运行 `python -m pytest tests/fins/test_upload_asset_plan.py -q --cov=dayu.fins.upload_asset_plan --cov-report=term-missing --cov-fail-under=80` | 0 | 15 passed；该生产文件 147 statements、21 missed，85.71%（展示为 86%），达到单文件 ≥80%。 |
| `source .venv/bin/activate` 后运行下列相邻矩阵 pytest 命令 | 0 | 1212 passed、1 skipped、3 条第三方 edgar deprecation warnings；40.35 秒。 |
| `source .venv/bin/activate` 后运行 `python -m pyright` | 0 | 0 errors、0 warnings、0 informations；另有版本更新提示。 |
| `git diff --check` | 0 | tracked 工作树无空白错误。 |

相邻矩阵精确命令：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_upload_failure.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_service_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_fins_commands.py -q
```

## 候选指纹与剩余边界

以下为本记录写入前 `git ls-files --others --exclude-standard -z` 所列既有未跟踪文件的内容 SHA-256；工作区原有 tracked diff 不因本次未跟踪文件编辑而改变。本记录自身为新增未跟踪文件，内容摘要是此 F8 的预检、owner 修改、验证与候选指纹；其最终 SHA-256 应在写入后从工作区另行计算。

| 未跟踪文件 | SHA-256 |
| --- | --- |
| `dayu/fins/storage/asset_filename_contract.py` | `c2c91eeebb8cc5f16a6aea3f72db916102addf1228282c35ecd7994655eb706f` |
| `dayu/fins/upload_asset_plan.py` | `3ad3d8551a1c94eec27b6f5b6180bf9264cf3e35e9f5ea40136d1c136f6a4780` |
| `dayu/fins/upload_usage_contract.py` | `64e5b33a7f907d3b604f3a9efd341b1849b5f9ac8615da1feab13c7e29ae8659` |
| `docs/gateflow/upload-material-assets-s1-code-rereview-r1r2-fix-20260929.md` | `32bd5870fb67d453466729eb670f2ad1d8d2eed34ce6c36c04030f83e54e837f` |
| `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` | `594b8c6d7b9f4b0f5de79e2921a48874d01a78e51b0da99c92c3be60901e0ec7` |
| `docs/gateflow/upload-material-assets-s1-code-review-fix-20260929.md` | `1db5c6ceb204d1ef4d4762373b9ca52a5b88b1c8579a2e429931be5a3670df8f` |
| `docs/gateflow/upload-material-assets-s1-code-review-fix2-20260929.md` | `82dc79d8666d61f33f62224e833eef744ae493251b5c167fe1259f743c5908d0` |
| `docs/gateflow/upload-material-assets-s1-implementation-20260929.md` | `010a845f070756cf9d8f60ebbcb4c0c4800611761fe9e5e5c1cfeb1b1ef1040a` |
| `docs/reviews/code-rereview-assets-s1-mimo-20260929.md` | `936af67004090e0f3aae6a9ff67d3bc85519808a9c5c9d38d2b2ec7cc7b9afdc` |
| `docs/reviews/code-review-20260929-114318.md` | `3c5609bdb875e566365f9e25aaf2ef955804a964d7804c6f6577317f1c33eb46` |
| `docs/reviews/code-review-20260929-130410.md` | `64de4b21db317a9b7312b62c4716cc9863b52977c58b7d7ee84f698c76469866` |
| `tests/fins/test_storage_asset_filename_contract.py` | `c5723c7016199b0dd132b77f42d5eb01980b158da1f38ca3242ef85ca5a5d534` |
| `tests/fins/test_upload_asset_plan.py` | `c151535fed72342a801c367a9099e84d8991167ec9dec9b3a39f1f6fabef5225` |
| `tests/fins/test_upload_usage_contract.py` | `2ff264cd6c75372dfd9cef58bcef9e15549718c00ec968a3ebd1489f748d7116` |

本轮没有重新跑真实 CLI 的混合批次，因为非法长名在目标文件系统上不能创建为真实文件；owner 纯规划路径可直接接收该名字并在读文件或转换之前拒绝。已有全量矩阵覆盖现行 CLI、tool、filing 与 publication 行为，但不能替代后续总控锁定新候选后的双路同版 review。未 commit、push、PR 或派发 Agent。
