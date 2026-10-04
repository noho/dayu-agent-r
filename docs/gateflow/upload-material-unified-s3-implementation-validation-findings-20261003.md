# S3 实施期验证登记

## US3-T01：转换成功收口变量可能未绑定

- 直接证据：`workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/pyright-first/stdout`，首次全量 pyright 报 `docling_process_converter.py:563:37` 的 `output_path` possibly unbound；真实等待 PID48038，exit1。原失败票据保留。
- owner：Fins ProcessDoclingConverter 请求独占输入/输出与成功收口；只能该 owner 内保证已建立输出路径，不能 consumer fallback 或关闭类型检查。
- 状态：实施 Agent 已修改，仍待修后全量 pyright、受影响 owner tests、同版双审及 root 裁决；未登记为 accepted/pass。
- 分类：fixed in current slice 的实施修复候选；当前 S3 完成前必须验证。没有新增业务语义、slice 或目标。

## 总控任务引用错误

“V15–V20”不存在，独立裁决 `upload-material-unified-s3-task-reference-correction-20261003.md`；按真实 accepted plan §7/§8/§9，不创造六项规则。

当前 gate：implementation S3；后续 S3 code review/fix/re-review/checkpoint。

## US3-V02：CN pipeline 逐文件覆盖门槛尚未满足

- 真实 final-regression-command exit0，445passed/1skipped，但 final-coverage.json 的 cn_pipeline.py 只有 67.5381%，低于已接受80%门槛；全包86%不能抵扣。
- 状态：required validation gap，当前S3集中关闭；不是新业务finding、slice或goal。
- 可以只读执行现有 tests/fins/test_cn_download_runtime.py 加入实际受影响回归/覆盖，使用本轮独占 cache/basetemp/coverage；此测试文件是保护输入，不需要也不授权修改。保其它原测试/失败票据；仅根据实际覆盖与最终源码绑定报告，不能伪造代码未执行的覆盖。
