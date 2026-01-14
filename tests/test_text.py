
from trendradar.utils.text import strip_markdown, convert_markdown_to_mrkdwn

def test_strip_markdown():
    text = "**Title** [Link](http://example.com) *italics*"
    stripped = strip_markdown(text)
    assert "Title" in stripped
    assert "Link" in stripped
    assert "[" not in stripped
    assert "]" not in stripped
    assert "*" not in stripped

def test_convert_markdown_to_mrkdwn():
    content = "**Bold** [Link](http://url)"
    mrkdwn = convert_markdown_to_mrkdwn(content)
    assert "*Bold*" in mrkdwn
    assert "<http://url|Link>" in mrkdwn
