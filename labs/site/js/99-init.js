// Boot. The script is loaded with `defer`, so the DOM is ready.
function boot() {
  const run = (name, fn) => { try { fn(); } catch (e) { console.error(`[labs] ${name} failed`, e); } };
  run('theme', initTheme);
  run('copy', initCopy);
  run('search', initSearch);
  run('values', () => applyValues(document));
  run('nav', initNav);
  run('tracks', initTracks);
  run('codeTabs', initCodeTabs);
  run('steps', initSteps);
  run('setup', initSetup);
  run('pathBanner', initPathBanner);
  run('toc', initToc);
  run('lightbox', initLightbox);
  run('videos', initVideos);
  run('catalog', initCatalog);
  run('troubleshooting', initTroubleshooting);
  run('tsPanel', initTsPanel);
  run('hero', initHero);
  run('diagrams', initDiagrams);
  run('widgets', () => renderWidgets(document));
  run('scrollRegions', () => watchScrollRegions(document));
  run('labLinks', updateLabLinks);
  run('mermaid', () => { initMermaid(); });
  addEventListener('storage', (e) => {
    if (e.key === 'aigw-progress') { if (LAB) updateProgressUI(false); else updateLabLinks(); }
    if (e.key === 'aigw-setup') updateSetupUI();
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
