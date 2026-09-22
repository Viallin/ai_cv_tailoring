from app.markdown_inline import InlineRun, parse_inline_runs


def test_plain_text_is_a_single_unstyled_run():
    assert parse_inline_runs("Plain text") == [InlineRun("Plain text", bold=False, italic=False)]


def test_whole_line_bold():
    assert parse_inline_runs("**Bold text**") == [InlineRun("Bold text", bold=True, italic=False)]


def test_whole_line_italic():
    assert parse_inline_runs("*Italic text*") == [InlineRun("Italic text", bold=False, italic=True)]


def test_mixed_inline_bold_then_plain():
    assert parse_inline_runs("**Position** — Company") == [
        InlineRun("Position", bold=True, italic=False),
        InlineRun(" — Company", bold=False, italic=False),
    ]


def test_plain_then_italic_then_plain():
    assert parse_inline_runs("before *italic* after") == [
        InlineRun("before ", bold=False, italic=False),
        InlineRun("italic", bold=False, italic=True),
        InlineRun(" after", bold=False, italic=False),
    ]


def test_stray_unmatched_marker_is_literal():
    assert parse_inline_runs("cost is $5 * quantity") == [
        InlineRun("cost is $5 * quantity", bold=False, italic=False)
    ]


def test_empty_line_returns_no_runs():
    assert parse_inline_runs("") == []


def test_bare_url_gets_url_set():
    assert parse_inline_runs("https://example.com") == [
        InlineRun("https://example.com", bold=False, italic=False, url="https://example.com")
    ]


def test_url_preceded_by_label_text():
    assert parse_inline_runs("Portfolio: https://example.com/me") == [
        InlineRun("Portfolio: ", bold=False, italic=False),
        InlineRun(
            "https://example.com/me",
            bold=False,
            italic=False,
            url="https://example.com/me",
        ),
    ]


def test_url_wrapped_in_parens_excludes_the_closing_paren():
    runs = parse_inline_runs("(https://example.com/me)")

    assert runs == [
        InlineRun("(", bold=False, italic=False),
        InlineRun(
            "https://example.com/me", bold=False, italic=False, url="https://example.com/me"
        ),
        InlineRun(")", bold=False, italic=False),
    ]


def test_url_inside_a_bold_span_keeps_bold_flag():
    runs = parse_inline_runs("**https://example.com**")

    assert runs == [
        InlineRun("https://example.com", bold=True, italic=False, url="https://example.com")
    ]


def test_two_urls_separated_by_a_pipe():
    runs = parse_inline_runs("https://a.example.com | https://b.example.com")

    urls = [r.url for r in runs if r.url]
    assert urls == ["https://a.example.com", "https://b.example.com"]


# ----- Phase 25: __underline__ spans and [text](url) links -----------------


def test_whole_line_underline():
    assert parse_inline_runs("__Underlined text__") == [
        InlineRun("Underlined text", bold=False, italic=False, underline=True)
    ]


def test_mixed_inline_underline_then_plain():
    assert parse_inline_runs("__Position__ — Company") == [
        InlineRun("Position", bold=False, italic=False, underline=True),
        InlineRun(" — Company", bold=False, italic=False),
    ]


def test_explicit_link_syntax_sets_display_text_and_url():
    assert parse_inline_runs("See [my portfolio](https://example.com/me) for more.") == [
        InlineRun("See ", bold=False, italic=False),
        InlineRun("my portfolio", bold=False, italic=False, url="https://example.com/me"),
        InlineRun(" for more.", bold=False, italic=False),
    ]


def test_explicit_link_display_text_is_not_bare_url_scanned_again():
    # A [text](url) span already carries its own explicit url — its
    # display text (free-form, not itself expected to look like a URL)
    # shouldn't also go through the bare-http(s):// autodetect pass.
    runs = parse_inline_runs("[https://looks-like-a-url.example](https://real-target.example)")

    assert runs == [InlineRun("https://looks-like-a-url.example", bold=False, italic=False, url="https://real-target.example")]


def test_bold_and_underline_can_appear_on_separate_spans_in_one_line():
    assert parse_inline_runs("**Bold** and __underlined__") == [
        InlineRun("Bold", bold=True, italic=False),
        InlineRun(" and ", bold=False, italic=False),
        InlineRun("underlined", bold=False, italic=False, underline=True),
    ]
