from __future__ import annotations

from typing import Literal

ResourceType = Literal["book", "movie", "tv_series"]

RESOURCE_TYPE_LABELS: dict[ResourceType, str] = {
    "book": "书籍",
    "movie": "电影",
    "tv_series": "电视剧",
}

RESOURCE_TYPE_SHORT_LABELS: dict[ResourceType, str] = {
    "book": "BOOK",
    "movie": "MOVIE",
    "tv_series": "TV",
}

RESOURCE_TYPE_AUTHOR_LABELS: dict[ResourceType, str] = {
    "book": "作者",
    "movie": "导演",
    "tv_series": "主创",
}

RESOURCE_TYPE_SCOPE_HINTS: dict[ResourceType, str] = {
    "book": "围绕书中的人物、情节、章节结构、主题、论证和写作手法出题，不要把影视改编、读后感或常识补进来。",
    "movie": "围绕电影的真实剧情、人物关系、关键场景、主题表达和创作信息出题，不要把同名作品、影评、花絮或别的版本混进来。",
    "tv_series": "围绕电视剧的真实剧情、人物关系、关键场景、集数进展和主创信息出题，不要把电影版、同名剧、剪辑总结或二创内容混进来。",
}


def normalize_resource_type(value: str | None) -> ResourceType:
    if value in RESOURCE_TYPE_LABELS:
        return value
    return "book"


def resource_type_label(value: str | None) -> str:
    return RESOURCE_TYPE_LABELS.get(normalize_resource_type(value), "书籍")


def resource_type_short_label(value: str | None) -> str:
    return RESOURCE_TYPE_SHORT_LABELS.get(normalize_resource_type(value), "BOOK")


def resource_author_label(value: str | None) -> str:
    return RESOURCE_TYPE_AUTHOR_LABELS.get(normalize_resource_type(value), "作者")


def resource_type_scope_hint(value: str | None) -> str:
    return RESOURCE_TYPE_SCOPE_HINTS.get(normalize_resource_type(value), RESOURCE_TYPE_SCOPE_HINTS["book"])
