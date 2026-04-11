"""SVG Builder — orchestrator connecting config, stats, and templates."""

from generator.templates import (
    flight_log,
    galaxy_header,
    projects_constellation,
    stats_card,
    tech_stack,
)


class SVGBuilder:
    """Builds all SVG assets from config and GitHub data.

    Expects a config dict that has already been through validate_config(),
    which resolves theme defaults and applies missing optional fields.
    """

    def __init__(
        self,
        config: dict,
        stats: dict,
        languages: dict,
        previous_stats: dict = None,
        commit_weeks: list = None,
        lang_meta: dict = None,
        flight_log: list = None,
    ):
        self.config = config
        self.stats = stats
        self.languages = languages
        self.previous_stats = previous_stats or {}
        self.commit_weeks = commit_weeks or []
        self.lang_meta = lang_meta or {}
        self.flight_log = flight_log or []
        self.theme = config["theme"]
        self.galaxy_arms = config.get("galaxy_arms", [])
        self.projects = config.get("projects", [])

    def render_galaxy_header(self) -> str:
        return galaxy_header.render(
            config=self.config,
            theme=self.theme,
            galaxy_arms=self.galaxy_arms,
            projects=self.projects,
        )

    def render_stats_card(self) -> str:
        metrics = self.config["stats"]["metrics"]
        return stats_card.render(
            stats=self.stats,
            metrics=metrics,
            theme=self.theme,
            previous_stats=self.previous_stats,
            commit_weeks=self.commit_weeks,
        )

    def render_tech_stack(self) -> str:
        lang_config = self.config.get("languages", {})
        return tech_stack.render(
            languages=self.languages,
            galaxy_arms=self.galaxy_arms,
            theme=self.theme,
            exclude=lang_config.get("exclude", []),
            max_display=lang_config.get("max_display", 8),
            lang_meta=self.lang_meta,
        )

    def render_flight_log(self) -> str:
        return flight_log.render(
            entries=self.flight_log,
            theme=self.theme,
            username=self.config.get("username", ""),
        )

    def render_projects_constellation(self) -> str:
        return projects_constellation.render(
            projects=self.projects,
            galaxy_arms=self.galaxy_arms,
            theme=self.theme,
        )
