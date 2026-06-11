import os, json, glob, threading
from flask import Flask, jsonify, render_template_string
from job_runner import main as run_scraper

app = Flask(__name__)
scraper_running = False

def get_latest_jobs():
    files = sorted(glob.glob("./output/jobs_*.json"), reverse=True)
    if not files:
        return []
    with open(files[0]) as f:
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
  button { padding: 7px 16px; border-radius: 8px; border: none; font-size: 13px; cursor: pointer; font-weight: 500; }
  #refresh-btn { background: #1a1a1a; color: #fff; }
  #refresh-btn:disabled { background: #888; cursor: not-allowed; }
  .stats { padding: 1rem 2rem; font-size: 13px; color: #666; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; padding: 0 2rem 2rem; }
  .card { background: #fff; border-radius: 12px; border: 1px solid #e5e5e0; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
  .card-title { font-size: 15px; font-weight: 600; line-height: 1.3; }
  .card-company { font-size: 13px; color: #555; }
  .card-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 2px; }
  .badge { font-size: 11px; padding: 3px 8px; border-radius: 99px; font-weight: 500; }
  .badge-ng { background: #e8f5e9; color: #2e7d32; }
  .badge-remote { background: #e3f2fd; color: #1565c0; }
  .badge-source { background: #f3e5f5; color: #6a1b9a; }
  .card-desc { font-size: 12px; color: #777; line-height: 1.5; flex: 1; }
  .apply-btn { margin-top: 4px; display: inline-block; padding: 8px 14px; background: #1a1a1a; color: #fff; border-radius: 8px; font-size: 13px; text-decoration: none; text-align: center; font-weight: 500; }
  .apply-btn:hover { background: #333; }
  #status { font-size: 13px; color: #f59e0b; font-weight: 500; }
  .empty { text-align: center; padding: 4rem; color: #999; grid-column: 1/-1; }
</style>
</head>
<body>
<header>
  <h1>Dev Jobs — Nigeria & Remote</h1>
  <div class="controls">
    <input type="text" id="search" placeholder="Search title or company..." oninput="filter()">
    <select id="source-filter" onchange="filter()">
      <option value="">All sources</option>
      <option value="serper">Google (Serper)</option>
      <option value="linkedin">LinkedIn</option>
      <option value="remoteok">RemoteOK</option>
      <option value="jobicy">Jobicy</option>
      <option value="remotive">Remotive</option>
    </select>
    <select id="location-filter" onchange="filter()">
      <option value="">All locations</option>
      <option value="nigeria">Nigeria only</option>
      <option value="remote">Remote only</option>
    </select>
    <span id="status"></span>
    <button id="refresh-btn" onclick="refresh()">Refresh jobs</button>
  </div>
</header>
<div class="stats" id="stats"></div>
<div class="grid" id="grid"></div>

<script>
let allJobs = [];

async function loadJobs() {
  const res = await fetch('/api/jobs');
  allJobs = await res.json();
  filter();
}

function filter() {
  const q = document.getElementById('search').value.toLowerCase();
  const src = document.getElementById('source-filter').value;
  const loc = document.getElementById('location-filter').value;

  let filtered = allJobs.filter(j => {
    const text = ((j.title || '') + ' ' + (j.company || '')).toLowerCase();
    const matchQ = !q || text.includes(q);
    const matchSrc = !src || (j.source || '').includes(src);
    const matchLoc = !loc
      || (loc === 'nigeria' && j.nigeria_relevant)
      || (loc === 'remote' && j.remote);
    return matchQ && matchSrc && matchLoc;
  });

  document.getElementById('stats').textContent =
    `Showing ${filtered.length} of ${allJobs.length} jobs`;

  const grid = document.getElementById('grid');
  if (!filtered.length) {
    grid.innerHTML = '<div class="empty">No jobs match your filters.</div>';
    return;
  }

  grid.innerHTML = filtered.map(j => `
    <div class="card">
      <div class="card-title">${j.title || 'Untitled'}</div>
      <div class="card-company">${j.company || 'Unknown company'}</div>
      <div class="card-meta">
        ${j.nigeria_relevant ? '<span class="badge badge-ng">Nigeria</span>' : ''}
        ${j.remote ? '<span class="badge badge-remote">Remote</span>' : ''}
        <span class="badge badge-source">${j.source || ''}</span>
      </div>
      <div class="card-desc">${(j.description || '').substring(0, 200)}${j.description && j.description.length > 200 ? '...' : ''}</div>
      ${j.apply_link ? `<a class="apply-btn" href="${j.apply_link}" target="_blank" rel="noopener">Apply</a>` : ''}
    </div>
  `).join('');
}

async function refresh() {
  const btn = document.getElementById('refresh-btn');
  const status = document.getElementById('status');
  btn.disabled = true;
  status.textContent = 'Scraping jobs...';
  try {
    await fetch('/api/refresh', { method: 'POST' });
    let done = false;
    while (!done) {
      await new Promise(r => setTimeout(r, 3000));
      const res = await fetch('/api/status');
      const data = await res.json();
      if (!data.running) {
        done = true;
        await loadJobs();
        status.textContent = 'Done!';
        setTimeout(() => status.textContent = '', 3000);
      } else {
        status.textContent = 'Still scraping...';
      }
    }
  } catch(e) {
    status.textContent = 'Error — check terminal';
  }
  btn.disabled = false;
}

loadJobs();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/jobs")
def api_jobs():
    return jsonify(get_latest_jobs())

@app.route("/api/status")
def api_status():
    return jsonify({"running": scraper_running})

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    global scraper_running
    if scraper_running:
        return jsonify({"status": "already running"})
    def run():
        global scraper_running
        scraper_running = True
        try:
            run_scraper()
        finally:
            scraper_running = False
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)