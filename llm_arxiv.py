import click
import llm
import arxiv
# Keep specific import for this one as it seemed to work
from arxiv import UnexpectedEmptyPageError, HTTPError
import fitz  # PyMuPDF
import tempfile
import os
import re
from typing import List, Union
# import base64 # No longer needed for image content


@llm.hookimpl
def register_commands(cli):
    return
    # @cli.command()
    # def hello_world():
    #     "Say hello world"
    #     click.echo("Hello world!")


@llm.hookimpl
def register_fragment_loaders(register):
    register("arxiv", arxiv_loader)


def extract_arxiv_id(argument: str) -> Union[str, None]:
    """Extracts arXiv ID from URL or returns the argument if it looks like an ID."""
    # Check for URL pattern: https://arxiv.org/abs/xxxx.xxxxx or /pdf/xxxx.xxxxx.pdf
    # Allows for optional 'v' followed by digits for versions
    match_url = re.match(r"https?://arxiv\.org/(?:abs|pdf)/(\d{4,}\.\d{4,}(?:v\d+)?)(?:\.pdf)?$", argument)
    if match_url:
        return match_url.group(1)

    # Check for ID pattern: xxxx.xxxxx or xxxx.xxxxxvN (enforce lengths)
    match_id = re.match(r"^(\d{4,}\.\d{4,}(?:v\d+)?)$", argument)
    if match_id:
        return match_id.group(1)

    # Check for older ID pattern: category/xxxxxxx (7 digits)
    match_old_id = re.match(r"^[a-z-]+(?:\.[A-Z]{2})?/\d{7}$", argument)
    if match_old_id:
        return argument # Return the full old ID including category

    return None


def arxiv_loader(argument: str) -> List[Union[llm.Fragment, llm.Attachment]]:
    """
    Load text and images from an arXiv paper PDF.

    Returns a list containing one text Fragment and multiple Attachment objects for images.
    Text fragment contains placeholders like [IMAGE: source_url (Image X)] for images found on each page.

    Argument is an arXiv ID (e.g., 2310.06825, hep-th/0101001)
    or an arXiv URL (e.g., https://arxiv.org/abs/2310.06825).
    """
    print(f"[DEBUG] arxiv_loader called with argument: {argument}")
    arxiv_id = extract_arxiv_id(argument)
    print(f"[DEBUG] Extracted arXiv ID: {arxiv_id}")
    if not arxiv_id:
        print(f"[DEBUG] Invalid arXiv ID: {argument}")
        raise ValueError(
            f"Invalid arXiv identifier or URL: {argument}. "
            "Expected format like '2310.06825', 'cs.CL/1234567', or 'https://arxiv.org/abs/...'.")

    try:
        print(f"[DEBUG] Searching arXiv for ID: {arxiv_id}")
        search = arxiv.Search(id_list=[arxiv_id], max_results=1)
        results = list(search.results())
        print(f"[DEBUG] Search results: {results}")
        if not results:
            print(f"[DEBUG] No results for arXiv ID: {arxiv_id}")
            raise ValueError(f"No paper found for arXiv ID: {arxiv_id}")
        paper = results[0]
        paper_source_url = paper.entry_id
        
        attachments = [] # For llm.Attachment objects
        full_text_parts = [] # Collect text parts page by page
        image_count = 0 # Counter for image placeholders

        image_temp_dir = tempfile.mkdtemp(prefix="llm_arxiv_img_")
        print(f"[DEBUG] Created image temp dir: {image_temp_dir}")

        with tempfile.TemporaryDirectory() as pdf_temp_dir:
            print(f"[DEBUG] Downloading PDF to: {pdf_temp_dir}")
            pdf_path = paper.download_pdf(dirpath=pdf_temp_dir)
            print(f"[DEBUG] Downloaded PDF path: {pdf_path}")
            try:
                print(f"[DEBUG] Opening PDF with fitz: {pdf_path}")
                doc = fitz.open(pdf_path)
                print(f"[DEBUG] PDF opened, number of pages: {doc.page_count}")
                for page_num, page in enumerate(doc):
                    print(f"[DEBUG] Processing page {page_num+1}")
                    page_text = page.get_text()
                    full_text_parts.append(page_text)
                    image_list = page.get_images(full=True)
                    print(f"[DEBUG] Found {len(image_list)} images on page {page_num+1}")
                    page_image_placeholders = []
                    for img_index, img_info in enumerate(image_list):
                        xref = img_info[0]
                        try:
                            print(f"[DEBUG] Extracting image {img_index+1} on page {page_num+1}")
                            base_image = doc.extract_image(xref)
                        except Exception as e:
                            print(f"[DEBUG] Failed to extract image {img_index+1} on page {page_num+1}: {e}")
                            continue 
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        image_count += 1
                        img_filename = f"page_{page_num + 1}_img_{img_index + 1}.{image_ext}"
                        img_path = os.path.join(image_temp_dir, img_filename)
                        with open(img_path, "wb") as img_file:
                            img_file.write(image_bytes)
                        # Check file existence and readability
                        if os.path.exists(img_path) and os.access(img_path, os.R_OK):
                            print(f"[DEBUG] Image file created and readable: {img_path}")
                        else:
                            print(f"[DEBUG] Image file missing or not readable: {img_path}")
                        img_source_metadata = f"{paper_source_url}/page_{page_num + 1}_img_{img_index + 1}.{image_ext}"
                        page_image_placeholders.append(f"\n[See attached image {image_count}: {img_source_metadata}]\n")
                        attachments.append(llm.Attachment(path=img_path))
                    if page_image_placeholders:
                        full_text_parts.append("".join(page_image_placeholders))
                doc.close()
                print(f"[DEBUG] Finished processing all pages and images.")
            except Exception as e:
                print(f"[DEBUG] Exception during PDF extraction: {e}")
                if 'doc' in locals() and hasattr(doc, 'is_open') and doc.is_open:
                    doc.close()
                raise ValueError(f"Failed to extract content from PDF {pdf_path}: {e}") from e
        full_text = "".join(full_text_parts)
        output_items: List[Union[llm.Fragment, llm.Attachment]] = [
            llm.Fragment(full_text, source=paper_source_url)
        ]
        output_items.extend(attachments)
        print(f"[DEBUG] Returning {len(output_items)} fragments/attachments:")
        for i, item in enumerate(output_items):
            print(f"  [DEBUG] Item {i}: type={type(item)}, repr={repr(item)}")
            if isinstance(item, llm.Attachment):
                print(f"    [DEBUG] Attachment path: {item.path}, exists: {os.path.exists(item.path)}")
        return output_items

    except UnexpectedEmptyPageError as e:
        print(f"[DEBUG] UnexpectedEmptyPageError: {e}")
        raise ValueError(f"arXiv search returned an unexpected empty page for ID: {arxiv_id}. Check the ID. Error: {e}") from e
    except HTTPError as e:
        print(f"[DEBUG] HTTPError: {e}")
        raise ValueError(f"Failed to fetch paper details from arXiv for ID {arxiv_id}: {e}") from e
    except Exception as e:
        print(f"[DEBUG] General Exception: {e}")
        raise ValueError(f"Error processing arXiv paper {arxiv_id}: {str(e)}") from e

# Ensure base64 is removed if no longer used elsewhere, for now it's still imported.
# from typing import List, Union, Any # Refine 'Any' if possible, but Union is key
# For the return type, it's List[Union[llm.Fragment, llm.Attachment]]
# The `Any` was a temporary placeholder in my thought process.
