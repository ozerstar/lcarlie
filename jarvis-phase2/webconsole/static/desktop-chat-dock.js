(() => {
  'use strict';
  const dock = document.getElementById('cmdBar');
  const launcher = document.getElementById('chatLauncher');
  const input = document.getElementById('chatInput');
  const log = document.getElementById('chatLog');
  const empty = document.getElementById('chatEmpty');
  if (!dock || !launcher || !input || !log || !empty) return;

  function open(focus = true) {
    dock.hidden = false;
    launcher.hidden = true;
    launcher.setAttribute('aria-expanded', 'true');
    if (focus) input.focus({preventScroll: true});
  }
  function minimize() {
    dock.hidden = true;
    launcher.hidden = false;
    launcher.setAttribute('aria-expanded', 'false');
    launcher.focus({preventScroll: true});
  }
  function close() {
    if (!document.getElementById('stopBtn').hidden)
      document.getElementById('stopBtn').click();
    dock.hidden = true;
    launcher.hidden = true;
    launcher.setAttribute('aria-expanded', 'false');
    document.getElementById('quickChat')?.focus({preventScroll: true});
  }
  launcher.addEventListener('click', () => open());
  document.getElementById('chatMinimize').addEventListener('click', minimize);
  document.getElementById('chatClose').addEventListener('click', close);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !dock.hidden) minimize();
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && document.activeElement === input)
      document.getElementById('chatForm').requestSubmit();
  });
  document.addEventListener('click', (event) => {
    if (event.target.closest('#quickChat, .iv-ask, [data-ed-ask], .qa-btn[data-ask], .quick-actions [data-ask]')) open(false);
    if (event.target.closest('#mainNav .nav-item')) minimize();
  }, true);
  new MutationObserver(() => { empty.hidden = log.childElementCount > 0; })
    .observe(log, {childList: true});
  empty.hidden = log.childElementCount > 0;
})();
