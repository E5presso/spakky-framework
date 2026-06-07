# spakky-task

> `spakky-task`는 task handler, schedule, crontab, direct execution 계약을 제공합니다.

태스크 추상화 — 스케줄링, 디스패치

## 플러그인 진입점

::: spakky.task.main
options:
show_root_heading: false

## 스테레오타입

::: spakky.task.stereotype.task_handler
options:
show_root_heading: false

::: spakky.task.stereotype.schedule
options:
show_root_heading: false

::: spakky.task.stereotype.crontab
options:
show_root_heading: false

## 인터페이스

::: spakky.task.interfaces.task_result
options:
show_root_heading: false

## 직접 실행

::: spakky.task.direct
options:
show_root_heading: false

## 후처리기

::: spakky.task.post_processor
options:
show_root_heading: false

## 에러

::: spakky.task.error
options:
show_root_heading: false

## 추가 모듈

::: spakky.task.main
    options:
      show_root_heading: false
