/* Striver A2Z - offline sheet UI.
 *
 * State lives in localStorage and, when sync is configured, in a private Gist.
 * Shape (v2): { v, updated, problems: { <id>: {solved, revision, note, ts} } }
 */
(() => {
  const KEY = 'a2z-progress-v1';          // kept: v1 data is migrated in place
  const $ = s => document.querySelector(s);
  const now = () => Date.now();

  let state = { v: 2, updated: null, problems: {} };
  let SHEET = null, ALL = [];
  let pushTimer = null;

  // ---------- persistence ----------

  function load() {
    let raw = null;
    try { raw = localStorage.getItem(KEY); } catch (e) {}
    if (!raw) return;
    let d;
    try { d = JSON.parse(raw); } catch (e) { return; }
    if (d && d.v === 2 && d.problems) { state = d; return; }
    // Migrate v1: separate solved/revision maps, no notes, no timestamps.
    const ts = now();
    const problems = {};
    Object.keys(d.solved || {}).forEach(id => {
      problems[id] = { solved: true, revision: false, note: '', ts };
    });
    Object.keys(d.revision || {}).forEach(id => {
      problems[id] = problems[id] || { solved: false, note: '', ts };
      problems[id].revision = true;
    });
    state = { v: 2, updated: new Date().toISOString(), problems };
    save(false);
  }

  function save(remote = true) {
    state.updated = new Date().toISOString();
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
    if (remote && window.A2ZSync && A2ZSync.configured()) schedulePush();
  }

  const rec = id => state.problems[id] || (state.problems[id] = {
    solved: false, revision: false, note: '', ts: 0,
  });

  function touch(id) { rec(id).ts = now(); }

  // ---------- sync ----------

  function syncStatus(text, cls) {
    const el = $('#sync-state');
    if (!el) return;
    el.textContent = text;
    el.className = 'sync-state ' + (cls || '');
  }

  function schedulePush() {
    clearTimeout(pushTimer);
    syncStatus('saving…', 'busy');
    pushTimer = setTimeout(async () => {
      try {
        await A2ZSync.push(state);
        syncStatus('synced', 'ok');
      } catch (e) {
        syncStatus('sync failed', 'err');
        console.warn('push failed', e);
      }
    }, 1500);
  }

  async function syncNow(silent) {
    if (!window.A2ZSync || !A2ZSync.configured()) return;
    syncStatus('syncing…', 'busy');
    try {
      const remote = await A2ZSync.pull();
      if (remote) {
        state = A2ZSync.merge(state, remote);
        try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
        render();
      }
      await A2ZSync.push(state);
      syncStatus('synced', 'ok');
    } catch (e) {
      syncStatus('sync failed', 'err');
      if (!silent) alert('Sync failed: ' + e.message);
    }
  }

  // ---------- rendering ----------

  const ESCMAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ESCMAP[c]);

  function render() {
    const root = $('#sections');
    root.innerHTML = '';
    SHEET.sections.forEach((cat, ci) => {
      const probs = cat.subcategories.flatMap(s => s.problems);
      const d = document.createElement('details');
      d.className = 'sec';
      d.open = ci === 0;
      d.innerHTML = '<summary>'
        + '<span class="chev">&#9654;</span>'
        + '<span>' + esc(cat.name) + '</span>'
        + '<span class="minibar"><i></i></span>'
        + '<span class="count">0 / ' + probs.length + '</span>'
        + '</summary>';
      cat.subcategories.forEach(sub => {
        const h = document.createElement('div');
        h.className = 'subhead';
        h.textContent = sub.name;
        d.appendChild(h);
        sub.problems.forEach(p => d.appendChild(rowEl(p)));
      });
      root.appendChild(d);
    });
    refresh();
  }

  function rowEl(p) {
    const r = rec(p.id);
    const el = document.createElement('div');
    el.className = 'rowwrap';
    el.dataset.id = p.id;
    el.dataset.diff = p.difficulty;
    el.dataset.name = (p.name || '').toLowerCase();

    const stmt = p.article_kind === 'statement';
    const art = p.article_available
      ? '<a class="pill' + (stmt ? ' stmt' : '') + '" href="articles/'
        + encodeURIComponent(p.article_slug) + '.html" title="'
        + (stmt ? 'Problem statement, examples and hints (no solution)'
                : 'Full article with solutions and code')
        + '">' + (stmt ? 'Statement' : 'Article') + '</a>'
      : '<span class="pill off" title="No article available for this problem">Article</span>';
    const yt = p.youtube
      ? '<a class="pill" href="' + esc(p.youtube) + '" target="_blank" rel="noopener">YouTube</a>' : '';
    const lc = p.leetcode
      ? '<a class="pill" href="' + esc(p.leetcode) + '" target="_blank" rel="noopener">LeetCode</a>' : '';

    el.innerHTML = '<div class="row">'
      + '<input type="checkbox" ' + (r.solved ? 'checked' : '') + ' aria-label="solved">'
      + '<span class="name">' + esc(p.name) + '</span>'
      + '<span class="links">' + art + yt + lc + '</span>'
      + '<button class="note-btn' + (r.note ? ' has' : '') + '" title="Notes">&#9998;</button>'
      + '<button class="star ' + (r.revision ? 'on' : '') + '" title="Mark for revision">&#9733;</button>'
      + '<span class="diff ' + p.difficulty + '">' + p.difficulty + '</span>'
      + '</div>'
      + '<div class="notebox hidden"><textarea placeholder="Notes: approach, edge cases, '
      + 'why you got it wrong...">' + esc(r.note) + '</textarea></div>';

    const row = el.querySelector('.row');
    if (r.solved) row.classList.add('done');

    el.querySelector('input').addEventListener('change', e => {
      rec(p.id).solved = e.target.checked;
      touch(p.id);
      row.classList.toggle('done', e.target.checked);
      save(); refresh();
    });
    el.querySelector('.star').addEventListener('click', e => {
      const on = !rec(p.id).revision;
      rec(p.id).revision = on;
      touch(p.id);
      e.currentTarget.classList.toggle('on', on);
      save(); applyFilters();
    });

    const box = el.querySelector('.notebox');
    const ta = box.querySelector('textarea');
    el.querySelector('.note-btn').addEventListener('click', () => {
      box.classList.toggle('hidden');
      if (!box.classList.contains('hidden')) { ta.focus(); autosize(ta); }
    });
    let noteTimer = null;
    ta.addEventListener('input', () => {
      autosize(ta);
      clearTimeout(noteTimer);
      noteTimer = setTimeout(() => {
        rec(p.id).note = ta.value;
        touch(p.id);
        el.querySelector('.note-btn').classList.toggle('has', !!ta.value.trim());
        save(); applyFilters();
      }, 400);
    });
    return el;
  }

  function autosize(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight + 2, 320) + 'px';
  }

  function refresh() {
    const solved = id => (state.problems[id] || {}).solved;
    const done = ALL.filter(p => solved(p.id));
    const by = d => ALL.filter(p => p.difficulty === d);
    const dby = d => done.filter(p => p.difficulty === d);
    $('#p-total').textContent = done.length + ' / ' + ALL.length;
    ['Easy', 'Medium', 'Hard'].forEach(d => {
      $('#p-' + d.toLowerCase()).textContent = dby(d).length + ' / ' + by(d).length;
    });
    const pct = ALL.length ? (done.length / ALL.length * 100) : 0;
    $('#p-bar').style.width = pct.toFixed(1) + '%';
    $('#p-pct').textContent = pct.toFixed(1) + '%';

    document.querySelectorAll('.sec').forEach(sec => {
      const rows = [...sec.querySelectorAll('.rowwrap')];
      const n = rows.filter(r => solved(r.dataset.id)).length;
      sec.querySelector('.count').textContent = n + ' / ' + rows.length;
      sec.querySelector('.minibar > i').style.width =
        (rows.length ? n / rows.length * 100 : 0) + '%';
    });
    applyFilters();
  }

  function applyFilters() {
    const q = $('#q').value.trim().toLowerCase();
    const diff = $('#f-diff').value;
    const st = $('#f-status').value;
    document.querySelectorAll('.sec').forEach(sec => {
      let shown = 0, lastHead = null, headHas = false;
      [...sec.children].forEach(node => {
        if (node.classList.contains('subhead')) {
          if (lastHead) lastHead.classList.toggle('hidden', !headHas);
          lastHead = node; headHas = false;
          return;
        }
        if (!node.classList.contains('rowwrap')) return;
        const id = node.dataset.id;
        const r = state.problems[id] || {};
        const hay = node.dataset.name + ' ' + (r.note || '').toLowerCase();
        let ok = (!q || hay.includes(q)) && (!diff || node.dataset.diff === diff);
        if (ok && st === 'solved') ok = !!r.solved;
        if (ok && st === 'unsolved') ok = !r.solved;
        if (ok && st === 'revision') ok = !!r.revision;
        if (ok && st === 'noted') ok = !!(r.note && r.note.trim());
        node.classList.toggle('hidden', !ok);
        if (ok) { shown++; headHas = true; }
      });
      if (lastHead) lastHead.classList.toggle('hidden', !headHas);
      sec.classList.toggle('hidden', shown === 0);
      if (q || diff || st) sec.open = shown > 0;
    });
  }

  // ---------- import / export ----------

  function exportProgress() {
    const blob = new Blob([JSON.stringify(state, null, 1)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'a2z-progress-' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function importProgress(file) {
    const fr = new FileReader();
    fr.onload = () => {
      try {
        const d = JSON.parse(fr.result);
        if (d.v === 2 && d.problems) {
          state = A2ZSync.merge(state, d);
        } else {
          const ts = now(), problems = {};
          Object.keys(d.solved || {}).forEach(id => {
            problems[id] = { solved: true, revision: false, note: '', ts };
          });
          Object.keys(d.revision || {}).forEach(id => {
            problems[id] = problems[id] || { solved: false, note: '', ts };
            problems[id].revision = true;
          });
          state = A2ZSync.merge(state, { v: 2, problems });
        }
        save(); render();
        alert('Progress imported.');
      } catch (e) { alert('That file could not be read as progress JSON.'); }
    };
    fr.readAsText(file);
  }

  // ---------- sync dialog ----------

  async function openSync() {
    if (A2ZSync.configured()) {
      if (confirm('Sync is on for this browser.\n\nGist ID: ' + (A2ZSync.gistId() || '—')
          + '\n\nOK = sync now,  Cancel = disconnect.')) {
        await syncNow();
      } else {
        A2ZSync.disconnect();
        syncStatus('off', '');
      }
      return;
    }
    const t = prompt(
      'Paste a GitHub fine-grained token with Gist access (write).\n\n'
      + 'It is stored only in this browser and sent only to api.github.com.\n'
      + 'Never commit it to the repo.');
    if (!t) return;
    syncStatus('connecting…', 'busy');
    A2ZSync.setToken(t);
    try {
      let id = null, made = false;
      try {
        id = await A2ZSync.findGist();
      } catch (e) {
        // Lookup failed (often a token without gist read). Do NOT fall through
        // to creating one - that is how a second machine ends up on its own
        // gist with progress silently split in two.
        const manual = prompt(
          'Could not list your gists (' + e.message + ').\n\n'
          + 'If you already set up sync on another machine, paste that gist ID '
          + '(Sync shows it there). Leave blank to cancel.');
        if (!manual) throw e;
        id = await A2ZSync.useGist(manual);
      }
      if (!id) {
        const manual = prompt(
          'No existing progress gist found on this account.\n\n'
          + 'If you already set one up on another machine, paste its gist ID.\n'
          + 'Leave blank to create a NEW one (do this on your first machine only).');
        if (manual) id = await A2ZSync.useGist(manual);
        else { id = await A2ZSync.createGist(); made = true; }
      }
      await syncNow();
      alert((made ? 'Created a new private gist.\n\n' : 'Connected to your gist.\n\n')
        + 'Gist ID: ' + id + '\n\nUse this same ID on your other machine.');
    } catch (e) {
      A2ZSync.disconnect();
      syncStatus('off', '');
      alert('Could not connect: ' + e.message);
    }
  }

  // ---------- boot ----------

  load();
  fetch('data/sheet.json?v=' + (window.__V || ''))
    .then(r => r.json())
    .then(d => {
      SHEET = d;
      ALL = d.sections.flatMap(c => c.subcategories.flatMap(s => s.problems));
      render();
      $('#q').addEventListener('input', applyFilters);
      $('#f-diff').addEventListener('change', applyFilters);
      $('#f-status').addEventListener('change', applyFilters);
      $('#export').addEventListener('click', exportProgress);
      $('#import').addEventListener('click', () => $('#file').click());
      $('#file').addEventListener('change', e => {
        if (e.target.files[0]) importProgress(e.target.files[0]);
      });
      $('#sync').addEventListener('click', openSync);
      $('#expand').addEventListener('click', () => {
        const anyClosed = [...document.querySelectorAll('.sec')].some(s => !s.open);
        document.querySelectorAll('.sec').forEach(s => s.open = anyClosed);
      });
      if (A2ZSync.configured()) syncNow(true); else syncStatus('off', '');
      // Pick up edits made on another machine when returning to the tab.
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && A2ZSync.configured()) syncNow(true);
      });
    })
    .catch(() => {
      $('#sections').innerHTML =
        '<p style="color:var(--hard)">Could not load data/sheet.json. '
        + 'If you opened this file directly, serve the folder over HTTP instead '
        + '(<code>python -m http.server</code>).</p>';
    });
})();
