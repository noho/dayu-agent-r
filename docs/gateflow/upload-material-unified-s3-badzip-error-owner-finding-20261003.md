# US3-C01：坏 ZIP 容器越过配置错误 owner

## 直接证据

root 在独占 /private/tmp 合成管理员配置，完整文件大小/SHA和manifestSHA匹配，只有 ZIP 容器字节非法；调用公共 create_docling_converter 实际抛 zipfile.BadZipFile，无 __cause__，而非约定 DoclingConversionError(CONVERTER_CONSTRUCTION)。原票据 `workspace/tmp/upload-material-unified-repair-20261002/s3-inflight-root-audit-20261003/badzip-public-factory.json` 绑定两owner源码SHA及输入根。只是配置错误反例，不冒真实财报正例。

源码同源：Documents._verify_archive 直接 ZipFile/open；BadZipFile 直接继承 Exception，不在 load/prepare/verify 的 (OSError, ValueError, KeyError) 归一集中；factory 只捕获 XbrlConfigurationError。因此静态坏配置不能按已接受 CONVERTER_CONSTRUCTION 合同到达消费者，parent prepare也可能将其误分IPC。

## 裁决与修复边界

accepted，未修复，本S3必须修。语义owner为Documents配置/ZIP校验，须在那里把实际坏ZIP容器/CRC错误转为XbrlConfigurationError并保原cause，既有factory/parent/worker投影复用；不得下游 catch BadZipFile 逐入口补偿，不新公开error code，不扩大goal。补实际owner及factory反例，必要复验后纳最终受影响测试/全量类型/同版双审。原成功及失败票据不覆盖。分类：fixed in current slice 的 required fix；不会切新slice。
