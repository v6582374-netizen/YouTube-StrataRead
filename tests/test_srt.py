from bionic_youtube.downloader.srt import cues_to_lines, load_cues

SAMPLE = """1
00:00:01,000 --> 00:00:03,000
<font color="#fff">Hello</font> world

2
00:00:03,100 --> 00:00:05,000
- hi there [Music]

3
00:00:05,100 --> 00:00:07,000
(applause)

4
00:00:07,100 --> 00:00:09,000
we are back
"""


def test_load_cues_strips_noise_and_tags():
    cues = load_cues(SAMPLE)
    texts = [c.text for c in cues]
    assert "Hello world" in texts[0]
    # bracketed/paren noise is stripped; applause cue drops because content ends empty
    assert all("Music" not in t for t in texts)
    assert all("applause" not in t for t in texts)


def test_cues_to_lines_plain_content():
    """We no longer inject a `讲话人:` prefix -- see commit history for why."""
    cues = load_cues(SAMPLE)
    lines = cues_to_lines(cues)
    assert lines, "expected at least one content line"
    assert not any(line.startswith("讲话人:") for line in lines)
