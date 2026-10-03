# UM-O14/O15 state plan：C3 依赖基线修复

- 范围：只修改 `docs/gateflow/upload-material-state-plan-20260929.md` 并新增本记录；不改变 goal、旧 review/裁决或产品。state plan 原 SHA-256：`cdf8d73d73c72b1dbf716b5c1cb964dbd99d90cdb3d1b689f010f68f7f0c4c70`；修复后 SHA-256：`5b74854bc10873e29fa94a716d88713d7ee48bd9236eb3d0a6d6a5445efeb191`。
- 只读依赖证据：相邻 `/private/tmp/dayu-upload-o12` HEAD `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c`；`docs/gateflow/upload-material-o12-company-plan-20260929.md` SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`。其最终 `docs/gateflow/upload-material-o12-plan-review-adjudication-20260929.md` 判同版 plan gate pass，并把 PR5-F1/F2/F3 设为实施约束；产品未实施。该 plan 文件首部保留修订时“待复审”历史措辞，状态以最终裁决为准。

## C3 修复映射

| C3 要求 | state plan 修复及边界 |
| --- | --- |
| 旧候选 SHA 与“待双路复审”事实过期 | 前置依赖、接缝表、白名单说明、停止条件和残余改指 accepted checkpoint、当前 SHA 与 plan gate pass；明确 O12 未实施/集成，本 state plan 仍待同版复审。 |
| 公司/材料发布 owner | 依赖与实施前核对固定合法公司独立 commit outcome，材料独立 batch/skip guard 严格比较 admission source 与 post-company meta；稳定目标拒绝仍在 `upload.started` 和公司写入前。公司已合法提交后材料失败/取消/guard conflict 保留 O34 公司事实，材料无权威 manifest 不算成功。 |
| COMPLETE tombstone 与恢复 | storage 同版可信完整 canonical business meta、独立 revision、presence/tombstone 一致；`MISSING`/`UNSAFE` 公开 meta/revision 为 None，损坏 fail closed。`auto` 与 prepare/guard 复用同份旧 meta；同指纹恢复原 ID/原版本（UM-A09 v3），异指纹按现行版本规则递增，首次时间保留。 |
| accepted adjudication 追加条件 | 接缝表和 owner 测试核对 alias 与公司漂移同轮时 alias 优先；material 公司并发/guard 冲突同源 typed publication conflict，filing 同异常仍 `storage_io`。upload job 异常及无 runner 路径只用 active-only 原子终态保存，同一 reason 写双摘要；已落盘终态不因后发 progress 异常覆写，download/preprocess 旧投影不变。O16 的 delete+files 业务拒绝仍归其共享 action/files owner。 |
| F8～F11、O34、UM-A09 与 closed reason | 保留 kind×三态动作表、target closed enum 增量和 `USAGE` 投影、tool 既有 `invalid_argument` 协议且 message/hint 来自 Fins、filing 既有投影、健康重复 delete 与损坏状态分界；未改变已接受用户行为。 |

## 验证与残余

- 预检：本 plan 原 SHA、相邻 O12 HEAD/plan SHA 均与任务指定值一致；只读实读 goal、state 总控 C3 末节、O12 accepted plan 与最终 adjudication。C3 是依赖状态漂移，可在计划层修正，未发现需改变 accepted 行为的冲突。
- 文本核对：state plan 中旧 SHA `45b6478a...`、O12“待双路复审”及旧候选状态表述已清除；修复后 `shasum -a 256` 得上述 SHA。`git diff --check` exit 0，但本 plan 为未跟踪文件，该命令不覆盖它；最终另以独立文本检查核对尾随空白、末尾换行、关键依赖标记和工作树范围。
- 工具记录：首次 memory `rg` 无匹配以 exit 1 返回；`get_goal` 因当前会话不支持 persistent thread 被拒。后续 memory 检索使用显式无匹配处理并 exit 0；goal 通过工作区 goal 文档只读绑定。除这两项外，本轮已执行 shell 检查均 exit 0。
- 残余：O12 accepted 只表示计划通过；其实际 API、owner 测试、active-only job 保存和 guard 行为尚待产品集成后实读。O16/身份依赖也须就绪，本 state plan 还需 Kimi/MiMo 对同一新 SHA 复审。不得据本计划进入 O14/O15 实施、产品验证或 PR。
