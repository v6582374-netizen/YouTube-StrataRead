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


def test_split_sentences_comma_and_semicolon_cjk():
    # Chinese comma / semicolon should terminate a clause; 、/：/“” should not.
    txt = "今天天气，真好；我有苹果、香蕉和橙子。"
    sents = split_sentences(txt)
    assert sents == ["今天天气，", "真好；", "我有苹果、香蕉和橙子。"]


def test_split_sentences_does_not_split_on_enumeration_or_colon():
    txt = "他说：我喜欢苹果、香蕉和葡萄。"
    sents = split_sentences(txt)
    assert sents == ["他说：我喜欢苹果、香蕉和葡萄。"]


def test_split_sentences_glues_closing_quote():
    txt = "他说：“你好。”然后走了。"
    sents = split_sentences(txt)
    # The inner 。 absorbs the trailing ” so the quoted clause stays together.
    assert sents == ["他说：“你好。”", "然后走了。"]


def test_split_sentences_english_comma_semicolon():
    txt = "Hello, world; goodbye."
    sents = split_sentences(txt)
    assert sents == ["Hello,", "world;", "goodbye."]


def test_split_sentences_preserves_abbreviations_and_decimals():
    txt = "We live in the U.S.A. Pi is 3.14, roughly."
    sents = split_sentences(txt)
    # U.S.A. should NOT split mid-abbreviation; the closing '.' followed by a
    # space does. The decimal 3.14 stays intact; final comma+period form the
    # boundary.
    assert sents == ["We live in the U.S.A.", "Pi is 3.14,", "roughly."]
