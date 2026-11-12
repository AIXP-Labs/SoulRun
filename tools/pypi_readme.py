"""The long description a package carries: README.md with its links made absolute.

README.md links to the other files of this repository by relative paths (``[GUIDE](GUIDE.md)``) and to its own
headings by anchors (``#known-limits``). On GitHub both work; on a package index the README is shown on its own and
both lead nowhere. This hatchling metadata hook hands the build README.md with every such link written against the
repository's address (``[project.urls] Repository``): a file as ``<repository>/blob/main/<path>``, an anchor as
``<repository>#<anchor>``. README.md itself is not changed; only the copy in the package metadata is.

Built-in to hatchling (``[tool.hatch.metadata.hooks.custom]``): no plugin to install, nothing at run time.
"""
from __future__ import annotations

import re
from pathlib import Path

try:
    from hatchling.metadata.plugin.interface import MetadataHookInterface
except ImportError:                                  # the tests use pypi_readme() alone, without hatchling
    MetadataHookInterface = object

README = "README.md"
# A Markdown link or image whose target is not already an address: [text](target) or ![alt](target).
LINK = re.compile(r"(\]\()(?!https?://|mailto:)([^)\s]+)(\))")


def pypi_readme(text: str, repository: str) -> str:
    """The README with every relative link and anchor written against the repository's address."""
    base = repository.rstrip("/")

    def absolute(match: re.Match) -> str:
        target = match.group(2)
        if target.startswith("#"):
            address = base + target
        else:
            address = f"{base}/blob/main/{target[2:] if target.startswith('./') else target}"
        return match.group(1) + address + match.group(3)

    return LINK.sub(absolute, text)


def relative_targets(text: str) -> list[str]:
    """The relative link targets (files and anchors) of a Markdown text."""
    return [m.group(2) for m in LINK.finditer(text)]


class CustomMetadataHook(MetadataHookInterface):
    PLUGIN_NAME = "custom"

    def update(self, metadata: dict) -> None:
        repository = metadata["urls"]["Repository"]
        text = (Path(self.root) / README).read_text(encoding="utf-8")
        metadata["readme"] = {"content-type": "text/markdown", "text": pypi_readme(text, repository)}
