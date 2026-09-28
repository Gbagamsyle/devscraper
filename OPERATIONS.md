# Public site and scheduled listing refreshes

The web app serves saved snapshots from `output/<role>/`. Visitors can use **Reload latest saved jobs** to fetch the existing snapshot without running searches, or **Search for fresh listings** to trigger a new scrape of the selected role. Public fresh searches share a global one-hour cooldown across all visitors; only one refresh may run at a time, and visitors cannot request all roles at once. Owner controls remain on `/admin` and may refresh all roles.

Google is capped at three searches per role (Nigeria, Africa, remote worldwide). LinkedIn is capped at six searches per role (three role terms × Nigeria/Remote). A public selected-role search may additionally make up to five Twitter searches and one RemoteOK request when enabled. **Refresh all roles** can make up to 18 Google, 36 LinkedIn, 30 Twitter, and six RemoteOK requests. The confirmation and cooldown reduce accidental API spend but cannot prevent a visitor from being the person who uses each allowed public refresh.

## Refresh snapshots manually

The owner can sign in on the website and refresh the selected role. For unattended updates, run the scraper from the project directory using the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe job_runner.py --all-roles
```

Use `--role frontend` (or another configured role) to refresh only one category. The command runs outside the web request path, so visitors cannot trigger or duplicate a metered search.

## Schedule updates

On Windows, create a Task Scheduler task that runs the command above on the desired cadence. Set **Start in** to the project directory so `.env`, logs, and output paths resolve correctly. On a Linux host, use that platform's scheduler to run the equivalent virtual-environment Python command. Choose a cadence that fits the search-provider budget; each full run queries every role.

The public Flask app should be deployed behind HTTPS with a production WSGI server. Set `OWNER_TOKEN`, a separate random `APP_SECRET_KEY`, and `SESSION_COOKIE_SECURE=true` in production. Keep all secrets server-side in a secret store, never in browser code or a public repository. Refresh serialization and the cooldown state use files under `output/`, shared across worker processes on one host. Do not run multiple hosts/instances with separate output directories; use a shared lock/state store or disable public refresh for multi-instance deployments.

## Configure owner secrets on Windows

Generate two different random values in PowerShell (run this block twice):

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[Convert]::ToBase64String($bytes)
```

Put one value in the private `.env` as `OWNER_TOKEN=...` and the other as `APP_SECRET_KEY=...`. Do not use the same value for both. Set `SESSION_COOKIE_SECURE=true` only after HTTPS is configured; for local `http://127.0.0.1`, leave it `false`. Restart the app after changing these values. Do not paste real secrets into chat or commit `.env`.
