(function () {
  'use strict';

  function splitDeclarations(styleText) {
    const declarations = [];
    let current = '';
    let quote = '';
    let depth = 0;
    let escapeNext = false;
    for (const ch of styleText || '') {
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
      if (ch === ';' && depth === 0) {
        if (current.trim()) declarations.push(current.trim());
        current = '';
        continue;
      }
      current += ch;
    }
    if (current.trim()) declarations.push(current.trim());
    return declarations;
  }

  function splitProperty(declaration) {
    let quote = '';
    let depth = 0;
    for (let index = 0; index < declaration.length; index += 1) {
      const ch = declaration[index];
      if (quote) {
        if (ch === quote && declaration[index - 1] !== '\\') quote = '';
        continue;
      }
      if (ch === '"' || ch === "'") {
        quote = ch;
        continue;
      }
      if (ch === '(') depth += 1;
      if (ch === ')' && depth > 0) depth -= 1;
      if (ch === ':' && depth === 0) {
        return [declaration.slice(0, index).trim(), declaration.slice(index + 1).trim()];
      }
    }
    return ['', ''];
  }

  function applyStyleText(element, styleText) {
    splitDeclarations(styleText).forEach((declaration) => {
      const [property, rawValue] = splitProperty(declaration);
      if (!property || !rawValue) return;
      const important = /\s*!important\s*$/i.test(rawValue);
      const value = rawValue.replace(/\s*!important\s*$/i, '').trim();
      element.style.setProperty(property, value, important ? 'important' : '');
    });
  }

  function normalizeElement(element) {
    if (!element || element.nodeType !== 1) return;
    const styleText = element.getAttribute('data-csp-style') || element.getAttribute('style') || '';
    if (!styleText) return;
    if (element.hasAttribute('style')) element.removeAttribute('style');
    applyStyleText(element, styleText);
  }

  function normalizeTree(root) {
    normalizeElement(root);
    if (!root.querySelectorAll) return;
    root.querySelectorAll('[data-csp-style],[style]').forEach(normalizeElement);
  }

  normalizeTree(document.documentElement);
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => normalizeTree(node));
    });
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  document.addEventListener('DOMContentLoaded', () => normalizeTree(document.documentElement));
})();
