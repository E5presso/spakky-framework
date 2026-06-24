# 애플리케이션 경계

> 외부 세계(HTTP·CLI·gRPC)와 데이터베이스를 Spakky 컴포넌트 모델에 붙이는 입출력 경계입니다. 코어에서 만든 UseCase를 어떤 채널로 노출할지 여기서 고릅니다.

만들려는 앱의 경계가 정해졌다면 해당 채널의 **기초**부터 보세요.

## 기초

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [FastAPI 통합](../guides/fastapi.md) | HTTP API를 FastAPI 위에 올리기 |
| [CLI (Typer)](../guides/typer.md) | Typer 기반 CLI 애플리케이션 만들기 |
| [gRPC 통합](../guides/grpc.md) | code-first gRPC 서비스 정의하기 |
| [데이터베이스 (SQLAlchemy)](../guides/sqlalchemy.md) | 데이터베이스와 트랜잭션 붙이기 |

## 심화

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [gRPC 심화](../guides/grpc-advanced.md) | 무설정 변환·스트리밍·인터셉터 |
