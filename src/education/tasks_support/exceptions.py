"""Q2 실패 기록에서 외부 예외 원문과 개인정보를 제외한다."""


class SafeTaskError(Exception):
    """Q2 실패 목록에는 식별자·안전한 코드만 전달한다."""
