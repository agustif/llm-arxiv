import llm
import arxiv
# Keep specific import for this one as it seemed to work
from arxiv import UnexpectedEmptyPageError, HTTPError
import fitz  # PyMuPDF
import tempfile
import re
from typing import List, Union, Tuple, Optional, Set, TypedDict, Literal # Added Set, TypedDict, Literal
import base64 # For image encoding
import markdownify # Added for HTML to Markdown conversion
import io # For handling image bytes
from PIL import Image # Added for image resizing
import os # Added for environment variable access
from urllib.parse import parse_qs # Added for parsing options from argument
import click # For the new command
import sys # Ensure sys is imported for stderr printing
import datetime # For formatting dates from arxiv results

# --- Types for Image Selection ---
class ImageSelectionCriteria(TypedDict, total=False):
    mode: Literal["all", "global", "pages"]
    indices: Set[int] # For "global" mode: global image indices. For "pages" mode: page numbers.


# --- Helper function to parse range strings like "1,3-5,7" ---
def parse_ranges_to_set(range_str: str) -> Set[int]:
    """Parses a string like '1,3-5,7' into a set of integers {1, 3, 4, 5, 7}."""
    result: Set[int] = set()
    if not range_str:
        return result
    parts = range_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start_str, end_str = part.split('-', 1)
            try:
                start = int(start_str)
                end = int(end_str)
                if start <= 0 or end <= 0:
                    raise ValueError("Page/image numbers must be positive.")
                if start > end:
                    raise ValueError(f"Invalid range: start ({start}) > end ({end}).")
                result.update(range(start, end + 1))
            except ValueError as e:
                raise ValueError(f"Invalid range part: '{part}'. {e}") from e
        else:
            try:
                val = int(part)
                if val <= 0:
                    raise ValueError("Page/image numbers must be positive.")
                result.add(val)
            except ValueError as e:
                raise ValueError(f"Invalid number in range string: '{part}'. {e}") from e
    return result

# --- Helper function to parse image selection specification string ---
def parse_image_selection_spec(spec_string: Optional[str]) -> Optional[ImageSelectionCriteria]:
    """
    Parses an image selection string.
    Returns None if no images should be included.
    Returns a dict like {"mode": "all"} or {"mode": "global", "indices": {1,2,3}}
    or {"mode": "pages", "indices": {1,2,3}}.
    """
    if spec_string is None:
        return None

    s_lower = spec_string.lower().strip()
    if not s_lower or s_lower in ["all", "true", "yes", "1"]: # Empty string (e.g. from ?i= or -i without arg) means all
        return {"mode": "all"}
    if s_lower in ["none", "false", "no", "0"]:
        return None

    if s_lower.startswith("g:"):
        try:
            indices = parse_ranges_to_set(spec_string[2:])
            if not indices:
                 raise ValueError("Global image selection ('G:') requires at least one image index or range.")
            return {"mode": "global", "indices": indices}
        except ValueError as e: # Catch errors from parse_ranges_to_set
            raise ValueError(f"Invalid global image selection format ('{spec_string}'): {e}") from e
    elif s_lower.startswith("p:"):
        try:
            page_numbers = parse_ranges_to_set(spec_string[2:])
            if not page_numbers:
                raise ValueError("Page selection ('P:') requires at least one page number or range.")
            return {"mode": "pages", "indices": page_numbers} # Using 'indices' key for page numbers
        except ValueError as e: # Catch errors from parse_ranges_to_set
            raise ValueError(f"Invalid page selection format ('{spec_string}'): {e}") from e
    
    raise ValueError(
        f"Invalid image selection format: '{spec_string}'. "
        "Expected 'all', 'none', 'G:1,2-5', 'P:1,2-4', or blank for all."
    )


# --- Helper Function for Core Logic ---
def _process_arxiv_paper(
    arxiv_id_or_url_main: str, 
    image_selection_criteria: Optional[ImageSelectionCriteria], 
    resize_option: Union[bool, int], 
) -> Tuple[str, List[llm.Attachment], str]:
    """
    Internal helper to fetch and process an arXiv paper.
    Returns markdown text, list of llm.Attachment objects, and the paper's source URL.
    """
    arxiv_id = extract_arxiv_id(arxiv_id_or_url_main)
    if not arxiv_id:
        raise ValueError(
            f"Invalid arXiv identifier or URL passed to _process_arxiv_paper: {arxiv_id_or_url_main}.")

    search = arxiv.Search(id_list=[arxiv_id], max_results=1)
    results = list(search.results())
    if not results:
        raise ValueError(f"No paper found for arXiv ID: {arxiv_id}")
    paper = results[0]
    paper_source_url = paper.entry_id

    attachments_list: List[llm.Attachment] = []
    full_html_parts: List[str] = []
    
    global_image_document_idx_counter = 0 # For 'G:' mode selection

    with tempfile.TemporaryDirectory() as temp_dir_for_pdf:
        pdf_path = paper.download_pdf(dirpath=temp_dir_for_pdf)
        try:
            with fitz.open(pdf_path) as doc:
                for page_num, page in enumerate(doc):
                    page_html_content = page.get_text("html") # Get HTML first
                    
                    current_page_conceptual_refs_for_placeholders: List[str] = []
                    current_page_attachments_for_this_page: List[llm.Attachment] = []

                    if image_selection_criteria: # Only attempt to process images if criteria exist
                        image_list = page.get_images(full=True)
                        for img_idx_on_page, img_info in enumerate(image_list):
                            global_image_document_idx_counter += 1 # Count every image found in doc order

                            # Determine if this specific image should be included
                            should_include_this_specific_image = False
                            mode = image_selection_criteria["mode"]
                            
                            if mode == "all":
                                should_include_this_specific_image = True
                            elif mode == "global":
                                # Explicitly check if indices is not None, though TypedDict implies it exists for this mode
                                if image_selection_criteria.get("indices") and global_image_document_idx_counter in image_selection_criteria["indices"]:
                                    should_include_this_specific_image = True
                            elif mode == "pages":
                                # Explicitly check for indices
                                if image_selection_criteria.get("indices") and (page_num + 1) in image_selection_criteria["indices"]:
                                    should_include_this_specific_image = True
                            
                            if not should_include_this_specific_image:
                                continue # Skip this image, don't process or add placeholder

                            # --- Start of actual image processing for selected image ---
                            xref = img_info[0]
                            try:
                                base_image = doc.extract_image(xref)
                            except Exception: # Skip if extraction fails
                                print(f"Warning: Failed to extract image {img_idx_on_page} (global {global_image_document_idx_counter}) on page {page_num + 1}. Skipping.", file=sys.stderr)
                                continue 
                            
                            image_bytes = base_image["image"]
                            original_ext_from_pdf = base_image["ext"].lower()
                            
                            pillow_input_ext_guess = original_ext_from_pdf
                            # jpx (JPEG2000) is not well supported by default Pillow, treat as png for broader compatibility attempt
                            if original_ext_from_pdf not in ["png", "jpeg", "jpg", "gif", "bmp"] or original_ext_from_pdf == "jpx":
                                pillow_input_ext_guess = "png"

                            try:
                                img = Image.open(io.BytesIO(image_bytes))
                                # Ensure a common mode BEFORE load() and resize()
                                if img.mode == 'P':
                                    img = img.convert('RGBA' if img.info.get('transparency') is not None else 'RGB')
                                elif img.mode not in ['RGB', 'RGBA', 'L', 'LA']:
                                    # For CMYK, YCbCr, or other complex modes, convert to RGBA early
                                    img = img.convert('RGBA')
                                
                                img.load() # Force loading of image data

                                # More detailed logging before the check
                                print(f"Debug: Image {img_idx_on_page} (global {global_image_document_idx_counter}) on page {page_num + 1}: Original PDF ext: {original_ext_from_pdf}, Pillow mode: {img.mode}, Pillow w: {img.width}, h: {img.height}", file=sys.stderr)

                                # Check for zero dimensions immediately after opening
                                if img.width <= 0 or img.height <= 0:
                                    print(f"Warning: Image {img_idx_on_page} (global {global_image_document_idx_counter}) on page {page_num + 1} has zero or negative dimensions (w={img.width}, h={img.height}) after opening. Skipping.", file=sys.stderr)
                                    continue # Skip to the next image

                                perform_resize = False
                                max_dim_to_use = 512 # Default for when resize_option is True

                                if isinstance(resize_option, int) and resize_option > 0:
                                    perform_resize = True
                                    max_dim_to_use = resize_option
                                elif resize_option is True: 
                                    perform_resize = True
                                    # max_dim_to_use is already set to default (512)
                                
                                if perform_resize:
                                    if img.width > max_dim_to_use or img.height > max_dim_to_use:
                                        if img.width > img.height:
                                            new_width = max_dim_to_use
                                            new_height = max(1, int(max_dim_to_use * img.height / img.width))
                                        else:
                                            new_height = max_dim_to_use
                                            new_width = max(1, int(max_dim_to_use * img.width / img.height))
                                        img = img.resize((new_width, new_height), Image.Resampling.BILINEAR)
                                        print(f"Debug: Image *after* resize: Mode: {img.mode}, Size: {img.size}, Info: {img.info}", file=sys.stderr)
                                        # Explicitly convert after resize to ensure a common mode
                                        if img.mode == 'P':
                                            img = img.convert('RGBA' if img.info.get('transparency') is not None else 'RGB')
                                        elif img.mode not in ['RGB', 'RGBA', 'L', 'LA']:
                                            img = img.convert('RGBA') # Default to RGBA if not a simple mode
                                
                                output_buffer = io.BytesIO()
                                processed_image_final_ext = None

                                if pillow_input_ext_guess in ["jpeg", "jpg"]:
                                    if img.mode not in ['RGB', 'L']: # If not RGB or Grayscale
                                        img = img.convert('RGB') # Convert to RGB (strips alpha if any)
                                    img.save(output_buffer, format="JPEG", quality=70, optimize=True) 
                                    processed_image_final_ext = "jpeg"
                                else: 
                                    # Default to PNG for non-JPEG originals
                                    # Ensure mode is suitable for PNG saving (L, LA, RGB, RGBA)
                                    if img.mode == 'P': # Palette
                                        # Convert to RGBA if transparency is present, else RGB
                                        img = img.convert('RGBA' if img.info.get('transparency') is not None else 'RGB')
                                    elif img.mode in ['CMYK', 'YCbCr']:
                                        img = img.convert('RGBA') # Convert to RGBA for broader compatibility
                                    elif img.mode not in ['L', 'LA', 'RGB', 'RGBA']:
                                        # For other unhandled modes (e.g., 'F', '1'), attempt conversion to RGBA
                                        # This is a fallback; specific handling might be better if such modes are common
                                        print(f"Warning: Image {img_idx_on_page} (global {global_image_document_idx_counter}) on page {page_num + 1} has unusual mode {img.mode}, converting to RGBA for PNG saving.", file=sys.stderr)
                                        img = img.convert('RGBA')
                                    
                                    # At this point, img.mode should be L, LA, RGB, or RGBA, all saveable as PNG
                                    img.save(output_buffer, format="PNG") # Temporarily remove optimize=True
                                    processed_image_final_ext = "png"
                                
                                processed_image_bytes = output_buffer.getvalue()
                                
                                # Conceptual ref uses page_num and img_idx_on_page for placeholder uniqueness
                                conceptual_ref = f"{paper_source_url}#page_{page_num + 1}_img_{img_idx_on_page + 1}"
                                current_page_conceptual_refs_for_placeholders.append(conceptual_ref)
                                
                                attachment = llm.Attachment(content=processed_image_bytes) 
                                attachment.type = f"image/{processed_image_final_ext}" 
                                current_page_attachments_for_this_page.append(attachment)

                            except Exception as processing_error:
                                print(f"Warning: Failed to process image {img_idx_on_page} (global {global_image_document_idx_counter}) on page {page_num + 1} (original ext: {original_ext_from_pdf}). Skipping. Error: {processing_error}", file=sys.stderr)
                            # --- End of actual image processing ---
                    
                    # Replace <img> tags in HTML with placeholders for *selected and processed* images
                    placeholder_iter = iter(current_page_conceptual_refs_for_placeholders)
                    def replace_img_with_placeholder_fn(match_obj):
                        try:
                            conceptual_ref_for_match = next(placeholder_iter)
                            return f"<p>[IMAGE: {conceptual_ref_for_match}]</p>" # Wrap placeholder in <p> for markdownify
                        except StopIteration: # Should not happen if lists are in sync
                            return "" 
                    
                    # Apply replacement to the original HTML content of the page
                    processed_page_html_content = re.sub(r"<img[^>]*>", replace_img_with_placeholder_fn, page_html_content, flags=re.IGNORECASE)
                    full_html_parts.append(processed_page_html_content)
                    attachments_list.extend(current_page_attachments_for_this_page) # Add processed attachments
                    
        except Exception as e:
            raise ValueError(f"Failed to extract content from PDF {pdf_path}: {e}") from e

    full_combined_html = "".join(full_html_parts)
    # Convert the final aggregated HTML (with placeholders) to Markdown
    markdown_text = markdownify.markdownify(full_combined_html, strip=['img']) # strip=['img'] redundant if placeholders work perfectly, but good safeguard.
    
    return markdown_text, attachments_list, paper_source_url


@llm.hookimpl
def register_fragment_loaders(register):
    register("arxiv", arxiv_loader)


def extract_arxiv_id(argument: str) -> Union[str, None]:
    """Extracts arXiv ID from URL or returns the argument if it looks like an ID."""
    match_url = re.match(r"https?://arxiv\.org/(?:abs|pdf)/(\d{4,}\.\d{4,}(?:v\d+)?)(?:\.pdf)?$", argument)
    if match_url:
        return match_url.group(1)

    match_id = re.match(r"^(\d{4,}\.\d{4,}(?:v\d+)?)$", argument)
    if match_id:
        return match_id.group(1)

    match_old_id = re.match(r"^[a-z-]+(?:\.[A-Z]{2})?/\d{7}$", argument)
    if match_old_id:
        return argument

    return None


def arxiv_loader(argument: str) -> List[Union[llm.Fragment, llm.Attachment]]:
    """
    Load text and images from an arXiv paper PDF. Fragment loader.
    Usage: llm -f arxiv:PAPER_ID_OR_URL[?options] "prompt"
    Options (append to ID/URL):
    - ?i[=SPEC] or ?include_images[=SPEC]: Include images.
        SPEC can be 'all' (default if ?i present), 'none',
        'G:1,3-5' (global images), 'P:1,2-4' (images from pages).
    - ?r[=VAL] or ?resize_images[=VAL]: VAL can be 'true' (default 512px) or PIXELS.
    """
    main_argument_part = argument
    query_string = ""
    if '?' in argument:
        main_argument_part, query_string = argument.split('?', 1)
    
    options = parse_qs(query_string)

    # Image selection for fragment loader
    image_spec_str_loader: Optional[str] = None
    raw_values_i = options.get('i', [])
    raw_values_include_images = options.get('include_images', [])
    
    chosen_raw_value_for_images: Optional[str] = None
    if raw_values_i:
        chosen_raw_value_for_images = raw_values_i[0]
    elif raw_values_include_images:
        chosen_raw_value_for_images = raw_values_include_images[0]
    # If chosen_raw_value_for_images is None here, it means no ?i or ?include_images param was present.
    # parse_image_selection_spec handles None correctly (-> no images).
    # It also handles "" (from ?i=) as "all".
    
    image_criteria_loader: Optional[ImageSelectionCriteria] = None
    try:
        # DEBUG PRINT for chosen_raw_value_for_images
        print(f"Debug arxiv_loader: chosen_raw_value_for_images = {repr(chosen_raw_value_for_images)}", file=sys.stderr)
        image_criteria_loader = parse_image_selection_spec(chosen_raw_value_for_images)
    except ValueError as e:
        raise ValueError(f"Invalid image selection option in fragment ('{chosen_raw_value_for_images}'): {e}") from e
    
    # Resize option for fragment loader
    resize_option_loader: Union[bool, int] = False # Default to no resize
    resize_values = options.get('resize_images', []) + options.get('r', [])
    if resize_values:
        val = resize_values[0].lower()
        if val in ['true', '1', 'yes', '']: # Empty means ?r was present
            resize_option_loader = True
        else:
            try:
                pixel_value = int(val)
                if pixel_value > 0:
                    resize_option_loader = pixel_value
                else: # Non-positive int, treat as just enabling default resize
                    resize_option_loader = True 
            except ValueError: # Not a bool-like string and not an int, treat as enabling default resize if ?r was present
                resize_option_loader = True 

    temp_arxiv_id = extract_arxiv_id(main_argument_part)
    if not temp_arxiv_id:
         raise ValueError(
            f"Invalid arXiv identifier or URL in fragment argument: {main_argument_part}.")

    try:
        markdown_text, attachments, paper_source_url_for_fragment = _process_arxiv_paper(
            main_argument_part, 
            image_criteria_loader, 
            resize_option_loader
        )
        
        fragments_and_attachments: List[Union[llm.Fragment, llm.Attachment]] = [
            llm.Fragment(content=markdown_text, source=paper_source_url_for_fragment)
        ]
        fragments_and_attachments.extend(attachments)
        return fragments_and_attachments

    except UnexpectedEmptyPageError as e:
         raise ValueError(f"arXiv search returned an unexpected empty page. Check the ID/URL. Error: {e}") from e
    except HTTPError as e:
        raise ValueError(f"Failed to fetch paper details from arXiv. Check network or ID/URL. Error: {e}") from e
    except ValueError as e: 
        raise e 
    except Exception as e:
        error_ref = temp_arxiv_id if temp_arxiv_id else main_argument_part
        raise ValueError(f"Error processing arXiv paper {error_ref} for fragment: {str(e)}") from e

# --- New Command: arxiv-search ---
@llm.hookimpl
def register_commands(cli):
    @cli.command(name="arxiv")
    @click.argument("paper_id_or_url", required=True)
    @click.argument("prompt", required=False, default=None)
    @click.option(
        "--include-images",
        "-i",
        "include_images_spec_str",
        type=str,
        default=None,
        help="Include images. Examples: 'all', 'none', 'G:1,3-5', 'P:1,2-4'. If omitted, no images included."
    )
    @click.option(
        "--resize-images",
        "-r",
        is_flag=True,
        help="Enable image resizing (default 512px, or use --max-dimension)."
    )
    @click.option(
        "--max-dimension",
        "-d",
        type=int,
        default=None,
        help="Set custom max dimension (pixels) for resizing. Requires -r."
    )
    @click.option(
        "-m",
        "--model",
        "model_id_option",
        type=str,
        default=None,
        help="LLM model to use for the prompt (if provided)."
    )
    @click.option(
        "-s",
        "--system",
        "system_prompt_option",
        type=str,
        default=None,
        help="System prompt to use with the LLM (if prompt provided)."
    )
    def arxiv_command(
        paper_id_or_url: str, 
        prompt: Optional[str],
        include_images_spec_str: Optional[str], 
        resize_images: bool, 
        max_dimension: Optional[int],
        model_id_option: Optional[str],
        system_prompt_option: Optional[str]
    ):
        """ 
        Fetch and process an arXiv paper. 
        Outputs Markdown text or, if a PROMPT is given, processes with an LLM.

        Examples:
          llm arxiv 2310.06825 -i P:1-3                # Markdown with images from pages 1-3
          llm arxiv 2310.06825 "Summarize this paper." -m gpt-4o # Summarize with gpt-4o
          llm arxiv 2310.06825 "What are the key contributions?" -i all -r 
        """
        try:
            temp_arxiv_id_cmd = extract_arxiv_id(paper_id_or_url)
            if not temp_arxiv_id_cmd:
                click.echo(f"Error: Invalid arXiv identifier or URL provided: {paper_id_or_url}", err=True)
                click.echo("Expected format like '2310.06825' or 'https://arxiv.org/abs/...'.", err=True)
                raise click.UsageError("Invalid arXiv identifier.")

            image_criteria_cmd: Optional[ImageSelectionCriteria] = None
            try:
                image_criteria_cmd = parse_image_selection_spec(include_images_spec_str)
            except ValueError as e:
                click.echo(f"Error in --include-images value ('{include_images_spec_str}'): {e}", err=True)
                raise click.BadParameter(str(e), param_hint='--include-images')

            actual_resize_option: Union[bool, int] = False
            if resize_images:
                if max_dimension and max_dimension > 0:
                    actual_resize_option = max_dimension
                else: 
                    actual_resize_option = True 
            
            markdown_text, attachments, paper_source_url = _process_arxiv_paper(
                paper_id_or_url, 
                image_criteria_cmd, 
                actual_resize_option
            )

            if prompt:
                # Process with LLM
                model_name_to_use = model_id_option
                model_obj = None

                if model_name_to_use:
                    try:
                        model_obj = llm.get_model(model_name_to_use)
                    except llm.UnknownModelError:
                        raise click.UsageError(f"Unknown model: {model_name_to_use}. See 'llm models list'.")
                else:
                    try:
                        # Attempt to get the default model
                        model_obj = llm.get_model(None) # This will get the default
                        if model_obj:
                             model_name_to_use = model_obj.model_id # Get the name for potential error messages
                        else: # Should not happen if llm.get_model(None) works as expected
                            raise llm.UnknownModelError("No default model configured.")
                    except llm.UnknownModelError: # Catches if no default is set or llm.get_model(None) fails
                        # Check if any models are installed at all before giving up
                        try:
                            # A bit of a hack: try to list models to see if any exist.
                            # This doesn't rely on get_models_aliases_and_paths() directly.
                            if not list(llm.get_plugins(group="llm.plugins.model")): # Check if model plugins exist
                                raise click.UsageError(
                                    "No LLM models found. Please install models, e.g., 'llm install llm-gpt4all-j'"
                                )
                        except Exception: # Broad catch if get_plugins is not available or fails
                             pass # Fall through to the next error

                        raise click.UsageError(
                            "No model specified with -m/--model, and no default model is set or found. "
                            "Ensure a default model is set (e.g., 'llm default-model MODEL_NAME') or provide one with -m."
                        )
                    except Exception as e: # Catch any other error from get_model(None)
                        raise click.UsageError(f"Could not load default LLM model: {e}")


                if not model_obj: # Should be caught above, but as a safeguard
                     raise click.UsageError("Failed to load an LLM model.")

                doc_fragment = llm.Fragment(content=markdown_text, source=paper_source_url)
                
                response_obj = model_obj.prompt(
                    prompt=prompt,
                    system=system_prompt_option,
                    fragments=[doc_fragment],
                    attachments=attachments
                )
                
                for chunk in response_obj:
                    click.echo(chunk, nl=False)
                click.echo() # Final newline

                # Consider showing cost if available and desired, e.g.:
                # if hasattr(response_obj, 'cost_tracker') and response_obj.cost_tracker:
                #    cost = response_obj.cost_tracker.cost
                #    if cost:
                #       click.echo(f"LLM Cost: ${cost:.6f}", err=True)

            else:
                # Original behavior: print Markdown
                click.echo(markdown_text)
                if image_criteria_cmd: # Only print if images were potentially processed
                    if attachments:
                        print(f"---Processed {len(attachments)} image attachment(s) based on selection criteria '{include_images_spec_str}'.---", file=sys.stderr)
                    elif include_images_spec_str and include_images_spec_str.lower() not in ["none", "false", "no", "0"]:
                         print(f"---Image inclusion was specified ('{include_images_spec_str}'), but no images were found or selected in the document.---", file=sys.stderr)
        
        except UnexpectedEmptyPageError as e:
             click.echo(f"Error: arXiv search returned an unexpected empty page for '{paper_id_or_url}'. Check the ID/URL. Details: {e}", err=True)
        except HTTPError as e:
            click.echo(f"Error: Failed to fetch paper details from arXiv for '{paper_id_or_url}'. Check network or ID/URL. Details: {e}", err=True)
        except ValueError as e: 
            click.echo(f"Error processing {paper_id_or_url}: {e}", err=True)
        except click.ClickException:
            raise
        except Exception as e: 
            click.echo(f"An unexpected error occurred while processing {paper_id_or_url}: {e}", err=True)

    # New arxiv_search command registration
    @cli.command(name="arxiv-search")
    @click.argument("query_string", required=True)
    @click.option(
        "--max-results", "-n",
        type=int,
        default=5,
        show_default=True,
        help="Maximum number of search results to return."
    )
    @click.option(
        "--sort-by",
        type=click.Choice(["relevance", "lastUpdatedDate", "submittedDate"], case_sensitive=False),
        default="relevance",
        show_default=True,
        help="Sort order for search results."
    )
    @click.option(
        "--details",
        is_flag=True,
        help="Show more details for each result (authors, full abstract, categories, dates)."
    )
    def arxiv_search_command(query_string: str, max_results: int, sort_by: str, details: bool):
        """Search arXiv for papers matching the QUERY_STRING."""
        try:
            sort_criterion_map = {
                "relevance": arxiv.SortCriterion.Relevance,
                "lastupdateddate": arxiv.SortCriterion.LastUpdatedDate,
                "submitteddate": arxiv.SortCriterion.SubmittedDate
            }
            actual_sort_criterion = sort_criterion_map[sort_by.lower()]

            search = arxiv.Search(
                query=query_string,
                max_results=max_results,
                sort_by=actual_sort_criterion
            )
            
            results = list(search.results())

            if not results:
                click.echo(f"No results found for query: '{query_string}'")
                return

            click.echo(f"Found {len(results)} result(s) for '{query_string}' (sorted by {sort_by}):\n")
            
            all_commands_to_copy = [] # List to store all commands

            for i, paper in enumerate(results):
                clean_id = extract_arxiv_id(paper.entry_id)
                click.echo(f"[{i+1}] ID: {clean_id}")
                click.echo(f"    Title: {paper.title}")

                command_to_run = f"llm arxiv {clean_id}"
                all_commands_to_copy.append(command_to_run) # Add to list

                # Styled command for display: bold, green, and underlined
                display_command = click.style(f"$ {command_to_run}", fg="green", bold=True, underline=True)
                
                # No OSC 52 sequence here per result, just display
                click.echo(f"    Command: {display_command}")

                if details:
                    authors_str = ", ".join([author.name for author in paper.authors])
                    click.echo(f"    Authors: {authors_str}")
                    click.echo(f"    Published: {paper.published.strftime('%Y-%m-%d %H:%M:%S %Z') if paper.published else 'N/A'}")
                    click.echo(f"    Updated: {paper.updated.strftime('%Y-%m-%d %H:%M:%S %Z') if paper.updated else 'N/A'}")
                    primary_category = paper.primary_category
                    categories_str = ", ".join(paper.categories)
                    click.echo(f"    Primary Category: {primary_category if primary_category else 'N/A'}")
                    click.echo(f"    Categories: {categories_str if categories_str else 'N/A'}")
                    click.echo(f"    Abstract: {paper.summary.replace('\n', ' ')}")
                    click.echo(f"    PDF Link: {paper.pdf_url}")
                else:
                    brief_summary = (paper.summary[:200] + '...') if len(paper.summary) > 200 else paper.summary
                    click.echo(f"    Abstract (brief): {brief_summary.replace('\n', ' ')}")
                click.echo("---")
            
            # After the loop, if there are commands, try to copy them all
            if all_commands_to_copy:
                concatenated_commands = "\n".join(all_commands_to_copy)
                b64_concatenated_commands = base64.b64encode(concatenated_commands.encode('utf-8')).decode('utf-8')
                osc_clipboard_all_seq = f"\033]52;c;{b64_concatenated_commands}\a"
                # Emit the OSC 52 sequence. It's non-visible.
                # We can print it to sys.stdout directly or via click.echo without a newline if preferred.
                # Using sys.stdout.write to avoid any potential click formatting/newlines.
                sys.stdout.write(osc_clipboard_all_seq)
                sys.stdout.flush() # Ensure it gets sent
                click.echo(f"\n(Attempted to copy {len(all_commands_to_copy)} command(s) to clipboard)", err=True)

        except HTTPError as e:
            click.echo(f"Error connecting to arXiv for search: {e}", err=True)
        except Exception as e:
            click.echo(f"An unexpected error occurred during search: {e}", err=True)