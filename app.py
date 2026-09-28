import os, json, glob, hmac, secrets, threading
from flask import Flask, jsonify, render_template_string, request, session
from config import APP_SECRET_KEY, OUTPUT_DIR, OWNER_TOKEN, ROLE_PROFILES
from job_runner import main as run_scraper

app = Flask(__name__)
app.secret_key = APP_SECRET_KEY
app.config.update(
  SESSION_COOKIE_HTTPONLY=True,
  SESSION_COOKIE_SAMESITE="Lax",
  SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").casefold() == "true",
)
scraper_running = False
scraper_lock = threading.Lock()

def get_latest_jobs(role="frontend"):
  role_output = os.path.join(OUTPUT_DIR, role)
  files = sorted(glob.glob(os.path.join(role_output, "jobs_*.json")), reverse=True)
  # Keep the existing frontend dataset visible until its first role-scoped run.
  if not files and role == "frontend":
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "jobs_*.json")), reverse=True)
  if not files:
    return []
  with open(files[0], encoding="utf-8") as f:
    return json.load(f)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dev Jobs — Nigeria & Remote</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #f5f5f0; color: #1a1a1a; }
  header { background: #fff; border-bottom: 1px solid #e5e5e0; padding: 1rem 2rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
  header h1 { font-size: 18px; font-weight: 600; }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  input, select { padding: 7px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 13px; background: #fff; }
  input { width: 220px; }
  #reload-btn { background: #1a1a1a; color: #fff; }
  #reload-btn:disabled { background: #888; cursor: wait; }
  button { padding: 7px 16px; border-radius: 8px; border: none; font-size: 13px; cursor: pointer; font-weight: 500; }
  .stats { padding: 1rem 2rem; font-size: 13px; color: #666; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; padding: 0 2rem 2rem; }
  .card { background: #fff; border-radius: 12px; border: 1px solid #e5e5e0; padding: 16px; display: flex; flex-direction: column; gap: 8px; cursor: pointer; transition: all 0.2s; }
  .card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); transform: translateY(-2px); }
  .card-title { font-size: 15px; font-weight: 600; line-height: 1.3; }
  .card-company { font-size: 13px; color: #555; }
  .card-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 2px; }
  .badge { font-size: 11px; padding: 3px 8px; border-radius: 99px; font-weight: 500; }
  .badge-ng { background: #e8f5e9; color: #2e7d32; }
  .badge-eligibility { background: #fff3cd; color: #775b00; text-transform: capitalize; }
  .badge-remote { background: #e3f2fd; color: #1565c0; }
  .badge-source { background: #f3e5f5; color: #6a1b9a; }
  .card-desc { font-size: 12px; color: #777; line-height: 1.5; flex: 1; }
  .apply-btn { margin-top: 4px; display: inline-block; padding: 8px 14px; background: #1a1a1a; color: #fff; border-radius: 8px; font-size: 13px; text-decoration: none; text-align: center; font-weight: 500; }
  .apply-btn:hover { background: #333; }
  #status { font-size: 13px; color: #f59e0b; font-weight: 500; }
  .empty { text-align: center; padding: 4rem; color: #999; grid-column: 1/-1; }
  #modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 1000; }
  #modal.active { display: flex; align-items: center; justify-content: center; }
  .modal-content { background: #fff; border-radius: 12px; width: 90%; max-width: 600px; max-height: 90vh; overflow-y: auto; padding: 32px; position: relative; }
  .close { position: absolute; top: 16px; right: 16px; font-size: 28px; font-weight: 700; cursor: pointer; color: #999; }
  .close:hover { color: #1a1a1a; }
  .modal-title { font-size: 22px; font-weight: 700; margin-bottom: 8px; }
  .modal-company { font-size: 16px; color: #666; margin-bottom: 16px; }
  .modal-field { margin-bottom: 16px; }
  .modal-field-label { font-size: 12px; font-weight: 700; color: #666; text-transform: uppercase; margin-bottom: 4px; }
  .modal-field-value { font-size: 14px; line-height: 1.6; }
</style>
</head>
<body>
<header>
  <h1>Dev Jobs — Nigeria & Remote</h1>
  <div class="controls">
    <select id="role-filter" aria-label="Choose role" onchange="loadJobs()">
      <option value="frontend">Frontend</option>
      <option value="backend">Backend</option>
      <option value="full-stack">Full-stack</option>
      <option value="mobile">Mobile</option>
      <option value="data">Data</option>
      <option value="product-design">Product design</option>
    </select>
    <input type="text" id="search" placeholder="Search title or company..." oninput="filter()">
    <select id="source-filter" onchange="filter()">
      <option value="">All sources</option>
      <option value="serper">Google (Serper)</option>
      <option value="linkedin">LinkedIn</option>
      <option value="remoteok">RemoteOK</option>
    </select>
    <select id="location-filter" onchange="filter()">
      <option value="">All eligibility</option>
      <option value="listed">Nigeria eligibility listed</option>
      <option value="unclear">Eligibility unclear</option>
      <option value="restricted">Restricted</option>
      <option value="remote">Remote only</option>
    </select>
    <button id="reload-btn" type="button" onclick="reloadSavedJobs()">Reload latest saved jobs</button>
  </div>
</header>
<div class="stats" id="stats"></div>
<div class="grid" id="grid"></div>

<div id="modal">
  <div class="modal-content">
    <span class="close" onclick="closeModal()">&times;</span>
    <div id="modal-body"></div>
  </div>
</div>

<script>
let allJobs = [];

async function loadJobs() {
  const role = document.getElementById('role-filter').value;
  const res = await fetch('/api/jobs?role=' + encodeURIComponent(role));
  allJobs = await res.json();
  document.getElementById('stats').dataset.updated = res.headers.get('X-Updated-At') || '';
  filter();
}

async function reloadSavedJobs() {
  const button = document.getElementById('reload-btn');
  button.disabled = true;
  button.textContent = 'Checking saved listings...';
  try {
    await loadJobs();
    const updatedAt = document.getElementById('stats').dataset.updated;
    document.getElementById('stats').textContent += updatedAt
      ? ` · Snapshot saved ${new Date(updatedAt).toLocaleString()}`
      : ' · No saved snapshot yet for this role';
  } catch (error) {
    document.getElementById('stats').textContent = 'Could not reload saved listings. Please try again.';
  } finally {
    button.disabled = false;
    button.textContent = 'Reload latest saved jobs';
  }
}

function escapeHTML(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[ch]);
}

function safeUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(url.protocol) ? escapeHTML(url.href) : '#';
  } catch (_) { return '#'; }
}

function sourceNames(job) {
  if (Array.isArray(job.sources) && job.sources.length) {
    return job.sources.map(s => typeof s === 'string' ? s : s.name).filter(Boolean);
  }
  return String(job.source || '').split(',').map(s => s.trim()).filter(Boolean);
}

function filter() {
  const q = document.getElementById('search').value.toLowerCase();
  const src = document.getElementById('source-filter').value;
  const loc = document.getElementById('location-filter').value;

  let filtered = allJobs.filter(j => {
    const text = ((j.title || '') + ' ' + (j.company || '')).toLowerCase();
    const matchQ = !q || text.includes(q);
    const matchSrc = !src || sourceNames(j).some(name => name.toLowerCase().includes(src));
    const eligibility = j.eligibility || (j.nigeria_relevant ? 'listed' : 'unclear');
    const matchLoc = !loc || (loc === 'remote' && (j.location || '').toLowerCase().includes('remote')) || (loc !== 'remote' && eligibility === loc);
    return matchQ && matchSrc && matchLoc;
  });

  const stats = document.getElementById('stats');
  const updatedAt = stats.dataset.updated;
  const snapshotNote = updatedAt ? ` · Snapshot saved ${new Date(updatedAt).toLocaleString()}` : '';
  stats.textContent = `Showing ${filtered.length} of ${allJobs.length} ${document.getElementById('role-filter').selectedOptions[0].text} jobs${snapshotNote}`;

  const grid = document.getElementById('grid');
  if (!filtered.length) {
    grid.innerHTML = updatedAt
      ? '<div class="empty">No jobs match your filters.</div>'
      : '<div class="empty">No saved listings for this role yet.</div>';
    return;
  }

  grid.innerHTML = filtered.map(j => `
    <div class="card" data-job-index="${allJobs.indexOf(j)}" onclick="handleCardClick(this)">
      <div class="card-title">${escapeHTML(j.title || 'Untitled')}</div>
      <div class="card-company">${escapeHTML(j.company || 'Unknown company')}</div>
      <div class="card-meta">
        <span class="badge badge-eligibility">${escapeHTML(j.eligibility || (j.nigeria_relevant ? 'listed' : 'unclear'))}</span>
        ${j.location && j.location.toLowerCase().includes('remote') ? '<span class="badge badge-remote">Remote</span>' : ''}
        <span class="badge badge-source">${escapeHTML(sourceNames(j).join(', '))}</span>
      </div>
      <div class="card-desc">${escapeHTML((j.description || '').substring(0, 200))}${j.description && j.description.length > 200 ? '...' : ''}</div>
      <span style="font-size: 12px; color: #999; margin-top: 8px;">👆 Click for details</span>
    </div>
  `).join('');
}

function handleCardClick(el) {
  const idx = parseInt(el.getAttribute('data-job-index'));
  showDetails(idx);
}

function showDetails(idx) {
  const j = allJobs[idx];
  if (!j) return;
  const desc = escapeHTML(j.description || '').split('\\n').join('<br>');
  const sourceEntries = Array.isArray(j.sources) ? j.sources : [];
  const sources = sourceEntries.length
    ? sourceEntries.map(source => {
        const name = escapeHTML(typeof source === 'string' ? source : source.name);
        const url = typeof source === 'string' ? '' : source.url;
        return url ? `<a href="${safeUrl(url)}" rel="noopener noreferrer" target="_blank">${name}</a>` : name;
      }).join(', ')
    : sourceNames(j).map(name => escapeHTML(name)).join(', ');
  const eligibility = j.eligibility || (j.nigeria_relevant ? 'listed' : 'unclear');
  const reason = j.eligibility_reason || 'Eligibility could not be determined from the available listing information.';
  const html = `
    <div class="modal-title">${escapeHTML(j.title || 'Untitled')}</div>
    <div class="modal-company">${escapeHTML(j.company || 'Unknown company')}</div>
    ${j.location ? `<div class="modal-field"><div class="modal-field-label">Listed location</div><div class="modal-field-value">📍 ${escapeHTML(j.location)}</div></div>` : ''}
    ${j.salary ? `<div class="modal-field"><div class="modal-field-label">Salary</div><div class="modal-field-value">💰 ${escapeHTML(j.salary)}</div></div>` : ''}
    ${j.posted ? `<div class="modal-field"><div class="modal-field-label">Posted</div><div class="modal-field-value">📅 ${escapeHTML(j.posted)}</div></div>` : ''}
    <div class="modal-field"><div class="modal-field-label">Sources</div><div class="modal-field-value">🔗 ${sources || 'Unknown'}</div></div>
    <div class="modal-field"><div class="modal-field-label">Nigeria eligibility: ${escapeHTML(eligibility)}</div><div class="modal-field-value">${escapeHTML(reason)}${j.eligibility_evidence ? `<br><strong>Evidence:</strong> ${escapeHTML(j.eligibility_evidence)}` : ''}</div></div>
    ${desc ? `<div class="modal-field"><div class="modal-field-label">Description</div><div class="modal-field-value">${desc}</div></div>` : ''}
    ${j.apply_link ? `<div style="margin-top: 12px;"><a class="apply-btn" href="${safeUrl(j.apply_link)}" rel="noopener noreferrer" target="_blank" style="display: block; text-align: center; padding: 12px;">Apply on external site →</a></div>` : ''}
    ${j.company ? `<div style="margin-top: 12px;"><a class="apply-btn" href="https://www.google.com/search?q=${encodeURIComponent(j.company + ' careers')}" rel="noopener noreferrer" target="_blank" style="display: block; text-align: center; padding: 10px; background:#eee; color:#111;">Search ${escapeHTML(j.company)} — jobs & careers</a></div>` : ''}
  `;
  document.getElementById('modal-body').innerHTML = html;
  document.getElementById('modal').classList.add('active');
}

function closeModal() { document.getElementById('modal').classList.remove('active'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
document.getElementById('modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });

loadJobs();
</script>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Owner tools — Dev Jobs</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 2rem; background: #f5f5f0; color: #1a1a1a; font: 15px system-ui, sans-serif; }
  main { max-width: 620px; margin: 5vh auto; padding: 2rem; background: white; border: 1px solid #e5e5e0; border-radius: 16px; }
  h1 { margin-top: 0; font-size: 1.5rem; }
  p { color: #666; line-height: 1.5; }
  label { display: block; margin: 1rem 0 .4rem; font-weight: 600; }
  input, select, button { padding: .7rem .9rem; border: 1px solid #ddd; border-radius: 8px; font: inherit; }
  input, select { width: 100%; }
  button { cursor: pointer; background: #1a1a1a; color: white; border: 0; }
  button:disabled { opacity: .55; cursor: wait; }
  .actions { display: flex; gap: .75rem; flex-wrap: wrap; margin-top: 1rem; }
  .actions button { flex: 1; min-width: 170px; }
  [hidden] { display: none !important; }
  #status { min-height: 1.5rem; margin-top: 1rem; color: #555; }
  a { color: #1558a6; }
</style>
</head>
<body>
<main>
  <h1>Owner tools</h1>
  <p>Private controls for refreshing saved job snapshots. Visitors can view these snapshots without signing in.</p>
  <form id="login-form">
    <label for="token">Owner token</label>
    <input id="token" type="password" autocomplete="current-password" required>
    <div class="actions"><button type="submit">Sign in</button></div>
  </form>
  <section id="actions" hidden>
    <label for="role">Snapshot to refresh</label>
    <select id="role">
      <option value="frontend">Frontend</option>
      <option value="backend">Backend</option>
      <option value="full-stack">Full-stack</option>
      <option value="mobile">Mobile</option>
      <option value="data">Data</option>
      <option value="product-design">Product design</option>
    </select>
    <div class="actions">
      <button id="refresh-selected" type="button" onclick="refresh(false)">Refresh selected role</button>
      <button id="refresh-all" type="button" onclick="refresh(true)">Refresh all roles</button>
      <button type="button" onclick="logout()">Sign out</button>
    </div>
  </section>
  <div id="status" role="status"></div>
  <a href="/">Return to public job board</a>
</main>
<script>
let csrfToken = '';
const loginForm = document.getElementById('login-form');
const actions = document.getElementById('actions');
const status = document.getElementById('status');

async function checkSession() {
  const response = await fetch('/api/owner/status');
  const data = await response.json();
  loginForm.hidden = data.authenticated;
  actions.hidden = !data.authenticated;
  csrfToken = data.csrf_token || '';
  if (data.authenticated) status.textContent = 'Signed in as owner.';
}

loginForm.addEventListener('submit', async event => {
  event.preventDefault();
  const tokenInput = document.getElementById('token');
  const response = await fetch('/api/owner/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: tokenInput.value })
  });
  const data = await response.json();
  tokenInput.value = '';
  if (!response.ok) {
    status.textContent = data.error || 'Sign-in failed.';
    return;
  }
  await checkSession();
});

async function logout() {
  await fetch('/api/owner/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } });
  csrfToken = '';
  status.textContent = 'Signed out.';
  await checkSession();
}

async function refresh(allRoles) {
  if (allRoles && !window.confirm('Refresh all six roles? This uses substantially more search quota.')) return;
  const buttons = [...document.querySelectorAll('#actions button')];
  buttons.forEach(button => button.disabled = true);
  status.textContent = 'Starting refresh...';
  try {
    const response = await fetch('/api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ role: allRoles ? 'all' : document.getElementById('role').value })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not start refresh.');
    status.textContent = 'Refreshing saved snapshots...';
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const check = await fetch('/api/status');
      const progress = await check.json();
      if (!check.ok) throw new Error(progress.error || 'Owner session expired.');
      if (!progress.running) break;
    }
    status.textContent = 'Refresh complete. Visitors can now reload the saved listings.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    buttons.forEach(button => button.disabled = false);
  }
}

checkSession();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/admin")
def admin():
    return render_template_string(ADMIN_HTML)

@app.route("/api/jobs")
def api_jobs():
    role = request.args.get("role", "frontend")
    if role not in ROLE_PROFILES:
        return jsonify({"error": "Unknown role"}), 400

    role_output = os.path.join(OUTPUT_DIR, role)
    files = sorted(glob.glob(os.path.join(role_output, "jobs_*.json")), reverse=True)
    if not files and role == "frontend":
        files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "jobs_*.json")), reverse=True)

    response = jsonify(get_latest_jobs(role))
    if files:
        from datetime import datetime

        timestamp = os.path.basename(files[0]).removeprefix("jobs_").removesuffix(".json")
        for timestamp_format in ("%Y%m%d_%H%M%S_%f", "%Y%m%d_%H%M%S", "%Y%m%d_%H%M"):
            try:
                saved_at = datetime.strptime(timestamp, timestamp_format).isoformat()
                response.headers["X-Updated-At"] = saved_at
                break
            except ValueError:
                continue
    return response


@app.route("/api/owner/status")
def api_owner_status():
    authenticated = bool(session.get("owner_authenticated"))
    return jsonify({
        "authenticated": authenticated,
        "csrf_token": session.get("csrf_token", "") if authenticated else "",
    })


@app.route("/api/owner/login", methods=["POST"])
def api_owner_login():
    if not OWNER_TOKEN or not app.secret_key:
        return jsonify({"error": "Owner sign-in is not configured on the server."}), 503
    supplied_token = (request.get_json(silent=True) or {}).get("token", "")
    if not hmac.compare_digest(str(supplied_token), OWNER_TOKEN):
        return jsonify({"error": "Invalid owner token."}), 401
    session.clear()
    session["owner_authenticated"] = True
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({"authenticated": True, "csrf_token": session["csrf_token"]})


def owner_csrf_valid():
    expected = session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    return bool(
        session.get("owner_authenticated")
        and expected
        and hmac.compare_digest(supplied, expected)
    )


@app.route("/api/owner/logout", methods=["POST"])
def api_owner_logout():
    if not owner_csrf_valid():
        return jsonify({"error": "Owner sign-in required."}), 401
    session.clear()
    return jsonify({"authenticated": False})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    global scraper_running
    if not owner_csrf_valid():
        return jsonify({"error": "Owner sign-in required."}), 401
    role = (request.get_json(silent=True) or {}).get("role", "frontend")
    if role != "all" and role not in ROLE_PROFILES:
        return jsonify({"error": "Unknown role."}), 400
    if not scraper_lock.acquire(blocking=False):
        return jsonify({"error": "A refresh is already running."}), 409
    scraper_running = True

    def run():
        global scraper_running
        try:
            roles = ROLE_PROFILES if role == "all" else [role]
            for selected_role in roles:
                run_scraper(role=selected_role)
        finally:
            scraper_running = False
            scraper_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started", "role": role}), 202


@app.route("/api/status")
def api_status():
    if not session.get("owner_authenticated"):
        return jsonify({"error": "Owner sign-in required."}), 401
    return jsonify({"running": scraper_running})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)