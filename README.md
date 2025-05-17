# llm-arxiv

[![PyPI](https://img.shields.io/pypi/v/llm-arxiv.svg)](https://pypi.org/project/llm-arxiv/)
[![Changelog](https://img.shields.io/github/v/release/agustif/llm-arxiv?include_prereleases&label=changelog)](https://github.com/agustif/llm-arxiv/releases)
[![Tests](https://github.com/agustif/llm-arxiv/actions/workflows/test.yml/badge.svg)](https://github.com/agustif/llm-arxiv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/agustif/llm-arxiv/blob/main/LICENSE)

LLM plugin for loading arXiv papers and their images.

This plugin allows you to search for arXiv papers, fetch their text content, and optionally, their images directly into `llm`.

## Installation

Install this plugin in the same environment as [LLM](https://llm.datasette.io/).

```bash
llm install llm-arxiv
```

The command above will also install the necessary dependencies: `arxiv`, `PyMuPDF`, and `Pillow`.

## Usage

This plugin provides three main ways to interact with arXiv papers:

1.  **As a fragment loader:** Allows you to inject arXiv paper content (text and optionally images) directly into a prompt using the `-f` or `--fragment` option with `llm`.
2.  **As a standalone command (`llm arxiv`):** Provides an `llm arxiv` command to fetch, process, and output paper content directly to stdout, which can then be piped to other commands or models.
3.  **As a search command (`llm arxiv-search`):** Allows you to search arXiv for papers based on a query string.

### 1. Fragment Loader (`-f arxiv:...`)

You can load an arXiv paper by its ID or full URL. The text content (converted to Markdown) and any selected images (as attachments) will be passed to the language model.

**Syntax:**

`llm -f 'arxiv:PAPER_ID_OR_URL[?options]' "Your prompt here..."`

*   `PAPER_ID_OR_URL`: Can be an arXiv ID (e.g., `2310.06825`, `astro-ph/0601009`) or a full arXiv URL (e.g., `https://arxiv.org/abs/2310.06825`, `http://arxiv.org/pdf/2310.06825.pdf`).
*   `[?options]`: Optional query parameters to control image inclusion and resizing. (Remember to quote the argument if using `?` or `&` in your shell).

**Fragment Loader Options:**

*   `i` / `include_images`: Controls image inclusion. If not specified, no images are included.
    *   `?i` or `?i=` or `?i=all`: Include all images from the paper.
    *   `?i=none`: Include no images (same as omitting `?i`).
    *   `?i=P:pages`: Include all images from specified pages. `pages` is a comma-separated list of page numbers or ranges (e.g., `P:1`, `P:1,3-5`, `P:2,4`). Page numbers are 1-indexed.
    *   `?i=G:indices`: Include images by their global index in the document (sequentially numbered as they appear). `indices` is a comma-separated list of image indices or ranges (e.g., `G:1`, `G:1-5,10`). Indices are 1-indexed.
*   `r` / `resize_images`: Controls image resizing. Resizing only applies if images are included.
    *   `?r` or `?r=true`: Enable image resizing. Images will be resized to a maximum dimension of 512px by default, preserving aspect ratio. Only images larger than this will be downscaled.
    *   `?r=PIXELS`: Enable image resizing and set a custom maximum dimension (e.g., `?r=800`).

**Examples (Fragment Loader):**

*   Load text only:
    ```bash
    llm -f 'arxiv:2310.06825' "Summarize this paper."
    ```
*   Load text and all images (resized to default 512px max):
    ```bash
    llm -f 'arxiv:2310.06825?i&r' -m gpt-4-vision-preview "Explain the diagrams in this paper."
    ```
*   Load text and images from page 1 and 3, resized to 800px max:
    ```bash
    llm -f 'arxiv:2310.06825?i=P:1,3&r=800' -m gemini-pro-vision "Describe the images on pages 1 and 3."
    ```
*   Load text and the first 5 globally indexed images, no resizing:
    ```bash
    llm -f 'arxiv:2310.06825?i=G:1-5' -m some-image-model "What do the first five images show?"
    ```

### 2. Standalone Command (`llm arxiv ...`)

The `llm arxiv` command fetches and processes an arXiv paper.
*   If no prompt is provided, it outputs the paper's content as Markdown to standard output. This can be piped to other commands or LLMs.
*   If a `PROMPT` is provided, it processes the paper content (including any selected images as attachments) with the specified or default LLM.

**Syntax:**

`llm arxiv PAPER_ID_OR_URL [PROMPT] [OPTIONS]`

**Arguments:**

*   `PAPER_ID_OR_URL`: The arXiv ID (e.g., `2310.06825`) or full URL.
*   `PROMPT` (Optional): A prompt to send to an LLM along with the paper's content.

**Command Options:**

*   `-i SPEC` / `--include-images SPEC`:
    Controls image inclusion. If not specified and a prompt is given, `parse_image_selection_spec`'s default behavior for `None` (no images) applies. If no prompt is given, no images are processed by default.
    *   `-i all` or (if `PROMPT` is present) simply `-i` with no value: Include all images.
    *   `-i ""` (empty string value): Include all images.
    *   `-i none`: Include no images.
    *   `-i P:pages`: Include all images from specified pages (e.g., `P:1`, `P:1,3-5`).
    *   `-i G:indices`: Include images by their global index (e.g., `G:1`, `G:1-5,10`).
*   `-r` / `--resize-images`:
    Enable image resizing. Images will be resized to a maximum dimension of 512px by default, preserving aspect ratio. Only images larger than this will be downscaled.
*   `-d PIXELS` / `--max-dimension PIXELS`:
    Set a custom maximum dimension in pixels for resizing. Requires `-r` to be active.
*   `-m MODEL_ID` / `--model MODEL_ID`:
    Specify the LLM model to use if a `PROMPT` is provided.
*   `-s SYSTEM_PROMPT` / `--system SYSTEM_PROMPT`:
    Specify a system prompt to use with the LLM if a `PROMPT` is provided.

**Examples (Standalone Command):**

*   Get Markdown content of a paper:
    ```bash
    llm arxiv 2310.06825
    ```
*   Get Markdown, prepare all images (resized), then pipe to a model:
    ```bash
    llm arxiv 2310.06825 -i all -r | llm -m gpt-4-vision-preview "Summarize this, paying attention to figures."
    ```
*   Directly prompt an LLM with the paper's content and images from pages 2 and 4 (resized to 600px):
    ```bash
    llm arxiv 2310.06825 "Explain figures on page 2 and 4." -i P:2,4 -r -d 600 -m gpt-4o
    ```
*   Summarize a paper using the default LLM and include all images:
    ```bash
    llm arxiv 2310.06825 "Summarize the key findings." -i all
    ```

### 3. Search Command (`llm arxiv-search ...`)

The `llm arxiv-search` command allows you to search for papers on arXiv using a query string.

**Syntax:**

`llm arxiv-search [OPTIONS] QUERY_STRING`

**Arguments:**

*   `QUERY_STRING`: The search query (e.g., "quantum computing", "author:Hawking title:black holes"). See [arXiv API user manual](https://arxiv.org/help/api/user-manual#query_details) for advanced query syntax.

**Options:**

*   `-n INT`, `--max-results INT`: Maximum number of search results to return (Default: `5`).
*   `--sort-by [relevance|lastUpdatedDate|submittedDate]`: Sort order for search results (Default: `relevance`).
*   `--details`: Show more details for each result, including authors, full abstract, categories, publication/update dates, and PDF link.

**Output:**

For each search result, the command will display:
*   The paper's ID and Title.
*   A suggested command to fetch the full paper with `llm arxiv <ID>`. This command is styled (e.g., bold, green, underlined, prefixed with `$`) for visibility.
*   A brief abstract (or full details if `--details` is used).

Additionally, the script will attempt to copy all the suggested `llm arxiv <ID>` commands (newline-separated) to your system clipboard using an OSC 52 escape sequence. A message like `(Attempted to copy N command(s) to clipboard)` will be printed to stderr. The success of this automatic copy depends on your terminal emulator's support and configuration (e.g., iTerm2 needs clipboard access enabled for applications).

**Examples (Search Command):**

*   Search for "large language models" and get top 3 results (brief):
    ```bash
    llm arxiv-search -n 3 "large language models"
    ```
    (This will also attempt to copy the 3 suggested `llm arxiv` commands to your clipboard.)

*   Search for papers by author "Hinton" on "neural networks", sorted by submission date, with full details:
    ```bash
    llm arxiv-search --sort-by submittedDate --details "au:Hinton AND ti:\"neural network\""
    ```

## Image Handling Notes

*   **Rationale for Optional Images:** Processing and including images can significantly increase the data size sent to language models. Many models have limitations on input context window size, and some may not support image inputs at all or may incur higher costs for them. The granular controls for image inclusion (all, none, specific pages/indices) and resizing allow users to manage this, ensuring that only necessary visual information is passed to the LLM, optimizing for cost, speed, and model compatibility.
*   Images are extracted from the PDF, converted to Markdown placeholders `[IMAGE: http://arxiv.org/abs/ID#page_X_img_Y]`, and attached as `llm.Attachment` objects if selected.
*   Supported input image formats from PDFs include common types like JPEG, PNG, GIF, BMP. Efforts are made to convert others, but complex or rare formats might be skipped.
*   When resized, images are converted to JPEG (for most common types) or PNG (if transparency or other features warrant it) to save tokens and improve compatibility with models.
*   Image processing errors are printed to `stderr` but do not stop the text extraction.

## Development

To contribute to this plugin, clone the repository and install it in editable mode:

```bash
git clone https://github.com/agustif/llm-arxiv.git
cd llm-arxiv
# It's recommended to use a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows use `venv\\Scripts\\activate`
# Install in editable mode
pip install -e .
# Install additional dependencies for testing (e.g., pytest, pytest-cov)
pip install pytest pytest-cov
# Run tests
pytest tests/
```

## AGENTS.md

See [AGENTS.md](AGENTS.md) for notes on how AI agents should interpret and use this tool and its outputs.
