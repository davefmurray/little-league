// Just enough DOM to run web/app.js in Node: an HTML parser for index.html and
// the editor's templates, simple selectors, bubbling events and <dialog>.
// Listener return values are collected so a test can await the async flow a
// click or file choice started.

const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
const decode = (s) => s.replace(/&(#x[\da-f]+|#\d+|\w+);/gi, (m, e) => {
  if (e[0] !== '#') return ENTITIES[e] ?? m;
  return String.fromCodePoint(e[1] === 'x' ? parseInt(e.slice(2), 16) : Number(e.slice(1)));
});
const kebab = (key) => key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

class EventHost {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
}

class Text {
  constructor(data) {
    this.nodeType = 3;
    this.data = data;
    this.parentNode = null;
  }

  get textContent() {
    return this.data;
  }
}

class Element extends EventHost {
  constructor(document, tag) {
    super();
    this.nodeType = 1;
    this.ownerDocument = document;
    this.localName = tag.toLowerCase();
    this.tagName = this.localName.toUpperCase();
    this.attributes = new Map();
    this.childNodes = [];
    this.parentNode = null;
    this.style = {};
    this.files = null;
    this.currentValue = null;
  }

  get children() { return this.childNodes.filter((n) => n.nodeType === 1); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  hasAttribute(name) { return this.attributes.has(name); }
  flag(name, on) { if (on) this.setAttribute(name, ''); else this.removeAttribute(name); }

  get id() { return this.getAttribute('id') ?? ''; }
  get hidden() { return this.hasAttribute('hidden'); }
  set hidden(on) { this.flag('hidden', on); }
  get disabled() { return this.hasAttribute('disabled'); }
  set disabled(on) { this.flag('disabled', on); }
  get open() { return this.hasAttribute('open'); }
  set open(on) { this.flag('open', on); }
  get type() { return this.getAttribute('type') ?? (this.localName === 'input' ? 'text' : ''); }
  get value() { return this.currentValue ?? this.getAttribute('value') ?? ''; }
  set value(v) { this.currentValue = String(v); }
  get maxLength() { return Number(this.getAttribute('maxlength') ?? -1); }
  set maxLength(v) { this.setAttribute('maxlength', v); }
  get title() { return this.getAttribute('title') ?? ''; }
  set title(v) { this.setAttribute('title', v); }
  get href() { return this.getAttribute('href') ?? ''; }
  set href(v) { this.setAttribute('href', v); }
  get download() { return this.getAttribute('download') ?? ''; }
  set download(v) { this.setAttribute('download', v); }
  get className() { return this.getAttribute('class') ?? ''; }
  set className(v) { this.setAttribute('class', v); }

  get classList() {
    const names = () => this.className.split(/\s+/).filter(Boolean);
    const set = (list) => { this.className = list.join(' '); };
    return {
      contains: (c) => names().includes(c),
      toggle: (c, force) => {
        const on = force ?? !names().includes(c);
        set(on ? [...new Set([...names(), c])] : names().filter((n) => n !== c));
        return on;
      },
    };
  }

  get dataset() {
    return new Proxy({}, {
      get: (_, key) => (typeof key === 'string' ? this.getAttribute(`data-${kebab(key)}`) ?? undefined : undefined),
      set: (_, key, value) => { this.setAttribute(`data-${kebab(key)}`, value); return true; },
    });
  }

  get textContent() { return this.childNodes.map((n) => n.textContent).join(''); }
  set textContent(v) {
    this.childNodes = [];
    if (v !== '') this.appendChild(new Text(String(v)));
  }
  set innerHTML(html) {
    this.childNodes = [];
    for (const node of parse(this.ownerDocument, html)) this.appendChild(node);
  }

  appendChild(node) {
    if (node.parentNode) node.parentNode.childNodes = node.parentNode.childNodes.filter((n) => n !== node);
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.childNodes = this.parentNode.childNodes.filter((n) => n !== this);
    this.parentNode = null;
  }

  get nextElementSibling() {
    const siblings = this.parentNode?.children ?? [];
    return siblings[siblings.indexOf(this) + 1] ?? null;
  }

  closest(selector) {
    const compounds = parseSelector(selector);
    for (let el = this; el?.nodeType === 1; el = el.parentNode) if (matches(el, compounds)) return el;
    return null;
  }
  querySelectorAll(selector) {
    const compounds = parseSelector(selector);
    return descendants(this).filter((el) => matches(el, compounds));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }

  dispatchEvent(event) { return this.ownerDocument.dispatch(this, event); }
  click() {
    if (this.disabled) return Promise.resolve([]);
    if (this.localName === 'a' && this.download) this.ownerDocument.downloads.push({ filename: this.download, href: this.href });
    return this.dispatchEvent(event('click'));
  }
  focus() { this.ownerDocument.activeElement = this; }
  /** A 2D context that keeps the last image put on a <canvas>. */
  getContext(type) {
    if (this.localName !== 'canvas' || type !== '2d') return null;
    this.context ??= {
      image: null,
      createImageData: (width, height) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) }),
      putImageData(image) { this.image = image; },
    };
    return this.context;
  }
  showModal() {
    if (this.open) throw new Error('showModal on an open dialog');
    this.open = true;
    this.querySelector('[autofocus]')?.focus();
  }
  close() {
    if (!this.open) return;
    this.open = false;
    setImmediate(() => this.dispatchEvent(event('close', { bubbles: false })));
  }
}

function descendants(root) {
  const out = [];
  for (const child of root.children) out.push(child, ...descendants(child));
  return out;
}

const TOKEN = /<!--[\s\S]*?-->|<!doctype[^>]*>|<\/([a-z][\w-]*)\s*>|<([a-z][\w-]*)((?:\s+[^\s"'>/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?)*)\s*(\/?)>|([^<]+)/gi;
const ATTR = /([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;

function parse(document, html) {
  const root = new Element(document, 'template');
  const stack = [root];
  for (const m of html.matchAll(TOKEN)) {
    const top = stack[stack.length - 1];
    if (m[5] !== undefined) {
      top.appendChild(new Text(decode(m[5])));
    } else if (m[1]) {
      const i = stack.findLastIndex((el) => el.localName === m[1].toLowerCase());
      if (i > 0) stack.length = i;
    } else if (m[2]) {
      const el = new Element(document, m[2]);
      for (const a of (m[3] ?? '').matchAll(ATTR)) el.setAttribute(a[1].toLowerCase(), decode(a[2] ?? a[3] ?? a[4] ?? ''));
      top.appendChild(el);
      if (!VOID.has(el.localName) && !m[4]) stack.push(el);
    }
  }
  const nodes = [...root.childNodes];
  for (const node of nodes) node.parentNode = null;
  return nodes;
}

function splitSelector(selector) {
  const parts = [];
  let current = '';
  let depth = 0;
  for (const ch of selector.trim()) {
    if (ch === '[') depth += 1;
    if (ch === ']') depth -= 1;
    if (/\s/.test(ch) && depth === 0) {
      if (current) parts.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  if (current) parts.push(current);
  return parts;
}

function parseCompound(text) {
  const compound = { tag: null, id: null, classes: [], attrs: [] };
  const re = /^[a-z][\w-]*|#[\w-]+|\.[\w-]+|\[([\w-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]"']*)))?\]/gi;
  let pos = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index !== pos) break;
    pos = re.lastIndex;
    if (m[0][0] === '#') compound.id = m[0].slice(1);
    else if (m[0][0] === '.') compound.classes.push(m[0].slice(1));
    else if (m[0][0] === '[') compound.attrs.push([m[1], m[2] ?? m[3] ?? m[4]]);
    else compound.tag = m[0].toLowerCase();
  }
  if (pos !== text.length) throw new Error(`Unsupported selector: ${text}`);
  return compound;
}

const parseSelector = (selector) => splitSelector(selector).map(parseCompound);

function matchCompound(el, c) {
  return (!c.tag || el.localName === c.tag) &&
    (!c.id || el.id === c.id) &&
    c.classes.every((name) => el.classList.contains(name)) &&
    c.attrs.every(([name, value]) => (value === undefined ? el.hasAttribute(name) : el.getAttribute(name) === value));
}

function matches(el, compounds) {
  if (!matchCompound(el, compounds[compounds.length - 1])) return false;
  let node = el.parentNode;
  for (let i = compounds.length - 2; i >= 0; i--) {
    while (node?.nodeType === 1 && !matchCompound(node, compounds[i])) node = node.parentNode;
    if (node?.nodeType !== 1) return false;
    node = node.parentNode;
  }
  return true;
}

export function event(type, init = {}) {
  return {
    type,
    bubbles: true,
    defaultPrevented: false,
    stopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.stopped = true; },
    ...init,
  };
}

class Document extends EventHost {
  constructor(window) {
    super();
    this.window = window;
    this.downloads = [];
    this.documentElement = new Element(this, 'html');
    this.body = this.documentElement.appendChild(new Element(this, 'body'));
    this.activeElement = this.body;
  }

  createElement(tag) { return new Element(this, tag); }
  getElementById(id) { return descendants(this.documentElement).find((el) => el.id === id) ?? null; }
  querySelector(selector) { return this.documentElement.querySelector(selector); }
  querySelectorAll(selector) { return this.documentElement.querySelectorAll(selector); }

  /** Bubble `ev` from `target`; resolves when every async listener it started settles. */
  dispatch(target, ev) {
    ev.target = target;
    const path = [target];
    if (ev.bubbles) {
      for (let node = target.parentNode; node; node = node.parentNode) path.push(node);
      path.push(this, this.window);
    }
    const results = [];
    for (const node of path) {
      ev.currentTarget = node;
      for (const fn of node.listeners.get(ev.type) ?? []) results.push(fn.call(node, ev));
      if (ev.stopped) break;
    }
    return Promise.all(results);
  }
}

/** Build a document from a full HTML page. */
export function createDom(html) {
  const window = new EventHost();
  const document = new Document(window);
  window.document = document;
  const body = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  document.body.innerHTML = body ? body[1] : html;
  return { window, document };
}
