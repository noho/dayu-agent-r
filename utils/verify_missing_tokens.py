"""为步骤 2.3 语义判定做 token 级全文验证（重跑转换，验证 missing/added 真伪）。

对指定 stem：

1. 重跑 docling 2.127 转换（do_ocr=True），新版导出缓存到 verify-cache/；
2. 用与 digest 相同口径（merged = texts ∪ tables 单元格）计数；
3. 对 digest 的 missing_merged token：输出 base 计数 vs 新版 texts/tables/merged 计数，
   新版计数为 0 的才是真丢失；
4. 对 added_merged token：输出新版计数与上下文片段（判断新增是否合理）。

:用法: python utils/verify_missing_tokens.py <stem> [stem ...] [--workers N]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / "workspace/tmp/docling-regression"
CACHE_ROOT = DATA_ROOT / "verify-cache"
SAMPLE_LIBRARY_ROOT = Path("/Users/leo/Documents/_2我的投资/workspace/portfolio")
NUMBER_TOKEN_PATTERN = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")


def _merge_counters(exported: dict) -> Counter[str]:
    """按 merged 口径计数数字 token。

    :param exported: export_to_dict 输出。
    :returns: merged 计数。
    :raises Exception: 不主动抛出异常。
    """

    texts = exported.get("texts") or []
    tables = exported.get("tables") or []
    text_counter = Counter(NUMBER_TOKEN_PATTERN.findall("\n".join(str(t.get("text", "")) for t in texts)))
    table_counter = Counter(
        NUMBER_TOKEN_PATTERN.findall(
            "\n".join(str(c.get("text", "")) for t in tables for c in ((t.get("data") or {}).get("table_cells") or []))
        )
    )
    return text_counter + table_counter


def _verify_one(stem: str) -> dict:
    """验证单份样本的 missing/added token。

    :param stem: 样本 stem。
    :returns: 验证结果 dict。
    :raises Exception: 不主动抛出异常。
    """

    cache_path = CACHE_ROOT / f"{stem}.json"
    if cache_path.exists():
        exported = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        from dayu.documents.docling_runtime import convert_pdf_bytes_with_docling

        pdf_path = next(SAMPLE_LIBRARY_ROOT.rglob(f"{stem}.pdf"))
        raw_bytes = pdf_path.read_bytes()
        conversion = convert_pdf_bytes_with_docling(raw_bytes, stream_name=pdf_path.name)
        exported = conversion.document.export_to_dict()
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(exported, ensure_ascii=False), encoding="utf-8")

    new_merged = _merge_counters(exported)
    new_texts = "\n".join(str(t.get("text", "")) for t in (exported.get("texts") or []))

    baseline = json.loads(
        next(SAMPLE_LIBRARY_ROOT.rglob(f"{stem}_docling.json")).read_text(encoding="utf-8")
    )
    base_merged = _merge_counters(baseline)

    digest = json.loads((DATA_ROOT / "digests" / f"{stem}.json").read_text(encoding="utf-8"))
    missing = digest["numbers"]["missing_merged"]
    added = digest["numbers"]["added_merged"]
    return {
        "stem": stem,
        "base_count": {t: base_merged[t] for t in missing},
        "new_count": {t: new_merged[t] for t in missing},
        "added_new_count": {t: new_merged[t] for t in added},
        "added_base_count": {t: base_merged[t] for t in added},
        "new_texts": new_texts,
        "missing": missing,
        "added": added,
    }


def _context(new_texts: str, token: str, max_hits: int = 3) -> list[str]:
    """在新版 texts 全文中找 token 的上下文片段。

    :param new_texts: 新版 texts 全文。
    :param token: 待定位 token。
    :param max_hits: 最多返回的命中数。
    :returns: 上下文片段列表。
    :raises Exception: 不主动抛出异常。
    """

    hits: list[str] = []
    for match in re.finditer(re.escape(token), new_texts):
        start = max(0, match.start() - 45)
        end = min(len(new_texts), match.end() + 45)
        hits.append(new_texts[start:end].replace("\n", "⏎"))
        if len(hits) >= max_hits:
            break
    return hits


def main() -> int:
    """批量验证并打印结果。

    :returns: 成功返回 0。
    :raises Exception: 不主动抛出异常。
    """

    parser = argparse.ArgumentParser(description="步骤 2.3 语义判定 token 级全文验证")
    parser.add_argument("stems", nargs="+", help="stem 列表")
    parser.add_argument("--workers", type=int, default=2, help="并行 worker 数")
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(_verify_one, stem): stem for stem in args.stems}
        for future in as_completed(future_map):
            stem = future_map[future]
            result = future.result()
            print(f"\n{'=' * 100}\nSTEM {stem}")
            print("missing token（token: base 计数 → new 计数）:")
            for token in result["missing"]:
                new_count = result["new_count"].get(token, 0)
                mark = "★真丢" if new_count == 0 else "  (仍存在)"
                print(f"  {token!r}: {result['base_count'].get(token, 0)} → {new_count}{mark}")
            print("added token（token: base 计数 → new 计数）:")
            for token in result["added"]:
                print(f"  {token!r}: {result['added_base_count'].get(token, 0)} → {result['added_new_count'].get(token, 0)}")
                for ctx in _context(result["new_texts"], token):
                    print(f"     ctx: {ctx!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
