"""SVG template: Language Telemetry + Focus Sectors radar (dynamic height)."""

import math

from generator.utils import calculate_language_percentages, esc, svg_arc_path, resolve_arm_colors

WIDTH = 850


def _build_language_orbit(lang_data, lang_meta, theme, cx, cy):
    """Build the language orbit view (left side of the card).

    Each language is rendered as a planet on its own orbit ring around a
    pulsing core. Orbit radius grows with index (top languages closest in),
    planet radius scales with sqrt(percentage), and rotation speed is
    inversely proportional to the number of repos using that language.

    Args:
        lang_data: list of dicts with name, percentage, color (from
            calculate_language_percentages)
        lang_meta: dict of {lang_name: {repos, last_activity}} — optional,
            used to vary orbit speed; may be None or empty
        theme: color palette dict
        cx, cy: orbit center

    Returns:
        str of SVG elements for the language orbit
    """
    lang_meta = lang_meta or {}
    core_color = theme.get("synapse_cyan", "#00d4ff")

    parts = []

    # Pulsing core
    parts.append(
        f'    <circle cx="{cx}" cy="{cy}" r="8" fill="{core_color}" opacity="0.25">'
        f'\n      <animate attributeName="r" values="6;9;6" dur="3s" repeatCount="indefinite"/>'
        f'\n      <animate attributeName="opacity" values="0.2;0.45;0.2" dur="3s" repeatCount="indefinite"/>'
        f'\n    </circle>'
        f'\n    <circle cx="{cx}" cy="{cy}" r="3" fill="{core_color}"/>'
    )

    if not lang_data:
        parts.append(
            f'    <text x="{cx}" y="{cy + 120}" text-anchor="middle" fill="{theme["text_faint"]}" '
            f'font-size="10" font-family="monospace" opacity="0.6">no language data</text>'
        )
        return "\n".join(parts)

    # Orbit rings and planets
    base_radius = 34
    ring_step = 18
    # Rings are drawn behind the planets
    ring_parts = []
    planet_parts = []
    legend_parts = []

    # Legend column on the far left (inside the left pane)
    legend_x = 25
    legend_start_y = 70
    legend_line_h = 16

    for i, lang in enumerate(lang_data):
        orbit_r = base_radius + i * ring_step
        # Planet size from percentage (clamp 4..12)
        pct = max(lang["percentage"], 0.5)
        planet_r = min(12, max(4, 3 + (pct ** 0.5) * 1.2))
        planet_color = lang["color"]
        name = lang["name"]

        # Orbit speed from repos count (more repos = faster)
        meta = lang_meta.get(name) or {}
        repo_count = meta.get("repos", 0) or 0
        # clamp speed: 12s (very active) to 45s (static)
        orbit_dur = max(12, 45 - repo_count * 2)

        # Starting angle spread around the circle
        start_deg = (i * 47) % 360  # deterministic but varied
        # Initial position before rotation (for the static planet placement
        # that then gets rotated by animateTransform)
        import math as _m
        sx = cx + orbit_r * _m.cos(_m.radians(start_deg))
        sy = cy + orbit_r * _m.sin(_m.radians(start_deg))

        # Orbit ring (behind)
        ring_parts.append(
            f'    <circle cx="{cx}" cy="{cy}" r="{orbit_r}" '
            f'fill="none" stroke="{planet_color}" stroke-width="0.6" '
            f'stroke-dasharray="2,3" opacity="0.25"/>'
        )

        # Planet group — the whole group rotates around (cx, cy)
        planet_parts.append(
            f'''    <g>
      <animateTransform attributeName="transform" type="rotate"
        from="0 {cx} {cy}" to="360 {cx} {cy}"
        dur="{orbit_dur}s" repeatCount="indefinite"/>
      <circle cx="{sx:.1f}" cy="{sy:.1f}" r="{planet_r:.1f}" fill="{planet_color}" opacity="0.9">
        <animate attributeName="opacity" values="0.75;1;0.75" dur="3s" repeatCount="indefinite"/>
      </circle>
      <circle cx="{sx:.1f}" cy="{sy:.1f}" r="{planet_r + 2:.1f}" fill="{planet_color}" opacity="0.18"/>
    </g>'''
        )

        # Legend row (static, doesn't rotate)
        ly = legend_start_y + i * legend_line_h
        legend_parts.append(
            f'    <circle cx="{legend_x + 4}" cy="{ly - 4}" r="4" fill="{planet_color}" opacity="0.9"/>'
        )
        legend_parts.append(
            f'    <text x="{legend_x + 14}" y="{ly}" fill="{theme["text_dim"]}" '
            f'font-size="10" font-family="monospace">{esc(name)}</text>'
        )
        legend_parts.append(
            f'    <text x="{legend_x + 110}" y="{ly}" fill="{theme["text_faint"]}" '
            f'font-size="10" font-family="monospace">{lang["percentage"]}%</text>'
        )

    parts.extend(ring_parts)
    parts.extend(planet_parts)
    parts.extend(legend_parts)

    return "\n".join(parts)


def _build_radar_grid(rcx, rcy, grid_rings, theme):
    """Build the concentric dashed circles of the radar grid.

    Args:
        rcx: radar center x
        rcy: radar center y
        grid_rings: list of ring radii
        theme: color palette dict

    Returns:
        str of SVG elements for the radar grid
    """
    parts = []
    for ring_r in grid_rings:
        parts.append(
            f'    <circle cx="{rcx}" cy="{rcy}" r="{ring_r}" '
            f'fill="none" stroke="{theme["text_faint"]}" '
            f'stroke-width="0.5" stroke-dasharray="3,3" opacity="0.25"/>'
        )
    return "\n".join(parts)


def _build_radar_sectors(sector_data, rcx, rcy, radius, theme):
    """Build arc sectors and boundary lines for the radar.

    Args:
        sector_data: list of sector dicts with start_deg, end_deg, color
        rcx: radar center x
        rcy: radar center y
        radius: radar radius
        theme: color palette dict

    Returns:
        str of SVG elements for the radar sectors
    """
    parts = []

    # Arc sectors (filled pie slices)
    for sec in sector_data:
        d = svg_arc_path(rcx, rcy, radius, sec["start_deg"], sec["end_deg"])
        parts.append(
            f'    <path d="{d}" fill="{sec["color"]}" fill-opacity="0.10" '
            f'stroke="{sec["color"]}" stroke-opacity="0.3" stroke-width="0.5"/>'
        )

    # Sector boundary lines (radial lines at sector edges)
    for i in range(len(sector_data)):
        angle_deg = i * 120
        angle_rad = math.radians(angle_deg - 90)
        lx = rcx + radius * math.cos(angle_rad)
        ly = rcy + radius * math.sin(angle_rad)
        parts.append(
            f'    <line x1="{rcx}" y1="{rcy}" x2="{lx:.1f}" y2="{ly:.1f}" '
            f'stroke="{theme["text_faint"]}" stroke-width="0.5" opacity="0.3"/>'
        )

    return "\n".join(parts)


def _build_radar_needle(rcx, rcy, radius, theme):
    """Build the rotating radar needle group (sweep trail, wedges, tip glow).

    Args:
        rcx: radar center x
        rcy: radar center y
        radius: radar radius
        theme: color palette dict

    Returns:
        SVG element string for the needle group
    """
    scan_color = theme.get("synapse_cyan", "#00d4ff")
    tip_x = rcx
    tip_y = rcy - radius
    # Sweep trail: 30-degree pie-slice arc behind the needle
    sweep_d = svg_arc_path(rcx, rcy, radius, 330, 360)
    # Outer wedge: triangle tapering from 2.5px half-width at center to tip
    outer_hw = 2.5
    # Inner bright core: narrower triangle (0.8px half-width)
    inner_hw = 0.8

    needle = (
        f'    <g>'
        f'\n      <!-- Sweep trail -->'
        f'\n      <path d="{sweep_d}" fill="{scan_color}" fill-opacity="0.07"/>'
        f'\n      <!-- Outer wedge -->'
        f'\n      <polygon points="{rcx - outer_hw},{rcy} {tip_x},{tip_y} {rcx + outer_hw},{rcy}" '
        f'fill="{scan_color}" opacity="0.25"/>'
        f'\n      <!-- Inner bright core -->'
        f'\n      <polygon points="{rcx - inner_hw},{rcy} {tip_x},{tip_y} {rcx + inner_hw},{rcy}" '
        f'fill="{scan_color}" opacity="0.5"/>'
        f'\n      <!-- Tip glow -->'
        f'\n      <circle cx="{tip_x}" cy="{tip_y}" r="2" fill="{scan_color}" opacity="0.6">'
        f'\n        <animate attributeName="opacity" values="0.4;0.8;0.4" dur="2s" repeatCount="indefinite"/>'
        f'\n      </circle>'
        f'\n      <animateTransform attributeName="transform" type="rotate" '
        f'from="0 {rcx} {rcy}" to="360 {rcx} {rcy}" '
        f'dur="8s" repeatCount="indefinite"/>'
        f'\n    </g>'
    )

    return needle


def _build_radar_labels_and_dots(sector_data, galaxy_arms, rcx, rcy, radius, theme):
    """Build labels at outer edge and dots per item for each sector.

    Args:
        sector_data: list of sector dicts with name, color, start_deg, end_deg, items
        galaxy_arms: list of arm configs with items
        rcx: radar center x
        rcy: radar center y
        radius: radar radius
        theme: color palette dict

    Returns:
        str of SVG elements for the radar labels and dots
    """
    parts = []

    # Labels at outer edge of each sector midpoint
    for sec in sector_data:
        mid_deg = (sec["start_deg"] + sec["end_deg"]) / 2
        mid_rad = math.radians(mid_deg - 90)
        label_r = radius + 18
        lx = rcx + label_r * math.cos(mid_rad)
        ly = rcy + label_r * math.sin(mid_rad)

        # Determine text-anchor based on position
        if abs(lx - rcx) < 5:
            anchor = "middle"
        elif lx > rcx:
            anchor = "start"
        else:
            anchor = "end"

        parts.append(
            f'    <text x="{lx:.1f}" y="{ly:.1f}" fill="{sec["color"]}" '
            f'font-size="9" font-family="monospace" text-anchor="{anchor}" '
            f'dominant-baseline="middle">{esc(sec["name"])}</text>'
        )
        # Item count below name
        count_y = ly + 12
        parts.append(
            f'    <text x="{lx:.1f}" y="{count_y:.1f}" fill="{theme["text_faint"]}" '
            f'font-size="8" font-family="monospace" text-anchor="{anchor}" '
            f'dominant-baseline="middle">({sec["items"]})</text>'
        )

    # Dots: one per item per sector, unconditional
    radii_cycle = [24, 40, 56]
    for sec_i, sec in enumerate(sector_data):
        arm = galaxy_arms[sec_i]
        items = arm.get("items", [])
        item_count = len(items)
        edge_pad = 10  # degrees of padding from sector edges
        for j, item in enumerate(items):
            # Angular: evenly spread within sector with edge padding
            usable_start = sec["start_deg"] + edge_pad
            usable_end = sec["end_deg"] - edge_pad
            if item_count == 1:
                item_angle = (usable_start + usable_end) / 2
            else:
                item_angle = usable_start + (usable_end - usable_start) * j / (item_count - 1)
            item_rad = math.radians(item_angle - 90)
            # Radial: cycle through grid ring radii
            dot_r = radii_cycle[j % 3]
            dx = rcx + dot_r * math.cos(item_rad)
            dy = rcy + dot_r * math.sin(item_rad)
            # Timing: pulse fires when needle sweeps past this angle
            pulse_begin = (item_angle / 360) * 8 - 0.3
            if pulse_begin < 0:
                pulse_begin += 8
            parts.append(
                f'    <circle cx="{dx:.1f}" cy="{dy:.1f}" r="3" '
                f'fill="{sec["color"]}" opacity="0.35">'
                f'\n      <animate attributeName="opacity" '
                f'values="0.35;0.35;1.0;0.35;0.35" '
                f'keyTimes="0;0.04;0.06;0.10;1" '
                f'dur="8s" begin="{pulse_begin:.2f}s" repeatCount="indefinite"/>'
                f'\n    </circle>'
            )

    return "\n".join(parts)


def render(
    languages: dict,
    galaxy_arms: list,
    theme: dict,
    exclude: list,
    max_display: int,
    lang_meta: dict = None,
) -> str:
    """Render the tech stack SVG.

    Args:
        languages: dict of language name -> byte count
        galaxy_arms: list of arm configs with name, color, items
        theme: color palette dict
        exclude: languages to exclude
        max_display: max languages to show
        lang_meta: optional {lang_name: {repos, last_activity}} to vary
            orbit rotation speed by activity
    """
    lang_data = calculate_language_percentages(languages, exclude, max_display)

    # Left side: Language Orbit (center is roughly at x=240 within left pane)
    orbit_cx = 260
    orbit_cy = 135
    orbit_str = _build_language_orbit(lang_data, lang_meta, theme, orbit_cx, orbit_cy)

    # Right side: Focus Sectors radar
    all_arm_colors = resolve_arm_colors(galaxy_arms, theme)

    # Build sector data
    sector_data = []
    for i, arm in enumerate(galaxy_arms):
        color = all_arm_colors[i]
        items = arm.get("items", [])
        sector_data.append({
            "name": arm["name"],
            "color": color,
            "items": len(items),
            "start_deg": i * 120 + 1,
            "end_deg": (i + 1) * 120 - 1,
        })

    # Radar geometry
    radius = 65
    rcx = 637  # center of right half (425..850)
    badge_start_y = 65
    rcy = badge_start_y + radius + 10  # center y
    grid_rings = [22, 44, 65]

    # Dynamic height — the orbit view needs room for the outermost ring
    max_orbit_r = 34 + max(len(lang_data) - 1, 0) * 18 + 14
    orbit_height = orbit_cy + max_orbit_r + 20
    radar_height = rcy + radius + 35
    height = max(240, orbit_height, radar_height)

    # Build radar SVG elements
    radar_parts = []
    radar_parts.append(_build_radar_grid(rcx, rcy, grid_rings, theme))
    radar_parts.append(_build_radar_sectors(sector_data, rcx, rcy, radius, theme))
    radar_parts.append(_build_radar_needle(rcx, rcy, radius, theme))
    radar_parts.append(_build_radar_labels_and_dots(sector_data, galaxy_arms, rcx, rcy, radius, theme))

    radar_str = "\n".join(radar_parts)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}">
  <defs/>

  <!-- Card background -->
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="12" ry="12"
        fill="{theme['nebula']}" stroke="{theme['star_dust']}" stroke-width="1"/>

  <!-- Left: Language Telemetry -->
  <text x="30" y="38" fill="{theme['text_faint']}" font-size="11" font-family="monospace" letter-spacing="3">LANGUAGE TELEMETRY</text>

  <!-- Vertical divider -->
  <line x1="425" y1="25" x2="425" y2="{height - 25}" stroke="{theme['star_dust']}" stroke-width="1" opacity="0.4"/>

  <!-- Right: Focus Sectors -->
  <text x="460" y="38" fill="{theme['text_faint']}" font-size="11" font-family="monospace" letter-spacing="3">FOCUS SECTORS</text>

{orbit_str}

{radar_str}
</svg>'''
