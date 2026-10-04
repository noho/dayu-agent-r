# UM-O20-F02 PR8-F1/F2：P0 当次证据规格修订

- 日期：2026-09-29；执行模型：`codex/gpt-6-sol`；范围仅为 P0 plan 的 PR8-F1/F2 和本修订记录。
- 修改前 plan SHA-256：`7bf2564dc0b828b59d5bdfddac4a7d91215cf06fac6ee5a86804d1049b906844`；冻结 E01 SHA-256：`f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`，预检均匹配。修改后 plan SHA-256：`4b4e18a1cf499a05cec293c3afe334aa5afe5c6ba0358ff62a92722a5f8bd545`。
- 已读 `AGENTS.md`、goal、冻结 E01、指定 MiMo review、总控裁决末节，以及 Docling 2.127.0/Arelle 2.45.3 的实际安装源码和对应 wheel metadata。源码关键点：Docling `backend/xml/xbrl_backend.py` 构造及模型赋值、`datamodel/document.py` 的 `DocumentLoadError` 分流、`pipeline/base_pipeline.py` 的 pipeline 捕获；Arelle `ModelDocument.py` 的 `load`、`urlDocs`、`urlUnloadableDocs`、`discoverHref`、`addDocumentReference`。

## 动机和 owner 判断

PR8 动机成立。Arelle `referencesDocument` 的 key 是目标文档，第二次同目标引用只合并类型且不保留第二元素；它的 owner 语义是聚合摘要。`urlDocs` 是成功文档登记，失败请求落在另一结构。Docling 的 `raises_on_error=False` 由 pipeline 使用，输入构造期的非 `DocumentLoadError` 仍会逃出。原计划把有损摘要当原始逐引用事件，又把无 result 的异常混入“失败结果”，会使 P0-B 证据被错误判定闭合。修复 owner 是 P0 取证规格；不在 Dayu 产品增加 hook 或下游补偿。

## 最小运行探针和直接观察

探针在主仓 Python 3.11.15 解释器 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python` 运行；该解释器的 Docling metadata 为 2.127.0。Arelle 2.45.3 只通过既有隔离目录 `/private/tmp/dayu-o20-f02-probe.AdlwrW/arelle2453` 与既有可用传递依赖目录提供 `PYTHONPATH`，没有安装新依赖。无 Arelle 探针不提供该 `PYTHONPATH`，且先由 `find_spec('arelle')` 实测为 false；没有在其他 Python 环境盲目 import Docling。源输入来自既有完全合成的 `typed.xml`/`typed.xsd`，每次新样本用 `/private/tmp` 临时目录，离线且关闭远程获取。以下是**本次修订方法探针**，未按 P0 持久双份归档或跑正式验收，不标记 P0 pass。

| 探针 | 同次直接观察 | 结论边界 |
| --- | --- | --- |
| Arelle 原始引用微样本 | 原始 `schemaRef` 元素三个：`typed.xsd`、`./typed.xsd`、`missing.xsd`；前两项的 `objectIndex` 为 2、3，`hrefObjects` 两项均指向同一个规范化 XSD URI/`filepath`；`referencesDocument` 对该目标只有一个记录且只留 index 2；`urlUnloadableDocs` 有规范化的 `missing.xsd: true`，`urlDocs` 无该失败目标；该次 `model.errors=[]`。 | 成功 href 的 multiplicity 可从 `hrefObjects` 对账；聚合摘要不保存次数；失败 href 不在 `hrefObjects`，且不能仅凭 `model.errors` 找回。 |
| Docling 重复同目标 | 两个原始 `schemaRef` 分别为 `typed.xsd`、`./typed.xsd`；`convert(..., False)` 返回 `SUCCESS`，同次 `modelDocument.hrefObjects` 保留 index 2、3，规范化后均指临时 taxonomy 中同一 XSD `filepath`；`referencesDocument` 仍只有一项。 | 该无 zip、仅 href 的受控样本能闭合原始元素与成功目标；不外推到 XSD import、catalog 或 zip entry。 |
| Docling 失败引用 | 原始 `schemaRef` 为 `typed.xsd`、`missing.xsd`；返回 `SUCCESS` 且模型可得、`errors=[]`；成功 `hrefObjects` 只有前者，`urlUnloadableDocs` 有规范化的 `missing.xsd: true`。 | 状态成功不证明引用闭包完整；失败元素只能从原始来源补齐并与失败集合核对。若完整同次关系缺失，正式向量 blocked。 |
| 无 typed 成功 / typed 导出错误 | 无 typed 合成 instance 返回 `SUCCESS`、`errors=[]`、backend/model 均有；原有 typed instance 返回 `FAILURE`、pipeline `errors` 含 `NoneType ... localName`，但 backend/model 仍有。 | 两条均有 result；不能从静态源码直接推及其他失败。 |
| 坏 taxonomy | 不存在的 taxonomy 目录触发 `ValueError("The 'taxonomy' backend option must be a directory")`，被 `DocumentLoadError` 包裹；`convert(..., False)` 返回 `FAILURE`、`input.valid=false`、`BACKEND_FAILURE`，无 `_backend`/模型。 | invalid-input result 是独立路径。首次探针误读 `_backend` 得到被脚本捕获的 `AttributeError`；随后按拒绝路径重跑，命令均 exit 0。 |
| 缺 Arelle | `find_spec('arelle') == false`；Docling 构造期抛 `ImportError`，cause 为 `ModuleNotFoundError("No module named 'arelle'")`；`convert(..., False)` 没有返回 result。 | 探针最外层必须抓异常链与完整 trace/双流；此处只能记无 result，不能捏造失败 `errors`。 |

上述运行观测来自当前工具双流；不是 P0 要求的原始双流、输入哈希、归档回读或合法性全套记录。无 typed/重复/失败微样本没有重新执行本版 Arelle `--validate --validationExitCode` 门槛。当前探针没有 zip+catalog、完整真实样本或 OS trace，不能证明 zip entry 实际读取、三平台文件/网络隔离、真实上传或无 typed 财报能力。一次 JS 工具编排语法错误发生在任何 shell 命令执行前，随后已纠正；实际执行的 shell 命令均 exit 0，脚本捕获的业务异常和首次探针读取错误不等于转换成功。

## 计划变更和停点

1. **PR8-F1**：§5 的当次模型证据改为成功加载目标、失败/不可加载请求、原始逐引用事件三套独立记录。明确 `urlDocs` key 是规范化请求 URI，`filepath` 是映射后目标；成功 href 用当次 `hrefObjects` 与原始元素逐项对账，失败 href 用原始元素和 `urlUnloadableDocs`/拒绝信息对账。XSD import/include、schemaLocation 等须各自验证逐元素的原始 URI、规范化及目标。`referencesDocument` 仅作聚合摘要。若任何正式向量不能闭合同次逐边关系，该向量/路径 `blocked: run evidence unavailable`；重放、OS trace、archive 形状路径均不能补作 zip entry 读取证据。
2. **PR8-F2**：§5 明列返回 result 且可有模型的成功/typed pipeline 错误、`DocumentLoadError` 返回 invalid-input result 且不假定 backend、构造/导入异常逃出且无 result 三条互斥路径。第三条在探针最外层捕获类型、消息、cause 链、完整 trace、双流及版本，走既有 blocked 出口；三种失败反例已做最小运行探针，正式 P0 仍须逐路径留原始可回读证据。

PR1–PR7 的合法性先行、三平台隔离、证据归档和 blocked 规则未修改；无 typed 能力声明上限及 Docling #4437 跟踪未回退。E01、goal、裁决、产品、测试、依赖、锁与 README 未改。未执行 P0 正式验收，未安装依赖、发 issue、commit/push/PR/merge 或派发子 Agent。仅文档变化，不触发代码测试、pyright 或 README 更新；下一 gate 仍是同一最终 plan SHA 的独立 plan review，不能将本修订记为 P0 pass。
