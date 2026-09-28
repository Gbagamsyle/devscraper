import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

import app as app_module
from config import ROLE_PROFILES
from free_boards import fetch_remoteok
from job_runner import (
    build_google_queries,
    filter_jobs_for_role,
    save_results,
    sort_by_eligibility,
    tag_nigeria,
)
from utils import classify_nigeria_eligibility, deduplicate_jobs


class JobFeatureTests(unittest.TestCase):
    def test_dedup_merges_sources_but_preserves_location_variants(self):
        jobs = [
            {
                "title": "Backend Engineer",
                "company": "Example Inc",
                "location": "Remote",
                "apply_link": "https://jobs.example.com/1",
                "source": "serper",
            },
            {
                "title": "Backend Engineer",
                "company": "Example Inc",
                "location": "Remote",
                "apply_link": "https://boards.example.com/1",
                "source": "linkedin",
            },
            {
                "title": "Backend Engineer",
                "company": "Example Inc",
                "location": "London, UK",
                "apply_link": "https://jobs.example.com/2",
                "source": "serper",
            },
        ]

        result = deduplicate_jobs(jobs)

        self.assertEqual(len(result), 2)
        remote = next(job for job in result if job["location"] == "Remote")
        self.assertEqual(remote["source"], "serper, linkedin")
        self.assertEqual({source["name"] for source in remote["sources"]}, {"serper", "linkedin"})
        self.assertEqual(len(remote["sources"]), 2)

    def test_remote_alone_is_unclear(self):
        result = classify_nigeria_eligibility({"location": "Remote", "description": ""})
        self.assertEqual(result["eligibility"], "unclear")
        self.assertIn("remote status alone", result["eligibility_reason"].casefold())

        incidental_mention = classify_nigeria_eligibility({
            "location": "Remote",
            "description": "Our engineering team recently visited Nigeria.",
        })
        self.assertEqual(incidental_mention["eligibility"], "unclear")

    def test_explicit_nigeria_scope_is_listed(self):
        result = classify_nigeria_eligibility({"location": "Remote — Nigeria"})
        self.assertEqual(result["eligibility"], "listed")
        self.assertIn("nigeria", result["eligibility_evidence"])

    def test_explicit_us_only_scope_is_restricted(self):
        result = classify_nigeria_eligibility({"location": "Remote — US only"})
        self.assertEqual(result["eligibility"], "restricted")

    def test_restricted_job_is_not_nigeria_relevant_or_promoted(self):
        restricted = tag_nigeria({
            "title": "Frontend Developer",
            "location": "Remote — US only",
            "description": "The hiring team was discussed in Nigeria; US only eligibility.",
        })
        listed = tag_nigeria({
            "title": "Frontend Developer",
            "location": "Remote — Nigeria",
        })
        unclear = tag_nigeria({"title": "Frontend Developer", "location": "Remote"})

        self.assertEqual(restricted["eligibility"], "restricted")
        self.assertFalse(restricted["nigeria_relevant"])
        self.assertEqual(
            [job["eligibility"] for job in sort_by_eligibility([restricted, unclear, listed])],
            ["listed", "unclear", "restricted"],
        )

    def test_google_search_budget_is_three_per_role(self):
        for role in ROLE_PROFILES:
            queries = build_google_queries(role)
            self.assertEqual(len(queries), 3)
            self.assertEqual(len(set(queries)), 3)
        self.assertEqual(sum(len(build_google_queries(role)) for role in ROLE_PROFILES), 18)

    def test_final_role_filter_drops_off_category_results(self):
        jobs = [
            {"title": "Backend Engineer", "tags": ["python"]},
            {"title": "Product Designer", "tags": ["figma", "product design"]},
            {"title": "Frontend Developer", "tags": ["react"]},
        ]
        result = filter_jobs_for_role(jobs, "backend")
        self.assertEqual([job["title"] for job in result], ["Backend Engineer"])

    def test_remoteok_specific_location_is_preserved(self):
        response = Mock()
        response.json.return_value = [
            {},
            {
                "position": "Frontend Developer",
                "company": "Example",
                "location": "United States only",
                "tags": ["frontend developer", "react"],
                "description": "Role details",
                "url": "https://example.com/job",
            },
        ]
        with patch("free_boards.requests.get", return_value=response):
            jobs = fetch_remoteok("frontend")
        self.assertEqual(jobs[0]["location"], "United States only")

    def test_results_are_saved_under_role_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, csv_path = save_results(
                [{"title": "Designer", "company": "Example", "sources": [{"name": "board", "url": "https://example.com/job"}], "role": "product-design"}],
                temp_dir,
                role="product-design",
            )

            self.assertEqual(Path(json_path).parent.name, "product-design")
            self.assertTrue(Path(json_path).exists())
            with open(json_path, encoding="utf-8") as file:
                self.assertEqual(json.load(file)[0]["role"], "product-design")
            with open(csv_path, newline="", encoding="utf-8") as file:
                row = next(csv.DictReader(file))
            self.assertEqual(json.loads(row["sources"])[0]["name"], "board")

    def test_public_app_is_separate_from_admin_controls(self):
        client = app_module.app.test_client()
        public_page = client.get("/").get_data(as_text=True)
        admin_page = client.get("/admin").get_data(as_text=True)
        self.assertNotIn("Owner tools", public_page)
        self.assertIn("Reload latest saved jobs", public_page)
        self.assertIn("Search for fresh listings", public_page)
        self.assertIn("Owner token", admin_page)
        self.assertIn("Refresh all roles", admin_page)
        self.assertNotIn("ownerToken", public_page)

    def test_public_refresh_is_single_role_and_has_global_cooldown(self):
        client = app_module.app.test_client()
        other_visitor = app_module.app.test_client()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            app_module, "OUTPUT_DIR", temp_dir
        ):
            forbidden = client.post("/api/refresh", json={"role": "all"})
            invalid_role = client.post("/api/refresh", json={"role": ["backend"]})

            class ImmediateThread:
                def __init__(self, target, daemon):
                    self.target = target

                def start(self):
                    self.target()

            with patch.object(app_module, "run_scraper") as run_scraper, patch.object(
                app_module.threading, "Thread", ImmediateThread
            ):
                started = client.post("/api/refresh", json={"role": "backend"})
                cooled_down = other_visitor.post("/api/refresh", json={"role": "mobile"})
            status = client.get("/api/public-refresh-status").get_json()

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(invalid_role.status_code, 400)
        self.assertEqual(started.status_code, 202)
        run_scraper.assert_called_once_with(role="backend")
        self.assertEqual(cooled_down.status_code, 429)
        self.assertGreater(cooled_down.get_json()["retry_after"], 0)
        self.assertFalse(status["running"])
        self.assertGreater(status["retry_after"], 0)

    def test_refresh_lock_blocks_simultaneous_visitor_requests(self):
        client = app_module.app.test_client()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            app_module, "OUTPUT_DIR", temp_dir
        ):
            class DeferredThread:
                run_target = None

                def __init__(self, target, daemon):
                    DeferredThread.run_target = staticmethod(target)

                def start(self):
                    pass

            with patch.object(app_module, "run_scraper"), patch.object(
                app_module.threading, "Thread", DeferredThread
            ):
                started = client.post("/api/refresh", json={"role": "backend"})
                concurrent = client.post("/api/refresh", json={"role": "frontend"})
                DeferredThread.run_target()

        self.assertEqual(started.status_code, 202)
        self.assertEqual(concurrent.status_code, 409)

    def test_owner_login_and_csrf_protect_refresh(self):
        client = app_module.app.test_client()
        with patch.object(app_module, "OWNER_TOKEN", "test-owner-secret"), patch.dict(
            app_module.app.config, {"SECRET_KEY": "independent-session-secret"}
        ):
            login = client.post("/api/owner/login", json={"token": "test-owner-secret"})
            csrf_token = login.get_json()["csrf_token"]

            with patch.object(app_module, "run_scraper") as should_not_run:
                bad_csrf = client.post(
                    "/api/refresh", json={"role": "backend"}, headers={"X-CSRF-Token": "wrong"}
                )
            self.assertEqual(login.status_code, 200)
            self.assertEqual(bad_csrf.status_code, 401)
            should_not_run.assert_not_called()

            class ImmediateThread:
                def __init__(self, target, daemon):
                    self.target = target

                def start(self):
                    self.target()

            with patch.object(app_module, "run_scraper") as run_scraper, patch.object(
                app_module.threading, "Thread", ImmediateThread
            ):
                started = client.post(
                    "/api/refresh",
                    json={"role": "backend"},
                    headers={"X-CSRF-Token": csrf_token},
                )

        self.assertEqual(started.status_code, 202)
        run_scraper.assert_called_once_with(role="backend")

    def test_owner_can_refresh_all_roles(self):
        client = app_module.app.test_client()
        with patch.object(app_module, "OWNER_TOKEN", "test-owner-secret"), patch.dict(
            app_module.app.config, {"SECRET_KEY": "independent-session-secret"}
        ):
            login = client.post("/api/owner/login", json={"token": "test-owner-secret"})
            csrf_token = login.get_json()["csrf_token"]

            class ImmediateThread:
                def __init__(self, target, daemon):
                    self.target = target

                def start(self):
                    self.target()

            with patch.object(app_module, "run_scraper") as run_scraper, patch.object(
                app_module.threading, "Thread", ImmediateThread
            ):
                response = client.post(
                    "/api/refresh",
                    json={"role": "all"},
                    headers={"X-CSRF-Token": csrf_token},
                )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            [call.kwargs["role"] for call in run_scraper.call_args_list],
            list(app_module.ROLE_PROFILES),
        )

    def test_jobs_api_loads_selected_role_snapshot(self):
        client = app_module.app.test_client()
        with tempfile.TemporaryDirectory() as temp_dir:
            role_dir = Path(temp_dir) / "backend"
            role_dir.mkdir()
            (role_dir / "jobs_20260928_120000.json").write_text(
                json.dumps([{"title": "Backend Engineer", "role": "backend"}]),
                encoding="utf-8",
            )
            with patch.object(app_module, "OUTPUT_DIR", temp_dir):
                response = client.get("/api/jobs?role=backend")
                invalid_role = client.get("/api/jobs?role=not-a-role")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0]["role"], "backend")
        self.assertTrue(response.headers.get("X-Updated-At"))
        self.assertEqual(invalid_role.status_code, 400)


if __name__ == "__main__":
    unittest.main()
