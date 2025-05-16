# AI Agent Instructions for `llm-arxiv`

This document provides guidance for AI agents assisting with the development and maintenance of the `llm-arxiv` repository.

## Project Overview

`llm-arxiv` is a Python-based plugin for the [LLM CLI tool](https://llm.datasette.io/) that enables users to load and process academic papers from arXiv. It fetches paper metadata and content, typically the PDF, and makes it available for language model processing.

## Key Files and Directories

*   **`llm_arxiv.py`**: This is the core file containing the plugin's logic. It implements the LLM plugin interface and handles fetching and processing arXiv papers. The `[project.entry-points.llm]` section in `pyproject.toml` points to this file (`arxiv = "llm_arxiv"`).
*   **`pyproject.toml`**: The main configuration file for the project. It defines dependencies (e.g., `llm`, `arxiv`, `PyMuPDF`), build system settings, project metadata, and the plugin entry point.
*   **`arxiv.py`**: This file might contain utility functions or a script related to interacting with the `arxiv` package or API. Be cautious if modifying, as its role needs to be clearly understood in context of the main `llm_arxiv.py` plugin.
*   **`fitz.py`**: This file likely contains utility functions or a script related to PDF processing, using `PyMuPDF` (which provides Fitz bindings). Similar to `arxiv.py`, understand its specific role before making changes.
*   **`README.md`**: The primary documentation for human users of the plugin. It should be kept up-to-date with features, installation instructions, and usage examples.
*   **`AGENTS.md`**: (This file) Contains specific instructions and context for AI agents working on this codebase.
*   **`tests/`**: This directory contains automated tests for the plugin, likely using `pytest`. New features and bug fixes should ideally be accompanied by relevant tests.
*   **`.github/workflows/`**: Contains GitHub Actions workflow definitions, for example, for running tests automatically.

## Common Development Tasks

When asked to perform tasks, consider the following:

*   **Adding Features**:
    *   Modifications will likely center around `llm_arxiv.py`.
    *   Consider how new features impact dependencies (`pyproject.toml`).
    *   Add corresponding tests in the `tests/` directory.
    *   Update `README.md` with user-facing documentation for the new feature.
*   **Bug Fixing**:
    *   Identify the relevant module (`llm_arxiv.py`, `arxiv.py`, `fitz.py`).
    *   Write a test case that reproduces the bug if possible.
    *   Ensure the fix doesn't break existing functionality by running all tests.
*   **Dependency Management**:
    *   Changes to dependencies are made in `pyproject.toml`.
    *   Be mindful of version compatibility.
*   **Documentation**:
    *   Keep `README.md` clear and up-to-date.
    *   Update this file (`AGENTS.md`) if there are significant changes to the development workflow or codebase structure relevant to AI agents.

## Important Considerations

*   **arXiv API Usage**: If directly interacting with the arXiv API (via the `arxiv` package or otherwise), be mindful of rate limits and terms of service.
*   **PDF Parsing**: PDF parsing can be complex. `PyMuPDF` (Fitz) is used. Ensure robustness and handle potential errors gracefully.
*   **Code Style and Quality**: Follow existing code style. Ensure code is clear, well-commented where non-obvious, and efficient.
*   **Testing**: Always aim to maintain or increase test coverage.

By following these guidelines, AI agents can contribute effectively to the `llm-arxiv` project. 