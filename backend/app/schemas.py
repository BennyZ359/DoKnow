"""Validate substantive learner input before recording evidence."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
NoteContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=1000000)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Tags = Annotated[list[Tag], Field(max_length=20)]


def require_meaningful(value: str, minimum: int) -> str:
    if len("".join(value.split())) < minimum:
        raise ValueError(f"请至少写 {minimum} 个非空白字符，用自己的话描述。")
    return value


class RequestModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def portable_text(cls, value):
        if isinstance(value, list):
            for item in value:
                cls.portable_text(item)
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
    question_id: Annotated[str, StringConstraints(max_length=40)] | None = None
    token: Annotated[str, StringConstraints(max_length=80)] | None = None


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
    content: NoteContent
    tags: Tags = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def normalized_tags(cls, value):
        return normalize_tags(value)

    @field_validator("content")
    @classmethod
    def meaningful(cls, value: str):
        return require_meaningful(value, 10)


def normalize_tags(value: list[str]) -> list[str]:
    result = []
    seen = set()
    for tag in value:
        if any(ord(char) < 32 or ord(char) == 127 for char in tag):
            raise ValueError("标签不能包含换行或控制字符。")
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            result.append(tag)
    return result


class VersionedUpdate(RequestModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def editable_fields(self):
        fields = self.model_fields_set - {"version"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("请提供要修改的字段，字段值不能为 null。")
        return self


class GoalUpdate(VersionedUpdate):
    title: Title | None = None
    motivation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = None
    daily_minutes: Annotated[int, Field(ge=10, le=180, strict=True)] | None = None


class KnowledgeUpdate(VersionedUpdate):
    title: Title | None = None
    content: NoteContent | None = None
    tags: Tags | None = None

    @field_validator("content")
    @classmethod
    def meaningful(cls, value):
        return require_meaningful(value, 10) if value is not None else value

    @field_validator("tags")
    @classmethod
    def normalized_tags(cls, value):
        return normalize_tags(value) if value is not None else value


class QuestionInput(RequestModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=4000)]
