# ADR-0026: 구조화 출력과 도구 스키마의 JSON Schema 2020-12 전체 지원

- **상태**: Accepted
- **날짜**: 2026-11-25
- **대체**: [ADR-0015](0015-multi-provider-llm-official-sdk-adapters.md) §6의 portable subset, [ADR-0018](0018-typed-agent-output-and-context.md) §2의 keyword subset과 순환 reference 거부

## 맥락 (Context)

v13.1.1까지 `LlmJsonCodec`은 구조화 출력의 출력 스키마와 도구의 입력 스키마를 JSON Schema의 일부(portable subset)로만 검증했습니다. Subset 밖의 키워드가 든 스키마는 `LlmResponseError`로 거부됐습니다. Core `AgentExecutionSpec.output_type`도 같은 subset을 강제했습니다. 그래서 Pydantic이 만드는 `minLength`, `pattern`, `minimum`, `format`, 설명이 붙은 `$ref`, 재귀 모델이 정의 시점에 거부됐습니다(#585).

JSON Schema 2020-12 명세(https://json-schema.org/draft/2020-12)를 기준으로 키워드를 나누면 다음과 같습니다. "v13.1.1"은 바꾸기 전에 codec이 받던 범위입니다.

| 어휘(vocabulary) | 키워드 | v13.1.1 | 이 ADR 뒤 |
|---|---|---|---|
| Core | `$schema`, `$id`, `$anchor`, `$comment` | 받음(검증 없음) | 받음 |
| Core | `$ref`, `$defs` | 거부 | 검증 |
| Core | `$dynamicRef`, `$dynamicAnchor`, `$vocabulary` | 거부 | 검증 |
| Applicator | `anyOf` | 검증 | 검증 |
| Applicator | `allOf`, `oneOf`, `not` | 거부 | 검증 |
| Applicator | `if`, `then`, `else`, `dependentSchemas` | 거부 | 검증 |
| Applicator | `properties`, `additionalProperties` | 검증(`type: object` 필요) | 검증(`type` 없이도) |
| Applicator | `patternProperties`, `propertyNames` | 거부 | 검증 |
| Applicator | `prefixItems`, `items` | 검증(`type: array` 필요) | 검증 |
| Applicator | `contains` | 거부 | 검증 |
| Unevaluated | `unevaluatedItems`, `unevaluatedProperties` | 거부 | 검증 |
| Validation | `type`(문자열과 배열) | 검증 | 검증 |
| Validation | `enum` | 검증(빈 배열 거부) | 검증(빈 배열은 어떤 값도 통과하지 않음) |
| Validation | `const` | 거부 | 검증 |
| Validation | `multipleOf`, `maximum`, `exclusiveMaximum`, `minimum`, `exclusiveMinimum` | 거부 | 검증 |
| Validation | `maxLength`, `minLength`, `pattern` | 거부 | 검증 |
| Validation | `maxItems`, `minItems` | 검증 | 검증 |
| Validation | `uniqueItems`, `maxContains`, `minContains` | 거부 | 검증 |
| Validation | `maxProperties`, `minProperties`, `required`, `dependentRequired` | `required`만 검증 | 검증 |
| Meta-data | `title`, `description`, `default`, `deprecated`, `readOnly`, `writeOnly`, `examples` | 받음 | 받음(annotation) |
| Format annotation | `format` | 거부 | annotation(2020-12 기본) |
| Content | `contentEncoding`, `contentMediaType`, `contentSchema` | 거부 | annotation(2020-12 기본) |
| 하위 스키마 | `true`, `false` | `items`, `additionalProperties`에서만 | 모든 자리 |

공급자의 strict 구조화 출력은 JSON Schema의 일부만 받습니다. 프레임워크가 전체를 검증해도, 공급자가 받지 않는 키워드가 든 스키마를 그대로 보내면 요청이 거부됩니다.

## 결정 동인 (Decision Drivers)

- 사용자의 스키마를 거부하지 않습니다. 근거는 2020-12 공식 테스트 스위트의 통과입니다.
- 원격 `$ref`를 네트워크로 가져오지 않습니다. 모델 출력 검증이 외부 요청을 만들면 안 됩니다.
- 공급자에게는 그 공급자의 공식 문서가 받는 범위로 보냅니다. 범위 밖의 제약은 프레임워크가 출력에서 검증합니다.
- Python 3.12–3.14와 Linux, macOS, Windows에서 같은 결과를 냅니다.

## 고려한 대안 (Considered Options)

### 대안 A: 자체 검증기를 키운다

v13.1.1의 codec에 키워드를 하나씩 더합니다. `$dynamicRef`, `unevaluated*`, ECMA-262 정규식의 정확한 구현은 큰 작업이고, 명세를 따르는지의 근거를 직접 만들어야 합니다. 채택하지 않았습니다.

### 대안 B: `jsonschema`(python-jsonschema) 4.26.0

MIT 라이선스이고 lock에 이미 다른 패키지의 의존으로 들어 있습니다. 2026-11-25에 공식 테스트 스위트(commit `e2a68a15`)의 2020-12 필수 테스트 1305개를 돌렸더니 10개가 실패했습니다. Python `re`가 ECMA-262의 `\p{L}` 같은 Unicode property escape를 지원하지 않아 `pattern`과 `patternProperties`에서 9개, custom meta-schema의 `$vocabulary`에서 1개입니다. 채택하지 않았습니다.

### 대안 C: `jsonschema-rs` 0.63.1

MIT 라이선스의 Rust 구현과 Python binding입니다. 같은 1305개를 모두 통과했습니다. `offline=True`로 원격 가져오기를 끌 수 있고, `registry`로 외부 스키마를 미리 등록할 수 있습니다. abi3 wheel이 Linux(glibc, musl), macOS, Windows에 있고 타입 정보(`py.typed`)를 함께 줍니다.

## 결정 (Decision)

### 1. Codec은 `jsonschema-rs`로 2020-12 전체를 검증합니다

`LlmJsonCodec.validate`와 새 `check_schema`는 `jsonschema_rs.Draft202012Validator(offline=True, validate_formats=False)`를 씁니다. `format`은 2020-12 기본대로 annotation입니다. 원격 `$ref`는 가져오지 않습니다. 애플리케이션은 `LlmJsonCodec(external_schemas=...)`로 외부 스키마를 retrieval URI에 등록할 수 있습니다. `spakky-llm`의 테스트는 공식 스위트의 2020-12 필수 테스트 1305개를 고정 commit의 fixture로 매번 돌립니다. `format-assertion` 태그와 `optional`, `proposals` 디렉터리는 2020-12의 필수 범위가 아니므로 돌리지 않습니다.

### 2. 거부의 이유는 키워드와 이유만 싣습니다

`LlmResponseError.details`는 `{"schema_keyword": ..., "reason": ...}`입니다. `reason`은 `invalid_schema`(meta-schema 위반), `unresolvable_reference`, `value_mismatch` 중 하나입니다. `properties`, `$defs` 같은 이름 지도의 키(사용자가 정한 이름)는 키워드로 보고하지 않습니다. 스키마의 값과 모델 출력 값은 싣지 않습니다.

### 3. Core `output_type`은 Pydantic 스키마를 그대로 둡니다

키워드 허용 목록을 없앱니다. 재귀하지 않는 local `$ref`는 계속 펼칩니다. `$ref` 옆의 annotation(`description` 등)은 펼친 스키마에 붙이고, 그 밖의 키워드는 `allOf`로 2020-12의 뜻을 지킵니다. 재귀하는 `$ref`는 `#/$defs/...`로 남기고 루트에 필요한 정의만 둡니다.

### 4. 공급자에게는 문서가 받는 범위로 보냅니다

`spakky.plugins.llm.schema_wire`가 공급자별 wire 사본을 만듭니다. 사본은 원래 스키마와 뜻이 같거나 더 넓습니다(키워드를 빼면 받는 값이 늘어납니다). 프레임워크는 모델 출력을 원래 스키마 전체로 검증합니다.

| 공급자 | 근거 문서(2026-11-25 확인) | strict wire | strict로 보낼 수 없을 때 |
|---|---|---|---|
| OpenAI Chat·Responses | https://developers.openai.com/api/docs/guides/structured-outputs | `not`, `dependentRequired`를 빼고 `oneOf`를 `anyOf`로 씁니다. 모든 object를 닫고 모든 property를 `required`에 넣습니다. | `allOf`, `if`/`then`/`else`, `dependentSchemas`, `additionalProperties` 스키마, object가 아닌 루트, 루트 `anyOf`: 원래 스키마를 `strict: false`로 보냅니다(구조화 출력과 도구 모두). |
| Anthropic | https://platform.claude.com/docs/en/build-with-claude/structured-outputs | 숫자·문자열 길이 제약과 `minItems` 0·1 밖의 배열 제약, `not`, 스칼라가 아닌 `enum`·`const`를 빼고, `minItems`는 1로 줄입니다. `oneOf`는 `anyOf`로, `type`·`properties` 옆의 `anyOf`는 각 branch로 옮깁니다. 모든 object를 닫습니다. | 재귀 스키마, `additionalProperties` 스키마, 옮길 수 없는 `anyOf`: 도구는 `strict: false`로, 구조화 출력은 `output_config` 없이 스키마를 담은 system 지시문으로 요청합니다. |
| Google Gemini | https://ai.google.dev/gemini-api/docs/structured-output | 문서에 있는 키워드와 예시에 쓰인 `anyOf`, `$ref`, `$defs`만 남기고 나머지를 뺍니다. `const`는 값 하나의 `enum`으로, `oneOf`는 `anyOf`로 씁니다. null이 아닌 type이 둘 이상인 `type` 배열은 `anyOf`로 나눕니다(#584). | 없음. 키워드를 빼면 항상 보낼 수 있습니다. |
| vLLM(OpenAI-compatible) | 확인하지 못함 | 원래 스키마를 `structured_outputs.json`에 그대로 보냅니다. | — |

## 결과 (Consequences)

### 긍정적

- 2020-12의 필수 테스트를 모두 통과하는 검증을 씁니다.
- 공급자가 받지 않는 키워드가 든 스키마로도 요청이 거부되지 않습니다.
- Pydantic의 제약 키워드와 재귀 모델을 `output_type`에 쓸 수 있습니다.

### 부정적

- `spakky-llm`이 native wheel 의존(`jsonschema-rs`)을 더합니다.
- 공급자가 닫힌 object를 요구하는 strict wire는 원래 스키마보다 좁습니다(추가 property 금지, OpenAI의 required-all). 이것은 v13.1.1과 같습니다.
- 넓힌 wire나 느슨한 요청에서는 모델이 원래 스키마에 맞지 않는 값을 낼 수 있습니다. 그 값은 `LlmResponseError`(`value_mismatch`)가 됩니다.
- Anthropic 구조화 출력의 지시문 요청은 grammar 제약이 없습니다. Anthropic 문서에는 `output_config.format`의 non-strict 형태가 없습니다.

### 중립적

- 원격 `$ref`(외부 URI)는 어느 공급자 경로에서도 받지 않습니다. 가져오지 않기로 했으므로 `unresolvable_reference`로 거부됩니다. 공급자 adapter는 외부 스키마를 등록하지 않습니다. 같은 스키마를 `$defs`에 넣으면 받습니다.

- OpenAI의 `strict: false`가 strict 목록 밖의 키워드를 받는지, Gemini의 `parametersJsonSchema`가 구조화 출력 문서의 범위를 그대로 따르는지는 문서에서 확인하지 못했습니다. 실제 호출로도 확인하지 않았습니다.
- v13.1.1의 `details` 이유(`unsupported_keyword`, `duplicate_type` 등)는 `invalid_schema`로 합쳐집니다.

## 참고 자료

- JSON Schema 2020-12: https://json-schema.org/draft/2020-12/json-schema-core, https://json-schema.org/draft/2020-12/json-schema-validation
- JSON-Schema-Test-Suite: https://github.com/json-schema-org/JSON-Schema-Test-Suite (commit `e2a68a15cd490750fd6b95e604e4054d7d978d1f`)
- `jsonschema-rs`: https://pypi.org/project/jsonschema-rs/
- 이슈 #583, #585
