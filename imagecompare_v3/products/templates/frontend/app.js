const API_BASE = '/api';
let currentSearchId = null;
let allProducts = [];
let allLensResults = [];
let viewMode = 'grid';
let activeFilters = { type: 'all', website: '', sort: 'price_asc', min: '', max: '' };
let lensFilter = 'all';
let lensWebsiteFilter = '';

// ── Nav ──────────────────────────────────────────────────────────
function showPage(id, navEl) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  if (navEl) navEl.classList.add('active');
  const titles = { dashboard:'Dashboard', upload:'Upload & Search', history:'Search History', results:'All Products', compare:'Price Comparison', lens:'Lens Results', scrape:'Scraper Control', export:'Download Data' };
  document.getElementById('page-title').textContent = titles[id] || id;
  if (id === 'dashboard') loadDashboard();
  if (id === 'history') loadHistory();
  if (id === 'results') loadProducts();
  if (id === 'compare') loadComparison();
  if (id === 'lens') loadLensResults();
  if (id === 'scrape') loadScrapeInfo();
  if (id === 'export') loadExportList();
}
function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }
function refreshCurrent() { const a = document.querySelector('.page.active').id.replace('page-',''); showPage(a, document.querySelector('.nav-item.active')); }
if (window.innerWidth <= 768) document.getElementById('menu-btn').style.display = 'flex';

// ── API ──────────────────────────────────────────────────────────
function getCsrfToken() { const m = document.cookie.match(/csrftoken=([^;]+)/); return m ? m[1] : ''; }
async function apiFetch(url, opts={}) {
  const res = await fetch(API_BASE + url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
async function apiPost(url, body={}) {
  const res = await fetch(API_BASE + url, { method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken()}, body:JSON.stringify(body) });
  return res.json();
}
function showToast(msg, ms=3000) {
  const t = document.getElementById('toast'); document.getElementById('toast-msg').textContent = msg;
  t.classList.add('show'); setTimeout(() => t.classList.remove('show'), ms);
}
function fmtPrice(p) { if (!p || p===0) return '—'; if (typeof p==='string'&&p.trim()) return p.trim(); if (typeof p==='number'&&p>0) return '₹'+p.toLocaleString('en-IN'); return '—'; }
function fmtStars(r) { const n=parseFloat(r); if(isNaN(n)) return r; const f=Math.round(n); return '★'.repeat(f)+'☆'.repeat(Math.max(0,5-f)); }
function getDomain(url) { try { return new URL(url).hostname.replace(/^www\./,''); } catch { return url; } }
function siteColor(s) { const m={amazon:'#FF9900',flipkart:'#2874F0',myntra:'#FF3F6C',meesho:'#7B2FBE',nykaa:'#FC2779',ajio:'#005596'}; const l=(s||'').toLowerCase(); for(const k of Object.keys(m)) if(l.includes(k)) return m[k]; return '#6B7280'; }

// ── Excel downloads ──────────────────────────────────────────────
function downloadCurrentExcel() {
  if (!currentSearchId) { showToast('No search selected'); return; }
  window.open(`/api/searches/${currentSearchId}/export/`, '_blank');
}
function downloadLensExcel() {
  if (!currentSearchId) { showToast('No search selected'); return; }
  window.open(`/api/searches/${currentSearchId}/export/lens/`, '_blank');
}
function downloadAllExcel() {
  window.open('/api/export/all/', '_blank');
}
function downloadSearchExcel(id) {
  window.open(`/api/searches/${id}/export/`, '_blank');
}
function downloadSearchLensExcel(id) {
  window.open(`/api/searches/${id}/export/lens/`, '_blank');
}

// ── Export page ──────────────────────────────────────────────────
async function loadExportList() {
  const el = document.getElementById('export-list');
  el.innerHTML = `<div class="loading-state"><div class="spinner"></div></div>`;
  try {
    const searches = await apiFetch('/searches/');
    if (!searches.length) {
      el.innerHTML = `<div class="empty-state" style="padding:30px"><div class="empty-icon">📭</div><div class="empty-title">No searches yet</div><div class="empty-sub">Upload an image to create a search</div></div>`;
      return;
    }
    el.innerHTML = searches.map(s => `
      <div class="history-item">
        <div style="width:40px;height:40px;border-radius:8px;background:var(--bg);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0">🖼</div>
        <div class="history-info">
          <div class="history-keyword">#${s.id} — ${s.search_keyword || 'Unnamed search'}</div>
          <div class="history-meta">${s.category||'—'} · ${s.classifier_phase||'—'} · ${s.shopping_count||0} shopping · ${s.visual_count||0} visual</div>
        </div>
        <div class="history-actions">
          <button class="btn btn-green btn-sm" onclick="downloadSearchExcel(${s.id})">📥 Products</button>
          <button class="btn btn-sm" onclick="downloadSearchLensExcel(${s.id})">🔍 Lens only</button>
        </div>
      </div>
    `).join('');
  } catch {
    el.innerHTML = `<div class="error-state">⚠ Could not load searches</div>`;
  }
}

// ── Dashboard ────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const searches = await apiFetch('/searches/');
    document.getElementById('stat-searches').textContent = searches.length;
    document.getElementById('history-badge').textContent = searches.length;
    let total=0, priced=0, unscraped=0; const wc={};
    for (const s of searches.slice(0,5)) {
      try {
        const d = await apiFetch('/searches/'+s.id+'/');
        const p = d.products||[];
        total+=p.length; priced+=p.filter(x=>x.price_numeric>0).length;
        unscraped+=(d.lens_results||[]).filter(r=>!r.scraped&&r.result_type==='visual').length;
        for(const x of p){const site=x.website||getDomain(x.product_link||'');wc[site]=(wc[site]||0)+1;}
      } catch {}
    }
    document.getElementById('stat-total').textContent=total;
    document.getElementById('stat-priced').textContent=priced;
    document.getElementById('stat-unscrapped').textContent=unscraped;
    document.getElementById('products-badge').textContent=total;
    const re=document.getElementById('recent-searches');
    re.innerHTML = !searches.length
      ? `<div class="empty-state" style="padding:20px"><div class="empty-icon">📭</div><div class="empty-title">No searches yet</div></div>`
      : searches.slice(0,5).map(s=>`
        <div class="history-item" onclick="selectSearch(${s.id})">
          <div style="width:36px;height:36px;border-radius:6px;background:var(--bg);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:18px">🖼</div>
          <div class="history-info"><div class="history-keyword">${s.search_keyword||'Unnamed'}</div><div class="history-meta">#${s.id} · ${s.category||'—'}</div></div>
          <span class="badge badge-gray">#${s.id}</span>
        </div>`).join('');
    const entries=Object.entries(wc).sort((a,b)=>b[1]-a[1]).slice(0,6);
    const ce=document.getElementById('website-chart');
    ce.innerHTML = !entries.length
      ? `<div class="empty-state" style="padding:20px"><div class="empty-icon">📊</div><div class="empty-title">No data yet</div></div>`
      : `<div style="display:flex;flex-direction:column;gap:10px">`+entries.map(([s,c])=>{const mx=Math.max(...entries.map(e=>e[1]));return`<div class="price-bar-row"><div class="price-bar-label">${s}</div><div class="price-bar-track"><div class="price-bar-fill" style="width:${Math.round(c/mx*100)}%;background:${siteColor(s)}"></div></div><div class="price-bar-value">${c}</div></div>`;}).join('')+`</div>`;
  } catch { showToast('Could not load dashboard'); }
}

// ── History ──────────────────────────────────────────────────────
async function loadHistory() {
  const el=document.getElementById('history-list');
  el.innerHTML=`<div class="card"><div class="loading-state"><div class="spinner"></div></div></div>`;
  try {
    const s=await apiFetch('/searches/');
    document.getElementById('history-badge').textContent=s.length;
    el.innerHTML = !s.length
      ? `<div class="card"><div class="empty-state"><div class="empty-icon">📭</div><div class="empty-title">No searches yet</div></div></div>`
      : `<div class="card" style="padding:0;overflow:hidden">`+s.map(x=>`
        <div class="history-item" onclick="selectSearch(${x.id})">
          <div style="width:44px;height:44px;border-radius:8px;background:var(--bg);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0">🖼</div>
          <div class="history-info">
            <div class="history-keyword">${x.search_keyword||'Unnamed search'}</div>
            <div class="history-meta">#${x.id} · ${x.category||'—'} · ${x.shopping_count||0} priced · ${x.visual_count||0} visual</div>
          </div>
          <div class="history-actions">
            <button class="btn btn-green btn-sm" onclick="event.stopPropagation();downloadSearchExcel(${x.id})">📥 Excel</button>
            <button class="btn btn-sm" onclick="event.stopPropagation();selectSearch(${x.id})">Open →</button>
          </div>
        </div>`).join('')+`</div>`;
  } catch { el.innerHTML=`<div class="error-state">⚠ Could not load history</div>`; }
}
function selectSearch(id) { currentSearchId=id; showPage('results', document.querySelectorAll('.nav-item')[3]); }

// ── Products ─────────────────────────────────────────────────────
async function loadProducts() {
  if (!currentSearchId) {
    try { const s=await apiFetch('/searches/'); if(s.length) currentSearchId=s[0].id; else { document.getElementById('products-empty').style.display='block'; return; } } catch { return; }
  }
  document.getElementById('products-loading').style.display='block';
  document.getElementById('product-grid-view').innerHTML='';
  document.getElementById('product-table-body').innerHTML='';
  document.getElementById('products-empty').style.display='none';
  const se=document.getElementById('results-session');
  se.style.display='flex';
  document.getElementById('results-session-label').textContent=`Search #${currentSearchId}`;
  try {
    const data=await apiFetch(`/searches/${currentSearchId}/products/?order=${activeFilters.sort==='price_asc'?'price_asc':'price_desc'}`);
    document.getElementById('results-session-sub').textContent=`${data.search_keyword} · ${data.total_products} products · ${data.with_price} priced`;
    allProducts=data.products||[];
    const sites=[...new Set(allProducts.map(p=>p.website||getDomain(p.product_link||'')).filter(Boolean))];
    const ss=document.getElementById('filter-website'); const cur=ss.value;
    ss.innerHTML=`<option value="">All websites</option>`+sites.map(s=>`<option value="${s}">${s}</option>`).join('');
    if(cur) ss.value=cur;
    renderProducts(allProducts);
  } catch(e) { document.getElementById('products-loading').style.display='none'; }
}
function renderProducts(prods) {
  document.getElementById('products-loading').style.display='none';
  let f=prods;
  if(activeFilters.type==='shopping') f=f.filter(p=>p.price_numeric>0);
  if(activeFilters.type==='visual') f=f.filter(p=>!p.price_numeric||p.price_numeric===0);
  if(activeFilters.website) f=f.filter(p=>(p.website||'').toLowerCase().includes(activeFilters.website.toLowerCase()));
  if(activeFilters.min) f=f.filter(p=>p.price_numeric>=parseFloat(activeFilters.min));
  if(activeFilters.max) f=f.filter(p=>p.price_numeric<=parseFloat(activeFilters.max));
  const gs=document.getElementById('global-search').value.toLowerCase();
  if(gs) f=f.filter(p=>(p.product_name||'').toLowerCase().includes(gs)||(p.website||'').toLowerCase().includes(gs));
  if(activeFilters.sort==='rating') f.sort((a,b)=>parseFloat(b.rating||0)-parseFloat(a.rating||0));
  document.getElementById('product-count-label').textContent=`${f.length} product${f.length!==1?'s':''}`;
  if(!f.length){document.getElementById('products-empty').style.display='block';document.getElementById('product-grid-view').innerHTML='';return;}
  document.getElementById('products-empty').style.display='none';
  const prices=f.map(p=>p.price_numeric).filter(p=>p>0);
  const lo=prices.length?Math.min(...prices):null, hi=prices.length?Math.max(...prices):null;
  document.getElementById('product-grid-view').innerHTML=f.map(p=>{
    const iL=lo!==null&&p.price_numeric===lo&&p.price_numeric>0, iH=hi!==null&&p.price_numeric===hi&&p.price_numeric>0&&prices.length>1;
    const th=p.thumbnail||p.image||p.image_url||p.thumbnail_url||p.product_image||p.img||p.picture||'';
    const site=p.website||getDomain(p.product_link||'')||'—';
    return `<div class="product-card">
      <div>${th?`<img class="product-img" src="${th}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`:''}
      <div class="product-img-placeholder" style="${th?'display:none':''}">🛍</div></div>
      <div class="product-body">
        <div class="product-source">${site}</div>
        <div class="product-name" title="${p.product_name||''}">${p.product_name||'Untitled'}</div>
        <div class="product-meta"><span class="product-price ${iL?'lowest':iH?'highest':''}">${fmtPrice(p.price||p.price_numeric)}</span></div>
        ${p.rating?`<div class="product-rating"><span class="stars">${fmtStars(p.rating)}</span> ${p.rating}${p.reviews?' ('+p.reviews+')':''}</div>`:''}
        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px">
          <span class="badge ${p.price_numeric>0?'badge-green':'badge-gray'}">${p.price_numeric>0?'Priced':'Visual'}</span>
          ${iL?'<span class="badge badge-green">Lowest</span>':''}${iH?'<span class="badge badge-red">Highest</span>':''}
        </div>
      </div>
      <div class="product-footer" style="display:flex;gap:6px">
        <a href="${p.product_link||'#'}" target="_blank" rel="noopener" class="btn btn-sm" style="flex:1;justify-content:center">Open Product↗</a>
        <button class="btn btn-sm" title="${p.last_scraped_at?'Last checked: '+new Date(p.last_scraped_at).toLocaleString():'Refresh price'}" onclick="rescrapeProduct(${p.id}, this)">🔄</button>
      </div>
    </div>`;
  }).join('');
  document.getElementById('product-table-body').innerHTML=f.map(p=>{
    const iL=lo!==null&&p.price_numeric===lo&&p.price_numeric>0, iH=hi!==null&&p.price_numeric===hi&&p.price_numeric>0&&prices.length>1;
    const th=p.thumbnail||p.image||p.image_url||p.thumbnail_url||p.product_image||p.img||p.picture||'';
    return `<tr class="${iL?'highlight-green':iH?'highlight-red':''}">
      <td style="max-width:240px"><div style="display:flex;align-items:center;gap:8px">
        ${th?`<img src="${th}" style="width:36px;height:36px;object-fit:cover;border-radius:6px;border:1px solid var(--border)" onerror="this.style.display='none'">`:`<div style="width:36px;height:36px;background:var(--bg);border-radius:6px;display:flex;align-items:center;justify-content:center">🛍</div>`}
        <span style="font-size:13px">${p.product_name||'—'}</span></div></td>
      <td>${p.website||getDomain(p.product_link||'')||'—'}</td>
      <td style="font-weight:${iL||iH?'600':'400'}">${fmtPrice(p.price||p.price_numeric)}</td>
      <td>${p.rating?`<span class="stars">${fmtStars(p.rating)}</span> ${p.rating}`:'—'}</td>
      <td><span class="badge ${p.price_numeric>0?'badge-green':'badge-gray'}">${p.price_numeric>0?'Priced':'Visual'}</span></td>
      <td style="display:flex;gap:4px">
        <a href="${p.product_link||'#'}" target="_blank" class="btn btn-sm" rel="noopener">Open ↗</a>
        <button class="btn btn-sm" onclick="rescrapeProduct(${p.id}, this)">🔄</button>
      </td>
    </tr>`;
  }).join('');
}
function setFilter(k,v,el){activeFilters[k]=v;document.querySelectorAll('#type-toggle .toggle-item').forEach(t=>t.classList.remove('active'));el.classList.add('active');renderProducts(allProducts);}
function applyFilters(){activeFilters.website=document.getElementById('filter-website').value;activeFilters.sort=document.getElementById('filter-sort').value;activeFilters.min=document.getElementById('filter-min').value;activeFilters.max=document.getElementById('filter-max').value;renderProducts(allProducts);}
function clearFilters(){document.getElementById('filter-website').value='';document.getElementById('filter-sort').value='price_asc';document.getElementById('filter-min').value='';document.getElementById('filter-max').value='';activeFilters={type:'all',website:'',sort:'price_asc',min:'',max:''};document.querySelectorAll('#type-toggle .toggle-item').forEach((t,i)=>t.classList.toggle('active',i===0));renderProducts(allProducts);}
function filterProducts(){renderProducts(allProducts);}
function setView(m){viewMode=m;document.getElementById('product-grid-view').style.display=m==='grid'?'grid':'none';document.getElementById('product-list-view').style.display=m==='list'?'block':'none';}

// ── Comparison ───────────────────────────────────────────────────
async function loadComparison() {
  if(!currentSearchId){try{const s=await apiFetch('/searches/');if(s.length)currentSearchId=s[0].id;}catch{return;}}
  document.getElementById('compare-session').style.display='flex';
  document.getElementById('compare-session-label').textContent=`Price comparison — Search #${currentSearchId}`;
  try {
    const data=await apiFetch(`/searches/${currentSearchId}/products/?order=price_asc`);
    const prods=(data.products||[]).filter(p=>p.price_numeric>0);
    document.getElementById('compare-session-sub').textContent=`${data.search_keyword} · ${prods.length} priced products`;
    if(!prods.length){['cmp-low','cmp-high','cmp-avg'].forEach(id=>document.getElementById(id).textContent='—');document.getElementById('cmp-sites').textContent='0';return;}
    const ps=prods.map(p=>p.price_numeric), lo=Math.min(...ps), hi=Math.max(...ps), avg=ps.reduce((a,b)=>a+b,0)/ps.length;
    const lP=prods.find(p=>p.price_numeric===lo), hP=prods.find(p=>p.price_numeric===hi);
    document.getElementById('cmp-low').textContent=fmtPrice(lo); document.getElementById('cmp-low-site').textContent=lP?.website||getDomain(lP?.product_link||'');
    document.getElementById('cmp-high').textContent=fmtPrice(hi); document.getElementById('cmp-high-site').textContent=hP?.website||getDomain(hP?.product_link||'');
    document.getElementById('cmp-avg').textContent=fmtPrice(Math.round(avg)); document.getElementById('cmp-count').textContent=`from ${prods.length} listings`;
    const bw={};for(const p of prods){const s=p.website||getDomain(p.product_link||'')||'Other';if(!bw[s])bw[s]=[];bw[s].push(p.price_numeric);}
    const sa=Object.entries(bw).map(([s,p])=>({s,avg:p.reduce((a,b)=>a+b,0)/p.length,cnt:p.length})).sort((a,b)=>a.avg-b.avg);
    document.getElementById('cmp-sites').textContent=sa.length;
    const maxA=Math.max(...sa.map(x=>x.avg));
    document.getElementById('price-bars').innerHTML=sa.map(x=>`<div class="price-bar-row"><div class="price-bar-label">${x.s}</div><div class="price-bar-track"><div class="price-bar-fill" style="width:${Math.round(x.avg/maxA*100)}%;background:${siteColor(x.s)}"></div></div><div class="price-bar-value">${fmtPrice(Math.round(x.avg))}</div></div>`).join('');
    document.getElementById('cmp-table-body').innerHTML=prods.map(p=>{const iL=p.price_numeric===lo,iH=p.price_numeric===hi;return`<tr class="${iL?'highlight-green':iH&&ps.length>1?'highlight-red':''}"><td>${p.website||getDomain(p.product_link||'')||'—'}</td><td style="font-weight:${iL||iH?600:400}">${fmtPrice(p.price||p.price_numeric)}${iL?'<span class="badge badge-green" style="margin-left:4px">Lowest</span>':''}${iH&&ps.length>1?'<span class="badge badge-red" style="margin-left:4px">Highest</span>':''}</td><td>${p.rating?`<span class="stars">${fmtStars(p.rating)}</span> ${p.rating}`:'—'}</td><td><a href="${p.product_link||'#'}" target="_blank" class="btn btn-sm" rel="noopener">Open ↗</a></td></tr>`;}).join('');
  } catch { showToast('Could not load comparison'); }
}

// ── Lens ─────────────────────────────────────────────────────────
async function loadLensResults() {
  if(!currentSearchId){try{const s=await apiFetch('/searches/');if(s.length)currentSearchId=s[0].id;}catch{return;}}
  document.getElementById('lens-loading').style.display='block';
  document.getElementById('lens-grid').innerHTML=''; document.getElementById('lens-empty').style.display='none';
  document.getElementById('lens-session').style.display='flex';
  document.getElementById('lens-session-label').textContent=`Lens results — Search #${currentSearchId}`;
  try {
    const data=await apiFetch(`/searches/${currentSearchId}/lens-results/`);
    allLensResults=data.results||[];
    document.getElementById('lens-session-sub').textContent=`${data.search_keyword} · ${data.counts?.shopping_with_price||0} shopping · ${data.counts?.visual_no_price||0} visual`;

    // Populate website dropdown — same pattern as All Products' filter-website.
    // Guarded with `if (ws)` so a missing/renamed element degrades gracefully
    // instead of throwing and silently blanking the whole page via the catch below.
    const sites=[...new Set(allLensResults.map(r=>r.source||getDomain(r.link||'')).filter(Boolean))].sort();
    const ws=document.getElementById('lens-filter-website');
    if (ws) {
      const cur=ws.value;
      ws.innerHTML=`<option value="">All websites</option>`+sites.map(s=>`<option value="${s}">${s}</option>`).join('');
      if(cur) ws.value=cur;
    }

    renderLensResults();
  } catch(e) {
    console.error('loadLensResults failed:', e);
    document.getElementById('lens-loading').style.display='none';
    document.getElementById('lens-empty').style.display='block';
  }
}

function renderLensResults() {
  document.getElementById('lens-loading').style.display='none';
  let f=allLensResults;
  if(lensFilter==='shopping') f=f.filter(r=>r.result_type==='shopping');
  if(lensFilter==='visual') f=f.filter(r=>r.result_type==='visual');
  if(lensFilter==='unscraped') f=f.filter(r=>!r.scraped&&r.result_type==='visual');
  if(lensWebsiteFilter) f=f.filter(r=>(r.source||getDomain(r.link||'')||'')===lensWebsiteFilter);
  if(!f.length){document.getElementById('lens-grid').innerHTML='';document.getElementById('lens-empty').style.display='block';return;}
  document.getElementById('lens-empty').style.display='none';
  document.getElementById('lens-grid').innerHTML=f.map(r=>{
    const th=r.thumbnail||r.image_url||''; const site=r.source||getDomain(r.link||'')||'—';
    const displayPrice = r.scraped_price || r.price || (r.result_type==='visual' ? 'No price yet' : '—');
    const displayRating = r.scraped_rating || r.rating || '';
    return `<div class="product-card">
      <div>${th?`<img class="product-img" src="${th}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`:''}
      <div class="product-img-placeholder" style="${th?'display:none':''}">🔍</div></div>
      <div class="product-body">
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          <span class="badge ${r.result_type==='shopping'?'badge-green':'badge-blue'}">${r.result_type}</span>
          ${r.scraped?'<span class="badge badge-gray">scraped</span>':''}
        </div>
        <div class="product-source">${site}</div>
        <div class="product-name">${r.title||'—'}</div>
        <div class="product-meta"><span class="product-price">${displayPrice}</span></div>
        ${displayRating?`<div class="product-rating"><span class="stars">${fmtStars(displayRating)}</span> ${displayRating}${r.reviews?' ('+r.reviews+')':''}</div>`:''}
      </div>
      <div class="product-footer"><div style="display:flex;gap:6px;flex-wrap:wrap">
        <a href="${r.link||'#'}" target="_blank" rel="noopener" class="btn btn-sm" style="flex:1;justify-content:center">Open ↗</a>
        ${r.result_type==='visual'&&!r.scraped?`<button class="btn btn-sm btn-primary" onclick="scrapeSingle(${r.id})">Scrape</button>`:''}
        ${r.link?`<button class="btn btn-sm" title="Re-check current price" onclick="rescrapeLensResult(${r.id})">🔄 Rescrape</button>`:''}
      </div></div>
      ${r.product_id?`<div style="padding:0 14px 10px"><span class="badge badge-green">✓ In products</span></div>`:(r.scraped?`<div style="padding:0 14px 10px"><span class="badge badge-gray">Not promoted</span></div>`:'')}
    </div>`;
  }).join('');
}
function setLensFilter(v,el){lensFilter=v;document.querySelectorAll('#lens-type-toggle .toggle-item').forEach(t=>t.classList.remove('active'));el.classList.add('active');renderLensResults();}

function applyLensWebsiteFilter() {
  const el = document.getElementById('lens-filter-website');
  lensWebsiteFilter = el ? el.value : '';
  renderLensResults();
}
async function scrapeSingle(id){showToast('Scraping #'+id+'...');try{await apiPost(`/lens-results/${id}/scrape/`);showToast('Done!');loadLensResults();}catch{showToast('Scrape failed');}}

// ── Scraper ──────────────────────────────────────────────────────
async function loadScrapeInfo() {
  if(!currentSearchId){try{const s=await apiFetch('/searches/');if(s.length)currentSearchId=s[0].id;}catch{return;}}
  document.getElementById('scrape-session').style.display='flex';
  document.getElementById('scrape-session-label').textContent=`Scraper — Search #${currentSearchId}`;
  try {
    const data=await apiFetch(`/searches/${currentSearchId}/lens-results/`);
    const sh=(data.results||[]).filter(r=>r.result_type==='shopping'&&!r.scraped).length;
    const vi=(data.results||[]).filter(r=>r.result_type==='visual'&&!r.scraped).length;
    document.getElementById('promote-pending').textContent=sh;
    document.getElementById('visual-pending').textContent=vi;
    document.getElementById('scrape-session-sub').textContent=`${data.search_keyword} · ${sh} shopping pending · ${vi} visual unscraped`;
  } catch {}
}
function logScrape(msg){const el=document.getElementById('scrape-log');el.innerHTML+=`\n[${new Date().toLocaleTimeString()}] ${msg}`;el.scrollTop=el.scrollHeight;}
async function runPromote(){const btn=document.getElementById('promote-btn');btn.disabled=true;btn.textContent='...Saving';logScrape('Saving shopping results...');try{const d=await apiPost(`/searches/${currentSearchId}/promote-shopping/`);const msg=`Saved ${d.promoted_count||0} shopping results to products`;logScrape('✓ '+msg);showToast(msg);document.getElementById('promote-result').style.display='block';document.getElementById('promote-result').innerHTML=`<div class="badge badge-green">✓ ${msg}</div>`;loadScrapeInfo();}catch(e){logScrape('✗ Failed: '+e.message);showToast('Failed');}finally{btn.disabled=false;btn.textContent='▶ Save shopping results';}}
async function runScrape(){const btn=document.getElementById('scrape-btn');const limit=document.getElementById('batch-size').value;btn.disabled=true;btn.textContent='...Scraping';logScrape(`Scraping batch (${limit})...`);try{const d=await apiPost(`/searches/${currentSearchId}/scrape/`,{limit:parseInt(limit)});const msg=`Scraped: ${d.scraped_this_run||0} done, ${d.failed||0} failed, ${d.remaining_visual||0} remaining`;logScrape('✓ '+msg);showToast(msg);document.getElementById('scrape-result').style.display='block';document.getElementById('scrape-result').innerHTML=`<div class="badge badge-green">✓ ${msg}</div>`;loadScrapeInfo();}catch(e){logScrape('✗ '+e.message);showToast('Failed');}finally{btn.disabled=false;btn.textContent='▶ Scrape batch';}}
async function runScrapeAll(){const btn=document.getElementById('scrape-all-btn');btn.disabled=true;btn.textContent='...Running';logScrape('Scraping all + auto-saving shopping results...');try{const d=await apiPost(`/searches/${currentSearchId}/scrape/all/`);const promoted = d.auto_promoted?.promoted ?? 0;logScrape(`✓ Done. Auto-promoted ${promoted} shopping results.`);showToast(`Scrape complete — ${promoted} shopping results saved automatically`);loadScrapeInfo();}catch(e){logScrape('✗ '+e.message);showToast('Failed');}finally{btn.disabled=false;btn.textContent='Scrape all';}}

// ── Upload ───────────────────────────────────────────────────────
let selectedFile=null;
function handleFileSelect(e){const f=e.target.files[0];if(f)setFile(f);}
function handleDrop(e){e.preventDefault();e.currentTarget.classList.remove('drag-over');const f=e.dataTransfer.files[0];if(f)setFile(f);}
function setFile(file){selectedFile=file;document.getElementById('search-btn').disabled=false;document.getElementById('file-name').textContent=file.name+' ('+(file.size/1024).toFixed(1)+' KB)';const r=new FileReader();r.onload=e=>{document.getElementById('img-preview').src=e.target.result;document.getElementById('preview-section').style.display='block';document.getElementById('upload-zone').style.display='none';};r.readAsDataURL(file);}
function clearFile(){selectedFile=null;document.getElementById('file-input').value='';document.getElementById('img-preview').src='';document.getElementById('preview-section').style.display='none';document.getElementById('upload-zone').style.display='block';document.getElementById('search-btn').disabled=true;resetUploadUI();}
function resetUploadUI(){setStep(1);document.getElementById('upload-panel').style.display='block';document.getElementById('processing-panel').style.display='none';document.getElementById('upload-result').style.display='none';}
function setStep(n){for(let i=1;i<=3;i++){const el=document.getElementById('step-'+i);el.className='step'+(i<n?' done':i===n?' active':'');el.querySelector('.step-dot').textContent=i<n?'✓':i;}}
function setProcStep(id,state){const el=document.getElementById(id);if(!el)return;el.dataset.state=state;el.querySelector('.pstep-icon').textContent={waiting:'⏳',active:'⏳',done:'✓',error:'✗'}[state]||'⏳';}

async function startSearch() {
  if(!selectedFile) return;
  const endpoint=document.getElementById('search-endpoint').value;
  const url=endpoint?`/api/upload/${endpoint}/`:'/api/upload/';
  document.getElementById('upload-panel').style.display='none';
  document.getElementById('processing-panel').style.display='block';
  document.getElementById('upload-result').style.display='none';
  setStep(2);
  ['pstep-upload','pstep-lens1','pstep-lens2','pstep-save'].forEach(id=>setProcStep(id,'waiting'));
  const startTime=Date.now();
  const te=document.getElementById('elapsed-timer');
  const et=setInterval(()=>{te.textContent=Math.round((Date.now()-startTime)/1000)+'s';},1000);
  const fe=document.getElementById('progress-fill');
  const le=document.getElementById('processing-label');
  setProcStep('pstep-upload','active');
  const stages=[{after:0,pct:5,step:'pstep-upload',label:'Uploading image...'},{after:5,pct:18,step:'pstep-lens1',label:'Google Lens searching...'},{after:25,pct:45,step:'pstep-lens1',label:'Google Lens — still working...'},{after:55,pct:65,step:'pstep-lens2',label:'Fetching exact matches...'},{after:75,pct:80,step:'pstep-save',label:'Saving results...'}];
  const order=['pstep-upload','pstep-lens1','pstep-lens2','pstep-save'];
  const sts=stages.map(s=>setTimeout(()=>{fe.style.width=s.pct+'%';le.textContent=s.label;const ci=order.indexOf(s.step);order.forEach((id,i)=>{if(i<ci)setProcStep(id,'done');else if(i===ci)setProcStep(id,'active');});},s.after*1000));
  function clearT(){clearInterval(et);sts.forEach(t=>clearTimeout(t));}
  try {
    const form=new FormData(); form.append('image',selectedFile);
    const res=await fetch(url,{method:'POST',headers:{'X-CSRFToken':getCsrfToken()},body:form});
    let data; try{data=await res.json();}catch{data={};}
    clearT(); fe.style.width='100%';
    if(!res.ok||data.error){
      let err=data.error||data.detail||`HTTP ${res.status}`;
      document.getElementById('processing-panel').style.display='none';
      document.getElementById('upload-panel').style.display='block';
      document.querySelectorAll('#upload-panel .upload-error').forEach(e=>e.remove());
      document.getElementById('upload-panel').insertAdjacentHTML('afterbegin',`<div class="upload-error" style="margin-bottom:16px;padding:14px 16px;background:var(--danger-bg);border:1px solid #FECACA;border-radius:8px"><div style="display:flex;gap:10px"><span style="font-size:18px">⚠</span><div><div style="font-size:13px;font-weight:600;color:var(--danger-text);margin-bottom:6px">${err}</div>${data.help?`<div style="font-size:12px;color:var(--danger-text);margin-bottom:8px">${data.help}</div>`:''}<button class="btn btn-sm" onclick="this.closest('.upload-error').remove();startSearch()">↺ Retry</button></div></div></div>`);
      setStep(1); return;
    }
    order.forEach(id=>setProcStep(id,'done'));
    currentSearchId=data.id; setStep(3);
    document.getElementById('processing-panel').style.display='none';
    document.getElementById('upload-result').style.display='block';
    const shopping=data.result_counts?.shopping_with_price||(data.shopping_results||[]).length||0;
    const visual=data.result_counts?.visual_no_price||(data.visual_matches||[]).length||0;
    const total=data.result_counts?.total||shopping+visual;
    const elapsed=Math.round((Date.now()-startTime)/1000);
    document.getElementById('res-shopping').textContent=shopping;
    document.getElementById('res-visual').textContent=visual;
    document.getElementById('res-total').textContent=total;
    document.getElementById('result-summary').textContent=`Found ${total} matches for "${data.search_keyword||data.detected_label}" in ${elapsed}s`;
    document.getElementById('result-label-row').innerHTML=[
      data.detected_label&&`<span class="badge badge-blue">${data.detected_label}</span>`,
      data.category&&`<span class="badge badge-gray">${data.category}</span>`,
      `<span class="badge badge-gray">⏱ ${elapsed}s</span>`,
    ].filter(Boolean).join('');
    // Wire download button for this search
    document.getElementById('dl-after-search').onclick=()=>downloadSearchExcel(data.id);
    showToast(`Search complete — ${total} results in ${elapsed}s`);
  } catch(e) {
    clearT();
    document.getElementById('processing-panel').style.display='none';
    document.getElementById('upload-panel').style.display='block';
    document.getElementById('upload-panel').insertAdjacentHTML('afterbegin',`<div class="upload-error" style="margin-bottom:16px;padding:14px 16px;background:var(--danger-bg);border:1px solid #FECACA;border-radius:8px"><div style="display:flex;gap:10px"><span>⚠</span><div><div style="font-size:13px;font-weight:600;color:var(--danger-text)">${e.message}</div><button class="btn btn-sm" onclick="this.closest('.upload-error').remove();startSearch()">↺ Retry</button></div></div></div>`);
    setStep(1);
  }
}

async function rescrapeProduct(id, btn) {
  const orig = btn.textContent;
  btn.disabled = true; btn.textContent = '...';
  try {
    const d = await apiPost(`/products/${id}/rescrape/`, {});
    if (d.success) {
      showToast(`Price updated: ${d.old_price||'—'} → ${d.price}`);
      loadProducts();
    } else if (d.kept_old_data) {
      showToast('Could not confirm new price — kept existing price');
    } else {
      showToast('Rescrape failed: ' + (d.error||'unknown'));
    }
  } catch { showToast('Rescrape failed'); }
  finally { btn.disabled = false; btn.textContent = orig; }
}

async function rescrapeAllProducts() {
  if (!currentSearchId) { showToast('No search selected'); return; }
  showToast('Refreshing all prices... this may take a while');
  logScrape && logScrape('Refreshing all product prices...');
  try {
    const d = await apiPost(`/searches/${currentSearchId}/rescrape-products/`, {});
    showToast(d.message || `Rescraped ${d.total||0} products`);
    loadProducts();
  } catch { showToast('Refresh failed'); }
}

async function rescrapeLensResult(id) {
  showToast('Re-checking price for #'+id+'...');
  try {
    const d = await apiPost(`/lens-results/${id}/scrape/`, {force: true});
    if (d.success) {
      showToast(d.promoted ? `Updated & in products: ${d.price}` : 'Rescraped, but not promoted');
    } else if (d.kept_old_data) {
      showToast('Site blocked the check — kept existing price');
    } else {
      showToast('Rescrape failed: ' + (d.error||'unknown'));
    }
    loadLensResults();
  } catch { showToast('Rescrape failed'); }
}

// ── Init ─────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  fetch(API_BASE+'/searches/',{method:'GET',credentials:'same-origin'}).catch(()=>{});
  loadDashboard();
});