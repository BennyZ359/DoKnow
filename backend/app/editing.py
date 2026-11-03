"""Small record edits are separate from courses and their learning evidence."""

import re

from .models import KnowledgeEntry
from .serialization import knowledge_data


class EditConflict(Exception):
    pass


def require_version(item, version: int):
    if item.version != version:
        raise EditConflict


def filter_notes(items, q: str = "", tag: str = "", source: str = ""):
    # Match the browser's locale-independent Unicode lowercasing.
    query = q.strip().lower()
    tag = tag.strip().lower()
    return [item for item in items if
            (not query or query in f"{item.title} {item.content} {' '.join(item.tags or [])}".lower())
            and (not tag or tag in {value.lower() for value in item.tags or []})
            and (not source or ("import" if item.source not in {"note", "reflection"} else item.source) == source)]


def markdown_text(value: str) -> str:
    # Metadata is one literal Markdown line; only the learner's body is Markdown.
    return re.sub(r"([\\`*_{}\[\]<>#|~])", r"\\\1", " ".join(value.split()))


def export_note(item: KnowledgeEntry) -> str:
    value = knowledge_data(item, detailed=True)
    source = {"note": "手写笔记", "reflection": "学习复盘"}.get(item.source, item.source)
    lines = [f"# {markdown_text(item.title)}", "", f"- 来源：{markdown_text(source)}",
             f"- 创建时间：{value['created_at']}", f"- 更新时间：{value['updated_at']}",
             f"- 版本：{item.version}", f"- 标签：{', '.join(markdown_text(tag) for tag in value['tags']) or '无'}",
             "", "## 正文", "", item.content]
    original = value["original"]
    if original != {"title": item.title, "content": item.content}:
        lines.extend(["", "## 原始记录（保留）", "", f"原始标题：{markdown_text(original['title'])}",
                      "", original["content"]])
    return "\n".join(lines) + "\n"
