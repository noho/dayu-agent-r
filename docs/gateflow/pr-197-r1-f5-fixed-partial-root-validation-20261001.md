# F5 固定中断候选的总控验证

时间：2026-10-01T22:35:08.954794+08:00

本记录补充在途观察的终态事实，不覆盖原冻结 artifact。实现97574已 outer1/turn.failed，没有完整作者交付；不接受 implementation/code gate。开发仅 codex/upload-material-oracle，main 未动，40个 partial 保全。

## 独立验证

- 固定40改动源前后 SHA 相同；诊断双审72输入 lease 仍保持，freeze SHA18124f2695338be5ca00ccb5b886294e6398365b30ad03d89b1481c0d0807e1c。
- 激活 .venv 后22受影响测试：1677 passed、1 failed、3条既有edgar warning，72.16s。唯一失败 F5-IV02 CLI取消摘要；并不表示其它未覆盖路径已正确。
- 全量 `python -m pyright dayu/ tests/ utils/` exit0。
- 同次coverage中23个改动生产文件均达到80%，无遗漏文件；这是失败测试候选的诊断值，收尾后仍须最终同字节验证。
- 全部command/stdout/stderr/exit/source-end/coverage、72source/40baseline/full diff含新tests在 `workspace/tmp/pr197-f5-interrupted-source-audit-20261001/` 保全。

## 集中必要修复（同一 F5-S1，不拆新业务 WU）

- **F5-IV01：accepted／未修复**。writer已终态且72输入保持，root再次检查 `_CAPTURE` 无条件读取 ignored tmp 两份 `.body/.json`；六个相关源/provenance文件均 git check-ignore=0、git ls-files --error-unmatch非零。正式checkout不会移交它们，违反accepted plan §9官方Raw回归可复核要求。测试资产owner将精确年度1446字节/季度658字节及provenance/hash移入正式可追踪测试资产或同字节常量；不能skip、造synthetic官方或再次采集冒充旧原件。原capture一律保留只读。下一实施允许必要 `tests/fins/fixtures/hk_f5_official_raw/` 目录及对应测试路径更新。
- **F5-IV02：accepted／未修复**。实际Fs→adapter→observed wait取消typed结果保留A和未知B；`dayu/cli/output.py`取消分支提前return漏投影。改在CLI terminal机械投影owner，保原cancel提示/exit130/输出通道，不在CLI推断财政，不删除真实链断言，不清typed A/B。无download摘要保原取消行为。
- 双路只读诊断若有其它实际finding，由root核owner/原路径/反例后集中登记/修复；不能据作者历史R01–06状态或reviewer两票直接判通过。

## 实现路由与门禁

gpt-6-sol原实施及一次恢复均模型容量失败；既有同provider唯一恢复已消耗。额外一次恢复授权具体异步待答，无产品writer，不自切provider或由root实现。MiMo94273/Kimi40623当前只读诊断，不可替代完整作者交付或正式代码双审。先收诊断并核租约，再按具体授权gpt-6-sol集中收尾、验证和正常门禁。业务裁决已定，不重问。

新版最终CI准备已核49pinned/36supplemental/canary/36label与92静态surface；仅preparation，真实CLI执行仍0。原17label与受控XBRL产品工作及最终真实CLI/registry/proof/readiness仍未完成。
