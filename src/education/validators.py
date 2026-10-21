"""교육 콘텐츠의 모델·프리셋 입력에 동일한 JSON 구조 계약을 적용한다."""

from django.core.exceptions import ValidationError


def validate_text_list(values):
    """목표·추천대상의 문자열 목록을 검증하며 입력값을 변경하지 않는다.

    Args:
        values: 비어 있지 않은 문자열들로 구성된 목록.

    Raises:
        ValidationError: 목록이 비었거나 문자열 외 값·공백 문자열을 포함한 경우.
    """
    if not isinstance(values, list) or not values:
        raise ValidationError("비어 있지 않은 문자열 목록이 필요합니다.")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValidationError("비어 있지 않은 문자열이 필요합니다.")


def validate_curriculum(curriculum):
    """중복 없는 양의 시수와 순서대로 구성된 교시·필수 설명을 검증한다.

    각 과정은 periods와 lessons를 가지며 시수와 교시 목록 길이가 같아야 한다.
    교시는 1부터 연속된 period와 topic·activity·description 문자열을 가진다.
    boolean은 정수 시수·교시 번호로 허용하지 않으며 입력값은 변경하지 않는다.

    Args:
        curriculum: 위 구조의 과정 객체로 구성된 비어 있지 않은 목록.

    Raises:
        ValidationError: 구조·시수·교시 순서·필수 문자열이 계약과 다른 경우.
    """
    if not isinstance(curriculum, list) or not curriculum:
        raise ValidationError("커리큘럼 목록이 필요합니다.")
    periods = set()
    for course in curriculum:
        if not isinstance(course, dict):
            raise ValidationError("과정은 시수와 교시 목록을 가진 객체여야 합니다.")
        length = course.get("periods")
        lessons = course.get("lessons")
        if type(length) is not int or length < 1 or length in periods:
            raise ValidationError("시수 구성이 올바르지 않습니다.")
        periods.add(length)
        if not isinstance(lessons, list) or len(lessons) != length:
            raise ValidationError("시수와 교시 수가 다릅니다.")
        for number, lesson in enumerate(lessons, 1):
            if not isinstance(lesson, dict):
                raise ValidationError("교시는 번호와 설명을 가진 객체여야 합니다.")
            period = lesson.get("period")
            if type(period) is not int or period != number:
                raise ValidationError("교시 순서가 올바르지 않습니다.")
            validate_text_list(
                [lesson.get(key) for key in ("topic", "activity", "description")]
            )
