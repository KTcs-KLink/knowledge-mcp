# 청크 데이터

문서별 청크를 JSONL 형식으로 저장합니다. 파일 하나에 한 출처의 청크만 넣고 파일명은 `source_id`를 사용합니다. 예: `SRC-0001.jsonl`.

원본 문서와 추출 텍스트를 저장소에 공유할 수 있다는 점이 확인된 자료만 업로드합니다. 조건이 확인되지 않은 자료는 청크도 올리지 말고 출처 URL만 manifest에 기록합니다.

- 한 줄에 JSON 객체 하나를 기록합니다.
- 각 청크는 `chunk_id`, `source_id`, `chunk_index`, `text`, `source_uri`, `chunker_version`을 포함합니다.
- 페이지를 확인할 수 있으면 `page_start`, `page_end`를 기록하고, 제목 구조를 추출할 수 있으면 `section`에 기록합니다.
- `chunk_id`는 `SRC-0001-0000`처럼 출처 ID와 0부터 시작하는 순번으로 만듭니다.
- 청크의 근거를 원본 문서까지 추적할 수 있어야 합니다. 출처·페이지 정보가 없는 청크는 올리지 않습니다.
- 형식은 `schemas/chunk.schema.json`을 기준으로 합니다.
