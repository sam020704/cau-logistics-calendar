# CAU Logistics Calendar — GitHub Pages + Actions

## 설치 (웹 브라우저만 사용)

1. ZIP을 압축 해제한다.
2. GitHub 저장소 `sam020704/cau-logistics-calendar`에서 **Add file → Upload files**를 클릭한다.
3. 압축 해제한 폴더 안의 `index.html`, `requirements.txt`, `data` 폴더, `scripts` 폴더, `.github/workflows/update.yml`을 **폴더 구조를 유지**해 업로드한다. GitHub 웹 업로드에서 폴더 전체를 끌어놓으면 하위 경로가 유지되는지 확인한다. `.github`는 숨김 폴더이므로 탐색기에서 숨김 항목을 표시해야 할 수 있다.
4. **Settings → Actions → General → Workflow permissions**에서 `Read and write permissions`를 선택하고 저장한다. 조직 정책에 따라 옵션이 없을 수 있다.
5. **Actions → Update CAU notices → Run workflow**를 누른다.
6. 실행이 성공하면 `data/notices.json`과 `data/events.json`이 자동 갱신되고 GitHub Pages에 반영된다.

## 중요: 실제 학교 상세 페이지 연동은 미검증

업로드된 게시판 HTML에서는 `javascript:view('3759','?')`와 `javascript:GoPage('2')`, `form[name=frm]`의 `p_idx`, `p_page`, `p_mode`가 확인된다. 그러나 실제 `view()` / `GoPage()` JavaScript 구현은 포함되지 않았다.

크롤러는 **POST** 요청에 `p_idx` + `p_mode=view`를 전달하고, 페이지 이동은 `p_page`로 시도한다. 이는 **추정 구현**이며 실제 사이트가 다르게 동작하면 Actions가 실패하거나 상세 본문을 읽지 못할 수 있다. 로그에 `GoPage 페이지 이동이 동작하지 않습니다`가 뜨면 반드시 학교 사이트의 JavaScript를 확인해 수정해야 한다. 페이지네이션 검증 실패 시 JSON 파일을 쓰지 않도록 되어 있다. 상세 본문 선택자를 찾지 못한 공지는 일정이 표시되지 않는다.

날짜 추출은 `신청기간`, `접수기간`, `지원기간`, `모집기간` 등 명확한 표현 옆에 있는 날짜를 기준으로 한다. 연도가 없는 시작 날짜나 첨부파일에만 있는 일정은 추출하지 않는다. 인턴십 모집은 보라색, 장학금은 청록색 등 카테고리별로 표시한다. 정확한 날짜 여부는 원문 확인이 필요하다.

## 파일 구조

- `index.html`: GitHub Pages 캘린더
- `data/notices.json`: 공지 목록 (초기 12건은 사용자 제공 목록 HTML에서 추출)
- `data/events.json`: 실제 본문 확인 전에는 빈 배열
- `scripts/crawl.py`: 공지 목록·상세 본문 크롤러
- `.github/workflows/update.yml`: 매일 10:15 KST 예약 실행 + 수동 실행
- `tests/test_crawl.py`: 오프라인 날짜 추출 테스트

## 테스트

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

**주의:** 파일을 컴퓨터에서 직접 더블클릭해 열면 `fetch('./data/...')`가 브라우저 정책에 막힐 수 있다. GitHub Pages 주소에서 열어야 한다. GitHub Pages는 정적 호스팅이므로 새로운 데이터는 GitHub Actions가 커밋한 뒤 반영된다.
