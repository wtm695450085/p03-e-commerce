/* ProSport — logika sklepu (vanilla JS) */
(() => {
  "use strict";

  const API = "";                  // ten sam origin
  const PAGE_SIZE = 24;
  const fmt = new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN" });

  // ---- stan ----
  const state = {
    store: null,
    departments: [],
    filters: { department: "all", q: "", brand: "", promo: false, sort: "popular" },
    page: 1,
    pages: 1,
    total: 0,
    loading: false,
    cart: loadCart(),
    // archiwum klientów / wybrana tożsamość
    identity: loadIdentity(),
    cust: { q: "", segment: "", tier: "", sort: "recent", page: 1, pages: 1, total: 0, loading: false },
    segmentsLoaded: false,
  };

  // ---- skróty DOM ----
  const $ = (s) => document.querySelector(s);
  const grid = $("#grid");
  const deptNav = $("#dept-nav");
  const heroChips = $("#hero-chips");

  // =====================================================================
  // INIT
  // =====================================================================
  async function init() {
    bindEvents();
    renderCart();
    renderIdentityBtn();
    try {
      const store = await fetchJSON(`${API}/api/store`);
      state.store = store;
      state.departments = store.departments;
      $("#hero-count").textContent = store.product_count;
      renderDeptNav();
      renderHeroChips();
      await loadProducts(true);
      if (state.identity) loadPromoAd();
    } catch (e) {
      grid.innerHTML = `<p style="color:var(--muted)">Nie udało się połączyć z API. Czy backend działa i baza jest zaseedowana?</p>`;
      console.error(e);
    }
  }

  // =====================================================================
  // DZIAŁY
  // =====================================================================
  function deptColor(slug) {
    const d = state.departments.find((x) => x.slug === slug);
    return d ? d.color : "var(--ink)";
  }

  function renderDeptNav() {
    const all = `<button class="dept-pill ${state.filters.department === "all" ? "active" : ""}" data-dept="all">
        <span class="dot" style="--pill-color:var(--ink)"></span> Wszystkie
        <span class="cnt">${state.store.product_count}</span></button>`;
    const pills = state.departments.map((d) => `
      <button class="dept-pill ${state.filters.department === d.slug ? "active" : ""}" data-dept="${d.slug}">
        <span class="dot" style="--pill-color:${d.color}"></span> ${d.name}
        <span class="cnt">${d.product_count}</span>
      </button>`).join("");
    deptNav.innerHTML = all + pills;
    deptNav.querySelectorAll(".dept-pill").forEach((b) =>
      b.addEventListener("click", () => selectDepartment(b.dataset.dept)));
  }

  function renderHeroChips() {
    heroChips.innerHTML = state.departments.map((d) => `
      <button class="hero-chip" data-dept="${d.slug}">
        <span class="dot" style="background:${d.color}"></span>${d.name}
        <span style="opacity:.6">${d.product_count}</span>
      </button>`).join("");
    heroChips.querySelectorAll(".hero-chip").forEach((b) =>
      b.addEventListener("click", () => {
        selectDepartment(b.dataset.dept);
        $(".toolbar").scrollIntoView({ behavior: "smooth", block: "start" });
      }));
  }

  async function selectDepartment(slug) {
    state.filters.department = slug;
    state.filters.brand = "";
    document.documentElement.style.setProperty("--dept", slug === "all" ? "var(--ink)" : deptColor(slug));
    $("#hero").classList.toggle("hidden", slug !== "all");
    const d = state.departments.find((x) => x.slug === slug);
    $("#section-title").textContent = slug === "all" ? "Wszystkie produkty" : d.name;
    renderDeptNav();
    await loadBrands();
    await loadProducts(true);
  }

  // =====================================================================
  // MARKI (filtr)
  // =====================================================================
  async function loadBrands() {
    const dep = state.filters.department;
    const brands = await fetchJSON(`${API}/api/brands${dep !== "all" ? `?department=${dep}` : ""}`);
    const sel = $("#brand-filter");
    sel.innerHTML = `<option value="">Wszystkie marki</option>` +
      brands.map((b) => `<option value="${b.brand}">${b.brand} (${b.count})</option>`).join("");
    sel.value = state.filters.brand;
  }

  // =====================================================================
  // PRODUKTY
  // =====================================================================
  async function loadProducts(reset) {
    if (state.loading) return;
    state.loading = true;
    if (reset) { state.page = 1; grid.innerHTML = skeletons(8); }

    const f = state.filters;
    const params = new URLSearchParams({
      page: state.page, page_size: PAGE_SIZE, sort: f.sort,
    });
    if (f.department !== "all") params.set("department", f.department);
    if (f.q) params.set("q", f.q);
    if (f.brand) params.set("brand", f.brand);
    if (f.promo) params.set("promo", "true");

    try {
      const data = await fetchJSON(`${API}/api/products?${params}`);
      state.pages = data.pages; state.total = data.total;
      if (reset) grid.innerHTML = "";
      data.items.forEach((p) => grid.insertAdjacentHTML("beforeend", cardHTML(p)));
      bindCards();
      $("#result-count").textContent = `${data.total} ${plural(data.total, "produkt", "produkty", "produktów")}`;
      $("#empty").hidden = data.total !== 0;
      $("#load-more").hidden = state.page >= state.pages || data.total === 0;
    } finally {
      state.loading = false;
    }
  }

  function cardHTML(p) {
    const sale = p.is_promo && p.old_price;
    const low = p.stock > 0 && p.stock <= 5;
    return `
    <article class="card" data-id="${p.id}">
      <div class="card-img">
        <img src="${p.image}" alt="${esc(p.name)}" loading="lazy" />
        <div class="card-badges">
          ${sale ? `<span class="badge promo">-${discount(p)}%</span>` : ""}
          ${low ? `<span class="badge low">Ostatnie ${p.stock}</span>` : ""}
        </div>
      </div>
      <div class="card-body">
        <span class="card-brand">${esc(p.brand)}</span>
        <h3 class="card-name">${esc(p.name)}</h3>
        <div class="card-rating"><span class="star">★</span> ${p.rating.toFixed(1)}
          <span class="rev">(${p.reviews})</span></div>
        <div class="card-foot">
          <div class="price">
            ${sale ? `<span class="was">${fmt.format(p.old_price)}</span>` : ""}
            <span class="now ${sale ? "sale" : ""}">${fmt.format(p.price)}</span>
          </div>
          <button class="add-btn" data-add="${p.id}" aria-label="Dodaj do koszyka">
            <svg viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>
          </button>
        </div>
      </div>
    </article>`;
  }

  function bindCards() {
    grid.querySelectorAll(".card").forEach((c) => {
      if (c.dataset.bound) return; c.dataset.bound = "1";
      c.addEventListener("click", (e) => {
        if (e.target.closest("[data-add]")) return;
        openModal(c.dataset.id);
      });
    });
    grid.querySelectorAll("[data-add]").forEach((b) => {
      if (b.dataset.bound) return; b.dataset.bound = "1";
      b.addEventListener("click", (e) => { e.stopPropagation(); addToCartById(b.dataset.add); });
    });
  }

  // =====================================================================
  // MODAL (szczegóły produktu)
  // =====================================================================
  async function openModal(id) {
    const modal = $("#modal"), body = $("#modal-body");
    body.innerHTML = `<div style="padding:60px;text-align:center;color:var(--muted)">Wczytywanie…</div>`;
    modal.hidden = false; document.body.style.overflow = "hidden";
    // pary per klaster — w klastrze aktywnego klienta (jeśli wybrany)
    const pairsUrl = `${API}/api/products/${id}/pairs` +
      (state.identity ? `?customer_id=${state.identity.id}` : "");
    const [p, pairsData] = await Promise.all([
      fetchJSON(`${API}/api/products/${id}`),
      fetchJSON(pairsUrl).catch(() => null),
    ]);
    document.documentElement.style.setProperty("--dept", deptColor(p.department));
    const sale = p.is_promo && p.old_price;
    const stockHTML = p.stock === 0
      ? `<p class="m-stock out">● Chwilowo niedostępny</p>`
      : p.stock <= 5
        ? `<p class="m-stock low">● Ostatnie sztuki: ${p.stock}</p>`
        : `<p class="m-stock in">● Dostępny</p>`;

    // sekcja "kupowane razem w Twoim klastrze"
    let pairsHTML = "";
    if (pairsData && pairsData.pairs && pairsData.pairs.length) {
      const clusterTag = pairsData.cluster
        ? `<span class="pairs-cluster-tag">klaster ${esc(pairsData.cluster)}${pairsData.fallback ? " (ogólny)" : ""}</span>`
        : "";
      const heading = state.identity
        ? `Często kupowane razem — w segmencie klienta ${clusterTag}`
        : `Często kupowane razem ${clusterTag}`;
      pairsHTML = `
      <div class="m-pairs" style="grid-column:1/-1">
        <h4>${heading}</h4>
        <div class="m-pairs-row">
          ${pairsData.pairs.map((s) => `
            <div class="m-sim m-pair" data-sim="${s.product_id}" title="${esc(s.reason)}">
              <img src="${s.image}" alt="${esc(s.name)}"/>
              <div class="n">${esc(s.name.split(" – ")[0])}</div>
              <div class="pair-cat">${esc(s.category)}</div>
              <div class="p">${fmt.format(s.price)}</div>
            </div>`).join("")}
        </div>
      </div>`;
    }

    body.innerHTML = `
      <div class="modal-img"><img src="${p.image}" alt="${esc(p.name)}"/></div>
      <div class="modal-info">
        <span class="m-brand">${esc(p.brand)} · ${esc(p.department_name)}</span>
        <h3>${esc(p.name)}</h3>
        <div class="m-rating"><span class="star">★</span> ${p.rating.toFixed(1)} · ${p.reviews} opinii · ${esc(p.category)}</div>
        <p class="m-desc">${esc(p.description)}</p>
        <div class="m-meta">${p.tags.map((t) => `<span class="m-tag">${esc(t)}</span>`).join("")}</div>
        <div class="m-price">
          <span class="now">${fmt.format(p.price)}</span>
          ${sale ? `<span class="was">${fmt.format(p.old_price)}</span>` : ""}
        </div>
        ${stockHTML}
        <button class="btn-primary btn-block" data-add-modal="${p.id}" ${p.stock === 0 ? "disabled" : ""}>
          ${p.stock === 0 ? "Niedostępny" : "Dodaj do koszyka"}</button>
      </div>
      ${pairsHTML}
      ${p.similar && p.similar.length ? `
      <div class="m-similar" style="grid-column:1/-1">
        <h4>Podobne produkty</h4>
        <div class="m-similar-row">
          ${p.similar.map((s) => `
            <div class="m-sim" data-sim="${s.id}">
              <img src="${s.image}" alt="${esc(s.name)}"/>
              <div class="n">${esc(s.name)}</div>
              <div class="p">${fmt.format(s.price)}</div>
            </div>`).join("")}
        </div>
      </div>` : ""}`;
    body.querySelector("[data-add-modal]")?.addEventListener("click", (e) => {
      addToCart(p); flashAdded(e.currentTarget);
    });
    body.querySelectorAll("[data-sim]").forEach((s) =>
      s.addEventListener("click", () => openModal(s.dataset.sim)));
  }

  function closeModal() { $("#modal").hidden = true; document.body.style.overflow = ""; }

  function flashAdded(btn) {
    const orig = btn.textContent;
    btn.textContent = "✓ Dodano"; btn.disabled = true;
    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1100);
  }

  // =====================================================================
  // KOSZYK
  // =====================================================================
  function loadCart() {
    try { return JSON.parse(localStorage.getItem("prosport_cart") || "[]"); }
    catch { return []; }
  }
  function saveCart() { localStorage.setItem("prosport_cart", JSON.stringify(state.cart)); }

  async function addToCartById(id) {
    const p = await fetchJSON(`${API}/api/products/${id}`);
    addToCart(p);
  }
  function addToCart(p) {
    const ex = state.cart.find((i) => i.id === p.id);
    if (ex) ex.quantity += 1;
    else state.cart.push({ id: p.id, name: p.name, price: p.price, image: p.image, quantity: 1 });
    saveCart(); renderCart(); toast(`Dodano: ${p.name.split(" – ")[0]}`);
  }
  function updateQty(id, delta) {
    const it = state.cart.find((i) => i.id === id); if (!it) return;
    it.quantity += delta;
    if (it.quantity <= 0) state.cart = state.cart.filter((i) => i.id !== id);
    saveCart(); renderCart();
  }
  function removeItem(id) { state.cart = state.cart.filter((i) => i.id !== id); saveCart(); renderCart(); }

  function cartTotal() { return state.cart.reduce((s, i) => s + i.price * i.quantity, 0); }
  function cartCount() { return state.cart.reduce((s, i) => s + i.quantity, 0); }

  function renderCart() {
    const count = cartCount();
    const badge = $("#cart-count");
    badge.textContent = count; badge.hidden = count === 0;
    const wrap = $("#cart-items"), empty = $("#cart-empty");
    if (!state.cart.length) {
      wrap.innerHTML = ""; empty.style.display = "flex";
      $("#checkout").disabled = true;
    } else {
      empty.style.display = "none";
      $("#checkout").disabled = false;
      wrap.innerHTML = state.cart.map((i) => `
        <div class="cart-item">
          <img src="${i.image}" alt="${esc(i.name)}"/>
          <div class="ci-info">
            <div class="ci-name">${esc(i.name)}</div>
            <div class="ci-price">${fmt.format(i.price)}</div>
            <div class="ci-controls">
              <div class="qty">
                <button data-dec="${i.id}">−</button><span>${i.quantity}</span><button data-inc="${i.id}">+</button>
              </div>
              <button class="ci-remove" data-rm="${i.id}">Usuń</button>
            </div>
          </div>
          <div class="ci-line">${fmt.format(i.price * i.quantity)}</div>
        </div>`).join("");
      wrap.querySelectorAll("[data-inc]").forEach((b) => b.onclick = () => updateQty(+b.dataset.inc, 1));
      wrap.querySelectorAll("[data-dec]").forEach((b) => b.onclick = () => updateQty(+b.dataset.dec, -1));
      wrap.querySelectorAll("[data-rm]").forEach((b) => b.onclick = () => removeItem(+b.dataset.rm));
    }
    $("#cart-total").textContent = fmt.format(cartTotal());
  }

  function openCart() { $("#cart").classList.add("open"); $("#cart").setAttribute("aria-hidden", "false"); $("#overlay").hidden = false; }
  function closeCart() { $("#cart").classList.remove("open"); $("#cart").setAttribute("aria-hidden", "true"); $("#overlay").hidden = true; }

  async function checkout() {
    if (!state.cart.length) return;
    const btn = $("#checkout"); btn.disabled = true; btn.textContent = "Przetwarzanie…";
    try {
      const res = await fetchJSON(`${API}/api/orders`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: state.cart.map((i) => ({ product_id: i.id, quantity: i.quantity })) }),
      });
      state.cart = []; saveCart(); renderCart(); closeCart();
      toast(`✓ Zamówienie #${res.order_id} złożone (symulacja) — ${fmt.format(res.total)}`, 3200);
    } catch (e) {
      toast("Nie udało się złożyć zamówienia.");
    } finally {
      btn.textContent = "Złóż zamówienie (symulacja)";
      renderCart();
    }
  }

  // =====================================================================
  // ZDARZENIA
  // =====================================================================
  function bindEvents() {
    let t;
    $("#search-input").addEventListener("input", (e) => {
      clearTimeout(t);
      t = setTimeout(() => { state.filters.q = e.target.value.trim(); loadProducts(true); }, 300);
    });
    $("#sort-select").addEventListener("change", (e) => { state.filters.sort = e.target.value; loadProducts(true); });
    $("#brand-filter").addEventListener("change", (e) => { state.filters.brand = e.target.value; loadProducts(true); });
    $("#promo-filter").addEventListener("change", (e) => { state.filters.promo = e.target.checked; loadProducts(true); });
    $("#load-more").addEventListener("click", () => { state.page++; loadProducts(false); });
    $("#reset-filters").addEventListener("click", () => {
      state.filters = { department: "all", q: "", brand: "", promo: false, sort: "popular" };
      $("#search-input").value = ""; $("#promo-filter").checked = false;
      $("#sort-select").value = "popular";
      selectDepartment("all");
    });
    $("#cart-btn").addEventListener("click", openCart);
    $("#cart-close").addEventListener("click", closeCart);
    $("#overlay").addEventListener("click", closeCart);
    $("#checkout").addEventListener("click", checkout);
    $("#modal-close").addEventListener("click", closeModal);
    $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

    // --- wybór klienta / tożsamość ---
    $("#identity-btn").addEventListener("click", openIdentity);
    $("#identity-close").addEventListener("click", closeIdentity);
    $("#id-overlay").addEventListener("click", closeIdentity);
    let ct;
    $("#id-search-input").addEventListener("input", (e) => {
      clearTimeout(ct);
      ct = setTimeout(() => { state.cust.q = e.target.value.trim(); loadCustomers(true); }, 300);
    });
    $("#id-segment").addEventListener("change", (e) => { state.cust.segment = e.target.value; loadCustomers(true); });
    $("#id-tier").addEventListener("change", (e) => { state.cust.tier = e.target.value; loadCustomers(true); });
    $("#id-sort").addEventListener("change", (e) => { state.cust.sort = e.target.value; loadCustomers(true); });
    $("#id-load-more").addEventListener("click", () => { state.cust.page++; loadCustomers(false); });
    $("#profile-close").addEventListener("click", closeProfile);
    $("#profile-modal").addEventListener("click", (e) => { if (e.target.id === "profile-modal") closeProfile(); });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closeModal(); closeCart(); closeProfile(); closeIdentity(); }
    });
  }

  // =====================================================================
  // TOŻSAMOŚĆ / ARCHIWUM KLIENTÓW
  // =====================================================================
  const CUST_PAGE = 20;
  const TIER_CLASS = {
    "VIP": "tier-vip", "Stały": "tier-staly", "Regularny": "tier-regularny",
    "Okazjonalny": "tier-okazjonalny", "Nowy": "tier-nowy",
  };

  function loadIdentity() {
    try { return JSON.parse(localStorage.getItem("prosport_identity") || "null"); }
    catch { return null; }
  }
  function saveIdentity() {
    if (state.identity) localStorage.setItem("prosport_identity", JSON.stringify(state.identity));
    else localStorage.removeItem("prosport_identity");
  }

  function avatarVars(hue) { return `--avatar:hsl(${hue ?? 210} 62% 48%)`; }
  function tierBadge(tier) {
    return `<span class="tag-tier ${TIER_CLASS[tier] || "tier-okazjonalny"}">${esc(tier || "—")}</span>`;
  }
  function deptName(slug) {
    const d = state.departments.find((x) => x.slug === slug);
    return d ? d.name : (slug || "—");
  }
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return "—";
    return d.toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  function renderIdentityBtn() {
    const btn = $("#identity-btn"), av = $("#identity-avatar"), lab = $("#identity-label");
    const id = state.identity;
    if (id) {
      btn.classList.add("set");
      av.textContent = id.initials || "?";
      av.style.cssText = avatarVars(id.avatar_hue);
      lab.textContent = id.full_name;
    } else {
      btn.classList.remove("set");
      av.textContent = "?"; av.style.cssText = "--avatar:#6B7280";
      lab.textContent = "Wybierz klienta";
    }
  }

  function openIdentity() {
    $("#identity-drawer").classList.add("open");
    $("#identity-drawer").setAttribute("aria-hidden", "false");
    $("#id-overlay").hidden = false;
    renderCurrentIdentity();
    if (!state.segmentsLoaded) loadSegments();
    loadCustomers(true);
  }
  function closeIdentity() {
    $("#identity-drawer").classList.remove("open");
    $("#identity-drawer").setAttribute("aria-hidden", "true");
    $("#id-overlay").hidden = true;
  }

  function renderCurrentIdentity() {
    const box = $("#id-current"), id = state.identity;
    if (!id) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = `
      <span class="cust-av" style="${avatarVars(id.avatar_hue)}">${esc(id.initials || "?")}</span>
      <div class="who"><b>${esc(id.full_name)}</b><span>Aktywna tożsamość · ${esc(id.segment || "")}</span></div>
      <button class="clear" id="id-clear">Wyloguj</button>`;
    box.querySelector("#id-clear").addEventListener("click", clearIdentity);
  }

  async function loadSegments() {
    try {
      const data = await fetchJSON(`${API}/api/customers/segments`);
      $("#id-segment").innerHTML =
        `<option value="">Wszystkie zainteresowania (${data.total})</option>` +
        data.segments.map((s) => `<option value="${esc(s.segment)}">${esc(s.segment)} (${s.count})</option>`).join("");
      $("#id-tier").innerHTML =
        `<option value="">Wszyscy klienci</option>` +
        data.tiers.map((t) => `<option value="${esc(t.tier)}">${esc(t.tier)} (${t.count})</option>`).join("");
      state.segmentsLoaded = true;
    } catch (e) { console.error(e); }
  }

  async function loadCustomers(reset) {
    const c = state.cust;
    if (c.loading) return;
    c.loading = true;
    if (reset) { c.page = 1; $("#id-list").innerHTML = custSkeletons(5); }
    const params = new URLSearchParams({ page: c.page, page_size: CUST_PAGE, sort: c.sort });
    if (c.q) params.set("q", c.q);
    if (c.segment) params.set("segment", c.segment);
    if (c.tier) params.set("tier", c.tier);
    try {
      const data = await fetchJSON(`${API}/api/customers?${params}`);
      c.pages = data.pages; c.total = data.total;
      const list = $("#id-list");
      if (reset) list.innerHTML = "";
      if (data.total === 0) {
        list.innerHTML = `<p class="p-empty" style="padding:20px 4px">Brak klientów spełniających kryteria.</p>`;
      } else {
        data.items.forEach((cust) => list.insertAdjacentHTML("beforeend", custRowHTML(cust)));
        bindCustRows();
      }
      $("#id-load-more").hidden = c.page >= c.pages || data.total === 0;
    } catch (e) {
      $("#id-list").innerHTML = `<p class="p-empty" style="padding:20px 4px">Nie udało się wczytać klientów. Czy uruchomiono: <code>python -m app.seed_customers</code>?</p>`;
      console.error(e);
    } finally {
      c.loading = false;
    }
  }

  function custRowHTML(c) {
    const active = state.identity && state.identity.id === c.id;
    return `
    <div class="cust-row ${active ? "active" : ""}" data-cid="${c.id}" style="${avatarVars(c.avatar_hue)}">
      <span class="cust-av">${esc(c.initials)}</span>
      <div class="cust-main">
        <div class="cust-name">${esc(c.full_name)}</div>
        <div class="cust-meta">${esc(c.city || "")} · ${esc(deptName(c.favorite_department))}</div>
        <div class="cust-badges"><span class="tag-seg">${esc(c.segment || "")}</span>${tierBadge(c.loyalty_tier)}</div>
      </div>
      <div class="cust-side">
        <span class="cust-spent">${fmt.format(c.total_spent || 0)}</span>
        <span class="cust-orders">${c.orders_count} zam. · ${c.visits_count} wiz.</span>
        <div class="cust-actions">
          <button class="mini-btn" data-profile="${c.id}">Profil</button>
          <button class="mini-btn pick" data-pick="${c.id}">${active ? "Wybrany" : "Wybierz"}</button>
        </div>
      </div>
    </div>`;
  }

  function bindCustRows() {
    $("#id-list").querySelectorAll(".cust-row").forEach((r) => {
      if (r.dataset.bound) return; r.dataset.bound = "1";
      r.querySelector("[data-pick]").addEventListener("click", (e) => { e.stopPropagation(); selectIdentity(+r.dataset.cid); });
      r.querySelector("[data-profile]").addEventListener("click", (e) => { e.stopPropagation(); openProfile(+r.dataset.cid); });
      r.addEventListener("click", () => openProfile(+r.dataset.cid));
    });
  }

  async function selectIdentity(id) {
    try {
      const c = await fetchJSON(`${API}/api/customers/${id}`);
      state.identity = {
        id: c.id, full_name: c.full_name, initials: c.initials,
        segment: c.segment, avatar_hue: c.avatar_hue,
      };
      saveIdentity(); renderIdentityBtn(); renderCurrentIdentity();
      $("#id-list").querySelectorAll(".cust-row").forEach((r) => {
        const on = +r.dataset.cid === id;
        r.classList.toggle("active", on);
        const pick = r.querySelector("[data-pick]");
        if (pick) pick.textContent = on ? "Wybrany" : "Wybierz";
      });
      const pBtn = $("#profile-body").querySelector("[data-pick-profile]");
      if (pBtn && +pBtn.dataset.pickProfile === id) { pBtn.textContent = "✓ Wybrany"; pBtn.classList.add("active"); }
      toast(`Wcielasz się w: ${c.full_name}`);
      loadPromoAd();
    } catch (e) { toast("Nie udało się wybrać klienta."); }
  }

  function clearIdentity() {
    state.identity = null; saveIdentity(); renderIdentityBtn(); renderCurrentIdentity();
    $("#id-list").querySelectorAll(".cust-row").forEach((r) => {
      r.classList.remove("active");
      const pick = r.querySelector("[data-pick]"); if (pick) pick.textContent = "Wybierz";
    });
    hidePromoAd();
    toast("Wylogowano klienta.");
  }

  // =====================================================================
  // SPERSONALIZOWANA REKLAMA (pływająca)
  // =====================================================================
  let promoDismissed = false;

  function hidePromoAd() {
    const el = $("#promo-ad");
    el.hidden = true; el.classList.remove("show");
  }

  async function loadPromoAd() {
    if (!state.identity || promoDismissed) return;
    try {
      const offer = await fetchJSON(`${API}/api/customers/${state.identity.id}/offer`);
      if (!offer.items || !offer.items.length) { hidePromoAd(); return; }
      renderPromoAd(offer);
    } catch (e) { hidePromoAd(); }
  }

  const PROMO_SLOGANS = [
    "Wyprzedaż tylko dla Ciebie!",
    "Indywidualna oferta — tylko dziś!",
    "Specjalne ceny wybrane dla Ciebie",
    "Twoja prywatna promocja",
  ];

  function renderPromoAd(offer) {
    const el = $("#promo-ad");
    const slogan = PROMO_SLOGANS[(state.identity.id) % PROMO_SLOGANS.length];
    const maxDisc = Math.max(...offer.items.map((i) => i.discount));
    el.innerHTML = `
      <button class="promo-close" id="promo-close" aria-label="Zamknij">✕</button>
      <div class="promo-hero">
        <span class="promo-hero-photo">
          <img src="/images/hero/wojciech-hero.png" alt="ProSport" />
        </span>
        <div class="promo-hero-txt">
          <span class="promo-eyebrow">−${maxDisc}% · Oferta indywidualna</span>
          <span class="promo-slogan">${esc(slogan)}</span>
        </div>
      </div>
      <div class="promo-greet">Cześć ${esc(offer.first_name || "")}! Wybraliśmy je specjalnie dla Ciebie:</div>
      <div class="promo-items">
        ${offer.items.map((it) => `
          <div class="promo-item" data-promo="${it.product_id}">
            <div class="promo-img"><img src="${it.image}" alt="${esc(it.name)}"/>
              <span class="promo-badge">−${it.discount}%</span>
            </div>
            <div class="promo-info">
              <div class="promo-name">${esc(it.name.split(" – ")[0])}</div>
              <div class="promo-prices">
                <span class="promo-old">${fmt.format(it.price)}</span>
                <span class="promo-new">${fmt.format(it.new_price)}</span>
              </div>
            </div>
          </div>`).join("")}
      </div>
      <div class="promo-foot">Promocja ważna tylko dla Twojego konta</div>`;
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add("show"));

    $("#promo-close").addEventListener("click", () => { promoDismissed = true; hidePromoAd(); });
    el.querySelectorAll("[data-promo]").forEach((it) =>
      it.addEventListener("click", () => openModal(it.dataset.promo)));
  }

  // ---- profil (rejestr sprzedaży klienta) ----
  async function openProfile(id) {
    const modal = $("#profile-modal"), body = $("#profile-body");
    body.innerHTML = `<div style="padding:60px;text-align:center;color:var(--muted)">Wczytywanie profilu…</div>`;
    modal.hidden = false; document.body.style.overflow = "hidden";
    try {
      const [prof, recs] = await Promise.all([
        fetchJSON(`${API}/api/customers/${id}`),
        fetchJSON(`${API}/api/customers/${id}/recommendations`).catch(() => null),
      ]);
      renderProfile(prof, recs);
    } catch (e) {
      body.innerHTML = `<div style="padding:60px;text-align:center;color:var(--muted)">Nie udało się wczytać profilu.</div>`;
    }
  }
  function closeProfile() {
    $("#profile-modal").hidden = true;
    if ($("#modal").hidden) document.body.style.overflow = "";
  }

  function renderProfile(c, recs) {
    const s = c.stats;
    const cl = c.clustering;   // może być null gdy klasteryzacja nie uruchomiona
    const active = state.identity && state.identity.id === c.id;

    // ---- RFM + Sparse clustering ----
    const CLUSTER_COLORS = { A:"#A8E063", B:"#58A6FF", C:"#FFA657", D:"#D2A8FF", E:"#FF6B6B" };
    const RFM_SEG_COLOR  = {
      "Champions":"#A8E063","Lojalny klient":"#58A6FF","Potencjalny Champion":"#39D353",
      "Nowy VIP":"#FFA657","Zagrożony wysoki":"#D2A8FF","Potrzebuje uwagi":"#8B949E",
      "Śpiący klient":"#6e7681","Nie może stracić":"#FF8C00",
      "Odejście VIP":"#FF6B6B","Odchodzący":"#CC3333","Stracony":"#888","Okazjonalny":"#6e7681",
    };
    const RFM_LABELS = { r:"Recency", f:"Frequency", m:"Monetary" };

    let clusteringHTML = "";
    if (cl) {
      const rfm = cl.rfm;
      const rfmColor = RFM_SEG_COLOR[rfm.segment] || "#8B949E";
      const kmColor  = CLUSTER_COLORS[cl.km_cluster] || "#8B949E";

      // RFM — trzy pasy z wypełnieniem
      const rfmAxes = ["r","f","m"].map(axis => {
        const score = rfm[axis];
        const dots  = Array.from({length:5}, (_,i) =>
          `<span class="rfm-dot ${i < score ? "on" : ""}" style="${i < score ? `background:${rfmColor}` : ""}"></span>`
        ).join("");
        return `
          <div class="rfm-axis-row">
            <span class="rfm-axis-label">${RFM_LABELS[axis]}</span>
            <span class="rfm-dots">${dots}</span>
            <span class="rfm-axis-score">${score}/5</span>
          </div>`;
      }).join("");

      // Sparse — paski prawdopodobieństwa
      const sparseMax = Math.max(...Object.values(cl.sparse));
      const sparseBars = Object.entries(cl.sparse)
        .sort((a,b) => b[1]-a[1])
        .map(([ltr, prob]) => {
          const pct   = Math.round(prob * 100);
          const width = Math.round(prob / sparseMax * 100);
          const isBest = ltr === cl.km_cluster;
          return `
            <div class="sparse-row ${isBest ? "sparse-best" : ""}">
              <span class="sparse-ltr" style="color:${CLUSTER_COLORS[ltr]}">Kl.${ltr}</span>
              <span class="sparse-track">
                <span class="sparse-fill" style="width:${width}%;background:${CLUSTER_COLORS[ltr]}"></span>
              </span>
              <span class="sparse-pct">${pct}%</span>
              ${isBest ? `<span class="sparse-badge">KM</span>` : ""}
            </div>`;
        }).join("");

      clusteringHTML = `
        <div class="p-section p-section-cluster">
          <h4>Analiza RFM</h4>
          <div class="rfm-block">
            ${rfmAxes}
            <div class="rfm-seg-pill" style="background:${rfmColor}1a;border-color:${rfmColor}55;color:${rfmColor}">
              ${esc(rfm.segment)}
            </div>
          </div>
        </div>
        <div class="p-section">
          <h4>Sparse Customer Clustering</h4>
          <div class="sparse-header">
            <span class="sparse-km-label">Klaster KM:</span>
            <span class="sparse-km-badge" style="background:${kmColor}22;border-color:${kmColor}55;color:${kmColor}">
              ${cl.km_cluster} — ${esc(cl.cluster_label || "")}
            </span>
          </div>
          <div class="sparse-bars">${sparseBars}</div>
          <a href="/dashboard" class="sparse-dash-link" target="_blank">
            → Otwórz dashboard analityczny
          </a>
        </div>`;
    } else {
      clusteringHTML = `
        <div class="p-section">
          <h4>Klasteryzacja</h4>
          <p class="p-empty">Brak danych — uruchom: <code>python -m app.cluster_customers</code></p>
        </div>`;
    }

    const maxDept = Math.max(1, ...s.by_department.map((d) => d.spent));
    const deptBars = s.by_department.length ? s.by_department.map((d) => `
      <div class="p-bar-row">
        <span>${esc(d.name || d.slug)}</span>
        <span class="p-bar-track"><span class="p-bar-fill" style="width:${Math.round(d.spent / maxDept * 100)}%;--dept:${deptColor(d.slug)}"></span></span>
        <span class="amt">${fmt.format(d.spent)}</span>
      </div>`).join("") : `<p class="p-empty">Brak zakupów.</p>`;

    const cats = s.top_categories.length
      ? s.top_categories.map((x) => `<span class="p-chip">${esc(x.category)}<b>${x.count}</b></span>`).join("")
      : `<span class="p-empty">—</span>`;
    const brands = (c.favorite_brands && c.favorite_brands.length)
      ? c.favorite_brands.map((b) => `<span class="p-chip">${esc(b)}</span>`).join("")
      : `<span class="p-empty">—</span>`;

    const orders = c.orders.length ? c.orders.map((o) => `
      <div class="p-order">
        <div class="p-order-top">
          <span class="when">${fmtDate(o.created_at)} · #${o.id}</span>
          <span class="p-order-status st-${esc(o.status)}">${esc(o.status)}</span>
          <span class="sum">${fmt.format(o.total)}</span>
        </div>
        <div class="p-order-items">${o.items.map((it) =>
          `${esc(it.name.split(" – ")[0])} <span class="q">×${it.quantity}</span>`).join(" · ")}</div>
      </div>`).join("") : `<p class="p-empty">Brak zamówień w archiwum.</p>`;

    const chat = c.messages.length ? c.messages.map((m) => `
      <div class="p-msg ${m.role === "klient" ? "klient" : "obsluga"}">
        <span class="meta">${m.role === "klient" ? "Klient" : "Obsługa"} · ${fmtDate(m.created_at)}${m.topic ? " · " + esc(m.topic) : ""}</span>
        ${esc(m.text)}
      </div>`).join("") : `<p class="p-empty">Brak historii czatu.</p>`;

    // badge klastra w heroso (obok segmentu)
    const clusterBadge = cl
      ? `<span class="tag-cluster" style="background:${(CLUSTER_COLORS[cl.km_cluster]||"#8B949E")}22;
             border:1px solid ${(CLUSTER_COLORS[cl.km_cluster]||"#8B949E")}55;
             color:${CLUSTER_COLORS[cl.km_cluster]||"#8B949E"}">
           Kl.${cl.km_cluster}
         </span>`
      : "";

    // ---- REKOMENDACJE + BLIŹNIACY ----
    const DEPT_COLORS = { obuwie:"#2D6CDF", odziez:"#E8590C", silownia:"#0CA678", akcesoria:"#7048E8" };
    let recsHTML = "";

    if (recs && recs.recommendations && recs.recommendations.length) {
      const m = recs.model;
      const items = recs.recommendations;

      // metryki modelu
      const metricsHTML = m && m.metrics ? `
        <div class="rec-model-bar">
          <span class="rec-model-name">⚡ LightGBM LambdaRank</span>
          <span class="rec-metric">NDCG@5 <b>${m.metrics.ndcg_at5}</b></span>
          <span class="rec-metric">MAP@5 <b>${m.metrics.map_at5}</b></span>
          <span class="rec-metric">AUC <b>${m.metrics.auc}</b></span>
          <span class="rec-metric">P@5 <b>${m.metrics.precision_at5}</b></span>
        </div>` : "";

      // jedna wspólna lista top 10
      const rows = items.map(r => {
        const color = DEPT_COLORS[r.department] || "#14181F";
        return `
          <div class="rec-row">
            <span class="rec-rank">#${r.rank}</span>
            <div class="rec-info">
              <div class="rec-name">${esc(r.name.split(" – ")[0])}
                <span class="rec-dept-tag" style="--dept-color:${color}">${esc(r.department_name || r.department)}</span>
              </div>
              <div class="rec-reason">${esc(r.reason)}</div>
            </div>
            <div class="rec-right">
              <span class="rec-price">${fmt.format(r.price)}</span>
              <span class="rec-prob" style="--prob-color:${color}">${Math.round(r.probability*100)}%</span>
            </div>
          </div>`;
      }).join("");

      // cyfrowi bliźniacy
      const twinsHTML = recs.digital_twins && recs.digital_twins.length ? `
        <div class="p-section">
          <h4>Cyfrowi bliźniacy — 5 najbardziej podobnych klientów</h4>
          <div class="twins-list">
            ${recs.digital_twins.map((t, i) => {
              const simPct = Math.round(t.similarity * 100);
              return `
                <div class="twin-row" data-twin="${t.id}">
                  <span class="twin-rank">#${i+1}</span>
                  <span class="twin-sim-bar">
                    <span class="twin-sim-fill" style="width:${simPct}%"></span>
                  </span>
                  <span class="twin-name">${esc(t.name)}</span>
                  <span class="twin-meta">${esc(t.segment)} · Kl.${esc(t.cluster)}</span>
                  <span class="twin-pct">${simPct}%</span>
                  <button class="mini-btn" onclick="event.stopPropagation()">Profil</button>
                </div>`;
            }).join("")}
          </div>
        </div>` : "";

      recsHTML = `
        <div class="p-section p-section-recs">
          <h4>Co prawdopodobnie kupi przy najbliższej wizycie — TOP 10</h4>
          ${metricsHTML}
          <div class="rec-list">${rows}</div>
        </div>
        ${twinsHTML}`;
    } else {
      recsHTML = `
        <div class="p-section">
          <h4>Rekomendacje</h4>
          <p class="p-empty">Brak danych — uruchom: <code>python -m app.recommend</code></p>
        </div>`;
    }

      $("#profile-body").innerHTML = `
      <div class="p-hero" style="${avatarVars(c.avatar_hue)}">
        <span class="p-av">${esc(c.initials)}</span>
        <div class="p-id">
          <h3 id="profile-title">${esc(c.full_name)}</h3>
          <div class="p-contact">${esc(c.email)} · ${esc(c.city || "")}${c.age ? " · " + c.age + " lat" : ""}${c.age_group ? " (" + c.age_group + ")" : ""}</div>
          <div class="p-badges">
            <span class="tag-seg">${esc(c.segment || "")}</span>
            ${tierBadge(c.loyalty_tier)}
            ${clusterBadge}
            ${c.affluence ? `<span class="tag-seg">${esc(c.affluence)}</span>` : ""}
            ${c.newsletter ? `<span class="tag-seg">newsletter</span>` : ""}
          </div>
        </div>
        <button class="p-pick ${active ? "active" : ""}" data-pick-profile="${c.id}">${active ? "✓ Wybrany" : "Wciel się"}</button>
      </div>
      <div class="p-section"><h4>Co go interesuje</h4><p class="p-interest">${esc(c.interest_summary || "—")}</p></div>
      <div class="p-section">
        <h4>Podsumowanie</h4>
        <div class="p-stats">
          <div class="p-stat"><div class="v">${fmt.format(s.total_spent)}</div><div class="l">Łącznie wydane</div></div>
          <div class="p-stat"><div class="v">${s.orders_count}</div><div class="l">Zamówienia${s.orders_cancelled ? ` (+${s.orders_cancelled} anul.)` : ""}</div></div>
          <div class="p-stat"><div class="v">${s.visits_count}</div><div class="l">Wizyty</div></div>
          <div class="p-stat"><div class="v">${fmt.format(s.avg_order)}</div><div class="l">Śr. koszyk</div></div>
        </div>
      </div>
      ${clusteringHTML}
      ${recsHTML}
      <div class="p-section"><h4>Wydatki wg działu</h4><div class="p-bars">${deptBars}</div></div>
      <div class="p-section"><h4>Najczęściej kupowane kategorie</h4><div class="p-chips">${cats}</div></div>
      <div class="p-section"><h4>Ulubione marki</h4><div class="p-chips">${brands}</div></div>
      <div class="p-section"><h4>Historia zamówień (${c.orders.length})</h4><div class="p-orders">${orders}</div></div>
      <div class="p-section"><h4>Czat z obsługą</h4><div class="p-chat">${chat}</div></div>`;

    $("#profile-body").querySelector("[data-pick-profile]").addEventListener("click", () => selectIdentity(c.id));
    // bliźniacy — klik otwiera profil
    $("#profile-body").querySelectorAll("[data-twin]").forEach(el =>
      el.querySelector(".mini-btn")?.addEventListener("click", () => openProfile(+el.dataset.twin))
    );
  }

  function custSkeletons(n) {
    return Array.from({ length: n }).map(() => `
      <div class="cust-row" style="--avatar:#E7E7E2">
        <span class="cust-av"></span>
        <div class="cust-main">
          <div class="cust-name" style="background:var(--surface-2);height:12px;width:60%;border-radius:4px"></div>
          <div class="cust-meta" style="background:var(--surface-2);height:10px;width:40%;border-radius:4px;margin-top:6px"></div>
        </div>
        <div class="cust-side"></div>
      </div>`).join("");
  }

  // =====================================================================
  // POMOCNICZE
  // =====================================================================
  async function fetchJSON(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  function esc(s) { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; }
  function discount(p) { return Math.round((1 - p.price / p.old_price) * 100); }
  function plural(n, one, few, many) {
    const m10 = n % 10, m100 = n % 100;
    if (n === 1) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }
  function skeletons(n) {
    return Array.from({ length: n }).map(() => `
      <article class="card"><div class="card-img" style="background:var(--surface-2)"></div>
      <div class="card-body"><span class="card-brand" style="background:var(--surface-2);height:10px;width:40%;border-radius:4px"></span>
      <h3 class="card-name" style="background:var(--surface-2);height:32px;border-radius:6px"></h3></div></article>`).join("");
  }
  let toastTimer;
  function toast(msg, dur = 2000) {
    const el = $("#toast");
    el.innerHTML = `<span class="t-dot"></span>${esc(msg)}`;
    el.hidden = false; requestAnimationFrame(() => el.classList.add("show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.hidden = true, 260); }, dur);
  }

  init();
})();
