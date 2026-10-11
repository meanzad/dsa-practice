/* Cross-machine sync for progress + notes, backed by a private GitHub Gist.
 *
 * The token lives only in this browser's localStorage. It is never committed,
 * never written into the page, and never sent anywhere except api.github.com.
 * Use a fine-grained token with Gist access and nothing else.
 */
window.A2ZSync = (() => {
  const TOKEN_KEY = 'a2z-gh-token';
  const GIST_KEY = 'a2z-gist-id';
  const FILENAME = 'a2z-progress.json';
  const API = 'https://api.github.com';

  const get = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const set = (k, v) => {
    try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch (e) {}
  };

  const token = () => get(TOKEN_KEY);
  const gistId = () => get(GIST_KEY);
  const configured = () => !!token();

  async function api(path, opts = {}) {
    const r = await fetch(API + path, {
      ...opts,
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: 'Bearer ' + token(),
        'X-GitHub-Api-Version': '2022-11-28',
        ...(opts.body ? { 'Content-Type': 'application/json' } : {}),
        ...(opts.headers || {}),
      },
    });
    if (!r.ok) {
      let detail = '';
      try { detail = (await r.json()).message || ''; } catch (e) {}
      const err = new Error(`GitHub ${r.status}${detail ? ': ' + detail : ''}`);
      err.status = r.status;
      throw err;
    }
    return r.json();
  }

  /** Verify the token and find (or create) the gist holding our state. */
  async function connect(newToken) {
    set(TOKEN_KEY, newToken.trim());
    // Look for an existing gist from a previous machine before making one.
    const gists = await api('/gists?per_page=100');
    const found = gists.find(g => g.files && g.files[FILENAME]);
    if (found) {
      set(GIST_KEY, found.id);
      return { created: false, id: found.id };
    }
    const made = await api('/gists', {
      method: 'POST',
      body: JSON.stringify({
        description: "Striver A2Z sheet - progress and notes (private)",
        public: false,
        files: { [FILENAME]: { content: JSON.stringify(emptyState(), null, 1) } },
      }),
    });
    set(GIST_KEY, made.id);
    return { created: true, id: made.id };
  }

  function disconnect() { set(TOKEN_KEY, null); set(GIST_KEY, null); }

  const emptyState = () => ({ v: 2, updated: new Date().toISOString(), problems: {} });

  async function pull() {
    if (!configured() || !gistId()) return null;
    const g = await api('/gists/' + gistId());
    const f = g.files && g.files[FILENAME];
    if (!f) return null;
    // Large gists come back truncated, with the full body at raw_url.
    const text = f.truncated ? await (await fetch(f.raw_url)).text() : f.content;
    try { return JSON.parse(text); } catch (e) { return null; }
  }

  async function push(state) {
    if (!configured() || !gistId()) return false;
    await api('/gists/' + gistId(), {
      method: 'PATCH',
      body: JSON.stringify({
        files: { [FILENAME]: { content: JSON.stringify(state, null, 1) } },
      }),
    });
    return true;
  }

  /** Per-problem last-write-wins. Two machines editing different problems
   *  both keep their work; the same problem resolves to the newer edit. */
  function merge(a, b) {
    const out = { v: 2, updated: new Date().toISOString(), problems: {} };
    const ids = new Set([
      ...Object.keys((a && a.problems) || {}),
      ...Object.keys((b && b.problems) || {}),
    ]);
    for (const id of ids) {
      const x = (a && a.problems && a.problems[id]) || null;
      const y = (b && b.problems && b.problems[id]) || null;
      if (!x) { out.problems[id] = y; continue; }
      if (!y) { out.problems[id] = x; continue; }
      out.problems[id] = (y.ts || 0) >= (x.ts || 0) ? y : x;
    }
    return out;
  }

  return { connect, disconnect, configured, gistId, pull, push, merge, emptyState,
           tokenPresent: configured };
})();
