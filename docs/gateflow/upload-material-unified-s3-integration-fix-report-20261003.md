RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-67b1c15c

# S3 T03/T04 集中测试迁移修复报告

label: upload-material-unified-s3-integration-fix-sol-20261003-01<br/>
gate: fix S3 T03/T04（已有 S3，不新增 WU/slice）<br/>
codex 为本轮 runtime，gpt-6-sol 为派发 provider 声明；可读取的实际事件未暴露模型名，MODEL=unknown。CANARY 逐字来自本轮指定文件的工具读取，不以 CANARY 推断模型。

## 根因、owner 与修改

动机成立：旧最终源码 42 文件实跑 2834 passed / 7 failed / 3 skipped、actual_wait=true / actual_exit=1，七个失败均在目标测试文件。直接依据为 docs/gateflow/upload-material-unified-s3-cross-slice-validation-findings-20261003.md；旧六项双审根核收为 docs/gateflow/upload-material-unified-s3-focused-rereview-root-adjudication-20261003.md。只修测试迁移，不重新裁决业务规则。

| Finding | 最终状态 | owner 与具体 diff |
| --- | --- | --- |
| US3-T03 | 已修复，待总控复审 | 受控 converter outcome 注入属于测试；两个 patch 目标改为真正被工厂消费的 dayu.fins.pipelines.docling_converter_factory.ProcessDoclingConverter。工厂 create_docling_converter 仍真实执行配置校验，DefaultFinsRuntime.create 只有 workspace_root，三市场 runner/准入/Fs/observation/job 均真实。 |
| US3-T04 | 已修复，待总控复审 | 唯一文案投影 owner 仍为 upload_format_contract.py；原四句连续 substring 改成四个独立事实断言，再补完整管理员受控配置及未配置/坏配置失败提示，不固化无关句子相邻性。 |

目标文件仅三个 hunk（diff 原始行号 2172、3648、3703）。_S1ContentConverter 的既有类型协议及全部业务断言保留：调用次数、零发布、company 独立、observation/job 五字段同源和双摘要。受控 converter 不冒称真实 Docling 正例。files_schema.description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files、material/primary 共享真源断言、全部候选/不保证转换/非任意 JSON 或 XML/delete 事实保留。expected 为明确语义字面量，不从 actual 复制。

精确 diff：workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/changes.diff<br/>
diff SHA256: 2bae545b8d66528585548730daf85e82b1542003c6088f5df3777ed12074a3a0<br/>
test before SHA256: 7b49bb082b3060c4b9b95c284225fea2bcc62a129e32bc5e0136449fa3f76368<br/>
test after SHA256: 4c8545d32c8b6e9f2d3e3ee169a738f727eb0e0e04e8ddf9540ca7171a8d0ea4

生产源码、README、依赖、旧 Raw、控制面/冻结输入均未修改，不新增生产注入参数、兼容 import/shim 或 fallback。

## 本轮验证与 sourceSHA

原字节复制既有 typed collect-v2.py，SHA256 9198c023a69754e7a20f187efab9e62adf8ce4ea25eec556cec02787ff752f48。没有新采集/验签框架。两次验证均先 source .venv/bin/activate，采集器使用 .venv python，真实 child.wait() 和退出码、stdout/stderr、command.json 均保存在独占目录。

84 项 source-final-v2.json SHA256: e47e6373be4a195e9587b308293891a25df07e8cbbdf9024ab7fbe7f76e748dc<br/>
仅目标测试 SHA 更新，其余 83 项逐 SHA 不变。旧六项 scope SHA 6aae2616a06581a2439bd3b396ce8da8c17b1c1884fddc6d72715f3b9528333f 按原根核收承接，不重复旧裁决。

完整目标文件测试 argv（不是仅七失败）：
~~~sh
workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python -m pytest tests/fins/test_fins_ingestion_tools.py -q --basetemp=workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/pytest-temp -o cache_dir=workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/pytest-cache --junitxml=workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/junit.xml --cov=dayu --cov-report=json:workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/coverage.json
~~~
实际采集器调用：.venv/bin/python workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/collect-v2.py workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/tests-full-file-01 <上述 argv>。
环境实际值见 tests-full-file-01/command.json：独占 basetemp、pytest cache、COVERAGE_FILE、JUnit、双流、TMPDIR、XDG_CONFIG_HOME、XDG_CACHE_HOME；PYTHONDONTWRITEBYTECODE=1 防止改写冻结运行库字节。

结果：144 passed / 0 failed / 0 skipped，3 条既有 edgartools DeprecationWarning。JUnit 144 个 testcase 均无 failure/error/skipped；原七个失败名称均在本轮通过。actual_wait=true / actual_exit=0；duration_wall_s=19.71977137500653。
JUnit SHA256: 45ec699931de9ced2adc617a3b05facd7fb2140a623144ffedaa962f3407d884<br/>
本轮 coverage SHA256: 5e614a3d14c1ddee20914ebbd8d8fd5aaf59b384ac1d9aea2d00b4ac760b57a3（只记录单文件执行，不替代旧并集逐生产文件覆盖）。

全量类型检查 argv：
~~~sh
/Users/leo/workspace/dayu-agent-r/.venv/bin/python -m pyright
~~~
实际采集器调用：.venv/bin/python workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/collect-v2.py workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/pyright-full-01 <上述 argv>。
结果：0 errors, 0 warnings, 0 informations；actual_wait=true / actual_exit=0；duration_wall_s=38.1040159999975。stdout 另有 pyright 版本升级提示，没有升级依赖。

tests-full-file-01/receipt.json SHA256: d89a52f483783624c5e7444d2ac6026bf8559832381561bf94269e7e35ad42d4<br/>
pyright-full-01/receipt.json SHA256: 0a282b90257d5cf6cd547029f4c1881fa11eb61908df6e32a0db7c4449d50c12<br/>
两份 receipt 与实际 command/source manifest/双流逐 SHA 核验；validation-readback.json 保存原七个失败本轮通过名称。git diff --check -- tests/fins/test_fins_ingestion_tools.py 实际退出 0。没有末尾 echo0 或管道伪造退出码。

## 旧证据按精确 SHA 承接

workspace/tmp/upload-material-unified-s3-integration-fix-sol-20261003-01/inherited-evidence.json SHA256: 09e56582964f771c63f79fcecbbcf78b2b7507cdfa24075a953bb6530afa4df1。
该票据列出原 41 未变测试文件逐 SHA、38 修改生产文件逐 SHA 及原覆盖、原外部 XBRL 正例/四负例及旧 Raw/source/JUnit/coverage 精确 SHA。原 JUnit 七失败全部在本轮唯一可改文件，其他 41 文件无失败。38 项覆盖均 ≥80，最低 84.82587064676616%；外部正例与四负例均实际 passed，无 skip。

旧 source manifest SHA256 8f3145364449fe0d7c7e9d60f4b6b944b8c5de894ee3d9d0a46dd04d4566f27f 与冻结 source-before 同版。保留旧 actualwaittrue/exit1、2834/7/3 与原 Raw/source/JUnit，不冒新整轮绿色执行，不把两版本拼成一次 42 文件绿色。未重跑宽回归、安装、边界矩阵、内核验收或完整 CLI campaign。

## 起末保护、docs decision 与恢复

起始 12376 项 input、12375 项 protected 均零漂移；结束 input 仅授权测试改变，12375 项 protected 零漂移，其中 472 项 dayu 文件均字节不变。五个冻结清单自身 SHA 均不变；workspace/branch/HEAD/main 与冻结一致。scan-start.json/scan-end.json 保存全部扫描结果，新增 repo 变更仅目标测试和本报告，其他新票据仅独占目录。

docs decision：已读 tests/README.md 的职责定义（已有测试分层、运行方式和维护约定，新增层级才同步）。本轮是已有 fixture 注入和断言迁移，无新层级/产品行为/用户工作流，无需 README 更新，且 README 不在写白名单。

产品测试和 pyright 无失败、无重跑。辅助读回第一次错误地把 XBRL 文件全部 10 用例当作外部 5 用例，AssertionError / 实际工具 exit=1。原工具结果与合并输出保存在 evidence-readback-01-failed/tool-result.json 和 combined-output.txt；工具仅返回合并输出，无法恢复独立原 stdout/stderr，限制明确保存于 stream-availability.json，不伪造双流/actual_wait。恢复在新 evidence-readback-02 由原 collector 保存原始 argv、双流、actual_wait=true / exit=0，按正例名称与四负例前缀筛选，并验证名称集合等于旧 root-readback。产品验证证据不受影响，旧票据未改。

首次报告生成调用因 JavaScript 模板内反引号导致执行前 SyntaxError，未启动进程/结束扫描；原错误保存在 delivery-01-tool-syntax-failed/tool-result.json，无 shell exit 或进程双流可声称。恢复采用新 end-scan-and-delivery-02 采集器目录执行一次结束扫描。初次只读目录枚举展示截断，后续定点读取恢复；不以截断内容作核验依据。

## 分类 residual 与停止状态

- fixed in current slice：US3-T03/T04 测试迁移遗漏已修复，待总控复审；owner：测试修复/总控。
- covered by later approved slice：Raw EOF 收口仍在全部 slices 后的既有 aggregate/PR 证据阶段；owner：总控。
- assigned to later work unit：Linux/Windows 验收沿用既有延期；完整 CLI campaign/正式 registry 仍在修复 WU closeout 后既定阶段；owner：总控，沿用既有决定。
- tracked by existing issue：抽取准确性归 Docling，上游 Docling#4437；不新增 parser/质量门槛；owner：Docling。
- requiring new issue or explicit user decision：首次辅助读回仅工具合并输出，原独立双流不可恢复；恢复票据完整，产品验证不受影响。总控复审裁定该证据限制及既有依赖提示；owner：总控。

本轮实现验证成功信号已达到。完成后停止，由总控复审；不自行给 S3/slice pass，不进入其他 gate，不派发子 Agent，不 commit/push/PR/merge。
