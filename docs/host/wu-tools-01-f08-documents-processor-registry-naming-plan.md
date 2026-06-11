# WU-TOOLS-01-F08 Documents Processor Registry Naming Cleanup Plan

## 元信息

- Work unit：`WU-TOOLS-01-F08`
- Gate：plan
- 日期：2026-06-11
- Planner：AgentCodex
- 设计 / 总控来源：
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/host/issues-implementation-control.md`
  - `docs/reviews/wu-tools-01-f08-goal-confirmation-controller.md`

## 目标、动机与成功信号

目标：把 documents 默认 processor registry builder 从迁移遗留的 OLD `engine` 命名中清理出来，更新直接调用方、导出、测试、稳定 README / 总控引用，并保持 processor registry 行为不变。

第一性原理判断：动机成立，严重性适中。这不是运行时行为 bug，而是 ownership / public naming drift。当前 builder 位于 `dayu.documents.processors.registry`，构建的是通用 documents registry，被 Doc tools 与 Fins 复用，不属于 `dayu.engine`。迁移完成后继续暴露 `build_engine_processor_registry(...)` 会误导边界。

成功信号：

- `build_engine_processor_registry` 在生产代码、测试、稳定 README 和 `docs/host/issues-implementation-control.md` 中无残留。
- `docs/reviews/` 下历史 review artifact 可以保留旧文本；`docs/host/` 下历史 plan artifact 也可以保留旧引用，除非它们是当前稳定控制状态。本 WU 在 `docs/host/` 下的 old-name cleanup control target 只有 `docs/host/issues-implementation-control.md`。
- documents 默认 registry 仍以同一名称、同一类、同一 priority、同一顺序注册 `DoclingProcessor`、`MarkdownProcessor`、`BSProcessor`。
- Fins registry 仍先加载 documents 默认 registry，再覆盖共享 documents processor 注册，并继续注册 Fins / SEC processor。
- focused tests 与 pyright 通过。

## 非目标与范围边界

非目标：

- 不修改 `ProcessorRegistry` 行为。
- 不修改 Docling / Markdown / BS / Fins processor 实现、priority 常量、fallback 规则、`supports(...)` 或 read / preprocess 行为。
- 不修改 Host / Engine 生命周期、ToolRuntime、存储 schema、Fins ingestion 状态机、Web tools 或 Service assembly。
- 禁止为旧名新增兼容 alias、旧名 re-export、旧名 wrapper 或 facade。

范围边界：

- implementation 只允许触及直接 registry naming 面、focused tests、`dayu/fins/README.md` 和 `docs/host/issues-implementation-control.md`。
- 若 implementation 前重新 `rg` 发现四个已知生产文件之外还有生产调用方，必须停止并重新裁决 scope。

## 直接证据

plan gate 已核对到的代码事实：

- `dayu/documents/processors/registry.py` 定义 `build_engine_processor_registry()`，注册：
  - `DoclingProcessor`，name `docling_processor`，priority `10`
  - `MarkdownProcessor`，name `markdown_processor`，priority `10`
  - `BSProcessor`，name `bs_processor`，priority `10`
- `dayu/documents/processors/__init__.py` 导入并导出 `build_engine_processor_registry`。
- `dayu/documents/processors/_doc_processor_factory.py` 导入旧 builder，缓存 `_ENGINE_PROCESSOR_REGISTRY`，通过 `_get_engine_processor_registry()` 返回。
- `dayu/fins/processors/registry.py` 导入旧 builder，在 `build_fins_processor_registry()` 中先构建 documents 默认 registry，再用 `overwrite=True` 覆盖注册 Fins processor。
- `dayu/fins/README.md` 稳定文档中存在 “`build_fins_processor_registry()` 在 engine 文档处理器注册表基础上...” 的旧 ownership 表述。
- `docs/host/issues-implementation-control.md` 当前状态、F08 section 和 active residual risk 中存在旧 builder 引用。

设计对齐：

- Host 设计真源明确 Engine 不拥有工具注册、文档存取或 Fins 语义。
- Engine 设计真源明确 Engine 不拥有工具注册表，不访问财报文档存储。
- 本 work unit 只强化 `dayu.documents` 作为共享文档基础能力 owner 的边界，不引入新层或新 contract。

## 命名决策

推荐新名称：`build_documents_processor_registry(...)`。

理由：

- 直接表达 owner 与能力：documents 共享 processor registry。
- 在 `dayu.fins.processors.registry` 调用点也自解释：Fins 从 documents registry 起步，再覆盖注册 Fins processor。
- 相比 `build_default_processor_registry(...)`，不需要读者依赖当前模块上下文去猜 “default 是谁的 default”。
- 明确消除 `engine` ownership 暗示。

拒绝备选：`build_default_processor_registry(...)`。

- 该名称在 `dayu.documents.processors.registry` 内部可读，但跨包 import 到 Fins 后语义变弱。
- 它没有表达 documents ownership，不能最小认知负担地修复当前问题。

## Contract / Schema / 状态机影响

- Public Python export 变化：`dayu.documents.processors` 导出 `build_documents_processor_registry`，不再导出 `build_engine_processor_registry`。
- 不允许旧名兼容 alias / re-export / wrapper / facade。
- 不涉及 durable schema、tool schema、EventLog、Host public request、Engine contract 或状态机。
- 不预期修改 LLM-facing prompt / schema；只更新开发者 README 与总控文档中的 ownership 表述。

## 受影响文件与精确改动

### `dayu/documents/processors/registry.py`

- 将 `build_engine_processor_registry() -> ProcessorRegistry` 重命名为 `build_documents_processor_registry() -> ProcessorRegistry`。
- 函数体必须保持语义等价：
  - 创建 `ProcessorRegistry()`
  - 注册 `DoclingProcessor` 为 `docling_processor`，priority `_GENERIC_PROCESSOR_PRIORITY`
  - 注册 `MarkdownProcessor` 为 `markdown_processor`，priority `_GENERIC_PROCESSOR_PRIORITY`
  - 注册 `BSProcessor` 为 `bs_processor`，priority `_GENERIC_PROCESSOR_PRIORITY`
  - 返回 registry
- 保持 `_GENERIC_PROCESSOR_PRIORITY = 10` 不变。
- 保留中文 docstring，但表述为 documents 默认处理器注册表，不出现 Engine ownership。
- 不新增 `build_engine_processor_registry = ...`。
- 不保留旧名 wrapper。

### `dayu/documents/processors/__init__.py`

- 将 `.registry` import 从 `build_engine_processor_registry` 改为 `build_documents_processor_registry`。
- 将 `__all__` 中 `"build_engine_processor_registry"` 改为 `"build_documents_processor_registry"`。
- 不保留旧名导出。

### `dayu/documents/processors/_doc_processor_factory.py`

- import 改为 `build_documents_processor_registry`。
- 清理模块级 cache / helper 的 `engine` 命名：
  - `_ENGINE_PROCESSOR_REGISTRY` -> `_DOCUMENTS_PROCESSOR_REGISTRY`
  - `_get_engine_processor_registry()` -> `_get_documents_processor_registry()`
- 触碰该 helper 时补齐严格类型：
  - `_DOCUMENTS_PROCESSOR_REGISTRY: ProcessorRegistry | None = None`
  - `_get_documents_processor_registry() -> ProcessorRegistry`
- helper docstring 改为 documents 处理器注册表。
- `create_doc_file_processor(...)` 调用 `_get_documents_processor_registry()`。
- 不修改后缀映射、MIME 推断、`LocalFileSource` 构造、registry resolve 或 processor 实例化。

### `dayu/fins/processors/registry.py`

- import 改为：
  - `from dayu.documents.processors.registry import build_documents_processor_registry`
- 模块 docstring 与 `build_fins_processor_registry()` docstring 从 “engine 核心处理器 / engine 文档处理器” 改为 “documents 默认处理器注册表”。
- 将 `registry = build_engine_processor_registry()` 改为 `registry = build_documents_processor_registry()`。
- 保持全部 priority 常量与注册顺序不变。
- 保持 Fins processor override 语义不变。
- `build_bs_experiment_registry()` 不改行为；只在必要时清理 stale wording。

### 测试

必须补 focused registry behavior tests。这里的 focused registry tests 是 contract tests，直接锁定 documents 默认 registry 与 Fins registry overlay contract；既有 pipeline tests 是 integration coverage，证明 registry 被下游路径实际消费。两者互补，不能互相替代：pipeline tests 不能替代 focused registry contract tests，focused registry tests 也不替代相关包集成测试。

必选文件：

- `tests/documents/test_processors.py`
- `tests/fins/test_processor_registry.py`

例外：只有 implementation 前有直接代码证据证明已有 focused Fins registry 测试文件比新建 `tests/fins/test_processor_registry.py` 更适合承载该 contract test 时，才允许换位置。无论放在哪个文件，都必须新增或更新 focused Fins registry behavior test；不允许因为已有 pipeline tests 覆盖 Fins preprocess / SEC pipeline 而跳过。

Documents test 断言：

- 从 `dayu.documents.processors` import `build_documents_processor_registry`。
- `build_documents_processor_registry().list_processors()` 精确等于：
  - `{"name": "docling_processor", "class": "DoclingProcessor", "priority": 10}`
  - `{"name": "markdown_processor", "class": "MarkdownProcessor", "priority": 10}`
  - `{"name": "bs_processor", "class": "BSProcessor", "priority": 10}`
- 该断言证明默认注册名称、类、priority 和同 priority 下当前顺序不变。

Fins test 断言：

- 调用 `build_fins_processor_registry()`。
- 优先用 public `list_processors()` 构造 `name -> (class, priority)` 映射，并断言当前 Fins registry 仍包含既有 priority 层级：
  - SEC 表单 BS 主路径 priority `200`
  - SEC 表单 edgartools 回退路径 priority `190`
  - `sec_processor` / `SecProcessor` priority `120`
  - `docling_processor` / `FinsDoclingProcessor` priority `100`
  - `markdown_processor` / `FinsMarkdownProcessor` priority `100`
  - `bs_processor` / `FinsBSProcessor` priority `80`
- 断言共享名称 `docling_processor`、`markdown_processor`、`bs_processor` 最终对应 Fins classes，证明 Fins 仍在 documents 默认 registry 基础上覆盖注册。
- 断言最终 Fins registry 中这些共享名称不再指向通用 `DoclingProcessor`、`MarkdownProcessor`、`BSProcessor`。
- 不要硬编码完整 `list_processors()` 顺序，除非某段顺序本身就是被测行为。Fins 当前重点是 overlay 后的 name/class/priority contract 与 priority bucket，不是整个 registry 的全列表顺序。
- 不要优先读取 private `_items`；public `list_processors()` 已足够支持这些断言。

### `dayu/fins/README.md`

README 触发判断：修改 `dayu/fins/` 必须检查 `dayu/fins/README.md`。该 README 有 `Agent更新约束【必须遵守】`，且当前稳定内容确实存在 processor registry ownership 旧表述，因此需要更新。

精确改动：

- 将 “`build_fins_processor_registry()` 在 engine 文档处理器注册表基础上覆盖注册...” 改为 “`build_fins_processor_registry()` 在 documents 默认处理器注册表基础上覆盖注册...” 或等价中文。
- 不加入 work unit 流水、测试命令、未来计划或用户手册内容。

### `tests/README.md`

README 触发判断：修改 / 新增 tests 需要检查 `tests/README.md`。

预期裁决：若新增测试仍位于既有 `tests/documents/` 与 `tests/fins/` 分层，且不新增测试层级、命令、fixture 类别或维护约定，则无需更新。当前 `tests/README.md` 已覆盖 documents processors 与 Fins processor registry / ingestion 测试边界。

### `docs/host/issues-implementation-control.md`

implementation closeout 时更新稳定总控引用：

- 当前状态表中 `WU-TOOLS-01-F08` 行：将旧函数名改为 `build_documents_processor_registry(...)`，并按真实 gate 状态更新 next entry point。
- F08 section：
  - 按实现进度 / 完成状态更新 status
  - implementation 后把旧函数引用改为新名
  - 记录本 plan artifact path
  - 记录已运行验证命令与结果
  - 实现与验证通过后关闭 `WU-TOOLS-01-S1-R2`
- Residual Risk 表：
  - 按总控规则将 `WU-TOOLS-01-S1-R2` 从 active residual 中关闭或移除，并在 F08 section 记录关闭依据。

不要机械重写历史 review artifact，也不要改写旧 completed work unit 的历史叙述，除非它们仍作为当前稳定状态或 active residual 出现。`docs/host/` 下旧 plan artifact 属于过程历史时可以保留旧名；本 WU 的稳定 control cleanup 只针对 `docs/host/issues-implementation-control.md`。

## Implementation Slice

单 slice：`S1 registry naming cleanup`。

单 slice 理由：

- 行为面集中在一个 builder 和直接调用方。
- 测试和文档都服务同一个命名边界修复。
- 拆分会制造临时 public export / docs 不一致，不能形成更好的独立验证闭环。

允许文件：

- `dayu/documents/processors/registry.py`
- `dayu/documents/processors/__init__.py`
- `dayu/documents/processors/_doc_processor_factory.py`
- `dayu/fins/processors/registry.py`
- `tests/documents/test_processors.py`
- `tests/fins/test_processor_registry.py`
- `dayu/fins/README.md`
- `docs/host/issues-implementation-control.md`

若 implementation 前有直接证据证明已有 focused Fins registry 测试文件更合适，可把 Fins contract test 放入该文件，并在 implementation closeout 说明证据；否则默认必须创建 / 使用 `tests/fins/test_processor_registry.py`。

前置条件：

- 当前分支仍不是 protected trunk。
- implementation 前重新运行 `rg`，确认没有新生产引用出现。

精确允许改动：

- 直接 rename 与引用更新。
- focused tests 证明行为不变。
- README / 总控按触发规则做稳定文档更新。

完成信号：

- 旧名在生产代码、测试、稳定 README / 总控中无残留。
- focused tests 证明 registry 行为不变。
- pyright 无新增或扩散错误。

停止条件：

- `rg` 在四个已知生产文件之外发现旧名生产调用方。
- 发现仓库外部或未覆盖 public consumer 必须保留旧 export 才能运行。
- focused tests 证明当前 registry 行为与本计划直接证据不一致。
- README 更新需要描述未来或未实现行为。
- pyright 暴露的 touched-file 类型错误需要改变 public contract 或 `ProcessorRegistry` 行为才能修复。

## 验证命令

所有命令从仓库根目录运行，先执行：

```bash
source .venv/bin/activate
```

旧名清理检查：

```bash
rg -n "build_engine_processor_registry|_ENGINE_PROCESSOR_REGISTRY|_get_engine_processor_registry" dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md
```

预期：无匹配。

历史 artifact 检查：

```bash
rg -n "build_engine_processor_registry" docs/reviews
```

预期：可以有匹配，但只能来自历史 review artifact。

Focused tests：

```bash
pytest tests/documents/test_processors.py tests/fins/test_processor_registry.py -q
```

若 implementation 前按上文例外规则把 Fins contract test 放入已有 focused 文件，用实际触碰的 Fins focused registry 测试文件替换，并在 closeout 说明原因。

相关包测试：

```bash
pytest tests/documents tests/fins -q
```

`tests/fins` 可能包含较重的 fixture / 环境路径。若 full `tests/fins` 失败，implementation closeout 必须区分失败属于本次 rename regression，还是预存 heavy fixture / environment issue；focused registry tests 是本 WU 行为不变的主要证明。

类型检查：

```bash
python -m pyright dayu/ tests/ utils/
```

可选 whitespace 检查：

```bash
git diff --check
```

## 行为不变证明

Documents 默认 registry：

- 用 `list_processors()` 证明 rename 前后的默认 builder 注册记录不变：
  - 名称仍为 `docling_processor`、`markdown_processor`、`bs_processor`
  - 类仍为 `DoclingProcessor`、`MarkdownProcessor`、`BSProcessor`
  - priority 仍为 `10`
  - 同 priority 下顺序仍为 Docling、Markdown、BS

Fins registry：

- `build_fins_processor_registry()` 必须先调用 `build_documents_processor_registry()`。
- 随后必须以 `overwrite=True` 覆盖共享名称：
  - `docling_processor` -> `FinsDoclingProcessor`，priority `100`
  - `markdown_processor` -> `FinsMarkdownProcessor`，priority `100`
  - `bs_processor` -> `FinsBSProcessor`，priority `80`
- 最终 registry 仍包含 SEC-specific processors 的现有 priority 层级 `200`、`190`、`120`。
- 测试断言 registry records，不只断言 import 成功。
- Fins registry 测试优先断言 `name -> (class, priority)` 映射和 priority bucket；只有顺序本身是目标行为时才断言完整顺序。

## 无过度设计说明

当前问题是直接旧名污染，方案只做直接 rename、直接调用方更新、focused behavior tests 和必要稳定文档同步。不引入新 registry abstraction、provider 机制、兼容层、迁移 shim、模块拆分或配置项。

## Residual Risk

- `docs/reviews/` 历史 artifact 和非当前稳定控制状态的 `docs/host/` 历史 plan artifact 会继续包含 `build_engine_processor_registry`，这是可接受留痕，不属于 success signal。
- 移除旧 public export 可能影响仓库外调用方；但项目规则禁止为旧名保留兼容 re-export / wrapper，正确缓解方式是 PR / release 说明，而不是 alias。
- 若 touched production file 的单文件覆盖率基线低于 80%，implementation closeout 必须如实说明覆盖缺口；本 WU 至少要用 focused tests 覆盖被改 registry 行为。
- full `tests/fins` 如因 heavy fixture / 环境问题失败，需在 closeout 中分类说明；这不自动推翻 focused registry contract tests 的行为证明，但若失败与 rename 相关则必须修复。

## Completion Report 格式

implementation closeout 必须说明：

- 改了哪些文件，以及新 public builder 名称。
- 运行了哪些 tests / pyright，结果是什么。
- README / 总控是否更新，更新依据是什么。
- `rg` 旧名清理信号是否达成。
- 剩余风险或未覆盖项。
- 建议下一 gate。
