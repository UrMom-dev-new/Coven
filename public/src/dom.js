export const $ = (id) => document.getElementById(id);

export function clear(node) {
  node.replaceChildren();
}

export function node(tag, options = {}, children = []) {
  const element = document.createElement(tag);
  if (options.className) element.className = options.className;
  if (options.text !== undefined) element.textContent = String(options.text);
  if (options.type) element.type = options.type;
  if (options.href) element.href = options.href;
  if (options.title) element.title = options.title;
  if (options.ariaLabel) element.setAttribute("aria-label", options.ariaLabel);
  if (options.hidden !== undefined) element.hidden = Boolean(options.hidden);
  if (options.dataset) {
    Object.entries(options.dataset).forEach(([key, value]) => {
      element.dataset[key] = String(value);
    });
  }
  if (options.attrs) {
    Object.entries(options.attrs).forEach(([key, value]) => {
      if (value !== undefined && value !== null) element.setAttribute(key, String(value));
    });
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child === null || child === undefined) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

export function field(label, value) {
  return node("div", {}, [node("dt", { text: label }), node("dd", { text: value || "" })]);
}

export function restoreFocus(id) {
  if (!id) return;
  const target = document.getElementById(id);
  if (target && typeof target.focus === "function") {
    target.focus({ preventScroll: true });
  }
}
