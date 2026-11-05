/**
 * SISTEMA DE AVALIAÇÃO DE CANDIDATOS POR JUÍZES
 * Aplicação Frontend SPA (Single Page Application)
 */

(function () {
  "use strict";

  // Estado da Aplicação
  const state = {
    token: localStorage.getItem("auth_token") || null,
    user: null,
    eventInfo: {},
    judge: {
      candidates: [],
      categories: [],
      progress: { evaluated_count: 0, total_candidates: 0, percentage: 0 },
      currentCandidate: null,
      selectedScores: {},
      filter: "all",
      searchQuery: ""
    },
    admin: {
      currentTab: "tabDashboard",
      candidates: [],
      judges: [],
      categories: [],
      rankings: [],
      matrix: null,
      stats: null,
      settings: {}
    }
  };

  // =========================================================================
  // Utilitários de Requisição HTTP (Fetch Wrapper)
  // =========================================================================

  async function apiRequest(endpoint, options = {}) {
    const headers = options.headers || {};
    headers["Accept"] = "application/json";

    if (state.token) {
      headers["Authorization"] = `Bearer ${state.token}`;
    }

    if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(endpoint, { ...options, headers });
      const data = await response.json().catch(() => ({}));

      if (response.status === 401) {
        // Sessão expirada ou não autenticada
        if (state.token) {
          showToast("Sessão expirada. Faça login novamente.", "error");
          logout();
        }
        return { success: false, error: data.error || "Não autenticado." };
      }

      if (!response.ok) {
        return { success: false, error: data.error || `Erro HTTP ${response.status}`, status: response.status, ...data };
      }

      return data;
    } catch (err) {
      console.error("Erro na requisição:", err);
      return { success: false, error: "Falha de comunicação com o servidor." };
    }
  }

  // =========================================================================
  // Notificações Toast
  // =========================================================================

  function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // =========================================================================
  // Navegação entre Telas (Views)
  // =========================================================================

  function switchView(viewId) {
    const views = [
      "viewLogin",
      "viewJudge",
      "viewJudgeEvaluation",
      "viewAdmin",
      "viewPublicResults"
    ];

    views.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = id === viewId ? "block" : "none";
    });

    updateHeaderUI();
  }

  function updateHeaderUI() {
    const headerActions = document.getElementById("headerUserActions");
    const roleBadge = document.getElementById("roleBadge");
    const userNameSpan = document.getElementById("headerUserName");
    const statusBadge = document.getElementById("votingStatusBadge");
    const eventNameHeader = document.getElementById("headerEventName");

    if (state.eventInfo && state.eventInfo.event_name) {
      eventNameHeader.textContent = state.eventInfo.event_name;
    }

    // Status da Votação
    const status = state.eventInfo.voting_status || "OPEN";
    if (status === "OPEN") {
      statusBadge.textContent = "Votação Aberta";
      statusBadge.className = "badge badge-emerald";
    } else if (status === "PAUSED") {
      statusBadge.textContent = "Votação Pausada";
      statusBadge.className = "badge badge-amber";
    } else {
      statusBadge.textContent = "Votação Encerrada";
      statusBadge.className = "badge badge-slate";
    }

    if (state.user) {
      headerActions.style.display = "flex";
      userNameSpan.textContent = state.user.name;

      roleBadge.style.display = "inline-flex";
      if (state.user.role === "ADMIN") {
        roleBadge.textContent = "Administrador";
        roleBadge.className = "badge badge-outline";
      } else {
        roleBadge.textContent = "Juiz Avaliador";
        roleBadge.className = "badge badge-outline";
      }

      const campBadge = document.getElementById("headerCampaignBadge");
      if (campBadge) {
        if (state.activeCampaign && state.activeCampaign.name) {
          campBadge.textContent = state.activeCampaign.name;
          campBadge.style.display = "inline-flex";
        } else {
          campBadge.style.display = "none";
        }
      }
    } else {
      headerActions.style.display = "none";
      roleBadge.style.display = "none";
      const campBadge = document.getElementById("headerCampaignBadge");
      if (campBadge) campBadge.style.display = "none";
    }
  }

  // =========================================================================
  // Fluxo de Autenticação
  // =========================================================================

  async function checkAuthSession() {
    const publicInfo = await apiRequest("/api/public/info");
    if (publicInfo.success) {
      state.eventInfo = publicInfo;
    }

    if (!state.token) {
      switchView("viewLogin");
      return;
    }

    const res = await apiRequest("/api/auth/me");
    if (res.success && res.user) {
      state.user = res.user;
      routeUserByRole();
    } else {
      logout();
    }
  }

  function routeUserByRole() {
    if (!state.user) {
      switchView("viewLogin");
      return;
    }

    if (state.user.role === "ADMIN") {
      switchView("viewAdmin");
      initAdminDashboard();
    } else if (state.user.role === "JUDGE") {
      switchView("viewJudge");
      loadJudgeVotingScreen();
    } else {
      switchView("viewLogin");
    }
  }

  async function handleLoginSubmit(e) {
    e.preventDefault();
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;
    const btn = document.getElementById("btnLoginSubmit");

    btn.disabled = true;
    btn.innerHTML = "<span>Autenticando...</span>";

    const res = await apiRequest("/api/auth/login", {
      method: "POST",
      body: { email, password }
    });

    btn.disabled = false;
    btn.innerHTML = `<span>Entrar no Sistema</span><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;

    if (res.success && res.token) {
      state.token = res.token;
      state.user = res.user;
      localStorage.setItem("auth_token", res.token);
      showToast(`Bem-vindo, ${res.user.name}!`, "success");
      routeUserByRole();
    } else {
      showToast(res.error || "Credenciais inválidas.", "error");
    }
  }

  function logout() {
    state.token = null;
    state.user = null;
    localStorage.removeItem("auth_token");
    apiRequest("/api/auth/logout", { method: "POST" });
    switchView("viewLogin");
    showToast("Você saiu do sistema.", "info");
  }

  // =========================================================================
  // Módulo do Juiz (Interface de Votação)
  // =========================================================================

  async function loadJudgeVotingScreen() {
    const res = await apiRequest("/api/judge/voting");
    if (!res.success) {
      showToast(res.error || "Erro ao carregar bancada de votação.", "error");
      return;
    }

    state.judge.candidates = res.candidates || [];
    state.judge.categories = res.categories || [];
    state.judge.progress = res.progress || {};
    state.eventInfo.voting_status = res.voting_status;
    state.eventInfo.allow_corrections = res.allow_corrections;
    if (res.campaign) {
      state.activeCampaign = res.campaign;
      updateHeaderUI();
    }

    renderJudgeProgress();
    renderJudgeCandidatesGrid();
  }

  function renderJudgeProgress() {
    const prog = state.judge.progress;
    const fractionEl = document.getElementById("judgeProgressFraction");
    const barEl = document.getElementById("judgeProgressBar");
    const alertEl = document.getElementById("judgeVotingClosedAlert");

    fractionEl.textContent = `${prog.evaluated_count} / ${prog.total_candidates}`;
    barEl.style.width = `${prog.percentage}%`;

    const countAll = state.judge.candidates.length;
    const countEvaluated = state.judge.candidates.filter(c => c.is_evaluated).length;
    const countPending = countAll - countEvaluated;

    document.getElementById("countAll").textContent = countAll;
    document.getElementById("countEvaluated").textContent = countEvaluated;
    document.getElementById("countPending").textContent = countPending;

    if (state.eventInfo.voting_status === "CLOSED") {
      alertEl.style.display = "flex";
    } else {
      alertEl.style.display = "none";
    }
  }

  function renderJudgeCandidatesGrid() {
    const grid = document.getElementById("judgeCandidatesGrid");
    grid.innerHTML = "";

    const filter = state.judge.filter;
    const query = state.judge.searchQuery.toLowerCase();

    const filtered = state.judge.candidates.filter(c => {
      if (filter === "pending" && c.is_evaluated) return false;
      if (filter === "evaluated" && !c.is_evaluated) return false;
      if (query && !c.name.toLowerCase().includes(query) && !(c.number || "").includes(query)) return false;
      return true;
    });

    if (filtered.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; background: white; border-radius: 12px; border: 1px dashed var(--slate-300);">
          <p style="color: var(--slate-500); font-weight: 600;">Nenhum candidato encontrado neste filtro.</p>
        </div>
      `;
      return;
    }

    filtered.forEach(cand => {
      const card = document.createElement("div");
      card.className = `candidate-judge-card ${cand.is_evaluated ? "is-evaluated" : "is-pending"}`;

      const photoUrl = cand.photo_url || "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300&auto=format&fit=crop&q=80";
      const statusBadgeHtml = cand.is_evaluated
        ? `<span class="badge badge-emerald card-badge-status">Concluído ✓</span>`
        : `<span class="badge badge-amber card-badge-status">Pendente ⏳</span>`;

      card.innerHTML = `
        <div class="card-candidate-header-clean">
          <div class="card-candidate-badge-num">Nº ${cand.number || cand.id}</div>
          ${statusBadgeHtml}
        </div>
        <div class="card-candidate-body">
          <h3 class="card-candidate-title">${cand.name}</h3>
          <p class="card-candidate-desc">${cand.description || "Sem descrição informada."}</p>
          <div class="card-candidate-footer">
            <button class="btn btn-sm btn-block ${cand.is_evaluated ? "btn-outline" : "btn-primary"}" data-cand-id="${cand.id}">
              ${cand.is_evaluated ? "Revisar Notas" : "Avaliar Candidato"}
            </button>
          </div>
        </div>
      `;

      card.querySelector("button").addEventListener("click", () => {
        openJudgeEvaluationScreen(cand);
      });

      grid.appendChild(card);
    });
  }

  function openJudgeEvaluationScreen(candidate) {
    state.judge.currentCandidate = candidate;
    state.judge.selectedScores = { ...(candidate.scores || {}) };

    document.getElementById("evalCandidateName").textContent = candidate.name;
    document.getElementById("evalCandidateNumber").textContent = `Nº ${candidate.number || candidate.id}`;
    document.getElementById("evalCandidateDesc").textContent = candidate.description || "Apresentação sem descrição.";

    const statusEl = document.getElementById("evalCurrentStatus");
    if (candidate.is_evaluated) {
      statusEl.innerHTML = `<span class="badge badge-emerald">Avaliação Já Realizada</span>`;
    } else {
      statusEl.innerHTML = `<span class="badge badge-amber">Avaliação Pendente</span>`;
    }

    renderEvaluationCategories();
    switchView("viewJudgeEvaluation");
  }

  function renderEvaluationCategories() {
    const list = document.getElementById("evalCategoriesList");
    list.innerHTML = "";

    const categories = state.judge.categories;
    const isClosed = state.eventInfo.voting_status === "CLOSED";
    const allowCorrections = state.eventInfo.allow_corrections;
    const isEvaluated = state.judge.currentCandidate && state.judge.currentCandidate.is_evaluated;

    const readOnly = isClosed || (isEvaluated && !allowCorrections);

    categories.forEach(cat => {
      const block = document.createElement("div");
      block.className = "category-eval-block";

      const currentScore = state.judge.selectedScores[cat.id] || null;

      block.innerHTML = `
        <div class="category-header-info">
          <span class="category-name-title">${cat.name}</span>
          <span class="category-selected-score" id="scoreDisplay_${cat.id}">
            ${currentScore !== null ? `Nota: ${currentScore}` : "Selecione a nota"}
          </span>
        </div>
        <p class="category-desc-info">${cat.description || "Atribua uma nota inteira de 1 a 10 para este critério."}</p>
        <div class="score-buttons-group" id="scoreGroup_${cat.id}"></div>
      `;

      const group = block.querySelector(`#scoreGroup_${cat.id}`);

      // Botões táteis de 1 a 10
      for (let scoreVal = 1; scoreVal <= 10; scoreVal++) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `btn-score ${currentScore === scoreVal ? "active" : ""}`;
        btn.textContent = scoreVal;
        btn.disabled = readOnly;

        btn.addEventListener("click", () => {
          if (readOnly) return;
          state.judge.selectedScores[cat.id] = scoreVal;

          // Atualizar estado visual
          group.querySelectorAll(".btn-score").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          block.querySelector(`#scoreDisplay_${cat.id}`).textContent = `Nota: ${scoreVal}`;
        });

        group.appendChild(btn);
      }

      list.appendChild(block);
    });

    const confirmBtn = document.getElementById("btnConfirmEvaluation");
    const confirmText = document.getElementById("btnConfirmText");

    if (readOnly) {
      confirmBtn.disabled = true;
      confirmText.textContent = isClosed ? "Votação Encerrada" : "Alterações Bloqueadas pelo Administrador";
    } else {
      confirmBtn.disabled = false;
      confirmText.textContent = isEvaluated ? "Salvar e Atualizar Avaliação" : "Salvar e Confirmar Avaliação";
    }
  }

  async function submitJudgeEvaluation() {
    const candidate = state.judge.currentCandidate;
    if (!candidate) return;

    const categories = state.judge.categories;
    const scores = state.judge.selectedScores;

    // Validar se todas as categorias receberam notas
    for (const cat of categories) {
      const score = scores[cat.id];
      if (score === undefined || score === null || score < 1 || score > 10) {
        showToast(`Por favor, atribua uma nota de 1 a 10 para a categoria: ${cat.name}`, "error");
        return;
      }
    }

    const confirmBtn = document.getElementById("btnConfirmEvaluation");
    confirmBtn.disabled = true;

    const res = await apiRequest("/api/judge/vote", {
      method: "POST",
      body: {
        candidate_id: candidate.id,
        scores: scores
      }
    });

    confirmBtn.disabled = false;

    if (res.success) {
      showToast(`Avaliação de ${candidate.name} confirmada com sucesso!`, "success");
      await loadJudgeVotingScreen();
      switchView("viewJudge");
    } else {
      showToast(res.error || "Erro ao salvar avaliação.", "error");
    }
  }

  // =========================================================================
  // Módulo Administrativo (Dashboard, Rankings, CRUDs, Governança)
  // =========================================================================

  function initAdminDashboard() {
    bindAdminNav();
    loadAdminDashboard();
  }

  function bindAdminNav() {
    document.querySelectorAll(".admin-nav-item").forEach(item => {
      item.addEventListener("click", () => {
        document.querySelectorAll(".admin-nav-item").forEach(i => i.classList.remove("active"));
        document.querySelectorAll(".admin-tab-pane").forEach(p => p.classList.remove("active"));

        item.classList.add("active");
        const tabId = item.getAttribute("data-tab");
        const pane = document.getElementById(tabId);
        if (pane) pane.classList.add("active");

        state.admin.currentTab = tabId;
        handleAdminTabLoad(tabId);
      });
    });
  }

  function handleAdminTabLoad(tabId) {
    if (tabId === "tabDashboard") loadAdminDashboard();
    else if (tabId === "tabRankings") loadAdminRankings();
    else if (tabId === "tabMonitoring") loadAdminMonitoring();
    else if (tabId === "tabCandidates") loadAdminCandidates();
    else if (tabId === "tabJudges") loadAdminJudges();
    else if (tabId === "tabCategories") loadAdminCategories();
    else if (tabId === "tabSettings") loadAdminSettings();
  }

  async function loadAdminDashboard() {
    const res = await apiRequest("/api/admin/dashboard");
    if (!res.success) {
      showToast(res.error || "Erro ao carregar dashboard.", "error");
      return;
    }

    const stats = res.stats;
    state.admin.stats = stats;
    state.eventInfo = { ...state.eventInfo, ...stats };
    if (stats.active_campaign) {
      state.activeCampaign = stats.active_campaign;
    }
    updateHeaderUI();

    document.getElementById("kpiTotalCandidates").textContent = stats.total_candidates;
    document.getElementById("kpiTotalJudges").textContent = stats.total_judges;
    document.getElementById("kpiSubmissionsDone").textContent = `${stats.completed_submissions} de ${stats.expected_submissions}`;
    document.getElementById("kpiSubmissionsPending").textContent = `${stats.pending_submissions} pendentes`;
    document.getElementById("kpiCompletionPercentage").textContent = `${stats.completion_percentage}%`;
    document.getElementById("kpiTotalNotes").textContent = `${stats.total_evaluations_recorded} notas registradas`;

    renderWinnerSpotlight(res.winners, res.is_winner_tie, stats.voting_status, stats.show_provisional_winner);
  }

  function renderWinnerSpotlight(winners, isTie, votingStatus, showProvisional) {
    const container = document.getElementById("winnerSpotlight");
    if (!container) return;

    if (!winners || winners.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 1.5rem;">
          <h3 style="color: #fbbf24; font-size: 1.2rem; font-weight: 700;">Aguardando Primeiras Avaliações</h3>
          <p style="color: #cbd5e1; font-size: 0.85rem; margin-top: 0.3rem;">Assim que os juízes confirmarem suas notas, o vencedor e a classificação serão computados automaticamente.</p>
        </div>
      `;
      return;
    }

    const isClosed = votingStatus === "CLOSED";
    const headerTitle = isClosed
      ? (isTie ? "🏆 Vencedores Oficiais do Evento (Empate em 1º Lugar)" : "🏆 Vencedor Oficial do Evento")
      : (isTie ? "⏳ Líderes Provisórios (Empate em 1º Lugar)" : "⏳ Vencedor Provisório (Apuração em Andamento)");

    let winnersHtml = "";
    winners.forEach(w => {
      winnersHtml += `
        <div class="winner-candidate-box" style="margin-top: 0.75rem;">
          <div class="winner-trophy-badge">
            <span>🏆</span>
          </div>
          <div class="winner-info">
            <h3>${w.name} ${isTie ? '<span class="badge badge-tie">Empate</span>' : ''}</h3>
            <p style="color: #cbd5e1; font-size: 0.85rem;">Inscrição Nº ${w.number || w.id} • ${w.judges_evaluated_count} juízes avaliaram • ${w.total_scores_count} notas computadas</p>
          </div>
          <div class="winner-score-badge">
            <div class="winner-score-val">${w.final_average_formatted}</div>
            <div class="winner-score-lbl">Média Final</div>
          </div>
        </div>
      `;
    });

    container.innerHTML = `
      <div class="winner-badge-header">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>
        <span>${headerTitle}</span>
      </div>
      ${winnersHtml}
    `;
  }

  async function loadAdminRankings() {
    const res = await apiRequest("/api/admin/rankings");
    if (!res.success) {
      showToast(res.error || "Erro ao carregar rankings.", "error");
      return;
    }

    state.admin.rankings = res.rankings || [];
    const tbody = document.getElementById("rankingsTableBody");
    tbody.innerHTML = "";

    if (state.admin.rankings.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem;">Nenhum candidato cadastrado.</td></tr>`;
      return;
    }

    state.admin.rankings.forEach(item => {
      const tr = document.createElement("tr");

      // Destaque visual para o pódio
      let rankDisplay = `#${item.rank}`;
      let rankClass = `rank-${item.rank}`;
      if (item.rank === 1) rankDisplay = `🥇 1º`;
      else if (item.rank === 2) rankDisplay = `🥈 2º`;
      else if (item.rank === 3) rankDisplay = `🥉 3º`;

      const tieBadge = item.is_tie ? `<span class="badge badge-tie" style="margin-left: 0.35rem;">Empate</span>` : "";

      // Detalhamento das médias por categoria
      let catAveragesHtml = "";
      if (item.category_averages) {
        Object.values(item.category_averages).forEach(c => {
          catAveragesHtml += `
            <span style="display:inline-block; margin-right: 0.6rem; font-size: 0.8rem; background: var(--slate-100); padding: 0.2rem 0.5rem; border-radius: 4px;">
              <strong>${c.category_name}:</strong> ${c.average_formatted}
            </span>
          `;
        });
      }

      tr.innerHTML = `
        <td><strong class="rank-badge ${rankClass}">${rankDisplay}</strong> ${tieBadge}</td>
        <td>
          <div style="display:flex; align-items:center; gap:0.75rem;">
            <span class="candidate-tag-small">Nº ${item.number || item.id}</span>
            <div>
              <strong>${item.name}</strong>
            </div>
          </div>
        </td>
        <td><span class="avg-pill">${item.final_average_formatted}</span></td>
        <td>${item.total_scores_count} notas</td>
        <td>${item.judges_evaluated_count} juízes</td>
        <td>${catAveragesHtml || '<span style="color:var(--slate-400);">-</span>'}</td>
      `;

      tbody.appendChild(tr);
    });
  }

  async function loadAdminMonitoring() {
    const res = await apiRequest("/api/admin/matrix");
    if (!res.success) {
      showToast(res.error || "Erro ao carregar monitoramento.", "error");
      return;
    }

    state.admin.matrix = res;

    // 1. Progresso individual dos juízes
    const judgesList = document.getElementById("judgesProgressList");
    judgesList.innerHTML = "";

    res.judge_progress.forEach(j => {
      const card = document.createElement("div");
      card.className = "judge-progress-card";
      card.style.marginBottom = "1rem";

      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <div>
            <strong>${j.judge_name}</strong> (${j.judge_email})
            ${j.is_finished ? '<span class="badge badge-emerald" style="margin-left: 0.5rem;">100% Concluído</span>' : '<span class="badge badge-amber" style="margin-left: 0.5rem;">Em Andamento</span>'}
          </div>
          <span style="font-family: var(--font-mono); font-weight: 700; color: var(--primary);">
            ${j.completed_candidates} de ${j.total_candidates} (${j.percentage}%)
          </span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" style="width: ${j.percentage}%;"></div>
        </div>
      `;

      judgesList.appendChild(card);
    });

    // 2. Matriz completa de notas
    renderScoreMatrix(res);
  }

  function renderScoreMatrix(data) {
    const container = document.getElementById("matrixContainer");
    if (!data.candidates || data.candidates.length === 0) {
      container.innerHTML = `<p style="padding: 1.5rem; text-align: center;">Nenhum candidato cadastrado.</p>`;
      return;
    }

    let headerCols = "<th>Candidato</th>";
    data.categories.forEach(cat => {
      headerCols += `<th>${cat.name}</th>`;
    });

    let bodyRows = "";
    data.candidates.forEach(cand => {
      let catCells = "";
      data.categories.forEach(cat => {
        const scoresObj = (data.matrix[cand.id] && data.matrix[cand.id][cat.id]) || {};
        const scoresList = Object.values(scoresObj);
        let cellText = "-";
        if (scoresList.length > 0) {
          const avg = (scoresList.reduce((a, b) => a + b, 0) / scoresList.length).toFixed(2);
          cellText = `<strong>${avg}</strong> <span style="font-size:0.75rem; color:var(--slate-500);">(${scoresList.join(", ")})</span>`;
        }
        catCells += `<td>${cellText}</td>`;
      });

      bodyRows += `
        <tr>
          <td>
            <strong>${cand.name}</strong>
            <span style="display:block; font-size:0.75rem; color:var(--slate-500);">Nº ${cand.number || cand.id}</span>
          </td>
          ${catCells}
        </tr>
      `;
    });

    container.innerHTML = `
      <table class="data-table">
        <thead><tr>${headerCols}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    `;
  }

  // --- CRUD: Candidatos ---
  async function loadAdminCandidates() {
    const res = await apiRequest("/api/admin/candidates");
    if (!res.success) return;

    state.admin.candidates = res.candidates || [];
    if (res.active_campaign) {
      state.activeCampaign = res.active_campaign;
      const campNameEl = document.getElementById("candidatesCampaignName");
      if (campNameEl) campNameEl.textContent = res.active_campaign.name;
      const dangerCampEl = document.getElementById("dangerCampaignName");
      if (dangerCampEl) dangerCampEl.textContent = res.active_campaign.name;
      updateHeaderUI();
    }

    const tbody = document.getElementById("candidatesTableBody");
    tbody.innerHTML = "";

    if (state.admin.candidates.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 2.5rem 1rem;">
            Nenhum candidato cadastrado nesta campanha até o momento.<br>
            <span style="font-size: 0.85rem;">Utilize o botão "Novo Candidato" ou importe múltiplos candidatos via arquivo .txt.</span>
          </td>
        </tr>
      `;
      return;
    }

    state.admin.candidates.forEach(c => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong class="candidate-tag-small">Nº ${c.number || c.id}</strong></td>
        <td><strong>${c.name}</strong></td>
        <td style="max-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${c.description || "-"}</td>
        <td>
          <div style="display:flex; gap:0.5rem;">
            <button class="btn btn-xs btn-outline" onclick='window.editCandidate(${JSON.stringify(c)})'>Editar</button>
            <button class="btn btn-xs btn-danger" onclick="window.deleteCandidate(${c.id}, '${c.name.replace(/'/g, "\\'")}')">Excluir</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  window.openCandidateModal = function () {
    document.getElementById("modalCandidateTitle").textContent = "Novo Candidato";
    document.getElementById("candidateFormId").value = "";
    document.getElementById("candidateFormName").value = "";
    document.getElementById("candidateFormDesc").value = "";
    document.getElementById("modalCandidate").classList.add("active");
  };

  window.editCandidate = function (cand) {
    document.getElementById("modalCandidateTitle").textContent = "Editar Candidato";
    document.getElementById("candidateFormId").value = cand.id;
    document.getElementById("candidateFormName").value = cand.name;
    document.getElementById("candidateFormDesc").value = cand.description || "";
    document.getElementById("modalCandidate").classList.add("active");
  };

  window.closeCandidateModal = function () {
    document.getElementById("modalCandidate").classList.remove("active");
  };

  async function handleCandidateFormSubmit(e) {
    e.preventDefault();
    const id = document.getElementById("candidateFormId").value;
    const name = document.getElementById("candidateFormName").value.trim();
    const description = document.getElementById("candidateFormDesc").value.trim();

    const url = id ? `/api/admin/candidates/${id}` : "/api/admin/candidates";
    const method = id ? "PUT" : "POST";

    const res = await apiRequest(url, {
      method,
      body: { name, description }
    });

    if (res.success) {
      showToast(res.message || "Candidato salvo com sucesso!", "success");
      closeCandidateModal();
      loadAdminCandidates();
      loadAdminDashboard();
    } else {
      showToast(res.error || "Erro ao salvar candidato.", "error");
    }
  }

  // --- Importação em Lote (.txt) ---
  window.openBulkCandidateModal = function () {
    const fileInput = document.getElementById("bulkCandidateFileInput");
    if (fileInput) fileInput.value = "";
    const textarea = document.getElementById("bulkCandidateText");
    if (textarea) textarea.value = "";
    window.updateBulkCandidatePreview();
    document.getElementById("modalBulkCandidate").classList.add("active");
  };

  window.closeBulkCandidateModal = function () {
    document.getElementById("modalBulkCandidate").classList.remove("active");
  };

  window.handleBulkCandidateFileSelected = function (e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (evt) {
      const content = evt.target.result;
      document.getElementById("bulkCandidateText").value = content;
      window.updateBulkCandidatePreview();
    };
    reader.readAsText(file, "UTF-8");
  };

  window.updateBulkCandidatePreview = function () {
    const textarea = document.getElementById("bulkCandidateText");
    const text = textarea ? textarea.value : "";
    const lines = text.split("\n").map(l => l.trim()).filter(l => l.length > 0);
    const badge = document.getElementById("bulkCandidatesCount");
    if (badge) {
      badge.textContent = `${lines.length} candidato${lines.length === 1 ? '' : 's'} identificado${lines.length === 1 ? '' : 's'}`;
    }
    const btn = document.getElementById("btnSubmitBulkCandidate");
    if (btn) {
      btn.disabled = lines.length === 0;
    }
  };

  window.handleBulkCandidateSubmit = async function (e) {
    e.preventDefault();
    const textarea = document.getElementById("bulkCandidateText");
    const text = textarea ? textarea.value : "";
    const names = text.split("\n").map(l => l.trim()).filter(l => l.length > 0);

    if (names.length === 0) {
      showToast("Nenhum candidato informado no arquivo ou texto.", "warning");
      return;
    }

    const res = await apiRequest("/api/admin/candidates/bulk-import", {
      method: "POST",
      body: { names }
    });

    if (res.success) {
      showToast(res.message || `${names.length} candidatos importados com sucesso!`, "success");
      closeBulkCandidateModal();
      loadAdminCandidates();
      loadAdminDashboard();
    } else {
      showToast(res.error || "Erro ao importar candidatos.", "error");
    }
  };

  window.deleteCandidate = async function (id, name) {
    if (!confirm(`Deseja realmente excluir o candidato "${name}"? Todas as notas associadas serão removidas.`)) return;

    const res = await apiRequest(`/api/admin/candidates/${id}`, { method: "DELETE" });
    if (res.success) {
      showToast(res.message || "Candidato excluído.", "success");
      loadAdminCandidates();
      loadAdminDashboard();
    } else {
      showToast(res.error || "Erro ao excluir candidato.", "error");
    }
  };

  // --- CRUD: Juízes ---
  async function loadAdminJudges() {
    const res = await apiRequest("/api/admin/judges");
    if (!res.success) return;

    state.admin.judges = res.judges || [];
    const tbody = document.getElementById("judgesTableBody");
    tbody.innerHTML = "";

    state.admin.judges.forEach(j => {
      const tr = document.createElement("tr");
      const judgeJson = JSON.stringify(j).replace(/'/g, "&#39;");
      tr.innerHTML = `
        <td><strong>${j.name}</strong></td>
        <td>${j.email}</td>
        <td><span class="badge ${j.active ? 'badge-emerald' : 'badge-slate'}">${j.active ? 'Ativo' : 'Inativo'}</span></td>
        <td>${new Date(j.created_at).toLocaleDateString("pt-BR")}</td>
        <td>
          <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
            <button class="btn btn-xs btn-outline" onclick='window.editJudge(${judgeJson})'>Editar</button>
            <button class="btn btn-xs btn-outline" onclick='window.openResetJudgePasswordModal(${judgeJson})' title="Definir nova senha para este juiz">🔑 Resetar Senha</button>
            <button class="btn btn-xs btn-danger" onclick="window.deleteJudge(${j.id}, '${j.name.replace(/'/g, "\\'")}')">Excluir</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  window.openResetJudgePasswordModal = function (judge) {
    document.getElementById("resetJudgeId").value = judge.id;
    document.getElementById("resetJudgeName").textContent = judge.name;
    document.getElementById("resetJudgeEmail").textContent = judge.email;
    document.getElementById("resetJudgeNewPassword").value = "";
    document.getElementById("modalResetJudgePassword").classList.add("active");
  };

  window.closeResetJudgePasswordModal = function () {
    document.getElementById("modalResetJudgePassword").classList.remove("active");
  };

  window.generateRandomJudgePassword = function () {
    const chars = "abcdefghjkmnpqrstuvwxyz23456789";
    let pwd = "juiz@";
    for (let i = 0; i < 4; i++) {
      pwd += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    document.getElementById("resetJudgeNewPassword").value = pwd;
  };

  window.handleResetJudgePasswordSubmit = async function (e) {
    e.preventDefault();
    const id = document.getElementById("resetJudgeId").value;
    const password = document.getElementById("resetJudgeNewPassword").value.trim();

    if (!password) {
      showToast("Por favor, digite a nova senha.", "error");
      return;
    }

    const res = await apiRequest(`/api/admin/judges/${id}/reset-password`, {
      method: "POST",
      body: { password }
    });

    if (res.success) {
      showToast(res.message || "Senha redefinida com sucesso!", "success");
      closeResetJudgePasswordModal();
    } else {
      showToast(res.error || "Erro ao redefinir senha.", "error");
    }
  };

  window.openJudgeModal = function () {
    document.getElementById("modalJudgeTitle").textContent = "Novo Juiz";
    document.getElementById("judgeFormId").value = "";
    document.getElementById("judgeFormName").value = "";
    document.getElementById("judgeFormEmail").value = "";
    document.getElementById("judgeFormPassword").value = "";
    document.getElementById("judgeFormPasswordLabel").textContent = "Senha de Acesso *";
    document.getElementById("judgeFormPasswordHint").style.display = "none";
    document.getElementById("modalJudge").classList.add("active");
  };

  window.editJudge = function (judge) {
    document.getElementById("modalJudgeTitle").textContent = "Editar Juiz";
    document.getElementById("judgeFormId").value = judge.id;
    document.getElementById("judgeFormName").value = judge.name;
    document.getElementById("judgeFormEmail").value = judge.email;
    document.getElementById("judgeFormPassword").value = "";
    document.getElementById("judgeFormPasswordLabel").textContent = "Nova Senha (Opcional)";
    document.getElementById("judgeFormPasswordHint").style.display = "block";
    document.getElementById("modalJudge").classList.add("active");
  };

  window.closeJudgeModal = function () {
    document.getElementById("modalJudge").classList.remove("active");
  };

  async function handleJudgeFormSubmit(e) {
    e.preventDefault();
    const id = document.getElementById("judgeFormId").value;
    const name = document.getElementById("judgeFormName").value.trim();
    const email = document.getElementById("judgeFormEmail").value.trim();
    const password = document.getElementById("judgeFormPassword").value;

    if (!id && !password) {
      showToast("A senha é obrigatória para cadastrar um novo juiz.", "error");
      return;
    }

    const url = id ? `/api/admin/judges/${id}` : "/api/admin/judges";
    const method = id ? "PUT" : "POST";

    const body = { name, email };
    if (password) body.password = password;

    const res = await apiRequest(url, { method, body });
    if (res.success) {
      showToast(res.message || "Juiz salvo com sucesso!", "success");
      closeJudgeModal();
      loadAdminJudges();
    } else {
      showToast(res.error || "Erro ao salvar juiz.", "error");
    }
  }

  window.deleteJudge = async function (id, name) {
    if (!confirm(`Deseja realmente excluir o juiz "${name}"?`)) return;

    const res = await apiRequest(`/api/admin/judges/${id}`, { method: "DELETE" });
    if (res.success) {
      showToast(res.message || "Juiz excluído.", "success");
      loadAdminJudges();
    } else {
      showToast(res.error || "Erro ao excluir juiz.", "error");
    }
  };

  // --- CRUD: Categorias ---
  async function loadAdminCategories() {
    const res = await apiRequest("/api/admin/categories");
    if (!res.success) return;

    state.admin.categories = res.categories || [];
    const tbody = document.getElementById("categoriesTableBody");
    tbody.innerHTML = "";

    state.admin.categories.forEach(cat => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>#${cat.display_order}</strong></td>
        <td><strong>${cat.name}</strong></td>
        <td>${cat.description || "-"}</td>
        <td><span class="badge ${cat.active ? 'badge-emerald' : 'badge-slate'}">${cat.active ? 'Ativa' : 'Inativa'}</span></td>
        <td>
          <div style="display:flex; gap:0.5rem;">
            <button class="btn btn-xs btn-outline" onclick='window.editCategory(${JSON.stringify(cat)})'>Editar</button>
            <button class="btn btn-xs btn-danger" onclick="window.deleteCategory(${cat.id}, '${cat.name.replace(/'/g, "\\'")}')">Excluir</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  window.openCategoryModal = function () {
    document.getElementById("modalCategoryTitle").textContent = "Nova Categoria de Avaliação";
    document.getElementById("categoryFormId").value = "";
    document.getElementById("categoryFormName").value = "";
    document.getElementById("categoryFormDesc").value = "";
    document.getElementById("categoryFormOrder").value = (state.admin.categories.length + 1);
    document.getElementById("modalCategory").classList.add("active");
  };

  window.editCategory = function (cat) {
    document.getElementById("modalCategoryTitle").textContent = "Editar Categoria";
    document.getElementById("categoryFormId").value = cat.id;
    document.getElementById("categoryFormName").value = cat.name;
    document.getElementById("categoryFormDesc").value = cat.description || "";
    document.getElementById("categoryFormOrder").value = cat.display_order || 1;
    document.getElementById("modalCategory").classList.add("active");
  };

  window.closeCategoryModal = function () {
    document.getElementById("modalCategory").classList.remove("active");
  };

  async function handleCategoryFormSubmit(e) {
    e.preventDefault();
    const id = document.getElementById("categoryFormId").value;
    const name = document.getElementById("categoryFormName").value.trim();
    const description = document.getElementById("categoryFormDesc").value.trim();
    const display_order = parseInt(document.getElementById("categoryFormOrder").value, 10) || 1;

    const url = id ? `/api/admin/categories/${id}` : "/api/admin/categories";
    const method = id ? "PUT" : "POST";

    const res = await apiRequest(url, {
      method,
      body: { name, description, display_order }
    });

    if (res.success) {
      showToast(res.message || "Categoria salva com sucesso!", "success");
      closeCategoryModal();
      loadAdminCategories();
    } else {
      showToast(res.error || "Erro ao salvar categoria.", "error");
    }
  }

  window.deleteCategory = async function (id, name) {
    if (!confirm(`Deseja excluir a categoria "${name}"? Se houver notas associadas, ela será desativada para preservar os resultados.`)) return;

    const res = await apiRequest(`/api/admin/categories/${id}`, { method: "DELETE" });
    if (res.success) {
      showToast(res.message || "Categoria processada.", "success");
      loadAdminCategories();
    } else {
      showToast(res.error || "Erro ao excluir categoria.", "error");
    }
  };

  // --- Governança, Configurações e Auditoria ---
  async function loadAdminSettings() {
    const res = await apiRequest("/api/admin/settings");
    if (!res.success) return;

    const settings = res.settings;
    state.admin.settings = settings;

    // Radios de status
    const statusVal = settings.voting_status || "OPEN";
    const radio = document.querySelector(`input[name="eventVotingStatus"][value="${statusVal}"]`);
    if (radio) radio.checked = true;

    // Toggles
    document.getElementById("settingAllowCorrections").checked = settings.allow_corrections === "true";
    document.getElementById("settingShowProvisionalWinner").checked = settings.show_provisional_winner === "true";
    document.getElementById("settingPublishResults").checked = settings.public_results_published === "true";
    document.getElementById("settingEventName").value = settings.event_name || "";

    loadAdminCampaigns();
    loadAdminAuditLogs();
  }

  // --- Gerenciamento de Campanhas ---
  async function loadAdminCampaigns() {
    const res = await apiRequest("/api/admin/campaigns");
    if (!res.success) return;

    const select = document.getElementById("campaignSelect");
    if (select) {
      select.innerHTML = "";
      (res.campaigns || []).forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = `${c.name} (${c.candidates_count || 0} candidatos)`;
        if (c.id === res.active_campaign_id) {
          opt.selected = true;
          state.activeCampaign = c;
        }
        select.appendChild(opt);
      });
    }

    const activeCamp = (res.campaigns || []).find(c => c.id === res.active_campaign_id);
    if (activeCamp) {
      state.activeCampaign = activeCamp;
      const dangerNameEl = document.getElementById("dangerCampaignName");
      if (dangerNameEl) dangerNameEl.textContent = activeCamp.name;

      const candCampNameEl = document.getElementById("candidatesCampaignName");
      if (candCampNameEl) candCampNameEl.textContent = activeCamp.name;
    }

    updateHeaderUI();
  }

  window.switchCampaign = async function (campaignId) {
    if (!campaignId) return;
    const res = await apiRequest(`/api/admin/campaigns/${campaignId}/activate`, { method: "POST" });
    if (res.success) {
      showToast(res.message, "success");
      await loadAdminCampaigns();
      await loadAdminCandidates();
      await loadAdminDashboard();
      if (state.admin.currentTab === "tabRankings") await loadAdminRankings();
      if (state.admin.currentTab === "tabMonitoring") await loadEvaluationMatrix();
    } else {
      showToast(res.error || "Erro ao alternar campanha.", "error");
    }
  };

  window.openNewCampaignModal = function () {
    document.getElementById("campaignFormName").value = "";
    document.getElementById("campaignFormDesc").value = "";
    document.getElementById("modalNewCampaign").classList.add("active");
  };

  window.closeNewCampaignModal = function () {
    document.getElementById("modalNewCampaign").classList.remove("active");
  };

  window.handleNewCampaignSubmit = async function (e) {
    e.preventDefault();
    const name = document.getElementById("campaignFormName").value.trim();
    const description = document.getElementById("campaignFormDesc").value.trim();

    if (!name) {
      showToast("Informe o nome da campanha.", "warning");
      return;
    }

    const res = await apiRequest("/api/admin/campaigns", {
      method: "POST",
      body: { name, description }
    });

    if (res.success) {
      showToast(res.message, "success");
      closeNewCampaignModal();
      await loadAdminCampaigns();
      await loadAdminCandidates();
      await loadAdminDashboard();
      await loadAdminSettings();
      if (state.admin.currentTab === "tabRankings") await loadAdminRankings();
      if (state.admin.currentTab === "tabMonitoring") await loadEvaluationMatrix();
    } else {
      showToast(res.error || "Erro ao criar campanha.", "error");
    }
  };

  window.clearCurrentCampaignCandidates = async function () {
    const activeCampName = state.activeCampaign ? state.activeCampaign.name : "atual";
    const confirmMsg = `ATENÇÃO: Deseja realmente excluir TODOS os candidatos e todas as notas da campanha "${activeCampName}"?\n\nEsta ação é irreversível e zerará a votação desta campanha!`;
    if (!confirm(confirmMsg)) return;

    const res = await apiRequest("/api/admin/candidates/clear-current-campaign", { method: "DELETE" });
    if (res.success) {
      showToast(res.message, "success");
      await loadAdminCandidates();
      await loadAdminDashboard();
      await loadAdminCampaigns();
      if (state.admin.currentTab === "tabRankings") await loadAdminRankings();
      if (state.admin.currentTab === "tabMonitoring") await loadEvaluationMatrix();
    } else {
      showToast(res.error || "Erro ao limpar candidatos da campanha.", "error");
    }
  };

  async function saveAdminSettings() {
    const selectedRadio = document.querySelector('input[name="eventVotingStatus"]:checked');
    const voting_status = selectedRadio ? selectedRadio.value : "OPEN";
    const allow_corrections = document.getElementById("settingAllowCorrections").checked ? "true" : "false";
    const show_provisional_winner = document.getElementById("settingShowProvisionalWinner").checked ? "true" : "false";
    const public_results_published = document.getElementById("settingPublishResults").checked ? "true" : "false";
    const event_name = document.getElementById("settingEventName").value.trim() || "Festival de Talentos";

    const res = await apiRequest("/api/admin/settings", {
      method: "PUT",
      body: {
        voting_status,
        allow_corrections,
        show_provisional_winner,
        public_results_published,
        event_name
      }
    });

    if (res.success) {
      showToast("Configurações salvas com sucesso!", "success");
      state.eventInfo = { ...state.eventInfo, ...res.settings };
      updateHeaderUI();
      loadAdminSettings();
    } else {
      showToast(res.error || "Erro ao salvar configurações.", "error");
    }
  }

  async function loadAdminAuditLogs() {
    const res = await apiRequest("/api/admin/audit-logs");
    if (!res.success) return;

    const tbody = document.getElementById("auditLogsTableBody");
    tbody.innerHTML = "";

    (res.logs || []).forEach(log => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-family: var(--font-mono); font-size: 0.8rem;">${new Date(log.created_at).toLocaleString("pt-BR")}</td>
        <td><strong>${log.user_name || "Sistema"}</strong></td>
        <td><span class="badge badge-outline">${log.action}</span></td>
        <td style="font-size: 0.85rem;">${log.details || "-"}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // =========================================================================
  // Inicialização e Event Listeners
  // =========================================================================

  function init() {
    // Formulário de Login
    const formLogin = document.getElementById("formLogin");
    if (formLogin) formLogin.addEventListener("submit", handleLoginSubmit);

    // Botão de Logout
    const btnLogout = document.getElementById("btnLogout");
    if (btnLogout) btnLogout.addEventListener("click", logout);

    // Navegação e Filtros do Juiz
    const btnBack = document.getElementById("btnBackToJudgeList");
    if (btnBack) btnBack.addEventListener("click", () => switchView("viewJudge"));

    const btnConfirm = document.getElementById("btnConfirmEvaluation");
    if (btnConfirm) btnConfirm.addEventListener("click", submitJudgeEvaluation);

    // Filtros de Candidatos no Juiz
    document.querySelectorAll(".pill").forEach(pill => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        state.judge.filter = pill.getAttribute("data-filter");
        renderJudgeCandidatesGrid();
      });
    });

    const searchInput = document.getElementById("judgeSearchCandidate");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        state.judge.searchQuery = e.target.value;
        renderJudgeCandidatesGrid();
      });
    }

    // Formulários Modais do Admin
    const formCand = document.getElementById("formCandidate");
    if (formCand) formCand.addEventListener("submit", handleCandidateFormSubmit);

    const formJudge = document.getElementById("formJudge");
    if (formJudge) formJudge.addEventListener("submit", handleJudgeFormSubmit);

    const formCat = document.getElementById("formCategory");
    if (formCat) formCat.addEventListener("submit", handleCategoryFormSubmit);

    // Salvar Configurações
    const btnSettings = document.getElementById("btnSaveSettings");
    if (btnSettings) btnSettings.addEventListener("click", saveAdminSettings);

    // Exportar funções necessárias no escopo global
    window.switchView = switchView;
    window.loadAdminDashboard = loadAdminDashboard;
    window.loadAdminRankings = loadAdminRankings;

    // Verificar sessão existente
    checkAuthSession();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
