"""CAU international logistics notice crawler. Conservative: abort on unverified pages."""
import argparse
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE = 'https://log.cau.ac.kr/dm/dm_1.php'
ROOT = Path(__file__).resolve().parents[1]
CUTOFF = date(2026, 8, 1)
HEADERS = {'User-Agent': 'CAU-Logistics-Calendar/1.0 (public notice index; low-frequency)'}
ID_RE = re.compile(r"view\(['\"](\d+)['\"]")
DATE_RE = re.compile(r'^(20\d{2})[./-](\d{1,2})[./-](\d{1,2})$')
FULL = r'(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?'
LABEL = re.compile(r'(신청\s*기간|접수\s*기간|지원\s*기간|모집\s*기간|제출\s*기간|행사\s*기간|진행\s*기간|운영\s*기간|신청\s*마감|접수\s*마감|행사\s*일시|개최\s*일시)\s*[:：]?\s*')


def iso(y, m, d):
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def parse_list(html):
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.select_one('table.tb3')
    if not table or not table.select_one('tbody'):
        raise RuntimeError('공지 목록 table.tb3를 찾을 수 없습니다')
    results = []
    for tr in table.select('tbody tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 4:
            continue
        a = cells[1].find('a')
        if not a:
            continue
        match = ID_RE.search(a.get('href', ''))
        dm = DATE_RE.match(cells[3].get_text(strip=True))
        if not match or not dm:
            continue
        published = iso(*dm.groups())
        if published and published >= CUTOFF.isoformat():
            results.append({'id': match.group(1), 'title': a.get_text(' ', strip=True),
                            'date': published, 'attachment': bool(cells[2].find('img')),
                            'url': BASE + '?' + urlencode({'p_idx': match.group(1), 'p_mode': 'view'})})
    return results, soup


def extract_events(body, notice):
    events = []
    for label in LABEL.finditer(body):
        segment = body[label.end():label.end()+145].split('\n')[0]
        dates = list(re.finditer(FULL, segment))
        if not dates:
            continue
        start = iso(*dates[0].groups())
        if not start:
            continue
        end = start
        if len(dates) > 1:
            between = segment[dates[0].end():dates[1].start()]
            if not re.search(r'[~～∼–—-]|부터|까지', between):
                continue
            end = iso(*dates[1].groups())
        else:
            suffix = segment[dates[0].end():]
            short = re.match(r'\s*[~～∼–—-]\s*(?:(\d{1,2})\s*[.\-/월]\s*)?(\d{1,2})\s*일?', suffix)
            if short:
                end = iso(dates[0].group(1), short.group(1) or dates[0].group(2), short.group(2))
        if not end or end < start or (date.fromisoformat(end)-date.fromisoformat(start)).days > 180:
            continue
        text = notice['title'] + ' ' + label.group(1)
        category = ('장학금' if '장학' in text else '인턴십' if re.search('인턴|현장실습|채용', text)
                    else '학사' if re.search('수강|학점|등록|졸업|학사', text) else '행사')
        event = {'id': f"{notice['id']}-{start}-{end}-{label.start()}", 'title': notice['title'] + ' · ' + label.group(1),
                 'start': start, 'end': end, 'category': category, 'url': notice['url'],
                 'notice_id': notice['id'], 'evidence': label.group(1) + ': ' + segment[:100]}
        if not any(e['start'] == start and e['end'] == end and e['title'] == event['title'] for e in events):
            events.append(event)
    # A heading followed by individually dated visits/events (e.g. "견학 및 행사 일정").
    lines = [x.strip() for x in body.splitlines() if x.strip()]
    in_schedule = False
    for i, line in enumerate(lines):
        if re.search(r'견학\s*및\s*행사\s*일정|행사\s*일정', line) and len(line) < 45:
            in_schedule = True
            continue
        if in_schedule and re.match(r'^<[^>]+>$', line):
            in_schedule = False
        if not in_schedule or not line.startswith('- '):
            continue
        # HTML line breaks may split the event name and its date.
        combined = line + (' ' + lines[i+1] if i+1 < len(lines) else '')
        match = re.search(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일', combined)
        if not match:
            continue
        year = int(notice['date'][:4])
        day = iso(year, *match.groups())
        if not day:
            continue
        name = line[2:].rstrip(':：').strip()
        if not name:
            continue
        event = {'id': f"{notice['id']}-{day}-schedule-{i}",
                 'title': name, 'start': day, 'end': day, 'category': '행사',
                 'url': notice['url'], 'notice_id': notice['id'],
                 'evidence': combined[:130]}
        if not any(e['title'] == name and e['start'] == day for e in events):
            events.append(event)
    return events


def fields_from_form(soup):
    form = soup.select_one('form[name="frm"]')
    if not form:
        raise RuntimeError('목록 form[name=frm] 없음')
    return {x.get('name'): x.get('value', '') for x in form.select('input[name]')}


def request_page(session, fields, **overrides):
    data = dict(fields)
    data.update(overrides)
    r = session.post(BASE, data=data, timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or 'utf-8'
    return r.text


def detail_text(html, expected_id):
    soup = BeautifulSoup(html, 'html.parser')
    # Do not mistake a returned list page for a detail page.
    if soup.select_one('table.tb3 tbody tr'):
        raise RuntimeError(f'{expected_id}: 상세 요청이 목록 페이지를 반환했습니다. view() 함수 확인 필요')
    for selector in ['#bo-cont', '.view-cont', '.view_content', '.board-view-content', '.bo-view-content',
                     '.bo_view .content', '.tb-view', '.view_con', '.board_view', '.view_contents', '.contents']:
        node = soup.select_one(selector)
        if node and len(node.get_text(' ', strip=True)) > 20:
            return node.get_text('\n', strip=True)
    raise RuntimeError(f'{expected_id}: 상세 본문 선택자 미확인. HTML 구조를 확인해 주세요')


def crawl(max_pages=30, delay=1.5):
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.get(BASE, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or 'utf-8'
    initial = response.text
    first_entries, soup = parse_list(initial)
    if not first_entries:
        raise RuntimeError('첫 페이지에 2026-08 이후 공지가 없습니다')
    fields = fields_from_form(soup)
    all_notices = {}
    all_events = {}
    old_notices = {n['id']: n for n in load('notices.json')}
    old_events = {e['id']: e for e in load('events.json')}
    previous_signature = None
    for page in range(1, max_pages+1):
        html = initial if page == 1 else request_page(session, fields, p_page=str(page))
        entries, page_soup = parse_list(html)
        signature = tuple((a.get('href'), a.get_text(' ', strip=True)) for a in page_soup.select('table.tb3 tbody tr:not(.notice) td:nth-child(2) a'))
        if page > 1 and (not signature or signature == previous_signature):
            raise RuntimeError('GoPage 페이지 이동이 동작하지 않습니다. JS 요청 방식 확인 필요')
        previous_signature = signature
        # pinned notices repeat; only non-pinned rows establish page progression
        normal_rows = page_soup.select('table.tb3 tbody tr:not(.notice)')
        normal_dates = []
        for row in normal_rows:
            td = row.find_all('td', recursive=False)
            if len(td) >= 4:
                m = DATE_RE.match(td[3].get_text(strip=True))
                if m:
                    normal_dates.append(iso(*m.groups()))
        for notice in entries:
            all_notices[notice['id']] = notice
        print(f'page={page} qualifying={len(entries)} normal_dates={normal_dates[:2]}')
        if page > 1 and not normal_dates:
            raise RuntimeError('페이지 이동 결과가 비정상입니다. GoPage() 구현 확인 필요')
        if normal_dates and max(normal_dates) < CUTOFF.isoformat():
            break
        if page == max_pages:
            raise RuntimeError('최대 페이지에 도달했습니다. 수집 완전성을 확인하고 max-pages를 늘리세요')
        time.sleep(delay)
    for i, notice in enumerate(all_notices.values()):
        # POST with p_mode=view is a hypothesis based on form fields; fail closed on mismatch.
        try:
            # The saved official detail page uses GET query parameters, not POST.
            params = dict(fields)
            params.update(p_idx=notice['id'], p_mode='view')
            response = session.get(BASE, params=params, timeout=25)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            detail = response.text
            body = detail_text(detail, notice['id'])
            for event in extract_events(body, notice):
                all_events[event['id']] = event
        except (requests.RequestException, RuntimeError) as exc:
            print(f'WARN detail {notice["id"]}: {exc}')
            # Preserve previously verified events when detail temporarily fails.
            for event in old_events.values():
                if event.get('notice_id') == notice['id']:
                    all_events[event['id']] = event
        time.sleep(delay)
    if not all_notices:
        raise RuntimeError('저장할 공지가 없습니다')
    # Retain previous notices if temporarily missing from the source, avoiding destructive updates.
    all_notices = {**old_notices, **all_notices}
    return sorted(all_notices.values(), key=lambda x: (x['date'], int(x['id'])), reverse=True), list(all_events.values())


def load(filename):
    path = ROOT / 'data' / filename
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError(filename + ' must contain an array')
    return data


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--max-pages', type=int, default=30)
    p.add_argument('--delay', type=float, default=1.5)
    args = p.parse_args()
    if args.max_pages < 2 or args.delay < 0.5:
        p.error('max-pages >= 2 and delay >= 0.5 required')
    notices, events = crawl(args.max_pages, args.delay)
    (ROOT/'data').mkdir(exist_ok=True)
    for filename, data in [('notices.json', notices), ('events.json', events)]:
        (ROOT/'data'/filename).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'OK notices={len(notices)} events={len(events)}')


if __name__ == '__main__':
    main()
