"""Hierarchical selection state machine for the reader.

Responsibilities:
- Render the current node's direct children as a numbered menu.
- Accept number / arrow+enter input.
- ``Esc`` / ``b`` => go up one level.
- ``h``         => go all the way to the root.
- ``q``         => quit.

When the user picks a leaf, :class:`Navigator.choose` returns the node so the
caller can drive the mode-specific body reader.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.keys import Key, key_reader


@dataclass
class Navigator:
    root: Node
    console: Console
    completed: set[str] = field(default_factory=set)
    _current: Node | None = None
    _cursor: int = 0

    def __post_init__(self) -> None:
        self._current = self.root

    # ------------------------------------------------------------------
    # generator API
    # ------------------------------------------------------------------
    def loop(self):
        """Coroutine yielding leaf :class:`Node` instances to be read.

        The caller must ``.send()`` back a status string after each yield:

        * ``"done"`` — leaf finished reading; navigator marks it complete and
          **automatically yields the next leaf in DFS order** (no menu in
          between). When there are no more leaves, we fall back to the root
          menu.
        * ``"back"`` — user pressed Esc/b inside the leaf reader; navigator
          returns to that leaf's parent menu.
        * ``"quit"`` — terminate.

        Entry point: the first iteration always shows the menu. A leaf is only
        yielded after the user explicitly picks one.
        """
        with key_reader() as read:
            while True:
                assert self._current is not None
                current = self._current
                self._render(current)
                key = read()
                if key is None:
                    continue
                action = self._handle(key, current)
                if action == "quit":
                    return
                if action == "leaf":
                    leaf = current.children[self._cursor]
                    # Hand control to the auto-advance sub-coroutine. It will
                    # keep yielding successive leaves until the user presses
                    # back or quits.
                    status = yield from self._read_sequence(leaf)
                    if status == "quit":
                        return
                    # after "back" or "all leaves done" we loop back to the
                    # menu state (``self._current`` was already repositioned
                    # inside ``_read_sequence``).

    def _read_sequence(self, first_leaf: Node):
        """Yield ``first_leaf`` and every subsequent leaf in DFS order.

        Returns the terminal status string (``"back"`` or ``"quit"``). Caller
        values sent via ``.send()`` are handled here.
        """
        leaves = self._all_leaves()
        try:
            idx = leaves.index(first_leaf)
        except ValueError:
            return "back"

        while idx < len(leaves):
            leaf = leaves[idx]
            reason = yield leaf
            if reason == "quit":
                return "quit"
            if reason == "done":
                self.completed.add(leaf.path)
                idx += 1
                continue
            if reason == "back":
                parent = _find_parent(self.root, leaf) or self.root
                self._current = parent
                try:
                    self._cursor = parent.children.index(leaf)
                except ValueError:
                    self._cursor = 0
                return "back"
        # exhausted the tree -- kick the user back to the root menu so they
        # can see every branch ticked ✓.
        self._current = self.root
        self._cursor = 0
        return "back"

    def _all_leaves(self) -> list[Node]:
        """Return every readable leaf in document order (pre-order DFS)."""
        out: list[Node] = []

        def dfs(n: Node) -> None:
            if n.is_leaf and n.level > 0:
                out.append(n)
                return
            for c in n.children:
                dfs(c)

        dfs(self.root)
        return out

    def _is_done(self, node: Node) -> bool:
        """A node is done when every leaf beneath it has been read."""
        if node.is_leaf:
            return node.path in self.completed
        if not node.children:
            return False
        return all(self._is_done(c) for c in node.children)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _handle(self, key: Key, current: Node) -> str:
        k = key.key
        n = len(current.children)
        if k in ("q", "ctrl-c"):
            return "quit"
        if k in ("h",):
            self._current = self.root
            self._cursor = 0
            return "noop"
        if k in ("escape", "b"):
            if current is self.root:
                return "quit"
            # go up: find parent by walking the tree
            self._current = _find_parent(self.root, current) or self.root
            self._cursor = 0
            return "noop"
        if k == "up":
            self._cursor = (self._cursor - 1) % max(n, 1)
            return "noop"
        if k == "down":
            self._cursor = (self._cursor + 1) % max(n, 1)
            return "noop"
        if k.isdigit() and n > 0:
            idx = int(k) - 1
            if 0 <= idx < n:
                self._cursor = idx
                return self._enter_child(current)
        if k in ("enter", "space", "tab") and n > 0:
            return self._enter_child(current)
        return "noop"

    def _enter_child(self, current: Node) -> str:
        child = current.children[self._cursor]
        if child.is_leaf:
            return "leaf"
        self._current = child
        self._cursor = 0
        return "noop"

    def _render(self, current: Node) -> None:
        self.console.clear()
        crumbs = _crumbs(self.root, current)
        self.console.print(
            "[dim]" + " / ".join(crumbs or ["(root)"]) + "[/]"
        )
        self.console.print()
        if current.body and current is not self.root:
            self.console.print(Panel(current.body, title="此节引言", border_style="dim"))
        if not current.children:
            self.console.print("[red]叶子节点，但未包含可读正文；按 Esc 返回。[/]")
            return
        body = Text()
        for i, child in enumerate(current.children):
            marker = "✓" if self._is_done(child) else " "
            cursor = "▶" if i == self._cursor else " "
            title = f"{cursor} {i + 1}) [{marker}] {child.title or '(untitled)'}"
            style = "bold cyan" if i == self._cursor else ""
            body.append(title + "\n", style=style)
        self.console.print(body)
        self.console.print()
        self.console.print(
            "[dim]↑/↓ 或数字选择, Enter/Tab 进入, Esc/b 返回, h 回根, q 退出[/]"
        )


def _find_parent(root: Node, target: Node) -> Node | None:
    for n in root.walk():
        if target in n.children:
            return n
    return None


def _crumbs(root: Node, target: Node) -> list[str]:
    if target is root:
        return []
    # walk: find path from root to target by DFS
    path: list[Node] = []

    def dfs(node: Node) -> bool:
        if node is target:
            return True
        for c in node.children:
            if dfs(c):
                path.append(c)
                return True
        return False

    if dfs(root):
        return [n.title for n in reversed(path)]
    return []
