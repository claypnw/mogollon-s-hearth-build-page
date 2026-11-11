(() => {
  'use strict';

  const byId = id => document.getElementById(id);
  const maps = ['world', 'skyrim'];
  const back = byId('back');
  const reset = byId('reset');
  const openSkyrim = byId('openSkyrim');
  const openArizona = byId('openArizona');
  const picker = byId('locationPicker');
  const dialog = byId('loreCard');
  const close = byId('loreClose');
  const dismiss = byId('loreDismiss');
  const explore = byId('loreExplore');
  const mapsLink = byId('loreMaps');
  const preview = byId('hoverCard');
  const svgNamespace = 'http://www.w3.org/2000/svg';

  let current;
  let returnFocus;
  let hoverTimer;

  function fillCard(title, heading, container) {
    heading.textContent = title;
    container.replaceChildren(...lore[title].map(paragraph => {
      const element = document.createElement('p');
      element.textContent = paragraph;
      return element;
    }));
  }

  function hidePreview() {
    clearTimeout(hoverTimer);
    preview.hidden = true;
  }

  function showCard(map, title, trigger, fromKeyboard = false) {
    if (map !== current || dialog.open) return;
    hidePreview();
    // Only restore map focus after keyboard activation. Mouse/touch
    // activation must not leave a visible focus ring on the map.
    returnFocus = fromKeyboard ? trigger : null;
    fillCard(title, byId('loreTitle'), byId('loreText'));
    explore.hidden = map !== 'world' || title !== 'Skyrim';
    mapsLink.hidden = map !== 'skyrim' || title !== 'Mogollon Hearth';
    dialog.showModal();
    byId('loreBody').scrollTop = 0;
  }

  function changeMap(name, focusTarget) {
    if (name === current) return;
    hidePreview();
    if (dialog.open) {
      returnFocus = null;
      dialog.close();
    }
    current = name;
    for (const map of maps) {
      const scene = byId(map);
      const active = map === name;
      scene.classList.toggle('active', active);
      scene.inert = !active;
      scene.setAttribute('aria-hidden', String(!active));
    }
    const detailed = name === 'skyrim';
    back.hidden = !detailed;
    openSkyrim.hidden = detailed;
    openArizona.hidden = !detailed;
    byId('subTitle').textContent = detailed ? 'Skyrim · Province of Tamriel' : 'Explore the lands of Tamriel';
    picker.replaceChildren(new Option('Choose a location', ''), ...Object.keys(regionsByMap[name])
      .sort((a, b) => a.localeCompare(b))
      .map(title => new Option(title, title)));
    const url = new URL(location.href);
    url.hash = detailed ? 'skyrim' : '';
    if (url.href !== location.href) history.replaceState({ view: name }, '', url);
    if (focusTarget) focusTarget.focus({ preventScroll: true });
  }

  function polygonPoints(geometry) {
    if (typeof geometry === 'string') return geometry;
    const [left, top, right, bottom] = geometry;
    return `${left},${top} ${right},${top} ${right},${bottom} ${left},${bottom}`;
  }

  for (const map of maps) {
    const svg = byId(map).querySelector('svg');
    for (const [title, geometry] of Object.entries(regionsByMap[map])) {
      const region = document.createElementNS(svgNamespace, 'polygon');
      region.setAttribute('points', polygonPoints(geometry));
      region.classList.add('region');
      region.setAttribute('role', 'button');
      region.setAttribute('tabindex', '0');
      region.setAttribute('aria-label', title);
      region.setAttribute('aria-haspopup', 'dialog');
      region.addEventListener('pointerenter', event => {
        if (event.pointerType !== 'mouse' || map !== current || dialog.open) return;
        hidePreview();
        const bounds = region.getBoundingClientRect();
        const mapBounds = svg.getBoundingClientRect();
        const onRight = bounds.left + bounds.width / 2 < mapBounds.left + mapBounds.width / 2;
        hoverTimer = setTimeout(() => {
          fillCard(title, byId('hoverTitle'), byId('hoverText'));
          preview.classList.toggle('on-left', !onRight);
          preview.hidden = false;
        }, 1500);
      });
      region.addEventListener('pointerleave', hidePreview);
      region.addEventListener('pointercancel', hidePreview);
      region.addEventListener('click', event => showCard(map, title, region, event.detail === 0));
      region.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          showCard(map, title, region, true);
        }
      });
      svg.append(region);
    }
  }

  picker.addEventListener('change', () => {
    const title = picker.value;
    picker.value = '';
    if (title) showCard(current, title, picker);
  });
  close.addEventListener('click', () => dialog.close());
  dismiss.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener('close', () => {
    if (dialog.open) return;
    if (returnFocus) {
      returnFocus.focus({ preventScroll: true });
    } else if (document.activeElement instanceof HTMLElement || document.activeElement instanceof SVGElement) {
      // Browsers may restore focus to the clicked SVG region when a modal closes.
      // For pointer users this causes a persistent highlight after dismissal.
      document.activeElement.blur();
    }
    returnFocus = null;
  });
  mapsLink.href = openArizona.href;
  mapsLink.addEventListener('click', () => dialog.close());
  explore.addEventListener('click', () => changeMap('skyrim', back));
  back.addEventListener('click', () => changeMap('world', openSkyrim));
  reset.addEventListener('click', () => changeMap('world', openSkyrim));
  openSkyrim.addEventListener('click', () => changeMap('skyrim', back));
  window.addEventListener('hashchange', () => changeMap(location.hash === '#skyrim' ? 'skyrim' : 'world'));
  window.addEventListener('blur', hidePreview);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hidePreview();
  });
  changeMap(location.hash === '#skyrim' ? 'skyrim' : 'world');
})();