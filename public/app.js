const state = {
  data: null,
  query: "",
  party: "",
  uf: "",
  category: "",
};

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

const brlFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const num = new Intl.NumberFormat("pt-BR");

function $(id) {
  return document.getElementById(id);
}

function norm(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function setText(id, text) {
  $(id).textContent = text;
}

function optionList(values, label) {
  return [`<option value="">${label}</option>`]
    .concat(values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`))
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function matchesQuery(parts) {
  if (!state.query) return true;
  const haystack = norm(parts.join(" "));
  return haystack.includes(norm(state.query));
}

function filteredDeputies() {
  return state.data.rankings.deputies.filter((row) => {
    if (state.party && row.party !== state.party) return false;
    if (state.uf && row.uf !== state.uf) return false;
    if (state.category && row.main_category !== state.category) return false;
    return matchesQuery([row.deputy, row.party, row.uf, row.main_category, row.main_supplier]);
  });
}

function filteredSuppliers() {
  return state.data.rankings.suppliers.filter((row) => {
    if (state.category && row.main_category !== state.category) return false;
    return matchesQuery([row.supplier, row.cnpjcpf, row.main_category]);
  });
}

function filteredDocuments() {
  return state.data.rankings.documents.filter((row) => {
    if (state.party && row.party !== state.party) return false;
    if (state.uf && row.uf !== state.uf) return false;
    if (state.category && row.category !== state.category) return false;
    return matchesQuery([row.deputy, row.party, row.uf, row.category, row.supplier, row.cnpjcpf, row.document]);
  });
}

function filteredAlerts() {
  return state.data.alerts.filter((row) => {
    if (state.party && row.party && row.party !== state.party) return false;
    if (state.uf && row.uf && row.uf !== state.uf) return false;
    if (state.category && row.category && row.category !== state.category) return false;
    return matchesQuery([row.type, row.title, row.deputy, row.party, row.uf, row.category, row.supplier, row.detail]);
  });
}

function renderBars(id, rows, titleKey, metaFn, valueKey = "total", limit = 15) {
  const list = rows.slice(0, limit);
  const max = Math.max(...list.map((row) => row[valueKey]), 1);
  $(id).innerHTML = list
    .map((row) => {
      const width = Math.max(2, (row[valueKey] / max) * 100);
      return `
        <div class="bar-row">
          <div class="row-top">
            <div class="row-title" title="${escapeHtml(row[titleKey])}">${escapeHtml(row[titleKey])}</div>
            <div class="row-meta">${brl.format(row[valueKey])}</div>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          <div class="row-meta">${escapeHtml(metaFn(row))}</div>
        </div>
      `;
    })
    .join("");
}

function renderSuppliers(rows) {
  $("supplierRanking").innerHTML = rows
    .slice(0, 18)
    .map(
      (row) => `
        <div class="compact-item">
          <div class="row-top">
            <div class="compact-title" title="${escapeHtml(row.supplier)}">${escapeHtml(row.supplier)}</div>
            <div class="row-meta">${brl.format(row.total)}</div>
          </div>
          <div class="compact-meta">
            ${num.format(row.count)} docs • ${num.format(row.deputies)} deputados • ${num.format(row.parties)} partidos • ${escapeHtml(row.main_category)}
          </div>
        </div>
      `,
    )
    .join("");
}

function renderTable(id, columns, rows, emptyMessage = "Sem registros para os filtros atuais.") {
  if (!rows.length) {
    $(id).innerHTML = `<p class="row-meta">${emptyMessage}</p>`;
    return;
  }
  const head = columns.map((col) => `<th class="${col.className || ""}">${escapeHtml(col.label)}</th>`).join("");
  const body = rows
    .map(
      (row) => `
        <tr>
          ${columns
            .map((col) => `<td class="${col.className || ""}">${col.render ? col.render(row) : escapeHtml(row[col.key])}</td>`)
            .join("")}
        </tr>
      `,
    )
    .join("");
  $(id).innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderAlerts() {
  const rows = filteredAlerts();
  $("alertChips").innerHTML = state.data.alert_counts
    .map((row) => `<span class="chip">${escapeHtml(row.type)}: ${num.format(row.count)}</span>`)
    .join("");
  renderTable(
    "alertsTable",
    [
      { label: "Severidade", render: (row) => `<span class="badge ${row.severity}">${escapeHtml(row.severity)}</span>` },
      { label: "Tipo", key: "type" },
      { label: "Ponto de atenção", render: (row) => `<strong>${escapeHtml(row.title)}</strong><br><span class="row-meta">${escapeHtml(row.detail)}</span>` },
      { label: "Deputado", render: (row) => escapeHtml([row.deputy, row.party, row.uf].filter(Boolean).join(" • ")) },
      { label: "Fornecedor", key: "supplier" },
      { label: "Categoria", key: "category" },
      { label: "Valor", className: "money", render: (row) => brlFull.format(row.value) },
      { label: "Doc.", render: (row) => (row.url ? `<a href="${escapeHtml(row.url)}" target="_blank" rel="noreferrer">abrir</a>` : "") },
    ],
    rows.slice(0, 24),
  );
}

function renderDocuments() {
  renderTable(
    "documentsTable",
    [
      { label: "Data", key: "date" },
      { label: "Deputado", render: (row) => `${escapeHtml(row.deputy)}<br><span class="row-meta">${escapeHtml(row.party)} • ${escapeHtml(row.uf)}</span>` },
      { label: "Categoria", key: "category" },
      { label: "Fornecedor", render: (row) => `${escapeHtml(row.supplier)}<br><span class="row-meta">${escapeHtml(row.cnpjcpf)}</span>` },
      { label: "Valor", className: "money", render: (row) => brlFull.format(row.value) },
      { label: "Documento", key: "document" },
      { label: "Link", render: (row) => (row.url ? `<a href="${escapeHtml(row.url)}" target="_blank" rel="noreferrer">abrir</a>` : "") },
    ],
    filteredDocuments().slice(0, 80),
  );
}

function drawMonthlyChart() {
  const canvas = $("monthlyChart");
  const ctx = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth || 900;
  const cssHeight = canvas.clientHeight || 320;
  canvas.width = cssWidth * ratio;
  canvas.height = cssHeight * ratio;
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const data = state.data.series.monthly;
  const pad = { left: 62, right: 16, top: 20, bottom: 38 };
  const width = cssWidth - pad.left - pad.right;
  const height = cssHeight - pad.top - pad.bottom;
  const max = Math.max(...data.map((row) => row.total), 1);

  ctx.strokeStyle = "#d9ded8";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, pad.top + height);
  ctx.lineTo(pad.left + width, pad.top + height);
  ctx.stroke();

  ctx.fillStyle = "#64707d";
  ctx.font = "12px system-ui";
  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + height - (height * i) / 4;
    const value = (max * i) / 4;
    ctx.fillText(brl.format(value), 4, y + 4);
    ctx.strokeStyle = "#edf0ed";
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + width, y);
    ctx.stroke();
  }

  const barWidth = Math.max(18, width / Math.max(data.length, 1) - 12);
  data.forEach((row, index) => {
    const x = pad.left + index * (width / data.length) + 6;
    const barHeight = (row.total / max) * (height - 6);
    const y = pad.top + height - barHeight;
    ctx.fillStyle = index % 2 ? "#2c6fb7" : "#27745f";
    ctx.fillRect(x, y, barWidth, barHeight);
    ctx.fillStyle = "#1f2933";
    ctx.fillText(String(row.month).padStart(2, "0"), x + barWidth / 2 - 7, pad.top + height + 22);
  });
}

function renderAll() {
  const deputies = filteredDeputies();
  const suppliers = filteredSuppliers();
  renderBars("deputyRanking", deputies, "deputy", (row) => `${row.party} • ${row.uf} • ${num.format(row.count)} docs • principal: ${row.main_category}`, "total", 12);
  renderBars("categoryRanking", state.data.rankings.categories, "category", (row) => `${num.format(row.count)} documentos`, "total", 12);
  renderSuppliers(suppliers);
  renderBars("partyRanking", state.data.rankings.parties, "party", (row) => `${num.format(row.count)} documentos`, "total", 12);
  renderBars("ufRanking", state.data.rankings.ufs, "uf", (row) => `${num.format(row.count)} documentos`, "total", 12);
  renderAlerts();
  renderDocuments();
  drawMonthlyChart();
}

function hydrateFilters() {
  const parties = [...new Set(state.data.rankings.deputies.map((row) => row.party).filter(Boolean))].sort();
  const ufs = [...new Set(state.data.rankings.deputies.map((row) => row.uf).filter(Boolean))].sort();
  const categories = state.data.rankings.categories.map((row) => row.category).sort();
  $("partyFilter").innerHTML = optionList(parties, "Todos");
  $("ufFilter").innerHTML = optionList(ufs, "Todas");
  $("categoryFilter").innerHTML = optionList(categories, "Todas");

  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderAll();
  });
  $("partyFilter").addEventListener("change", (event) => {
    state.party = event.target.value;
    renderAll();
  });
  $("ufFilter").addEventListener("change", (event) => {
    state.uf = event.target.value;
    renderAll();
  });
  $("categoryFilter").addEventListener("change", (event) => {
    state.category = event.target.value;
    renderAll();
  });
  $("clearFilters").addEventListener("click", () => {
    state.query = "";
    state.party = "";
    state.uf = "";
    state.category = "";
    $("searchInput").value = "";
    $("partyFilter").value = "";
    $("ufFilter").value = "";
    $("categoryFilter").value = "";
    renderAll();
  });
}

async function init() {
  const response = await fetch("data/dashboard.json", { cache: "no-store" });
  state.data = await response.json();
  const meta = state.data.meta;
  const summary = state.data.summary;
  const leadDeputy = state.data.rankings.deputies[0];
  const leadCategory = state.data.rankings.categories[0];
  const leadSupplier = state.data.rankings.suppliers[0];

  setText("updatedAt", `Gerado em ${new Date(meta.generated_at).toLocaleString("pt-BR")} • ${summary.first_date} a ${summary.last_date}`);
  $("sourceLink").href = meta.source_url;
  setText("methodologyNote", meta.methodology_note);
  setText("kpiTotal", brl.format(summary.total));
  setText("kpiDocs", num.format(summary.documents));
  setText("kpiDeputies", num.format(summary.deputies));
  setText("kpiSuppliers", num.format(summary.suppliers));
  setText("kpiAvgDoc", brlFull.format(summary.avg_per_doc));
  setText("kpiAlerts", num.format(summary.alerts));
  setText("leadDeputy", leadDeputy ? leadDeputy.deputy : "-");
  setText(
    "leadDeputyMeta",
    leadDeputy ? `${leadDeputy.party} • ${leadDeputy.uf} • ${brlFull.format(leadDeputy.total)}` : "-",
  );
  setText("leadCategory", leadCategory ? leadCategory.category.replace(/\.$/, "") : "-");
  setText(
    "leadCategoryMeta",
    leadCategory ? `${brlFull.format(leadCategory.total)} • ${num.format(leadCategory.count)} documentos` : "-",
  );
  setText("leadSupplier", leadSupplier ? leadSupplier.supplier : "-");
  setText(
    "leadSupplierMeta",
    leadSupplier ? `${brlFull.format(leadSupplier.total)} • ${num.format(leadSupplier.count)} documentos` : "-",
  );

  hydrateFilters();
  renderAll();
  window.addEventListener("resize", drawMonthlyChart);
}

init().catch((error) => {
  document.body.innerHTML = `<main><section class="notice"><strong>Erro ao carregar dados.</strong> ${escapeHtml(error.message)}</section></main>`;
});
