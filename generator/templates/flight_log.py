"""SVG template: Flight Log terminal (850x180) — recent commit activity."""

from generator.utils import esc

WIDTH, HEIGHT = 850, 180
MAX_ENTRIES = 5
LINE_HEIGHT = 18


def _commit_type(message: str) -> str:
    """Classify a conventional commit prefix. Returns one of:
    feat, fix, chore, docs, refactor, test, style, perf, or 'other'.
    """
    lower = message.lower().lstrip()
    for prefix in ("feat", "fix", "chore", "docs", "refactor", "test", "style", "perf"):
        if lower.startswith(prefix + ":") or lower.startswith(prefix + "("):
            return prefix
    return "other"


def _type_color(commit_type: str, theme: dict) -> str:
    """Map commit type to a theme color."""
    mapping = {
        "feat": theme.get("synapse_cyan", "#00d4ff"),
        "fix": theme.get("axon_amber", "#ffb020"),
        "perf": theme.get("axon_amber", "#ffb020"),
        "refactor": theme.get("dendrite_violet", "#a78bfa"),
        "docs": theme.get("text_dim", "#94a3b8"),
        "chore": theme.get("text_dim", "#94a3b8"),
        "test": theme.get("text_dim", "#94a3b8"),
        "style": theme.get("text_dim", "#94a3b8"),
        "other": theme.get("text_bright", "#f1f5f9"),
    }
    return mapping.get(commit_type, theme.get("text_bright", "#f1f5f9"))


def _format_timestamp(iso: str) -> str:
    """Render an ISO8601 timestamp as 'YYYY-MM-DD HH:MM'. Tolerant to bad input."""
    if not iso:
        return "----/--/-- --:--"
    # Accept "2026-04-10T14:32:00Z" and similar.
    try:
        date_part, time_part = iso.split("T", 1)
        hm = time_part[:5]
        return f"{date_part} {hm}"
    except (ValueError, IndexError):
        return iso[:16]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def render(entries: list, theme: dict, username: str = "") -> str:
    """Render the flight log terminal SVG.

    Args:
        entries: list of dicts {sha, message, timestamp, repo}
        theme: color palette dict
        username: optional, used in the prompt line header
    """
    entries = (entries or [])[:MAX_ENTRIES]

    title_color = theme.get("text_faint", "#64748b")
    prompt_color = theme.get("synapse_cyan", "#00d4ff")
    ts_color = theme.get("text_faint", "#64748b")
    sha_color = theme.get("dendrite_violet", "#a78bfa")
    empty_color = theme.get("text_dim", "#94a3b8")

    # Prompt line
    prompt_text = (
        f"$ git log --author={username} -{MAX_ENTRIES}"
        if username
        else f"$ git log -{MAX_ENTRIES}"
    )

    # Build log lines
    line_elements = []
    start_y = 78
    for i, entry in enumerate(entries):
        y = start_y + i * LINE_HEIGHT
        ts = _format_timestamp(entry.get("timestamp", ""))
        sha = (entry.get("sha") or "")[:7]
        msg = _truncate(entry.get("message", ""), 60)
        ctype = _commit_type(msg)
        msg_color = _type_color(ctype, theme)
        delay = f"{0.4 + i * 0.35:.2f}s"

        line_elements.append(
            f'''    <g opacity="0">
      <text x="30" y="{y}" fill="{ts_color}" font-size="11" font-family="monospace">[{esc(ts)}]</text>
      <text x="160" y="{y}" fill="{sha_color}" font-size="11" font-family="monospace">{esc(sha)}</text>
      <text x="225" y="{y}" fill="{msg_color}" font-size="11" font-family="monospace">{esc(msg)}</text>
      <animate attributeName="opacity" from="0" to="1" dur="0.3s" begin="{delay}" fill="freeze"/>
    </g>'''
        )

    # Fallback when there are no entries
    if not entries:
        line_elements.append(
            f'''    <text x="30" y="{start_y}" fill="{empty_color}" font-size="11"
        font-family="monospace" opacity="0.7">
      # No recent activity in the last 90 days.
    </text>'''
        )

    lines_str = "\n".join(line_elements)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="flight-scanline" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{prompt_color}" stop-opacity="0"/>
      <stop offset="50%" stop-color="{prompt_color}" stop-opacity="0.12"/>
      <stop offset="100%" stop-color="{prompt_color}" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="flight-clip">
      <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" ry="12"/>
    </clipPath>
  </defs>

  <!-- Card background -->
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" ry="12"
        fill="{theme['void']}" stroke="{theme['star_dust']}" stroke-width="1"/>

  <!-- Section title -->
  <text x="30" y="28" fill="{title_color}" font-size="11" font-family="monospace" letter-spacing="3">FLIGHT LOG</text>

  <!-- Prompt line -->
  <text x="30" y="55" fill="{prompt_color}" font-size="11" font-family="monospace">{esc(prompt_text)}</text>

  <!-- Log entries -->
{lines_str}

  <!-- CRT scanline sweep -->
  <g clip-path="url(#flight-clip)">
    <rect x="0" y="-30" width="{WIDTH}" height="30" fill="url(#flight-scanline)">
      <animateTransform attributeName="transform" type="translate"
        from="0 0" to="0 {HEIGHT + 30}" dur="8s" repeatCount="indefinite"/>
    </rect>
  </g>
</svg>'''
