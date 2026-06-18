"""Parse unified diff into DiffSummary dict, replacing diff_reader_agent."""

import os

_EXT_LANG = {
    ".kt": "kotlin",
    ".java": "java",
    ".py": "python",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "typescript",
    ".sql": "sql",
    ".xml": "other",
    ".json": "other",
    ".md": "other",
}


def _lang_from_path(path: str) -> str:
    _, ext = os.path.splitext(path)
    return _EXT_LANG.get(ext.lower(), "other")


def parse_diff(pr_url: str, diff_content: str) -> dict:
    """Parse a unified diff string into DiffSummary dict.

    Output schema matches what diff_reader_agent used to produce:
    { "pr_url": str, "hunks": [{ "file": str, "lang": str, "diff_text": str }] }
    """
    hunks = []
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff_content.split("\n"):
        if line.startswith("--- ") and not line.startswith("--- /dev/null"):
            if current_file is not None and current_lines:
                hunks.append({
                    "file": current_file,
                    "lang": _lang_from_path(current_file),
                    "diff_text": "\n".join(current_lines),
                })
            current_file = line[4:].strip()
            current_lines = [line]
        elif current_file is not None:
            current_lines.append(line)

    if current_file is not None and current_lines:
        hunks.append({
            "file": current_file,
            "lang": _lang_from_path(current_file),
            "diff_text": "\n".join(current_lines),
        })

    return {"pr_url": pr_url, "hunks": hunks}
