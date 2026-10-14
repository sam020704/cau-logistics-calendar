import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from crawl import parse_list, extract_events

class CrawlerTests(unittest.TestCase):
    def test_saved_notice_page(self):
        path = Path(__file__).resolve().parents[2]/'중앙대학교 국제물류학과.html'
        if not path.exists():
            self.skipTest('Uploaded HTML fixture not in distributed ZIP')
        rows, _ = parse_list(path.read_text(encoding='utf-8'))
        self.assertTrue(any(r['id'] == '3759' for r in rows))
        self.assertTrue(all(r['date'] >= '2026-08-01' for r in rows))
    def test_range(self):
        n = {'id':'1','title':'물류 인턴십','url':'https://log.cau.ac.kr/dm/dm_1.php'}
        events=extract_events('신청기간: 2026.10.12 ~ 2026.10.23',n)
        self.assertEqual((events[0]['start'],events[0]['end']),('2026-10-12','2026-10-23'))
    def test_no_unlabeled_dates(self):
        n = {'id':'1','title':'공지','url':'https://log.cau.ac.kr/dm/dm_1.php'}
        self.assertEqual(extract_events('작성일: 2026.10.12',n),[])
if __name__ == '__main__': unittest.main()
