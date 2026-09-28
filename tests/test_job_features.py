import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from job_runner import save_results
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
        response = client.post("/api/refresh", json={"role": "frontend"})
        public_page = client.get("/").get_data(as_text=True)
        admin_page = client.get("/admin").get_data(as_text=True)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Owner tools", public_page)
        self.assertIn("Reload latest saved jobs", public_page)
        self.assertIn("Owner token", admin_page)
        self.assertIn("Refresh all roles", admin_page)
        self.assertNotIn("ownerToken", public_page)

    def test_owner_login_and_csrf_protect_refresh(self):
        client = app_module.app.test_client()
        with patch.object(app_module, "OWNER_TOKEN", "test-owner-secret"), patch.dict(
            app_module.app.config, {"SECRET_KEY": "independent-session-secret"}
        ):
            login = client.post("/api/owner/login", json={"token": "test-owner-secret"})
            csrf_token = login.get_json()["csrf_token"]

            bad_csrf = client.post(
                "/api/refresh", json={"role": "backend"}, headers={"X-CSRF-Token": "wrong"}
            )
            self.assertEqual(login.status_code, 200)
            self.assertEqual(bad_csrf.status_code, 401)

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
