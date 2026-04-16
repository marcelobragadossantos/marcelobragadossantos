"""SVG template: Contribution Graph (850x220) — 52-week area chart with grid."""

import math

WIDTH, HEIGHT = 850, 220
GRAPH_LEFT = 60
GRAPH_RIGHT = 820
GRAPH_TOP = 55
GRAPH_BOTTOM = 175


def render(commit_weeks: list, theme: dict) -> str:
    """Render a 52-week contribution area chart.

    Args:
        commit_weeks: list of ints (oldest → newest), ideally 52 entries
        theme: color palette dict
    """
    commit_weeks = commit_weeks or []
    accent = theme.get("synapse_cyan", "#00d4ff")
    violet = theme.get("dendrite_violet", "#a78bfa")
    faint = theme.get("text_faint", "#64748b")
    dim = theme.get("text_dim", "#94a3b8")
    grid_color = theme.get("star_dust", "#1a2332")

    graph_w = GRAPH_RIGHT - GRAPH_LEFT
    graph_h = GRAPH_BOTTOM - GRAPH_TOP

    if not commit_weeks or len(commit_weeks) < 2:
        return _render_empty(theme, accent, faint)

    max_v = max(commit_weeks) or 1
    n = len(commit_weeks)
    step = graph_w / (n - 1)

    # Build polyline points
    points = []
    for i, v in enumerate(commit_weeks):
        px = GRAPH_LEFT + i * step
        py = GRAPH_BOTTOM - (v / max_v) * graph_h
        points.append((px, py))

    points_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    # Area fill polygon (closed to baseline)
    area_str = (
        f"{GRAPH_LEFT:.1f},{GRAPH_BOTTOM:.1f} "
        + points_str
        + f" {GRAPH_RIGHT:.1f},{GRAPH_BOTTOM:.1f}"
    )

    # Horizontal grid lines (4 levels)
    grid_lines = []
    for i in range(1, 5):
        gy = GRAPH_BOTTOM - (graph_h * i / 4)
        label_val = int(max_v * i / 4)
        grid_lines.append(
            f'    <line x1="{GRAPH_LEFT}" y1="{gy:.1f}" x2="{GRAPH_RIGHT}" '
            f'y2="{gy:.1f}" stroke="{grid_color}" stroke-width="0.5" opacity="0.6"/>'
        )
        grid_lines.append(
            f'    <text x="{GRAPH_LEFT - 8}" y="{gy + 3:.1f}" fill="{faint}" '
            f'font-size="9" font-family="monospace" text-anchor="end">{label_val}</text>'
        )
    grid_str = "\n".join(grid_lines)

    # Month labels along the bottom (every ~4.3 weeks)
    month_labels = _build_month_labels(n, faint)

    # Weekly peak indicator
    peak_idx = commit_weeks.index(max(commit_weeks))
    peak_x, peak_y = points[peak_idx]
    peak_val = max(commit_weeks)

    # Total contributions
    total = sum(commit_weeks)

    # Summary stats on the right
    avg_week = total / n if n > 0 else 0
    recent_4 = sum(commit_weeks[-4:]) if len(commit_weeks) >= 4 else total

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <linearGradient id="area-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{accent}" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="{accent}" stop-opacity="0.03"/>
    </linearGradient>
    <linearGradient id="line-grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{violet}"/>
      <stop offset="50%" stop-color="{accent}"/>
      <stop offset="100%" stop-color="{violet}"/>
    </linearGradient>
    <filter id="glow-graph" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Card background -->
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" ry="12"
        fill="{theme['nebula']}" stroke="{theme['star_dust']}" stroke-width="1"/>

  <!-- Title -->
  <text x="30" y="32" fill="{faint}" font-size="11" font-family="monospace" letter-spacing="3">CONTRIBUTION FLIGHT PATH</text>

  <!-- Summary badges -->
  <text x="{WIDTH - 30}" y="32" fill="{dim}" font-size="10" font-family="monospace" text-anchor="end">
    total: <tspan fill="{accent}" font-weight="bold">{total}</tspan>
    · avg/wk: <tspan fill="{accent}">{avg_week:.0f}</tspan>
    · last 28d: <tspan fill="{accent}">{recent_4}</tspan>
  </text>

  <!-- Baseline -->
  <line x1="{GRAPH_LEFT}" y1="{GRAPH_BOTTOM}" x2="{GRAPH_RIGHT}" y2="{GRAPH_BOTTOM}"
        stroke="{grid_color}" stroke-width="1"/>

  <!-- Grid -->
{grid_str}

  <!-- Month labels -->
{month_labels}

  <!-- Area fill -->
  <polygon points="{area_str}" fill="url(#area-grad)"/>

  <!-- Line -->
  <polyline points="{points_str}" fill="none" stroke="url(#line-grad)"
            stroke-width="2" stroke-linejoin="round" filter="url(#glow-graph)"/>

  <!-- Peak marker -->
  <circle cx="{peak_x:.1f}" cy="{peak_y:.1f}" r="4" fill="{accent}" opacity="0.9">
    <animate attributeName="r" values="3;5;3" dur="2s" repeatCount="indefinite"/>
    <animate attributeName="opacity" values="0.7;1;0.7" dur="2s" repeatCount="indefinite"/>
  </circle>
  <text x="{peak_x:.1f}" y="{peak_y - 10:.1f}" fill="{accent}" font-size="10"
        font-family="monospace" text-anchor="middle" font-weight="bold">{peak_val}</text>

  <!-- Zero label -->
  <text x="{GRAPH_LEFT - 8}" y="{GRAPH_BOTTOM + 3}" fill="{faint}" font-size="9"
        font-family="monospace" text-anchor="end">0</text>
</svg>'''


def _build_month_labels(n: int, color: str) -> str:
    """Build month labels spaced evenly along the x-axis."""
    import datetime

    today = datetime.date.today()
    graph_w = GRAPH_RIGHT - GRAPH_LEFT

    labels = []
    # Show a label roughly every 4 weeks
    for i in range(0, n, 4):
        weeks_ago = n - 1 - i
        d = today - datetime.timedelta(weeks=weeks_ago)
        month_str = d.strftime("%b")
        px = GRAPH_LEFT + (i / (n - 1)) * graph_w if n > 1 else GRAPH_LEFT
        labels.append(
            f'    <text x="{px:.1f}" y="{GRAPH_BOTTOM + 16}" fill="{color}" '
            f'font-size="9" font-family="monospace" text-anchor="middle">{month_str}</text>'
        )
    return "\n".join(labels)


def _render_empty(theme: dict, accent: str, faint: str) -> str:
    """Render a placeholder when no commit week data is available."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" ry="12"
        fill="{theme['nebula']}" stroke="{theme['star_dust']}" stroke-width="1"/>
  <text x="30" y="32" fill="{faint}" font-size="11" font-family="monospace" letter-spacing="3">CONTRIBUTION FLIGHT PATH</text>
  <text x="{WIDTH / 2}" y="{HEIGHT / 2 + 5}" fill="{faint}" font-size="12"
        font-family="monospace" text-anchor="middle" opacity="0.6">
    # No contribution data available. Configure a PAT with read:user scope.
  </text>
</svg>'''
