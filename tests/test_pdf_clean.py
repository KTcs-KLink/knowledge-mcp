import unittest

from src.ingestion.pdf_parser import clean_deleted_text, remove_deleted_content


class DeletionTests(unittest.TestCase):
    def test_deleted_units_are_removed(self):
        for text in ['제33조 삭제 <2018.7.17>', '제3조(지참 및 조퇴) 삭제 <2019.12.3>',
                     '제10조의2 삭제 <2021.1.22>', '③ 삭제 <2014.7.8>', '3. 삭제 <2021.1.22>',
                     '나. 삭제 <2018.6.18>', '[별표 9] 삭제 <2010.12.1>', '삭제',
                     '※ 삭제 <2018. 10. 30> ※ 삭제 <2017. 6. 15>']:
            with self.subTest(text=text):
                self.assertEqual(clean_deleted_text(text), '')

    def test_article_heading_stays_when_only_first_paragraph_deleted(self):
        self.assertEqual(clean_deleted_text('제8조(고용절차) ① 삭제 <2018.7.17.>'), '제8조(고용절차)')

    def test_deletion_notes_are_removed(self):
        for text in ['[삭제 2014.7.8]', '[본조삭제 2014.7.8]', '<삭제 2014.7.8>', '(삭제)']:
            self.assertEqual(clean_deleted_text(text), '')

    def test_partial_deletion_keeps_active_sentence(self):
        self.assertEqual(clean_deleted_text('금액을 감액하되, (삭제) 감액 후 기준급은 상한을 초과할 수 없다.'),
                         '금액을 감액하되, 감액 후 기준급은 상한을 초과할 수 없다.')

    def test_meaningful_deletion_instructions_stay(self):
        for text in ['기입내용을 추가 또는 삭제할 수 있다.', '개인정보 삭제 절차를 안내한다.',
                     '삭제된 정보의 복구를 금지한다.', '③ 신청 내역 삭제 방법']:
            self.assertEqual(clean_deleted_text(text), text)

    def test_other_history_stays(self):
        for text in ['[본조신설 1999.4.2]', '[전문개정 2013.12.27.]']:
            self.assertEqual(clean_deleted_text(text), text)

    def test_annex_and_mixed_annotations(self):
        for text in ['【 별표 5-4】 삭제 <2022.12.30>', '(별표 17) 삭제<2018. 12. 28>',
                     '주) 1. 삭제 <2024.12.23>', '② <개정 2011.9.9, 삭제 2013.8.20>']:
            self.assertEqual(clean_deleted_text(text), '')
        self.assertEqual(clean_deleted_text('(5) 유효한 내용 (6) 삭제 <2026.1.26.>'), '(5) 유효한 내용')
        self.assertEqual(clean_deleted_text('유효한 본문 ※ 삭제 <2012. 10. 5> ※ 남길 주석'), '유효한 본문 ※ 남길 주석')
        self.assertEqual(clean_deleted_text('(별표 11) 삭제 <2010. 4. 28> (별표 12) <개정 2013. 8. 20>'),
                         '(별표 12) <개정 2013. 8. 20>')

    def test_block_removal_preserves_locations_and_order(self):
        blocks = [{'id':'B00001','type':'text','text':'③ 삭제 <2014.7.8>','locations':[{'page':1}]},
                  {'id':'B00002','type':'text','text':'④ 유효한 내용','locations':[{'page':2}]}]
        result = remove_deleted_content(blocks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'B00001')
        self.assertEqual(result[0]['locations'], [{'page':2}])
        self.assertEqual(blocks[1]['id'], 'B00002')

    def test_table_rows_keep_matching_locations(self):
        block = {'id':'B00001','type':'table','locations':[{'page':1}],
                 'rows':[['항목','내용'],['제33조','삭제'],['정보','삭제할 수 있다.']],
                 'row_locations':[{'page':1},{'page':2},{'page':3}]}
        result = remove_deleted_content([block])[0]
        self.assertEqual(result['rows'], [['항목','내용'],['정보','삭제할 수 있다.']])
        self.assertEqual(result['row_locations'], [{'page':1},{'page':3}])


if __name__ == '__main__':
    unittest.main()
