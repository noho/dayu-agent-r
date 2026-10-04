# O04/O23 S1 F14 修复记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-9c18e1c9

## 锁定与动机

- 工作区 `/private/tmp/dayu-upload-assets`；编辑前 HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`，tracked `git diff --binary` SHA-256 `07b0df8c06253c64431316ac32b11d540df8b182861e7112d9fd417c8b3a60bf`，未跟踪 planner SHA-256 `707d12a79c5cec4c97047749bc68bd0593a6e93adb39249aeac751bd791be7fc`，均一致。
- 已读 AGENTS、accepted goal/plan、总控裁决末节、F12/F13 记录，以及真实 usage owner、admission、tool 与测试。F14 动机成立：admission 已产生 `FinsUploadUsageFailure(code, message)`，tool 却检查 `exc.__cause__` 来决定公开 error。相同 fact 可因重抛历史不同而改变 tool 结果；cause 不是业务分类真源。
- 本轮只处理 F14；不改文件状态预检、不实施 O05/O16/O25、不提交或推进 PR。F1–F13/R1/R2 仍为待总控最终同版复审的候选。

## Owner 与改动

- `dayu/fins/upload_usage_contract.py` 在 typed usage fact 增加 `REQUEST` / `ASSET_PLAN` 封闭类别。普通请求工厂保持 `REQUEST`；唯一 planner reason 投影产生 `ASSET_PLAN`。fact 校验类别类型和规划类别与 closed code 的对应，允许 `MISSING_FILES` 等已有 code 在两个类别共用，不复制 reason→code 表。
- `dayu/fins/tools/upload_tools.py` 只读取 fact 类别：规划错误继续使用规划 public code，filing/ticker 等普通 usage 继续使用 `invalid_argument`。message 和既有 hint 保持同源及原值；tool 不再 import planner error 类型或读取 exception cause。
- owner 测试覆盖所有规划 reason 的类别、共用 code 的两个类别和不合法 fact 组合。真实 tool callable 测试用实际 admission 产生的同一 fact，分别保留与去除 cause，断言 error/message/hint 完全一致、零 job/observation；原有真实 JSON 路径失败和文件状态预检测试继续运行。
- 按 README 职责更新 `dayu/fins/README.md` 和 `tests/README.md`；根 README 的最终用户流程没有变化。

## 验证与限制

- 虚拟环境下聚焦 owner/tool 用例：30 passed。受影响五文件与 coverage：691 passed；`upload_usage_contract.py` 95%，`upload_tools.py` 94%，逐文件均超过 80%。coverage 先加载已有 processor registry，避免该共享虚拟环境在测试收集时重复加载 NumPy C 扩展；没有修改产品环境或依赖。
- 虚拟环境下上传相邻矩阵：1515 passed、1 skipped；三条 edgar 第三方 deprecation warning。`python -m pyright`：0 errors、0 warnings、0 informations；工具另提示可用较新版本。`git diff --check` 通过。
- 本轮无失败命令或工具调用。没有重跑真实 Docling 完整发布；本项针对失败分类，真实 tool JSON 与相邻转换/CLI 测试覆盖其边界。

## 最终内容锁

- HEAD：`1453a659a79d4c9a93838412dfdecfa7feeddf98`。
- tracked `git diff --binary` SHA-256：`05d8977450722aa7cefbd51607ceec14721a1301b7d109ab4e98d46213b6c14b`。
- 下表列出除本记录外的全部未跟踪文件；本记录自身 SHA-256 在交付报告列出，避免自引用。

| SHA-256 | 未跟踪文件 |
| --- | --- |
| `c2c91eeebb8cc5f16a6aea3f72db916102addf1228282c35ecd7994655eb706f` | `dayu/fins/storage/asset_filename_contract.py` |
| `707d12a79c5cec4c97047749bc68bd0593a6e93adb39249aeac751bd791be7fc` | `dayu/fins/upload_asset_plan.py` |
| `eac24f88fc6de8b8bd99811ce2e2042ff1cdd663e434d0ad417524e864bd532e` | `dayu/fins/upload_usage_contract.py` |
| `32bd5870fb67d453466729eb670f2ad1d8d2eed34ce6c36c04030f83e54e837f` | `docs/gateflow/upload-material-assets-s1-code-rereview-r1r2-fix-20260929.md` |
| `65ebb9e3e8d41d2db7d438668a8c793908cebcd6b73512814847fd651d72f9c7` | `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` |
| `d5f91457ba73184933339afcae939adda0383a3f3a0570d15e7339f1c855b80d` | `docs/gateflow/upload-material-assets-s1-code-review-f12f13-fix-20260929.md` |
| `6771d1767cb7d841e8284cdae1f39c454f714690a29238f338bce6f1852bab06` | `docs/gateflow/upload-material-assets-s1-code-review-f8-fix-20260929.md` |
| `5dbfdbc7d5a0da5a80e752412737fdf9464372249b760269adfe72cdfb5ff00a` | `docs/gateflow/upload-material-assets-s1-code-review-f9f11-fix-20260929.md` |
| `1db5c6ceb204d1ef4d4762373b9ca52a5b88b1c8579a2e429931be5a3670df8f` | `docs/gateflow/upload-material-assets-s1-code-review-fix-20260929.md` |
| `82dc79d8666d61f33f62224e833eef744ae493251b5c167fe1259f743c5908d0` | `docs/gateflow/upload-material-assets-s1-code-review-fix2-20260929.md` |
| `010a845f070756cf9d8f60ebbcb4c0c4800611761fe9e5e5c1cfeb1b1ef1040a` | `docs/gateflow/upload-material-assets-s1-implementation-20260929.md` |
| `936af67004090e0f3aae6a9ff67d3bc85519808a9c5c9d38d2b2ec7cc7b9afdc` | `docs/reviews/code-rereview-assets-s1-mimo-20260929.md` |
| `3c5609bdb875e566365f9e25aaf2ef955804a964d7804c6f6577317f1c33eb46` | `docs/reviews/code-review-20260929-114318.md` |
| `64de4b21db317a9b7312b62c4716cc9863b52977c58b7d7ee84f698c76469866` | `docs/reviews/code-review-20260929-130410.md` |
| `d7585ffa3f0783e30e4076ee51d03e7383e46bf22f6df2ec66dc2d208578fa2e` | `docs/reviews/code-review-20260929-133817.md` |
| `7632acd85e32e733d887bccf2dbe8d6d7600869dbc210c16b30da8be9d8b19d9` | `docs/reviews/code-review-20260929-142240.md` |
| `c5723c7016199b0dd132b77f42d5eb01980b158da1f38ca3242ef85ca5a5d534` | `tests/fins/test_storage_asset_filename_contract.py` |
| `2ac85fe123eef78c7226159a47a43a6b6706fc4528cc5d089e0f4fee712bafec` | `tests/fins/test_upload_asset_plan.py` |
| `c0ea2c8e204ed9bea25a45378c051ce09c45b4baada11815f134db7fe4d45ff5` | `tests/fins/test_upload_usage_contract.py` |
