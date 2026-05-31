// ── SETTINGS FRAGMENTS ─────────────────────────────────────────────────────
(function () {
  'use strict';

  const fragments = [
    {slotId:'settings-tab-api-keys-slot', viewId:'stab-api-keys', url:'/views/settings/api-keys.html'},
    {slotId:'settings-tab-model-slot', viewId:'stab-model', url:'/views/settings/model.html'},
    {slotId:'settings-tab-rag-provider-slot', viewId:'stab-rag-provider', url:'/views/settings/rag-provider.html'},
    {slotId:'settings-tab-rag-slot', viewId:'stab-rag', url:'/views/settings/rag.html'},
    {slotId:'settings-tab-chat-slot', viewId:'stab-chat', url:'/views/settings/chat.html'},
    {slotId:'settings-tab-documents-slot', viewId:'stab-documents', url:'/views/settings/documents.html'},
    {slotId:'settings-tab-workspaces-slot', viewId:'stab-workspaces', url:'/views/settings/workspaces.html'},
    {slotId:'settings-tab-matters-slot', viewId:'stab-matters', url:'/views/settings/matters.html'},
    {slotId:'settings-tab-appearance-slot', viewId:'stab-appearance', url:'/views/settings/appearance.html'},
    {slotId:'settings-tab-users-slot', viewId:'stab-users', url:'/views/settings/users.html'},
    {slotId:'settings-tab-activity-slot', viewId:'stab-activity', url:'/views/settings/activity.html'},
  ];

  async function loadFragment(fragment) {
    const slot = document.getElementById(fragment.slotId);
    if (!slot || document.getElementById(fragment.viewId)) return;
    const response = await fetch(fragment.url);
    if (!response.ok) throw new Error(`${fragment.url} failed to load`);
    slot.outerHTML = await response.text();
  }

  window.loadSettingsFragments = () => Promise.all(fragments.map(loadFragment));
})();
