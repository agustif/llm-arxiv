import pytest
from llm_arxiv import extract_arxiv_id, arxiv_loader
from unittest.mock import patch, MagicMock
import llm
import arxiv
import base64


@pytest.mark.parametrize(
    "argument, expected_id",
    [
        # Standard IDs
        ("2310.06825", "2310.06825"),
        ("2310.06825v1", "2310.06825v1"),
        ("1234.56789", "1234.56789"),
        # URLs
        ("https://arxiv.org/abs/2310.06825", "2310.06825"),
        ("http://arxiv.org/abs/2310.06825v2", "2310.06825v2"),
        ("https://arxiv.org/pdf/1234.56789.pdf", "1234.56789"),
        ("http://arxiv.org/pdf/1234.56789v3.pdf", "1234.56789v3"),
        # Older IDs
        ("hep-th/0101001", "hep-th/0101001"),
        ("math.GT/0309136", "math.GT/0309136"),
        ("cs.AI/0101001", "cs.AI/0101001"),
        # Invalid cases
        ("not an id", None),
        ("https://example.com/abs/2310.06825", None),
        ("arxiv.org/abs/2310.06825", None), # Missing scheme
        ("123.456", None), # Incorrect format
        ("cs.AI/123456", None), # Incorrect old format (needs 7 digits)
    ]
)
def test_extract_arxiv_id(argument, expected_id):
    assert extract_arxiv_id(argument) == expected_id


@patch("llm_arxiv.fitz.open")
@patch("llm_arxiv.arxiv.Search")
def test_arxiv_loader_success(mock_search_class, mock_fitz_open):
    # --- Mock arXiv Search and Result ---
    mock_search_instance = MagicMock()
    mock_paper = MagicMock(spec=arxiv.Result)
    mock_paper.entry_id = "http://arxiv.org/abs/1234.5678v1"
    mock_paper.download_pdf.return_value = "/tmp/fake_paper.pdf"
    mock_search_instance.results.return_value = iter([mock_paper])
    mock_search_class.return_value = mock_search_instance

    # --- Mock PyMuPDF (fitz) ---
    mock_doc = MagicMock()
    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = "This is page 1. "
    # Provide one image on page 1
    mock_page1.get_images.return_value = [(10,)] # (xref,)
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = "This is page 2."
    mock_page2.get_images.return_value = []
    mock_doc.__iter__.return_value = iter([mock_page1, mock_page2])
    # Mock the extract_image call
    mock_doc.extract_image.return_value = {"image": b"fake_image_bytes", "ext": "png"}
    # Configure mock_doc to be a context manager returning itself
    mock_doc.__enter__.return_value = mock_doc
    
    # Ensure __exit__ calls close() and returns None
    def mock_exit_calls_close(*args):
        mock_doc.close() # Call the close method on mock_doc
        return None
    mock_doc.__exit__.side_effect = mock_exit_calls_close

    # mock_fitz_open should return mock_doc
    mock_fitz_open.return_value = mock_doc

    # --- Call the loader ---
    fragments = arxiv_loader("1234.5678")

    # --- Assertions ---
    assert isinstance(fragments, list)
    assert len(fragments) == 2 # Text fragment + 1 image attachment
    
    # Check the first fragment (text)
    text_fragment = fragments[0]
    assert isinstance(text_fragment, llm.Fragment)
    assert text_fragment.source == "http://arxiv.org/abs/1234.5678v1"
    # Expected img_source: "http://arxiv.org/abs/1234.5678v1/page_1_img_1.png"
    expected_text = "This is page 1. \n[IMAGE: http://arxiv.org/abs/1234.5678v1/page_1_img_1.png]\nThis is page 2."
    actual_text = str(text_fragment)
    assert actual_text == expected_text

    # Check the attachment
    attachment = fragments[1]
    assert isinstance(attachment, llm.Fragment) # Should be llm.Fragment based on llm_arxiv.py
    assert attachment.source == "http://arxiv.org/abs/1234.5678v1/page_1_img_1.png"
    assert str(attachment) == base64.b64encode(b"fake_image_bytes").decode("utf-8")

    # Check mocks were called correctly
    mock_search_class.assert_called_once_with(id_list=["1234.5678"], max_results=1)
    mock_search_instance.results.assert_called_once()
    mock_paper.download_pdf.assert_called_once()
    mock_fitz_open.assert_called_once_with("/tmp/fake_paper.pdf")
    assert mock_page1.get_text.call_count == 1
    assert mock_page2.get_text.call_count == 1
    # Check that get_images was called for each page
    assert mock_page1.get_images.call_count == 1
    assert mock_page2.get_images.call_count == 1
    # Ensure doc.extract_image was called for the image on page 1
    mock_doc.extract_image.assert_called_once_with(10)
    # Ensure doc.close() was called
    mock_doc.close.assert_called_once()


@pytest.mark.parametrize(
    "argument, expected_error_msg_part",
    [
        ("invalid-id", "Invalid arXiv identifier or URL: invalid-id"),
        ("http://example.com/1234.5678", "Invalid arXiv identifier or URL: http://example.com/1234.5678"),
    ]
)
def test_arxiv_loader_invalid_id(argument, expected_error_msg_part):
    with pytest.raises(ValueError) as excinfo:
        arxiv_loader(argument)
    assert expected_error_msg_part in str(excinfo.value)


@patch("llm_arxiv.arxiv.Search")
def test_arxiv_loader_no_results(mock_search_class):
    # Configure Search to return an empty iterator
    mock_search_instance = MagicMock()
    mock_search_instance.results.return_value = iter([])
    mock_search_class.return_value = mock_search_instance

    with pytest.raises(ValueError) as excinfo:
        arxiv_loader("1234.5678")
    assert "No paper found for arXiv ID: 1234.5678" in str(excinfo.value)
    mock_search_class.assert_called_once_with(id_list=["1234.5678"], max_results=1)


@patch("llm_arxiv.arxiv.Search")
def test_arxiv_loader_arxiv_api_error(mock_search_class):
    # Configure Search results to raise an exception
    mock_search_instance = MagicMock()
    # Use arxiv.HTTPError for the side_effect, providing only required args
    mock_search_instance.results.side_effect = arxiv.HTTPError(
        url="http://fake.export.arxiv.org",
        status=500,
        retry=False
    )
    mock_search_class.return_value = mock_search_instance

    with pytest.raises(ValueError) as excinfo:
        arxiv_loader("1234.5678")
    # Check that the error message contains the actual HTTPError string representation
    expected_msg = "Failed to fetch paper details from arXiv for ID 1234.5678: Page request resulted in HTTP 500 (http://fake.export.arxiv.org)"
    assert expected_msg in str(excinfo.value)
    mock_search_class.assert_called_once_with(id_list=["1234.5678"], max_results=1)


@patch("llm_arxiv.arxiv.Search")
def test_arxiv_loader_pdf_download_error(mock_search_class):
    # Configure download_pdf to raise an exception
    mock_search_instance = MagicMock()
    mock_paper = MagicMock(spec=arxiv.Result)
    mock_paper.entry_id = "http://arxiv.org/abs/1234.5678v1"
    mock_paper.download_pdf.side_effect = Exception("Download failed")
    mock_search_instance.results.return_value = iter([mock_paper])
    mock_search_class.return_value = mock_search_instance

    with pytest.raises(ValueError) as excinfo:
        arxiv_loader("1234.5678")
    # The error message wraps the original exception
    assert "Error processing arXiv paper 1234.5678: Download failed" in str(excinfo.value)
    mock_search_class.assert_called_once_with(id_list=["1234.5678"], max_results=1)
    mock_paper.download_pdf.assert_called_once()


@patch("llm_arxiv.fitz.open")
@patch("llm_arxiv.arxiv.Search")
def test_arxiv_loader_pdf_extract_error(mock_search_class, mock_fitz_open):
    # Configure search and download to succeed
    mock_search_instance = MagicMock()
    mock_paper = MagicMock(spec=arxiv.Result)
    mock_paper.entry_id = "http://arxiv.org/abs/1234.5678v1"
    mock_paper.download_pdf.return_value = "/tmp/fake_paper.pdf"
    mock_search_instance.results.return_value = iter([mock_paper])
    mock_search_class.return_value = mock_search_instance

    # Configure fitz.open to raise an exception
    mock_fitz_open.side_effect = Exception("Fitz error")

    with pytest.raises(ValueError) as excinfo:
        arxiv_loader("1234.5678")

    # Check the wrapped error message
    expected_msg = "Error processing arXiv paper 1234.5678: Failed to extract content from PDF /tmp/fake_paper.pdf: Fitz error"
    assert expected_msg in str(excinfo.value)
    mock_search_class.assert_called_once_with(id_list=["1234.5678"], max_results=1)
    mock_paper.download_pdf.assert_called_once()
    mock_fitz_open.assert_called_once_with("/tmp/fake_paper.pdf")
