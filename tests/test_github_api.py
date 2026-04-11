"""Tests for the GitHub API client, especially the viewer-identity gating."""

from unittest.mock import patch, MagicMock

from generator.github_api import GitHubAPI


def _mock_response(status_code=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {"X-RateLimit-Remaining": "5000", "X-RateLimit-Reset": "0"}
    resp.raise_for_status = MagicMock()
    resp.text = ""
    return resp


class TestTokenMatchesTargetUser:
    def test_no_token_returns_false(self):
        api = GitHubAPI("marcelobragadossantos", token="")
        assert api._token_matches_target_user() is False

    def test_matching_viewer_returns_true(self):
        api = GitHubAPI("marcelobragadossantos", token="tok")
        with patch("generator.github_api.requests.request") as mock_req:
            mock_req.return_value = _mock_response(
                json_data={"login": "marcelobragadossantos"}
            )
            assert api._token_matches_target_user() is True

    def test_matching_viewer_is_case_insensitive(self):
        api = GitHubAPI("MarceloBragaDosSantos", token="tok")
        with patch("generator.github_api.requests.request") as mock_req:
            mock_req.return_value = _mock_response(
                json_data={"login": "marcelobragadossantos"}
            )
            assert api._token_matches_target_user() is True

    def test_bot_viewer_returns_false(self):
        api = GitHubAPI("marcelobragadossantos", token="tok")
        with patch("generator.github_api.requests.request") as mock_req:
            mock_req.return_value = _mock_response(
                json_data={"login": "github-actions[bot]"}
            )
            assert api._token_matches_target_user() is False

    def test_user_endpoint_error_returns_false(self):
        api = GitHubAPI("marcelobragadossantos", token="tok")
        with patch("generator.github_api.requests.request") as mock_req:
            mock_req.return_value = _mock_response(status_code=401)
            assert api._token_matches_target_user() is False

    def test_result_is_cached(self):
        api = GitHubAPI("marcelobragadossantos", token="tok")
        with patch("generator.github_api.requests.request") as mock_req:
            mock_req.return_value = _mock_response(
                json_data={"login": "marcelobragadossantos"}
            )
            api._token_matches_target_user()
            api._token_matches_target_user()
            api._token_matches_target_user()
            # /user should only be called once; subsequent calls hit the cache
            assert mock_req.call_count == 1


class TestPaginateReposRouting:
    def test_bot_token_falls_back_to_public_endpoint(self):
        """When the token viewer is a bot, _paginate_repos must use
        /users/{username}/repos instead of /user/repos."""
        api = GitHubAPI("marcelobragadossantos", token="tok")
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append(url)
            if url.endswith("/user"):
                return _mock_response(json_data={"login": "github-actions[bot]"})
            # Public repos endpoint returns one page then empty
            if "/users/marcelobragadossantos/repos" in url:
                if kwargs.get("params", {}).get("page", 1) == 1:
                    return _mock_response(
                        json_data=[{"id": 1, "full_name": "marcelobragadossantos/x",
                                    "fork": False, "languages_url": "u", "private": False,
                                    "stargazers_count": 3, "pushed_at": "2026-04-01T00:00:00Z"}]
                    )
                return _mock_response(json_data=[])
            return _mock_response(json_data=[])

        with patch("generator.github_api.requests.request", side_effect=fake_request):
            pages = list(api._paginate_repos())

        # Assert the public endpoint was used, not /user/repos
        assert any("/users/marcelobragadossantos/repos" in u for u in calls)
        assert not any(u.endswith("/user/repos") for u in calls)
        assert pages == [[{"id": 1, "full_name": "marcelobragadossantos/x",
                           "fork": False, "languages_url": "u", "private": False,
                           "stargazers_count": 3, "pushed_at": "2026-04-01T00:00:00Z"}]]

    def test_matching_token_uses_authenticated_endpoint(self):
        api = GitHubAPI("marcelobragadossantos", token="tok")
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append(url)
            if url.endswith("/user"):
                return _mock_response(json_data={"login": "marcelobragadossantos"})
            if url.endswith("/user/repos"):
                if kwargs.get("params", {}).get("page", 1) == 1:
                    return _mock_response(
                        json_data=[{"id": 1, "full_name": "marcelobragadossantos/p",
                                    "fork": False, "languages_url": "u", "private": True,
                                    "stargazers_count": 0, "pushed_at": "2026-04-01T00:00:00Z"}]
                    )
                return _mock_response(json_data=[])
            return _mock_response(json_data=[])

        with patch("generator.github_api.requests.request", side_effect=fake_request):
            list(api._paginate_repos())

        assert any(u.endswith("/user/repos") for u in calls)


class TestFetchStatsRouting:
    def test_bot_token_routes_to_rest(self):
        """fetch_stats must use REST (public endpoints) when the viewer
        doesn't match the target user."""
        api = GitHubAPI("marcelobragadossantos", token="tok")

        def fake_request(method, url, **kwargs):
            if url.endswith("/user"):
                return _mock_response(json_data={"login": "github-actions[bot]"})
            if url.endswith("/users/marcelobragadossantos"):
                return _mock_response(json_data={"public_repos": 4, "total_private_repos": 0})
            if "/users/marcelobragadossantos/repos" in url:
                return _mock_response(json_data=[])
            if "/users/marcelobragadossantos/events/public" in url:
                return _mock_response(json_data=[])
            if "/search/issues" in url:
                return _mock_response(json_data={"total_count": 7})
            # GraphQL must NOT be called
            if "graphql" in url:
                raise AssertionError(
                    "fetch_stats should not call GraphQL with a non-matching viewer"
                )
            return _mock_response(json_data={})

        with patch("generator.github_api.requests.request", side_effect=fake_request):
            stats = api.fetch_stats()

        assert stats["repos"] == 4
        assert stats["prs"] == 7

    def test_matching_token_routes_to_graphql(self):
        api = GitHubAPI("marcelobragadossantos", token="tok")

        def fake_request(method, url, **kwargs):
            if url.endswith("/user"):
                return _mock_response(json_data={"login": "marcelobragadossantos"})
            if "graphql" in url:
                return _mock_response(
                    json_data={
                        "data": {
                            "user": {
                                "pullRequests": {"totalCount": 99},
                                "issues": {"totalCount": 33},
                                "repositories": {
                                    "totalCount": 25,
                                    "nodes": [{"stargazerCount": 5}, {"stargazerCount": 3}],
                                },
                                "contributionsCollection": {
                                    "totalCommitContributions": 200,
                                    "restrictedContributionsCount": 50,
                                },
                            }
                        }
                    }
                )
            return _mock_response(json_data={})

        with patch("generator.github_api.requests.request", side_effect=fake_request):
            stats = api.fetch_stats()

        assert stats["commits"] == 250
        assert stats["stars"] == 8
        assert stats["repos"] == 25
        assert stats["prs"] == 99


class TestFetchFlightLog:
    def test_extracts_push_event_commits(self):
        api = GitHubAPI("marcelobragadossantos", token="")
        events = [
            {
                "type": "PushEvent",
                "created_at": "2026-04-10T14:32:00Z",
                "repo": {"name": "marcelobragadossantos/app"},
                "payload": {
                    "commits": [
                        {"sha": "abc1234", "message": "feat: add telemetry"},
                        {"sha": "def5678", "message": "fix: null pointer"},
                    ]
                },
            },
            {"type": "WatchEvent", "payload": {}},
        ]
        with patch("generator.github_api.requests.request") as mock_req:
            mock_req.return_value = _mock_response(json_data=events)
            log = api.fetch_flight_log(limit=5)

        assert len(log) == 2
        assert log[0]["sha"] == "def5678"  # reversed order → newest first
        assert log[0]["message"] == "fix: null pointer"
        assert log[1]["message"] == "feat: add telemetry"
        assert log[0]["repo"] == "marcelobragadossantos/app"

    def test_empty_events_returns_empty_list(self):
        api = GitHubAPI("marcelobragadossantos", token="")
        with patch("generator.github_api.requests.request") as mock_req:
            mock_req.return_value = _mock_response(json_data=[])
            assert api.fetch_flight_log() == []


class TestFetchCommitWeeks:
    def test_returns_empty_without_matching_token(self):
        api = GitHubAPI("marcelobragadossantos", token="")
        assert api.fetch_commit_weeks() == []

    def test_parses_contribution_calendar(self):
        api = GitHubAPI("marcelobragadossantos", token="tok")

        def fake_request(method, url, **kwargs):
            if url.endswith("/user"):
                return _mock_response(json_data={"login": "marcelobragadossantos"})
            if "graphql" in url:
                # Build 2 weeks with known totals
                return _mock_response(
                    json_data={
                        "data": {
                            "user": {
                                "contributionsCollection": {
                                    "contributionCalendar": {
                                        "weeks": [
                                            {"contributionDays": [
                                                {"contributionCount": 1},
                                                {"contributionCount": 2},
                                            ]},
                                            {"contributionDays": [
                                                {"contributionCount": 3},
                                                {"contributionCount": 4},
                                            ]},
                                        ]
                                    }
                                }
                            }
                        }
                    }
                )
            return _mock_response(json_data={})

        with patch("generator.github_api.requests.request", side_effect=fake_request):
            weeks = api.fetch_commit_weeks()

        assert weeks == [3, 7]
