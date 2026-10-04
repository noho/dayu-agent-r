# UM-O20-F01：material 格式说明与共享 capability 同源

- Work unit：`UM-O20-F01`；Gate：goal confirmation。工作区 `/private/tmp/dayu-upload-o20`，分支 `codex/upload-material-o20`，基线 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 用户裁决来源：主工作区 `docs/reviews/upload-material-um-o20-oracle-adjudication.md`；原五份输入为不符合声明子类型的负样本，不能证明有效 Docling JSON 或 XBRL instance 不可转换。用户已接受本项 public text 修复方向，并要求有效内容均进入 Docling；抽取准确率归上游 Docling，不在本项目实现解析器。

## 动机与严重性

动机由当前代码直接成立：`dayu/documents/docling_runtime.py` 的共享 converter capability 含 `XML_XBRL`/`JSON_DOCLING`；`dayu/fins/upload_format_contract.py:project_fins_upload_format_text` 的 filing 文案说明 `.xml`/`.json` 子类型候选，但 material 文案只列后缀与“转换资格”。相同能力向 filing/material 用户表达不同承诺，使普通 JSON/XML 或独立 linkbase 的 material 用户缺少可操作的输入类型说明。严重性限于公开帮助/schema 表述；冻结失败已 typed 且没有 material publication，不能据此声称转换器运行能力已失效或已发布错误内容。

## 目标与非目标

目标：在 Fins 格式文案唯一投影处使 material 的文件说明明确 `.json` 仅 Docling JSON 候选，`.xml/.xbrl` 仅 XBRL instance 候选，扩展名命中不保证内容能转换；CLI、tool schema、batch/其它消费者继续复用同一投影，不各自写特例。保留 filing 现有准确说明和共享 capability 的实际格式集合。测试断言 owner 文案及各消费者的一致来源，真实 CLI `--help`/必要 tool schema 复核用户可见语义。按触发规则与 README 读者职责判断文档更新。

非目标：不改变转换、后缀准入、docling 资产、失败分类/日志、仓储或 schema；不新增普通 JSON/XML/linkbase 的本地转换器；不把 Docling 内容抽取准确率纳入项目职责。有效 Docling JSON 与 XBRL instance 的端到端能力补证属于独立 `UM-O20-E01`；XBRL 可选依赖/部署能力是否需产品修复仍是条件项 `UM-O20-F02`，待补证裁决。

## 语义 owner、成功信号与停止条件

格式能力真源在 `dayu.documents.docling_runtime`；Fins 用户/LLM 可读说明的唯一 owner 是 `dayu.fins.upload_format_contract.project_fins_upload_format_text`。CLI 与 tool 只消费投影。成功信号是同一 material 说明准确表达候选子类型，三条入口无词义漂移，受影响测试与 pyright 通过；不得用静态文案测试代替真实 CLI help 核验。若代码事实表明任一入口另有独立格式文案、需要改变 converter capability 或会把“支持候选”误说成“有效输入必成功”，停止 implementation 重新裁定范围。

Goal confirmation：**pass**。依据用户已明确接受 UM-O20-F01 方向与上述当前 owner 代码事实；下一 gate 是 gpt-6-sol 生成可执行 plan，再由 Kimi/MiMo 两路 review。所有闭环代码最终汇入现有 draft PR #197，用户手工 merge main。
