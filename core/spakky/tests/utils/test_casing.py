from spakky.core.utils.casing import pascal_to_snake, snake_to_pascal


def test_pascal_to_snake() -> None:
    """PascalCase 문자열이 snake_case로 올바르게 변환되는지 검증한다."""
    assert pascal_to_snake("PascalCase") == "pascal_case"
    assert pascal_to_snake("ISampleClass") == "i_sample_class"


def test_snake_to_pascal() -> None:
    """snake_case 문자열이 PascalCase로 올바르게 변환되는지 검증한다."""
    assert snake_to_pascal("snake_case") == "SnakeCase"
