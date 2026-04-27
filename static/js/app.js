'use strict';
const $ = id => document.getElementById(id);
const state = { view:'chat', product:'', imageB64:null, isLoading:false, msgCount:0,
  lib:{ panel:'cats', catProduct:'', catName:'', page:1, searchTimer:null } };

const el = {
  sidebar:$('sidebar'), overlay:$('sidebarOverlay'), menuBtn:$('menuBtn'),
  sidebarClose:$('sidebarClose'), navChat:$('navChat'), navLibrary:$('navLibrary'),
  topbarTitle:$('topbarTitle'), productTabs:$('productTabs'),
  libTopbar:$('libTopbar'), libBreadcrumb:$('libBreadcrumb'), libSearchInput:$('libSearchInput'),
  viewChat:$('viewChat'), viewLibrary:$('viewLibrary'),
  welcomeState:$('welcomeState'), messages:$('messages'), inputArea:$('inputArea'),
  chatInput:$('chatInput'), sendBtn:$('sendBtn'),
  imageInput:$('imageInput'), imagePreviewStrip:$('imagePreviewStrip'),
  imagePreviewThumb:$('imagePreviewThumb'), imageRemoveBtn:$('imageRemoveBtn'),
  sourcesInfo:$('sourcesInfo'), charCount:$('charCount'),
  statusDot:$('statusDot'), statusText:$('statusText'), kbCountSidebar:$('kbCountSidebar'),
  lightbox:$('lightbox'), lightboxImg:$('lightboxImg'), lightboxClose:$('lightboxClose'),
  libPanelCats:$('libPanelCats'), libPanelList:$('libPanelList'),
  libPanelReader:$('libPanelReader'), libPanelSearch:$('libPanelSearch'),
  libCatGrid:$('libCatGrid'), libArticleList:$('libArticleList'),
  libPagination:$('libPagination'), libReader:$('libReader'),
  libSearchResults:$('libSearchResults'),
};

// ── Sidebar ─────────────────────────────────────
function openSidebar(){ el.sidebar.classList.add('open'); el.overlay.classList.add('open'); }
function closeSidebar(){ el.sidebar.classList.remove('open'); el.overlay.classList.remove('open'); }
el.menuBtn.addEventListener('click', openSidebar);
el.sidebarClose.addEventListener('click', closeSidebar);
el.overlay.addEventListener('click', closeSidebar);

// ── View Switch ──────────────────────────────────
function switchView(view){
  state.view = view;
  const isChat = view === 'chat';
  el.viewChat.style.display = isChat ? 'flex' : 'none';
  el.viewLibrary.style.display = isChat ? 'none' : 'flex';
  el.inputArea.style.display = isChat ? 'block' : 'none';
  el.productTabs.style.display = isChat ? 'flex' : 'none';
  el.libTopbar.style.display = isChat ? 'none' : 'flex';
  el.navChat.classList.toggle('active', isChat);
  el.navLibrary.classList.toggle('active', !isChat);
  el.topbarTitle.textContent = isChat ? 'Consultor IA' : 'Biblioteca';
  if (!isChat) { showLibPanel('cats'); loadCategories(); }
  closeSidebar();
}
el.navChat.addEventListener('click', () => switchView('chat'));
el.navLibrary.addEventListener('click', () => switchView('library'));

// ── Product tabs ─────────────────────────────────
el.productTabs.addEventListener('click', e => {
  const tab = e.target.closest('.product-tab');
  if (!tab) return;
  el.productTabs.querySelectorAll('.product-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  state.product = tab.dataset.product || '';
});

// ── Quick prompts ────────────────────────────────
document.addEventListener('click', e => {
  const btn = e.target.closest('.quick-prompt');
  if (!btn) return;
  el.chatInput.value = btn.dataset.prompt || '';
  el.chatInput.dispatchEvent(new Event('input'));
  el.chatInput.focus();
});

// ── Textarea ─────────────────────────────────────
el.chatInput.addEventListener('input', () => {
  el.chatInput.style.height = 'auto';
  el.chatInput.style.height = Math.min(el.chatInput.scrollHeight, 150) + 'px';
  const len = el.chatInput.value.length;
  el.charCount.textContent = len > 1800 ? `${len}/2000` : '';
});
el.chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); sendMessage(); }
});

// ── Image upload ─────────────────────────────────
el.imageInput.addEventListener('change', e => {
  const file = e.target.files[0]; if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    state.imageB64 = ev.target.result.split(',')[1];
    el.imagePreviewThumb.src = ev.target.result;
    el.imagePreviewStrip.style.display = 'block';
  };
  reader.readAsDataURL(file);
});
el.imageRemoveBtn.addEventListener('click', () => {
  state.imageB64 = null; el.imageInput.value = '';
  el.imagePreviewStrip.style.display = 'none';
});

// ── Markdown ─────────────────────────────────────
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function md(text){
  let h = text
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_,l,c) => `<pre><code>${esc(c.trim())}</code></pre>`)
    .replace(/`([^`]+)`/g, (_,c) => `<code>${esc(c)}</code>`)
    .replace(/^### (.+)$/gm,'<h3>$1</h3>').replace(/^## (.+)$/gm,'<h2>$1</h2>').replace(/^# (.+)$/gm,'<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_,alt,src) =>
      `<img src="${src}" alt="${esc(alt)}" loading="lazy" title="${esc(alt)}" />`)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^---$/gm,'<hr style="border:none;border-top:1px solid var(--border);margin:.75rem 0">')
    .replace(/^\d+\. (.+)$/gm,'<li>$1</li>').replace(/^[-*] (.+)$/gm,'<li>$1</li>')
    .replace(/\n\n/g,'</p><p>').replace(/\n/g,'<br>');
  return `<p>${h}</p>`;
}

function dlBtn(url, label){
  const ext = (url.split('.').pop()||'').toUpperCase().slice(0,5);
  return `<a href="${url}" target="_blank" rel="noopener" class="download-btn" download>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    ${esc(label)} ${ext ? `(.${ext.toLowerCase()})`:''}</a>`;
}

// ── Chat messages ────────────────────────────────
function appendMsg(role, content, meta={}){
  if (state.msgCount===0){ el.welcomeState.style.display='none'; el.messages.style.display='flex'; }
  state.msgCount++;
  const div = document.createElement('div');
  div.className = `message ${role}`;
  const avatar = role==='bot'
    ? `<div class="msg-avatar bot"><svg viewBox="0 0 32 32" fill="none"><path d="M16 2L4 8v8c0 7 5.5 12.5 12 14 6.5-1.5 12-7 12-14V8L16 2z" fill="white"/><path d="M11 16l3 3 7-7" stroke="#C8102E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>`
    : `<div class="msg-avatar user">Tú</div>`;
  let body = role==='bot' ? md(content) : `<p>${esc(content)}</p>`;
  if (meta.downloads?.length){
    body += `<div class="download-section"><h4>📥 Archivos Disponibles</h4>${meta.downloads.slice(0,8).map(d=>dlBtn(d.url,d.text)).join('')}</div>`;
  }
  if (meta.relatedLinks?.length){
    body += `<div class="related-links"><h4>🔗 Artículos Relacionados</h4>${meta.relatedLinks.slice(0,5).map(l=>`<a href="${l.url}" class="related-link" target="_blank" rel="noopener">→ ${esc(l.text)}</a>`).join('')}</div>`;
  }
  const metaTxt = meta.model ? `${meta.model} · ${meta.sources||0} fuentes · ${meta.time||''}s` : '';
  div.innerHTML = `${avatar}<div><div class="msg-bubble">${body}</div>${metaTxt?`<div class="msg-meta">${esc(metaTxt)}</div>`:''}</div>`;
  div.querySelectorAll('.msg-bubble img').forEach(img => img.addEventListener('click',()=>openLightbox(img.src,img.alt)));
  el.messages.appendChild(div);
  requestAnimationFrame(()=>{ el.messages.scrollTop = el.messages.scrollHeight; });
}

function appendTyping(){
  const div = document.createElement('div');
  div.className='message bot'; div.id='typingMsg';
  div.innerHTML=`<div class="msg-avatar bot"><svg viewBox="0 0 32 32" fill="none"><path d="M16 2L4 8v8c0 7 5.5 12.5 12 14 6.5-1.5 12-7 12-14V8L16 2z" fill="white"/><path d="M11 16l3 3 7-7" stroke="#C8102E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div><div class="msg-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;
  el.messages.appendChild(div);
  el.messages.scrollTop = el.messages.scrollHeight;
  return div;
}

// ── Send ─────────────────────────────────────────
el.sendBtn.addEventListener('click', sendMessage);
async function sendMessage(){
  const q = el.chatInput.value.trim();
  if (!q || state.isLoading) return;
  state.isLoading=true; el.sendBtn.disabled=true; el.chatInput.disabled=true;
  appendMsg('user', q);
  el.chatInput.value=''; el.chatInput.style.height='auto';
  const img = state.imageB64; state.imageB64=null; el.imageInput.value=''; el.imagePreviewStrip.style.display='none';
  const typing = appendTyping();
  el.sourcesInfo.textContent='Buscando en documentación Sophos...';
  try {
    const res = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q,image_b64:img||null,product:state.product||null})});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    typing.remove();
    if (data.error && !data.answer){ appendMsg('bot',`⚠️ ${data.error}`); return; }
    const downloads=[], related=[], seenD=new Set(), seenR=new Set();
    (data.sources||[]).forEach(s=>{
      (s.downloads||[]).forEach(d=>{ if(!seenD.has(d.url)){seenD.add(d.url);downloads.push(d);} });
      (s.related_links||[]).forEach(l=>{ if(!seenR.has(l.url)){seenR.add(l.url);related.push(l);} });
    });
    appendMsg('bot', data.answer, {downloads,relatedLinks:related,model:data.model,sources:data.sources?.length||0,time:data.response_time});
    el.sourcesInfo.textContent = data.sources ? `${data.sources.length} fuentes · ${data.response_time}s` : '';
  } catch(err){
    typing.remove();
    appendMsg('bot',`❌ Error de conexión: ${err.message}`);
    el.sourcesInfo.textContent='';
  } finally {
    state.isLoading=false; el.sendBtn.disabled=false; el.chatInput.disabled=false; el.chatInput.focus();
  }
}

// ── Lightbox ─────────────────────────────────────
function openLightbox(src,alt){ el.lightboxImg.src=src; el.lightboxImg.alt=alt||''; el.lightbox.style.display='flex'; }
function closeLightbox(){ el.lightbox.style.display='none'; }
el.lightboxClose.addEventListener('click', closeLightbox);
el.lightbox.addEventListener('click', e=>{ if(e.target===el.lightbox) closeLightbox(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeLightbox(); });

// ════════════════════════════════════════════════
// BIBLIOTECA — Local data panels
// ════════════════════════════════════════════════
const PRODUCT_META = {
  firewall:  {icon:'🔥', name:'Sophos Firewall',  desc:'NAT, VPN, políticas, SD-WAN'},
  endpoint:  {icon:'🛡️', name:'Sophos Endpoint',  desc:'Intercept X, agentes, exclusiones'},
  server:    {icon:'🖥️', name:'Sophos Server',    desc:'Server Protection, agentes servidor'},
  email:     {icon:'✉️', name:'Sophos Email',     desc:'Antispam, SPF/DKIM, cuarentena'},
  xdr:       {icon:'🔍', name:'Sophos XDR/MDR',   desc:'Detección y respuesta extendida'},
  ztna:      {icon:'🌐', name:'Sophos ZTNA/VPN',  desc:'Zero Trust, acceso remoto seguro'},
  general:   {icon:'📄', name:'General',           desc:'Documentación general Sophos'},
};

function showLibPanel(panel){
  state.lib.panel = panel;
  ['Cats','List','Reader','Search'].forEach(p => {
    const el2 = $(`libPanel${p}`);
    if(el2) el2.style.display = (p.toLowerCase()===panel) ? 'flex' : 'none';
  });
  if($(`libPanel${panel.charAt(0).toUpperCase()+panel.slice(1)}`))
    $(`libPanel${panel.charAt(0).toUpperCase()+panel.slice(1)}`).style.flexDirection='column';
  updateBreadcrumb();
}

function updateBreadcrumb(){
  const {panel, catName} = state.lib;
  let html = `<span class="bc-link" onclick="showLibPanel('cats');loadCategories()">Biblioteca</span>`;
  if(panel==='list') html += `<span class="bc-sep">›</span><span class="bc-cur">${esc(catName)}</span>`;
  if(panel==='reader') html += `<span class="bc-sep">›</span><span class="bc-link" onclick="loadArticleList(state.lib.catProduct,1)">${esc(catName)}</span><span class="bc-sep">›</span><span class="bc-cur">Artículo</span>`;
  if(panel==='search') html += `<span class="bc-sep">›</span><span class="bc-cur">Búsqueda</span>`;
  el.libBreadcrumb.innerHTML = html;
}

async function loadCategories(){
  el.libCatGrid.innerHTML = '<div class="lib-loading">Cargando categorías...</div>';
  showLibPanel('cats');
  try {
    const res = await fetch('/api/library/categories');
    const data = await res.json();
    if(!data.categories?.length){ el.libCatGrid.innerHTML='<div class="lib-loading">Sin datos locales.</div>'; return; }
    el.libCatGrid.innerHTML = data.categories.map(c => {
      const m = PRODUCT_META[c.id] || {icon:'📄',name:c.id,desc:''};
      return `<button class="lib-cat-card" onclick="loadArticleList('${c.id}',1,'${esc(m.name)}')">
        <div class="lib-cat-icon">${m.icon}</div>
        <div class="lib-cat-name">${m.name}</div>
        <div class="lib-cat-count">${c.count} artículos</div>
        <div class="lib-cat-desc">${m.desc}</div>
      </button>`;
    }).join('');
  } catch(e){ el.libCatGrid.innerHTML=`<div class="lib-loading">Error: ${esc(e.message)}</div>`; }
}

async function loadArticleList(product, page=1, name=''){
  state.lib.catProduct = product;
  state.lib.page = page;
  if(name) state.lib.catName = name;
  showLibPanel('list');
  el.libArticleList.innerHTML = '<div style="text-align:center;color:var(--txt3);padding:2rem">Cargando artículos...</div>';
  try {
    const res = await fetch(`/api/library/articles?product=${product}&page=${page}`);
    const data = await res.json();
    if(!data.articles?.length){ el.libArticleList.innerHTML='<div style="text-align:center;color:var(--txt3);padding:2rem">Sin artículos en esta categoría.</div>'; return; }
    // Back button
    el.libArticleList.innerHTML = `<div class="lib-back-row">
      <button class="lib-back-btn" onclick="showLibPanel('cats');loadCategories()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 5l-7 7 7 7"/></svg> Categorías</button>
      <span class="lib-panel-title">${esc(state.lib.catName)} (${data.total})</span>
    </div>` +
    data.articles.map(a => `<div class="lib-article-item" onclick="loadArticle('${esc(a.hash)}','${esc(a.title.replace(/'/g,"\\'"))}')">
      <div class="lib-article-title">${esc(a.title)}</div>
      ${a.snippet ? `<div class="lib-article-snippet">${esc(a.snippet)}</div>` : ''}
      <div class="lib-article-meta">
        ${a.has_downloads ? '<span class="lib-article-badge has-dl">📥 Descargas</span>' : ''}
        ${a.has_images ? '<span class="lib-article-badge">🖼 Imágenes</span>' : ''}
      </div>
    </div>`).join('');
    // Pagination
    el.libPagination.innerHTML = data.pages > 1 ? `
      <button class="lib-page-btn" onclick="loadArticleList('${product}',${page-1})" ${page<=1?'disabled':''}>← Anterior</button>
      <span class="lib-page-info">Pág ${page} / ${data.pages}</span>
      <button class="lib-page-btn" onclick="loadArticleList('${product}',${page+1})" ${page>=data.pages?'disabled':''}>Siguiente →</button>` : '';
  } catch(e){ el.libArticleList.innerHTML=`<div style="text-align:center;color:var(--txt3);padding:2rem">Error: ${esc(e.message)}</div>`; }
}

async function loadArticle(hash, title=''){
  showLibPanel('reader');
  state.lib.catName = title || state.lib.catName;
  updateBreadcrumb();
  el.libReader.innerHTML = '<div style="text-align:center;color:var(--txt3);padding:2rem">Cargando artículo...</div>';
  try {
    const res = await fetch(`/api/library/article/${hash}`);
    const data = await res.json();
    if(data.error){ el.libReader.innerHTML=`<p style="color:var(--txt3)">${esc(data.error)}</p>`; return; }
    let html = `<div class="lib-back-row">
      <button class="lib-back-btn" onclick="loadArticleList(state.lib.catProduct,state.lib.page)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 5l-7 7 7 7"/></svg> Volver</button>
      ${data.url ? `<a href="${data.url}" target="_blank" rel="noopener" style="font-size:.72rem;color:#5b9bd5;margin-left:auto;text-decoration:none">Ver en Sophos ↗</a>` : ''}
    </div>`;
    html += `<div style="padding:1rem"><h1 class="lib-reader" style="font-size:1.15rem;font-weight:700;margin-bottom:1rem">${esc(data.title)}</h1>`;
    html += `<div class="lib-reader">${md(data.text || '')}</div>`;
    if(data.downloads?.length){
      html += `<div class="lib-reader-downloads"><h4>📥 Archivos Disponibles</h4>${data.downloads.slice(0,8).map(d=>dlBtn(d.url,d.text)).join('')}</div>`;
    }
    if(data.related_links?.length){
      html += `<div class="lib-reader-downloads" style="margin-top:.75rem"><h4>🔗 Artículos Relacionados</h4>${data.related_links.slice(0,6).map(l=>`<a href="${l.url}" target="_blank" rel="noopener" class="related-link">→ ${esc(l.text)}</a>`).join('')}</div>`;
    }
    html += '</div>';
    el.libReader.innerHTML = html;
    el.libReader.querySelectorAll('img').forEach(img=>img.addEventListener('click',()=>openLightbox(img.src,img.alt)));
  } catch(e){ el.libReader.innerHTML=`<p style="color:var(--txt3)">Error: ${esc(e.message)}</p>`; }
}

// ── Library search ────────────────────────────────
el.libSearchInput && el.libSearchInput.addEventListener('input', e => {
  const q = e.target.value.trim();
  clearTimeout(state.lib.searchTimer);
  if(!q){ if(state.lib.panel==='search') showLibPanel('cats'); return; }
  state.lib.searchTimer = setTimeout(()=>searchLibrary(q), 350);
});

async function searchLibrary(query){
  showLibPanel('search');
  el.libSearchResults.innerHTML = '<div class="lib-loading">Buscando...</div>';
  try {
    const res = await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,top_k:12})});
    const data = await res.json();
    if(!data.results?.length){
      el.libSearchResults.innerHTML='<div class="lib-no-results">Sin resultados. Intenta otros términos.</div>'; return;
    }
    el.libSearchResults.innerHTML = `<div class="lib-back-row">
      <span class="lib-panel-title">${data.count} resultados para "${esc(query)}"</span>
    </div>` +
    data.results.map(r=>`<div class="lib-article-item" onclick="loadArticle('${esc((r.url||'').split('/').pop()||r.title.replace(/\W+/g,'-'))}','${esc(r.title.replace(/'/g,"\\'"))}')">
      <div class="lib-article-title">${esc(r.title)}</div>
      ${r.heading ? `<div style="font-size:.72rem;color:var(--accent);margin:.15rem 0">${esc(r.heading)}</div>` : ''}
      <div class="lib-article-snippet">${esc((r.chunk||'').slice(0,200))}…</div>
      <div class="lib-article-meta"><span class="lib-article-badge">Score: ${r.score}</span><span class="lib-article-badge">${r.chunk_type}</span>
      ${r.url?`<a href="${r.url}" target="_blank" rel="noopener" style="font-size:.7rem;color:#5b9bd5;margin-left:auto" onclick="event.stopPropagation()">Fuente ↗</a>`:''}
      </div>
    </div>`).join('');
  } catch(e){ el.libSearchResults.innerHTML=`<div class="lib-no-results">Error: ${esc(e.message)}</div>`; }
}

// ── Status ───────────────────────────────────────
async function checkStatus(){
  try {
    const res = await fetch('/api/status');
    const d = await res.json();
    const ok = d.groq_ok;
    el.statusDot.className = `status-dot ${ok?'online':'offline'}`;
    el.statusText.textContent = ok ? 'Groq Conectado' : 'Sin conexión';
    if(el.kbCountSidebar) el.kbCountSidebar.textContent = (d.kb_count||d.local_articles||'0').toLocaleString();
  } catch {
    el.statusDot.className='status-dot offline';
    el.statusText.textContent='Sin conexión';
  }
}

checkStatus();
setInterval(checkStatus, 60000);
el.chatInput.focus();
