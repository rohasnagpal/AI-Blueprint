(function () {
  'use strict';

  const primaryNavItems = [
    {view:'chat', label:'New Chat', navId:'nav-chat', icon:'chat'},
    {view:'add-doc', label:'Add Document', navId:'more-add-doc', icon:'upload'},
    {view:'view-docs', label:'View Documents', navId:'more-view-docs', icon:'documents', badge:'docs-count-badge'},
    {group:'prep', label:'Prep', navId:'nav-prep', icon:'arbitration'},
    {group:'workflows', label:'Workflows', navId:'nav-workflows', icon:'review'},
    {view:'personas', label:'Personas', navId:'nav-personas', icon:'personas'},
    {view:'settings', label:'Settings', navId:'nav-settings', icon:'settings'},
    {view:'admin-users', label:'Admin Users', navId:'nav-admin-users', icon:'users', hidden:true},
  ];

  const menuGroups = {
    prep: [
      {view:'arbitration-prep', label:'Arbitration Prep', navId:'more-arbitration-prep', icon:'arbitration'},
      {view:'litigation-prep', label:'Litigation Prep', navId:'more-litigation-prep', icon:'litigation'},
      {view:'mediation-prep', label:'Mediation Prep', navId:'more-mediation-prep', icon:'mediation'},
      {view:'negotiation-prep', label:'Negotiation Prep', navId:'more-negotiation-prep', icon:'negotiation'},
    ],
    workflows: [
      {view:'contract-review', label:'Contract Review', navId:'more-contract-review', icon:'review'},
      {view:'draft', label:'Draft', navId:'more-draft', icon:'draft'},
      {view:'email', label:'Email', navId:'more-email', icon:'email'},
      {view:'translate', label:'Translate', navId:'more-translate', icon:'translate'},
    ],
  };

  const moreNavItems = [...menuGroups.prep, ...menuGroups.workflows];

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
      slotId:'arbitration-prep-view-slot',
      viewId:'view-arbitration-prep',
      url:'/views/arbitration-prep.html',
      fallbackHtml:'<div class="view" id="view-arbitration-prep"><div class="add-doc-view"><div class="view-header"><h2>Arbitration Prep</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'litigation-prep-view-slot',
      viewId:'view-litigation-prep',
      url:'/views/litigation-prep.html',
      fallbackHtml:'<div class="view" id="view-litigation-prep"><div class="add-doc-view"><div class="view-header"><h2>Litigation Prep</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'mediation-prep-view-slot',
      viewId:'view-mediation-prep',
      url:'/views/mediation-prep.html',
      fallbackHtml:'<div class="view" id="view-mediation-prep"><div class="add-doc-view"><div class="view-header"><h2>Mediation Prep</h2><p>Refresh the page and try again.</p></div></div></div>',
    },
    {
      slotId:'negotiation-prep-view-slot',
      viewId:'view-negotiation-prep',
      url:'/views/negotiation-prep.html',
      fallbackHtml:'<div class="view" id="view-negotiation-prep"><div class="add-doc-view"><div class="view-header"><h2>Negotiation Prep</h2><p>Refresh the page and try again.</p></div></div></div>',
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

  const navItems = [...primaryNavItems.filter(item => item.view), ...moreNavItems];
  const viewRoutes = {chat:'/chat',personas:'/personas',email:'/email','add-doc':'/documents/add',translate:'/translate','contract-review':'/contract-review','arbitration-prep':'/arbitration-prep','litigation-prep':'/litigation-prep','mediation-prep':'/mediation-prep','negotiation-prep':'/negotiation-prep',draft:'/draft','view-docs':'/documents',workspaces:'/settings/workspaces',settings:'/settings','admin-users':'/settings/users'};
  const icons = {
    chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    personas: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>',
    more: '<circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    documents: '<rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
    translate: '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
    review: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    arbitration: '<path d="M12 3v18"/><path d="M5 7h14"/><path d="M6 7l-3 6h6L6 7Z"/><path d="M18 7l-3 6h6l-3-6Z"/><path d="M8 21h8"/>',
    litigation: '<path d="M14 3h7v7"/><path d="M10 21H3v-7"/><path d="m21 3-7 7"/><path d="m3 21 7-7"/><path d="M12 8v8"/><path d="M8 12h8"/>',
    mediation: '<path d="M7 11v2a5 5 0 0 0 10 0v-2"/><path d="M5 9h4l2 2h2l2-2h4"/><path d="M12 16v5"/><path d="M8 21h8"/><path d="M6 5h12"/>',
    negotiation: '<path d="M8 12h8"/><path d="M12 8v8"/><path d="M4 8h5l2 2"/><path d="M20 16h-5l-2-2"/><path d="M5 16h4"/><path d="M15 8h4"/>',
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
      <div class="nav-item" id="${item.navId}" ${item.view ? `data-view="${item.view}"` : `data-nav-group="${item.group}"`}>
        ${icon(item.icon)}
        ${item.label}
        ${item.badge ? '<span class="nav-badge" id="' + item.badge + '">0</span>' : ''}
      </div>
    `).join('');

    function openMenuGroup(group) {
      const items = menuGroups[group] || [];
      more.innerHTML = items.map(item => `
        <button type="button" id="${item.navId}" data-view="${item.view}">
          ${icon(item.icon)}
          ${item.label}
          ${item.badge ? '<span class="nav-badge" id="' + item.badge + '">0</span>' : ''}
        </button>
      `).join('');

      items.forEach(item => {
        const button = document.getElementById(item.navId);
        button?.addEventListener('click', () => callbacks.switchViewFromMore(item.view));
      });

      document.querySelectorAll('.sidebar-more-menu button').forEach(button => button.classList.remove('active'));
      const activeView = document.querySelector('.nav-item.active')?.dataset.view || localStorage.getItem('aibp_last_view');
      if (activeView) document.getElementById('more-' + activeView)?.classList.add('active');
      more.classList.add('open');
    }

    primaryNavItems.forEach(item => {
      const navItem = document.getElementById(item.navId);
      if (item.hidden && navItem) navItem.style.display = 'none';
      if (item.view) {
        navItem?.addEventListener('click', () => {
          more.classList.remove('open');
          more.dataset.group = '';
          document.querySelectorAll('[data-nav-group]').forEach(groupItem => groupItem.classList.remove('active'));
          callbacks.switchView(item.view);
        });
      } else if (item.group) {
        navItem?.addEventListener('click', (event) => {
          event.stopPropagation();
          const isOpen = more.classList.contains('open') && more.dataset.group === item.group;
          document.querySelectorAll('[data-nav-group]').forEach(groupItem => groupItem.classList.remove('active'));
          if (isOpen) {
            more.classList.remove('open');
            more.dataset.group = '';
            return;
          }
          more.dataset.group = item.group;
          navItem.classList.add('active');
          openMenuGroup(item.group);
        });
      }
    });
  }

  window.AIBP_NAVIGATION = {
    menuGroups,
    primaryNavItems,
    moreNavItems,
    navItems,
    viewFragments,
    views: {chat:'view-chat',personas:'view-personas',email:'view-email','add-doc':'view-add-doc',translate:'view-translate','contract-review':'view-contract-review','arbitration-prep':'view-arbitration-prep','litigation-prep':'view-litigation-prep','mediation-prep':'view-mediation-prep','negotiation-prep':'view-negotiation-prep',draft:'view-draft','view-docs':'view-view-docs',workspaces:'view-settings',settings:'view-settings','admin-users':'view-settings'},
    navs: navItems.reduce((navs, item) => {
      navs[item.view] = item.navId;
      return navs;
    }, {workspaces:'nav-settings'}),
    titles: {chat:'Chat',personas:'Personas',email:'Email','add-doc':'Add Document',translate:'Translate','contract-review':'Contract Review','arbitration-prep':'Arbitration Prep','litigation-prep':'Litigation Prep','mediation-prep':'Mediation Prep','negotiation-prep':'Negotiation Prep',draft:'Draft','view-docs':'View Documents',workspaces:'Workspaces',settings:'Settings','admin-users':'Admin Users'},
    viewRoutes,
    routeViews: Object.entries(viewRoutes).reduce((routes, [view, path]) => {
      routes[path] = view;
      return routes;
    }, {'/':'chat','/admin/users':'admin-users'}),
    loadViewFragments: () => Promise.all(viewFragments.map(loadViewFragment)),
    renderSidebarNav,
  };
})();
