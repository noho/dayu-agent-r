# US3-C01 补证：不支持的 ZIP 压缩方法

原始finding保持原字节与原SHA，本文补充同一owner输入反例，不新增slice或目标。

## 同一 owner 的第二个已复现异常（同项集中修，不新切片）

root又通过公共factory复现：合法ZIP索引、完整文件及成员size/hash声明，但使用stdlib不支持的压缩方法时原始NotImplementedError泄漏。票据 `workspace/tmp/upload-material-unified-repair-20261002/s3-inflight-root-audit-20261003/zipmethod-public-factory.json`。故只补BadZipFile不足；实际ZIP库输入异常必须在ZIP校验owner收束为配置错误并保cause，不在Fins各入口补捕。不能把未知内部编程错误盲目当配置错误；针对ZIP库操作边界及其明确输入异常类型实施和测试。
