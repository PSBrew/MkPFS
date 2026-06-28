---
name: PyPI packaging guidelines
description: Practical checklist for publishing a good Python library to PyPI
type: reference
---

Use `pyproject.toml` as the primary source of packaging metadata.

Keep core metadata explicit: name, version, supported Python versions, runtime dependencies, license, README, keywords, classifiers, and project URLs.

Build and publish both source distributions and wheels.

Prefer a package directory layout for multi-file libraries.

Keep dependency groups separate from runtime dependencies when possible.

For a small pure-Python library, keep metadata centralized, document the project clearly in the README, and ensure the README renders safely on PyPI.

## README guidance

Use a supported format: Markdown, reStructuredText, or plain text.

Keep the README at the repository root and use it as the long description.

Make the content renderer-safe for PyPI and validate builds before publishing.

## Repo-specific notes

- Package name: `mkpfs`; CLI entrypoint defined in pyproject.
- Keep README command reference aligned with CLI surface: `pack`, `verify`, `inspect`, `tree`, `unpack`.
- Validate release artifacts with `uv build` and `uv run --frozen twine check dist/*` before publishing.

## References

- https://packaging.python.org/en/latest/overview/
- https://packaging.python.org/en/latest/specifications/
- https://packaging.python.org/en/latest/guides/making-a-pypi-friendly-readme/
