(() => {
  const request = JSON.parse("__JEV_QA_PAYLOAD__");
  const checks = Array.isArray(request && request.checks) ? request.checks : [];
  const round = value => Number.isFinite(value) ? Math.round(value * 100) / 100 : null;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const rect = value => {
    if (!value || ![value.x, value.y, value.width, value.height, value.right, value.bottom].every(finite)) return null;
    return {
      x: round(value.x), y: round(value.y), width: round(value.width), height: round(value.height),
      right: round(value.right), bottom: round(value.bottom)
    };
  };
  const textValue = element => {
    const value = typeof element.innerText === "string" ? element.innerText : element.textContent;
    return typeof value === "string" ? {value: value.slice(0, 2000), truncated: value.length > 2000} : {value: "", truncated: false};
  };
  const opaqueRgb = value => {
    if (typeof value !== "string" || !/^rgba?\(/i.test(value)) return null;
    const parts = value.slice(value.indexOf("(") + 1, -1).split(",").map(part => Number(part.trim()));
    if (parts.length !== 3 && parts.length !== 4) return null;
    if (!parts.slice(0, 3).every(part => finite(part) && part >= 0 && part <= 255)) return null;
    if (parts.length === 4 && (!finite(parts[3]) || parts[3] !== 1)) return null;
    return parts.slice(0, 3);
  };
  const transparent = value => {
    if (value === "transparent") return true;
    if (typeof value !== "string" || !/^rgba?\(/i.test(value)) return false;
    const parts = value.slice(value.indexOf("(") + 1, -1).split(",").map(part => Number(part.trim()));
    return parts.length === 4 && parts[3] === 0;
  };
  const luminance = color => color.map(value => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
  const effects = element => {
    const reasons = [];
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (Number(style.opacity) !== 1) reasons.push("ancestor_opacity");
      if (style.filter && style.filter !== "none") reasons.push("ancestor_filter");
      if (style.transform && style.transform !== "none") reasons.push("ancestor_transform");
      if (node !== element && [style.overflowX, style.overflowY].some(value => value === "hidden" || value === "clip")) {
        reasons.push("ancestor_clipping");
      }
    }
    return [...new Set(reasons)];
  };
  const visible = (element, style, bounds) => {
    let checked = true;
    try {
      checked = typeof element.checkVisibility === "function"
        ? element.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) : true;
    } catch (_error) {
      checked = false;
    }
    return checked && style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity) !== 0 && bounds.width > 0 && bounds.height > 0;
  };
  const resolve = selector => {
    if (typeof selector !== "string") return {info: {status: "measurement_error", reason: "invalid_selector"}};
    let nodes;
    try {
      nodes = [...document.querySelectorAll(selector)];
    } catch (_error) {
      return {info: {status: "measurement_error", reason: "invalid_selector"}};
    }
    if (!nodes.length) return {info: {status: "measurement_error", reason: "selector_not_found", matchCount: 0}};
    if (nodes.length !== 1) {
      return {info: {status: "measurement_error", reason: "selector_ambiguous", matchCount: nodes.length}};
    }
    const element = nodes[0];
    const style = getComputedStyle(element);
    const bounds = rect(element.getBoundingClientRect());
    if (!bounds) return {info: {status: "measurement_error", reason: "invalid_geometry"}};
    const info = {status: "measured", visible: visible(element, style, bounds), box: bounds};
    if (!info.visible) info.status = "measurement_error", info.reason = "not_visible";
    return {element, style, info};
  };
  const addText = resolved => {
    if (!resolved.element) return resolved.info;
    try {
      const range = document.createRange();
      range.selectNodeContents(resolved.element);
      resolved.info.textBox = rect(range.getBoundingClientRect());
      const text = textValue(resolved.element);
      resolved.info.fullText = text.value;
      resolved.info.fullTextTruncated = text.truncated;
    } catch (_error) {
      resolved.info.status = "measurement_error";
      resolved.info.reason = "text_bounds_unavailable";
    }
    return resolved.info;
  };
  const addOverflow = resolved => {
    if (!resolved.element) return resolved.info;
    const style = resolved.style;
    resolved.info.overflowX = style.overflowX;
    resolved.info.overflowY = style.overflowY;
    resolved.info.whiteSpace = style.whiteSpace;
    resolved.info.textOverflow = style.textOverflow;
    resolved.info.clientWidth = round(resolved.element.clientWidth);
    resolved.info.scrollWidth = round(resolved.element.scrollWidth);
    resolved.info.clientHeight = round(resolved.element.clientHeight);
    resolved.info.scrollHeight = round(resolved.element.scrollHeight);
    return resolved.info;
  };
  const addEffects = resolved => {
    const unsupported = effects(resolved.element);
    if (unsupported.length) {
      resolved.info.status = "unsupported";
      resolved.info.reason = "unsupported_ancestor_effect";
      resolved.info.unsupported = unsupported;
    }
    return resolved.info;
  };
  const addContrast = resolved => {
    if (!resolved.element) return resolved.info;
    const reasons = effects(resolved.element);
    const foreground = opaqueRgb(resolved.style.color);
    let background = null;
    for (let node = resolved.element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.backgroundImage && style.backgroundImage !== "none") reasons.push("complex_background");
      const color = style.backgroundColor;
      const parsed = opaqueRgb(color);
      if (parsed) {
        background = parsed;
        break;
      }
      if (color && !transparent(color)) reasons.push("non_opaque_rgb_background");
    }
    resolved.info.foreground = foreground;
    resolved.info.background = background;
    resolved.info.contrastSupported = reasons.length === 0 && !!foreground && !!background;
    resolved.info.contrastRatio = resolved.info.contrastSupported
      ? round((Math.max(luminance(foreground), luminance(background)) + 0.05) /
        (Math.min(luminance(foreground), luminance(background)) + 0.05)) : null;
    if (!resolved.info.contrastSupported) {
      resolved.info.status = "unsupported";
      resolved.info.reason = reasons[0] || (!foreground ? "foreground_not_solid_rgb" : "background_not_solid_rgb");
      if (reasons.length) resolved.info.unsupported = [...new Set(reasons)];
    }
    return resolved.info;
  };
  const addDisabled = resolved => {
    if (!resolved.element) return resolved.info;
    resolved.info.nativeDisabled = resolved.element.matches(":disabled");
    resolved.info.ariaDisabled = resolved.element.getAttribute("aria-disabled") === "true";
    resolved.info.tag = resolved.element.tagName.toLowerCase();
    resolved.info.role = resolved.element.getAttribute("role");
    return resolved.info;
  };
  const hitTarget = element => {
    const tag = element ? element.tagName.toLowerCase() : null;
    return element ? {tag, role: element.getAttribute("role")} : null;
  };
  const addHits = resolved => {
    if (!resolved.element) return resolved.info;
    if (!resolved.info.visible) {
      resolved.info.inViewport = false;
      resolved.info.hitSamples = [];
      return resolved.info;
    }
    const bounds = resolved.info.box;
    const points = [];
    for (const dx of [0.15, 0.5, 0.85]) for (const dy of [0.2, 0.5, 0.8]) {
      points.push({x: round(bounds.x + dx * bounds.width), y: round(bounds.y + dy * bounds.height)});
    }
    const inViewport = points.every(point => point.x >= 0 && point.y >= 0 && point.x < innerWidth && point.y < innerHeight);
    resolved.info.inViewport = inViewport;
    if (!inViewport) {
      resolved.info.hitSamples = [];
      resolved.info.reason = "offscreen_hit_points";
      return resolved.info;
    }
    resolved.info.hitSamples = points.map(point => {
      const hit = document.elementFromPoint(point.x, point.y);
      return {
        ...point,
        targetReceivesHit: !!hit && resolved.element.contains(hit),
        topElement: hitTarget(hit)
      };
    });
    return resolved.info;
  };
  const textElement = selector => {
    const resolved = resolve(selector);
    addText(resolved);
    return addOverflow(resolved);
  };
  const geometryElement = selector => {
    const resolved = resolve(selector);
    addEffects(resolved);
    return resolved.info;
  };
  const intersection = (first, second) => {
    if (!first || !second) return null;
    const width = Math.max(0, Math.min(first.right, second.right) - Math.max(first.x, second.x));
    const height = Math.max(0, Math.min(first.bottom, second.bottom) - Math.max(first.y, second.y));
    return round(width * height);
  };
  const measure = check => {
    if (!check || typeof check.kind !== "string") return {status: "measurement_error", reason: "invalid_check"};
    if (check.kind === "horizontal_fit") {
      const width = Number(innerWidth);
      const documentWidth = Math.max(Number(document.documentElement && document.documentElement.scrollWidth) || 0,
        Number(document.body && document.body.scrollWidth) || 0);
      if (!finite(width) || !finite(documentWidth)) return {status: "measurement_error", reason: "viewport_unavailable"};
      return {status: "measured", viewportWidth: round(width), documentWidth: round(documentWidth)};
    }
    if (check.kind === "unclipped") {
      const resolved = resolve(check.selector);
      addText(resolved);
      addOverflow(resolved);
      return addEffects(resolved);
    }
    if (check.kind === "contrast") {
      const resolved = resolve(check.selector);
      return addContrast(resolved);
    }
    if (check.kind === "disabled") {
      const resolved = resolve(check.selector);
      return addDisabled(resolved);
    }
    if (check.kind === "aligned") {
      return {status: "measured", first: geometryElement(check.selector), second: geometryElement(check.other)};
    }
    if (check.kind === "unobstructed") {
      const resolved = resolve(check.selector);
      return addHits(resolved);
    }
    if (check.kind === "ellipsis") {
      const resolved = resolve(check.selector);
      addText(resolved);
      addOverflow(resolved);
      if (resolved.element) resolved.info.title = resolved.element.getAttribute("title");
      return addEffects(resolved);
    }
    if (check.kind === "decorative_overlap") {
      const subject = geometryElement(check.selector);
      const decorative = geometryElement(check.decorative);
      const content = geometryElement(check.content);
      const statuses = [subject, decorative, content];
      if (statuses.some(item => item.status !== "measured")) {
        return {status: "measurement_error", reason: statuses.find(item => item.status !== "measured").reason || "geometry_unavailable",
          subject: subject.box || null, decorative: decorative.box || null, content: content.box || null};
      }
      return {
        status: "measured",
        visible: true,
        subject: subject.box,
        decorative: decorative.box,
        content: content.box,
        decorativeIntersectionPx2: intersection(subject.box, decorative.box),
        contentIntersectionPx2: intersection(subject.box, content.box)
      };
    }
    if (check.kind === "artwork") {
      const resolved = resolve(check.selector);
      const info = resolved.info;
      info.pixelContentInspected = false;
      return info;
    }
    if (check.kind === "contextual") {
      const resolved = resolve(check.selector);
      addText(resolved);
      if (resolved.element) {
        resolved.info.tag = resolved.element.tagName.toLowerCase();
        resolved.info.role = resolved.element.getAttribute("role");
      }
      addEffects(resolved);
      return resolved.info;
    }
    return {status: "measurement_error", reason: "unsupported_kind"};
  };
  const results = Object.fromEntries(checks.map(check => [String(check.id), measure(check)]));
  return {
    viewport: {
      width: round(Number(innerWidth)), height: round(Number(innerHeight)),
      documentWidth: round(Math.max(Number(document.documentElement && document.documentElement.scrollWidth) || 0,
        Number(document.body && document.body.scrollWidth) || 0))
    },
    checks: results,
    coverage: {geometry: true, textBounds: checks.some(check => ["unclipped", "ellipsis", "contextual"].includes(check.kind)),
      contrast: checks.some(check => check.kind === "contrast"), hitTesting: checks.some(check => check.kind === "unobstructed"),
      pixelContentInspected: false}
  };
})()
