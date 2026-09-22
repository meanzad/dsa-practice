/* Language tabs + copy buttons for archived article pages. */
(() => {
  const PREF = 'a2z-lang';
  let preferred = null;
  try { preferred = localStorage.getItem(PREF); } catch (e) {}

  const show = (wrap, i) => {
    wrap.querySelectorAll('.tab').forEach(t =>
      t.classList.toggle('on', t.dataset.i === String(i)));
    wrap.querySelectorAll('pre[data-i]').forEach(p =>
      p.classList.toggle('hidden', p.dataset.i !== String(i)));
  };

  document.querySelectorAll('.codewrap').forEach(wrap => {
    const tabs = [...wrap.querySelectorAll('.tab')];

    tabs.forEach(t => t.addEventListener('click', () => {
      show(wrap, t.dataset.i);
      // Remember the language across every code block and every article.
      try { localStorage.setItem(PREF, t.textContent.trim()); } catch (e) {}
      document.querySelectorAll('.codewrap').forEach(other => {
        if (other === wrap) return;
        const m = [...other.querySelectorAll('.tab')]
          .find(x => x.textContent.trim() === t.textContent.trim());
        if (m) show(other, m.dataset.i);
      });
    }));

    if (preferred) {
      const m = tabs.find(x => x.textContent.trim() === preferred);
      if (m) show(wrap, m.dataset.i);
    }

    const copy = wrap.querySelector('.copy');
    if (copy) copy.addEventListener('click', () => {
      const vis = wrap.querySelector('pre[data-i]:not(.hidden)');
      if (!vis) return;
      navigator.clipboard.writeText(vis.innerText).then(() => {
        copy.textContent = 'Copied';
        setTimeout(() => { copy.textContent = 'Copy'; }, 1200);
      }).catch(() => { copy.textContent = 'Press Ctrl+C'; });
    });
  });
})();
