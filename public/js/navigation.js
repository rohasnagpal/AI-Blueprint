(function () {
  'use strict';

  const primaryNavItems = [
    {view:'chat', label:'New Chat', navId:'nav-chat', icon:'chat'},
    {view:'personas', label:'Personas', navId:'nav-personas', icon:'personas'},
    {view:'settings', label:'Settings', navId:'nav-settings', icon:'settings'},
  ];

  const moreNavItems = [
    {view:'add-doc', label:'Add Document', navId:'more-add-doc', icon:'upload'},
    {view:'view-docs', label:'View Documents', navId:'more-view-docs', icon:'documents', badge:'docs-count-badge'},
    {view:'translate', label:'Translate', navId:'more-translate', icon:'translate'},
    {view:'contract-review', label:'Contract Review', navId:'more-contract-review', icon:'review'},
    {view:'draft', label:'Draft', navId:'more-draft', icon:'draft'},
    {view:'email', label:'Email', navId:'more-email', icon:'email'},
    {view:'admin-users', label:'Admin Users', navId:'nav-admin-users', icon:'users', hidden:true},
  ];

  const viewFragments = [
    {
      slotId:'chat-view-slot',
      viewId:'view-chat',
      url:'/views/chat.html',
      fallbackHtml:'<div class="view active" id="view-chat"><div class="chat-messages" id="chat-messages"><div class="welcome" id="welcome-screen"><h2>AI Blueprint</h2><p>Refresh the page and try again.</p></div><div class="msg-group" id="chat-conversation"></div></div></div>',
    },
    {
      slotId:'personas-view-slot',
      viewId:'view-personas',
      url:'/views/personas.html',
      fallbackHtml:'<div class="view" id="view-personas"><div class="add-doc-view"><div class="view-header"><h2>Personas</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'settings-view-slot',
      viewId:'view-settings',
      url:'/views/settings.html',
      fallbackHtml:'<div class="view" id="view-settings"><div class="settings-layout"><div class="settings-content"><div class="settings-section active"><div class="settings-section-title">Settings unavailable</div><div class="settings-section-desc">Refresh the page and try again.</div></div></div></div></div>',
    },
    {
      slotId:'add-document-view-slot',
      viewId:'view-add-doc',
      url:'/views/add-document.html',
      fallbackHtml:'<div class="view" id="view-add-doc"><div class="add-doc-view"><div class="view-header"><h2>Add Documents</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'documents-view-slot',
      viewId:'view-view-docs',
      url:'/views/documents.html',
      fallbackHtml:'<div class="view" id="view-view-docs"><div class="view-docs-area"><div class="view-header"><h2>Your Documents</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'email-view-slot',
      viewId:'view-email',
      url:'/views/email.html',
      fallbackHtml:'<div class="view" id="view-email"><div class="add-doc-view"><div class="view-header"><h2>Email</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'translate-view-slot',
      viewId:'view-translate',
      url:'/views/translate.html',
      fallbackHtml:'<div class="view" id="view-translate"><div class="add-doc-view"><div class="view-header"><h2>Translate</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'contract-review-view-slot',
      viewId:'view-contract-review',
      url:'/views/contract-review.html',
      fallbackHtml:'<div class="view" id="view-contract-review"><div class="add-doc-view"><div class="view-header"><h2>Contract Review</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'draft-view-slot',
      viewId:'view-draft',
      url:'/views/draft.html',
      fallbackHtml:'<div class="view" id="view-draft"><div class="add-doc-view"><div class="view-header"><h2>Draft</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'global-modals-slot',
      viewId:'persona-detail-modal',
      url:'/views/modals.html',
      fallbackHtml:'',
    },
  ];

  const navItems = [...primaryNavItems, ...moreNavItems];
  const viewRoutes = {chat:'/chat',personas:'/personas',email:'/email','add-doc':'/documents/add',translate:'/translate','contract-review':'/contract-review',draft:'/draft','view-docs':'/documents',workspaces:'/settings/workspaces',settings:'/settings','admin-users':'/settings/users'};
  const icons = {
    chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    personas: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>',
    more: '<circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    documents: '<rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
    translate: '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
    review: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    draft: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/><path d="M15 5 19 9"/>',
    email: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  };

  function icon(name) {
    const fill = name === 'more' ? 'currentColor' : 'none';
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="${fill}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icons[name] || ''}</svg>`;
  }

  async function loadViewFragment(fragment) {
    const slot = document.getElementById(fragment.slotId);
    if (!slot || document.getElementById(fragment.viewId)) return;
    try {
      const response = await fetch(fragment.url);
      if (!response.ok) throw new Error(`${fragment.url} failed to load`);
      slot.outerHTML = await response.text();
    } catch (error) {
      slot.innerHTML = fragment.fallbackHtml || '';
    }
  }

  function renderSidebarNav(callbacks) {
    const primary = document.getElementById('primary-nav');
    const more = document.getElementById('sidebar-more-menu');
    if (!primary || !more) return;

    primary.innerHTML = primaryNavItems.map(item => `
      <div class="nav-item" id="${item.navId}" data-view="${item.view}">
        ${icon(item.icon)}
        ${item.label}
      </div>
    `).join('') + `
      <div class="nav-item" id="nav-more" data-nav-action="more">
        ${icon('more')}
        More
      </div>
    `;

    more.innerHTML = moreNavItems.map(item => `
      <button type="button" id="${item.navId}" data-view="${item.view}">
        ${icon(item.icon)}
        ${item.label}
        ${item.badge ? '<span class="nav-badge" id="' + item.badge + '">0</span>' : ''}
      </button>
    `).join('');

    primaryNavItems.forEach(item => {
      document.getElementById(item.navId)?.addEventListener('click', () => callbacks.switchView(item.view));
    });
    moreNavItems.forEach(item => {
      const button = document.getElementById(item.navId);
      if (item.hidden && button) button.style.display = 'none';
      button?.addEventListener('click', () => callbacks.switchViewFromMore(item.view));
    });
    document.getElementById('nav-more')?.addEventListener('click', callbacks.toggleSidebarMore);
  }

  window.AIBP_NAVIGATION = {
    primaryNavItems,
    moreNavItems,
    navItems,
    viewFragments,
    views: {chat:'view-chat',personas:'view-personas',email:'view-email','add-doc':'view-add-doc',translate:'view-translate','contract-review':'view-contract-review',draft:'view-draft','view-docs':'view-view-docs',workspaces:'view-settings',settings:'view-settings','admin-users':'view-settings'},
    navs: navItems.reduce((navs, item) => {
      navs[item.view] = item.navId;
      return navs;
    }, {workspaces:'nav-settings'}),
    titles: {chat:'Chat',personas:'Personas',email:'Email','add-doc':'Add Document',translate:'Translate','contract-review':'Contract Review',draft:'Draft','view-docs':'View Documents',workspaces:'Workspaces',settings:'Settings','admin-users':'Admin Users'},
    viewRoutes,
    routeViews: Object.entries(viewRoutes).reduce((routes, [view, path]) => {
      routes[path] = view;
      return routes;
    }, {'/':'chat','/admin/users':'admin-users'}),
    loadViewFragments: () => Promise.all(viewFragments.map(loadViewFragment)),
    renderSidebarNav,
  };
})();
