"""Parse a Markdown outline into a hierarchical node tree.

A node carries:
- ``level``: heading level (0 = synthetic root, 1..6 = H1..H6)
- ``title``: the raw heading text
- ``body``: raw body paragraphs (only populated for leaf nodes)
- ``sentences``: body split into sentences (only on leaves)
- ``children``: child headings (nested)
- ``path``: dot-separated id used for progress tracking

We use ``markdown-it-py`` in its default flavour to get a stable token stream.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt

from youtube_strataread.utils.text import split_sentences


@dataclass
class Node:
    level: int
    title: str
    path: str = ""
    body: str = ""
    sentences: list[str] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def parse_markdown(md_text: str) -> Node:
    md = MarkdownIt("commonmark")
    tokens = md.parse(md_text)

    root = Node(level=0, title="(root)", path="root")
    stack: list[Node] = [root]

    pending_paragraphs: list[str] = []

    def flush_body_into_current() -> None:
        if not pending_paragraphs:
            return
        current = stack[-1]
        current.body = "\n\n".join(pending_paragraphs).strip()
        pending_paragraphs.clear()

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == "heading_open":
            # commit body paragraphs to the *current* top (which is still the
            # previous heading's node) before starting a new heading.
            flush_body_into_current()
            level = int(t.tag[1:])
            # read inline content
            inline = tokens[i + 1]
            title = inline.content.strip() if inline.type == "inline" else ""
            # unwind stack to parent
            while stack and stack[-1].level >= level:
                stack.pop()
            parent = stack[-1] if stack else root
            node = Node(level=level, title=title)
            parent.children.append(node)
            stack.append(node)
            i += 3  # heading_open, inline, heading_close
            continue
        if t.type == "paragraph_open":
            inline = tokens[i + 1]
            if inline.type == "inline":
                pending_paragraphs.append(inline.content.strip())
            i += 3
            continue
        if t.type in {"bullet_list_open", "ordered_list_open"}:
            # Treat each list_item's inline content as a paragraph-line.
            # Simplified: walk until the matching close token.
            depth = 1
            j = i + 1
            items: list[str] = []
            while j < len(tokens) and depth > 0:
                if tokens[j].type in {"bullet_list_open", "ordered_list_open"}:
                    depth += 1
                elif tokens[j].type in {"bullet_list_close", "ordered_list_close"}:
                    depth -= 1
                elif tokens[j].type == "inline":
                    items.append(tokens[j].content.strip())
                j += 1
            if items:
                pending_paragraphs.append("\n".join(f"- {it}" for it in items))
            i = j
            continue
        i += 1

    flush_body_into_current()
    _finalise(root)
    return root


def _finalise(root: Node) -> None:
    _assign_paths(root)
    for n in root.walk():
        if n.is_leaf and n.body:
            n.sentences = split_sentences(n.body)


def _assign_paths(node: Node, prefix: str = "") -> None:
    for idx, child in enumerate(node.children):
        child.path = f"{prefix}{idx + 1}"
        _assign_paths(child, prefix=child.path + ".")


def doc_hash(md_text: str) -> str:
    return hashlib.sha1(md_text.encode("utf-8")).hexdigest()[:16]


def parse_file(path: Path) -> tuple[Node, str]:
    text = path.read_text(encoding="utf-8")
    return parse_markdown(text), doc_hash(text)
