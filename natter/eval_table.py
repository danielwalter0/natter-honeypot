"""Render evaluation rows as a markdown table. Pure, no I/O."""

# Column order of the table. A row is a dict from these names to text.
COLUMNS = [
    "scenario",
    "status",
    "is_scam",
    "scam_type",
    "org",
    "payment",
    "amount",
    "injection",
    "identifiers P/R",
    "tactics P/R",
    "info P/R",
    "rejections",
    "quotes verified",
    "digit leaks",
    "safe stalls",
    "callback turn",
    "payment turn",
]


def render_table(rows: list[dict[str, str]]) -> str:
    """One markdown table. A missing cell is left blank."""
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for row in rows:
        lines.append("| " + " | ".join(row.get(name, "") for name in COLUMNS) + " |")
    return "\n".join(lines)
