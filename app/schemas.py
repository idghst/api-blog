from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _camel_case(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


PostType = Literal["guide", "news", "stock"]
PostLocale = Literal["ko", "en"]


class PostOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        extra="ignore",
        populate_by_name=True,
    )

    slug: str
    title: str
    description: str
    type: PostType
    tags: list[str]
    body: str
    ticker: str | None = None
    cover: str | None = None
    locale: PostLocale
    draft: bool
    published_at: datetime | None = None
    updated_at: datetime
    created_at: datetime


class PostList(BaseModel):
    items: list[PostOut]
    count: int = Field(ge=0)


class PostCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    slug: Annotated[str, Field(min_length=1, max_length=200)]
    title: Annotated[str, Field(min_length=1, max_length=500)]
    description: Annotated[str, Field(max_length=2_000)] = ""
    type: PostType
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list
    )
    body: Annotated[str, Field(min_length=1)]
    ticker: Annotated[str | None, Field(max_length=40)] = None
    cover: Annotated[str | None, Field(max_length=2_000)] = None
    locale: PostLocale = "ko"
    draft: bool = False
    published_at: datetime | None = None


class PostPatch(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    slug: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    title: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    description: Annotated[str | None, Field(max_length=2_000)] = None
    type: PostType | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = None
    body: Annotated[str | None, Field(min_length=1)] = None
    ticker: Annotated[str | None, Field(max_length=40)] = None
    cover: Annotated[str | None, Field(max_length=2_000)] = None
    locale: PostLocale | None = None
    draft: bool | None = None
    published_at: datetime | None = None

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> "PostPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


CommentAuthor = Annotated[str, Field(min_length=1, max_length=80)]
CommentBody = Annotated[str, Field(min_length=1, max_length=2_000)]
BlobMime = Literal["image/png", "image/jpeg", "image/webp", "image/gif"]


class CommentOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        extra="ignore",
        populate_by_name=True,
    )

    id: int
    author: str
    body: str
    created_at: datetime


class CommentList(BaseModel):
    items: list[CommentOut]
    count: int = Field(ge=0)


class CommentCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    author: CommentAuthor
    body: CommentBody


class BlobMeta(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        extra="ignore",
        populate_by_name=True,
    )

    id: str
    description: str
    mime_type: BlobMime
    created_at: datetime


class BlobCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    description: Annotated[str, Field(min_length=1, max_length=500)]
    mime_type: BlobMime
    content_base64: Annotated[str, Field(min_length=1)]
