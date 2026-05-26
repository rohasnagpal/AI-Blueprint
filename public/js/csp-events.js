(function () {
  'use strict';

  const EVENT_ATTRS = {
    click: 'onclick',
    change: 'onchange',
    focus: 'onfocus',
    input: 'oninput',
    keydown: 'onkeydown',
  };

  const DATA_ATTRS = {
    onclick: 'data-csp-onclick',
    onchange: 'data-csp-onchange',
    onfocus: 'data-csp-onfocus',
    oninput: 'data-csp-oninput',
    onkeydown: 'data-csp-onkeydown',
  };

  const ATTR_EVENTS = Object.fromEntries(Object.entries(EVENT_ATTRS).map(([eventName, attr]) => [attr, eventName]));

  function splitTopLevel(value, separator) {
    const parts = [];
    let current = '';
    let quote = '';
    let depth = 0;
    let escapeNext = false;
    for (const ch of value) {
      if (escapeNext) {
        current += ch;
        escapeNext = false;
        continue;
      }
      if (ch === '\\') {
        current += ch;
        escapeNext = true;
        continue;
      }
      if (quote) {
        current += ch;
        if (ch === quote) quote = '';
        continue;
      }
      if (ch === '"' || ch === "'") {
        current += ch;
        quote = ch;
        continue;
      }
      if (ch === '(') depth += 1;
      if (ch === ')' && depth > 0) depth -= 1;
      if (ch === separator && depth === 0) {
        if (current.trim()) parts.push(current.trim());
        current = '';
        continue;
      }
      current += ch;
    }
    if (current.trim()) parts.push(current.trim());
    return parts;
  }

  function unquote(value) {
    return value.slice(1, -1).replace(/\\(['"\\])/g, '$1');
  }

  function resolveExpression(token, element, event) {
    const value = token.trim();
    if (!value) return undefined;
    if (value === 'event') return event;
    if (value === 'this') return element;
    if (value === 'this.value') return element.value;
    if (value === 'true') return true;
    if (value === 'false') return false;
    if (value === 'null') return null;
    if ((value.startsWith("'") && value.endsWith("'")) || (value.startsWith('"') && value.endsWith('"'))) {
      return unquote(value);
    }
    if (/^-?\d+(\.\d+)?$/.test(value)) return Number(value);
    const fixedMatch = value.match(/^\(this\.value\/100\)\.toFixed\((\d+)\)$/);
    if (fixedMatch) return (Number(element.value) / 100).toFixed(Number(fixedMatch[1]));
    return value;
  }

  function parseArgs(args, element, event) {
    if (!args.trim()) return [];
    return splitTopLevel(args, ',').map((arg) => resolveExpression(arg, element, event));
  }

  function runStatement(statement, element, event) {
    const code = statement.trim();
    if (!code) return;

    if (code === 'event.stopPropagation()') {
      event.stopPropagation();
      return;
    }
    if (code === 'event.preventDefault()') {
      event.preventDefault();
      return;
    }

    let match = code.match(/^this\.removeAttribute\((.*)\)$/);
    if (match) {
      element.removeAttribute(resolveExpression(match[1], element, event));
      return;
    }

    match = code.match(/^this\.classList\.(toggle|add|remove)\((.*)\)$/);
    if (match) {
      element.classList[match[1]](...parseArgs(match[2], element, event));
      return;
    }

    match = code.match(/^document\.getElementById\((.*)\)\.click\(\)$/);
    if (match) {
      const target = document.getElementById(resolveExpression(match[1], element, event));
      if (target) target.click();
      return;
    }

    match = code.match(/^this\.nextElementSibling\.textContent\s*=\s*(.+)$/);
    if (match && element.nextElementSibling) {
      element.nextElementSibling.textContent = resolveExpression(match[1], element, event);
      return;
    }

    match = code.match(/^([A-Za-z_$][\w$]*)\((.*)\)$/);
    if (match && typeof window[match[1]] === 'function') {
      window[match[1]](...parseArgs(match[2], element, event));
    }
  }

  function runHandler(code, element, event) {
    splitTopLevel(code || '', ';').forEach((statement) => runStatement(statement, element, event));
  }

  function normalizeElement(element) {
    if (!element || element.nodeType !== 1) return;
    Object.values(EVENT_ATTRS).forEach((attr) => {
      if (!element.hasAttribute(attr)) return;
      const dataAttr = DATA_ATTRS[attr];
      if (!element.hasAttribute(dataAttr)) element.setAttribute(dataAttr, element.getAttribute(attr));
      element.removeAttribute(attr);
      const boundAttr = `data-csp-bound-${ATTR_EVENTS[attr]}`;
      if (element.hasAttribute(boundAttr)) return;
      element.setAttribute(boundAttr, 'true');
      element.addEventListener(ATTR_EVENTS[attr], (event) => {
        runHandler(element.getAttribute(dataAttr), element, event);
        if (event.cancelBubble) event.stopImmediatePropagation();
      });
    });
  }

  function normalizeTree(root) {
    normalizeElement(root);
    if (!root.querySelectorAll) return;
    root.querySelectorAll('[onclick],[onchange],[onfocus],[oninput],[onkeydown]').forEach(normalizeElement);
  }

  document.addEventListener('DOMContentLoaded', () => {
    normalizeTree(document.documentElement);
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => normalizeTree(node));
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  });
})();
