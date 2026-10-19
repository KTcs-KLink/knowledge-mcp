"""텍스트 PDF의 본문·표를 추출하고 같은 조의 내용을 묶는다. 청킹·OCR은 별도다."""
from __future__ import annotations

import argparse
import hashlib
import re
from collections import defaultdict
from pathlib import Path

try:
    from ._pdf_layout import ordered_page_blocks, stitch_tables
except ImportError:
    from _pdf_layout import ordered_page_blocks, stitch_tables


ROOT = Path(__file__).resolve().parents[2]
PARSER_VERSION = "0.6.1"



BOUNDARY = re.compile(
    r"^(?:제\s*\d+\s*[장절조](?:의\s*\d+)?|부\s*칙|[\[【]?별\s*[표지]|"
    r"[①-⑳❶-❿]|(?!\d{4}\s*[.．]\s*\d{1,2}\s*[.．])\d+\s*[.．)]\s*|[가-하]\s*[.．)]\s*|"
    r"[\[<〈](?:개정|신설|삭제|전문개정|본조))")
STANDALONE = re.compile(r"^(?:제\s*\d+\s*[장절]|부\s*칙|[\[【]?별\s*[표지])")
END = re.compile(r"[.!?。][’”\"')\]〉>]*$")
# 단독 '다.'와 그 뒤의 개정 주석은 목록 '다. 제출서류'와 구분한다.
SENTENCE_TAIL = re.compile(
    r"^다[.!?。](?:\s*[<〈\[](?:개정|신설|전문개정|본조신설)[^>〉\]]*[>〉\]])*\s*$")
PARTICLES = {"은", "는", "이", "가", "을", "를", "의", "에", "에서", "에게",
             "으로", "로", "와", "과", "도", "만", "부터", "까지", "이라", "라고"}
OPEN_HISTORY = re.compile(r"[<〈\[]\s*(?:개정|신설|삭제|전문개정|본조신설|본조개정)[^>〉\]]*$")
HISTORY_DATE_LINE = re.compile(r"^(?:[\d.．\s,~\-/·ㆍ]|개정|신설|삭제)+(?:[>〉\]])?\s*$")


def join_text(left, right):
    """확실한 조사·인용어 분할만 붙이고 나머지는 공백으로 연결한다."""
    left, right = left.rstrip(), right.lstrip()
    first = right.split(maxsplit=1)[0]
    quoted_word = (re.search(r"[‘“\"']([가-힣A-Za-z]+)$", left)
                   and re.match(r"[가-힣A-Za-z]+[’”\"']", right))
    attach = quoted_word or (left.endswith("으") and right.startswith("로"))
    if OPEN_HISTORY.search(left) and left.endswith((".", "．")) and re.match(r"^\d", right):
        attach = True
    if SENTENCE_TAIL.fullmatch(right) and re.search(r"[가-힣]$", left):
        attach = True
    if first in PARTICLES and re.search(r"[가-힣’”')\]]$", left):
        attach = True
    if right.startswith(tuple(",.;:!?，。)]}’”")) or left.endswith(tuple("([{‘“")):
        attach = True
    return left + ("" if attach else " ") + right


def can_continue(previous, current):
    if previous["type"] != "line" or current["type"] != "line":
        return False
    sentence_tail = (SENTENCE_TAIL.fullmatch(current["text"].strip())
                     and re.search(r"[가-힣]$", previous["text"].rstrip()))
    history_tail = (OPEN_HISTORY.search(previous["text"])
                    and HISTORY_DATE_LINE.fullmatch(current["text"].strip()))
    if BOUNDARY.match(current["text"].lstrip()) and not (sentence_tail or history_tail):
        return False
    if STANDALONE.match(previous["text"].lstrip()):
        return False
    # 개정 이력 등 독립 주석 뒤의 본문은 연결하지 않는다.
    if re.match(r"^[\[<〈](?:개정|신설|삭제|전문개정|본조)", previous["text"].lstrip()) and not history_tail:
        return False
    if END.search(previous["text"].rstrip()) and not history_tail:
        return False
    old_size, size = previous.get("font_size", 0), current.get("font_size", 0)
    if old_size and size and abs(old_size - size) > max(1.5, old_size * .18):
        return False
    last = previous.get("source_locations", [previous["location"]])[-1]
    old_page, page = last["page"], current["location"]["page"]
    a, b = last["bbox"], current["location"]["bbox"]
    old_col, col = previous["column"], current["column"]
    if page == old_page and old_col == col:
        # 일반 줄 간격 범위 안에서 이어지는 줄만 연결한다.
        gap = b[1] - a[3]
        return (-1 <= gap <= max(12, (old_size or 10) * 1.4)
                and abs(b[0] - a[0]) <= (old_size or 10) * 2.5)
    # 다음 단/페이지로 넘어가는 경우에는 본문 하단→상단인지도 확인한다.
    next_column = page == old_page and old_col == "left" and col == "right"
    next_page = page == old_page + 1 and (
        (old_col == "right" and col == "left") or old_col == col == "full")
    width_a, width_b = a[2] - a[0], b[2] - b[0]
    return ((next_column or next_page)
            and a[3] > previous["page_height"] * .70
            and b[1] < current["page_height"] * .35
            and width_a > previous["page_width"] * .20
            and width_b > current["page_width"] * .15)


def restore_paragraphs(blocks):
    result = []
    for block in blocks:
        if result and can_continue(result[-1], block):
            previous = result[-1]
            previous.setdefault("raw_text", previous["text"])
            previous["raw_text"] += "\n" + block["text"]
            previous["text"] = join_text(previous["text"], block["text"])
            previous.setdefault("source_locations", [previous["location"]])
            previous["source_locations"].append(block["location"])
            # 다음 줄과 비교할 때 마지막 줄의 단·글자 크기를 사용한다.
            previous["column"] = block["column"]
            previous["font_size"] = block.get("font_size", 0)
            previous["page_height"] = block["page_height"]
            previous["page_width"] = block["page_width"]
        else:
            result.append(dict(block))
    return result


ARTICLE = r"제\s*\d+\s*[장절조](?:\s*의\s*\d+)?(?:\s*[（(][^）)]*[）)])?"
ITEM = r"(?:[①-⑳❶-❿]|\(\s*\d+\s*\)|\d+\s*[.．)]|[가-하]\s*[.．)])"
ANNEX_NUMBER = r"\d+(?:\s*[-의]\s*\d+)?"
ANNEX = rf"(?:[\[【(（]\s*별\s*[표지]\s*{ANNEX_NUMBER}\s*[\]】)）]|별\s*[표지]\s*{ANNEX_NUMBER})"
HISTORY = r"(?:<[^>]*>|〈[^〉]*〉|\[[^\]]*\])"
DELETED_UNIT = re.compile(
    rf"^(?:주\s*\)\s*)?(?:{ARTICLE}|{ITEM}|{ANNEX})?\s*삭제\s*(?:{HISTORY}\s*)*[.。]?$"
)
DELETED_FIRST_ITEM = re.compile(
    rf"^(?P<heading>{ARTICLE})\s*{ITEM}\s*삭제\s*(?:{HISTORY}\s*)*$"
)
DELETED_NOTES = re.compile(rf"^(?:※\s*삭제\s*(?:{HISTORY}\s*)*)+$")
NOTE_BODY = r"\s*(?:본조|본항|본호|본목|전문)?\s*삭제(?:\s+[\d.\s,~\-]+)?\s*"
DELETION_NOTE = re.compile(
    rf"(?:\[{NOTE_BODY}\]|<{NOTE_BODY}>|〈{NOTE_BODY}〉|\({NOTE_BODY}\))"
)
INLINE_DELETION = re.compile(rf"(?:{ANNEX}|\(\s*\d+\s*\)|※)\s*삭제\s*(?:{HISTORY}\s*)*")
DELETED_HISTORY_UNIT = re.compile(rf"^(?:{ARTICLE}|{ITEM})\s*(?P<notes>(?:{HISTORY}\s*)+)$")


def clean_deleted_text(text):
    text = text.strip()
    # 조 전체가 아니라 첫 항만 삭제된 경우에는 조 제목을 남긴다.
    first_item = DELETED_FIRST_ITEM.fullmatch(text)
    if first_item:
        return first_item["heading"].strip()
    if DELETED_UNIT.fullmatch(text) or DELETED_NOTES.fullmatch(text):
        return ""
    history_unit = DELETED_HISTORY_UNIT.fullmatch(text)
    if history_unit and "삭제" in history_unit["notes"]:
        return ""
    text = INLINE_DELETION.sub("", text)
    text = DELETION_NOTE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def remove_deleted_content(blocks):
    """표의 행을 제외할 때는 대응하는 원문 행 위치도 함께 제외한다."""
    result = []
    for source in blocks:
        block = dict(source)
        if block["type"] == "text":
            block["text"] = clean_deleted_text(block["text"])
            if not block["text"]:
                continue
        else:
            rows, row_locations = [], []
            for row, location in zip(block["rows"], block["row_locations"]):
                joined = " ".join(str(cell or "") for cell in row).strip()
                # 번호+삭제만 있는 표의 행도 제외한다. 빈 행은 그대로 둔다.
                if joined and not clean_deleted_text(joined):
                    continue
                rows.append([clean_deleted_text(cell) if isinstance(cell, str) else cell for cell in row])
                row_locations.append(location)
            if not rows:
                continue
            block["rows"], block["row_locations"] = rows, row_locations
        block["id"] = f"B{len(result) + 1:05d}"
        result.append(block)
    return result


def remove_margins(blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    """상하단의 반복 문구만 제거하고 제거한 내용도 별도로 보존한다."""
    groups = defaultdict(list)
    protected = re.compile(r"^(제\s*\d+\s*[장절조]|부\s*칙|[\[【]?별\s*[표지])")
    for block in blocks:
        if block["type"] != "line":
            continue
        text = block["text"].strip()
        if protected.match(text):
            continue
        _, top, _, bottom = block["location"]["bbox"]
        height = block["page_height"]
        side = "top" if bottom < height * .075 else "bottom" if top > height * .92 else None
        if side:
            # 숫자를 정규화하여 '인사0100 - 8'처럼 페이지마다 바뀌는 쪽수도 찾는다.
            signature = re.sub(r"\d+", "#", re.sub(r"\s+", "", text))
            # 반복 본문을 지우지 않도록 페이지 내 세로 위치도 비교한다.
            groups[(side, signature, round(top / height, 2))].append(block)
    excluded = set()
    for group in groups.values():
        if len({b["location"]["page"] for b in group}) >= 2:
            excluded.update(id(b) for b in group)
    removed = [{"text": b["text"], "location": b["location"],
                "reason": "repeated_page_margin"} for b in blocks if id(b) in excluded]
    return [b for b in blocks if id(b) not in excluded], removed


def page_locations(locations):
    """좌표를 출력하지 않고 중복 없는 원문 페이지 번호만 남긴다."""
    return [{"page": page} for page in dict.fromkeys(location["page"] for location in locations)]


def export_block(block: dict, index: int) -> dict:
    """라이브러리 내부 항목을 제외하고 후속 처리에 필요한 항목을 반환한다."""
    result = {
        "id": f"B{index:05d}",
        "type": "table" if block["type"] == "table" else "text",
        "locations": page_locations(block.get("source_locations", [block["location"]])),
    }
    if block["type"] == "table":
        result["rows"] = block["grid"]
        result["row_locations"] = [{"page": row["page"]} for row in block["row_sources"]]
    else:
        result["text"] = block["text"]
    return result


ARTICLE_HEADING = re.compile(
    r"^제\s*(?P<number>\d+)\s*조(?:\s*의\s*(?P<subnumber>\d+))?"
    r"\s*(?P<title>[（(][^）)]*[）)])?"
)
ARTICLE_STOP = re.compile(
    r"^(?:제\s*\d+\s*[장절](?:\s|$)|부\s*칙(?:\s|$|[（(<〈\[])|"
    r"[【\[(（]\s*별\s*[표지]\s*\d+|별\s*[표지]\s*\d+(?:\s|$))"
)


def article_heading(text):
    match = ARTICLE_HEADING.match(text)
    if not match:
        return None
    rest = text[match.end():].lstrip()
    if re.match(r"^제\s*\d+\s*항(?:을|를)\s*준용", rest):
        return None
    # '제2조에 따라', '제2조 제1항' 같은 본문 참조는 새 조로 보지 않는다.
    if not match['title'] and rest and not re.match(r"^[①-⑳❶-❿]", rest):
        return None
    number = f"제{match['number']}조"
    if match['subnumber']:
        number += f"의{match['subnumber']}"
    return number + (match['title'] or '')


def group_articles(blocks):
    """읽기 순서의 모든 내용을 유지하면서 같은 조를 하나의 블록으로 묶는다."""
    result, current = [], None
    for source in blocks:
        text = source.get('text', '')
        heading = article_heading(text) if source['type'] == 'text' else None
        if heading:
            current = {'id': '', 'type': 'article', 'title': heading,
                       'locations': list(source['locations']), 'text': text}
            result.append(current)
            continue
        if source['type'] == 'text' and ARTICLE_STOP.match(text):
            current = None
        if current is None:
            result.append(dict(source))
            continue
        current['locations'].extend(source['locations'])
        if source['type'] == 'table':
            tables = current.setdefault('tables', [])
            table = dict(source)
            # 최종 블록 ID가 정해지면 표 ID와 본문의 자리표시도 함께 정한다.
            marker = f"{{{{TABLE_{len(tables) + 1}}}}}"
            tables.append(table)
            current['text'] += '\n' + marker
        else:
            current['text'] += '\n' + text
    for index, block in enumerate(result, 1):
        block['id'] = f'B{index:05d}'
        block['locations'] = page_locations(block['locations'])
        for number, table in enumerate(block.get('tables', []), 1):
            table['id'] = f"{block['id']}-T{number:02d}"
            block['text'] = block['text'].replace(f'{{{{TABLE_{number}}}}}', f"[표 {table['id']}]")
    return result


def parse_pdf(path: str | Path, *, merge_tables: bool = True,
              strip_margins: bool = True) -> dict:
    """PDF를 읽어 Markdown 출력에 사용할 본문·표 정보를 반환한다."""
    import pdfplumber

    path = Path(path).resolve()
    if path.suffix.lower() != ".pdf":
        raise ValueError("PDF만 지원합니다. HWP·HWPX는 별도 파서가 필요합니다.")
    if not path.is_file():
        raise FileNotFoundError(f"파일이 없습니다: {path}")
    with path.open("rb") as stream:
        file_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    blocks, warnings = [], []
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            raise ValueError("페이지가 없는 PDF입니다.")
        page_count = len(pdf.pages)
        for number, page in enumerate(pdf.pages, 1):
            page_blocks, _ = ordered_page_blocks(page.dedupe_chars(), number)
            if not any(b["text"].strip() for b in page_blocks):
                warnings.append({"page": number, "message": "추출 가능한 글자가 없습니다. 빈 페이지 또는 OCR 필요 여부를 확인하세요."})
            blocks.extend(page_blocks)
            page.close()
    blocks, _ = remove_margins(blocks) if strip_margins else (blocks, [])
    connections = []
    if merge_tables:
        blocks, connections = stitch_tables(blocks)
    for decision in connections:
        if decision["status"] == "review_required":
            warnings.append({"page": decision["to"]["page"],
                             "message": "이전 표와 이어지는지 확인이 필요하여 별도 표로 유지했습니다."})
    for block in blocks:
        if block.get("row_continuation_candidates"):
            warnings.append({"page": block["row_continuation_candidates"][0]["source_location"]["page"],
                             "message": "연결한 표에 중간에서 나뉜 행이 있는지 확인하세요."})
    blocks = restore_paragraphs(blocks)
    content = remove_deleted_content([export_block(block, i) for i, block in enumerate(blocks, 1)])
    content = group_articles(content)
    if not any(b["text"].strip() for b in blocks):
        raise ValueError("본문 텍스트를 추출하지 못했습니다. 스캔 PDF는 OCR 처리가 필요합니다.")
    return {
        "document": {"filename": path.name, "sha256": file_hash, "page_count": page_count},
        "blocks": content,
        "warnings": warnings,
    }


def markdown_table(table):
    rows = table['rows']
    width = max(map(len, rows), default=0)
    if not width:
        return ''
    def row(values):
        cells = [str(value or '').replace('\\', '\\\\').replace('|', '\\|')
                 .replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>') for value in values]
        return '| ' + ' | '.join(cells + [''] * (width - len(cells))) + ' |'
    return '\n'.join([row(rows[0]), row(['---'] * width), *(row(values) for values in rows[1:])])


def render_markdown(result):
    document = result['document']
    lines = [f"# {Path(document['filename']).stem}", '',
             f"> 원본: {document['filename']}", '']
    chapter = section = False
    for block in result['blocks']:
        if block['type'] == 'article':
            text = '\n\n'.join(block['text'].splitlines())
            for table in block.get('tables', []):
                text = text.replace(f"[표 {table['id']}]", '\n' + markdown_table(table) + '\n')
            match = ARTICLE_HEADING.match(text)
            body = text[match.end():].lstrip() if match else text
            level = '####' if section else '###' if chapter else '##'
            lines.extend([f"{level} {block['title']}", '', body, ''])
        elif block['type'] == 'table':
            lines.extend([markdown_table(block), ''])
        else:
            text = block['text']
            if re.match(r'^제\s*\d+\s*장(?:\s|$)', text):
                chapter, section = True, False
                text = '## ' + text
            elif re.match(r'^제\s*\d+\s*절(?:\s|$)', text):
                section = True
                text = '### ' + text
            elif ARTICLE_STOP.match(text):
                chapter = section = False
                text = '## ' + text
            lines.extend([text, ''])
    if result.get('warnings'):
        lines.extend(['## 파싱 확인사항', ''])
        lines.extend(f"- {warning['message']}" for warning in result['warnings'])
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).rstrip() + '\n'


def save_result(result: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'parsing.md').write_text(render_markdown(result), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "data/raw",
                        help="PDF 파일 또는 폴더 (기본값: data/raw)")
    parser.add_argument("--out", type=Path, default=ROOT / "data/parsed")
    parser.add_argument("--no-merge-tables", action="store_true")
    parser.add_argument("--keep-margins", action="store_true")
    args = parser.parse_args()
    if not args.input.exists():
        parser.error(f"입력 경로가 없습니다: {args.input}")
    entries = sorted(p for p in args.input.iterdir() if p.is_file()) if args.input.is_dir() else [args.input]
    files = [p for p in entries if p.suffix.lower() == ".pdf"] if args.input.is_dir() else entries
    skipped = [{"filename": p.name, "reason": "현재 PDF만 지원합니다."}
               for p in entries if args.input.is_dir() and p.suffix.lower() != ".pdf"]
    for item in skipped:
        print(f"건너뜀: {item['filename']}: {item['reason']}")
    if not files:
        parser.error("처리할 PDF가 없습니다. 폴더 안의 HWP 등은 처리하지 않습니다.")
    errors = []
    for path in files:
        try:
            result = parse_pdf(path, merge_tables=not args.no_merge_tables,
                               strip_margins=not args.keep_margins)
            directory = args.out / f"{path.stem}_{result['document']['sha256'][:8]}"
            save_result(result, directory)
            tables = sum(int(b["type"] == "table") + len(b.get('tables', [])) for b in result["blocks"])
            print(f"완료: {path.name} ({result['document']['page_count']}페이지, 표 {tables}개) -> {directory}")
        except Exception as exc:
            # 한 파일의 실패가 나머지 파일 처리를 중단하지 않도록 한다.
            errors.append({"filename": path.name, "error": str(exc)})
            print(f"실패: {path.name}: {exc}")
    args.out.mkdir(parents=True, exist_ok=True)
    summary = ['# 파싱 실행 결과', '', f'- 성공: {len(files) - len(errors)} / {len(files)}개',
               f'- 실패: {len(errors)}개', f'- 지원하지 않는 형식: {len(skipped)}개', '']
    summary.extend(f"- 실패: {item['filename']} — {item['error']}" for item in errors)
    summary.extend(f"- 건너뜀: {item['filename']} — {item['reason']}" for item in skipped)
    (args.out / 'run_summary.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
