const API = ""; // same-origin; change to e.g. "http://127.0.0.1:5001" if this file is opened outside Django

let current = { search: null, lens: null, products: null, tab: "all" };

function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2600);
}

async function api(path, opts = {}){
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if(!res.ok){
    let body = {};
    try{ body = await res.json(); }catch(e){}
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res.json();
}

function el(html){
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstChild;
}

function fmtMoney(n){
  if(!n) return "";
  return "₹" + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

function placeholderImg(){
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38"><rect width="38" height="38" fill="#EFE7DA"/><text x="19" y="23" font-size="9" text-anchor="middle" fill="#6E5A45" font-family="Inter">no img</text></svg>`
  );
}

function escapeHtml(s){
  if(s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------------------------------------------------------------- search picker (dynamic, no manual ID entry)

async function loadSearchList(){
  const select = document.getElementById('searchSelect');
  select.innerHTML = `<option value="">Loading your searches…</option>`;
  try{
    const searches = await api('/api/searches/');
    if(!searches.length){
      select.innerHTML = `<option value="">No searches yet</option>`;
      document.getElementById('emptyState').style.display = 'block';
      return;
    }
    select.innerHTML = searches.map(s => {
      const label = (s.search_keyword || s.detected_label || `Search #${s.id}`).slice(0, 60);
      const counts = `${s.shopping_count || 0} priced / ${s.visual_count || 0} visual`;
      return `<option value="${s.id}">#${s.id} — ${escapeHtml(label)} (${counts})</option>`;
    }).join('');
    // auto-load the most recent search (first in list, since SearchHistory orders by -created_at)
    select.value = searches[0].id;
    await loadSearch(searches[0].id);
  }catch(e){
    select.innerHTML = `<option value="">Couldn't load searches</option>`;
    toast(e.message);
  }
}

// ---------------------------------------------------------------- load a chosen search

async function loadSearch(id){
  if(!id) return;
  try{
    const [detail, lensAll] = await Promise.all([
      api(`/api/searches/${id}/`),
      api(`/api/searches/${id}/lens-results/`),
    ]);
    let products = { products: [], with_price: 0, without_price: 0, by_website: {} };
    try{
      products = await api(`/api/searches/${id}/products/`);
    }catch(e){ /* no products yet — fine */ }

    current.search = { id, ...detail };
    current.lens = lensAll;
    current.products = products;
    current.tab = 'all';

    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('metaStrip').style.display = 'flex';
    document.getElementById('tabs').style.display = 'flex';
    document.getElementById('toolbar').style.display = 'flex';
    document.querySelectorAll('nav.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === 'all'));

    document.getElementById('metaKeyword').textContent = detail.search_keyword || '—';
    document.getElementById('metaCategory').textContent = detail.category || '';
    document.getElementById('metaCounts').textContent =
      `${lensAll.counts.total} links found — ${lensAll.counts.shopping_with_price} priced, ${lensAll.counts.visual_no_price} need scraping`;

    renderStats();
    renderToolbar();
    renderTab();
  }catch(e){
    toast(e.message);
  }
}

function renderStats(){
  const c = current.lens.counts;
  const p = current.products;
  const host = document.getElementById('stats');
  host.style.display = 'grid';
  host.innerHTML = `
    <div class="stat"><div class="num">${c.total}</div><div class="label">Total links found</div></div>
    <div class="stat good"><div class="num">${c.shopping_with_price}</div><div class="label">Priced by Google Lens</div></div>
    <div class="stat warn"><div class="num">${c.visual_no_price}</div><div class="label">Awaiting scrape</div></div>
    <div class="stat"><div class="num">${(p.total_products ?? (p.products ? p.products.length : 0))}</div><div class="label">Products in comparison</div></div>
  `;
}

function renderToolbar(){
  const host = document.getElementById('toolbar');
  host.innerHTML = `
    <div class="group">
      <button class="primary" id="promoteBtn">Promote priced results</button>
      <button id="scrapeBtn">Scrape next batch</button>
      <input type="number" id="limitInput" value="20" min="1" max="42" style="width:64px;" />
      <button id="scrapeAllBtn">Scrape all remaining</button>
    </div>
    <div class="spacer"></div>
    <div class="group" id="progressGroup" style="display:none;">
      <div class="progress-row">
        <span id="progressLabel">Scraping…</span>
        <div class="progress-track"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
      </div>
    </div>
  `;
  document.getElementById('promoteBtn').onclick = promoteShopping;
  document.getElementById('scrapeBtn').onclick = scrapeBatch;
  document.getElementById('scrapeAllBtn').onclick = scrapeAll;
}

// ---------------------------------------------------------------- actions

async function promoteShopping(){
  const id = current.search.id;
  setBusy(true, 'Promoting priced results…');
  try{
    const res = await api(`/api/searches/${id}/promote-shopping/`, { method: 'POST' });
    toast(res.message || 'Promoted shopping results.');
    await loadSearch(id);
  }catch(e){ toast(e.message); }
  setBusy(false);
}

async function scrapeBatch(){
  const id = current.search.id;
  const limit = parseInt(document.getElementById('limitInput').value || '20', 10);
  setBusy(true, `Scraping ${limit} links…`);
  try{
    const res = await api(`/api/searches/${id}/scrape/`, {
      method: 'POST', body: JSON.stringify({ limit }),
    });
    toast(res.message || `Scraped ${res.scraped || 0} links.`);
    await loadSearch(id);
  }catch(e){ toast(e.message); }
  setBusy(false);
}

async function scrapeAll(){
  const id = current.search.id;
  setBusy(true, 'Scraping all remaining links — this can take a while…');
  try{
    const res = await api(`/api/searches/${id}/scrape/all/`, { method: 'POST' });
    toast(res.message || 'Scrape complete.');
    await loadSearch(id);
  }catch(e){ toast(e.message); }
  setBusy(false);
}

function setBusy(isBusy, label){
  document.querySelectorAll('#toolbar button').forEach(b => b.disabled = isBusy);
  const group = document.getElementById('progressGroup');
  if(!group) return;
  group.style.display = isBusy ? 'flex' : 'none';
  if(isBusy){
    document.getElementById('progressLabel').textContent = label;
    document.getElementById('progressFill').style.width = '60%';
  }
}

// ---------------------------------------------------------------- tabs

function renderTab(){
  if(!current.search) return;
  const host = document.getElementById('panelHost');
  host.innerHTML = '';
  if(current.tab === 'products'){
    host.appendChild(renderProductsPanel());
  } else {
    host.appendChild(renderLensPanel(current.tab));
  }
}

function renderLensPanel(mode){
  let rows = current.lens.results.slice();
  if(mode === 'unscraped') rows = rows.filter(r => !r.scraped && r.result_type === 'visual');
  if(mode === 'scraped')   rows = rows.filter(r => r.scraped || r.result_type === 'shopping');

  const wrap = el(`<div></div>`);
  const bar = buildFilterBar(rows, mode, (filtered) => {
    const table = wrap.querySelector('.table-wrap');
    table.replaceWith(buildLensTable(filtered, mode));
  });
  wrap.appendChild(bar);
  wrap.appendChild(buildLensTable(rows, mode));
  return wrap;
}

function buildFilterBar(rows, mode, onChange){
  const sources = [...new Set(rows.map(r => r.source).filter(Boolean))].sort();
  const bar = el(`
    <div class="toolbar" style="margin-bottom:12px;">
      <div class="group">
        <label>Source</label>
        <select id="srcFilter"><option value="">All sources</option>${sources.map(s => `<option value="${s}">${escapeHtml(s)}</option>`).join('')}</select>
      </div>
      <div class="group">
        <label>Sort</label>
        <select id="sortFilter">
          <option value="rank">Rank</option>
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
        </select>
      </div>
      <div class="spacer"></div>
      <div class="group" style="color:var(--ink-faint);font-size:12.5px;">${rows.length} results</div>
    </div>
  `);
  function apply(){
    let filtered = rows.slice();
    const src = bar.querySelector('#srcFilter').value;
    if(src) filtered = filtered.filter(r => r.source === src);
    const sort = bar.querySelector('#sortFilter').value;
    if(sort === 'price_asc') filtered.sort((a, b) => effPrice(a) - effPrice(b));
    if(sort === 'price_desc') filtered.sort((a, b) => effPrice(b) - effPrice(a));
    onChange(filtered);
  }
  bar.querySelector('#srcFilter').onchange = apply;
  bar.querySelector('#sortFilter').onchange = apply;
  return bar;
}

function effPrice(r){
  if(r.price_numeric) return r.price_numeric;
  if(r.scraped_price){
    const m = r.scraped_price.match(/[\d.]+/);
    return m ? parseFloat(m[0]) : 0;
  }
  return 0;
}

function buildLensTable(rows, mode){
  if(rows.length === 0){
    return el(`<div class="table-wrap"><div class="empty"><h3>Nothing here</h3><p>${
      mode === 'unscraped' ? 'All visual links have been scraped already.' : 'No results match this view yet.'
    }</p></div></div>`);
  }
  const body = rows.map(r => {
    const isShopping = r.result_type === 'shopping';
    const price = isShopping ? r.price : (r.scraped ? r.scraped_price : '');
    const rating = isShopping ? r.rating : (r.scraped_rating || r.rating);
    let statusHtml;
    if(isShopping) statusHtml = `<span class="pill-status scraped">Priced by Lens</span>`;
    else if(!r.scraped) statusHtml = `<span class="pill-status pending">Pending</span>`;
    else if(price) statusHtml = `<span class="pill-status scraped">Scraped</span>`;
    else statusHtml = `<span class="pill-status failed">No price found</span>`;

    return `
      <tr>
        <td>
          <div class="prod-cell">
            <img src="${r.thumbnail || r.image_url || placeholderImg()}" onerror="this.src='${placeholderImg()}'" />
            <div class="prod-title" title="${escapeHtml(r.title)}">${escapeHtml(r.title)}</div>
          </div>
        </td>
        <td><span class="src-pill">${escapeHtml(r.source || '—')}</span></td>
        <td>${price ? `<span class="price">${escapeHtml(price)}</span>` : `<span class="price none">—</span>`}</td>
        <td>${rating ? `<span class="rating">★ ${escapeHtml(rating)}</span>` : `<span class="rating">—</span>`}</td>
        <td>${statusHtml}</td>
        <td><a class="link-btn" href="${r.link}" target="_blank" rel="noopener">Visit ↗</a></td>
      </tr>`;
  }).join('');

  return el(`
    <div class="table-wrap">
      <table>
        <thead><tr><th>Product</th><th>Source</th><th>Price</th><th>Rating</th><th>Status</th><th></th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `);
}

function renderProductsPanel(){
  const data = current.products;
  const wrap = el(`<div></div>`);
  let products = (data.products || []).slice();

  if(products.length === 0){
    wrap.appendChild(el(`
      <div class="table-wrap"><div class="empty">
        <h3>No products yet</h3>
        <p>Promote priced results or scrape the unscraped queue first, then come back to this tab.</p>
      </div></div>
    `));
    return wrap;
  }

  const websites = [...new Set(products.map(p => p.website).filter(Boolean))].sort();
  const priced = products.filter(p => p.price_numeric > 0).map(p => p.price_numeric);
  const minPrice = priced.length ? Math.min(...priced) : 0;

  const bar = el(`
    <div class="toolbar" style="margin-bottom:12px;">
      <div class="group">
        <label>Website</label>
        <select id="webFilter"><option value="">All websites</option>${websites.map(w => `<option value="${w}">${escapeHtml(w)}</option>`).join('')}</select>
      </div>
      <div class="group">
        <label>Sort</label>
        <select id="prodSort">
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
        </select>
      </div>
      <div class="spacer"></div>
      <div class="group" style="color:var(--ink-faint);font-size:12.5px;">${products.length} products</div>
    </div>
  `);
  wrap.appendChild(bar);

  const tableHost = el(`<div></div>`);
  wrap.appendChild(tableHost);

  function render(){
    let list = products.slice();
    const web = bar.querySelector('#webFilter').value;
    if(web) list = list.filter(p => p.website === web);
    const sort = bar.querySelector('#prodSort').value;
    list.sort((a, b) => sort === 'price_desc' ? b.price_numeric - a.price_numeric : a.price_numeric - b.price_numeric);

    const rows = list.map(p => {
      const isBest = p.price_numeric === minPrice && minPrice > 0;
      return `
        <tr class="${isBest ? 'best' : ''}">
          <td>
            <div class="prod-cell">
              <img src="${p.product_image || placeholderImg()}" onerror="this.src='${placeholderImg()}'" />
              <div class="prod-title" title="${escapeHtml(p.product_name)}">${escapeHtml(p.product_name)}</div>
            </div>
          </td>
          <td><span class="src-pill">${escapeHtml(p.website)}</span></td>
          <td>${p.price_numeric > 0 ? `<span class="price">${fmtMoney(p.price_numeric)}</span>` : `<span class="price none">${escapeHtml(p.price || '—')}</span>`}</td>
          <td>${p.rating ? `<span class="rating">★ ${escapeHtml(p.rating)} ${p.reviews ? `(${escapeHtml(p.reviews)})` : ''}</span>` : `<span class="rating">—</span>`}</td>
          <td>${escapeHtml(p.delivery || '—')}</td>
          <td><a class="link-btn" href="${p.product_link}" target="_blank" rel="noopener">Visit ↗</a></td>
        </tr>`;
    }).join('');

    tableHost.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead><tr><th>Product</th><th>Website</th><th>Price</th><th>Rating</th><th>Delivery</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }
  bar.querySelector('#webFilter').onchange = render;
  bar.querySelector('#prodSort').onchange = render;
  render();
  return wrap;
}

// ---------------------------------------------------------------- wire up static page elements

document.addEventListener('click', (e) => {
  const btn = e.target.closest('nav.tabs button');
  if(!btn) return;
  document.querySelectorAll('nav.tabs button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  current.tab = btn.dataset.tab;
  renderTab();
});

document.getElementById('searchSelect').addEventListener('change', (e) => {
  if(e.target.value) loadSearch(e.target.value);
});

document.getElementById('refreshSearches').addEventListener('click', loadSearchList);

window.addEventListener('DOMContentLoaded', loadSearchList);