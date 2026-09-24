/* Striver A2Z - offline sheet UI. Progress lives in localStorage. */
(() => {
  const KEY = 'a2z-progress-v1';
  const $ = s => document.querySelector(s);

  let state = { solved: {}, revision: {} };
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) state = Object.assign(state, JSON.parse(raw));
  } catch (e) { /* private mode / blocked storage - run without persistence */ }

  const save = () => {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  };

  let SHEET = null, ALL = [];

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
    const el = document.createElement('div');
    el.className = 'row';
    el.dataset.id = p.id;
    el.dataset.diff = p.difficulty;
    el.dataset.name = (p.name || '').toLowerCase();

    // "Article" = full archived editorial with code. "Statement" = recovered
    // from the relaunched site, which keeps its solutions behind a login.
    const stmt = p.article_kind === 'statement';
    const art = p.article_available
      ? '<a class="pill' + (stmt ? ' stmt' : '') + '" href="articles/'
        + encodeURIComponent(p.article_slug) + '.html" title="'
        + (stmt ? 'Problem statement, examples and hints (no solution)'
                : 'Full article with solutions and code')
        + '">' + (stmt ? 'Statement' : 'Article') + '</a>'
      : '<span class="pill off" title="No article available for this problem">Article</span>';
    // These deliberately point at the LIVE sites, never the archive.
    const yt = p.youtube
      ? '<a class="pill" href="' + esc(p.youtube) + '" target="_blank" rel="noopener">YouTube</a>' : '';
    const lc = p.leetcode
      ? '<a class="pill" href="' + esc(p.leetcode) + '" target="_blank" rel="noopener">LeetCode</a>' : '';

    el.innerHTML = '<input type="checkbox" ' + (state.solved[p.id] ? 'checked' : '') + ' aria-label="solved">'
      + '<span class="name">' + esc(p.name) + '</span>'
      + '<span class="links">' + art + yt + lc + '</span>'
      + '<button class="star ' + (state.revision[p.id] ? 'on' : '') + '" title="Mark for revision">&#9733;</button>'
      + '<span class="diff ' + p.difficulty + '">' + p.difficulty + '</span>';

    if (state.solved[p.id]) el.classList.add('done');

    el.querySelector('input').addEventListener('change', e => {
      if (e.target.checked) state.solved[p.id] = 1; else delete state.solved[p.id];
      el.classList.toggle('done', e.target.checked);
      save(); refresh();
    });
    el.querySelector('.star').addEventListener('click', e => {
      const on = !state.revision[p.id];
      if (on) state.revision[p.id] = 1; else delete state.revision[p.id];
      e.currentTarget.classList.toggle('on', on);
      save(); applyFilters();
    });
    return el;
  }

  function refresh() {
    const done = ALL.filter(p => state.solved[p.id]);
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
      const rows = [...sec.querySelectorAll('.row')];
      const n = rows.filter(r => state.solved[r.dataset.id]).length;
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
        if (!node.classList.contains('row')) return;
        const id = node.dataset.id;
        let ok = (!q || node.dataset.name.includes(q))
              && (!diff || node.dataset.diff === diff);
        if (ok && st === 'solved') ok = !!state.solved[id];
        if (ok && st === 'unsolved') ok = !state.solved[id];
        if (ok && st === 'revision') ok = !!state.revision[id];
        node.classList.toggle('hidden', !ok);
        if (ok) { shown++; headHas = true; }
      });
      if (lastHead) lastHead.classList.toggle('hidden', !headHas);
      sec.classList.toggle('hidden', shown === 0);
      // Auto-open sections while actively searching or filtering.
      if (q || diff || st) sec.open = shown > 0;
    });
  }

  function exportProgress() {
    const payload = { exported: new Date().toISOString(), solved: state.solved, revision: state.revision };
    const blob = new Blob([JSON.stringify(payload, null, 1)], { type: 'application/json' });
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
        state.solved = d.solved || {};
        state.revision = d.revision || {};
        save(); render();
        alert('Progress imported.');
      } catch (e) { alert('That file could not be read as progress JSON.'); }
    };
    fr.readAsText(file);
  }

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
      $('#expand').addEventListener('click', () => {
        const anyClosed = [...document.querySelectorAll('.sec')].some(s => !s.open);
        document.querySelectorAll('.sec').forEach(s => s.open = anyClosed);
      });
    })
    .catch(() => {
      $('#sections').innerHTML =
        '<p style="color:var(--hard)">Could not load data/sheet.json. '
        + 'If you opened this file directly, serve the folder over HTTP instead '
        + '(<code>python -m http.server</code>).</p>';
    });
})();
