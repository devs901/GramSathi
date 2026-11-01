/* GramSathi web app: admin console + citizen portal. Vanilla JS, no build step. */
'use strict';

// ---------------------------------------------------------------- helpers
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const fdate = (s) => (s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');
const label = (s) => String(s || '').replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const state = { token: store.get('gs_token'), user: null, page: null, users: [] };

async function api(path, { method = 'GET', body, raw = false } = {}) {
  const res = await fetch('/api' + path, {
    method,
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(state.token ? { Authorization: 'Bearer ' + state.token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && state.user) { logout(); throw new Error('Session expired. Please sign in again.'); }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const err = new Error(data.error || 'Request failed');
    err.details = data.details;
    throw err;
  }
  return raw ? res : res.json();
}

let toastTimer;
function toast(msg, isErr = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = 'toast'), 3200);
}
const fail = (e) => toast(e.message || 'Something went wrong', true);

const badge = (status) => `<span class="badge badge-${esc(status)}">${esc(label(status))}</span>`;
const src = (s) => `<span class="src ${s === 'claude' ? '' : 'rules'}" title="${s === 'claude' ? 'Written by Claude' : 'Built-in rules (no AI key set)'}">${s === 'claude' ? 'AI' : 'Rules'}</span>`;
const empty = (icon, text, sub = '') => `<div class="empty-state"><div class="empty-icon">${icon}</div><div class="empty-text">${esc(text)}</div><div class="empty-sub">${esc(sub)}</div></div>`;

// ---------------------------------------------------------------- modal + forms
function openModal(title, bodyHtml, footerHtml = '') {
  closeModal();
  const el = document.createElement('div');
  el.className = 'modal-overlay';
  el.id = 'modal';
  el.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-header"><div class="modal-title">${esc(title)}</div><button class="modal-close" data-act="close" aria-label="Close">×</button></div><div class="modal-body">${bodyHtml}</div>${footerHtml ? `<div class="modal-footer">${footerHtml}</div>` : ''}</div>`;
  el.addEventListener('mousedown', (e) => { if (e.target === el) closeModal(); });
  document.body.appendChild(el);
  const first = el.querySelector('input,select,textarea,button.btn');
  if (first) first.focus();
  return el;
}
function closeModal() { $('#modal')?.remove(); }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

function field(f) {
  const id = 'f_' + f.name;
  const v = f.value ?? '';
  let input;
  if (f.type === 'select') input = `<select class="form-select" id="${id}" name="${f.name}" ${f.required ? 'required' : ''}>${f.options.map((o) => { const [val, text] = Array.isArray(o) ? o : [o, label(o)]; return `<option value="${esc(val)}" ${String(val) === String(v) ? 'selected' : ''}>${esc(text)}</option>`; }).join('')}</select>`;
  else if (f.type === 'textarea') input = `<textarea class="form-textarea" id="${id}" name="${f.name}" ${f.required ? 'required' : ''}>${esc(v)}</textarea>`;
  else input = `<input class="form-input" id="${id}" name="${f.name}" type="${f.type || 'text'}" value="${esc(v)}" ${f.required ? 'required' : ''} ${f.step ? `step="${f.step}"` : ''} ${f.min != null ? `min="${f.min}"` : ''}>`;
  return `<div class="form-group"><label class="form-label" for="${id}">${esc(f.label)}</label>${input}</div>`;
}

function formModal(title, fields, submitText, onSubmit, extraTop = '') {
  const half = (arr) => { const out = []; for (let i = 0; i < arr.length; i += 2) out.push(`<div class="form-row">${arr.slice(i, i + 2).map(field).join('')}</div>`); return out.join(''); };
  const wide = fields.filter((f) => f.type === 'textarea');
  const narrow = fields.filter((f) => f.type !== 'textarea');
  const m = openModal(title, `<form id="modal-form" novalidate>${extraTop}<div id="form-err"></div>${half(narrow)}${wide.map(field).join('')}</form>`,
    `<button class="btn btn-ghost" data-act="close" type="button">Cancel</button><button class="btn btn-primary" form="modal-form" type="submit">${esc(submitText)}</button>`);
  $('#modal-form', m).addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    if (!form.reportValidity()) return;
    const data = {};
    for (const f of fields) {
      const raw = form.elements[f.name].value;
      data[f.name] = f.type === 'number' ? (raw === '' ? null : Number(raw)) : f.type === 'checkbox' ? form.elements[f.name].checked : raw;
    }
    try { await onSubmit(data); closeModal(); }
    catch (err) {
      const list = (err.details || []).map((d) => `<li>${esc(d.field)}: ${esc(d.message)}</li>`).join('');
      $('#form-err').innerHTML = `<div class="form-err">${esc(err.message)}${list ? `<ul>${list}</ul>` : ''}</div>`;
    }
  });
  return m;
}

// ---------------------------------------------------------------- auth screens
function renderLogin(mode = 'login') {
  const reg = mode === 'register';
  $('#root').innerHTML = `<div class="login-page"><div class="login-card">
    <div class="login-logo"><h1>🏛️ GramSathi</h1><p>${reg ? 'Create your citizen account' : 'Village services, in one place'}</p></div>
    <div id="auth-err"></div>
    <form id="auth-form" novalidate>
      ${reg ? `<div class="form-group"><label class="form-label" for="a_name">Full name</label><input class="form-input" id="a_name" name="name" autocomplete="name" required></div>` : ''}
      <div class="form-group"><label class="form-label" for="a_email">Email</label><input class="form-input" id="a_email" name="email" type="email" autocomplete="email" required></div>
      ${reg ? `<div class="form-row"><div class="form-group"><label class="form-label" for="a_mobile">Mobile</label><input class="form-input" id="a_mobile" name="mobile" inputmode="numeric" autocomplete="tel" required></div><div class="form-group"><label class="form-label" for="a_age">Age</label><input class="form-input" id="a_age" name="age" type="number" min="1" max="120" required></div></div>
      <div class="form-group"><label class="form-label" for="a_village">Village</label><input class="form-input" id="a_village" name="village"></div>` : ''}
      <div class="form-group"><label class="form-label" for="a_pw">Password</label><input class="form-input" id="a_pw" name="password" type="password" autocomplete="${reg ? 'new-password' : 'current-password'}" required>${reg ? '<div class="muted" style="margin-top:4px">At least 8 characters, with letters and numbers.</div>' : ''}</div>
      <button class="login-submit" type="submit">${reg ? 'Create account' : 'Sign in'}</button>
    </form>
    <p style="text-align:center;margin-top:14px" class="muted">${reg ? 'Already registered?' : 'New here?'} <button class="link-btn" data-act="auth-toggle" data-mode="${reg ? 'login' : 'register'}">${reg ? 'Sign in' : 'Create an account'}</button></p>
    ${reg ? '' : `<div class="demo-row">Demo accounts (seeded data)<br><button class="btn btn-ghost btn-sm" data-act="demo" data-e="admin@gramsathi.in" data-p="Admin@1234">Admin</button><button class="btn btn-ghost btn-sm" data-act="demo" data-e="ramesh@example.com" data-p="Citizen@1234">Citizen</button></div>`}
  </div></div>`;
  $('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    if (!f.reportValidity()) return;
    const body = Object.fromEntries(new FormData(f));
    if (reg) body.age = Number(body.age);
    try {
      const s = await api(reg ? '/auth/register' : '/auth/login', { method: 'POST', body });
      state.token = s.token; store.set('gs_token', s.token); state.user = s.user;
      start();
    } catch (err) {
      const list = (err.details || []).map((d) => `<li>${esc(d.field)}: ${esc(d.message)}</li>`).join('');
      $('#auth-err').innerHTML = `<div class="login-error">${esc(err.message)}${list ? `<ul style="margin-left:16px">${list}</ul>` : ''}</div>`;
    }
  });
}

function logout() { state.token = null; state.user = null; store.set('gs_token', null); renderLogin(); }

// ---------------------------------------------------------------- shell
const NAV = {
  admin: [['dashboard', '🏛️', 'Dashboard'], ['documents', '📋', 'Document requests'], ['users', '👥', 'Citizens'], ['ration', '🌾', 'Ration'], ['anganwadi', '🏫', 'Anganwadi'], ['taxes', '💧', 'Water & property tax'], ['news', '📰', 'News'], ['audit', '🧾', 'Activity log'], ['rozgar', '💼', 'Rozgar moderation']],
  citizen: [['home', '🏠', 'My overview'], ['ration', '🌾', 'Ration card'], ['documents', '📄', 'Certificates'], ['anganwadi', '🏫', 'Anganwadi'], ['taxes', '💧', 'Water & property tax'], ['news', '📰', 'News'], ['assistant', '💬', 'Ask Sahayak'], ['rozgar', '💼', 'Rozgar jobs']],
};

function shell() {
  const role = state.user.role;
  $('#root').innerHTML = `<div class="app-layout">
    <aside class="sidebar"><div class="sidebar-logo"><h2>🏛️ GramSathi</h2><p>${role === 'admin' ? 'Panchayat console' : 'Citizen portal'}</p></div>
      <nav class="sidebar-nav" aria-label="Main">${NAV[role].map(([k, i, t]) => `<button class="nav-item" data-act="nav" data-page="${k}"><span class="nav-icon">${i}</span>${esc(t)}</button>`).join('')}</nav>
      <div class="sidebar-footer"></div></aside>
    <div class="main-content"><header class="header"><div><div class="header-title" id="h-title"></div><div class="header-subtitle" id="h-sub"></div></div>
      <div class="header-right"><span class="admin-badge">${esc(state.user.name)}</span><button class="logout-btn" data-act="logout">Sign out</button></div></header>
      <main class="page" id="page"></main></div></div>`;
}

async function go(page) {
  const role = state.user.role;
  const entry = NAV[role].find(([k]) => k === page) || NAV[role][0];
  state.page = entry[0];
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.page === state.page));
  $('#h-title').textContent = entry[1] + ' ' + entry[2];
  $('#h-sub').textContent = state.user.village || '';
  store.set('gs_page', state.page);
  const el = $('#page');
  el.innerHTML = '<div class="loading-screen" style="min-height:40vh"><div class="spinner"></div></div>';
  try { el.innerHTML = await PAGES[role][state.page](); const after = AFTER[state.page]; if (after) after(); }
  catch (e) { el.innerHTML = empty('⚠️', 'Could not load this page', e.message); }
}

// ---------------------------------------------------------------- admin pages
function trendChart(trend) {
  if (!trend.length) return empty('📊', 'No requests yet', 'Certificate requests will appear here by month.');
  const max = Math.max(...trend.map((t) => t.requests), 1);
  const cols = trend.map((t) => {
    const pend = t.requests - t.approved - t.rejected;
    const seg = (n, c) => n ? `<div class="bar-seg ${c}" style="height:${(n / max) * 120}px"></div>` : '';
    return `<div class="bar-col"><div class="bar-num">${t.requests}</div><div class="bar-stack">${seg(t.approved, 'approved')}${seg(pend, 'pending')}${seg(t.rejected, 'rejected')}</div><div class="bar-lbl">${esc(new Date(t.month + '-01').toLocaleDateString('en-IN', { month: 'short', year: '2-digit' }))}</div></div>`;
  }).join('');
  return `<div class="bars" role="img" aria-label="Certificate requests per month">${cols}</div><div class="legend"><span><i style="background:var(--green-mid)"></i>Approved</span><span><i style="background:var(--marigold)"></i>Pending</span><span><i style="background:#DC2626"></i>Rejected</span></div>`;
}

async function loadInsights() {
  const box = $('#insights');
  box.innerHTML = '<span class="muted">Thinking…</span>';
  try {
    const r = await api('/admin/ai/insights', { method: 'POST' });
    box.innerHTML = `<ul>${r.items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul><div style="margin-top:10px">${src(r.source)}</div>`;
  } catch (e) { box.textContent = e.message; }
}

const PAGES = { admin: {}, citizen: {} };
const AFTER = { dashboard: () => loadInsights() };

PAGES.admin.dashboard = async () => {
  const s = await api('/admin/dashboard');
  const d = s.dues, total = d.collected + d.outstanding;
  const pct = total ? Math.round((d.collected / total) * 100) : 0;
  return `<div class="stats-grid">
    <div class="stat-card"><div class="stat-icon">👥</div><div class="stat-value">${s.citizens.total}</div><div class="stat-label">Citizens (${s.citizens.new_30d} new this month)</div></div>
    <div class="stat-card ${s.documents.pending ? 'warn' : ''}"><div class="stat-icon">📋</div><div class="stat-value">${s.documents.pending}</div><div class="stat-label">Requests waiting for review</div></div>
    <div class="stat-card ${d.overdue_count ? 'bad' : ''}"><div class="stat-icon">⏰</div><div class="stat-value">${money(d.overdue_amount)}</div><div class="stat-label">Overdue across ${d.overdue_count} bill(s)</div></div>
    <div class="stat-card ${s.ration.expiring_30d ? 'warn' : ''}"><div class="stat-icon">🌾</div><div class="stat-value">${s.ration.active}</div><div class="stat-label">Active ration cards (${s.ration.expiring_30d} expire within 30 days)</div></div></div>
  <div class="grid-2">
    <div class="card"><div class="card-header"><div class="card-title">Certificate requests by month</div></div>${trendChart(s.documents.trend)}</div>
    <div class="ai-card"><strong>What needs attention</strong><div id="insights"></div><button class="link-btn" style="margin-top:8px" data-act="insights">Refresh</button></div></div>
  <div class="grid-2">
    <div class="card"><div class="card-header"><div class="card-title">Tax collected: ${pct}%</div><span class="muted">${money(d.collected)} of ${money(total)}</span></div><div class="pad"><div class="meter"><span class="low" style="width:${pct}%"></span></div>
      <h4 style="margin:14px 0 6px;font-size:14px">Largest overdue balances</h4>${d.top_defaulters.length ? `<table><tbody>${d.top_defaulters.map((u) => `<tr><td>${esc(u.name)}</td><td style="text-align:right;font-weight:700">${money(u.overdue_amount)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No overdue balances.</p>'}</div></div>
    <div class="card"><div class="card-header"><div class="card-title">Children per Anganwadi</div></div><div class="pad">${s.anganwadi.per_center.map((c) => `<div style="display:flex;justify-content:space-between;padding:6px 0;font-size:14px"><span>${esc(c.name)}</span><strong>${c.children}</strong></div>`).join('') || '<p class="muted">No centers yet.</p>'}</div></div></div>`;
};

function reviewPanel(r) {
  if (!r) return '<p class="muted">No automated review is available for this request.</p>';
  return `<div class="risk-head"><span class="risk-score">${r.risk_score}</span><span class="badge badge-${esc(r.risk_level)}">${esc(r.risk_level)} risk</span> ${src(r.source)}</div>
    <div class="meter"><span class="${esc(r.risk_level)}" style="width:${Math.max(r.risk_score, 3)}%"></span></div>
    <p style="font-size:14px">${esc(r.summary)}</p>
    ${r.flags.length ? `<ul class="flags">${r.flags.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>` : '<ul class="flags"><li class="none">No flags raised</li></ul>'}`;
}

function docDetails(d) {
  const rows = Object.entries(d.data).filter(([, v]) => v).map(([k, v]) => `<div class="doc-detail-item"><div class="doc-detail-label">${esc(label(k))}</div><div class="doc-detail-value">${esc(v)}</div></div>`).join('');
  return `<div class="doc-detail-grid">${rows}</div>`;
}

PAGES.admin.documents = async () => {
  const status = state.docFilter || '';
  const { items } = await api('/documents' + (status ? '?status=' + status : ''));
  state.docs = Object.fromEntries(items.map((d) => [d.id, d]));
  const tabs = [['', 'All'], ['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected']];
  return `<div class="page-head"><div><h2>Certificate requests</h2><p>Each request is pre-checked automatically. Review the flags, then approve or reject.</p></div></div>
    <div class="filter-tabs" style="margin-bottom:14px">${tabs.map(([k, t]) => `<button class="filter-tab ${status === k ? 'active' : ''}" data-act="doc-filter" data-s="${k}">${t}</button>`).join('')}</div>
    <div class="card"><div class="table-wrap">${items.length ? `<table><thead><tr><th>#</th><th>Applicant</th><th>Type</th><th>Pre-check</th><th>Status</th><th>Submitted</th><th></th></tr></thead><tbody>${items.map((d) => `<tr><td>${d.id}</td><td>${esc(d.applicant_name)}<div class="muted">${esc(d.data.full_name)}</div></td><td>${esc(label(d.doc_type))}</td><td>${d.ai_review ? `<span class="badge badge-${esc(d.ai_review.risk_level)}">${esc(d.ai_review.risk_level)} · ${d.ai_review.risk_score}</span>` : '—'}</td><td>${badge(d.status)}</td><td>${fdate(d.created_at)}</td><td><button class="btn btn-ghost btn-sm" data-act="doc-open" data-id="${d.id}">${d.status === 'pending' ? 'Review' : 'View'}</button></td></tr>`).join('')}</tbody></table>` : empty('📭', 'No requests here', 'New certificate requests from citizens will show up in this list.')}</div></div>`;
};

PAGES.admin.users = async () => {
  const { items, total } = await api('/admin/users' + (state.userQ ? '?q=' + encodeURIComponent(state.userQ) : ''));
  state.userList = items;
  return `<div class="page-head"><div><h2>Citizens</h2><p>${total} account(s)</p></div><form data-form="user-search" class="toolbar-right"><input class="search-input" name="q" placeholder="Search name, email or mobile" value="${esc(state.userQ || '')}" aria-label="Search citizens"><button class="btn btn-primary" type="submit">Search</button></form></div>
    <div class="card"><div class="table-wrap">${items.length ? `<table><thead><tr><th>Name</th><th>Contact</th><th>Village</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody>${items.map((u) => `<tr><td><div style="display:flex;gap:10px;align-items:center"><div class="avatar">${esc(u.name[0])}</div>${esc(u.name)}</div></td><td>${esc(u.email)}<div class="muted">${esc(u.mobile)}</div></td><td>${esc(u.village || '—')}</td><td><span class="badge badge-${u.role === 'admin' ? 'admin' : 'user'}">${esc(u.role)}</span></td><td>${badge(u.is_active ? 'active' : 'inactive')}</td><td>${u.id === state.user.id ? '' : `<button class="btn btn-sm ${u.is_active ? 'btn-danger' : 'btn-success'}" data-act="user-toggle" data-id="${u.id}" data-active="${u.is_active ? 0 : 1}">${u.is_active ? 'Deactivate' : 'Reactivate'}</button>`}</td></tr>`).join('')}</tbody></table>` : empty('🔍', 'No citizens match', 'Try a different name, email or mobile number.')}</div></div>`;
};

async function userOptions() {
  if (!state.users.length) state.users = (await api('/admin/users?role=citizen&limit=200')).items;
  return state.users.map((u) => [u.id, `${u.name} (${u.email})`]);
}

PAGES.admin.ration = async () => {
  const { items } = await api('/admin/ration');
  return `<div class="page-head"><div><h2>Ration cards</h2><p>${items.length} card(s) on record</p></div><button class="btn btn-primary" data-act="ration-add">Add ration card</button></div>
    <div class="card"><div class="table-wrap">${items.length ? `<table><thead><tr><th>Card</th><th>Holder</th><th>Type</th><th>Valid until</th><th>Entitlement</th><th>Status</th></tr></thead><tbody>${items.map((c) => `<tr><td>${esc(c.card_no)}</td><td>${esc(c.holder_name)}</td><td>${esc(c.card_type)}</td><td>${fdate(c.validity_end)}</td><td>${c.items.map((i) => `${esc(i.name)} ${i.quantity}${esc(i.unit)}`).join(', ') || '—'}</td><td>${badge(c.status)}</td></tr>`).join('')}</tbody></table>` : empty('🌾', 'No ration cards yet', 'Add the first card to link a family to its monthly entitlement.')}</div></div>`;
};

PAGES.admin.anganwadi = async () => {
  const [c, b] = await Promise.all([api('/anganwadi'), api('/admin/anganwadi/beneficiaries')]);
  return `<div class="page-head"><div><h2>Anganwadi centers</h2><p>${c.items.length} center(s), ${b.items.length} enrolment(s)</p></div><div class="row-actions"><button class="btn btn-ghost" data-act="ben-add">Enrol a child</button><button class="btn btn-primary" data-act="center-add">Add center</button></div></div>
    <div class="grid-3" style="margin-bottom:20px">${c.items.map((x) => `<div class="card svc"><h3>${esc(x.name)}</h3><div class="muted">${esc(x.address)} · ${esc(x.open_time)}–${esc(x.close_time)}</div><div class="tags">${x.services.map((s) => `<span class="tag">${esc(s)}</span>`).join('')}</div><div class="kv"><dt>Active children</dt><dd>${x.active_children}</dd><dt>Phone</dt><dd>${esc(x.phone || '—')}</dd></div></div>`).join('')}</div>
    <div class="card"><div class="card-header"><div class="card-title">Enrolments</div></div><div class="table-wrap">${b.items.length ? `<table><thead><tr><th>Child</th><th>Guardian</th><th>Center</th><th>Age group</th><th>Last visit</th><th>Status</th></tr></thead><tbody>${b.items.map((x) => `<tr><td>${esc(x.child_name)}</td><td>${esc(x.guardian)}</td><td>${esc(x.center)}</td><td>${esc(x.age_group)}</td><td>${fdate(x.last_visit)}</td><td>${badge(x.status)}</td></tr>`).join('')}</tbody></table>` : empty('👶', 'No enrolments yet', 'Enrol a child to start tracking attendance.')}</div></div>`;
};

PAGES.admin.taxes = async () => {
  const [w, p] = await Promise.all([api('/admin/water'), api('/admin/property')]);
  const bills = w.items.flatMap((c) => c.bills.map((b) => ({ ...b, holder: c.holder_name, no: c.connection_no })));
  const today = new Date().toISOString().slice(0, 10);
  const due = (paid, d) => (paid ? badge('approved').replace('Approved', 'Paid') : d < today ? '<span class="badge badge-rejected">Overdue</span>' : badge('pending').replace('Pending', 'Due'));
  return `<div class="page-head"><div><h2>Water & property tax</h2><p>Property tax is calculated from value × rate on the server.</p></div><div class="row-actions"><button class="btn btn-ghost" data-act="water-add">Add water bill</button><button class="btn btn-primary" data-act="prop-add">Add property</button></div></div>
    <div class="card" style="margin-bottom:20px"><div class="card-header"><div class="card-title">Water bills</div></div><div class="table-wrap">${bills.length ? `<table><thead><tr><th>Connection</th><th>Holder</th><th>Period</th><th>Amount</th><th>Due</th><th>Status</th></tr></thead><tbody>${bills.map((b) => `<tr><td>${esc(b.no)}</td><td>${esc(b.holder)}</td><td>${esc(b.period)}</td><td>${money(b.amount)}</td><td>${fdate(b.due_date)}</td><td>${due(b.paid, b.due_date)}</td></tr>`).join('')}</tbody></table>` : empty('💧', 'No water bills yet', 'Add a bill to create the connection and notify the holder in their portal.')}</div></div>
    <div class="card"><div class="card-header"><div class="card-title">Properties</div></div><div class="table-wrap">${p.items.length ? `<table><thead><tr><th>Property</th><th>Owner</th><th>Value</th><th>Rate</th><th>Annual tax</th><th>Due</th><th>Status</th></tr></thead><tbody>${p.items.map((x) => `<tr><td>${esc(x.property_no)}</td><td>${esc(x.holder_name)}</td><td>${money(x.value)}</td><td>${x.tax_rate}%</td><td>${money(x.annual_tax)}</td><td>${fdate(x.due_date)}</td><td>${due(x.paid, x.due_date)}</td></tr>`).join('')}</tbody></table>` : empty('🏠', 'No properties yet', 'Add a property to calculate its annual tax.')}</div></div>`;
};

PAGES.admin.audit = async () => {
  const { items } = await api('/admin/audit');
  return `<div class="page-head"><div><h2>Activity log</h2><p>The latest 100 changes, with who made them.</p></div></div><div class="card"><div class="table-wrap"><table><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Item</th><th>Detail</th></tr></thead><tbody>${items.map((a) => `<tr><td>${esc(new Date(a.created_at).toLocaleString('en-IN'))}</td><td>${esc(a.actor || 'system')}</td><td>${esc(a.action)}</td><td>${esc(a.entity)} #${a.entity_id ?? ''}</td><td class="muted">${esc(a.detail)}</td></tr>`).join('')}</tbody></table></div></div>`;
};

// ---------------------------------------------------------------- news (both roles)
const newsPage = async () => {
  const admin = state.user.role === 'admin';
  const { items } = await api('/news' + (admin ? '?all=1' : ''));
  state.news = Object.fromEntries(items.map((n) => [n.id, n]));
  const lang = state.lang || 'en';
  const show = (n) => ({ title: (lang !== 'en' && n['title_' + lang]) || n.title, text: (lang !== 'en' && n['description_' + lang]) || n.description });
  return `<div class="page-head"><div><h2>Village news</h2><p>Announcements, deadlines and health updates.</p></div><div class="row-actions">
    <select class="form-select" data-change="lang" aria-label="Language"><option value="en" ${lang === 'en' ? 'selected' : ''}>English</option><option value="hi" ${lang === 'hi' ? 'selected' : ''}>हिन्दी</option><option value="mr" ${lang === 'mr' ? 'selected' : ''}>मराठी</option></select>
    ${admin ? '<button class="btn btn-primary" data-act="news-add">Write announcement</button>' : ''}</div></div>
    ${items.length ? `<div class="grid-3">${items.map((n) => { const s = show(n); return `<div class="card svc" style="${n.active ? '' : 'opacity:.6'}"><div style="display:flex;justify-content:space-between;gap:8px"><span class="tag">${esc(label(n.category))}</span>${n.priority >= 4 ? '<span class="badge badge-rejected">Urgent</span>' : ''}</div><h3 style="margin-top:10px">${esc(s.title)}</h3><p style="font-size:14px;line-height:1.55;color:var(--ink-soft)">${esc(s.text)}</p><div class="muted" style="margin-top:10px">${fdate(n.created_at)}${n.active ? '' : ' · Hidden'}</div>${admin ? `<div class="row-actions" style="margin-top:12px"><button class="btn btn-ghost btn-sm" data-act="news-edit" data-id="${n.id}">Edit</button><button class="btn btn-danger btn-sm" data-act="news-del" data-id="${n.id}">Delete</button></div>` : ''}</div>`; }).join('')}</div>` : empty('📰', 'No announcements yet', admin ? 'Write the first one. The AI can draft it from rough notes and translate it.' : 'Check back soon.')}`;
};
PAGES.admin.news = newsPage;
PAGES.citizen.news = newsPage;

PAGES.admin.rozgar = async () => {
  const { items } = await api('/admin/rozgar/moderation');
  return `<div class="page-head"><div><h2>Rozgar moderation</h2><p>Review flagged employment posts before they become visible to citizens.</p></div><span class="badge badge-pending">${items.length} pending</span></div>
  ${items.length ? `<div class="rozgar-grid">${items.map(j => `<article class="card rozgar-card"><div class="rozgar-top"><span class="badge badge-pending">Needs review</span><span class="rozgar-risk">Risk ${j.scam_score}/100</span></div><h3>${esc(j.title)}</h3><p class="muted">${esc(j.company)} · ${esc(j.location)} · ${esc(j.employer_name)}</p><p>${esc(j.description)}</p><div class="tags">${j.skills.map(x=>`<span class="tag">${esc(x)}</span>`).join('')}</div><div class="rozgar-flags">${j.scam_flags.map(x=>`<span>⚠ ${esc(x)}</span>`).join('')}</div><div class="row-actions"><button class="btn btn-danger" data-act="rozgar-moderate" data-id="${j.id}" data-status="rejected">Reject</button><button class="btn btn-primary" data-act="rozgar-moderate" data-id="${j.id}" data-status="published">Approve & publish</button></div></article>`).join('')}</div>` : empty('🛡️','No jobs awaiting review','New flagged posts will appear here.')}`;
};

// ---------------------------------------------------------------- citizen pages
PAGES.citizen.home = async () => {
  const [r, w, p, d, n] = await Promise.all([api('/me/ration'), api('/me/water'), api('/me/property'), api('/documents'), api('/news')]);
  const today = new Date().toISOString().slice(0, 10);
  const unpaid = [...w.items.flatMap((c) => c.bills.filter((b) => !b.paid).map((b) => ({ l: 'Water ' + b.period, a: b.amount, d: b.due_date }))), ...p.items.filter((x) => !x.paid).map((x) => ({ l: 'Property ' + x.property_no, a: x.annual_tax, d: x.due_date }))];
  const owed = unpaid.reduce((s, x) => s + x.a, 0);
  const pend = d.items.filter((x) => x.status === 'pending').length;
  const approved = d.items.filter((x) => x.status === 'approved').length;
  const overdue = unpaid.filter((x) => x.d < today).length;
  const latestNews = n.items.slice(0, 3);
  const firstName = state.user.name.split(' ')[0];
  return `<section class="gs-welcome">
      <div class="gs-welcome-copy"><div class="gs-eyebrow"><span class="gs-live-dot"></span> YOUR VILLAGE, ONE DIGITAL HOME</div>
        <h2>Namaste, ${esc(firstName)} <span>👋</span></h2><p>Good to see you. Your GramSathi services and village updates are all in one place.</p>
        <div class="gs-welcome-actions"><button class="gs-primary-action" data-act="nav" data-page="assistant">✨ Ask Sahayak AI <span>→</span></button><button class="gs-secondary-action" data-act="nav" data-page="documents">＋ Apply for a certificate</button></div>
      </div><div class="gs-welcome-art" aria-hidden="true"><div class="gs-sun"></div><div class="gs-hill hill-one"></div><div class="gs-hill hill-two"></div><div class="gs-house">🏡</div><div class="gs-art-label">आपले गाव · आपली सेवा</div></div>
    </section>
    <div class="gs-section-heading"><div><span class="gs-kicker">AT A GLANCE</span><h3>Your service overview</h3></div><span class="gs-updated">Updated just now</span></div>
    <div class="gs-stat-grid">
      <button class="gs-stat-tile tile-bill" data-act="nav" data-page="taxes"><span class="gs-stat-icon">💧</span><span class="gs-stat-meta">PENDING DUES</span><strong>${money(owed)}</strong><small>${unpaid.length ? `${unpaid.length} unpaid bill(s) · ${overdue} overdue` : 'You are all caught up'} </small><span class="gs-tile-arrow">↗</span></button>
      <button class="gs-stat-tile tile-ration" data-act="nav" data-page="ration"><span class="gs-stat-icon">🌾</span><span class="gs-stat-meta">RATION CARD</span><strong>${r.items[0] ? esc(r.items[0].card_type) : 'Not linked'}</strong><small>${r.items[0] ? `Valid until ${fdate(r.items[0].validity_end)}` : 'View card information'}</small><span class="gs-tile-arrow">↗</span></button>
      <button class="gs-stat-tile tile-docs" data-act="nav" data-page="documents"><span class="gs-stat-icon">📄</span><span class="gs-stat-meta">APPLICATIONS</span><strong>${d.items.length}</strong><small>${pend} pending · ${approved} approved</small><span class="gs-tile-arrow">↗</span></button>
      <button class="gs-stat-tile tile-news" data-act="nav" data-page="news"><span class="gs-stat-icon">📢</span><span class="gs-stat-meta">VILLAGE UPDATES</span><strong>${n.items.length}</strong><small>Announcements and notices</small><span class="gs-tile-arrow">↗</span></button>
    </div>
    <div class="gs-home-grid">
      <section class="gs-panel gs-ai-panel"><div class="gs-panel-top"><div class="gs-ai-mark">✦</div><div><span class="gs-kicker">YOUR DIGITAL VILLAGE ASSISTANT</span><h3>Meet Sahayak AI</h3></div><span class="gs-ai-status">● READY</span></div>
        <p class="gs-ai-intro">Ask in simple English, हिंदी or मराठी. Get help understanding services, your applications and your personal records.</p>
        <div class="gs-prompt-list"><button data-act="home-prompt" data-q="Do I have any pending water or property tax dues?">💧 Check my pending bills <span>→</span></button><button data-act="home-prompt" data-q="What is my ration entitlement?">🌾 Understand my ration details <span>→</span></button><button data-act="home-prompt" data-q="What is the status of my certificate request?">📄 Track my certificate <span>→</span></button><button data-act="home-prompt" data-q="What services can I access through GramSathi?">🧭 Find available village services <span>→</span></button></div>
        <form class="gs-ai-input" data-form="home-chat"><input name="message" maxlength="1000" placeholder="Ask Sahayak anything…" aria-label="Ask Sahayak AI" required><button type="submit" aria-label="Send question">➤</button></form><div class="gs-ai-note">🔒 Sahayak answers personal-record questions using your account data. Always verify important government decisions with the relevant office.</div>
      </section>
      <section class="gs-panel"><div class="gs-panel-heading"><div><span class="gs-kicker">QUICK ACCESS</span><h3>Popular services</h3></div><span class="gs-heading-icon">⌘</span></div>
        <div class="gs-service-grid"><button class="gs-service" data-act="nav" data-page="documents"><span class="service-emoji service-purple">📜</span><strong>Certificates</strong><small>Apply & track</small></button><button class="gs-service" data-act="nav" data-page="ration"><span class="service-emoji service-green">🌾</span><strong>Ration card</strong><small>Card & entitlement</small></button><button class="gs-service" data-act="nav" data-page="taxes"><span class="service-emoji service-blue">💧</span><strong>Pay bills</strong><small>Water & property</small></button><button class="gs-service" data-act="nav" data-page="anganwadi"><span class="service-emoji service-orange">🧒</span><strong>Anganwadi</strong><small>Centers & children</small></button><button class="gs-service" data-act="nav" data-page="news"><span class="service-emoji service-pink">📣</span><strong>Village news</strong><small>Notices & updates</small></button><button class="gs-service" data-act="nav" data-page="assistant"><span class="service-emoji service-indigo">🤖</span><strong>Ask Sahayak</strong><small>AI assistance</small></button></div>
      </section>
    </div>
    <div class="gs-home-grid gs-bottom-grid">
      <section class="gs-panel"><div class="gs-panel-heading"><div><span class="gs-kicker">FROM YOUR PANCHAYAT</span><h3>Latest village updates</h3></div><button class="gs-text-link" data-act="nav" data-page="news">View all →</button></div>
        ${latestNews.length ? `<div class="gs-news-list">${latestNews.map((x, i) => `<article class="gs-news-item"><span class="gs-news-icon">${['📢','🗓️','🌱'][i % 3]}</span><div><strong>${esc(x.title)}</strong><p>${esc(x.description)}</p><small>${fdate(x.created_at)}</small></div></article>`).join('')}</div>` : `<div class="gs-empty-news">📰<strong>No new announcements</strong><span>New updates from your Gram Panchayat will appear here.</span></div>`}
      </section>
      <section class="gs-panel gs-help-panel"><span class="gs-kicker">NEED A HAND?</span><div class="gs-help-illustration">🤝</div><h3>We're here to help.</h3><p>Not sure which service you need? Start with Sahayak or visit your service pages to explore what is available.</p><button class="gs-help-button" data-act="nav" data-page="assistant">Get help from Sahayak <span>→</span></button><div class="gs-safety-note">ℹ️ Never share your password, OTP or bank PIN with anyone.</div></section>
    </div>`;
};

PAGES.citizen.ration = async () => {
  const { items } = await api('/me/ration');
  if (!items.length) return empty('🌾', 'No ration card linked', 'Visit the panchayat office with your family documents to have a card added.');
  return `<div class="grid-3">${items.map((c) => `<div class="card svc"><h3>${esc(c.card_type)} card ${esc(c.card_no)}</h3><div>${badge(c.status)}</div><dl class="kv"><dt>Valid</dt><dd>${fdate(c.validity_start)} to ${fdate(c.validity_end)}</dd><dt>Collect from</dt><dd>${esc(c.distribution_point || '—')}</dd><dt>Last collected</dt><dd>${fdate(c.last_distribution)}</dd></dl><div class="tags">${c.items.map((i) => `<span class="tag">${esc(i.name)} ${i.quantity}${esc(i.unit)}</span>`).join('')}</div></div>`).join('')}</div>`;
};

PAGES.citizen.documents = async () => {
  const { items } = await api('/documents');
  state.docs = Object.fromEntries(items.map((d) => [d.id, d]));
  return `<div class="page-head"><div><h2>Certificates</h2><p>Request a certificate. Once the panchayat approves it, you can download the PDF.</p></div><button class="btn btn-primary" data-act="doc-new">Request a certificate</button></div>
    <div class="card"><div class="table-wrap">${items.length ? `<table><thead><tr><th>#</th><th>Certificate</th><th>For</th><th>Status</th><th>Submitted</th><th></th></tr></thead><tbody>${items.map((d) => `<tr><td>${d.id}</td><td>${esc(label(d.doc_type))}</td><td>${esc(d.data.full_name)}</td><td>${badge(d.status)}${d.admin_note ? `<div class="muted">${esc(d.admin_note)}</div>` : ''}</td><td>${fdate(d.created_at)}</td><td>${d.status === 'approved' ? `<button class="btn btn-success btn-sm" data-act="doc-pdf" data-id="${d.id}">Download PDF</button>` : ''}</td></tr>`).join('')}</tbody></table>` : empty('📄', 'No requests yet', 'Request a birth or bonafide certificate to get started.')}</div></div>`;
};

PAGES.citizen.anganwadi = async () => {
  const mine = await api('/me/anganwadi');
  let centers;
  try { centers = await new Promise((res) => { if (!navigator.geolocation) return res(null); navigator.geolocation.getCurrentPosition((p) => res({ lat: p.coords.latitude, lng: p.coords.longitude }), () => res(null), { timeout: 1500 }); }); } catch { centers = null; }
  const list = await api('/anganwadi' + (centers ? `?lat=${centers.lat}&lng=${centers.lng}` : ''));
  return `<div class="page-head"><div><h2>Anganwadi</h2><p>${centers ? 'Centers sorted by distance from you.' : 'Centers in your area.'}</p></div></div>
    ${mine.items.length ? `<div class="card" style="margin-bottom:20px"><div class="card-header"><div class="card-title">Your children</div></div><div class="table-wrap"><table><tbody>${mine.items.map((x) => `<tr><td>${esc(x.child_name)}</td><td>${esc(x.center)}</td><td>${esc(x.age_group)} yrs</td><td>${badge(x.status)}</td><td class="muted">Last visit ${fdate(x.last_visit)}</td></tr>`).join('')}</tbody></table></div></div>` : ''}
    <div class="grid-3">${list.items.map((x) => `<div class="card svc"><h3>${esc(x.name)}</h3><div class="muted">${esc(x.address)}</div><div class="tags">${x.services.map((s) => `<span class="tag">${esc(s)}</span>`).join('')}</div><dl class="kv"><dt>Open</dt><dd>${esc(x.open_time)}–${esc(x.close_time)}</dd><dt>Phone</dt><dd>${esc(x.phone || '—')}</dd>${x.distance_km != null ? `<dt>Distance</dt><dd>${x.distance_km} km</dd>` : ''}</dl></div>`).join('')}</div>`;
};

PAGES.citizen.rozgar = async () => {
  const [jobs, prof, mine, apps] = await Promise.all([api('/rozgar/jobs'), api('/rozgar/profile'), api('/rozgar/jobs/mine'), api('/rozgar/applications/mine')]);
  const p=prof.profile||{};
  return `<div class="page-head"><div><h2>Rozgar · Local opportunities</h2><p>Discover jobs, build a simple profile and connect with local employers. Never pay a fee to get a job.</p></div><span class="badge badge-approved">${jobs.items.length} live jobs</span></div>
  <section class="card rozgar-profile"><div class="card-header"><div><div class="card-title">Your Rozgar profile</div><p class="muted">A stronger profile helps explain why a job may match your skills.</p></div></div><form data-form="rozgar-profile" class="rozgar-form"><div class="form-row"><div class="form-group"><label class="form-label">I am</label><select class="form-select" name="profile_type"><option value="worker" ${p.profile_type!=='employer'?'selected':''}>Looking for work</option><option value="employer" ${p.profile_type==='employer'?'selected':''}>Hiring workers</option></select></div><div class="form-group"><label class="form-label">Headline</label><input class="form-input" name="headline" maxlength="120" value="${esc(p.headline||'')}" placeholder="e.g. Fresher · Python & SQL"></div></div><div class="form-row"><div class="form-group"><label class="form-label">Skills (comma separated)</label><input class="form-input" name="skills" value="${esc((p.skills||[]).join(', '))}" placeholder="Python, SQL, Excel"></div><div class="form-group"><label class="form-label">Experience (years)</label><input class="form-input" type="number" min="0" max="60" step="0.5" name="experience_years" value="${Number(p.experience_years||0)}"></div></div><div class="form-row"><div class="form-group"><label class="form-label">Education</label><input class="form-input" name="education" value="${esc(p.education||'')}" placeholder="B.E. / Diploma / 12th"></div><div class="form-group"><label class="form-label">Preferred location</label><input class="form-input" name="location" value="${esc(p.location||'')}" placeholder="Nashik, Pune, Remote"></div></div><div class="form-group"><label class="form-label">About you</label><textarea id="rozgar-bio" class="form-textarea" name="bio" maxlength="1200" placeholder="Tell employers about your experience and goals">${esc(p.bio||'')}</textarea><button type="button" class="btn btn-ghost btn-sm" data-act="rozgar-voice" data-target="rozgar-bio">🎙 Dictate in your language</button></div><label class="muted"><input type="checkbox" name="phone_public" ${p.phone_public?'checked':''}> Contact-sharing preference (mobile number is not exposed in this demo)</label><button type="button" class="btn btn-ghost btn-sm" data-act="rozgar-profile-draft">✨ Draft profile with Sahayak</button><button class="btn btn-primary" type="submit">Save profile</button></form></section>
  <div class="page-head" style="margin-top:26px"><div><h2>Recommended jobs</h2><p>Match scores are explainable skill overlap, not an employment guarantee.</p></div></div>
  <div class="rozgar-grid">${jobs.items.map(j=>`<article class="card rozgar-card"><div class="rozgar-top"><span class="badge badge-approved">${esc(j.job_type)}</span><strong class="rozgar-match">${j.match_score}% match</strong></div><h3>${esc(j.title)}</h3><p class="muted">${esc(j.company)} · ${esc(j.location)}</p><p>${esc(j.description)}</p><div class="tags">${j.skills.map(x=>`<span class="tag">${esc(x)}</span>`).join('')}</div><p class="rozgar-reason">${esc(j.match_reason)}</p><div class="rozgar-bottom"><strong>${j.salary_min!=null&&j.salary_max!=null?money(j.salary_min)+' – '+money(j.salary_max):j.salary_min!=null?'From '+money(j.salary_min):j.salary_max!=null?'Up to '+money(j.salary_max):'Salary not disclosed'}</strong>${j.employer_id===state.user.id?'<span class="badge badge-approved">Your post</span>':j.applied?'<span class="badge badge-pending">Applied</span>':`<button class="btn btn-primary btn-sm" data-act="rozgar-apply" data-id="${j.id}">Apply now</button>`}</div></article>`).join('')||empty('💼','No matching jobs yet','Try again later or update your location and skills.')}</div>
  <div class="grid-2" style="margin-top:22px"><section class="card"><div class="card-header"><div class="card-title">My applications</div></div>${apps.items.length?`<div class="table-wrap"><table><thead><tr><th>Role</th><th>Company</th><th>Status</th><th>Match</th></tr></thead><tbody>${apps.items.map(a=>`<tr><td>${esc(a.title)}</td><td>${esc(a.company)}</td><td>${badge(a.status)}</td><td>${a.match_score}%</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted pad">You have not applied to a job yet.</p>'}</section>
  <section class="card"><div class="card-header"><div class="card-title">Post a job</div></div><form data-form="rozgar-job" class="rozgar-form pad"><div class="form-group"><label class="form-label">Job title</label><input class="form-input" name="title" required minlength="3"></div><div class="form-group"><label class="form-label">Company / employer</label><input class="form-input" name="company" required minlength="2"></div><div class="form-group"><label class="form-label">Description</label><textarea id="rozgar-job-description" class="form-textarea" name="description" required minlength="20"></textarea><button type="button" class="btn btn-ghost btn-sm" data-act="rozgar-voice" data-target="rozgar-job-description">🎙 Dictate in your language</button></div><div class="form-group"><label class="form-label">Skills (comma separated)</label><input class="form-input" name="skills" placeholder="Excel, Communication"></div><div class="form-row"><div class="form-group"><label class="form-label">Location</label><input class="form-input" name="location" required></div><div class="form-group"><label class="form-label">Job type</label><select class="form-select" name="job_type"><option>Full-time</option><option>Part-time</option><option>Internship</option><option>Contract</option></select></div></div><div class="form-row"><div class="form-group"><label class="form-label">Min salary (₹/month)</label><input class="form-input" type="number" min="0" name="salary_min"></div><div class="form-group"><label class="form-label">Max salary (₹/month)</label><input class="form-input" type="number" min="0" name="salary_max"></div></div><button type="button" class="btn btn-ghost btn-sm" data-act="rozgar-job-draft">✨ Improve job post with Sahayak</button><button class="btn btn-primary" type="submit">Submit job for review</button><small class="muted">Posts with scam-risk signals are held for admin moderation.</small></form></section></div>
  <section class="card" style="margin-top:22px"><div class="card-header"><div class="card-title">My job posts & applicants</div></div>${mine.items.length?mine.items.map(j=>`<div class="rozgar-own-job"><div><strong>${esc(j.title)}</strong><p class="muted">${esc(j.company)} · ${badge(j.status)} · ${j.applicant_count} applicant(s)</p></div><div class="row-actions"><button class="btn btn-ghost btn-sm" data-act="rozgar-summary" data-id="${j.id}">Applicant summary</button><button class="btn btn-ghost btn-sm" data-act="rozgar-applicants" data-id="${j.id}">View applicants</button></div></div>`).join(''):'<p class="muted pad">No job posts yet.</p>'}</section>`;
};

PAGES.citizen.taxes = async () => {
  const [w, p] = await Promise.all([api('/me/water'), api('/me/property')]);
  const today = new Date().toISOString().slice(0, 10);
  const st = (paid, d) => (paid ? '<span class="badge badge-approved">Paid</span>' : d < today ? '<span class="badge badge-rejected">Overdue</span>' : '<span class="badge badge-pending">Due</span>');
  const bills = w.items.flatMap((c) => c.bills.map((b) => ({ ...b, no: c.connection_no })));
  return `<div class="page-head"><div><h2>Water & property tax</h2><p>Payments here are simulated until a payment gateway is connected.</p></div></div>
    <div class="card" style="margin-bottom:20px"><div class="card-header"><div class="card-title">Water bills</div></div><div class="table-wrap">${bills.length ? `<table><thead><tr><th>Connection</th><th>Period</th><th>Amount</th><th>Due</th><th>Status</th><th></th></tr></thead><tbody>${bills.map((b) => `<tr><td>${esc(b.no)}</td><td>${esc(b.period)}</td><td>${money(b.amount)}</td><td>${fdate(b.due_date)}</td><td>${st(b.paid, b.due_date)}</td><td>${b.paid ? '' : `<button class="btn btn-primary btn-sm" data-act="pay-water" data-id="${b.id}">Pay ${money(b.amount)}</button>`}</td></tr>`).join('')}</tbody></table>` : empty('💧', 'No water connection', 'Contact the panchayat office to add a connection.')}</div></div>
    <div class="card"><div class="card-header"><div class="card-title">Property tax</div></div><div class="table-wrap">${p.items.length ? `<table><thead><tr><th>Property</th><th>Value</th><th>Rate</th><th>Annual tax</th><th>Due</th><th>Status</th><th></th></tr></thead><tbody>${p.items.map((x) => `<tr><td>${esc(x.property_no)}</td><td>${money(x.value)}</td><td>${x.tax_rate}%</td><td>${money(x.annual_tax)}</td><td>${fdate(x.due_date)}</td><td>${st(x.paid, x.due_date)}</td><td>${x.paid ? '' : `<button class="btn btn-primary btn-sm" data-act="pay-prop" data-id="${x.id}">Pay ${money(x.annual_tax)}</button>`}</td></tr>`).join('')}</tbody></table>` : empty('🏠', 'No property on record', 'Contact the panchayat office to register your property.')}</div></div>`;
};

PAGES.citizen.assistant = async () => {
  const { items } = await api('/ai/chat/history');
  const lang = state.chatLang || 'en';
  const bubble = (m) => `<div class="msg ${m.role}">${esc(m.content)}${m.role === 'assistant' ? `<small>${m.source === 'claude' ? 'AI answer' : 'Offline answer'}</small>` : ''}</div>`;
  return `<div class="page-head"><div><h2>Ask Sahayak</h2><p>Ask about your ration, dues, certificates or village news. Answers use only your own records.</p></div>
    <select class="form-select" data-change="chat-lang" aria-label="Reply language"><option value="en" ${lang === 'en' ? 'selected' : ''}>Reply in English</option><option value="hi" ${lang === 'hi' ? 'selected' : ''}>हिन्दी में उत्तर</option><option value="mr" ${lang === 'mr' ? 'selected' : ''}>मराठीत उत्तर</option></select></div>
    <div class="card chat"><div class="chat-log" id="chat-log" aria-live="polite">${items.length ? items.map(bubble).join('') : '<div class="muted">No messages yet. Try one of the questions below.</div>'}</div>
    <div class="suggest">${['What is my ration entitlement?', 'Do I have any tax due?', 'Where is my certificate request?'].map((q) => `<button class="filter-tab" data-act="suggest" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <form class="chat-form" data-form="chat"><input class="form-input" name="message" maxlength="1000" placeholder="Type your question" aria-label="Your question" autocomplete="off" required><button class="btn btn-primary" type="submit">Send</button></form></div>`;
};
AFTER.assistant = () => { const l = $('#chat-log'); if (l) l.scrollTop = l.scrollHeight; };

async function sendChat(message) {
  const log = $('#chat-log');
  if (!message.trim()) return;
  if (log.querySelector('.muted')) log.innerHTML = '';
  log.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(message)}</div><div class="msg assistant" id="typing">…</div>`);
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api('/ai/chat', { method: 'POST', body: { message, language: state.chatLang || 'en' } });
    $('#typing').outerHTML = `<div class="msg assistant">${esc(r.reply)}<small>${r.source === 'claude' ? 'AI answer' : 'Offline answer'}</small></div>`;
  } catch (e) { $('#typing').outerHTML = `<div class="msg assistant">${esc(e.message)}</div>`; }
  log.scrollTop = log.scrollHeight;
}

// ---------------------------------------------------------------- actions
const DOC_FIELDS = [
  { name: 'doc_type', label: 'Certificate type', type: 'select', options: [['birth_certificate', 'Birth certificate'], ['bonafide_certificate', 'Bonafide (student) certificate']], required: true },
  { name: 'full_name', label: 'Full name of the person', required: true },
  { name: 'date_of_birth', label: 'Date of birth', type: 'date', required: true },
  { name: 'father_name', label: "Father's name", required: true },
  { name: 'mother_name', label: "Mother's name" },
  { name: 'place_of_birth', label: 'Place of birth (birth certificate)' },
  { name: 'school_name', label: 'School (bonafide certificate)' },
  { name: 'purpose', label: 'Purpose (bonafide certificate)' },
  { name: 'address', label: 'Address', type: 'textarea', required: true },
];

function newsForm(item = {}) {
  const f = [
    { name: 'title', label: 'Title', required: true, value: item.title },
    { name: 'category', label: 'Category', type: 'select', options: ['general', 'scheme', 'deadline', 'alert', 'health'], value: item.category || 'general' },
    { name: 'priority', label: 'Priority (1 low to 5 urgent)', type: 'number', min: 1, value: item.priority ?? 3, required: true },
    { name: 'active', label: 'Visibility', type: 'select', options: [['true', 'Visible to citizens'], ['false', 'Hidden']], value: String(item.active ?? true) },
    { name: 'title_hi', label: 'Title in Hindi', value: item.title_hi }, { name: 'title_mr', label: 'Title in Marathi', value: item.title_mr },
    { name: 'description', label: 'Announcement', type: 'textarea', required: true, value: item.description },
    { name: 'description_hi', label: 'Hindi text', type: 'textarea', value: item.description_hi },
    { name: 'description_mr', label: 'Marathi text', type: 'textarea', value: item.description_mr },
  ];
  const assist = `<div class="ai-card" style="margin-bottom:16px"><strong>Draft with AI</strong><p class="muted" style="margin:4px 0 8px">Paste rough notes. It writes the announcement and translates it into Hindi and Marathi. Check the facts before publishing.</p><textarea class="form-textarea" id="draft-notes" placeholder="e.g. Free health camp Sunday 9am to 1pm at panchayat hall, bring Aadhaar"></textarea><button type="button" class="btn btn-ghost btn-sm" style="margin-top:8px" data-act="news-draft">Write draft</button> <span id="draft-src"></span></div>`;
  return { f, assist };
}

const ACTIONS = {
  'home-prompt': (d) => { state.chatPrefill = d.q; go('assistant').then(() => { const input = $('[name=message]'); if (input) { input.value = state.chatPrefill; input.focus(); } }); },
  close: () => closeModal(),
  logout,
  nav: (d) => go(d.page),
  'auth-toggle': (d) => renderLogin(d.mode),
  demo: async (d) => { $('#a_email').value = d.e; $('#a_pw').value = d.p; $('#auth-form').requestSubmit(); },
  insights: loadInsights,
  'doc-filter': (d) => { state.docFilter = d.s; go('documents'); },
  'doc-open': (d) => {
    const doc = state.docs[d.id];
    const pending = doc.status === 'pending';
    const m = openModal(`Request #${doc.id}: ${label(doc.doc_type)}`, `<p class="muted" style="margin-bottom:12px">Submitted by ${esc(doc.applicant_name)} (${esc(doc.applicant_email)}) on ${fdate(doc.created_at)}</p>${docDetails(doc)}<h4 style="margin:18px 0 8px">Automatic pre-check</h4>${reviewPanel(doc.ai_review)}${pending ? '<label class="form-label" for="note" style="margin-top:16px">Note to the applicant (required if rejecting)</label><textarea class="form-textarea" id="note"></textarea>' : `<p style="margin-top:14px">${badge(doc.status)} ${esc(doc.admin_note)}</p>`}`,
      pending ? `<button class="btn btn-danger" data-act="doc-decide" data-id="${doc.id}" data-d="rejected">Reject</button><button class="btn btn-primary" data-act="doc-decide" data-id="${doc.id}" data-d="approved">Approve</button>` : '');
    return m;
  },
  'doc-decide': async (d) => {
    try { await api(`/documents/${d.id}/review`, { method: 'POST', body: { decision: d.d, note: $('#note').value } }); closeModal(); toast(d.d === 'approved' ? 'Request approved' : 'Request rejected'); go('documents'); } catch (e) { fail(e); }
  },
  'doc-new': () => formModal('Request a certificate', DOC_FIELDS, 'Submit request', async (data) => { await api('/documents', { method: 'POST', body: data }); toast('Request submitted'); go('documents'); }),
  'doc-pdf': async (d) => {
    try {
      const res = await api(`/documents/${d.id}/pdf`, { raw: true });
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement('a'), { href: url, download: `gramsathi-${d.id}.pdf` });
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) { fail(e); }
  },
  'user-toggle': async (d) => { try { await api(`/admin/users/${d.id}`, { method: 'PATCH', body: { is_active: d.active === '1' } }); toast(d.active === '1' ? 'Account reactivated' : 'Account deactivated'); go('users'); } catch (e) { fail(e); } },
  'ration-add': async () => {
    const users = await userOptions();
    formModal('Add ration card', [
      { name: 'user_id', label: 'Card holder', type: 'select', options: users, required: true }, { name: 'card_no', label: 'Card number', required: true },
      { name: 'card_type', label: 'Type', type: 'select', options: ['BPL', 'APL', 'AAY'] }, { name: 'distribution_point', label: 'Distribution point' },
      { name: 'validity_start', label: 'Valid from', type: 'date', required: true }, { name: 'validity_end', label: 'Valid until', type: 'date', required: true },
      { name: 'rice', label: 'Rice (kg per month)', type: 'number', min: 0, value: 10 }, { name: 'wheat', label: 'Wheat (kg per month)', type: 'number', min: 0, value: 15 },
    ], 'Save card', async (d) => {
      const items = [['Rice', d.rice], ['Wheat', d.wheat]].filter(([, q]) => q).map(([name, quantity]) => ({ name, quantity, unit: 'kg' }));
      await api('/admin/ration', { method: 'POST', body: { user_id: Number(d.user_id), card_no: d.card_no, card_type: d.card_type, distribution_point: d.distribution_point, validity_start: d.validity_start, validity_end: d.validity_end, items } });
      toast('Ration card saved'); go('ration');
    });
  },
  'center-add': () => formModal('Add Anganwadi center', [
    { name: 'name', label: 'Name', required: true }, { name: 'phone', label: 'Phone' }, { name: 'latitude', label: 'Latitude', type: 'number', step: 'any', required: true }, { name: 'longitude', label: 'Longitude', type: 'number', step: 'any', required: true },
    { name: 'open_time', label: 'Opens', type: 'time', value: '09:00', required: true }, { name: 'close_time', label: 'Closes', type: 'time', value: '16:00', required: true },
    { name: 'services', label: 'Services (comma separated)', type: 'textarea', value: 'Nutrition Support, Pre-school' }, { name: 'address', label: 'Address', type: 'textarea', required: true },
  ], 'Save center', async (d) => { d.services = d.services.split(',').map((s) => s.trim()).filter(Boolean); await api('/admin/anganwadi', { method: 'POST', body: d }); toast('Center added'); go('anganwadi'); }),
  'ben-add': async () => {
    const [users, centers] = await Promise.all([userOptions(), api('/anganwadi')]);
    formModal('Enrol a child', [
      { name: 'user_id', label: 'Guardian', type: 'select', options: users, required: true }, { name: 'center_id', label: 'Center', type: 'select', options: centers.items.map((c) => [c.id, c.name]), required: true },
      { name: 'child_name', label: "Child's name", required: true }, { name: 'age_group', label: 'Age group', type: 'select', options: [['0-6', '0 to 6 years'], ['6-14', '6 to 14 years']] },
      { name: 'enrollment_date', label: 'Enrolment date', type: 'date', required: true, value: new Date().toISOString().slice(0, 10) },
    ], 'Enrol child', async (d) => { await api('/admin/anganwadi/beneficiaries', { method: 'POST', body: { ...d, user_id: Number(d.user_id), center_id: Number(d.center_id) } }); toast('Child enrolled'); go('anganwadi'); });
  },
  'water-add': async () => {
    const users = await userOptions();
    formModal('Add water bill', [
      { name: 'user_id', label: 'Holder', type: 'select', options: users, required: true }, { name: 'connection_no', label: 'Connection number', required: true },
      { name: 'period', label: 'Billing month (YYYY-MM)', required: true, value: new Date().toISOString().slice(0, 7) }, { name: 'amount', label: 'Amount (₹)', type: 'number', min: 0, required: true },
      { name: 'due_date', label: 'Due date', type: 'date', required: true },
    ], 'Save bill', async (d) => { await api('/admin/water/bills', { method: 'POST', body: { ...d, user_id: Number(d.user_id) } }); toast('Bill saved'); go('taxes'); });
  },
  'prop-add': async () => {
    const users = await userOptions();
    formModal('Add property', [
      { name: 'user_id', label: 'Owner', type: 'select', options: users, required: true }, { name: 'property_no', label: 'Property number', required: true },
      { name: 'area_sqft', label: 'Area (sq ft)', type: 'number', min: 1, required: true }, { name: 'value', label: 'Assessed value (₹)', type: 'number', min: 0, required: true },
      { name: 'tax_rate', label: 'Tax rate (% per year)', type: 'number', step: 'any', min: 0, required: true }, { name: 'due_date', label: 'Due date', type: 'date', required: true },
      { name: 'address', label: 'Address', type: 'textarea', required: true },
    ], 'Save property', async (d) => { await api('/admin/property', { method: 'POST', body: { ...d, user_id: Number(d.user_id) } }); toast('Property saved'); go('taxes'); });
  },
  'news-add': () => { const { f, assist } = newsForm(); formModal('Write announcement', f, 'Publish', saveNews(null), assist); },
  'news-edit': (d) => { const { f } = newsForm(state.news[d.id]); formModal('Edit announcement', f, 'Save changes', saveNews(d.id)); },
  'news-del': async (d) => { if (!confirm('Delete this announcement?')) return; try { await api('/news/' + d.id, { method: 'DELETE' }); toast('Announcement deleted'); go('news'); } catch (e) { fail(e); } },
  'news-draft': async () => {
    const notes = $('#draft-notes').value.trim();
    if (notes.length < 5) return toast('Write a few notes first', true);
    $('#draft-src').textContent = 'Writing…';
    try {
      const r = await api('/ai/news-draft', { method: 'POST', body: { points: notes } });
      for (const k of ['title', 'description', 'category', 'priority', 'title_hi', 'description_hi', 'title_mr', 'description_mr']) { const el = $('#f_' + k); if (el) el.value = r[k]; }
      $('#draft-src').innerHTML = src(r.source) + (r.source === 'rules' ? ' <span class="muted">Translations need an AI key.</span>' : '');
    } catch (e) { $('#draft-src').textContent = e.message; }
  },
  'pay-water': async (d) => { try { await api(`/me/water/bills/${d.id}/pay`, { method: 'POST' }); toast('Payment recorded (simulated)'); go('taxes'); } catch (e) { fail(e); } },
  'pay-prop': async (d) => { try { await api(`/me/property/${d.id}/pay`, { method: 'POST' }); toast('Payment recorded (simulated)'); go('taxes'); } catch (e) { fail(e); } },
  'rozgar-profile-draft': async () => { const f=$('[data-form=rozgar-profile]'); const skills=f.elements.skills.value.split(',').map(x=>x.trim()).filter(Boolean); try{const r=await api('/ai/rozgar/profile-draft',{method:'POST',body:{skills,education:f.elements.education.value,experience:f.elements.bio.value,target_role:f.elements.headline.value}});f.elements.headline.value=r.headline;f.elements.bio.value=r.bio;toast(`Profile draft ready (${r.source})`);}catch(e){fail(e);} },
  'rozgar-job-draft': async () => { const f=$('[data-form=rozgar-job]'); const notes=[f.elements.title.value,f.elements.company.value,f.elements.description.value,f.elements.skills.value,f.elements.location.value].filter(Boolean).join('. '); if(notes.length<10)return toast('Enter a few job details first',true); try{const r=await api('/ai/rozgar/job-draft',{method:'POST',body:{notes}});f.elements.title.value=r.title;f.elements.description.value=r.description;if(r.skills.length)f.elements.skills.value=r.skills.join(', ');toast(`Job draft ready (${r.source})`);}catch(e){fail(e);} },
  'rozgar-summary': async (d) => { try{const r=await api(`/rozgar/jobs/${d.id}/applicant-summary`);openModal('Applicant summary',`<p>${esc(r.summary)}</p><p class="muted">${esc(r.source)} fallback · Review candidates individually; this is not an automated hiring decision.</p>`);}catch(e){fail(e);} },
  'rozgar-voice': (d) => { const SR=window.SpeechRecognition||window.webkitSpeechRecognition; if(!SR){toast('Voice input is not supported in this browser. Try Chrome.',true);return;} const target=document.getElementById(d.target); const rec=new SR(); rec.lang=state.chatLang==='mr'?'mr-IN':state.chatLang==='hi'?'hi-IN':'en-IN'; rec.interimResults=false; rec.onresult=(e)=>{target.value=(target.value+' '+e.results[0][0].transcript).trim();}; rec.onerror=()=>toast('Microphone permission or speech recognition failed.',true); rec.start(); toast('Listening… speak now'); },
  'rozgar-apply': async (d) => { let note=prompt('Add a short cover note (optional):')||''; try { if(!note){const j=(await api('/rozgar/jobs')).items.find(x=>String(x.id)===String(d.id));const pr=(await api('/rozgar/profile')).profile||{};const draft=await api('/ai/rozgar/cover-draft',{method:'POST',body:{job_title:j?.title||'this role',company:j?.company||'',skills:pr.skills||[],experience:pr.bio||''}});note=draft.cover_note;} const r=await api(`/rozgar/jobs/${d.id}/apply`,{method:'POST',body:{cover_note:note}}); toast(`Applied successfully · ${r.match_score}% skill match`); go('rozgar'); } catch(e){ fail(e); } },
  'rozgar-moderate': async (d) => { try { await api(`/admin/rozgar/jobs/${d.id}/moderate`,{method:'POST',body:{status:d.status}}); toast('Moderation decision saved'); go('rozgar'); } catch(e){ fail(e); } },
  'rozgar-applicants': async (d) => { try { const r=await api(`/rozgar/jobs/${d.id}/applicants`); const html=r.items.length?`<div class="table-wrap"><table><thead><tr><th>Applicant</th><th>Skills</th><th>Match</th><th>Status</th><th>Update</th></tr></thead><tbody>${r.items.map(a=>`<tr><td>${esc(a.name)}<small class="muted">${esc(a.email)}</small></td><td>${esc((a.skills||[]).join(', '))}</td><td>${a.match_score}%</td><td>${badge(a.status)}</td><td><select class="form-select" data-app-status="${a.id}"><option value="submitted">Submitted</option><option value="shortlisted">Shortlist</option><option value="rejected">Reject</option><option value="hired">Hire</option></select></td></tr>`).join('')}</tbody></table></div>`:empty('👥','No applicants yet'); const m=openModal('Applicants',html); m.querySelectorAll('[data-app-status]').forEach(sel=>sel.addEventListener('change',async()=>{try{await api(`/rozgar/applications/${sel.dataset.appStatus}`,{method:'PATCH',body:{status:sel.value}});toast('Applicant updated');}catch(e){fail(e);}})); } catch(e){fail(e);} },
  suggest: (d) => sendChat(d.q),
};

const saveNews = (id) => async (d) => {
  const body = { ...d, priority: Number(d.priority), active: d.active === 'true' };
  await api(id ? '/news/' + id : '/news', { method: id ? 'PUT' : 'POST', body });
  toast(id ? 'Changes saved' : 'Announcement published'); go('news');
};

document.addEventListener('click', (e) => { const el = e.target.closest('[data-act]'); if (el && ACTIONS[el.dataset.act]) { e.preventDefault(); ACTIONS[el.dataset.act](el.dataset, el); } });
document.addEventListener('submit', (e) => {
  const f = e.target.dataset?.form;
  if (f === 'user-search') { e.preventDefault(); state.userQ = new FormData(e.target).get('q'); go('users'); }
  if (f === 'chat') { e.preventDefault(); const i = e.target.elements.message; const m = i.value; i.value = ''; sendChat(m); }
  if (f === 'rozgar-profile') { e.preventDefault(); const d=Object.fromEntries(new FormData(e.target)); d.skills=d.skills.split(',').map(x=>x.trim()).filter(Boolean); d.experience_years=Number(d.experience_years||0); d.phone_public=e.target.elements.phone_public.checked; api('/rozgar/profile',{method:'PUT',body:d}).then(()=>{toast('Rozgar profile saved');go('rozgar');}).catch(fail); }
  if (f === 'rozgar-job') { e.preventDefault(); const d=Object.fromEntries(new FormData(e.target)); d.skills=d.skills.split(',').map(x=>x.trim()).filter(Boolean); d.salary_min=d.salary_min===''?null:Number(d.salary_min); d.salary_max=d.salary_max===''?null:Number(d.salary_max); api('/rozgar/jobs',{method:'POST',body:d}).then(r=>{toast(r.message);go('rozgar');}).catch(fail); }
  if (f === 'home-chat') { e.preventDefault(); const i = e.target.elements.message; const m = i.value.trim(); if (!m) return; i.value = ''; state.chatPrefill = m; go('assistant').then(() => sendChat(m)); }
});
document.addEventListener('change', (e) => {
  const c = e.target.dataset?.change;
  if (c === 'lang') { state.lang = e.target.value; go('news'); }
  if (c === 'chat-lang') state.chatLang = e.target.value;
});

// ---------------------------------------------------------------- boot
function start() { shell(); go(state.user.role === 'admin' ? (store.get('gs_page') && NAV.admin.some(([k]) => k === store.get('gs_page')) ? store.get('gs_page') : 'dashboard') : 'home'); }
(async function boot() {
  if (!state.token) return renderLogin();
  try { state.user = (await api('/auth/me')).user; start(); }
  catch { state.token = null; store.set('gs_token', null); renderLogin(); }
})();
