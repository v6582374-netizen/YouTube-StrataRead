from youtube_strataread.utils.text import slugify, split_sentences


def test_slugify_basic():
    s = slugify("Hello World 2024 🚀!")
    assert s == "Hello-World-2024"


def test_slugify_chinese():
    s = slugify("深度学习：从入门到放弃!")
    assert "深度学习" in s


def test_slugify_empty_falls_back_to_hash():
    s = slugify("")
    assert s.startswith("video-")


def test_slugify_truncates():
    long = "a" * 200
    assert len(slugify(long, max_len=32)) <= 32


def test_split_sentences_cjk():
    txt = "讲话人: 今天我们来聊聊深度学习。它其实并不神秘！你同意吗？"
    sents = split_sentences(txt)
    assert len(sents) >= 3


def test_split_sentences_english():
    txt = "Hello there. How are you? I'm fine!"
    sents = split_sentences(txt)
    assert sents == ["Hello there.", "How are you?", "I'm fine!"]
