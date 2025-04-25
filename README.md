# llm-arxiv

[![PyPI](https://img.shields.io/pypi/v/llm-arxiv.svg)](https://pypi.org/project/llm-arxiv/)
[![Changelog](https://img.shields.io/github/v/release/agustif/llm-arxiv?include_prereleases&label=changelog)](https://github.com/agustif/llm-arxiv/releases)
[![Tests](https://github.com/agustif/llm-arxiv/actions/workflows/test.yml/badge.svg)](https://github.com/agustif/llm-arxiv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/agustif/llm-arxiv/blob/main/LICENSE)

LLM plugin for loading arXiv paper text content using the `arxiv` API and PyMuPDF.

## Installation

Install this plugin in the same environment as [LLM](https://llm.datasette.io/).

```bash
llm install llm-arxiv
```

This plugin requires the `arxiv` and `PyMuPDF` packages.

## Usage

This plugin adds support for the `arxiv:` fragment prefix. You can use it to load the full text content of a paper from its arXiv ID or URL.

```bash
# Load by ID (new format)
llm -f arxiv:2310.06825

# Load by ID (old format)
llm -f arxiv:hep-th/0101001

# Load by URL
llm -f arxiv:https://arxiv.org/abs/2310.06825
```

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:
```bash
cd llm-arxiv
python -m venv venv
source venv/bin/activate
```
Now install the dependencies and test dependencies:
```bash
# Install in editable mode with test dependencies
python -m pip install -e '.[test]'
```
To run the tests:
```bash
pytest
```
