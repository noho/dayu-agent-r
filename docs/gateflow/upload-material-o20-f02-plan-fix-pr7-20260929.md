# UM-O20-F02：PR7-F1 P0 计划修订记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-160d98c7

- 工作区：`/private/tmp/dayu-upload-o20-f02`。本次只修订 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md` §5 P0-B，并新增本记录；未执行 P0、未运行真实 taxonomy 或安装依赖。
- 修订前 plan SHA-256：`720cf5027420e6b1f2badf679179871ee1e30154a6ff26608013027c204f1f99`；修订后 plan SHA-256：`7bf2564dc0b828b59d5bdfddac4a7d91215cf06fac6ee5a86804d1049b906844`。
- 冻结 E01 SHA-256：`f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`，修订前后未变。goal、probe、旧 review、总控裁决及产品文件未改。

## 动机、修复映射与直接依据

| 裁决项 | 计划 §5 P0-B 修订 | 直接依据 |
| --- | --- | --- |
| PR7-F1：失败时默认抛出会丢同次结果句柄 | 先用最小自足的合法无 typed 成功样本与合法含 typed 失败样本，实测成功/失败两路的属性链；每次 Path/Stream 在同一转换进程以 `raises_on_error=False` 保留 `result`，立即快照 `result.input._backend.model_xbrl` 的 `urlDocs` 请求 URI→实际加载目标和 `referencesDocument` 来源/目标/引用类型/元素，连同状态、`errors`、版本、配置、输入哈希与双流留存。 | Docling 2.127.0 `document_converter.py:515-523, 641-658` 与 `pipeline/base_pipeline.py:79-108,185-186`；`document_converter.py:242-245` 确认 XBRL 使用 `SimplePipeline`；`backend/xml/xbrl_backend.py:181,344`。Arelle 2.45.3 `ModelDocument.py:535,678-681,1488-1496,2171-2174`。 |
| 内部接口与失败边界 | 明确以上属性均为第三方内部 API，仅供 P0 取证；升级或属性失效先留原始证据并按原 `blocked: run evidence unavailable` 出口回 plan/fix，不能加 Dayu 产品 hook。backend 初始化或 `model_xbrl` 赋值前的失败也可能无模型，不伪造映射。 | `backend/xml/xbrl_backend.py:115-185` 显示临时目录在赋值前退出，初始化失败走异常；`datamodel/document.py:306-335` 显示 backend 装配失败路径。 |
| 证据来源隔离 | 模型快照记录的是当次加载目标，临时路径在转换返回前已清理，不能事后重读补证；OS trace 仅证明可见文件访问，不能证明 zip 内 entry 或 catalog 映射；独立 Arelle 重放仍单列。 | Docling `backend/xml/xbrl_backend.py:120-181` 的 `TemporaryDirectory`；MiMo `docs/reviews/plan-review-20260929-144041.md` §1.2/§3 与总控裁决末节。 |

## 验证与残余

- 已逐字核对 AGENTS.md、goal、冻结 E01、指定 plan、MiMo PR7 review 与总控裁决末节；修订前两 SHA 与任务锁定值一致。只读核对本机 Docling 版本 `2.127.0` 及上述 Docling/Arelle 一手源码；修订后复算 plan/E01 SHA，检查新增 P0-B 段落恰一处。未把源码可行性写成已运行探针。
- **P0 尚未执行**：成功/失败样本的运行期属性链、zip/catalog 映射、真实正样本、三平台隔离和产品能力仍待原计划门槛；旧计划的 blocked 状态不因本次文字修订转为 pass。此内部对象链在 Docling 版本变化时必须重验。
- 本次仅改 Markdown 计划和记录，没有代码改动；未运行受影响测试、pyright 或 README 同步。
- 检查/编辑异常如实披露：首次 `functions.exec` JavaScript 包装语法错误，未发出 shell 命令；一次 `rg` 使用了不存在的本 worktree `.venv/.../xbrl_backend.py` 等路径，shell exit 2，随后从主仓 venv 正确路径只读核对源码；一次 `apply_patch` 因预期整行与实际 P0-C 行不匹配而失败，随后用唯一锚点替换成功。其余已发出的检查 shell 命令均 exit 0。按严格逐命令口径，本轮存在上述失败，不宣称全部工具成功。
