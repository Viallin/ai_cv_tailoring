import pytest

from app.errors import ParsingError
from app.resume_reader import read_resume_text


def test_reads_plain_text_file(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("Ada Lovelace\nAnalytical Engineer", encoding="utf-8")

    assert read_resume_text(path) == "Ada Lovelace\nAnalytical Engineer"


def test_reads_markdown_file(tmp_path):
    path = tmp_path / "resume.md"
    path.write_text("# Ada Lovelace", encoding="utf-8")

    assert read_resume_text(path) == "# Ada Lovelace"


def test_treats_extensionless_file_as_plain_text(tmp_path):
    path = tmp_path / "resume"
    path.write_text("Ada Lovelace", encoding="utf-8")

    assert read_resume_text(path) == "Ada Lovelace"


def test_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "resume.odt"
    path.write_text("not a supported format", encoding="utf-8")

    with pytest.raises(ParsingError):
        read_resume_text(path)


def test_extracts_text_from_docx(tmp_path):
    from docx import Document

    path = tmp_path / "resume.docx"
    document = Document()
    document.add_paragraph("Ada Lovelace")
    document.add_paragraph("Analytical Engineer")
    document.save(str(path))

    assert read_resume_text(path) == "Ada Lovelace\nAnalytical Engineer"


def test_raises_when_docx_has_no_extractable_text(tmp_path):
    from docx import Document

    path = tmp_path / "resume.docx"
    Document().save(str(path))  # blank document, no paragraphs

    with pytest.raises(ParsingError):
        read_resume_text(path)


def test_raises_when_docx_is_corrupt(tmp_path):
    path = tmp_path / "resume.docx"
    path.write_bytes(b"not really a docx")

    with pytest.raises(ParsingError):
        read_resume_text(path)


def test_extracts_text_from_rtf(tmp_path):
    path = tmp_path / "resume.rtf"
    path.write_text(r"{\rtf1\ansi\deff0 Ada Lovelace\par Analytical Engineer}", encoding="ascii")

    assert read_resume_text(path) == "Ada Lovelace\nAnalytical Engineer"


def test_extracts_cyrillic_text_from_rtf_with_ansicpg1251(tmp_path):
    # \ansicpg1251 is the legacy Windows Cyrillic codepage RTF exports from
    # older word processors commonly declare; \'XX are the hex-escaped
    # bytes for "Привет" under that codepage. Written as raw ASCII bytes
    # (not a Python string literal) to avoid this source file itself
    # needing non-ASCII content.
    path = tmp_path / "resume.rtf"
    rtf = r"{\rtf1\ansi\ansicpg1251\deff0{\fonttbl{\f0 Arial;}}\f0\fs24 \'cf\'f0\'e8\'e2\'e5\'f2}"
    path.write_bytes(rtf.encode("ascii"))

    assert read_resume_text(path) == "Привет"


def test_raises_when_rtf_has_no_extractable_text(tmp_path):
    path = tmp_path / "resume.rtf"
    path.write_text(r"{\rtf1\ansi\deff0}", encoding="ascii")

    with pytest.raises(ParsingError):
        read_resume_text(path)


def test_extracts_text_from_pdf(tmp_path, mocker):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")  # content is irrelevant, PdfReader is mocked

    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Ada Lovelace\nAnalytical Engineer"
    fake_page.get.return_value = None  # no /Annots, same as a real page with no links
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    # Every PDF extraction gets the trailing-character-truncation caveat
    # appended (see test_always_appends_the_truncation_caveat_to_pdf_text)
    # — startswith rather than == here for that reason.
    assert read_resume_text(path).startswith("Ada Lovelace\nAnalytical Engineer")


def test_joins_multiple_pdf_pages(tmp_path, mocker):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    page_one, page_two = mocker.Mock(), mocker.Mock()
    page_one.extract_text.return_value = "Page one"
    page_one.get.return_value = None
    page_two.extract_text.return_value = "Page two"
    page_two.get.return_value = None
    fake_reader = mocker.Mock()
    fake_reader.pages = [page_one, page_two]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    assert read_resume_text(path).startswith("Page one\nPage two")


def test_raises_when_pdf_has_no_extractable_text(tmp_path, mocker):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = ""
    fake_page.get.return_value = None
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    with pytest.raises(ParsingError):
        read_resume_text(path)


def test_raises_when_pdf_reader_errors(tmp_path, mocker):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")
    mocker.patch("pypdf.PdfReader", side_effect=Exception("corrupt pdf"))

    with pytest.raises(ParsingError):
        read_resume_text(path)


def _link_annotation(uri: str):
    # Mirrors the shape pypdf hands back for a real `/Link` annotation:
    # `page.get("/Annots")` is a list of objects with `.get_object()`
    # (resolving an indirect reference to the actual dict — a no-op here
    # since DictionaryObject.get_object() returns itself) whose `/A`
    # action dict likewise resolves via `.get_object()` to one holding
    # `/URI`. Real objects, not Mocks, so `_extract_pdf_links` exercises
    # its actual `.get_object()`/`.get()` calls instead of Mock stand-ins.
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject

    action = DictionaryObject({NameObject("/URI"): TextStringObject(uri)})
    return DictionaryObject(
        {NameObject("/Subtype"): NameObject("/Link"), NameObject("/A"): action}
    )


def test_extracts_pdf_link_annotations_into_a_trailing_section(tmp_path, mocker):
    # Found live: a PDF where "linkedin"/"figma" contact rows were
    # hyperlinked to real profile URLs came out of plain text extraction
    # as bare words — page.extract_text() has no idea a /Link annotation
    # exists. This appends the real URLs so the CV Parser LLM (see
    # 01_cv_parser_v1.md's "Hyperlinks" rule) can match them back to those
    # bare mentions by domain.
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Ada Lovelace\nlinkedin"
    fake_page.get.return_value = [_link_annotation("https://www.linkedin.com/in/ada/")]
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    text = read_resume_text(path)

    assert text.startswith("Ada Lovelace\nlinkedin")
    assert "Hyperlinks embedded in this PDF" in text
    assert "https://www.linkedin.com/in/ada/" in text


def test_omits_the_links_section_when_the_pdf_has_no_link_annotations(tmp_path, mocker):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Ada Lovelace"
    fake_page.get.return_value = None  # no /Annots at all
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    assert "Hyperlinks embedded in this PDF" not in read_resume_text(path)


def test_deduplicates_repeated_pdf_link_annotations(tmp_path, mocker):
    # A company name hyperlinked to its site, mentioned/linked more than
    # once, shouldn't pad the list with the same URL over and over.
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    annots = [_link_annotation("https://example.com/"), _link_annotation("https://example.com/")]
    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Ada Lovelace"
    fake_page.get.return_value = annots
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    text = read_resume_text(path)

    assert text.count("https://example.com/") == 1


def test_ignores_a_malformed_pdf_annotation_without_losing_the_others(tmp_path, mocker):
    # One broken/unexpected annotation entry shouldn't take down extraction
    # for the whole document, or hide every other, well-formed link.
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    malformed = mocker.Mock()
    malformed.get_object.side_effect = Exception("boom")
    annots = [malformed, _link_annotation("https://example.com/")]
    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Ada Lovelace"
    fake_page.get.return_value = annots
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    text = read_resume_text(path)

    assert "https://example.com/" in text


def test_ignores_a_non_link_annotation(tmp_path, mocker):
    # Not every /Annots entry is a hyperlink (e.g. a /Text sticky-note
    # comment, or a highlight) — only /Link ones name a URI at all.
    from pypdf.generic import DictionaryObject, NameObject

    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    non_link = DictionaryObject({NameObject("/Subtype"): NameObject("/Text")})
    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Ada Lovelace"
    fake_page.get.return_value = [non_link]
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    assert "Hyperlinks embedded in this PDF" not in read_resume_text(path)


def test_always_appends_the_truncation_caveat_to_pdf_text(tmp_path, mocker):
    # Found live: a PDF whose text extraction silently dropped trailing
    # characters (no marker left behind — an extracted "Presen" reads as a
    # slightly odd but plausible word on its own) came back from the CV
    # Parser LLM with a dropped final digit in one role's end date
    # fabricated into a specific, wrong year. Since a dropped character
    # leaves nothing to detect and conditionally warn about, this caveat is
    # unconditional for every PDF, not keyed off finding anything unusual
    # in this particular one — see 01_cv_parser_v1.md's "PDF text
    # extraction" rule for the actual instruction this sets up.
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Ada Lovelace\nAugust 2018 - April 2024"
    fake_page.get.return_value = None
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    text = read_resume_text(path)

    assert text.startswith("Ada Lovelace\nAugust 2018 - April 2024")
    assert "extracted from a PDF" in text


def test_includes_both_the_truncation_caveat_and_the_links_section_when_links_exist(tmp_path, mocker):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-fake")

    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "linkedin"
    fake_page.get.return_value = [_link_annotation("https://www.linkedin.com/in/ada/")]
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    text = read_resume_text(path)

    assert "extracted from a PDF" in text
    assert "https://www.linkedin.com/in/ada/" in text
