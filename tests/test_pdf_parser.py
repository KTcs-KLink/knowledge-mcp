"""읽기 순서·표 연결·원문 위치 보존을 확인하는 회귀 테스트."""
import tempfile
import unittest
from pathlib import Path

from src.ingestion._pdf_layout import ordered_page_blocks, stitch_tables
from src.ingestion.pdf_parser import export_block, parse_pdf, remove_margins, save_result
from src.ingestion.pdf_parser import restore_paragraphs, render_markdown, markdown_table
from src.ingestion.pdf_parser import group_articles


def line(text, page, top=100, column="full"):
    return {"type": "line", "text": text,
            "location": {"page": page, "bbox": [20, top, 250, top + 10]},
            "page_height": 800, "page_width": 600, "column": column}


def table(page, rows, top, bottom, column="full", x=30):
    location = {"page": page, "bbox": [x, top, x + 240, bottom]}
    return {"type": "table", "text": "", "grid": rows,
            "location": location, "source_locations": [location],
            "row_sources": [{"page": page, "cells": [
                [x, top, x + 80, bottom], [x + 80, top, x + 240, bottom]]} for _ in rows],
            "page_height": 800, "page_width": 600, "column": column}


class FakePage:
    width, height = 600, 800

    def __init__(self, columns):
        self.words = []
        for i in range(15):
            for column in range(columns):
                x = 40 + column * 300
                self.words.append({"x0": x, "x1": x + 200, "top": 100 + i * 20,
                                   "bottom": 110 + i * 20, "text": f"{column}-{i}", "size": 10})

    def find_tables(self):
        return []

    def extract_words(self, **kwargs):
        return self.words


class ParserTests(unittest.TestCase):
    def test_article_groups_all_items_and_history(self):
        texts = ['제2조(구성) ① 첫 항의 내용이다.', '1. 첫 호', '2. 둘째 호',
                 '② 둘째 항의 내용이다.', '[본조신설 1999.4.2]', '제3조(권한) 다음 조이다.']
        blocks = [{'id':f'B{i:05d}', 'type':'text', 'text':text, 'locations':[{'page':1}]} for i,text in enumerate(texts,1)]
        result = group_articles(blocks)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['title'], '제2조(구성)')
        self.assertEqual(result[0]['text'], '\n'.join(texts[:-1]))
        self.assertEqual(result[0]['locations'], [{'page':1}])

    def test_article_stops_at_chapter_supplement_and_annex(self):
        for heading in ['제2장 복무', '제1절 일반', '부칙 <2026.1.1>', '【별표 1】 양식', '(별표 2) 양식']:
            texts = ['제2조(구성) 내용', heading, '별도 내용']
            blocks = [{'id':'', 'type':'text', 'text':text, 'locations':[{'page':1}]} for text in texts]
            result = group_articles(blocks)
            self.assertEqual(len(result), 3, heading)
            self.assertEqual(result[0]['text'], texts[0])

    def test_article_keeps_table_and_its_position(self):
        blocks = [{'id':'', 'type':'text', 'text':'제2조(구성) ① 본문', 'locations':[{'page':1}]},
                  {'id':'', 'type':'table', 'rows':[['항목','내용']], 'locations':[{'page':1}], 'row_locations':[{'page':1}]},
                  {'id':'', 'type':'text', 'text':'② 표 다음 내용', 'locations':[{'page':2}]}]
        result = group_articles(blocks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], '제2조(구성) ① 본문\n[표 B00001-T01]\n② 표 다음 내용')
        self.assertEqual(result[0]['tables'][0]['rows'], [['항목','내용']])
        self.assertEqual(result[0]['tables'][0]['id'], 'B00001-T01')
        self.assertEqual(result[0]['locations'], [{'page':1}, {'page':2}])

    def test_article_reference_is_not_a_heading(self):
        texts = ['제2조(구성) 내용', '제1조 제2항을 따른다.',
                 '제391조(이사회의 결의 방법) 제2항을 준용한다.', '제3조의2(범위) 다른 내용']
        blocks = [{'id':'', 'type':'text', 'text':text, 'locations':[{'page':1}]} for text in texts]
        result = group_articles(blocks)
        self.assertEqual(len(result), 2)
        self.assertIn(texts[1], result[0]['text'])
        self.assertEqual(result[1]['title'], '제3조의2(범위)')

    def test_same_number_in_supplement_stays_separate(self):
        texts = ['제1조(목적) 본문', '부칙', '제1조(시행일) 시행 내용']
        blocks = [{'id':'', 'type':'text', 'text':text, 'locations':[{'page':1}]} for text in texts]
        result = group_articles(blocks)
        self.assertEqual(len(result), 3)
        self.assertNotEqual(result[0]['id'], result[2]['id'])

    def test_amendment_dates_are_not_numbered_items(self):
        blocks = [line('② 이사회 의장은 직무를 대행한다. <개정 1998.4.11,', 1, 100),
                  line('1999.4.2, 2007.5.25>', 1, 118)]
        result = restore_paragraphs(blocks)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['text'].endswith('<개정 1998.4.11, 1999.4.2, 2007.5.25>'))
        self.assertEqual(len(result[0]['source_locations']), 2)

    def test_open_standalone_history_can_continue_after_date_dot(self):
        result = restore_paragraphs([line('[본조신설 1999.4.', 1, 100), line('2]', 1, 118)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], '[본조신설 1999.4.2]')

    def test_actual_numeric_items_are_not_joined(self):
        result = restore_paragraphs([line('다음 각 호에 따른', 1, 100), line('1. 제출 서류', 1, 118)])
        self.assertEqual(len(result), 2)

    def test_open_history_does_not_consume_next_article(self):
        result = restore_paragraphs([line('본문 <개정 1999.4.', 1, 100), line('제3조(범위) 본문', 1, 118)])
        self.assertEqual(len(result), 2)

    def test_completed_history_stays_separate(self):
        result = restore_paragraphs([line('[본조신설 1999.4.2]', 1, 100), line('새 본문', 1, 118)])
        self.assertEqual(len(result), 2)

    def test_sentence_tail_with_amendment_is_not_a_list_item(self):
        blocks = [line('제2조(구성) 이사의 정수는 100분의 50미만으로 한', 1, 100),
                  line('다. <개정 1998.4.11, 1999.4.2, 2018.6.18>', 1, 118)]
        result = restore_paragraphs(blocks)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['text'].endswith('한다. <개정 1998.4.11, 1999.4.2, 2018.6.18>'))
        self.assertEqual(len(result[0]['source_locations']), 2)

    def test_plain_sentence_tail_is_joined_without_space(self):
        result = restore_paragraphs([line('규정에 따른', 1, 100), line('다.', 1, 118)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], '규정에 따른다.')

    def test_real_lettered_item_stays_separate(self):
        blocks = [line('나. 신청 방법', 1, 100), line('다. 제출 서류', 1, 118)]
        self.assertEqual(len(restore_paragraphs(blocks)), 2)

    def test_sentence_tail_does_not_cross_table_or_large_gap(self):
        blocks = [line('다음과 같이 한', 1, 100), table(1, [['A','B']], 120, 160),
                  line('다.', 1, 180)]
        self.assertEqual(len(restore_paragraphs(blocks)), 3)
        self.assertEqual(len(restore_paragraphs([line('규정에 따른', 1, 100), line('다.', 1, 180)])), 2)

    def test_restore_broken_quoted_word_and_locations(self):
        blocks = [line('제1조(목적) 이 세칙은 (이하 ‘규', 1, 100),
                  line('정’이라 한다)의 시행에 필요한 사항과', 1, 118),
                  line('세부사항을 규정함을 목적으로 한다.', 1, 136)]
        result = restore_paragraphs(blocks)
        self.assertEqual(len(result), 1)
        self.assertIn('‘규정’이라 한다)', result[0]['text'])
        self.assertIn('사항과 세부사항', result[0]['text'])
        self.assertEqual(len(result[0]['source_locations']), 3)
        self.assertEqual(result[0]['raw_text'].splitlines(), [b['text'] for b in blocks])

    def test_restore_keeps_headings_items_and_tables_separate(self):
        blocks = [line('제1장 총칙', 1, 100), line('제1조(목적) 이 규정은', 1, 118),
                  line('① 첫 항목은', 1, 136), line('규정에 따른다.', 1, 154),
                  table(1, [['번호', '내용']], 180, 220), line('제2조(범위) 다음과 같다.', 1, 240)]
        result = restore_paragraphs(blocks)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[2]['text'], '① 첫 항목은 규정에 따른다.')

    def test_restore_does_not_join_completed_sentence(self):
        result = restore_paragraphs([line('첫 문장이다.', 1, 100), line('새 문장이다.', 1, 118)])
        self.assertEqual(len(result), 2)

    def test_restore_across_columns_and_pages(self):
        for following in [line('정’이라 한다)의 규정에 따른다.', 1, 80, 'right'),
                          line('정’이라 한다)의 규정에 따른다.', 2, 80, 'left')]:
            previous = line('이하 ‘규', 1, 720, 'left' if following['location']['page']==1 else 'right')
            result = restore_paragraphs([previous, following])
            self.assertEqual(len(result), 1)
            self.assertIn('‘규정’', result[0]['text'])
            self.assertEqual(len(result[0]['source_locations']), 2)

    def test_restore_respects_large_gap_and_new_article(self):
        blocks = [line('이 규정은', 1, 100), line('큰 간격 뒤의 문단', 1, 150),
                  line('제2조(범위) 다른 조항', 1, 168)]
        self.assertEqual(len(restore_paragraphs(blocks)), 3)

    def test_single_column_order(self):
        blocks, layout = ordered_page_blocks(FakePage(1), 1)
        self.assertEqual(layout["columns"], 1)
        self.assertEqual([b["text"] for b in blocks], [f"0-{i}" for i in range(15)])

    def test_two_column_order(self):
        blocks, layout = ordered_page_blocks(FakePage(2), 1)
        self.assertEqual(layout["columns"], 2)
        self.assertEqual([b["text"] for b in blocks],
                         [f"{c}-{i}" for c in range(2) for i in range(15)])

    def test_repeated_margin_not_body_or_heading(self):
        blocks = [line("규정 - 1", 1, 745), line("규정 - 2", 2, 745),
                  line("본문", 1, 100), line("본문", 2, 100),
                  line("제1조 목적", 1, 10), line("제1조 목적", 2, 10)]
        kept, removed = remove_margins(blocks)
        self.assertEqual(len(removed), 2)
        self.assertEqual(len(kept), 4)

    def test_table_repeated_header_connects_pages(self):
        blocks = [table(1, [["번호", "내용"], ["1", "A"]], 600, 760),
                  table(2, [["번호", "내용"], ["2", "B"]], 60, 180)]
        merged, decisions = stitch_tables(blocks)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["grid"]), 3)
        self.assertEqual(len(merged[0]["row_sources"]), 3)
        self.assertEqual(len(merged[0]["source_locations"]), 2)
        self.assertEqual(decisions[0]["reason"], "repeated_header")

    def test_headerless_sequential_table(self):
        blocks = [table(1, [["1", "A"]], 600, 760), table(2, [["2", "B"]], 60, 180)]
        merged, _ = stitch_tables(blocks)
        self.assertEqual(len(merged), 1)

    def test_geometry_alone_does_not_merge(self):
        blocks = [table(1, [["항목A", "설명"]], 600, 760),
                  table(2, [["항목B", "다른 설명"]], 60, 180)]
        merged, decisions = stitch_tables(blocks)
        self.assertEqual(len(merged), 2)
        self.assertEqual(decisions[0]["status"], "review_required")

    def test_body_between_tables_prevents_merge(self):
        blocks = [table(1, [["번호", "내용"]], 600, 760), line("새로운 표 설명", 2),
                  table(2, [["번호", "내용"]], 120, 200)]
        merged, _ = stitch_tables(blocks)
        self.assertEqual(len(merged), 3)

    def test_same_page_left_right_table(self):
        blocks = [table(1, [["번호", "내용"], ["1", "A"]], 600, 760, "left"),
                  table(1, [["번호", "내용"], ["2", "B"]], 60, 180, "right", 330)]
        merged, _ = stitch_tables(blocks)
        self.assertEqual(len(merged), 1)

    def test_export_locations_and_markdown(self):
        block = export_block(line("본문", 1), 1)
        self.assertEqual(block["locations"][0]["page"], 1)
        self.assertNotIn('bbox', block['locations'][0])
        self.assertEqual(set(block), {"id", "type", "text", "locations"})
        result = {"document": {"filename": "test.pdf", "page_count": 1}, "blocks": [block]}
        with tempfile.TemporaryDirectory() as tmp:
            save_result(result, Path(tmp))
            saved = (Path(tmp) / "parsing.md").read_text(encoding="utf-8")
            self.assertIn('본문', saved)
            self.assertNotIn('<!-- pages:', saved)
            self.assertNotIn('전체 1쪽', saved)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["parsing.md"])

    def test_markdown_article_title_once_and_inline_table_order(self):
        result = {'document': {'filename':'test.pdf', 'page_count':2}, 'blocks': [
            {'type':'article', 'title':'제2조(구성)', 'locations':[{'page':1},{'page':2}],
             'text':'제2조(구성) ① 표 앞 내용\n[표 B00001-T01]\n② 표 뒤 내용\n[본조신설 1999.4.2]',
             'tables':[{'id':'B00001-T01', 'rows':[['구분','인원'],['상임이사','7인 이내']]}]}]}
        text = render_markdown(result)
        self.assertEqual(text.count('제2조(구성)'), 1)
        self.assertNotIn('<!-- pages:', text)
        self.assertNotIn('전체 2쪽', text)
        self.assertLess(text.index('① 표 앞 내용'), text.index('| 구분 | 인원 |'))
        self.assertLess(text.index('| 상임이사 | 7인 이내 |'), text.index('② 표 뒤 내용'))
        self.assertNotIn('[표 B00001-T01]', text)
        self.assertIn('[본조신설 1999.4.2]', text)

    def test_markdown_table_escapes_pipes_and_keeps_cell_lines(self):
        text = markdown_table({'rows':[['항목','내용'],['A|B','첫줄\n둘째줄'],['빈칸',None]]})
        self.assertIn('A\\|B', text)
        self.assertIn('첫줄<br>둘째줄', text)
        self.assertIn('| 빈칸 |  |', text)

    def test_markdown_warning_keeps_message_without_page_prefix(self):
        result = {'document': {'filename':'test.pdf', 'page_count':2}, 'blocks':[],
                  'warnings':[{'page':2,'message':'표 연결 확인 필요'}]}
        text = render_markdown(result)
        self.assertIn('- 표 연결 확인 필요', text)
        self.assertNotIn('2쪽:', text)

    def test_export_table_keeps_grid_and_row_sources_without_duplicate_text(self):
        source = table(1, [["항목", "내용"], ["1", "A"]], 100, 200)
        source["text"] = "항목 | 내용\n1 | A"
        block = export_block(source, 1)
        self.assertEqual(set(block), {"id", "type", "locations", "rows", "row_locations"})
        self.assertEqual(block["rows"], source["grid"])
        self.assertEqual(block["row_locations"], [{'page':1}, {'page':1}])

    def test_unsupported_and_missing_input(self):
        with self.assertRaises(ValueError):
            parse_pdf("test.hwp")
        with self.assertRaises(FileNotFoundError):
            parse_pdf("missing.pdf")


if __name__ == "__main__":
    unittest.main()
