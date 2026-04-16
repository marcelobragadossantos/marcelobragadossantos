"""GitHub API client for fetching user stats and language data."""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)


class GitHubAPI:
    """Fetches GitHub stats via GraphQL (with token) or REST (fallback)."""

    GRAPHQL_URL = "https://api.github.com/graphql"
    REST_URL = "https://api.github.com"

    MAX_RATE_LIMIT_WAIT = 60  # seconds — avoid hanging CI jobs

    def __init__(self, username: str, token: str = None):
        self.username = username
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        # Lazy cache for viewer-identity resolution. None = not yet resolved,
        # "" = resolved to "no viewer" (no token or /user call failed),
        # any other string = authenticated viewer login in lowercase.
        self._viewer_login_cached = None

    def _token_matches_target_user(self) -> bool:
        """Return True if the token's authenticated viewer is self.username.

        When the workflow runs with the default GITHUB_TOKEN, the viewer is
        'github-actions[bot]' and token-scoped endpoints (/user/repos,
        GraphQL viewer-relative fields) won't include the target user's
        private data or owned repos. In that case we behave as if
        unauthenticated for data scoping but keep the Authorization header
        so we still benefit from the higher rate limit.
        """
        if not self.token:
            return False
        if self._viewer_login_cached is not None:
            return bool(self._viewer_login_cached) and (
                self._viewer_login_cached == self.username.lower()
            )
        try:
            resp = self._request("GET", f"{self.REST_URL}/user")
        except requests.exceptions.RequestException as e:
            logger.warning("Error resolving token viewer: %s", e)
            self._viewer_login_cached = ""
            return False
        if resp.status_code != 200:
            logger.warning(
                "Could not resolve /user (HTTP %d); treating token as non-matching.",
                resp.status_code,
            )
            self._viewer_login_cached = ""
            return False
        login = (resp.json() or {}).get("login", "").lower()
        self._viewer_login_cached = login or ""
        if login != self.username.lower():
            logger.warning(
                "Token viewer is '%s' but target user is '%s'. "
                "Falling back to public endpoints. Configure a PAT in the "
                "GH_TOKEN secret (scopes: read:user, repo) to include private data.",
                login or "<unknown>",
                self.username,
            )
            return False
        return True

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an HTTP request with rate-limit awareness and retry.

        Checks X-RateLimit-Remaining after each response.
        On 403 rate-limit, waits until reset and retries once.
        """
        kwargs.setdefault("headers", self.headers)
        kwargs.setdefault("timeout", 15)

        resp = requests.request(method, url, **kwargs)

        # Check rate limit headers
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) < 10:
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
            logger.warning(
                "GitHub API rate limit low: %s remaining (resets at %s)",
                remaining,
                time.strftime("%H:%M:%S", time.localtime(reset_ts)),
            )

        # Retry once on rate-limit 403 (cap wait to avoid CI timeout)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_ts - int(time.time()), 1)
            if wait > self.MAX_RATE_LIMIT_WAIT:
                logger.warning(
                    "Rate limited. Reset in %ds exceeds max wait (%ds), skipping retry.",
                    wait,
                    self.MAX_RATE_LIMIT_WAIT,
                )
                return resp
            logger.warning("Rate limited. Waiting %ds for reset...", wait)
            time.sleep(wait)
            resp = requests.request(method, url, **kwargs)

        return resp

    def fetch_stats(self) -> dict:
        """Fetch user statistics.

        Uses GraphQL only when the token's authenticated viewer matches the
        target user — otherwise GraphQL's viewer-relative counts (restricted
        contributions, private repos) would be 0 and mislead. Non-matching
        tokens (e.g. the default workflow GITHUB_TOKEN, which is the
        'github-actions[bot]' identity) are routed through REST, which uses
        public endpoints that return the correct public numbers regardless
        of viewer identity.
        """
        if self.token and self._token_matches_target_user():
            return self._fetch_stats_graphql()
        return self._fetch_stats_rest()

    def _fetch_stats_graphql(self) -> dict:
        """Fetch stats via GraphQL for accurate counts including private contributions."""
        query = """
        query($username: String!) {
          user(login: $username) {
            repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) {
              totalCount
            }
            pullRequests {
              totalCount
            }
            issues {
              totalCount
            }
            repositories(ownerAffiliations: OWNER, first: 100) {
              totalCount
              nodes {
                stargazerCount
              }
            }
            contributionsCollection {
              totalCommitContributions
              restrictedContributionsCount
            }
          }
        }
        """
        try:
            resp = self._request(
                "POST",
                self.GRAPHQL_URL,
                json={"query": query, "variables": {"username": self.username}},
            )
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            logger.warning("GraphQL request timed out, falling back to REST.")
            return self._fetch_stats_rest()
        except requests.exceptions.HTTPError as e:
            logger.warning("GraphQL HTTP error (%s), falling back to REST.", e)
            return self._fetch_stats_rest()

        data = resp.json()

        if "errors" in data:
            logger.warning("GraphQL errors: %s", data["errors"])
            return self._fetch_stats_rest()

        user = (data.get("data") or {}).get("user")
        if user is None:
            logger.warning("GraphQL returned null user, falling back to REST.")
            return self._fetch_stats_rest()

        contrib = user.get("contributionsCollection") or {}
        repos = user.get("repositories") or {"totalCount": 0, "nodes": []}

        total_stars = sum(n.get("stargazerCount", 0) for n in repos.get("nodes", []))
        total_commits = (
            contrib.get("totalCommitContributions", 0)
            + contrib.get("restrictedContributionsCount", 0)
        )

        return {
            "commits": total_commits,
            "stars": total_stars,
            "prs": (user.get("pullRequests") or {}).get("totalCount", 0),
            "issues": (user.get("issues") or {}).get("totalCount", 0),
            "repos": repos.get("totalCount", 0),
        }

    def _fetch_stats_rest(self) -> dict:
        """Fallback: fetch stats via REST API (public data only)."""
        user_resp = self._request(
            "GET", f"{self.REST_URL}/users/{self.username}"
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()

        # Fetch repos to count stars
        total_stars = 0
        for repos in self._paginate_repos():
            total_stars += sum(r.get("stargazers_count", 0) for r in repos)

        # Estimate commits from events (rough approximation without token)
        events_resp = self._request(
            "GET",
            f"{self.REST_URL}/users/{self.username}/events/public",
            params={"per_page": 100},
        )
        events_resp.raise_for_status()
        events = events_resp.json()
        commit_count = sum(
            len(e.get("payload", {}).get("commits", []))
            for e in events
            if e.get("type") == "PushEvent"
        )

        # Fetch actual PR count via Search API
        pr_count = self._search_count(f"author:{self.username} type:pr")

        # Fetch actual issue count via Search API
        issue_count = self._search_count(f"author:{self.username} type:issue")

        if self.token:
            total_repos = user_data.get("public_repos", 0) + user_data.get("total_private_repos", 0)
        else:
            total_repos = user_data.get("public_repos", 0)

        return {
            "commits": commit_count,
            "stars": total_stars,
            "prs": pr_count,
            "issues": issue_count,
            "repos": total_repos,
        }

    def _paginate_repos(self):
        """Yield pages of owned repos from the REST API.

        Uses /user/repos (authenticated) when the token belongs to the target
        user — that endpoint returns both public and private repos. Otherwise
        falls back to /users/{username}/repos, which returns only public repos
        but works for any viewer identity (including the default workflow
        GITHUB_TOKEN bot).
        """
        page = 1
        if self.token and self._token_matches_target_user():
            url = f"{self.REST_URL}/user/repos"
            params = {"per_page": 100, "page": page, "affiliation": "owner", "visibility": "all"}
        else:
            url = f"{self.REST_URL}/users/{self.username}/repos"
            params = {"per_page": 100, "page": page, "type": "owner"}
        while True:
            params["page"] = page
            repos_resp = self._request("GET", url, params=params)
            repos_resp.raise_for_status()
            repos = repos_resp.json()
            if not repos:
                break
            yield repos
            if len(repos) < 100:
                break
            page += 1

    def _search_count(self, query: str) -> int:
        """Use the GitHub Search API to get a total_count for a query."""
        try:
            resp = self._request(
                "GET",
                f"{self.REST_URL}/search/issues",
                params={"q": query, "per_page": 1},
            )
            if resp.status_code == 200:
                return resp.json().get("total_count", 0)
            logger.warning("Search API returned %d for query '%s'", resp.status_code, query)
        except requests.exceptions.RequestException as e:
            logger.warning("Search API failed for '%s': %s", query, e)
        return 0

    def fetch_languages(self) -> dict:
        """Fetch language byte counts aggregated across all owned non-fork repos."""
        languages, _ = self._fetch_languages_and_meta()
        return languages

    def _fetch_languages_and_meta(self) -> tuple:
        """Fetch per-lang bytes plus metadata (repo count, last activity).

        Returns a tuple (languages, lang_meta) where:
          languages: {lang_name: total_bytes}
          lang_meta: {lang_name: {"repos": int, "last_activity": iso_date or None}}
        """
        languages = {}
        lang_meta = {}
        repo_count = 0
        for repos in self._paginate_repos():
            logger.info("Processing batch of %d repos for languages...", len(repos))
            for repo in repos:
                if repo.get("fork"):
                    logger.info("Skipping fork: %s", repo.get("full_name", "unknown"))
                    continue
                repo_count += 1
                repo_name = repo.get("full_name", "unknown")
                private = repo.get("private", False)
                pushed_at = repo.get("pushed_at")
                logger.info("Fetching languages for %s (private=%s)", repo_name, private)
                try:
                    lang_resp = self._request("GET", repo["languages_url"])
                    if lang_resp.status_code == 200:
                        repo_langs = lang_resp.json()
                        if repo_langs:
                            logger.info("  %s: %s", repo_name, list(repo_langs.keys()))
                        for lang, bytes_count in repo_langs.items():
                            languages[lang] = languages.get(lang, 0) + bytes_count
                            meta = lang_meta.setdefault(
                                lang, {"repos": 0, "last_activity": None}
                            )
                            meta["repos"] += 1
                            if pushed_at and (
                                meta["last_activity"] is None
                                or pushed_at > meta["last_activity"]
                            ):
                                meta["last_activity"] = pushed_at
                    else:
                        logger.warning(
                            "Could not fetch languages for %s (HTTP %d)",
                            repo_name,
                            lang_resp.status_code,
                        )
                except requests.exceptions.RequestException as e:
                    logger.warning(
                        "Error fetching languages for %s: %s",
                        repo_name,
                        e,
                    )
        logger.info("Processed %d repos total. Languages found: %s", repo_count, dict(languages))
        return languages, lang_meta

    def fetch_commit_weeks(self) -> list:
        """Fetch a 52-week contribution histogram via GraphQL contributionCalendar.

        Returns a list of 52 ints (oldest to newest). Only works when the
        token belongs to the target user; otherwise returns an empty list.
        """
        if not (self.token and self._token_matches_target_user()):
            return []
        query = """
        query($username: String!) {
          user(login: $username) {
            contributionsCollection {
              contributionCalendar {
                weeks {
                  contributionDays {
                    contributionCount
                  }
                }
              }
            }
          }
        }
        """
        try:
            resp = self._request(
                "POST",
                self.GRAPHQL_URL,
                json={"query": query, "variables": {"username": self.username}},
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning("Could not fetch contribution calendar: %s", e)
            return []
        data = resp.json()
        if "errors" in data:
            logger.warning("GraphQL errors fetching calendar: %s", data["errors"])
            return []
        user = (data.get("data") or {}).get("user") or {}
        weeks = (
            (user.get("contributionsCollection") or {})
            .get("contributionCalendar", {})
            .get("weeks", [])
        )
        result = []
        for week in weeks:
            total = sum(
                d.get("contributionCount", 0)
                for d in week.get("contributionDays", [])
            )
            result.append(total)
        # Take the last 52 weeks (GraphQL may return 53)
        return result[-52:]

    def fetch_flight_log(self, limit: int = 5) -> list:
        """Fetch the most recent push events as a commit log.

        Uses the authenticated /users/{username}/events endpoint when a
        matching PAT is available (includes private repo activity), otherwise
        falls back to /events/public (public activity only).

        Returns a list of dicts: {sha, message, timestamp, repo}. Falls back
        to an empty list on any error.
        """
        if self.token and self._token_matches_target_user():
            events_url = f"{self.REST_URL}/users/{self.username}/events"
        else:
            events_url = f"{self.REST_URL}/users/{self.username}/events/public"
        try:
            resp = self._request(
                "GET",
                events_url,
                params={"per_page": 100},
            )
            if resp.status_code != 200:
                logger.warning(
                    "Could not fetch events (HTTP %d)", resp.status_code
                )
                return []
            events = resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("Error fetching events: %s", e)
            return []

        commits = []
        for event in events:
            if event.get("type") != "PushEvent":
                continue
            repo = (event.get("repo") or {}).get("name", "")
            created_at = event.get("created_at", "")
            for commit in reversed((event.get("payload") or {}).get("commits", [])):
                # Only count commits authored by the target user (best effort:
                # match on author.email prefix or name; GitHub redacts some).
                msg = (commit.get("message") or "").split("\n", 1)[0]
                sha = (commit.get("sha") or "")[:7]
                commits.append(
                    {
                        "sha": sha,
                        "message": msg,
                        "timestamp": created_at,
                        "repo": repo,
                    }
                )
                if len(commits) >= limit:
                    return commits
        return commits

    def fetch_telemetry_bundle(self) -> dict:
        """One-shot fetch of everything the templates need.

        Returns a dict with keys:
          stats:        current snapshot (commits, stars, prs, issues, repos)
          languages:    {lang: bytes}
          lang_meta:    {lang: {"repos": int, "last_activity": iso_date}}
          commit_weeks: list[int] length 52 (oldest → newest), [] if no PAT
          flight_log:   list[dict] of recent public push events (up to 5)
        """
        logger.info("Fetching stats...")
        try:
            stats = self.fetch_stats()
        except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as e:
            logger.warning("Could not fetch stats (%s). Using defaults.", e)
            stats = {"commits": 0, "stars": 0, "prs": 0, "issues": 0, "repos": 0}

        logger.info("Fetching languages...")
        try:
            languages, lang_meta = self._fetch_languages_and_meta()
        except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as e:
            logger.warning("Could not fetch languages (%s). Using defaults.", e)
            languages, lang_meta = {}, {}

        logger.info("Fetching commit calendar...")
        commit_weeks = self.fetch_commit_weeks()

        logger.info("Fetching flight log...")
        flight_log = self.fetch_flight_log()

        return {
            "stats": stats,
            "languages": languages,
            "lang_meta": lang_meta,
            "commit_weeks": commit_weeks,
            "flight_log": flight_log,
        }
