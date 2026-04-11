"""SVG template: Mission Telemetry stats card (850x220 with delta + sparkline)."""

from generator.utils import METRIC_ICONS, METRIC_LABELS, METRIC_COLORS, format_number

WIDTH, HEIGHT = 850, 220


def _format_delta(current: int, previous: int) -> tuple:
    """Return (symbol, text, is_up) for the delta between current and previous.

    Returns (None, "", None) if there's no meaningful delta to show.
    """
    if previous is None:
        return (None, "", None)
    diff = current - previous
    if diff == 0:
        return ("·", "+0", None)
    if diff > 0:
        return ("▲", f"+{format_number(diff)}", True)
    return ("▼", f"-{format_number(abs(diff))}", False)


def _build_sparkline(weeks: list, x: float, y: float, width: float, height: float,
                     color: str) -> str:
    """Build a small polyline sparkline from a list of week totals.

    Args:
        weeks: list of ints (oldest → newest), ideally 52 points
        x, y: top-left anchor
        width, height: bounding box
        color: stroke color

    Returns:
        SVG fragment (empty string if weeks is empty/degenerate)
    """
    if not weeks or len(weeks) < 2:
        return ""
    max_v = max(weeks)
    if max_v <= 0:
        max_v = 1
    n = len(weeks)
    step = width / (n - 1)
    points = []
    for i, v in enumerate(weeks):
        px = x + i * step
        # Flip Y: higher values up
        py = y + height - (v / max_v) * height
        points.append(f"{px:.1f},{py:.1f}")
    points_str = " ".join(points)
    # Baseline + polyline + subtle area fill
    baseline_y = y + height
    area_points = f"{x:.1f},{baseline_y:.1f} " + points_str + f" {x + width:.1f},{baseline_y:.1f}"
    return (
        f'      <polygon points="{area_points}" fill="{color}" fill-opacity="0.12"/>\n'
        f'      <polyline points="{points_str}" fill="none" stroke="{color}" '
        f'stroke-width="1.2" stroke-linejoin="round" opacity="0.85"/>'
    )


def render(stats: dict, metrics: list, theme: dict,
           previous_stats: dict = None, commit_weeks: list = None) -> str:
    """Render the stats card SVG.

    Args:
        stats: dict with keys like commits, stars, prs, issues, repos
        metrics: list of metric keys to display
        theme: color palette dict
        previous_stats: optional prior snapshot for delta computation
        commit_weeks: optional 52-week commit histogram for the sparkline
    """
    previous_stats = previous_stats or {}
    commit_weeks = commit_weeks or []
    cell_width = WIDTH / len(metrics)

    delta_up_color = theme.get("synapse_cyan", "#00d4ff")
    delta_down_color = theme.get("axon_amber", "#ffb020")
    delta_flat_color = theme.get("text_faint", "#64748b")

    # Build metric cells
    cells = []
    dividers = []
    for i, key in enumerate(metrics):
        cx = cell_width * i + cell_width / 2
        icon_color = theme.get(METRIC_COLORS.get(key, "synapse_cyan"), "#00d4ff")
        raw_value = stats.get(key, 0)
        value = format_number(raw_value)
        label = METRIC_LABELS.get(key, key.title())
        icon_path = METRIC_ICONS.get(key, "")
        delay = f"{i * 0.3}s"

        # Delta line
        delta_svg = ""
        symbol, delta_text, is_up = _format_delta(raw_value, previous_stats.get(key))
        if symbol is not None:
            if is_up is True:
                delta_color = delta_up_color
            elif is_up is False:
                delta_color = delta_down_color
            else:
                delta_color = delta_flat_color
            delta_svg = (
                f'      <text x="0" y="38" text-anchor="middle" fill="{delta_color}" '
                f'font-size="10" font-family="monospace" letter-spacing="0.5">'
                f'{symbol} {delta_text}</text>'
            )

        # Sparkline only on the commits cell
        sparkline_svg = ""
        if key == "commits" and commit_weeks:
            spark_w = cell_width - 40
            spark_h = 18
            spark_x = -spark_w / 2
            spark_y = 52
            sparkline_svg = _build_sparkline(
                commit_weeks, spark_x, spark_y, spark_w, spark_h, icon_color
            )

        cells.append(f'''    <g class="metric-cell" transform="translate({cx}, 105)">
      <g transform="translate(-8, -30) scale(1)">
        <svg viewBox="0 0 16 16" width="16" height="16" fill="{icon_color}" class="metric-icon" style="animation-delay: {delay}">
          {icon_path}
        </svg>
      </g>
      <text x="0" y="2" text-anchor="middle" fill="{icon_color}" font-size="28" font-weight="bold" font-family="sans-serif" opacity="0.35" filter="url(#num-glow)">{value}</text>
      <text x="0" y="2" text-anchor="middle" fill="{theme['text_bright']}" font-size="28" font-weight="bold" font-family="sans-serif">{value}</text>
      <text x="0" y="20" text-anchor="middle" fill="{theme['text_faint']}" font-size="11" font-family="monospace" letter-spacing="1">{label}</text>
{delta_svg}
{sparkline_svg}
    </g>''')

        # Vertical divider between cells (not after last)
        if i < len(metrics) - 1:
            dx = cell_width * (i + 1)
            dividers.append(
                f'    <line x1="{dx}" y1="55" x2="{dx}" y2="195" '
                f'stroke="{theme["star_dust"]}" stroke-width="1" opacity="0.5"/>'
            )

    cells_str = "\n".join(cells)
    dividers_str = "\n".join(dividers)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <style>
      .metric-icon {{
        animation: count-glow 4s ease-in-out infinite;
      }}
      @keyframes count-glow {{
        0%, 100% {{ fill-opacity: 0.7; }}
        50% {{ fill-opacity: 1; }}
      }}
    </style>
    <filter id="num-glow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="3"/>
    </filter>
  </defs>

  <!-- Card background -->
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" ry="12"
        fill="{theme['nebula']}" stroke="{theme['star_dust']}" stroke-width="1"/>

  <!-- Section title -->
  <text x="30" y="38" fill="{theme['text_faint']}" font-size="11" font-family="monospace" letter-spacing="3">MISSION TELEMETRY</text>

  <!-- Dividers -->
{dividers_str}

  <!-- Metric cells -->
{cells_str}
</svg>'''
