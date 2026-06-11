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
  .card { background: #fff; border-radius: 12px; border: 1px solid #e5e5e0; padding: 16px; display: flex; flex-direction: column; gap: 8px; cursor: pointer; transition: all 0.2s; }
  .card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); transform: translateY(-2px); }
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
    <input type="text" id="search" placeholder="Search title or company..." oninput="filter()">
    <select id="source-filter" onchange="filter()">
      <option value="">All sources</option>
      <option value="serper">Google (Serper)</option>
      <option value="linkedin">LinkedIn</option>
      <option value="remoteok">RemoteOK</option>
    </select>
    <select id="location-filter" onchange="filter()">
      <option value="">All locations</option>
      <option value="nigeria">Nigeria only</option>
      <option value="remote">Remote only</option>
    </select>
    <button id="refresh-btn" onclick="refresh()">Refresh jobs</button>
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
    const matchLoc = !loc || (loc === 'nigeria' && j.nigeria_relevant) || (loc === 'remote' && j.location.toLowerCase().includes('remote'));
    return matchQ && matchSrc && matchLoc;
  });

  document.getElementById('stats').textContent = `Showing ${filtered.length} of ${allJobs.length} jobs`;

  const grid = document.getElementById('grid');
  if (!filtered.length) {
    grid.innerHTML = '<div class="empty">No jobs match your filters.</div>';
    return;
  }

  grid.innerHTML = filtered.map((j, idx) => `
    <div class="card" onclick="showDetails(${allJobs.indexOf(j)})">
      <div class="card-title">${j.title || 'Untitled'}</div>
      <div class="card-company">${j.company || 'Unknown company'}</div>
      <div class="card-meta">
        ${j.nigeria_relevant ? '<span class="badge badge-ng">Nigeria</span>' : ''}
        ${j.location && j.location.toLowerCase().includes('remote') ? '<span class="badge badge-remote">Remote</span>' : ''}
        <span class="badge badge-source">${j.source || ''}</span>
      </div>
      <div class="card-desc">${(j.description || '').substring(0, 200)}${j.description && j.description.length > 200 ? '...' : ''}</div>
      <span style="font-size: 12px; color: #999; margin-top: 8px;">👆 Click for details</span>
    </div>
  `).join('');
}

function showDetails(idx) {
  const j = allJobs[idx];
  const html = `
    <div class="modal-title">${j.title}</div>
    <div class="modal-company">${j.company}</div>
    
    ${j.location ? `<div class="modal-field"><div class="modal-field-label">Location</div><div class="modal-field-value">📍 ${j.location}</div></div>` : ''}
    ${j.salary ? `<div class="modal-field"><div class="modal-field-label">Salary</div><div class="modal-field-value">💰 ${j.salary}</div></div>` : ''}
    ${j.posted ? `<div class="modal-field"><div class="modal-field-label">Posted</div><div class="modal-field-value">📅 ${j.posted}</div></div>` : ''}
    <div class="modal-field"><div class="modal-field-label">Source</div><div class="modal-field-value">🔗 ${j.source}</div></div>
    ${j.nigeria_relevant ? '<div class="modal-field"><div class="modal-field-label">Nigeria Relevant</div><div class="modal-field-value">✓ Yes</div></div>' : ''}
    
    ${j.description ? `<div class="modal-field"><div class="modal-field-label">Description</div><div class="modal-field-value">${j.description.replace(/\\n/g, '<br>')}</div></div>` : ''}
    
    ${j.apply_link ? `<div style="margin-top: 24px;"><a class="apply-btn" href="${j.apply_link}" target="_blank" style="display: block; text-align: center; padding: 12px;">Apply on external site →</a></div>` : ''}
  `;
  document.getElementById('modal-body').innerHTML = html;
  document.getElementById('modal').classList.add('active');
}

function closeModal() {
  document.getElementById('modal').classList.remove('active');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

document.getElementById('modal').addEventListener('click', e => {
  if (e.target.id === 'modal') closeModal();
});

async function refresh() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true;
  btn.textContent = 'Scraping...';
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
        btn.textContent = 'Done! Refresh jobs';
        setTimeout(() => { btn.textContent = 'Refresh jobs'; btn.disabled = false; }, 2000);
      }
    }
  } catch(e) {
    btn.textContent = 'Error - check console';
    btn.disabled = false;
  }
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