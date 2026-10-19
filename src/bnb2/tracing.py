"""5단계: Langfuse 트레이싱 + 개인정보 마스킹."""

import os
import re
from functools import cache

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.span_filter import is_langfuse_span

PATTERNS = [
    (re.compile(r"01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}"), "[전화번호]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[이메일]"),
]


def mask_text(text: str) -> str:
    for pattern, label in PATTERNS:
        text = pattern.sub(label, text)
    # 패턴으로 못 잡는 값(주소, 와이파이 비밀번호 등)은 .env 의 MASK_TERMS 에 쉼표로 적는다.
    for term in filter(None, (t.strip() for t in os.getenv("MASK_TERMS", "").split(","))):
        text = text.replace(term, "[비공개]")
    return text


def mask(*, data, **kwargs):
    """Langfuse 로 보내기 직전의 모든 입력·출력에 적용된다. 실제 처리(Claude 호출 등)에는 원문이 쓰인다."""
    if isinstance(data, str):
        return mask_text(data)
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [mask(data=v) for v in data]
    return data


@cache
def client() -> Langfuse:
    # 처음 한 번만 만든다. CallbackHandler 는 이 클라이언트(마스킹 포함)를 가져다 쓴다.
    # is_langfuse_span: anthropic SDK 가 자체로 남기는 기록(anthropic.messages.create)을 빼서,
    # ChatAnthropic 기록과 겹쳐 토큰·비용이 2배로 잡히지 않게 한다.
    return Langfuse(mask=mask, should_export_span=is_langfuse_span)


def handler() -> CallbackHandler:
    client()
    return CallbackHandler()
