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
  const numberStyle = (style, property) => {
    const value = Number.parseFloat(style[property]);
    return finite(value) ? value : 0;
  };
  const imageBox = (element, style, bounds) => {
    const borderLeft = numberStyle(style, "borderLeftWidth");
    const borderRight = numberStyle(style, "borderRightWidth");
    const borderTop = numberStyle(style, "borderTopWidth");
    const borderBottom = numberStyle(style, "borderBottomWidth");
    const paddingLeft = numberStyle(style, "paddingLeft");
    const paddingRight = numberStyle(style, "paddingRight");
    const paddingTop = numberStyle(style, "paddingTop");
    const paddingBottom = numberStyle(style, "paddingBottom");
    const width = bounds.width - borderLeft - borderRight - paddingLeft - paddingRight;
    const height = bounds.height - borderTop - borderBottom - paddingTop - paddingBottom;
    if (!finite(width) || !finite(height) || width <= 0 || height <= 0) return null;
    return rect({
      x: bounds.x + borderLeft + paddingLeft,
      y: bounds.y + borderTop + paddingTop,
      width, height, right: bounds.x + borderLeft + paddingLeft + width,
      bottom: bounds.y + borderTop + paddingTop + height
    });
  };
  const clientBox = (element, style, bounds) => {
    const borderLeft = numberStyle(style, "borderLeftWidth");
    const borderTop = numberStyle(style, "borderTopWidth");
    const clientLeft = Number(element.clientLeft);
    const clientTop = Number(element.clientTop);
    const width = Number(element.clientWidth);
    const height = Number(element.clientHeight);
    if (!finite(width) || !finite(height) || width <= 0 || height <= 0) return null;
    const left = finite(clientLeft) ? clientLeft : borderLeft;
    const top = finite(clientTop) ? clientTop : borderTop;
    return rect({x: bounds.x + left, y: bounds.y + top, width, height,
      right: bounds.x + left + width, bottom: bounds.y + top + height});
  };
  const makeBox = (x, y, width, height) => {
    if (![x, y, width, height].every(finite) || width <= 0 || height <= 0) return null;
    return rect({x, y, width, height, right: x + width, bottom: y + height});
  };
  const intersectBox = (first, second) => {
    if (!first || !second) return null;
    const x = Math.max(first.x, second.x);
    const y = Math.max(first.y, second.y);
    const right = Math.min(first.right, second.right);
    const bottom = Math.min(first.bottom, second.bottom);
    return makeBox(x, y, right - x, bottom - y);
  };
  const positionTerm = (value, axis) => {
    const text = String(value).toLowerCase();
    const keyword = {
      x: {left: 0, center: 0.5, right: 1},
      y: {top: 0, center: 0.5, bottom: 1}
    }[axis];
    if (Object.prototype.hasOwnProperty.call(keyword, text)) return {percent: keyword[text], pixels: 0};
    const match = /^([+-]?(?:\d+\.?\d*|\.\d+))(px|%)$/.exec(text);
    if (!match) return null;
    const number = Number(match[1]);
    if (!finite(number)) return null;
    return match[2] === "%" ? {percent: number / 100, pixels: 0} : {percent: 0, pixels: number};
  };
  const objectPosition = (value, paintedWidth, paintedHeight, contentWidth, contentHeight) => {
    if (typeof value !== "string") return null;
    const parts = value.trim().split(/\s+/);
    if (parts.length !== 2) return null;
    const x = positionTerm(parts[0], "x");
    const y = positionTerm(parts[1], "y");
    if (!x || !y) return null;
    const left = (contentWidth - paintedWidth) * x.percent + x.pixels;
    const top = (contentHeight - paintedHeight) * y.percent + y.pixels;
    return finite(left) && finite(top) ? {left, top} : null;
  };
  const clippedAxes = value => ["hidden", "clip", "auto", "scroll"].includes(value);
  const imageUnsupported = element => {
    const reasons = [];
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (Number(style.opacity) !== 1) reasons.push("ancestor_opacity");
      if (style.filter && style.filter !== "none") reasons.push("ancestor_filter");
      if (style.transform && style.transform !== "none") reasons.push("ancestor_transform");
      if (style.rotate && style.rotate !== "none" && style.rotate !== "0deg") reasons.push("ancestor_rotate");
      if (style.scale && style.scale !== "none" && style.scale !== "1") reasons.push("ancestor_scale");
      if (style.translate && style.translate !== "none" && style.translate !== "0px") reasons.push("ancestor_translate");
      if (style.clipPath && style.clipPath !== "none") reasons.push("ancestor_clip_path");
      if ((style.mask && style.mask !== "none") || (style.maskImage && style.maskImage !== "none")) reasons.push("ancestor_mask");
      if ((node === document.body || node === document.documentElement) &&
          (style.overflowX === "hidden" || style.overflowX === "clip" ||
           style.overflowY === "hidden" || style.overflowY === "clip")) {
        reasons.push("root_overflow_geometry");
      }
      if (style.overflowX === "clip" || style.overflowY === "clip") {
        const clipMargin = String(style.overflowClipMargin || "0px").trim();
        if (clipMargin !== "0px" && !(node === element && clipMargin === "content-box")) {
          reasons.push("overflow_clip_margin");
        }
      }
      if (style.borderRadius && style.borderRadius !== "0px" &&
          (node === element || clippedAxes(style.overflowX) || clippedAxes(style.overflowY))) {
        reasons.push("ancestor_rounded_clipping");
      }
      if (style.zoom && style.zoom !== "1" && style.zoom !== "normal") reasons.push("ancestor_zoom");
      if (style.contain && style.contain !== "none" && /(?:^|\s)(?:paint|strict|content)(?:\s|$)/.test(style.contain)) {
        reasons.push("ancestor_paint_containment");
      }
      if (["absolute", "fixed", "sticky"].includes(style.position)) reasons.push("complex_positioning");
    }
    return [...new Set(reasons)];
  };
  const imageAncestorClips = (element, initial) => {
    let visibleBox = initial;
    for (let node = element.parentElement; node; node = node.parentElement) {
      // Body and html scrolling moves the page; it does not crop the image source.
      const style = getComputedStyle(node);
      if ((node === document.body || node === document.documentElement) &&
          !["hidden", "clip"].some(value => style.overflowX === value || style.overflowY === value)) continue;
      if (!clippedAxes(style.overflowX) && !clippedAxes(style.overflowY)) continue;
      const bounds = rect(node.getBoundingClientRect());
      const clip = bounds && clientBox(node, style, bounds);
      if (!clip) return {visibleBox: null, reason: "invalid_ancestor_clip_geometry"};
      if (clippedAxes(style.overflowX)) {
        visibleBox = intersectBox(visibleBox, {x: clip.x, y: -1e9, width: clip.width, height: 2e9,
          right: clip.right, bottom: 1e9});
      }
      if (clippedAxes(style.overflowY)) {
        visibleBox = intersectBox(visibleBox, {x: -1e9, y: clip.y, width: 2e9, height: clip.height,
          right: 1e9, bottom: clip.bottom});
      }
      if (!visibleBox) break;
    }
    return {visibleBox};
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
  const imageMeasurement = check => {
    const resolved = resolve(check.selector);
    const info = resolved.info;
    const image = resolved.element;
    if (!image) return info;
    if (image.tagName.toLowerCase() !== "img") {
      info.status = "measurement_error";
      info.reason = "image_element_required";
      return info;
    }
    if (info.status !== "measured") return info;
    const naturalWidth = Number(image.naturalWidth);
    const naturalHeight = Number(image.naturalHeight);
    if (!finite(naturalWidth) || !finite(naturalHeight) || naturalWidth <= 0 || naturalHeight <= 0 || image.complete !== true) {
      info.status = "measurement_error";
      info.reason = "image_not_loaded";
      return info;
    }
    const unsupported = imageUnsupported(image);
    if (unsupported.length) {
      info.status = "unsupported";
      info.reason = "unsupported_image_effect";
      info.unsupported = unsupported;
      return info;
    }
    const content = imageBox(image, resolved.style, info.box);
    if (!content) {
      info.status = "measurement_error";
      info.reason = "invalid_image_content_geometry";
      return info;
    }
    const fit = resolved.style.objectFit || "fill";
    if (!["fill", "contain", "cover", "none", "scale-down"].includes(fit)) {
      info.status = "unsupported";
      info.reason = "unsupported_object_fit";
      return info;
    }
    const containScale = Math.min(content.width / naturalWidth, content.height / naturalHeight);
    let scale = 1;
    if (fit === "contain") scale = containScale;
    if (fit === "cover") scale = Math.max(content.width / naturalWidth, content.height / naturalHeight);
    if (fit === "scale-down") scale = Math.min(1, containScale);
    const paintedWidth = fit === "fill" ? content.width : naturalWidth * scale;
    const paintedHeight = fit === "fill" ? content.height : naturalHeight * scale;
    if (![scale, paintedWidth, paintedHeight].every(value => finite(value) && value > 0)) {
      info.status = "measurement_error";
      info.reason = "invalid_image_paint_geometry";
      return info;
    }
    const position = objectPosition(resolved.style.objectPosition, paintedWidth, paintedHeight,
      content.width, content.height);
    if (!position) {
      info.status = "unsupported";
      info.reason = "unsupported_object_position";
      return info;
    }
    const painted = makeBox(content.x + position.left, content.y + position.top, paintedWidth, paintedHeight);
    let visibleBox = intersectBox(painted, content);
    if (!painted || !visibleBox) {
      info.status = "measurement_error";
      info.reason = "image_not_visible";
      return info;
    }
    const clipped = imageAncestorClips(image, visibleBox);
    visibleBox = clipped.visibleBox;
    if (!visibleBox) {
      info.status = "measurement_error";
      info.reason = "image_not_visible";
      return info;
    }
    let containerBox = null;
    let containerInnerBox = null;
    if (check.kind === "image_contained") {
      const containerResolved = resolve(check.container);
      if (!containerResolved.element || containerResolved.info.status !== "measured" ||
          containerResolved.element === image || !containerResolved.element.contains(image)) {
        info.status = "measurement_error";
        info.reason = "invalid_image_container";
        return info;
      }
      containerBox = containerResolved.info.box;
      containerInnerBox = clientBox(containerResolved.element, containerResolved.style, containerBox);
      if (!containerInnerBox) {
        info.status = "measurement_error";
        info.reason = "invalid_image_container_geometry";
        return info;
      }
      info.containerBox = containerBox;
      info.containerInnerBox = containerInnerBox;
      info.containerIsAncestor = true;
    }
    const sourceBox = makeBox(0, 0, naturalWidth, naturalHeight);
    const scaleX = paintedWidth / naturalWidth;
    const scaleY = paintedHeight / naturalHeight;
    const sourceLeft = Math.max(0, Math.min(naturalWidth, (visibleBox.x - painted.x) / scaleX));
    const sourceTop = Math.max(0, Math.min(naturalHeight, (visibleBox.y - painted.y) / scaleY));
    const sourceRight = Math.max(sourceLeft, Math.min(naturalWidth, (visibleBox.right - painted.x) / scaleX));
    const sourceBottom = Math.max(sourceTop, Math.min(naturalHeight, (visibleBox.bottom - painted.y) / scaleY));
    const visibleSourceBox = makeBox(sourceLeft, sourceTop, sourceRight - sourceLeft, sourceBottom - sourceTop);
    const sourceClipPx = Math.max(
      Math.abs(visibleBox.x - painted.x), Math.abs(visibleBox.y - painted.y),
      Math.abs(visibleBox.right - painted.right), Math.abs(visibleBox.bottom - painted.bottom)
    );
    info.tag = "img";
    info.naturalWidth = round(naturalWidth);
    info.naturalHeight = round(naturalHeight);
    info.contentBox = content;
    info.sourceBox = sourceBox;
    info.paintedBox = painted;
    info.visibleBox = visibleBox;
    info.visibleSourceBox = visibleSourceBox;
    info.objectFit = fit;
    info.objectPosition = resolved.style.objectPosition;
    info.sourceClipPx = round(sourceClipPx);
    info.sourceClipped = sourceClipPx > 0.01;
    return info;
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
    if (check.kind === "image_contained" || check.kind === "image_crop") {
      return imageMeasurement(check);
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
