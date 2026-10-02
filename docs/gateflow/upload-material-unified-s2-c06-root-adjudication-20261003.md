# S2 US2-C06 总控裁决：CLI 准入不得获得仓储能力

## 状态与同路径直接证据

US2-C06：**accepted / 未修复**。当前同一个 WU/S2、HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`、唯一 workspace `/Users/leo/workspace/dayu-agent-r`、分支 `codex/upload-material-oracle`。这是现成项目分层和 owner 约束的必要修复，不新增业务规则、schema、slice/gate 或验收。

总控直接读取当前 `dayu/cli/commands/fins.py::_prevalidate_upload_material_request`：CLI 从 `dayu.fins.service_runtime` 获得 `material_upload_state_repository_for_workspace` 返回的仓储，再直接向 admission 传入该仓储触发状态读取。getter 当前函数体仅返回 FsMaterialUploadStateRepository。早期 surface-01 的直接 storage import 违反两条现有 CLI 架构测试；现已移动 import，但仍把仓储能力泄漏给 UI，CLI 模块自己的 docstring 明确“不读取 Fins storage”。项目要求 UI → Service、语义 owner 修复和禁止无有效语义 wrapper，不能只靠转移 import 满足 AST 测试。

直接可复用的已有语义边界是 `dayu.fins.service_runtime::prevalidate_fins_upload_filing_request_for_workspace`：它装配无业务初始化的只读仓储、消费准入 owner 并返回 validated handoff，不把仓储交给 CLI。

## 批准的最窄接线

在既有白名单 `dayu/fins/service_runtime.py` 增加材料对应的有效语义服务准入函数：

```python
prevalidate_fins_upload_material_request_for_workspace(
    request: FinsUploadMaterialRequest, *, workspace_root: Path,
) -> ValidatedFinsUploadMaterialRequest
```

它在 Service/Fins runtime 装配边界创建 `create_directories=False` 的真实材料状态仓储，调用唯一 R admission 并返回同一 validated handoff。CLI 只构造请求、提供已解析 workspace、消费该函数的 typed handoff；不获取/持有仓储、不从状态重算目标/公司、不增加 callback/factory/兼容默认。移除当前 getter 及其新调用，不留转发 re-export 或未使用 admission import 掩盖真实消费关系。现有 filing helper 及语义保持。

保留 S1 静态首错 → S2 target/company 受理顺序，仍在 production Service factory、stream/started/job 前失败，无公司/材料业务初始化。异常不得宽 catch 所有 ValueError 而将参数用法误分类成存储损坏；typed usage/prevalidation 与真实 operational cause 按既有 owner 原样传递，不创造公开 reason 或局部 fallback。

均在本轮已有白名单内，普通必需调用与现有测试迁移已授权；不要等待用户或再拆 implementation slice。现有两条 CLI 架构测试的禁止集合保留，不弱化断言。测试覆盖 Service 准入→实际仓储→唯一 admission→同一 handoff，CLI 参数前置错误仍不启动 Service factory。

## 真实并发探针与最终验收

生产真实 consumer 变动后，独占 barrier recipe 按实际绑定核对 Service runtime 和 SEC/CN 的 admission 引用；不保留未使用的 CLI import 只为满足旧探针断言。依旧先包装 owner 再 import 真消费者，包装只暂停并原样返回。旧 race-01/02 Raw 与失败票据保留；最终候选需新 label/fresh base 的真实双 CLI 验证，记录最终源码版本、共同旧 MISSING、actual owned exits、ok/skipped、winner→loser 零业务差异及恢复，不能用更早源码证明新版通过。全部 V7–V14、受影响回归、pyright、覆盖率及同版双审继续有效。

当前 runner 32721 在途；按约定读取 root 新裁决文件并同轮集中完成。此 finding 必须在真实修复、同版双审和总控独立核收后才能标已修复。
