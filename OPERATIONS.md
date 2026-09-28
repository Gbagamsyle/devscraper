# Public site and scheduled listing refreshes

The web app serves saved snapshots from `output/<role>/`. Visitors can browse and filter jobs without signing in, then use **Reload latest saved jobs** to fetch the latest already-saved snapshot; this does not run searches. Owner controls are on the separate `/admin` page and require the server-side `OWNER_TOKEN`. Use **Refresh all roles** there to populate/update every role snapshot (it performs significantly more searches); other roles show no listings until refreshed at least once.

## Refresh snapshots manually

The owner can sign in on the website and refresh the selected role. For unattended updates, run the scraper from the project directory using the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe job_runner.py --all-roles
```

Use `--role frontend` (or another configured role) to refresh only one category. The command runs outside the web request path, so visitors cannot trigger or duplicate a metered search.

## Schedule updates

On Windows, create a Task Scheduler task that runs the command above on the desired cadence. Set **Start in** to the project directory so `.env`, logs, and output paths resolve correctly. On a Linux host, use that platform's scheduler to run the equivalent virtual-environment Python command. Choose a cadence that fits the search-provider budget; each full run queries every role.

The public Flask app should be deployed behind HTTPS with a production WSGI server. Set `OWNER_TOKEN`, a separate random `APP_SECRET_KEY`, and `SESSION_COOKIE_SECURE=true` in production. Keep all secrets server-side in a secret store, never in browser code or a public repository. The in-process refresh lock is intended for a single app process; on multi-worker or multi-instance deployments, use a shared job queue/lock or rely on the scheduled CLI refresh instead of the owner web refresh.

## Configure owner secrets on Windows

Generate two different random values in PowerShell (run this block twice):

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[Convert]::ToBase64String($bytes)
```

Put one value in the private `.env` as `OWNER_TOKEN=...` and the other as `APP_SECRET_KEY=...`. Do not use the same value for both. Set `SESSION_COOKIE_SECURE=true` only after HTTPS is configured; for local `http://127.0.0.1`, leave it `false`. Restart the app after changing these values. Do not paste real secrets into chat or commit `.env`.
