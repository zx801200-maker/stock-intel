/* Stock Intel v2.0 互動式前端邏輯（全球多語新聞 + 台股三大法人 + 2年期策略回測 + 互動K線） */

(function () {
  "use strict";

  const state = {
    report: null,
    selectedSymbol: null,
    selectedStrategyId: null,
    customStocks: [],
    marketFilter: "ALL",
    sectorFilter: "ALL",
    sortBy: "total",
    searchQuery: "",
    newsFilter: "ALL",
    subChartMode: "volume",
    hoveredIndex: null,
    creditMarketFilter: "ALL",
    creditSort: "risk_desc",
    selectedCreditSymbol: null,
    watchlist: [],
  };

  const isStandalone = Boolean(window.__INITIAL_REPORT__);
  const $ = (id) => document.getElementById(id);

  function showToast(msg, duration = 3000) {
    const el = $("statusToast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("show"), duration);
  }

  function esc(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(v, digits = 2, suffix = "") {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(digits) + suffix;
  }

  function fmtSigned(v, digits = 2, suffix = "") {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    return (n >= 0 ? "+" : "") + n.toFixed(digits) + suffix;
  }

  function fmtSignedInt(v, suffix = "") {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    const n = Math.round(Number(v));
    return (n >= 0 ? "+" : "") + n.toLocaleString() + suffix;
  }

  function fmtMarketCap(val, currency) {
    if (!val || Number.isNaN(Number(val))) return "—";
    const n = Number(val);
    if (currency === "TWD") {
      if (n >= 1e12) return (n / 1e12).toFixed(2) + " 兆 TWD";
      if (n >= 1e8) return (n / 1e8).toFixed(0) + " 億 TWD";
    }
    if (n >= 1e12) return "$" + (n / 1e12).toFixed(2) + "T";
    if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return "$" + (n / 1e6).toFixed(0) + "M";
    return String(n);
  }

  function sentimentClass(score, invert = false) {
    const eff = invert ? -score : score;
    if (eff > 0.15) return "text-bull";
    if (eff < -0.15) return "text-bear";
    return "text-neutral";
  }

  function tagClassForLabel(label) {
    if (/(強烈利多|高度利多|溫和利多|利多|偏多|強力關注|偏多布局|強勢多頭|買超|大買|持有偏多|護盤)/.test(label)) return "tag-bull";
    if (/(警戒利空|溫和利空|偏空|利空|謹慎避開|空頭|賣超|大賣)/.test(label)) return "tag-bear";
    return "tag-neutral";
  }

  function getAllStocks() {
    if (!state.report) return [];
    const map = new Map();
    for (const s of state.customStocks) map.set(s.symbol, s);
    for (const s of state.report.stocks || []) {
      if (!map.has(s.symbol)) map.set(s.symbol, s);
    }
    return Array.from(map.values());
  }

  /* ---- 渲染分頁 1：全球總經 + 區域溫度計 + 台股三大法人 ---- */
  function renderMacro() {
    const r = state.report;
    const m = r.macro;

    const dt = new Date(r.generated_at);
    const localStr = Number.isNaN(dt.getTime()) ? r.generated_at : dt.toLocaleString("zh-TW", { hour12: false });
    $("metaStamp").textContent = `更新：${localStr} | 全球 ${r.news_count} 則情資・${r.stocks_analyzed} 檔標的`;

    $("engineBadge").textContent = m.analysis_engine === "local_quant" ? "內建多語量化引擎" : `AI 引擎：${m.analysis_engine}`;
    $("modeBadge").textContent = isStandalone ? "離線報告快照" : r.data_mode.toUpperCase();

    const stanceEl = $("stanceLabel");
    stanceEl.textContent = m.stance;
    stanceEl.className = "stance-label " + (m.overall_score >= 10 ? "text-bull" : m.overall_score <= -10 ? "text-bear" : "text-neutral");

    const scoreEl = $("stanceScore");
    scoreEl.textContent = fmtSigned(m.overall_score, 1);
    scoreEl.className = "stance-score mono " + (m.overall_score >= 10 ? "text-bull" : m.overall_score <= -10 ? "text-bear" : "text-neutral");

    $("confidenceVal").textContent = `${m.confidence}%`;
    $("gaugeMarker").style.left = `${Math.max(2, Math.min(98, (m.overall_score + 100) / 2))}%`;

    $("subNews").textContent = fmtSigned(m.news_sentiment_score, 1);
    $("subNews").className = "sub-score-val mono " + sentimentClass(m.news_sentiment_score);
    $("subMom").textContent = fmtSigned(m.market_momentum_score, 1);
    $("subMom").className = "sub-score-val mono " + sentimentClass(m.market_momentum_score);
    $("subRisk").textContent = fmtSigned(m.risk_index_score, 1);
    $("subRisk").className = "sub-score-val mono " + sentimentClass(m.risk_index_score);

    $("executiveSummary").textContent = m.executive_summary;

    const llmBox = $("llmCommentaryBox");
    if (m.llm_commentary) {
      llmBox.style.display = "block";
      llmBox.innerHTML = `<strong>AI 策略師深度推演：</strong>${esc(m.llm_commentary)}`;
    } else {
      llmBox.style.display = "none";
    }

    $("actionPlanList").innerHTML = (m.action_plan || []).map((a) => `<li>${esc(a)}</li>`).join("");

    $("benchmarkGrid").innerHTML = (m.benchmarks || [])
      .map((b) => {
        const c1Cls = sentimentClass(b.change_pct_1d, b.invert_sentiment);
        const c5Cls = sentimentClass(b.change_pct_5d, b.invert_sentiment);
        return `
          <div class="bm-card">
            <div class="bm-cat">${esc(b.category)}</div>
            <div class="bm-name" title="${esc(b.name)}">${esc(b.name)}</div>
            <div class="bm-price mono">${fmtNum(b.price, 2)}</div>
            <div class="bm-changes mono">
              <span class="${c1Cls}">1日 ${fmtSigned(b.change_pct_1d, 2, "%")}</span>
              <span class="${c5Cls}">5日 ${fmtSigned(b.change_pct_5d, 2, "%")}</span>
            </div>
          </div>
        `;
      })
      .join("");

    // 台股大盤三大法人
    const twInst = m.tw_institutional;
    const twPanel = $("twInstPanel");
    if (twInst && twInst.date) {
      twPanel.style.display = "block";
      $("twInstSub").textContent = twInst.summary;
      const sigEl = $("twInstSignal");
      sigEl.textContent = `${twInst.date} ・ ${twInst.signal}`;
      sigEl.className = "tag " + tagClassForLabel(twInst.signal);

      const cells = [
        ["外資及陸資", twInst.foreign_net_billion],
        ["投信", twInst.trust_net_billion],
        ["自營商（含避險）", twInst.dealer_net_billion],
        ["三大法人合計", twInst.total_net_billion],
      ];
      $("twInstStrip").innerHTML = cells
        .map(
          ([lbl, val]) => `
          <div class="inst-cell">
            <div class="kpi-label">${esc(lbl)}</div>
            <div class="inst-val mono ${sentimentClass(val)}">${fmtSigned(val, 2, " 億")}</div>
          </div>
        `
        )
        .join("");
    } else {
      twPanel.style.display = "none";
    }

    // AI 信用風險雷達快覽橫幅
    const crBanner = $("macroCreditBanner");
    const cr = r.credit_radar;
    if (cr && crBanner) {
      crBanner.style.display = "flex";
      const lvCls = cr.systemic_score >= 48 ? "tag-bear" : (cr.systemic_score >= 30 ? "tag-neutral" : "tag-bull");
      $("macroCreditBadge").textContent = `${cr.risk_level} ・ ${Number(cr.systemic_score).toFixed(1)} / 100`;
      $("macroCreditBadge").className = "tag mono " + lvCls;
      $("macroCreditSpread").textContent = cr.spread_regime || "—";
      $("macroCreditSummary").textContent = cr.ai_summary || "";
    } else if (crBanner) {
      crBanner.style.display = "none";
    }

    // 全球 7 大板塊新聞情緒
    $("regionGrid").innerHTML = (m.region_summary || [])
      .map(
        (rg) => `
        <div class="region-card">
          <div class="region-top">
            <strong>${esc(rg.region)}</strong>
            <span class="tag ${tagClassForLabel(rg.direction)} mono">${esc(rg.direction)} ${fmtSigned(rg.avg_score, 0)}</span>
          </div>
          <div class="panel-sub mono" style="margin-bottom:4px;">蒐集 ${rg.news_count} 則情資</div>
          <div class="panel-sub" title="${esc(rg.top_headline)}" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">${esc(rg.top_headline)}</div>
        </div>
      `
      )
      .join("");

    $("bullCatalysts").innerHTML = (m.bullish_catalysts || []).map((c) => `<li>${esc(c)}</li>`).join("");
    $("bearRisks").innerHTML = (m.bearish_risks || []).map((c) => `<li>${esc(c)}</li>`).join("");

    $("themeGrid").innerHTML = (m.themes || [])
      .map(
        (t) => `
        <div class="theme-card">
          <div class="theme-head">
            <span class="theme-name">${esc(t.theme_name)}</span>
            <span class="tag ${tagClassForLabel(t.direction)} mono">${esc(t.direction)} ${fmtSigned(t.score, 0)}</span>
          </div>
          <p class="theme-desc">${esc(t.reasoning)}</p>
        </div>
      `
      )
      .join("");

    $("disclaimerText").textContent = r.disclaimer || "";
  }

  /* ---- 消息面清單 & 完整報導閱讀器 Modal（支援即時全文擷取與前往來源網站驗證） ---- */
  let _lastModalSector = null;
  let _lastModalStock = null;

  function _hostOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "";
    }
  }

  function closeNewsModal() {
    const m = $("newsModal");
    if (m) m.style.display = "none";
  }

  function openStockNewsModal(stock) {
    _lastModalSector = null;
    _lastModalStock = stock;
    const modal = $("newsModal");
    $("modalBackBtn").style.display = "none";
    $("modalTitle").textContent = `${stock.name} (${stock.symbol}) — 個股消息面與來源驗證`;
    const rel = stock.related_news || [];
    $("modalSub").textContent = `${stock.sector_name} ｜ 共 ${rel.length} 則關聯消息 ｜ 點擊任一報導檢視完整內文與來源網站`;
    $("modalFooter").style.display = "none";

    if (!rel.length) {
      $("modalBody").innerHTML = `<div class="loading-state">此標的目前尚無收錄新聞，請點擊右上角「重新掃描全球情資」或透過即時診斷重新抓取最新報導。</div>`;
      modal.style.display = "flex";
      return;
    }

    $("modalBody").innerHTML = `
      <div style="display:flex; flex-direction:column; gap:8px;">
        ${rel
          .map(
            (item, idx) => `
          <div class="modal-news-card" data-sidx="${idx}">
            <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
              <div style="font-weight:700; font-size:14px; color:var(--text-primary);">${esc(item.title)}</div>
              <span class="tag ${tagClassForLabel(item.sentiment_label || "中性")}">${esc(item.event_type || item.sentiment_label || "消息")}</span>
            </div>
            ${item.event_reason || item.reason ? `<div class="panel-sub" style="margin-top:4px; color:var(--text-secondary);">${esc(item.event_reason || item.reason)}</div>` : ""}
            <div class="news-meta" style="margin-top:6px;">
              <span>${esc(item.macro_region || "")}・${esc(item.source || "")}</span>
              ${item.is_official ? `<span class="tag tag-brand">官方公告</span>` : ""}
              <span style="color:var(--brand); font-weight:600; margin-left:auto;">點擊閱讀完整內文與來源 →</span>
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    `;

    $("modalBody").querySelectorAll(".modal-news-card").forEach((el) => {
      el.addEventListener("click", () => {
        const idx = Number(el.getAttribute("data-sidx"));
        if (rel[idx]) openArticleModal(rel[idx], true);
      });
    });
    modal.style.display = "flex";
  }

  function openSectorNewsModal(sector) {
    _lastModalStock = null;
    _lastModalSector = sector;
    const modal = $("newsModal");
    $("modalBackBtn").style.display = "none";
    $("modalTitle").textContent = `${sector.name} — 消息面要素與相關報導`;
    $("modalSub").textContent = `產業評分 ${sector.score.toFixed(1)} (${sector.outlook_label}) ｜ 共 ${sector.news_count} 則相關情報 ｜ 點擊任一報導檢視完整內文與來源網站`;
    $("modalFooter").style.display = "none";

    const bullList = sector.bullish_catalysts_news || [];
    const bearList = sector.bearish_catalysts_news || [];
    const extraList = (sector.top_headlines || []).filter(
      (h) => !bullList.some((b) => b.title === h.title) && !bearList.some((r) => r.title === h.title)
    );

    const renderGroup = (heading, cls, arr, prefix) => {
      if (!arr.length) return "";
      return `
        <div>
          <div class="stance-kicker ${cls}" style="margin-bottom:8px;">${heading}（${arr.length} 則）</div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            ${arr
              .map(
                (item, idx) => `
              <div class="modal-news-card" data-grp="${prefix}" data-idx="${idx}">
                <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
                  <div style="font-weight:700; font-size:14px; color:var(--text-primary);">${esc(item.title)}</div>
                  <span class="tag ${tagClassForLabel(item.sentiment_label || (prefix === "bull" ? "利多" : "利空"))}">${esc(item.event_type || item.sentiment_label || "消息")}</span>
                </div>
                ${item.reason || item.event_reason ? `<div class="panel-sub" style="margin-top:4px; color:var(--text-secondary);">${esc(item.reason || item.event_reason)}</div>` : ""}
                <div class="news-meta" style="margin-top:6px;">
                  <span>${esc(item.macro_region || "")}・${esc(item.source || "")}</span>
                  ${item.is_official ? `<span class="tag tag-brand">官方公告</span>` : ""}
                  <span style="color:var(--brand); font-weight:600; margin-left:auto;">點擊閱讀完整內文與來源 →</span>
                </div>
              </div>
            `
              )
              .join("")}
          </div>
        </div>
      `;
    };

    const htmlBlocks = [
      sector.news_summary_reason
        ? `<div class="llm-box"><strong>消息面綜合解讀：</strong>${esc(sector.news_summary_reason)}</div>`
        : "",
      renderGroup("▲ 消息面利多要素（合約／官方核准／勝訴／訂單）", "text-bull", bullList, "bull"),
      renderGroup("▼ 消息面利空事由（監管調查／出口管制／拋售／衝突）", "text-bear", bearList, "bear"),
      renderGroup("其他關聯新聞", "", extraList, "extra"),
    ].filter(Boolean);

    $("modalBody").innerHTML = htmlBlocks.length
      ? htmlBlocks.join("")
      : `<div class="loading-state">此產業近期尚無歸類之新聞頭條，建議透過右上角「重新掃描全球情資」更新。</div>`;

    $("modalBody").querySelectorAll(".modal-news-card").forEach((el) => {
      el.addEventListener("click", () => {
        const grp = el.getAttribute("data-grp");
        const idx = Number(el.getAttribute("data-idx"));
        const pool = grp === "bull" ? bullList : grp === "bear" ? bearList : extraList;
        if (pool[idx]) openArticleModal(pool[idx], true);
      });
    });

    modal.style.display = "flex";
  }

  async function openArticleModal(item, allowBack = false) {
    const modal = $("newsModal");
    $("modalBackBtn").style.display = allowBack && (_lastModalSector || _lastModalStock) ? "inline-flex" : "none";
    $("modalTitle").textContent = item.source ? `${item.source} — 報導內文與來源驗證` : "完整報導檢視";

    const dtStr = item.published_at ? new Date(item.published_at).toLocaleString("zh-TW", { hour12: false }) : "";
    $("modalSub").textContent = [item.macro_region, item.lang ? item.lang.toUpperCase() : "", dtStr].filter(Boolean).join(" ・ ") || "即時新聞情資";

    const rawBody = (item.full_content || item.summary || "").trim();
    const reason = item.reason || item.event_reason || "";
    const evType = item.event_type || item.sentiment_label || "";
    const link = (item.final_url || item.link || "").trim();
    const domain = item.domain || _hostOf(link);

    const renderBodyParagraphs = (text, note) => {
      const paras = String(text || "")
        .split(/\n{2,}/)
        .map((p) => p.trim())
        .filter(Boolean);
      const pHtml = paras.length
        ? paras.map((p) => `<p>${esc(p)}</p>`).join("")
        : `<p class="panel-sub">此來源 RSS 僅提供標題與連結，未附帶完整內文摘要。</p>`;
      const noteHtml = note ? `<div class="catalyst-box" style="margin-top:8px;">${esc(note)}</div>` : "";
      return pHtml + noteHtml;
    };

    $("modalBody").innerHTML = `
      <div>
        <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px;">
          ${item.is_official ? `<span class="tag tag-brand">官方公告</span>` : ""}
          ${evType ? `<span class="tag ${tagClassForLabel(item.sentiment_label || evType)}">${esc(evType)}</span>` : ""}
          ${item.sentiment_score !== undefined ? `<span class="tag tag-muted mono">情緒 ${fmtSigned(item.sentiment_score, 2)}</span>` : ""}
        </div>
        <h2 style="margin:0; font-size:18px; line-height:1.45;">${esc(item.title)}</h2>
      </div>
      ${reason ? `<div class="llm-box"><strong>系統消息面歸因：</strong>${esc(reason)}</div>` : ""}
      <div>
        <div class="stance-kicker" style="margin-bottom:6px;">完整報導內文 / 摘要</div>
        <div id="articleBodyContent" class="article-body">${renderBodyParagraphs(rawBody, "")}</div>
      </div>
    `;

    const footer = $("modalFooter");
    if (link) {
      footer.style.display = "flex";
      footer.innerHTML = `
        <div class="source-url-preview mono">來源網域：<strong>${esc(domain || "外部媒體")}</strong><br/>${esc(link.slice(0, 96))}${link.length > 96 ? "..." : ""}</div>
        <a href="${esc(link)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="text-decoration:none; flex-shrink:0;">前往來源網站人工驗證 ↗</a>
      `;
    } else {
      footer.style.display = "none";
    }

    modal.style.display = "flex";

    // 若處於即時伺服器模式、且內文偏短、且非 Google 轉址，自動即時向 /api/article 抓取完整原文
    if (!isStandalone && link && rawBody.length < 480) {
      const box = $("articleBodyContent");
      if (box) {
        box.insertAdjacentHTML("beforeend", `<div id="articleFetchHint" class="panel-sub mono">正在向來源網站即時擷取完整報導內文...</div>`);
      }
      try {
        const res = await fetch(`/api/article?url=${encodeURIComponent(link)}`);
        const data = await res.json();
        const hint = $("articleFetchHint");
        if (hint) hint.remove();
        if (data.ok && data.full_text && $("articleBodyContent")) {
          $("articleBodyContent").innerHTML = renderBodyParagraphs(data.full_text, "");
          if (data.final_url && footer) {
            const fDomain = data.domain || _hostOf(data.final_url);
            footer.innerHTML = `
              <div class="source-url-preview mono">已驗證來源：<strong>${esc(fDomain)}</strong><br/>${esc(data.final_url.slice(0, 96))}${data.final_url.length > 96 ? "..." : ""}</div>
              <a href="${esc(data.final_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="text-decoration:none; flex-shrink:0;">前往來源網站人工驗證 ↗</a>
            `;
          }
        } else if (data.note && $("articleBodyContent")) {
          $("articleBodyContent").insertAdjacentHTML("beforeend", `<div class="catalyst-box">${esc(data.note)}</div>`);
        }
      } catch {
        const hint = $("articleFetchHint");
        if (hint) hint.remove();
      }
    }
  }

  /* ---- 渲染分頁 2：精簡清爽版 產業利多 × 利空排行（點擊查看消息面詳情） ---- */
  function _renderSectorCard(s, idx, mode) {
    const isBear = mode === "bear";
    const barColor = isBear ? "var(--bear)" : (s.score >= 60 ? "var(--bull)" : "var(--brand)");
    const isSel = state.sectorFilter === s.sector_id;
    const rankPrefix = isBear ? `警戒 #${idx + 1}` : `推薦 #${idx + 1}`;

    const bullNews = s.bullish_catalysts_news || [];
    const bearNews = s.bearish_catalysts_news || [];
    const totalCat = bullNews.length + bearNews.length;
    const primaryCat = isBear ? (bearNews[0] || bullNews[0]) : (bullNews[0] || bearNews[0]);
    const pillText = primaryCat
      ? `${isBear ? "▼" : "▲"} 【${primaryCat.event_type}】${String(primaryCat.title || "").slice(0, 34)}...`
      : (s.news_summary_reason || "點擊查看最新產業消息面摘要").slice(0, 44);

    return `
      <article class="sector-card ${isSel ? "selected" : ""}" data-sector-id="${esc(s.sector_id)}" style="cursor:default;">
        <div class="sector-top">
          <div>
            <div class="sector-rank">${rankPrefix} ・ ${esc(s.en_name)}</div>
            <h3 class="sector-name">${esc(s.name)}</h3>
          </div>
          <div class="sector-score-badge">
            <div class="sector-score-num mono" style="color:${barColor};">${s.score.toFixed(1)}</div>
            <span class="tag ${tagClassForLabel(s.outlook_label)}">${esc(s.outlook_label)}</span>
          </div>
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill" style="width:${Math.min(100, s.score)}%; background:${barColor};"></div>
        </div>
        <div class="sector-pill-summary" title="${esc(primaryCat ? primaryCat.title : "")}">${esc(pillText)}</div>
        <div class="sector-tickers">
          ${(s.stock_symbols || []).map((sym) => `<span class="tag tag-muted mono">${esc(sym)}</span>`).join("")}
        </div>
        <div class="sector-metrics mono">
          <span>新聞 ${fmtSigned(s.news_score, 0)} (${s.news_count}則)</span>
          <span>總經 ${fmtSigned(s.macro_tailwind_score, 0)}</span>
          <span>動能 ${fmtSigned(s.price_momentum_score, 0)}</span>
        </div>
        <div class="sector-actions">
          <button type="button" class="btn sec-news-btn" data-sid="${esc(s.sector_id)}">查看消息面 (${Math.max(totalCat, s.news_count)}則)</button>
          <button type="button" class="btn btn-primary sec-stocks-btn" data-sid="${esc(s.sector_id)}">檢視成分股 →</button>
        </div>
      </article>
    `;
  }

  function renderSectors() {
    const sectors = state.report.sectors || [];
    const bullSecs = state.report.bullish_sectors || sectors.slice(0, 4);
    const bearSecs = state.report.bearish_sectors || [...sectors].reverse().slice(0, 4);
    const secMap = new Map(sectors.map((s) => [s.sector_id, s]));

    const sel = $("sectorFilter");
    const curVal = sel.value;
    sel.innerHTML =
      `<option value="ALL">全部產業 (${sectors.length})</option>` +
      sectors.map((s) => `<option value="${esc(s.sector_id)}">${esc(s.name)} (${s.score.toFixed(1)}分)</option>`).join("");
    if ([...sel.options].some((o) => o.value === curVal)) sel.value = curVal;

    $("bullishSectorGrid").innerHTML = bullSecs.map((s, idx) => _renderSectorCard(s, idx, "bull")).join("");
    $("bearishSectorGrid").innerHTML = bearSecs.map((s, idx) => _renderSectorCard(s, idx, "bear")).join("");

    document.querySelectorAll(".sec-news-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sec = secMap.get(btn.getAttribute("data-sid"));
        if (sec) openSectorNewsModal(sec);
      });
    });

    document.querySelectorAll(".sec-stocks-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sid = btn.getAttribute("data-sid");
        state.sectorFilter = sid;
        $("sectorFilter").value = sid;
        switchTab("stocks");
        renderStockList(true);
      });
    });
  }

  /* ---- 渲染分頁 3：個股清單 + 詳情 + 三大法人 + 回測 ---- */
  function getFilteredStocks() {
    let list = getAllStocks();
    if (state.marketFilter === "WATCHLIST") list = list.filter((s) => isWatched(s.symbol));
    else if (state.marketFilter !== "ALL") list = list.filter((s) => s.market === state.marketFilter);
    if (state.sectorFilter !== "ALL") list = list.filter((s) => s.sector_id === state.sectorFilter);
    if (state.searchQuery.trim()) {
      const q = state.searchQuery.trim().toLowerCase();
      list = list.filter(
        (s) =>
          s.symbol.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          s.sector_name.toLowerCase().includes(q)
      );
    }
    list.sort((a, b) => {
      if (state.sortBy === "fundamental") return b.fundamental.score - a.fundamental.score;
      if (state.sortBy === "technical") return b.technical.score - a.technical.score;
      if (state.sortBy === "backtest") {
        return ((b.backtest && b.backtest.best_total_return_pct) || -999) - ((a.backtest && a.backtest.best_total_return_pct) || -999);
      }
      return b.total_score - a.total_score;
    });
    return list;
  }

  function renderStockList(autoSelectFirst = false) {
    const list = getFilteredStocks();
    const panel = $("stockListPanel");
    if (!list.length) {
      panel.innerHTML = `<div class="loading-state">${
        state.marketFilter === "WATCHLIST"
          ? "目前自選股清單為空，請切換至「★ 自選股追蹤」分頁或點擊個股旁的「☆ 加入自選」按鈕新增。"
          : "沒有符合篩選條件的個股，您也可以直接在右上方輸入任意美股或台股代號即時查詢。"
      }</div>`;
      return;
    }
    if (autoSelectFirst || !list.some((s) => s.symbol === state.selectedSymbol)) {
      state.selectedSymbol = list[0].symbol;
      state.selectedStrategyId = null;
    }

    panel.innerHTML = list
      .map((s) => {
        const active = s.symbol === state.selectedSymbol ? "active" : "";
        const chgCls = sentimentClass(s.technical.change_pct_1d);
        const btStr = s.backtest ? `・回測 ${fmtSigned(s.backtest.best_total_return_pct, 0, "%")}` : "";
        const instStr = s.institutional ? `・法人 ${fmtSignedInt(s.institutional.total_net_lots, "張")}` : "";
        const starMark = isWatched(s.symbol) ? `<span style="color:var(--neutral);">★</span> ` : "";
        return `
          <div class="stock-row ${active}" data-symbol="${esc(s.symbol)}">
            <div>
              <div class="stock-row-title">
                <span>${starMark}${esc(s.name)}</span>
                <span class="tag tag-muted mono">${esc(s.symbol)}</span>
              </div>
              <div class="stock-row-sub">
                基本 ${s.fundamental.grade}・技術 ${s.technical.score.toFixed(0)}${instStr}${btStr}
              </div>
            </div>
            <div class="stock-row-right">
              <div class="stock-row-score mono">${s.total_score.toFixed(1)} <span class="tag ${tagClassForLabel(s.rating)}">${esc(s.rating)}</span></div>
              <div class="stock-row-price mono">
                ${fmtNum(s.technical.price, 2)} <span class="${chgCls}">${fmtSigned(s.technical.change_pct_1d, 2, "%")}</span>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    panel.querySelectorAll(".stock-row").forEach((row) => {
      row.addEventListener("click", () => {
        state.selectedSymbol = row.getAttribute("data-symbol");
        state.selectedStrategyId = null;
        renderStockList(false);
        renderStockDetail();
      });
    });

    renderStockDetail();
  }

  function renderStockDetail() {
    const stock = getAllStocks().find((s) => s.symbol === state.selectedSymbol);
    if (!stock) return;
    const f = stock.fundamental;
    const t = stock.technical;
    const inst = stock.institutional;
    const bt = stock.backtest;

    $("detailName").textContent = stock.name;
    $("detailSymbol").textContent = `${stock.symbol} ・ ${stock.market === "TW" ? "台股" : "美股"}`;
    const ratingEl = $("detailRating");
    ratingEl.textContent = stock.rating;
    ratingEl.className = "tag " + tagClassForLabel(stock.rating);
    const starBtn = $("detailStarBtn");
    if (starBtn) {
      const watched = isWatched(stock.symbol);
      starBtn.textContent = watched ? "★ 已追蹤自選" : "☆ 加入自選";
      starBtn.classList.toggle("starred", watched);
      starBtn.setAttribute("data-sym", stock.symbol);
    }

    $("detailMeta").textContent = `${stock.sector_name} ｜ ${stock.role} ｜ 資料來源：${f.data_source}`;
    $("detailPrice").textContent = `${fmtNum(t.price, 2)} ${f.currency || ""}`;
    $("detailChanges").innerHTML =
      `<span class="${sentimentClass(t.change_pct_1d)}">1日 ${fmtSigned(t.change_pct_1d, 2, "%")}</span> ・ ` +
      `<span class="${sentimentClass(t.change_pct_5d)}">5日 ${fmtSigned(t.change_pct_5d, 2, "%")}</span> ・ ` +
      `<span class="${sentimentClass(t.change_pct_20d)}">20日 ${fmtSigned(t.change_pct_20d, 2, "%")}</span>`;

    $("detailSummary").textContent = stock.summary;
    $("kpiTotal").textContent = `${stock.total_score.toFixed(1)} / 100`;
    $("kpiFund").textContent = `${f.grade} (${f.score.toFixed(1)})`;
    $("kpiTech").textContent = `${t.trend_label} (${t.score.toFixed(1)})`;
    $("kpiSR").textContent = `${fmtNum(t.support_level, 1)} / ${fmtNum(t.resistance_level, 1)}`;

    // 台股三大法人區塊
    const instBox = $("stockInstBox");
    if (inst) {
      instBox.style.display = "block";
      const badge = $("stockInstBadge");
      badge.textContent = `${inst.date} ・ ${inst.signal} (${inst.score.toFixed(0)}分)`;
      badge.className = "tag " + tagClassForLabel(inst.signal);
      $("stockInstGrid").innerHTML = [
        ["外資買賣超", inst.foreign_net_lots],
        ["投信買賣超", inst.trust_net_lots],
        ["自營商買賣超", inst.dealer_net_lots],
        ["三大法人合計", inst.total_net_lots],
      ]
        .map(
          ([k, v]) => `
          <div class="inst-cell">
            <div class="kpi-label">${esc(k)}</div>
            <div class="inst-val mono ${sentimentClass(v)}">${fmtSignedInt(v, " 張")}</div>
          </div>
        `
        )
        .join("");
      $("instPros").innerHTML = (inst.pros || []).map((p) => `<li>${esc(p)}</li>`).join("");
      $("instCons").innerHTML = (inst.cons || []).map((c) => `<li>${esc(c)}</li>`).join("");
    } else {
      instBox.style.display = "none";
    }

    // 策略回測區塊
    const btBox = $("backtestBox");
    if (bt && bt.strategies && bt.strategies.length) {
      btBox.style.display = "block";
      if (!state.selectedStrategyId || !bt.strategies.some((x) => x.id === state.selectedStrategyId)) {
        state.selectedStrategyId = bt.best_strategy_id;
      }
      $("btSub").textContent = `區間：${bt.start_date} ~ ${bt.end_date} (${bt.trading_days} 交易日) ｜ 成本模型：${bt.fee_model} ｜ 買進持有基準：${fmtSigned(bt.benchmark_return_pct, 1, "%")} (最大回撤 ${fmtNum(bt.benchmark_max_drawdown_pct, 1, "%")})`;
      const bestBadge = $("btBestBadge");
      bestBadge.textContent = `最佳策略：${bt.best_strategy_name} (${bt.best_current_signal})`;
      bestBadge.className = "tag " + tagClassForLabel(bt.best_current_signal);

      $("btTableBody").innerHTML = bt.strategies
        .map((st) => {
          const isAct = st.id === state.selectedStrategyId ? "active" : "";
          const star = st.id === bt.best_strategy_id ? "★ " : "";
          return `
            <tr class="bt-row ${isAct}" data-stid="${esc(st.id)}">
              <td><strong>${star}${esc(st.name)}</strong></td>
              <td class="mono ${sentimentClass(st.total_return_pct)}">${fmtSigned(st.total_return_pct, 1, "%")}</td>
              <td class="mono ${sentimentClass(st.alpha_pct)}">${fmtSigned(st.alpha_pct, 1, "%")}</td>
              <td class="mono">${fmtSigned(st.cagr_pct, 1, "%")}</td>
              <td class="mono text-bear">${fmtNum(st.max_drawdown_pct, 1, "%")}</td>
              <td class="mono">${fmtNum(st.sharpe_ratio, 2)}</td>
              <td class="mono">${fmtNum(st.win_rate_pct, 1, "%")} (${st.trade_count})</td>
              <td><span class="tag ${tagClassForLabel(st.current_signal)}">${esc(st.current_signal)}</span></td>
            </tr>
          `;
        })
        .join("");

      $("btTableBody").querySelectorAll(".bt-row").forEach((tr) => {
        tr.addEventListener("click", () => {
          state.selectedStrategyId = tr.getAttribute("data-stid");
          renderStockDetail();
        });
      });
    } else {
      btBox.style.display = "none";
    }

    const metrics = [
      ["總市值", fmtMarketCap(f.market_cap, f.currency)],
      ["本益比 (PE)", fmtNum(f.pe_ratio, 1, "x")],
      ["預估本益比", fmtNum(f.forward_pe, 1, "x")],
      ["股價淨值比 (PB)", fmtNum(f.pb_ratio, 2, "x")],
      ["現金殖利率", fmtNum(f.dividend_yield_pct, 2, "%")],
      ["ROE", fmtNum(f.roe_pct, 1, "%")],
      ["毛利率", fmtNum(f.gross_margin_pct, 1, "%")],
      ["營業利益率", fmtNum(f.operating_margin_pct, 1, "%")],
      ["財報營收成長", fmtSigned(f.revenue_growth_pct, 1, "%")],
      ["法人目標價空間", fmtSigned(f.target_upside_pct, 1, "%")],
      ["RSI(14) / KD", `${fmtNum(t.rsi14, 1)} / K${fmtNum(t.k_val, 0)}`],
      ["量能比 / ATR%", `${fmtNum(t.volume_ratio, 2, "x")} / ${fmtNum(t.atr_pct, 1, "%")}`],
    ];
    if (f.twse_monthly_rev_yoy_pct !== null && f.twse_monthly_rev_yoy_pct !== undefined) {
      metrics.splice(8, 0, [`TWSE 月營收YoY (${f.twse_rev_period || ""})`, fmtSigned(f.twse_monthly_rev_yoy_pct, 1, "%")]);
      metrics.splice(9, 0, ["TWSE 累計營收YoY", fmtSigned(f.twse_cum_rev_yoy_pct, 1, "%")]);
    }

    $("fundamentalMetrics").innerHTML = metrics
      .map(
        ([k, v]) => `
        <div class="metric-cell">
          <div class="metric-cell-k">${esc(k)}</div>
          <div class="metric-cell-v mono">${esc(v)}</div>
        </div>
      `
      )
      .join("");

    $("fundPros").innerHTML = (f.pros || []).map((p) => `<li>${esc(p)}</li>`).join("");
    $("fundCons").innerHTML = (f.cons || []).map((c) => `<li>${esc(c)}</li>`).join("");
    $("techPros").innerHTML = (t.pros || []).map((p) => `<li>${esc(p)}</li>`).join("");
    $("techCons").innerHTML = (t.cons || []).map((c) => `<li>${esc(c)}</li>`).join("");

    // 個股 AI 信用風險體檢
    const scBox = $("stockCreditBox");
    const scr = stock.credit_risk;
    if (scr && scBox) {
      scBox.style.display = "block";
      $("stockCreditDiag").textContent = scr.ai_diagnosis || "";
      const rEl = $("stockCreditRating");
      rEl.textContent = scr.credit_rating || "—";
      rEl.className = "rating-badge mono " + _creditRatingCls(scr.credit_rating);
      const lEl = $("stockCreditLevel");
      lEl.textContent = `${scr.risk_level} (${Number(scr.risk_score).toFixed(1)}分)`;
      lEl.className = "tag mono " + _creditLevelTagCls(scr.risk_score);
      const dimLabels = [
        ["leverage", "財務槓桿壓力"],
        ["liquidity", "短期流動性"],
        ["cashflow", "現金流償債力"],
        ["market_stress", "市場隱含違約"],
        ["event_risk", "AI消息信用"],
      ];
      $("stockCreditDims").innerHTML = dimLabels
        .map(([k, lbl]) => {
          const val = Number((scr.dimensions && scr.dimensions[k]) || 0);
          const col = val >= 60 ? "var(--bear)" : (val >= 38 ? "var(--neutral)" : "var(--bull)");
          return `
            <div class="credit-dim-row">
              <span>${lbl}</span>
              <div class="credit-dim-track"><div class="credit-dim-fill" style="width:${Math.min(100, val)}%; background:${col};"></div></div>
              <span class="mono" style="text-align:right; color:${col}; font-weight:700;">${val.toFixed(0)}</span>
            </div>
          `;
        })
        .join("");
    } else if (scBox) {
      scBox.style.display = "none";
    }

    const relWrap = $("relatedNewsWrap");
    const relNews = stock.related_news || [];
    if (relNews.length) {
      relWrap.style.display = "block";
      $("relatedNewsList").innerHTML = relNews
        .map(
          (n, idx) => `
          <div class="news-item modal-news-card" data-rel-idx="${idx}" style="cursor:pointer;">
            <div>
              <div class="news-title">${esc(n.title)}</div>
              <div class="news-meta">
                <span>${esc(n.macro_region || "")}・${esc(n.source || "")}</span>
                ${n.event_type ? `<span class="tag ${tagClassForLabel(n.sentiment_label)}">${esc(n.event_type)}</span>` : ""}
                <span style="color:var(--brand); font-weight:600; margin-left:auto;">點擊閱讀完整內文與來源 →</span>
              </div>
            </div>
            <span class="tag ${tagClassForLabel(n.sentiment_label)}">${esc(n.sentiment_label)}</span>
          </div>
        `
        )
        .join("");
      $("relatedNewsList").querySelectorAll("[data-rel-idx]").forEach((el) => {
        el.addEventListener("click", () => {
          const item = relNews[Number(el.getAttribute("data-rel-idx"))];
          if (item) openArticleModal(item, false);
        });
      });
    } else {
      relWrap.style.display = "block";
      $("relatedNewsList").innerHTML = `<div class="panel-sub">近期無直接針對此公司的即時新聞（系統不硬塞無關報導）。</div>`;
    }

    state.hoveredIndex = null;
    requestAnimationFrame(() => {
      drawStockChart(stock);
      drawEquityChart(stock);
    });
  }

  /* ---- 繪製策略淨值 vs 買進持有雙線權益曲線 ---- */
  function drawEquityChart(stock) {
    const canvas = $("equityChartCanvas");
    if (!canvas || !stock.backtest || !stock.backtest.strategies) return;
    const strat = stock.backtest.strategies.find((x) => x.id === state.selectedStrategyId) || stock.backtest.strategies[0];
    const curve = (strat && strat.equity_curve) || [];
    if (curve.length < 2) return;

    const wrap = canvas.parentElement;
    const width = wrap.clientWidth || 600;
    const height = wrap.clientHeight || 175;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const cs = getComputedStyle(document.documentElement);
    const colStrat = cs.getPropertyValue("--brand").trim() || "#1b4f8a";
    const colBH = cs.getPropertyValue("--chart-ma60").trim() || "#6b7280";
    const colGrid = cs.getPropertyValue("--chart-grid").trim() || "#eceae2";
    const colAxis = cs.getPropertyValue("--chart-axis").trim() || "#767f8e";

    const padL = 10, padR = 50, padT = 10, padB = 22;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    let minV = Infinity, maxV = -Infinity;
    for (const pt of curve) {
      minV = Math.min(minV, pt.strategy, pt.buyhold);
      maxV = Math.max(maxV, pt.strategy, pt.buyhold);
    }
    const span = maxV - minV || 10;
    minV -= span * 0.08;
    maxV += span * 0.08;

    const xAt = (i) => padL + (i / (curve.length - 1)) * plotW;
    const yAt = (v) => padT + (1 - (v - minV) / (maxV - minV)) * plotH;

    ctx.strokeStyle = colGrid;
    ctx.fillStyle = colAxis;
    ctx.font = "11px JetBrains Mono, monospace";
    for (let g = 0; g <= 3; g++) {
      const y = padT + (g / 3) * plotH;
      const val = maxV - (g / 3) * (maxV - minV);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(width - padR, y); ctx.stroke();
      ctx.fillText(val.toFixed(0), width - padR + 6, y + 4);
    }

    // 基期 100 虛線
    if (100 >= minV && 100 <= maxV) {
      ctx.strokeStyle = colAxis;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(padL, yAt(100)); ctx.lineTo(width - padR, yAt(100)); ctx.stroke();
      ctx.setLineDash([]);
    }

    // 買進持有曲線
    ctx.strokeStyle = colBH;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    curve.forEach((pt, i) => {
      if (i === 0) ctx.moveTo(xAt(i), yAt(pt.buyhold));
      else ctx.lineTo(xAt(i), yAt(pt.buyhold));
    });
    ctx.stroke();

    // 策略曲線
    ctx.strokeStyle = colStrat;
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    curve.forEach((pt, i) => {
      if (i === 0) ctx.moveTo(xAt(i), yAt(pt.strategy));
      else ctx.lineTo(xAt(i), yAt(pt.strategy));
    });
    ctx.stroke();

    ctx.fillStyle = colAxis;
    const step = Math.max(1, Math.floor(curve.length / 4));
    for (let i = 0; i < curve.length; i += step) {
      ctx.fillText(curve[i].date.slice(2, 7), xAt(i) - 16, height - 5);
    }
  }

  /* ---- 自繪高解析 Canvas K 線 + 均線 + 副圖 (成交量 / RSI / MACD) ---- */
  function drawStockChart(stock) {
    const canvas = $("stockChartCanvas");
    if (!canvas) return;
    const series = (stock.technical && stock.technical.series) || [];
    const wrap = canvas.parentElement;
    const width = wrap.clientWidth || 640;
    const height = wrap.clientHeight || 290;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    if (!series.length) return;

    const cs = getComputedStyle(document.documentElement);
    const colBull = cs.getPropertyValue("--bull").trim() || "#0d7a52";
    const colBear = cs.getPropertyValue("--bear").trim() || "#c23636";
    const colGrid = cs.getPropertyValue("--chart-grid").trim() || "#eceae2";
    const colAxis = cs.getPropertyValue("--chart-axis").trim() || "#767f8e";
    const colMa5 = cs.getPropertyValue("--chart-ma5").trim() || "#d97706";
    const colMa20 = cs.getPropertyValue("--chart-ma20").trim() || "#1b4f8a";
    const colMa60 = cs.getPropertyValue("--chart-ma60").trim() || "#6b7280";

    const padL = 10, padR = 54, padT = 10;
    const mainH = Math.floor(height * 0.64);
    const subTop = padT + mainH + 14;
    const subH = height - subTop - 20;
    const plotW = width - padL - padR;

    let minP = Infinity, maxP = -Infinity;
    for (const d of series) {
      minP = Math.min(minP, d.low);
      maxP = Math.max(maxP, d.high);
      if (d.ma20) { minP = Math.min(minP, d.ma20); maxP = Math.max(maxP, d.ma20); }
      if (d.ma60) { minP = Math.min(minP, d.ma60); maxP = Math.max(maxP, d.ma60); }
    }
    const pSpan = maxP - minP || 1;
    minP -= pSpan * 0.05;
    maxP += pSpan * 0.05;

    const xFor = (i) => padL + ((i + 0.5) / series.length) * plotW;
    const yPrice = (p) => padT + (1 - (p - minP) / (maxP - minP)) * mainH;

    ctx.strokeStyle = colGrid;
    ctx.lineWidth = 1;
    ctx.fillStyle = colAxis;
    ctx.font = "11px JetBrains Mono, monospace";
    for (let g = 0; g <= 4; g++) {
      const y = padT + (g / 4) * mainH;
      const val = maxP - (g / 4) * (maxP - minP);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(width - padR, y); ctx.stroke();
      ctx.fillText(val.toFixed(val >= 100 ? 0 : 2), width - padR + 5, y + 4);
    }

    const barW = Math.max(2, Math.min(10, (plotW / series.length) * 0.64));
    series.forEach((d, i) => {
      const x = xFor(i);
      const col = d.close >= d.open ? colBull : colBear;
      ctx.strokeStyle = col;
      ctx.fillStyle = col;
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(x, yPrice(d.high)); ctx.lineTo(x, yPrice(d.low)); ctx.stroke();
      const yO = yPrice(d.open), yC = yPrice(d.close);
      ctx.fillRect(x - barW / 2, Math.min(yO, yC), barW, Math.max(1.5, Math.abs(yC - yO)));
    });

    function drawLine(field, color) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      let started = false;
      series.forEach((d, i) => {
        if (d[field] === null || d[field] === undefined) return;
        const x = xFor(i), y = yPrice(d[field]);
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }
    drawLine("ma60", colMa60);
    drawLine("ma20", colMa20);
    drawLine("ma5", colMa5);

    ctx.strokeStyle = colGrid;
    ctx.beginPath(); ctx.moveTo(padL, subTop); ctx.lineTo(width - padR, subTop); ctx.stroke();

    if (state.subChartMode === "volume") {
      const maxV = Math.max(...series.map((d) => d.volume || 0), 1);
      series.forEach((d, i) => {
        const x = xFor(i);
        const h = ((d.volume || 0) / maxV) * subH;
        ctx.fillStyle = d.close >= d.open ? colBull + "66" : colBear + "66";
        ctx.fillRect(x - barW / 2, subTop + subH - h, barW, h);
      });
      ctx.fillStyle = colAxis;
      ctx.fillText("VOL", width - padR + 5, subTop + 12);
    } else if (state.subChartMode === "rsi") {
      const yRsi = (v) => subTop + (1 - v / 100) * subH;
      [30, 70].forEach((lvl) => {
        ctx.strokeStyle = colGrid;
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(padL, yRsi(lvl)); ctx.lineTo(width - padR, yRsi(lvl)); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = colAxis;
        ctx.fillText(String(lvl), width - padR + 5, yRsi(lvl) + 3);
      });
      ctx.strokeStyle = colMa20;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      series.forEach((d, i) => {
        if (d.rsi14 === null || d.rsi14 === undefined) return;
        const x = xFor(i), y = yRsi(d.rsi14);
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      });
      ctx.stroke();
    } else if (state.subChartMode === "macd") {
      const maxAbs = Math.max(...series.map((d) => Math.abs(d.macd_hist || 0)), 0.01);
      const midY = subTop + subH / 2;
      ctx.strokeStyle = colGrid;
      ctx.beginPath(); ctx.moveTo(padL, midY); ctx.lineTo(width - padR, midY); ctx.stroke();
      series.forEach((d, i) => {
        const v = d.macd_hist || 0;
        const x = xFor(i);
        const h = (Math.abs(v) / maxAbs) * (subH / 2);
        ctx.fillStyle = v >= 0 ? colBull : colBear;
        ctx.fillRect(x - barW / 2, v >= 0 ? midY - h : midY, barW, Math.max(1, h));
      });
      ctx.fillStyle = colAxis;
      ctx.fillText("MACD", width - padR + 5, midY + 4);
    }

    ctx.fillStyle = colAxis;
    const step = Math.max(1, Math.floor(series.length / 5));
    for (let i = 0; i < series.length; i += step) ctx.fillText(series[i].date.slice(5), xFor(i) - 16, height - 4);

    if (state.hoveredIndex !== null && series[state.hoveredIndex]) {
      const d = series[state.hoveredIndex];
      const hx = xFor(state.hoveredIndex), hy = yPrice(d.close);
      ctx.strokeStyle = colAxis;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(hx, padT); ctx.lineTo(hx, height - 18);
      ctx.moveTo(padL, hy); ctx.lineTo(width - padR, hy);
      ctx.stroke();
      ctx.setLineDash([]);
      $("chartHoverReadout").textContent =
        `${d.date} ｜ 開 ${fmtNum(d.open)} 高 ${fmtNum(d.high)} 低 ${fmtNum(d.low)} 收 ${fmtNum(d.close)} ｜ ` +
        `MA5 ${fmtNum(d.ma5)} ・ MA20 ${fmtNum(d.ma20)} ・ RSI ${fmtNum(d.rsi14, 1)} ・ 量 ${(d.volume || 0).toLocaleString()}`;
    }

    if (!canvas._bound) {
      canvas._bound = true;
      canvas.addEventListener("mousemove", (ev) => {
        const curStock = getAllStocks().find((s) => s.symbol === state.selectedSymbol);
        if (!curStock) return;
        const arr = (curStock.technical && curStock.technical.series) || [];
        if (!arr.length) return;
        const rect = canvas.getBoundingClientRect();
        const relX = ev.clientX - rect.left - padL;
        const idx = Math.max(0, Math.min(arr.length - 1, Math.floor((relX / (rect.width - padL - padR)) * arr.length)));
        if (idx !== state.hoveredIndex) {
          state.hoveredIndex = idx;
          drawStockChart(curStock);
        }
      });
      canvas.addEventListener("mouseleave", () => {
        state.hoveredIndex = null;
        const curStock = getAllStocks().find((s) => s.symbol === state.selectedSymbol);
        if (curStock) drawStockChart(curStock);
      });
    }
  }

  /* ---- 渲染分頁 4：全球多語系財經情資 ---- */
  function renderNews() {
    let list = (state.report && state.report.news) || [];
    if (state.newsFilter === "BULL") list = list.filter((n) => n.sentiment_score >= 0.12);
    else if (state.newsFilter === "BEAR") list = list.filter((n) => n.sentiment_score <= -0.12);
    else if (state.newsFilter !== "ALL") list = list.filter((n) => n.macro_region === state.newsFilter);

    const secMap = new Map((state.report.sectors || []).map((s) => [s.sector_id, s.name]));

    $("newsFeedList").innerHTML = list.length
      ? list
          .map((n, idx) => {
            const secTags = (n.matched_sectors || [])
              .map((sid) => `<span class="tag tag-brand">${esc(secMap.get(sid) || sid)}</span>`)
              .join("");
            const kws = (n.matched_keywords || [])
              .slice(0, 4)
              .map((k) => `<span class="mono">${esc(k)}</span>`)
              .join(" ");
            const evTag = n.event_type
              ? `<span class="tag ${n.sentiment_score >= 0 ? "tag-bull" : "tag-bear"}">${esc(n.event_type)}</span>`
              : "";
            const offTag = n.is_official ? `<span class="tag tag-brand">官方公告</span>` : "";
            return `
              <article class="news-item modal-news-card" data-news-idx="${idx}" style="cursor:pointer;">
                <div>
                  <h3 class="news-title">${esc(n.title)}</h3>
                  ${n.event_reason ? `<p class="news-summary"><strong>消息面解讀：</strong>${esc(n.event_reason)}</p>` : (n.summary ? `<p class="news-summary">${esc(n.summary)}</p>` : "")}
                  <div class="news-meta">
                    ${offTag}
                    ${evTag}
                    <span class="tag tag-muted">${esc(n.macro_region || n.region)} (${esc((n.lang || "").toUpperCase())})</span>
                    <span>${esc(n.source)}</span>
                    ${secTags}
                    ${kws ? `<span>關鍵詞：${kws}</span>` : ""}
                    <span style="color:var(--brand); font-weight:600; margin-left:auto;">閱讀完整報導與來源 →</span>
                  </div>
                </div>
                <div style="text-align:right; flex-shrink:0;">
                  <span class="tag ${tagClassForLabel(n.sentiment_label)}">${esc(n.sentiment_label)}</span>
                  <div class="panel-sub mono" style="margin-top:4px;">${fmtSigned(n.sentiment_score, 2)}</div>
                </div>
              </article>
            `;
          })
          .join("")
      : `<div class="loading-state">此篩選條件下暫無新聞。</div>`;

    $("newsFeedList").querySelectorAll("[data-news-idx]").forEach((el) => {
      el.addEventListener("click", () => {
        const item = list[Number(el.getAttribute("data-news-idx"))];
        if (item) openArticleModal(item, false);
      });
    });
  }

  /* ---- 渲染分頁 4：AI 信用風險雷達（五維互動 Canvas 雷達圖 + 利差代理 + 監控表 + 信用快訊） ---- */
  function _creditRatingCls(rating) {
    if (["AAA", "AA", "A"].includes(rating)) return "rating-ig";
    if (["BBB", "BB"].includes(rating)) return "rating-mid";
    return "rating-hy";
  }

  function _creditLevelTagCls(score) {
    const s = Number(score || 0);
    if (s >= 48) return "tag-bear";
    if (s >= 30) return "tag-neutral";
    return "tag-bull";
  }

  function drawCreditRadarCanvas(sysDims, compDims) {
    const canvas = $("creditRadarCanvas");
    if (!canvas) return;
    const wrap = canvas.parentElement;
    const width = wrap.clientWidth || 320;
    const height = wrap.clientHeight || 290;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const cs = getComputedStyle(document.documentElement);
    const colBrand = cs.getPropertyValue("--brand").trim() || "#1b4f8a";
    const colBear = cs.getPropertyValue("--bear").trim() || "#c23636";
    const colGrid = cs.getPropertyValue("--border-strong").trim() || "#cbd5e1";
    const colText = cs.getPropertyValue("--text-secondary").trim() || "#4b5563";
    const colMuted = cs.getPropertyValue("--text-muted").trim() || "#767f8e";

    const axes = [
      { key: "leverage", label: "財務槓桿" },
      { key: "liquidity", label: "短期流動性" },
      { key: "cashflow", label: "現金流償債" },
      { key: "market_stress", label: "波動違約" },
      { key: "event_risk", label: "AI消息信用" },
    ];

    const cx = width / 2;
    const cy = height / 2 + 8;
    const radius = Math.min(width, height) * 0.34;
    const N = axes.length;
    const angleAt = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / N;

    // 繪製同心五邊形網格 (20, 40, 60, 80, 100)
    ctx.strokeStyle = colGrid;
    ctx.lineWidth = 1;
    for (let ring = 1; ring <= 5; ring++) {
      const r = (radius * ring) / 5;
      ctx.globalAlpha = ring === 5 ? 0.65 : 0.35;
      ctx.beginPath();
      for (let i = 0; i < N; i++) {
        const a = angleAt(i);
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // 繪製軸線與外圍標籤
    ctx.font = "600 11.5px -apple-system, BlinkMacSystemFont, sans-serif";
    for (let i = 0; i < N; i++) {
      const a = angleAt(i);
      const xEnd = cx + Math.cos(a) * radius;
      const yEnd = cy + Math.sin(a) * radius;
      ctx.strokeStyle = colGrid;
      ctx.globalAlpha = 0.45;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(xEnd, yEnd);
      ctx.stroke();
      ctx.globalAlpha = 1;

      const lx = cx + Math.cos(a) * (radius + 24);
      const ly = cy + Math.sin(a) * (radius + 20);
      ctx.fillStyle = colText;
      ctx.textAlign = Math.cos(a) > 0.25 ? "left" : Math.cos(a) < -0.25 ? "right" : "center";
      ctx.textBaseline = Math.sin(a) > 0.25 ? "top" : Math.sin(a) < -0.25 ? "bottom" : "middle";
      const valTxt = compDims ? ` ${Math.round(Number(compDims[axes[i].key] || 0))}` : "";
      ctx.fillText(axes[i].label + valTxt, lx, ly);
    }

    // 刻度數字
    ctx.fillStyle = colMuted;
    ctx.font = "10px JetBrains Mono, monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (const lv of [40, 80]) {
      ctx.fillText(String(lv), cx + 4, cy - (radius * lv) / 100);
    }

    const drawPoly = (dimsObj, strokeColor, fillAlpha, dashed = false) => {
      if (!dimsObj) return;
      ctx.save();
      ctx.beginPath();
      for (let i = 0; i < N; i++) {
        const v = Math.max(4, Math.min(100, Number(dimsObj[axes[i].key] || 0)));
        const r = (radius * v) / 100;
        const a = angleAt(i);
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = strokeColor;
      ctx.globalAlpha = fillAlpha;
      ctx.fill();
      ctx.globalAlpha = 0.95;
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = dashed ? 2 : 2.2;
      if (dashed) ctx.setLineDash([5, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      for (let i = 0; i < N; i++) {
        const v = Math.max(4, Math.min(100, Number(dimsObj[axes[i].key] || 0)));
        const r = (radius * v) / 100;
        const a = angleAt(i);
        ctx.beginPath();
        ctx.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 3.2, 0, Math.PI * 2);
        ctx.fillStyle = strokeColor;
        ctx.fill();
      }
      ctx.restore();
    };

    drawPoly(sysDims, colBrand, 0.16, true);
    drawPoly(compDims, colBear, 0.22, false);
  }

  function renderCreditCompanyDetail(cr, item) {
    if (!item) return;
    $("radarFocusName").textContent = `${item.name} (${item.symbol})`;
    $("ccTitle").textContent = `${item.name} (${item.symbol}) — AI 信用診斷書`;
    $("ccSub").textContent = `${item.market === "TW" ? "台股" : "美股"} ・ ${item.sector_name} ・ 風險指數 ${Number(item.risk_score).toFixed(1)} (${item.risk_level})`;
    const rEl = $("ccRating");
    rEl.textContent = item.credit_rating || "—";
    rEl.className = "rating-badge mono " + _creditRatingCls(item.credit_rating);
    $("ccDiagnosis").textContent = item.ai_diagnosis || "";

    const m = item.metrics || {};
    const tiles = [
      ["負債權益比 (D/E)", m.debt_to_equity !== null && m.debt_to_equity !== undefined ? `${fmtNum(m.debt_to_equity, 0)}%` : "—"],
      ["淨負債/EBITDA", m.net_debt_to_ebitda !== null && m.net_debt_to_ebitda !== undefined ? `${fmtNum(m.net_debt_to_ebitda, 2)}x` : "—"],
      ["現金/總負債", m.cash_to_debt !== null && m.cash_to_debt !== undefined ? `${fmtNum(m.cash_to_debt, 2)}x` : "—"],
      ["流動 / 速動比", `${fmtNum(m.current_ratio, 2)} / ${fmtNum(m.quick_ratio, 2)}`],
      ["FCF 利潤率", fmtSigned(m.fcf_margin_pct, 1, "%")],
      ["60D 波動 / 回撤", `${fmtNum(m.volatility_60d_pct, 0, "%")} / ${fmtNum(m.drawdown_52w_pct, 0, "%")}`],
    ];
    $("ccMetrics").innerHTML = tiles
      .map(
        ([k, v]) => `
        <div class="metric-cell">
          <div class="metric-key">${k}</div>
          <div class="metric-val mono">${esc(v)}</div>
        </div>
      `
      )
      .join("");
    $("ccRedFlags").innerHTML = (item.red_flags || []).map((x) => `<li>${esc(x)}</li>`).join("");
    $("ccBuffers").innerHTML = (item.buffers || []).map((x) => `<li>${esc(x)}</li>`).join("");

    requestAnimationFrame(() => drawCreditRadarCanvas(cr.dimensions, item.dimensions));
  }

  function renderCreditRadar() {
    const cr = state.report && state.report.credit_radar;
    if (!cr) return;

    const scoreEl = $("creditSysScore");
    scoreEl.textContent = Number(cr.systemic_score).toFixed(1);
    scoreEl.className = "stance-score mono " + (cr.systemic_score >= 48 ? "text-bear" : (cr.systemic_score >= 30 ? "text-neutral" : "text-bull"));

    $("creditSpreadBadge").textContent = cr.spread_regime || "—";
    const lvBadge = $("creditLevelBadge");
    lvBadge.textContent = cr.risk_level || "—";
    lvBadge.className = "tag " + _creditLevelTagCls(cr.systemic_score);

    $("creditAiSummary").textContent = cr.ai_summary || "";
    $("creditWarnings").innerHTML = (cr.key_warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
    $("creditMitigations").innerHTML = (cr.mitigations || []).map((m) => `<li>${esc(m)}</li>`).join("");

    // 模擬信評分布條
    const dist = cr.rating_distribution || {};
    $("creditRatingDist").innerHTML = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]
      .map((g) => `<span class="rating-badge mono ${_creditRatingCls(g)}">${g}: ${dist[g] || 0}</span>`)
      .join("");

    // 信用市場代理指標網格
    $("creditProxyGrid").innerHTML = (cr.proxies || [])
      .map(
        (p) => `
        <div class="bm-card">
          <div class="bm-cat">${esc(p.category)}</div>
          <div class="bm-name" title="${esc(p.name)}">${esc(p.name)}</div>
          <div class="bm-price mono">${p.price !== null && p.price !== undefined ? fmtNum(p.price, 2) : fmtSigned(p.change_pct_5d, 2, "%")}</div>
          <div class="bm-changes mono">
            <span class="${p.is_stress ? "text-bear" : "text-bull"}">5日 ${fmtSigned(p.change_pct_5d, 2, "%")}</span>
            <span class="panel-sub">1月 ${fmtSigned(p.change_pct_1m, 2, "%")}</span>
          </div>
          <div style="margin-top:6px;"><span class="tag ${p.is_stress ? "tag-bear" : "tag-muted"}">${esc(p.status || "")}</span></div>
        </div>
      `
      )
      .join("");

    // 個股信用風險監控表
    let list = [...(cr.watchlist || [])];
    if (state.creditMarketFilter !== "ALL") list = list.filter((w) => w.market === state.creditMarketFilter);
    if (state.creditSort === "risk_asc") list.sort((a, b) => a.risk_score - b.risk_score);
    else list.sort((a, b) => b.risk_score - a.risk_score);

    if (!state.selectedCreditSymbol || !list.some((w) => w.symbol === state.selectedCreditSymbol)) {
      state.selectedCreditSymbol = list.length ? list[0].symbol : null;
    }

    $("creditWatchlistBody").innerHTML = list.length
      ? list
          .map((w) => {
            const active = w.symbol === state.selectedCreditSymbol ? "active-strat" : "";
            const m = w.metrics || {};
            return `
              <tr class="${active}" data-csym="${esc(w.symbol)}">
                <td><strong>${esc(w.name)}</strong> <span class="panel-sub mono">${esc(w.symbol)}</span></td>
                <td><span class="rating-badge mono ${_creditRatingCls(w.credit_rating)}">${esc(w.credit_rating)}</span></td>
                <td class="mono" style="font-weight:700;">${Number(w.risk_score).toFixed(1)}</td>
                <td class="mono">${m.debt_to_equity !== null && m.debt_to_equity !== undefined ? `${fmtNum(m.debt_to_equity, 0)}%` : "—"}</td>
                <td class="mono">${fmtNum(m.current_ratio, 2)}</td>
                <td class="mono">${fmtNum(m.volatility_60d_pct, 0, "%")}</td>
                <td><span class="tag ${_creditLevelTagCls(w.risk_score)}">${esc(w.risk_level)}</span></td>
              </tr>
            `;
          })
          .join("")
      : `<tr><td colspan="7" style="text-align:center; padding:16px;">暫無符合條件之標的</td></tr>`;

    $("creditWatchlistBody").querySelectorAll("tr[data-csym]").forEach((tr) => {
      tr.addEventListener("click", () => {
        state.selectedCreditSymbol = tr.getAttribute("data-csym");
        renderCreditRadar();
      });
    });

    const curItem = list.find((w) => w.symbol === state.selectedCreditSymbol) || list[0];
    if (curItem) renderCreditCompanyDetail(cr, curItem);
    else requestAnimationFrame(() => drawCreditRadarCanvas(cr.dimensions, null));

    // 全球 AI 信用事件預警快訊（點擊開啟完整內文與來源網站驗證 Modal）
    const cNews = cr.credit_news || [];
    $("creditNewsList").innerHTML = cNews.length
      ? cNews
          .map(
            (n, idx) => `
          <div class="news-item modal-news-card" data-cnews-idx="${idx}" style="cursor:pointer;">
            <div>
              <div class="news-title">${esc(n.title)}</div>
              <div class="news-meta">
                <span class="tag tag-bear">${esc(n.event_type)}</span>
                <span>${esc(n.macro_region || "")}・${esc(n.source || "")}</span>
                <span style="color:var(--brand); font-weight:600; margin-left:auto;">閱讀完整內文與來源 →</span>
              </div>
            </div>
          </div>
        `
          )
          .join("")
      : `<div class="loading-state">近期全球情報未偵測到重大信用違約／降評快訊。</div>`;

    $("creditNewsList").querySelectorAll("[data-cnews-idx]").forEach((el) => {
      el.addEventListener("click", () => {
        const it = cNews[Number(el.getAttribute("data-cnews-idx"))];
        if (it) openArticleModal(it, false);
      });
    });
  }

  /* ---- 自選股追蹤欄位（支援 SQLite API 持久化 + 離線 localStorage 雙模式） ---- */
  const WL_STORAGE_KEY = "stock_intel_watchlist_v1";

  function _normalizeSymInput(raw) {
    const clean = String(raw || "").trim().toUpperCase();
    if (!clean) return "";
    if (/^\d{4,6}$/.test(clean)) return `${clean}.TW`;
    return clean;
  }

  function _saveLocalWatchlist() {
    try {
      localStorage.setItem(WL_STORAGE_KEY, JSON.stringify(state.watchlist || []));
    } catch {
      /* ignore quota */
    }
  }

  function _loadLocalWatchlist() {
    try {
      const raw = localStorage.getItem(WL_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function initWatchlist() {
    const serverWl = (state.report && state.report.watchlist) || [];
    const localWl = _loadLocalWatchlist();
    const map = new Map();
    for (const item of serverWl) {
      if (item && item.symbol) map.set(item.symbol.toUpperCase(), item);
    }
    if (isStandalone || !serverWl.length) {
      for (const item of localWl) {
        if (item && item.symbol && !map.has(item.symbol.toUpperCase())) {
          map.set(item.symbol.toUpperCase(), item);
        }
      }
    }
    state.watchlist = Array.from(map.values());
    _saveLocalWatchlist();
  }

  function isWatched(symbol) {
    const norm = _normalizeSymInput(symbol);
    return (state.watchlist || []).some((w) => w.symbol.toUpperCase() === norm);
  }

  async function addWatchlistSymbol(rawSymbol, note = "") {
    const norm = _normalizeSymInput(rawSymbol);
    if (!norm) return;
    const btn = $("wlAddBtn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "加入中...";
    }
    try {
      if (!isStandalone) {
        const res = await fetch("/api/watchlist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol: norm, note: String(note || "").trim() }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `無法加入 ${norm}`);
        }
        const data = await res.json();
        if (data.stock && !getAllStocks().some((s) => s.symbol.toUpperCase() === data.stock.symbol.toUpperCase())) {
          state.customStocks = [data.stock, ...state.customStocks];
        }
        const saved = data.item;
        state.watchlist = [saved, ...state.watchlist.filter((w) => w.symbol.toUpperCase() !== saved.symbol.toUpperCase())];
        _saveLocalWatchlist();
        renderWatchlist();
        renderStockList(false);
        showToast(`已加入自選股：★ ${saved.name} (${saved.symbol})`);
        return;
      }

      // 離線模式：優先配對已收錄標的
      const found = getAllStocks().find((s) => s.symbol.toUpperCase() === norm || s.symbol.toUpperCase() === `${norm}.TW`);
      const entry = {
        symbol: found ? found.symbol : norm,
        name: found ? found.name : norm,
        market: found ? found.market : (norm.endsWith(".TW") || norm.endsWith(".TWO") ? "TW" : "US"),
        note: String(note || "").trim(),
        added_at: new Date().toISOString(),
      };
      state.watchlist = [entry, ...state.watchlist.filter((w) => w.symbol.toUpperCase() !== entry.symbol.toUpperCase())];
      _saveLocalWatchlist();
      renderWatchlist();
      renderStockList(false);
      showToast(`已加入自選股：★ ${entry.name} (${entry.symbol})`);
    } catch (err) {
      showToast(err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "+ 加入自選股";
      }
    }
  }

  async function removeWatchlistSymbol(symbol) {
    const norm = _normalizeSymInput(symbol);
    if (!isStandalone) {
      try {
        await fetch(`/api/watchlist/${encodeURIComponent(norm)}`, { method: "DELETE" });
      } catch {
        /* ignore */
      }
    }
    state.watchlist = state.watchlist.filter((w) => w.symbol.toUpperCase() !== norm);
    _saveLocalWatchlist();
    renderWatchlist();
    renderStockList(false);
    showToast(`已從自選股移除 ${norm}`);
  }

  let _editingWlSym = null;

  async function saveWatchlistNote(symbol, nextText) {
    const norm = _normalizeSymInput(symbol);
    const cur = state.watchlist.find((w) => w.symbol.toUpperCase() === norm);
    if (!cur) return;
    const trimmed = String(nextText || "").trim().slice(0, 160);
    if (!isStandalone) {
      try {
        await fetch(`/api/watchlist/${encodeURIComponent(norm)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: trimmed }),
        });
      } catch {
        /* ignore */
      }
    }
    cur.note = trimmed;
    _editingWlSym = null;
    _saveLocalWatchlist();
    renderWatchlist();
    showToast(`已更新 ${cur.symbol} 投資備忘`);
  }

  function renderWatchlist() {
    const wl = state.watchlist || [];
    if ($("wlTabCount")) $("wlTabCount").textContent = String(wl.length);

    const stockMap = new Map(getAllStocks().map((s) => [s.symbol.toUpperCase(), s]));
    const matchedStocks = wl.map((w) => stockMap.get(w.symbol.toUpperCase())).filter(Boolean);

    const avgTot = matchedStocks.length
      ? matchedStocks.reduce((a, s) => a + Number(s.total_score || 0), 0) / matchedStocks.length
      : null;
    const avgCredit = matchedStocks.length
      ? matchedStocks.reduce((a, s) => a + Number((s.credit_risk && s.credit_risk.risk_score) || 35), 0) / matchedStocks.length
      : null;
    const bullCnt = matchedStocks.filter((s) => ["強力關注", "偏多布局"].includes(s.rating)).length;

    if ($("wlKpiStrip")) {
      $("wlKpiStrip").innerHTML = `
        <div class="kpi-tile"><div class="kpi-label">自選追蹤檔數</div><div class="kpi-value mono">${wl.length} 檔</div></div>
        <div class="kpi-tile"><div class="kpi-label">自選平均綜合分</div><div class="kpi-value mono">${avgTot !== null ? avgTot.toFixed(1) : "—"}</div></div>
        <div class="kpi-tile"><div class="kpi-label">偏多／強力關注</div><div class="kpi-value mono text-bull">${bullCnt} 檔</div></div>
        <div class="kpi-tile"><div class="kpi-label">平均 AI 信用風險</div><div class="kpi-value mono">${avgCredit !== null ? avgCredit.toFixed(1) + " / 100" : "—"}</div></div>
      `;
    }

    const grid = $("watchlistGrid");
    if (!grid) return;
    if (!wl.length) {
      grid.innerHTML = `<div class="loading-state" style="grid-column:1/-1;">尚未加入任何自選股。可在上方輸入美股／台股代號（如 2330、NVDA、TSLA），或直接點擊上方熱門標的快速加入！</div>`;
      return;
    }

    const renderNoteBox = (w) => {
      const sym = w.symbol.toUpperCase();
      if (_editingWlSym === sym) {
        return `
          <div class="wl-note-box" style="gap:6px;">
            <input type="text" class="input-field wl-note-input" data-sym="${esc(sym)}" value="${esc(w.note || "")}" placeholder="輸入目標價或觀察備忘..." style="height:28px; font-size:12px; flex:1; min-width:0;" />
            <button type="button" class="btn btn-primary wl-note-save" data-sym="${esc(sym)}" style="height:28px; padding:0 9px; font-size:11px;">儲存</button>
            <button type="button" class="btn wl-note-cancel" style="height:28px; padding:0 8px; font-size:11px;">取消</button>
          </div>
        `;
      }
      return `
        <div class="wl-note-box">
          <span style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${esc(w.note || "")}">📝 ${esc(w.note || "點擊右側新增目標價或觀察備忘")}</span>
          <button type="button" class="btn wl-note-btn" data-sym="${esc(sym)}" style="height:26px; padding:0 8px; font-size:11px; flex-shrink:0;">編輯</button>
        </div>
      `;
    };

    grid.innerHTML = wl
      .map((w) => {
        const s = stockMap.get(w.symbol.toUpperCase());
        if (!s) {
          return `
            <article class="wl-card">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
                <div>
                  <div style="font-weight:700; font-size:15px;">★ ${esc(w.name || w.symbol)}</div>
                  <div class="panel-sub mono">${esc(w.symbol)} ・ ${w.market === "TW" ? "台股" : "美股"}</div>
                </div>
                <span class="tag tag-muted">待即時抓取</span>
              </div>
              ${renderNoteBox(w)}
              <div class="sector-actions">
                <button type="button" class="btn btn-primary wl-open-btn" data-sym="${esc(w.symbol)}">即時診斷 →</button>
                <button type="button" class="btn wl-del-btn" data-sym="${esc(w.symbol)}">移除</button>
              </div>
            </article>
          `;
        }
        const f = s.fundamental;
        const t = s.technical;
        const cr = s.credit_risk;
        const bt = s.backtest;
        const inst = s.institutional;
        const relNews = s.related_news || [];
        const topN = relNews[0];
        const newsPillHtml = topN
          ? `<div class="sector-pill-summary" title="${esc(topN.title)}">${esc(`${topN.sentiment_score >= 0 ? "▲" : "▼"} 【${topN.event_type || topN.sentiment_label || "消息"}】${String(topN.title || "").slice(0, 34)}${String(topN.title || "").length > 34 ? "..." : ""}`)}</div>`
          : `<div class="panel-sub" style="font-size:12px;">消息面：近期無直接針對此公司的即時新聞</div>`;
        return `
          <article class="wl-card">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px;">
              <div>
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                  <strong style="font-size:15px;">★ ${esc(s.name)}</strong>
                  <span class="tag tag-muted mono">${esc(s.symbol)}</span>
                </div>
                <div class="panel-sub" style="margin-top:2px;">${esc(s.sector_name)}</div>
              </div>
              <div style="text-align:right;" class="mono">
                <div style="font-size:17px; font-weight:800;">${fmtNum(t.price, 2)}</div>
                <div class="${sentimentClass(t.change_pct_1d)}" style="font-size:12px;">1日 ${fmtSigned(t.change_pct_1d, 2, "%")}</div>
              </div>
            </div>

            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              <span class="tag ${tagClassForLabel(s.rating)} mono">${esc(s.rating)} (${s.total_score.toFixed(1)})</span>
              <span class="tag tag-muted mono">基本 ${esc(f.grade)}</span>
              <span class="tag ${tagClassForLabel(t.trend_label)}">${esc(t.trend_label)}</span>
              ${cr ? `<span class="rating-badge mono ${_creditRatingCls(cr.credit_rating)}">信評 ${esc(cr.credit_rating)}</span>` : ""}
            </div>

            ${newsPillHtml}

            <div class="sector-metrics mono" style="padding-top:6px;">
              <span>${inst ? `法人 ${fmtSignedInt(inst.total_net_lots, "張")}` : `RSI ${fmtNum(t.rsi14, 0)}`}</span>
              <span>${bt ? `回測 ${fmtSigned(bt.best_total_return_pct, 1, "%")} (${bt.best_current_signal})` : "—"}</span>
            </div>

            ${renderNoteBox(w)}

            <div class="sector-actions" style="grid-template-columns: ${relNews.length ? "1fr 1fr auto" : "1fr auto"};">
              ${relNews.length ? `<button type="button" class="btn wl-news-btn" data-sym="${esc(s.symbol)}">查看消息面 (${relNews.length})</button>` : ""}
              <button type="button" class="btn btn-primary wl-open-btn" data-sym="${esc(s.symbol)}">深度診斷 →</button>
              <button type="button" class="btn wl-del-btn" data-sym="${esc(w.symbol)}" title="移除自選">✕</button>
            </div>
          </article>
        `;
      })
      .join("");

    grid.querySelectorAll(".wl-news-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const s = stockMap.get(btn.getAttribute("data-sym").toUpperCase());
        if (s) openStockNewsModal(s);
      });
    });
    grid.querySelectorAll(".wl-open-btn").forEach((btn) => {
      btn.addEventListener("click", () => lookupCustomStock(btn.getAttribute("data-sym")));
    });
    grid.querySelectorAll(".wl-del-btn").forEach((btn) => {
      btn.addEventListener("click", () => removeWatchlistSymbol(btn.getAttribute("data-sym")));
    });
    grid.querySelectorAll(".wl-note-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        _editingWlSym = btn.getAttribute("data-sym");
        renderWatchlist();
      });
    });
    grid.querySelectorAll(".wl-note-save").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sym = btn.getAttribute("data-sym");
        const inp = grid.querySelector(`.wl-note-input[data-sym="${CSS.escape(sym)}"]`);
        saveWatchlistNote(sym, inp ? inp.value : "");
      });
    });
    grid.querySelectorAll(".wl-note-cancel").forEach((btn) => {
      btn.addEventListener("click", () => {
        _editingWlSym = null;
        renderWatchlist();
      });
    });
    grid.querySelectorAll(".wl-note-input").forEach((inp) => {
      inp.focus();
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") saveWatchlistNote(inp.getAttribute("data-sym"), inp.value);
        if (e.key === "Escape") { _editingWlSym = null; renderWatchlist(); }
      });
    });
  }

  function renderAll() {
    $("loadingBox").style.display = "none";
    $("appContent").style.display = "block";
    initWatchlist();
    renderMacro();
    renderSectors();
    renderWatchlist();
    renderStockList(false);
    renderCreditRadar();
    renderNews();
  }

  function switchTab(tabName) {
    document.querySelectorAll(".nav-tab").forEach((btn) => btn.classList.toggle("active", btn.getAttribute("data-tab") === tabName));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabName}`));
    if (tabName === "stocks") {
      const curStock = getAllStocks().find((s) => s.symbol === state.selectedSymbol);
      if (curStock) {
        requestAnimationFrame(() => {
          drawStockChart(curStock);
          drawEquityChart(curStock);
        });
      }
    } else if (tabName === "credit") {
      renderCreditRadar();
    } else if (tabName === "watchlist") {
      renderWatchlist();
    }
  }

  async function loadReport(force = false) {
    if (isStandalone && !force) {
      state.report = window.__INITIAL_REPORT__;
      renderAll();
      return;
    }
    if (isStandalone && force) {
      showToast("目前為離線報告檔，請執行 python3 run.py serve 啟動即時伺服器以重新抓取。");
      return;
    }

    const btn = $("refreshBtn");
    btn.disabled = true;
    btn.textContent = "掃描中...";
    try {
      const res = await fetch(force ? "/api/refresh" : "/api/report", { method: force ? "POST" : "GET" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.report = await res.json();
      renderAll();
      if (force) showToast("已完成全球多語情資、三大法人、AI 信用風險雷達與策略回測更新");
    } catch (err) {
      $("loadingBox").textContent = `載入失敗：${err.message}，請稍後重試。`;
      showToast(`更新失敗：${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "重新掃描全球情資";
    }
  }

  async function lookupCustomStock(rawSymbol) {
    const clean = rawSymbol.trim().toUpperCase();
    if (!clean) return;
    const existing = getAllStocks().find((s) => s.symbol === clean || s.symbol === `${clean}.TW` || s.symbol === `${clean}.TWO`);
    if (existing) {
      state.marketFilter = "ALL";
      state.sectorFilter = "ALL";
      $("sectorFilter").value = "ALL";
      state.selectedSymbol = existing.symbol;
      state.selectedStrategyId = null;
      switchTab("stocks");
      renderStockList(false);
      showToast(`已定位至 ${existing.name} (${existing.symbol})`);
      return;
    }
    if (isStandalone) {
      showToast("離線模式僅能檢視已收錄標的；啟動 python3 run.py serve 可即時查詢任意美股／台股。");
      return;
    }

    const btn = $("lookupBtn");
    btn.disabled = true;
    btn.textContent = "診斷中...";
    try {
      const res = await fetch(`/api/stock/${encodeURIComponent(clean)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `找不到代號 ${clean}`);
      }
      const stock = await res.json();
      state.customStocks = [stock, ...state.customStocks.filter((s) => s.symbol !== stock.symbol)];
      state.marketFilter = "ALL";
      state.sectorFilter = "ALL";
      $("sectorFilter").value = "ALL";
      state.selectedSymbol = stock.symbol;
      state.selectedStrategyId = null;
      switchTab("stocks");
      renderStockList(false);
      showToast(`已完成 ${stock.name} (${stock.symbol}) 基本面、信用體檢與 2 年期策略回測`);
    } catch (err) {
      showToast(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "即時診斷";
    }
  }

  document.querySelectorAll(".nav-tab").forEach((btn) => btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab"))));
  if ($("gotoCreditBtn")) $("gotoCreditBtn").addEventListener("click", () => switchTab("credit"));
  $("refreshBtn").addEventListener("click", () => loadReport(true));
  $("lookupForm").addEventListener("submit", (e) => { e.preventDefault(); lookupCustomStock($("lookupInput").value); });

  $("themeBtn").addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    document.documentElement.setAttribute("data-theme", isDark ? "light" : "dark");
    $("themeBtn").textContent = isDark ? "深色模式" : "淺色模式";
    const curStock = getAllStocks().find((s) => s.symbol === state.selectedSymbol);
    if (curStock) requestAnimationFrame(() => { drawStockChart(curStock); drawEquityChart(curStock); });
    if ($("tab-credit") && $("tab-credit").classList.contains("active")) renderCreditRadar();
  });

  document.querySelectorAll(".chip[data-market]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".chip[data-market]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.marketFilter = btn.getAttribute("data-market");
      renderStockList(true);
    });
  });

  document.querySelectorAll(".credit-mkt-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".credit-mkt-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.creditMarketFilter = btn.getAttribute("data-cmkt");
      renderCreditRadar();
    });
  });
  if ($("creditSortSel")) {
    $("creditSortSel").addEventListener("change", (e) => {
      state.creditSort = e.target.value;
      renderCreditRadar();
    });
  }

  $("sectorFilter").addEventListener("change", (e) => { state.sectorFilter = e.target.value; renderStockList(true); });
  $("sortFilter").addEventListener("change", (e) => { state.sortBy = e.target.value; renderStockList(false); });
  $("stockSearch").addEventListener("input", (e) => { state.searchQuery = e.target.value; renderStockList(true); });

  document.querySelectorAll(".subchart-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subchart-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.subChartMode = btn.getAttribute("data-sub");
      const curStock = getAllStocks().find((s) => s.symbol === state.selectedSymbol);
      if (curStock) drawStockChart(curStock);
    });
  });

  document.querySelectorAll(".news-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".news-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.newsFilter = btn.getAttribute("data-nfilter");
      renderNews();
    });
  });

  const handleWlAdd = async () => {
    const symEl = $("wlSymbolInput");
    const noteEl = $("wlNoteInput");
    if (!symEl || !symEl.value.trim()) return;
    await addWatchlistSymbol(symEl.value, noteEl ? noteEl.value : "");
    symEl.value = "";
    if (noteEl) noteEl.value = "";
  };
  if ($("wlAddBtn")) $("wlAddBtn").addEventListener("click", handleWlAdd);
  if ($("wlSymbolInput")) $("wlSymbolInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); handleWlAdd(); } });
  if ($("wlNoteInput")) $("wlNoteInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); handleWlAdd(); } });
  document.querySelectorAll(".wl-quick-btn").forEach((btn) => {
    btn.addEventListener("click", () => addWatchlistSymbol(btn.getAttribute("data-qsym"), ""));
  });
  if ($("detailStarBtn")) {
    $("detailStarBtn").addEventListener("click", () => {
      const sym = $("detailStarBtn").getAttribute("data-sym") || state.selectedSymbol;
      if (!sym) return;
      if (isWatched(sym)) removeWatchlistSymbol(sym);
      else addWatchlistSymbol(sym, "");
    });
  }

  $("modalCloseBtn").addEventListener("click", closeNewsModal);
  $("modalBackBtn").addEventListener("click", () => {
    if (_lastModalStock) openStockNewsModal(_lastModalStock);
    else if (_lastModalSector) openSectorNewsModal(_lastModalSector);
  });
  $("newsModal").addEventListener("click", (e) => {
    if (e.target === $("newsModal")) closeNewsModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeNewsModal();
  });

  window.addEventListener("resize", () => {
    const curStock = getAllStocks().find((s) => s.symbol === state.selectedSymbol);
    if (curStock && $("tab-stocks").classList.contains("active")) {
      drawStockChart(curStock);
      drawEquityChart(curStock);
    }
    if ($("tab-credit") && $("tab-credit").classList.contains("active")) {
      renderCreditRadar();
    }
  });

  loadReport(false);
})();
