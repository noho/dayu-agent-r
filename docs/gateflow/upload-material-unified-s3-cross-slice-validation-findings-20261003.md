# S3 最终源码跨 slice 回归：测试迁移收尾登记

## 实际验证

根总控在S3 focused re-review期间，针对最终源并行执行42文件测试并集（S1/S2/S3真实命令票据去重），不推进aggregate gate。managed session27562已actualouter1，collector真实waittrue/exit1；84项源码/配置清单逐SHA核验无漂移；原Raw保于 `workspace/tmp/upload-material-unified-repair-20261002/s3-final-source-union-01/`。实际2834passed/7failed/3skipped/3旧edgartools warnings，240.60s。全38修改生产文件均≥80（精确值/root外部五用例结果见root-readback.json）。五个外部XBRL正/负用例均真实passed，未跳过；当前不能把整体回归写pass。

## US3-T03 — accepted / 未修复：旧转换器测试注入位置未跟随装配 owner

直接证据：tests/fins/test_fins_ingestion_tools.py:3651/3706的两个测试仍patch `dayu.fins.pipelines.docling_process_converter.ProcessDoclingConverter`。S3新增 `docling_converter_factory.py`在模块首部直接导入该class，并由DefaultFinsRuntime.get_ingestion_runtime在service_runtime.py:483-485调用create_docling_converter，再共享传给SEC/CN/HK runner。因此原patch没有影响工厂已绑定符号；六个用例converter.calls=[]，而真实生产转换正常到达：坏docx是正确execution失败、正常txt发布成功。

owner：测试的受控转换结果注入。修复应迁移到实际工厂消费的constructor/明确既有测试注入边界，继续真实准入/市场runner/仓储/observation/job；不得为旧patch改生产import、补shim/注入参数或删调用次数/失败同源断言。不把受控测试称真实Docling正例。scope仅该现有tests文件及必要testsREADME职责说明，无产品语义修改。

## US3-T04 — accepted / 未修复：schema断言固化了旧句子相邻顺序

直接证据：tests/fins/test_fins_ingestion_tools.py:2175-2181把原material JSON/XML候选说明与delete规则拼成连续字符串。S3正确唯一投影owner upload_format_contract.py在XML候选与delete之间新增“XBRL转换需要管理员完成受控部署配置”，因此连续substring断言失败；同测试更早已assert files_schema.description==FINS_UPLOAD_FORMAT_TEXT.upload_tool_files，生产CLI/tool共享真源一致。

owner：测试对业务可读语义的断言。逐语义事实验证（保全部现有候选/不保证转换/DoclingJSON/XML非任意内容/delete事实，补受控配置说明），不固化无关句子相邻性、不删核心断言、不改owner文案绕过测试。

## 裁决与下一入口

这是S3装配/文案改动的两处测试迁移遗漏，7失败合并为同一集中收尾，不新WU、不新slice。先取得在途MiMo旧版复审终态与核收，防改冻结输入；随后gpt-6-sol一次修全部T03/T04并验证完整该tests文件/full pyright，三项原R01/R02/D01源字节不变可继承同源复审，两个新项必须同版MiMo/ds-flash复审后方可S3 checkpoint。其余41文件仅在源码/测试SHA完全不变且JUnit确无失败时继承此次实跑，保整轮failed事实；不把不同版本拼成单次绿色运行。若需最终整体单次绿，在aggregate明确针对剩余风险再跑，而不是每轮默认重复大suite。

Raw EOF收口仍全部slice后已批准aggregate/PR证据资产owner；Linux/Windows延期；抽取质量Docling#4437；完整CLI/registry仍WU完成后独立阶段。当前gate仍re-review S3旧版进行中，新增T03/T04未修，不允许最终通过。原根/子报告历史状态保持；本artifact追加实际失败事实。
