# Knowledge MCP

Assistant가 사용할 지식 데이터의 출처와 이용 조건을 관리하고, 검색 기능을 MCP Server 도구로 제공하는 프로젝트입니다. 사용자 화면과 Assistant 서버·오케스트레이터 및 MCP Client는 [`ai-assistant`](https://github.com/KTcs-KLink/ai-assistant) 저장소에서 개발합니다.

> 출처나 이용 조건이 불명확한 자료의 원문과 추출 텍스트는 저장소에 올리지 않습니다.

## 목표와 범위

- 문서 출처와 이용 조건을 추적할 수 있도록 manifest를 관리합니다.
- 합의된 형식으로 문서를 정제하고 청크로 나누는 절차를 마련합니다.
- 검색 결과와 근거 출처를 반환하는 MCP 도구를 제공합니다.
- 원본·청크 변경을 검토할 수 있도록 생성 방법과 변경 이력을 남깁니다.

저장소 구조와 데이터 형식은 준비되어 있지만, 실제 수집·청킹·검색·MCP 동작은 구현 및 검증 전입니다. 확정되지 않은 실행 명령이나 도구 규격은 임의로 가정하지 않습니다.

## 저장소 역할

| 저장소 | 담당 |
| --- | --- |
| `knowledge-mcp` | 데이터 출처와 청크, 처리 파이프라인, 검색 및 MCP 기능 |
| [`ai-assistant`](https://github.com/KTcs-KLink/ai-assistant) | 사용자 화면, Assistant 서버·오케스트레이터, 모델 연동, MCP Client |
| [`.github`](https://github.com/KTcs-KLink/.github) | 조직 공통 협업 규칙과 템플릿 |

## 폴더 구조

```text
data/
  sources/       재배포 조건이 확인된 원본 문서
  chunks/        문서별 청크 JSONL
  manifests/     출처, 이용 조건, 파일 정보
schemas/         데이터 형식 정의
src/
  ingestion/     문서 수집·정제·청킹 처리
  mcp/           MCP 서버와 도구
tests/           데이터 및 기능 테스트
docs/adr/        주요 설계 결정 기록
```

## 데이터 등록 절차

1. `data/manifests/sources.csv`에서 사용하지 않은 `SRC-0001` 형식의 `source_id`를 정합니다. ID는 삭제 후에도 재사용하지 않습니다.
2. 출처, 게시일·수집일, 이용 조건, 재배포 허용 여부를 확인합니다. 조건이 불분명하거나 재배포가 허용되지 않으면 원문과 청크 텍스트를 추가하지 말고, 허용되는 범위에서 출처와 확인 상태만 기록합니다.
3. 허용된 원문은 `data/sources/`에, 청크는 `data/chunks/SRC-0001.jsonl`에 둡니다. 청크 각 줄은 [`schemas/chunk.schema.json`](schemas/chunk.schema.json) 형식을 따릅니다.
4. manifest에 `source_id`, 제목, 출처, 이용 조건, 재배포 가능 여부 및 관련 파일 정보를 기록합니다. 파일 해시 등 열은 현재 manifest 형식에 맞춰 관리합니다.
5. 원문과 청크를 함께 변경하는 PR에는 출처, 이용 조건, 청킹 방법, 영향받은 파일과 확인 방법을 적습니다.

원문 변경으로 청크를 다시 만들 때는 같은 `source_id`를 유지하고 변경 이유와 재생성 방법을 PR에 남깁니다. 임베딩과 벡터 인덱스는 재생성 가능한 산출물이므로 Git에 올리지 않습니다.

### 청크 JSONL 예시

```json
{"chunk_id":"SRC-0001-0000","source_id":"SRC-0001","chunk_index":0,"text":"문서에서 추출한 청크 내용","page_start":1,"page_end":1,"section":"문서 제목 > 절 제목","source_uri":"https://example.org/document","chunker_version":"v1"}
```

## 연동 원칙

- MCP 도구의 이름, 입력·출력, 오류 응답은 Assistant 서버의 MCP Client 담당자와 합의해 문서화합니다.
- 검색 결과에는 가능한 범위에서 `source_id`, 문서 제목, 위치와 출처 URI를 포함해 근거를 추적할 수 있게 합니다.
- 데이터가 없거나 검색 결과가 없으면 빈 근거를 임의의 답변으로 대체하지 않고 결과 없음을 명확히 전달합니다.
- 민감정보와 승인되지 않은 KTcs 내부 자료를 저장소, 로그, 테스트 fixture에 포함하지 않습니다.

## 개발 및 기여

기술 스택과 처리 명령, MCP 실행 방법은 구현이 확정된 뒤 이 README에 추가합니다. 주요 설계 선택은 [`docs/adr/`](docs/adr/)에 기록하고, 브랜치·커밋·PR 절차는 조직 [협업 가이드](https://github.com/KTcs-KLink/.github/blob/main/CONTRIBUTING.md)를 따릅니다.

데이터 변경 PR에서는 이용 조건과 출처를 검토할 수 있도록 관련 근거를 함께 적어 주세요. 자동 검사가 준비되기 전에는 PR에 수동 확인 절차와 결과를 남깁니다.

## 관련 문서

- [조직 소개 및 프로젝트 개요](https://github.com/KTcs-KLink/.github)
- [조직 협업 가이드](https://github.com/KTcs-KLink/.github/blob/main/CONTRIBUTING.md)
- [AI Assistant](https://github.com/KTcs-KLink/ai-assistant)
- [청크 스키마](schemas/chunk.schema.json)
- [출처 manifest 안내](data/manifests/README.md)
