"""Tests for auto-advance + parent checkmark semantics in the Navigator.

We bypass the key_reader / render bits and poke the internal methods directly
because those require a live TTY.
"""
from __future__ import annotations

from rich.console import Console

from bionic_youtube.reader.doc_tree import parse_markdown
from bionic_youtube.reader.navigator import Navigator

SAMPLE_MD = """# 为什么深度学习有效？
## 起源
### 感知机
感知机是第一代神经网络。它由 Rosenblatt 提出。
### 反向传播
反向传播让多层网络成为可能。
## 爆发
### 算力与数据
GPU 提供了算力。
# 接下来会发生什么？
## 多模态
图像与文本的融合。
"""


def _make_nav() -> Navigator:
    root = parse_markdown(SAMPLE_MD)
    return Navigator(root=root, console=Console())


def test_all_leaves_in_document_order() -> None:
    nav = _make_nav()
    leaves = nav._all_leaves()
    titles = [n.title for n in leaves]
    assert titles == ["感知机", "反向传播", "算力与数据", "多模态"]


def test_is_done_bubbles_up() -> None:
    nav = _make_nav()
    root = nav.root
    h1 = root.children[0]  # "为什么深度学习有效？"
    h2_origin = h1.children[0]  # "起源"

    # Nothing done yet
    assert not nav._is_done(h1)
    assert not nav._is_done(h2_origin)

    # Mark "感知机" leaf done -> 起源 not yet (反向传播 missing)
    leaf_perceptron = h2_origin.children[0]
    nav.completed.add(leaf_perceptron.path)
    assert not nav._is_done(h2_origin)

    # Mark 反向传播 too -> 起源 done; 但 爆发 未读，所以 H1 still not done.
    leaf_backprop = h2_origin.children[1]
    nav.completed.add(leaf_backprop.path)
    assert nav._is_done(h2_origin)
    assert not nav._is_done(h1)

    # Finish the 爆发 subtree -> H1 done.
    h2_boom = h1.children[1]  # "爆发"
    leaf_gpu = h2_boom.children[0]
    nav.completed.add(leaf_gpu.path)
    assert nav._is_done(h1)


def test_read_sequence_auto_advances_and_completes() -> None:
    """Drive the inner sub-coroutine manually to prove auto-advance works."""
    nav = _make_nav()
    leaves = nav._all_leaves()
    gen = nav._read_sequence(leaves[0])
    # first leaf
    first = next(gen)
    assert first.title == "感知机"
    # send done => should yield next leaf without any menu in between
    second = gen.send("done")
    assert second.title == "反向传播"
    third = gen.send("done")
    assert third.title == "算力与数据"
    fourth = gen.send("done")
    assert fourth.title == "多模态"
    # finishing the last leaf terminates the coroutine
    try:
        gen.send("done")
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        # _read_sequence returns "back" to kick caller back to root menu
        assert stop.value == "back"
    # all 4 leaves marked done
    assert len(nav.completed) == 4


def test_read_sequence_back_returns_to_parent_menu() -> None:
    nav = _make_nav()
    leaves = nav._all_leaves()
    gen = nav._read_sequence(leaves[0])
    next(gen)  # yields "感知机"
    try:
        gen.send("back")
        raise AssertionError("expected StopIteration")
    except StopIteration as stop:
        assert stop.value == "back"
    # navigator should now be positioned on the parent of "感知机"
    assert nav._current is not None
    assert nav._current.title == "起源"
    # and cursor should point at 感知机 (index 0 of 起源's children)
    assert nav._cursor == 0
