"""File exchange system for the gateway.

Handles bidirectional file exchange between agents and users:
- Inbound: Channel adapters download media, append
  [file: /path] to message text
- Outbound: Agents include [send_file: /path] in responses,
  files attached to outbound message
- Long responses (>4000 chars) saved as .md file and attached
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SEND_FILE_PATTERN = re.compile(r"\[send_file:\s*([^\]]+)\]")
FILE_REF_PATTERN = re.compile(r"\[file:\s*([^\]]+)\]")
LONG_RESPONSE_THRESHOLD = 4000


def extract_send_files(text: str) -> tuple[str, list[Path]]:
    """Extract [send_file: /path] tags from response text.

    Returns (cleaned_text, list_of_file_paths).
    Validates each path exists before including.
    """
    files: list[Path] = []
    for match in SEND_FILE_PATTERN.finditer(text):
        raw_path = match.group(1).strip()
        path = Path(raw_path).expanduser()
        if path.exists():
            files.append(path)
        else:
            logger.warning(
                "send_file path does not exist, skipping: %s",
                raw_path,
            )

    # Strip all send_file tags (even for missing files)
    cleaned = SEND_FILE_PATTERN.sub("", text).strip()
    # Collapse any resulting triple-newlines
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")

    return cleaned, files


def append_file_reference(text: str, file_path: Path) -> str:
    """Append [file: /path] reference to message text."""
    ref = f"[file: {file_path}]"
    if text:
        return f"{text}\n{ref}"
    return ref


def handle_long_response(
    text: str,
    files_dir: Path,
) -> tuple[str, Path | None]:
    """If text exceeds threshold, save to .md and return preview.

    Returns (display_text, file_path_or_none).
    If the text is short enough, returns (text, None) unchanged.
    """
    if len(text) <= LONG_RESPONSE_THRESHOLD:
        return text, None

    # Save full response as timestamped markdown file
    files_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_path = files_dir / f"response_{stamp}.md"
    file_path.write_text(text, encoding="utf-8")
    logger.info(
        "Long response (%d chars) saved to %s",
        len(text),
        file_path,
    )

    # Return truncated preview
    preview = text[:500] + "\n\n... (full response attached as file)"
    return preview, file_path


def resolve_files_dir(config: dict[str, Any]) -> Path:
    """Resolve files directory from config.

    Defaults to ~/.letsgo/gateway/files.
    """
    raw = config.get("files_dir", "~/.letsgo/gateway/files")
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path
