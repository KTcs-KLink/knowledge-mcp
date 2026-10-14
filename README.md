# Knowledge MCP

업무지식 문서와 청크 데이터를 관리하고, 이를 검색·활용하는 MCP 기능을 제공하는 프로젝트입니다. 현재 KTcs 제공 데이터는 없으므로 공개적으로 이용할 수 있고 재사용 조건을 확인한 자료 또는 명시적으로 허가된 자료만 사용합니다.

## 폴더 구조

```text
data/
  sources/       재배포가 허용된 원본 문서
  chunks/        문서별 청크 JSONL 파일
  manifests/     문서 출처와 이용 조건 목록
schemas/         데이터 형식 정의
src/
  ingestion/     문서 수집·정제·청킹 코드
  mcp/           MCP 서버와 도구
tests/           데이터·기능 확인 코드
docs/adr/        주요 구조·기술 결정 기록
```

## 문서와 청크 올리는 방법

1. 새 문서에 `SRC-0001`처럼 고유한 `source_id`를 부여합니다. 사용 중인 번호는 `data/manifests/sources.csv`에서 확인합니다.
2. 원본과 그 문서에서 추출한 청크는 재배포가 허용된 경우에만 Git에 추가합니다. 조건이 불분명하거나 허용되지 않으면 파일과 청크 텍스트는 올리지 말고 출처 URL과 확인 상태만 manifest에 기록합니다.
3. 청크는 `data/chunks/SRC-0001.jsonl`처럼 원본과 같은 ID로 저장합니다. 각 줄은 청크 한 건이며, `schemas/chunk.schema.json` 형식을 따릅니다.
4. manifest에 제목, 출처, 게시·수집일, 이용 조건, 재배포 가능 여부, 파일 해시를 기록합니다.
5. 원본과 청크를 함께 바꾸는 PR에는 출처, 이용 조건, 청킹 방법과 변경 파일을 적습니다.

ID는 한 번 부여하면 재사용하지 않습니다. 원본이 바뀌어 청크를 다시 만들면 같은 ID를 유지하고 PR에 변경 이유와 재생성 방법을 기록합니다. 벡터 인덱스와 임베딩은 재생성 가능한 산출물이므로 Git에 올리지 않습니다.

## 청크 JSONL 예시

```json
{"chunk_id":"SRC-0001-0000","source_id":"SRC-0001","chunk_index":0,"text":"문서에서 추출한 청크 내용","page_start":1,"page_end":1,"section":"문서 제목 > 절 제목","source_uri":"https://example.org/document","chunker_version":"v1"}
```

조직 공통의 브랜치·커밋·PR 규칙은 [협업 가이드](https://github.com/KTcs-KLink/.github/blob/main/CONTRIBUTING.md)를 따릅니다.
