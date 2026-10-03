# UM-O13-F01 PR4-F1 计划修订记录

- 范围：仅修订 `docs/gateflow/upload-material-o13-tombstone-plan-20260929.md` 的实施白名单第 1、7 项；本记录为唯一新增 artifact。未实施 O13。
- 输入计划 SHA-256：`bb4542115c8823ba2f754768bd15dfbf8ac081d19eba32aeeaaa663ed5af03c8`，与指定锁值一致。
- 修订后计划 SHA-256：`ce9f3e7a55d17afb2894bd0d4eb98c4b051214abfe4500ba7d40a759f4a7870c`。

## 修复映射与证据

| 来源 | 直接证据 | 计划修订 |
| --- | --- | --- |
| 总控 PR4-F1 accepted；MiMo review finding 1 | `_fs_source_document_core.py` 的 `delete_material`、`restore_material`、`delete_filing`、`restore_filing` 均直调 `_toggle_source_deleted`；四个入口现有 Raises 仅列 `FileNotFoundError`、`ValueError`、`OSError`。计划要求的 `require_source_meta_is_deleted` 对缺失 `is_deleted` 抛 `KeyError`、非布尔值抛 `ValueError`；真实转换的 `_prepare_complete_source_meta` 经 `SourceDocumentProvenance.from_meta` 对缺失 provenance 字段抛 `KeyError`、非法值抛 `ValueError`。 | 白名单第 1 项明确要求同一 core 文件的共用 owner 与四个直调入口同步 Raises：`KeyError` 覆盖 source meta 缺必需字段（含 `is_deleted`、provenance），`ValueError` 覆盖非布尔 `is_deleted` 与其它非法值；保留各入口已列异常。不更改异常、行为或签名。 |
| 总控对 MiMo Q1 的裁决 | `publish_prepared_upload` 同时承载多种发布路径，原因描述若限定 delete 会过窄；第 5–7 项现有通用异常原因已足够。 | 白名单第 7 项只明确 `publish_prepared_upload` 的 Raises 原因使用通用描述，不限定 delete 路径；第 5–6 项 PR3 修订保持不变，服务仍仅限指定方法的 docstring。 |

## 静态验证与边界

- 已读取 `AGENTS.md`、goal、MiMo review、总控裁决末节、计划及四个入口现有 Raises，并核对 canonical reader 与 provenance 校验的直接异常来源。
- 输入 SHA 锁核对通过；修订后复核计划 SHA、白名单第 1/7 项、其余白名单与工作区状态。无产品、测试、README、goal、oracle、旧 review 或裁决修改。
- 本轮是计划文档修订，未安装依赖，未运行 pytest、pyright、coverage 或真实 CLI；这些仍属于后续实施与复审 gate。没有新行为验收结论。
- 一次 `functions.exec` JavaScript 包装调用在 shell 启动前因括号语法错误失败；拆正后重新执行，后续 shell 探索命令均 exit 0。此失败不作为静态验证证据。

## 残余与下一入口

- PR4-F1 仅在计划层收口，四入口 docstring 与 owner 行为仍待实施、测试和 review；计划未放行实施。
- 既有覆盖率薄上沿、no-op provenance 复核窗口、batch 物理 copy/swap、O14/O15/O18/O33 集成边界及隔离 CLI 环境门保持原计划约束。
- 下一入口仍是对相同最终计划 SHA 的有效 Kimi/MiMo 双路 plan review；本轮不派发、不提交或推送。
