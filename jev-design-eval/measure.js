(() => {
  const round = n => Math.round(n * 100) / 100;
  const rect = r => ({x: round(r.x), y: round(r.y), width: round(r.width), height: round(r.height),
    right: round(r.right), bottom: round(r.bottom)});
  const rgb = s => {
    if (!/^rgba?\(/.test(s)) return null;
    const values = s.match(/[\d.]+/g).map(Number);
    return values.length === 3 || values[3] === 1 ? values.slice(0, 3) : null;
  };
  const luminance = c => c.map(x => {x /= 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4;})
    .reduce((a, x, i) => a + x * [.2126, .7152, .0722][i], 0);
  const measure = id => {
    const e = document.getElementById(id);
    if (!e) return null;
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    const visible = e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) && r.width > 0 && r.height > 0;
    let bg = null, p = e, backgroundSupported = true;
    while (p && !bg) {
      const ps = getComputedStyle(p);
      if (ps.backgroundImage !== 'none' || Number(ps.opacity) !== 1) backgroundSupported = false;
      if (ps.backgroundColor !== 'rgba(0, 0, 0, 0)' && ps.backgroundColor !== 'transparent') {
        bg = rgb(ps.backgroundColor);
        if (!bg) backgroundSupported = false;
        break;
      }
      p = p.parentElement;
    }
    const fg = rgb(s.color);
    const ratio = fg && bg && backgroundSupported ? (Math.max(luminance(fg), luminance(bg)) + .05) /
      (Math.min(luminance(fg), luminance(bg)) + .05) : null;
    const range = document.createRange(); range.selectNodeContents(e);
    const tr = range.getBoundingClientRect();
    const samples = [];
    if (visible) for (const dx of [.15, .5, .85]) for (const dy of [.2, .5, .8]) {
      const x = r.x + dx*r.width, y = r.y + dy*r.height;
      const hit = document.elementFromPoint(x, y);
      samples.push({x:round(x), y:round(y), targetReceivesHit:!!hit && e.contains(hit),
        topElement:hit ? {tag:hit.tagName.toLowerCase(), role:hit.getAttribute('role'),
          text:(hit.innerText || '').slice(0,100)} : null});
    }
    return {tag:e.tagName.toLowerCase(), role:e.getAttribute('role'), text:(e.innerText || '').slice(0,600),
      title:e.getAttribute('title'), disabled:e.matches(':disabled'), visible, box:rect(r), textBox:rect(tr),
      clientWidth:e.clientWidth, scrollWidth:e.scrollWidth, clientHeight:e.clientHeight, scrollHeight:e.scrollHeight,
      style:{fontSize:s.fontSize, lineHeight:s.lineHeight, color:s.color, backgroundColor:s.backgroundColor,
        overflowX:s.overflowX, overflowY:s.overflowY, whiteSpace:s.whiteSpace, textOverflow:s.textOverflow},
      contrastRatio:ratio === null ? null : round(ratio), contrastMeasurementSupported:!!(fg && bg && backgroundSupported),
      hitSamples:samples, pixelContentInspected:false};
  };
  const ids = ['session-title','session-art','availability-badge','brand-art','code-status','receipt-button',
    'attendee-name','attendee-email','confirm-button','project-label'];
  const elements = Object.fromEntries(ids.map(id => [id, measure(id)]));
  const intersection = (a,b) => !a || !b || !a.visible || !b.visible ? null : round(
    Math.max(0, Math.min(a.box.right,b.box.right)-Math.max(a.box.x,b.box.x)) *
    Math.max(0, Math.min(a.box.bottom,b.box.bottom)-Math.max(a.box.y,b.box.y)));
  return {viewport:{width:innerWidth,height:innerHeight,scrollX,scrollY,
      documentWidth:document.documentElement.scrollWidth}, elements,
    relationships:{badgeArtIntersectionPx2:intersection(elements['availability-badge'],elements['session-art']),
      badgeTitleIntersectionPx2:intersection(elements['availability-badge'],elements['session-title'])},
    coverage:{geometry:true,computedStyles:true,hitTesting:'nine sampled points per visible element',
      images:false,canvasContents:false,complexBackgroundContrast:false}};
})()
