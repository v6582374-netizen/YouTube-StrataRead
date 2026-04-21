from youtube_strataread.reader.bionic_render import render_str
from youtube_strataread.reader.doc_tree import parse_markdown

SAMPLE_MD = """# 为什么深度学习有效？
一些前言。

## 起源
### 感知机
讲话人: 感知机是第一代神经网络。
讲话人: 它由 Rosenblatt 提出。

### 反向传播
讲话人: 反向传播让多层网络成为可能。

## 爆发
### 算力与数据
讲话人: GPU 提供了算力。

# 接下来会发生什么？
## 多模态
讲话人: 图像与文本的融合。
"""


def test_parse_markdown_builds_tree_and_leaves():
    root = parse_markdown(SAMPLE_MD)
    assert len(root.children) == 2
    # first H1 should have two H2 children
    h1 = root.children[0]
    assert len(h1.children) == 2
    # leaves are the H3 nodes + H2 under the second H1 (no H3 there)
    leaves = [n for n in root.walk() if n.is_leaf and n.level > 0]
    assert len(leaves) >= 4
    # every leaf has sentences when body exists
    for leaf in leaves:
        if leaf.body:
            assert leaf.sentences


def test_bionic_render_english_bolds_prefix():
    # len("Reading")==7, ceil(7*0.4)==3 -> "Rea"
    s = render_str("Reading")
    assert s == "[bold]Rea[/]ding"


def test_bionic_render_cjk_first_half():
    s = render_str("深度学习")
    # first two chars should be wrapped in [bold]
    assert s.startswith("[bold]深度[/]")
    assert s.endswith("学习")


def test_bionic_render_leaves_punct():
    s = render_str("Hello, world!")
    assert ", " in s and "!" in s


def test_parse_markdown_preserves_thematic_breaks_in_non_leaf_body():
    root = parse_markdown(
        "# Chapter\n"
        "Intro paragraph.\n\n"
        "---\n\n"
        "After break.\n\n"
        "## Leaf\n"
        "Body.\n"
    )

    chapter = root.children[0]
    assert chapter.body == "Intro paragraph.\n\n---\n\nAfter break."
