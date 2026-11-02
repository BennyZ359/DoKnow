"""Validate substantive learner input before recording evidence."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


def require_meaningful(value: str, minimum: int) -> str:
    if len("".join(value.split())) < minimum:
        raise ValueError(f"请至少写 {minimum} 个非空白字符，用自己的话描述。")
    return value


class RequestModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def portable_text(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("输入不能包含空字符，请删除后重试。")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("输入包含无法保存的 Unicode 字符，请重新输入。")
        return value


class GoalInput(RequestModel):
    title: Title
    motivation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    daily_minutes: int = Field(default=30, ge=10, le=180, strict=True)


class ChatInput(RequestModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class LearnInput(RequestModel):
    reflection: Content

    @field_validator("reflection")
    @classmethod
    def meaningful(cls, value: str):
        return require_meaningful(value, 20)


class PracticeInput(RequestModel):
    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SubmissionInput(RequestModel):
    content: Content

    @field_validator("content")
    @classmethod
    def meaningful(cls, value: str):
        return require_meaningful(value, 20)


class ReflectionInput(RequestModel):
    content: Content
    takeaway: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    change: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]

    @field_validator("content")
    @classmethod
    def meaningful_content(cls, value: str):
        return require_meaningful(value, 20)

    @field_validator("takeaway", "change")
    @classmethod
    def meaningful_insight(cls, value: str):
        return require_meaningful(value, 10)


class ReviewInput(RequestModel):
    rating: Literal[1, 2, 3, 4]
    answer: Content

    @field_validator("rating", mode="before")
    @classmethod
    def integer_rating(cls, value):
        if type(value) is not int:
            raise ValueError("自评应为 1 到 4 的整数。")
        return value

    @field_validator("answer")
    @classmethod
    def meaningful(cls, value: str):
        return require_meaningful(value, 20)


class KnowledgeInput(RequestModel):
    title: Title
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=1000000)]

    @field_validator("content")
    @classmethod
    def meaningful(cls, value: str):
        return require_meaningful(value, 10)


class QuestionInput(RequestModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=4000)]
