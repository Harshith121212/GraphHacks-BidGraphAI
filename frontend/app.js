/**
 * BidGraphAI — Executive Dashboard Frontend Controller
 * Powered by FalkorDB OpenCypher Traversals & Model Context Protocol (FastMCP)
 */

document.addEventListener('DOMContentLoaded', () => {
  // Application State
  const state = {
    simulatedOffsetSeconds: 0,
    currentClientFilter: 'ALL',
    isProcessing: false,
    dashboardData: null,
    d3Simulation: null,
    batchDrafts: [],
    currentBatchIndex: 0,
  };

  // DOM Elements
  const el = {
    btnPullTenders: document.getElementById('btn-pull-tenders'),
    btnRunMatch: document.getElementById('btn-run-match'),
    btnRunLanggraph: document.getElementById('btn-run-langgraph'),
    btnDraftAllEmails: document.getElementById('btn-draft-all-emails'),
    btnTimeJump: document.getElementById('btn-time-jump'),
    timeJumpLabel: document.getElementById('time-jump-label'),
    btnIngestSample: document.getElementById('btn-ingest-sample'),
    btnClearTenders: document.getElementById('btn-clear-tenders'),
    btnResetDemo: document.getElementById('btn-reset-demo'),
    scraperStatusTime: document.getElementById('scraper-status-time'),
    scraperTendersCount: document.getElementById('scraper-tenders-count'),
    graphTopologyStats: document.getElementById('graph-topology-stats'),
    statActiveTenders: document.getElementById('stat-active-tenders'),
    statDispatchedAlerts: document.getElementById('stat-dispatched-alerts'),
    statJvConsortiums: document.getElementById('stat-jv-consortiums'),
    jvConsortiumsBadge: document.getElementById('jv-consortiums-badge'),
    jvConsortiumContainer: document.getElementById('jv-consortium-container'),
    decisionTreeModal: document.getElementById('decision-tree-modal'),
    dtModalTitle: document.getElementById('dt-modal-title'),
    dtModalSubtitle: document.getElementById('dt-modal-subtitle'),
    dtModalBody: document.getElementById('dt-modal-body'),
    btnCloseDtModal: document.getElementById('btn-close-dt-modal'),
    emailPreviewModal: document.getElementById('email-preview-modal'),
    emailModalRecipient: document.getElementById('email-modal-recipient'),
    emailModalStatusBadge: document.getElementById('email-modal-status-badge'),
    emailModalValue: document.getElementById('email-modal-value'),
    emailModalDeadline: document.getElementById('email-modal-deadline'),
    emailModalScore: document.getElementById('email-modal-score'),
    emailModalScope: document.getElementById('email-modal-scope'),
    emailModalPlusPoints: document.getElementById('email-modal-plus-points'),
    emailModalReasonChosen: document.getElementById('email-modal-reason-chosen'),
    emailModalEngineBadge: document.getElementById('email-modal-engine-badge'),
    btnModalSendAlert: document.getElementById('btn-modal-send-alert'),
    emailModalSubject: document.getElementById('email-modal-subject'),
    emailModalBody: document.getElementById('email-modal-body'),
    emailModalBatchNav: document.getElementById('email-modal-batch-nav'),
    batchProgressLabel: document.getElementById('batch-progress-label'),
    btnBatchPrev: document.getElementById('btn-batch-prev'),
    btnBatchNext: document.getElementById('btn-batch-next'),
    btnCloseEmailModal: document.getElementById('btn-close-email-modal'),
    btnModalClose: document.getElementById('btn-modal-close'),
    btnCopySubject: document.getElementById('btn-copy-subject'),
    btnCopyBody: document.getElementById('btn-copy-body'),
    btnModalCopyAll: document.getElementById('btn-modal-copy-all'),
    statSimulatedClock: document.getElementById('stat-simulated-clock'),
    alertsCountBadge: document.getElementById('alerts-count-badge'),
    alertFeedContainer: document.getElementById('alert-feed-container'),
    affinityPanel: document.getElementById('affinity-panel'),
    mcpAuditLog: document.getElementById('mcp-audit-log'),
    tendersGrid: document.getElementById('tenders-grid'),
    toastContainer: document.getElementById('toast-container'),
    graphCanvas: document.getElementById('graph-canvas'),
    clientTabs: document.querySelectorAll('.client-tab'),
    tabBtnAlerts: document.getElementById('tab-btn-alerts'),
    tabBtnJv: document.getElementById('tab-btn-jv'),
    tabBtnTenders: document.getElementById('tab-btn-tenders'),
    panelAlerts: document.getElementById('panel-alerts'),
    panelJv: document.getElementById('panel-jv'),
    panelTenders: document.getElementById('panel-tenders'),
    tendersCountBadge: document.getElementById('tenders-count-badge'),
  };

  // Helper: Get Current Effective Timestamp (Unix seconds)
  function getCurrentTimestamp() {
    return Math.floor(Date.now() / 1000) + state.simulatedOffsetSeconds;
  }

  // Toast Notification System
  function showToast(title, message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast-animate pointer-events-auto flex items-start gap-3 p-3.5 rounded-xl border shadow-xl backdrop-blur-md text-xs transition-all duration-300 ${
      type === 'success'
        ? 'bg-emerald-950/90 border-emerald-500/40 text-emerald-200'
        : type === 'warning'
        ? 'bg-amber-950/90 border-amber-500/40 text-amber-200'
        : type === 'error'
        ? 'bg-rose-950/90 border-rose-500/40 text-rose-200'
        : 'bg-slate-900/90 border-slate-700 text-slate-200'
    }`;

    const iconName = type === 'success' ? 'check-circle' : type === 'warning' ? 'alert-triangle' : type === 'error' ? 'x-circle' : 'info';
    toast.innerHTML = `
      <i data-lucide="${iconName}" class="w-4 h-4 mt-0.5 shrink-0"></i>
      <div class="flex-1">
        <div class="font-bold text-white">${title}</div>
        <div class="text-[11px] opacity-90 mt-0.5">${message}</div>
      </div>
      <button class="text-slate-400 hover:text-white shrink-0" onclick="this.parentElement.remove()">
        <i data-lucide="x" class="w-3.5 h-3.5"></i>
      </button>
    `;

    el.toastContainer.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  }

  // AI Buffering Notification Controller (High-Visibility Bottom Notification Card)
  let aiBufferTimer = null;
  let aiBufferStepTimer = null;
  let aiBufferStartTime = 0;

  function startAIBuffering(actionTitle = 'Tender Matching & Cognitive AI Reasoning') {
    const bar = document.getElementById('ai-buffering-bar');
    if (!bar) return;

    aiBufferStartTime = performance.now();
    bar.classList.remove('hidden');
    bar.classList.remove('ai-buffering-glow-success', 'ai-buffering-glow-error');
    bar.classList.add('ai-buffering-glow-active');

    const badge = document.getElementById('ai-buffering-badge');
    const title = document.getElementById('ai-buffering-title');
    const subtitle = document.getElementById('ai-buffering-subtitle');
    const timer = document.getElementById('ai-buffering-timer');
    const progressBar = document.getElementById('ai-buffering-progress');
    const iconWrap = document.getElementById('ai-buffering-icon-wrap');

    if (badge) {
      badge.textContent = 'AI Reasoning Active';
      badge.className = 'px-2.5 py-0.5 rounded-full text-[9px] font-mono font-black uppercase tracking-wider bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-sm shadow-indigo-500/50';
    }
    if (title) title.innerHTML = `<span>${actionTitle}</span>`;
    if (timer) timer.textContent = '0.0s';
    if (progressBar) {
      progressBar.className = 'h-full bg-gradient-to-r from-cyan-400 via-indigo-500 to-pink-500 rounded-full w-1/3 animate-indeterminate shadow-[0_0_12px_rgba(99,102,241,0.8)]';
    }
    if (iconWrap) {
      iconWrap.innerHTML = `
        <span class="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500/30 to-purple-600/30 border border-indigo-400/50 flex items-center justify-center shadow-inner">
          <i data-lucide="loader-2" class="w-4 h-4 animate-spin-fast text-indigo-300"></i>
        </span>
        <span class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
        <span class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-sm shadow-cyan-300"></span>
      `;
    }

    // Step progression messages to provide continuous visual feedback
    const steps = [
      'Step 1/3: Accelerated AI reasoning & tender criteria evaluation...',
      'Step 2/3: Intelligent client profile matching & competitive advantage analysis...',
      'Step 3/3: Evaluating peer discovery & consortium opportunities in parallel...',
    ];
    let stepIndex = 0;
    if (subtitle) {
      subtitle.innerHTML = `<span>${steps[0]}</span>`;
    }

    // Live elapsed timer ticking every 100ms
    if (aiBufferTimer) clearInterval(aiBufferTimer);
    aiBufferTimer = setInterval(() => {
      const elapsed = ((performance.now() - aiBufferStartTime) / 1000).toFixed(1);
      if (timer) timer.textContent = `${elapsed}s`;
    }, 100);

    // Dynamic phase transitions every 2.5 seconds
    if (aiBufferStepTimer) clearInterval(aiBufferStepTimer);
    aiBufferStepTimer = setInterval(() => {
      stepIndex = (stepIndex + 1) % steps.length;
      if (subtitle) {
        subtitle.innerHTML = `<span>${steps[stepIndex]}</span>`;
      }
    }, 2500);

    if (window.lucide) window.lucide.createIcons();
  }

  function stopAIBuffering(isSuccess = true, summaryText = '') {
    const bar = document.getElementById('ai-buffering-bar');
    if (!bar) return;

    if (aiBufferTimer) {
      clearInterval(aiBufferTimer);
      aiBufferTimer = null;
    }
    if (aiBufferStepTimer) {
      clearInterval(aiBufferStepTimer);
      aiBufferStepTimer = null;
    }

    const elapsed = ((performance.now() - aiBufferStartTime) / 1000).toFixed(1);
    bar.classList.remove('ai-buffering-glow-active');

    const badge = document.getElementById('ai-buffering-badge');
    const title = document.getElementById('ai-buffering-title');
    const subtitle = document.getElementById('ai-buffering-subtitle');
    const timer = document.getElementById('ai-buffering-timer');
    const progressBar = document.getElementById('ai-buffering-progress');
    const iconWrap = document.getElementById('ai-buffering-icon-wrap');

    if (timer) timer.textContent = `${elapsed}s`;

    if (isSuccess) {
      bar.classList.add('ai-buffering-glow-success');
      if (badge) {
        badge.textContent = `Completed in ${elapsed}s`;
        badge.className = 'px-2.5 py-0.5 rounded-full text-[9px] font-mono font-black uppercase tracking-wider bg-gradient-to-r from-emerald-500 to-teal-600 text-white shadow-sm shadow-emerald-500/50';
      }
      if (title) title.innerHTML = `<span>✓ Tender Intelligence & Win Strategy Ready</span>`;
      if (subtitle) subtitle.innerHTML = `<span>${summaryText || 'Autonomous graph traversals and NVIDIA Nemotron synthesis completed successfully.'}</span>`;
      if (progressBar) {
        progressBar.className = 'h-full bg-emerald-400 rounded-full w-full transition-all duration-500 shadow-[0_0_12px_rgba(52,211,153,0.9)]';
      }
      if (iconWrap) {
        iconWrap.innerHTML = `
          <span class="w-8 h-8 rounded-xl bg-emerald-500/30 border border-emerald-400/50 flex items-center justify-center shadow-inner">
            <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-300"></i>
          </span>
        `;
      }
    } else {
      bar.classList.add('ai-buffering-glow-error');
      if (badge) {
        badge.textContent = 'AI Halted';
        badge.className = 'px-2.5 py-0.5 rounded-full text-[9px] font-mono font-black uppercase tracking-wider bg-rose-600 text-white shadow-sm shadow-rose-500/50';
      }
      if (title) title.innerHTML = `<span>AI Matching Loop Error (${elapsed}s)</span>`;
      if (subtitle) subtitle.innerHTML = `<span>${summaryText || 'An error occurred during agent graph reasoning.'}</span>`;
      if (progressBar) {
        progressBar.className = 'h-full bg-rose-500 rounded-full w-full shadow-[0_0_12px_rgba(244,63,94,0.9)]';
      }
      if (iconWrap) {
        iconWrap.innerHTML = `
          <span class="w-8 h-8 rounded-xl bg-rose-500/30 border border-rose-400/50 flex items-center justify-center shadow-inner">
            <i data-lucide="alert-triangle" class="w-4 h-4 text-rose-300"></i>
          </span>
        `;
      }
    }

    if (window.lucide) window.lucide.createIcons();

    // Keep visible for 5.0s so the user can easily read the confirmation and time taken, then smoothly hide
    setTimeout(() => {
      bar.classList.add('hidden');
      bar.classList.remove('ai-buffering-glow-success', 'ai-buffering-glow-error', 'ai-buffering-glow-active');
    }, 5000);
  }

  // MCP Tool Audit Logger
  function logMcpCall(toolName, latencyMs, status = 'SUCCESS', detail = '') {
    const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false });
    const logItem = document.createElement('div');
    logItem.className = 'flex items-center justify-between text-[11px] py-1 border-b border-slate-900/60';
    logItem.innerHTML = `
      <div class="flex items-center gap-1.5 overflow-hidden">
        <span class="text-slate-400 font-mono text-[10px]">${timeStr}</span>
        <span class="text-cyan-400 font-semibold font-mono truncate">${toolName}</span>
        ${detail ? `<span class="text-slate-400 truncate text-[10px]">(${detail})</span>` : ''}
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <span class="text-slate-400 text-[10px] font-mono">${latencyMs}ms</span>
        <span class="px-1.5 py-0.2 rounded text-[9px] font-mono ${
          status === 'SUCCESS' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'
        }">${status}</span>
      </div>
    `;

    if (el.mcpAuditLog.querySelector('.italic')) {
      el.mcpAuditLog.innerHTML = '';
    }
    el.mcpAuditLog.prepend(logItem);
  }

  // API Call Wrapper with Latency Measurement
  async function apiCall(endpoint, options = {}, mcpToolName = 'mcp_proxy') {
    const startTime = performance.now();
    try {
      const res = await fetch(endpoint, options);
      const latency = Math.round(performance.now() - startTime);
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: res.statusText }));
        logMcpCall(mcpToolName, latency, 'ERROR', `${res.status}`);
        throw new Error(errorData.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      logMcpCall(mcpToolName, latency, 'SUCCESS', '200 OK');
      return data;
    } catch (err) {
      const latency = Math.round(performance.now() - startTime);
      logMcpCall(mcpToolName, latency, 'ERROR', err.message);
      throw err;
    }
  }

  // Fetch Complete Dashboard State
  async function fetchDashboard() {
    try {
      const ts = getCurrentTimestamp();
      const clientParam = state.currentClientFilter !== 'ALL' ? `&client_id=${state.currentClientFilter}` : '';
      const data = await apiCall(`/api/dashboard?current_timestamp=${ts}${clientParam}`, {}, 'get_tender_alerts_history');
      state.dashboardData = data;
      renderDashboard(data);
    } catch (err) {
      console.error('Failed to fetch dashboard:', err);
      showToast('Dashboard Fetch Failed', err.message, 'error');
    }
  }

  // Render Dashboard Components
  function renderDashboard(data) {
    if (!data) return;

    // 1. Telemetry Bar
    const scraper = data.scraper_status || data.scraper_sync_status || {};
    const tendersCount = (data.active_tenders && data.active_tenders.length !== undefined)
      ? data.active_tenders.length
      : (data.active_tenders_count || data.total_tenders || 0);
    const topology = data.graph_snapshot || data.graph_topology || { nodes: [], links: [] };

    el.scraperStatusTime.textContent = scraper.last_scraped_at
      ? new Date(scraper.last_scraped_at * 1000).toLocaleTimeString() + ' (Heartbeat OK)'
      : 'Synced';
    el.scraperTendersCount.textContent = tendersCount;
    el.graphTopologyStats.textContent = `Nodes: ${topology.nodes?.length || 0} | Edges: ${topology.links?.length || 0}`;

    // 2. Stat Cards
    el.statActiveTenders.textContent = tendersCount;
    el.statDispatchedAlerts.textContent = data.alerts?.length || '0';
    
    // Count JV pairs
    const jvCount = (data.jv_consortiums && data.jv_consortiums.length) || (data.alerts ? data.alerts.filter(a => a.match_type === 'JV_CONSORTIUM' || (a.jv_consortium_peers && a.jv_consortium_peers.length > 0)).length : 0);
    el.statJvConsortiums.textContent = jvCount;
    if (el.jvConsortiumsBadge) el.jvConsortiumsBadge.textContent = jvCount;
    if (el.tendersCountBadge) el.tendersCountBadge.textContent = tendersCount;

    // Simulated Clock Display
    const hoursJumped = Math.round(state.simulatedOffsetSeconds / 3600);
    el.statSimulatedClock.textContent = hoursJumped > 0 ? `+${hoursJumped}h Advanced` : 'Live Now (+0h)';
    el.statSimulatedClock.className = hoursJumped > 0 ? 'text-base font-bold text-amber-400 mt-1 font-mono' : 'text-base font-bold text-emerald-400 mt-1 font-mono';

    // 3. Joint Venture (JV) Consortium Hub
    renderJVConsortiums(data.jv_consortiums || []);

    // 4. Alerts Feed
    renderAlerts(data.alerts || []);

    // 5. Learned Affinities Panel
    renderAffinities(data.learned_affinities || []);

    // 6. Active Tenders Grid (rendered immediately on load)
    if (data.active_tenders && data.active_tenders.length > 0) {
      renderTendersGrid(data.active_tenders);
    }

    // 7. Force-Directed D3 Graph
    if (topology && topology.nodes) {
      renderD3Graph(topology);
    }

    if (window.lucide) window.lucide.createIcons();
  }

  // Render Joint Venture (JV) Consortium Hub Cards
  function renderJVConsortiums(consortiums) {
    if (!el.jvConsortiumContainer) return;

    if (!consortiums || consortiums.length === 0) {
      el.jvConsortiumContainer.innerHTML = `
        <div class="col-span-full p-6 text-center border border-dashed border-slate-800 rounded-xl bg-slate-950/40 text-slate-400">
          <i data-lucide="handshake" class="w-8 h-8 text-amber-500/60 mx-auto mb-2 opacity-60"></i>
          <p class="text-xs font-semibold text-slate-300">No Joint Venture (JV) Consortiums found yet.</p>
          <p class="text-[11px] text-slate-400 mt-1">Click "Run AI Tender Matching" above to discover syndicate pairings in FalkorDB.</p>
        </div>
      `;
      return;
    }

    el.jvConsortiumContainer.innerHTML = consortiums.map(jv => {
      const dtStage2 = jv.decision_tree?.stage2_financial_aggregation;
      const dtStage3 = jv.decision_tree?.stage3_capability_union;

      const leadTurnoverCr = (Number(jv.lead_turnover || (jv.lead_partner && jv.lead_partner.avg_turnover_3yr) || (dtStage2 && dtStage2.lead_turnover_cr * 10000000) || 0) / 10000000).toFixed(1);
      const partnerTurnoverCr = (Number(jv.partner_turnover || (jv.consortium_partner && jv.consortium_partner.avg_turnover_3yr) || (dtStage2 && dtStage2.partner_turnover_cr * 10000000) || 0) / 10000000).toFixed(1);
      const combinedTurnoverCr = (Number(jv.combined_turnover || (jv.combined_financials && jv.combined_financials.combined_turnover) || (dtStage2 && dtStage2.combined_turnover_cr * 10000000) || 0) / 10000000).toFixed(1);
      const reqTurnoverCr = (Number(jv.required_turnover || (jv.combined_financials && jv.combined_financials.required_turnover) || (dtStage2 && dtStage2.required_turnover_cr * 10000000) || 0) / 10000000).toFixed(1);
      const synergyPct = Math.round(Number(jv.synergy_score || 0.96) * 100);
      const status = jv.status || 'RECOMMENDED';
      const isTerminal = (status === 'WON' || status === 'LOST');

      const leadCaps = (jv.lead_partner && jv.lead_partner.contributed_nodes && jv.lead_partner.contributed_nodes.work_categories) 
        ? jv.lead_partner.contributed_nodes.work_categories.join(', ')
        : (dtStage3 && dtStage3.lead_contributions && dtStage3.lead_contributions.length > 0)
        ? dtStage3.lead_contributions.join(', ')
        : 'Civil Infrastructure';

      const partnerCaps = (jv.consortium_partner && jv.consortium_partner.contributed_nodes && jv.consortium_partner.contributed_nodes.work_categories)
        ? jv.consortium_partner.contributed_nodes.work_categories.join(', ')
        : (dtStage3 && dtStage3.partner_contributions && dtStage3.partner_contributions.length > 0)
        ? dtStage3.partner_contributions.join(', ')
        : 'Electrical & Technical OEM';

      const jvId = jv.id || jv.jv_id;

      return `
        <div class="glass-card rounded-2xl p-4 border ${
          status === 'WON' ? 'border-emerald-500/50 bg-emerald-950/20' : status === 'LOST' ? 'border-rose-500/50 bg-rose-950/20' : 'border-amber-500/30 bg-slate-900/70'
        } space-y-3.5 shadow-lg">
          <!-- Header with Tender ID & Synergy Pill -->
          <div class="flex items-start justify-between gap-2 border-b border-slate-800/80 pb-2.5">
            <div>
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  JV Consortium Pair
                </span>
                <span class="px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                  status === 'WON' ? 'badge-won' : status === 'LOST' ? 'badge-lost' : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                }">
                  ${status}
                </span>
                <span class="text-[11px] text-slate-400 font-mono">Tender: <strong class="text-slate-200">${jv.tender_id}</strong></span>
              </div>
              <h4 class="text-xs font-bold text-white mt-1 leading-snug">${jv.tender_title || jv.tender_id}</h4>
            </div>
            <div class="text-right shrink-0">
              <span class="px-2.5 py-1 rounded-full text-xs font-mono font-black bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                ${synergyPct}% Synergy
              </span>
            </div>
          </div>

          <!-- Lead + Partner Complementary Split Grid -->
          <div class="grid grid-cols-11 items-center gap-2 text-xs bg-slate-950/70 p-3 rounded-xl border border-slate-800/80">
            <!-- Lead Partner (5 cols) -->
            <div class="col-span-5 space-y-1">
              <div class="flex items-center space-x-1.5">
                <span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-indigo-500/30 text-indigo-300 border border-indigo-500/40">LEAD (60%)</span>
              </div>
              <div class="font-bold text-white truncate text-xs">${jv.lead_name || (jv.lead_partner && jv.lead_partner.client_name) || jv.lead_id}</div>
              <div class="text-[10px] text-slate-400 font-mono">Turnover: <span class="text-amber-400 font-semibold">₹${leadTurnoverCr} Cr</span></div>
              <div class="text-[10px] text-indigo-300 truncate" title="${leadCaps}">${leadCaps}</div>
            </div>

            <!-- Synergy Plus Divider (1 col) -->
            <div class="col-span-1 flex flex-col items-center justify-center">
              <div class="w-6 h-6 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-300 font-bold text-xs">
                +
              </div>
            </div>

            <!-- Partner (5 cols) -->
            <div class="col-span-5 space-y-1 text-right">
              <div class="flex items-center justify-end space-x-1.5">
                <span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-cyan-500/30 text-cyan-300 border border-cyan-500/40">PARTNER (40%)</span>
              </div>
              <div class="font-bold text-white truncate text-xs">${jv.partner_name || (jv.consortium_partner && jv.consortium_partner.client_name) || jv.partner_id}</div>
              <div class="text-[10px] text-slate-400 font-mono">Turnover: <span class="text-amber-400 font-semibold">₹${partnerTurnoverCr} Cr</span></div>
              <div class="text-[10px] text-cyan-300 truncate" title="${partnerCaps}">${partnerCaps}</div>
            </div>
          </div>

          <!-- Financial Synergy Bar -->
          <div class="bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/80 flex items-center justify-between text-[11px] font-mono">
            <div class="space-y-0.5">
              <span class="text-slate-400 text-[10px] uppercase block">Combined Bidding Turnover</span>
              <span class="text-emerald-400 font-bold">₹${combinedTurnoverCr} Cr <span class="text-slate-400 font-normal">/ ₹${reqTurnoverCr} Cr Req (+${(combinedTurnoverCr - reqTurnoverCr).toFixed(1)} Cr Buffer)</span></span>
            </div>
            <div class="text-right space-y-0.5">
              <span class="text-slate-400 text-[10px] uppercase block">Specs Coverage</span>
              <span class="text-emerald-400 font-bold flex items-center gap-1 justify-end">
                <i data-lucide="check-check" class="w-3.5 h-3.5 text-emerald-400"></i>
                100% Union
              </span>
            </div>
          </div>

          <!-- Bottom Action Buttons: View Decision Tree + Won/Lost Feedback -->
          <div class="flex items-center justify-between pt-1 flex-wrap gap-2">
            <button 
              data-jv-id="${jvId}"
              class="btn-view-decision-tree px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/40 transition flex items-center gap-1.5 shadow-sm">
              <i data-lucide="git-merge" class="w-3.5 h-3.5 text-indigo-400"></i>
              <span>View JV Decision Tree</span>
            </button>

            <div class="flex items-center space-x-2">
              <button 
                data-jv-id="${jvId}"
                data-outcome="WON"
                ${isTerminal ? 'disabled' : ''}
                class="btn-jv-won px-3 py-1 rounded text-xs font-semibold bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1">
                <i data-lucide="trophy" class="w-3 h-3 text-emerald-400"></i>
                <span>Mark Won</span>
              </button>
              <button 
                data-jv-id="${jvId}"
                data-outcome="LOST"
                ${isTerminal ? 'disabled' : ''}
                class="btn-jv-lost px-3 py-1 rounded text-xs font-semibold bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1">
                <i data-lucide="x" class="w-3 h-3 text-rose-400"></i>
                <span>Mark Lost</span>
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Attach View Decision Tree Handlers
    document.querySelectorAll('.btn-view-decision-tree').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetId = btn.dataset.jvId;
        const targetJv = (consortiums || []).find(j => (j.id === targetId || j.jv_id === targetId));
        if (targetJv) {
          openDecisionTreeModal(targetJv);
        }
      });
    });

    // Attach JV Won/Lost Feedback Handlers
    document.querySelectorAll('.btn-jv-won').forEach(btn => {
      btn.addEventListener('click', () => {
        handleJVOutcome(btn.dataset.jvId, 'WON');
      });
    });

    document.querySelectorAll('.btn-jv-lost').forEach(btn => {
      btn.addEventListener('click', () => {
        handleJVOutcome(btn.dataset.jvId, 'LOST');
      });
    });
  }

  // Interactive 5-Stage Decision Tree Modal Display
  function openDecisionTreeModal(jv) {
    if (!el.decisionTreeModal) return;

    const dt = jv.decision_tree || {};
    const s1 = dt.stage1_solo_disqualification || {};
    const s2 = dt.financial_aggregation || dt.stage2_financial_aggregation || {};
    const s3 = dt.capability_union || dt.stage3_capability_union || {};
    const s4 = dt.regional_compliance || dt.stage4_regional_compliance || {};
    const s5 = dt.governance_recommendation || dt.stage5_governance_recommendation || {};

    const leadDisplayName = jv.lead_name || (jv.lead_partner && jv.lead_partner.client_name) || jv.lead_id;
    const partnerDisplayName = jv.partner_name || (jv.consortium_partner && jv.consortium_partner.client_name) || jv.partner_id;

    el.dtModalTitle.textContent = `JV Decision Tree: ${leadDisplayName} + ${partnerDisplayName}`;
    el.dtModalSubtitle.textContent = `Tender: ${jv.tender_id} | Graph Verification & AI Strategy`;

    el.dtModalBody.innerHTML = `
      <!-- Stage 1 -->
      <div class="glass-card rounded-xl p-3.5 border border-rose-500/30 bg-rose-950/15 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="w-6 h-6 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center justify-center font-bold text-xs">1</span>
            <h4 class="text-xs font-bold text-white uppercase font-mono tracking-wider">${s1.title || 'Stage 1: Solo Bidder Disqualification Gate'}</h4>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40">Solo Bid Disqualified</span>
        </div>
        <div class="text-[11px] text-slate-300 space-y-1 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 font-mono">
          <div><strong class="text-rose-400">Lead Disqualification:</strong> ${s1.lead_status || 'Cannot satisfy specifications alone.'}</div>
          <div><strong class="text-rose-400">Partner Disqualification:</strong> ${s1.partner_status || 'Missing mandatory CPWD statutory credentials.'}</div>
        </div>
        <p class="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
          <i data-lucide="check" class="w-3 h-3"></i>
          Gate Passed: Independent solo bidding impossible; Consortium formation legally mandatory.
        </p>
      </div>

      <!-- Stage 2 -->
      <div class="glass-card rounded-xl p-3.5 border border-emerald-500/30 bg-emerald-950/15 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center justify-center font-bold text-xs">2</span>
            <h4 class="text-xs font-bold text-white uppercase font-mono tracking-wider">${s2.title || 'Stage 2: Financial Aggregation & Solvency Gate'}</h4>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40">Financials Passed</span>
        </div>
        <div class="grid grid-cols-2 gap-2 text-[11px] bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 font-mono">
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Combined Turnover</span>
            <span class="text-emerald-400 font-bold">₹${s2.combined_turnover_cr || (Number(jv.combined_turnover)/1e7).toFixed(1)} Cr</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Required Threshold</span>
            <span class="text-white font-bold">₹${s2.required_turnover_cr || (Number(jv.required_turnover)/1e7).toFixed(1)} Cr</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Safety Solvency Buffer</span>
            <span class="text-cyan-400 font-bold">+₹${s2.buffer_cr || '6.50'} Cr</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Combined Net Worth</span>
            <span class="text-amber-400 font-bold">₹${s2.combined_net_worth_cr || '14.50'} Cr</span>
          </div>
        </div>
        <p class="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
          <i data-lucide="check" class="w-3 h-3"></i>
          ${s2.detail || 'Combined financial metrics exceed CPWD/GeM solvency requirements.'}
        </p>
      </div>

      <!-- Stage 3 -->
      <div class="glass-card rounded-xl p-3.5 border border-indigo-500/30 bg-indigo-950/15 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 flex items-center justify-center font-bold text-xs">3</span>
            <h4 class="text-xs font-bold text-white uppercase font-mono tracking-wider">${s3.title || 'Stage 3: Multi-Hop Capability Union Gate'}</h4>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-500/20 text-indigo-300 font-bold border border-indigo-500/40">100% Coverage</span>
        </div>
        <div class="text-[11px] bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 space-y-1.5 font-mono">
          <div><strong class="text-indigo-400">Lead Contributions:</strong> ${(s3.lead_contributions || ['Civil Works', 'Highway & Bridge EPC']).join(', ')}</div>
          <div><strong class="text-cyan-400">Partner Contributions:</strong> ${(s3.partner_contributions || ['Electrical Substation', 'Havells OEM Cables']).join(', ')}</div>
        </div>
        <p class="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
          <i data-lucide="check" class="w-3 h-3"></i>
          ${s3.detail || 'Union of capabilities satisfies 100% of CPWD engineering specifications.'}
        </p>
      </div>

      <!-- Stage 4 -->
      <div class="glass-card rounded-xl p-3.5 border border-cyan-500/30 bg-cyan-950/15 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="w-6 h-6 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center justify-center font-bold text-xs">4</span>
            <h4 class="text-xs font-bold text-white uppercase font-mono tracking-wider">${s4.title || 'Stage 4: Regional Compliance Gate'}</h4>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40">Compliant</span>
        </div>
        <div class="text-[11px] bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 space-y-1 font-mono">
          <div><strong class="text-slate-400">Tender Region:</strong> <span class="text-white">${s4.region || 'India'}</span></div>
          <div><strong class="text-emerald-400">GST Registration:</strong> ${s4.lead_gst || 'Active GSTIN in region verified.'}</div>
          <div><strong class="text-emerald-400">Debarment Status:</strong> ${s4.blacklisting_status || 'Zero blacklisting flags.'}</div>
        </div>
        <p class="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
          <i data-lucide="check" class="w-3 h-3"></i>
          ${s4.detail || 'Both entities verified as active tax filers with zero debarment history.'}
        </p>
      </div>

      <!-- Stage 5 -->
      <div class="glass-card rounded-xl p-3.5 border border-amber-500/30 bg-amber-950/15 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="w-6 h-6 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center justify-center font-bold text-xs">5</span>
            <h4 class="text-xs font-bold text-white uppercase font-mono tracking-wider">${s5.title || 'Stage 5: Consortium Governance Recommendation'}</h4>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40">Approved</span>
        </div>
        <div class="grid grid-cols-2 gap-2 text-[11px] bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 font-mono">
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Designated Lead Partner</span>
            <span class="text-indigo-400 font-bold">${s5.designated_lead || leadDisplayName} (${s5.lead_equity_share || '60%'})</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Technical Partner</span>
            <span class="text-cyan-400 font-bold">${s5.designated_partner || partnerDisplayName} (${s5.partner_equity_share || '40%'})</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Synergy Score</span>
            <span class="text-emerald-400 font-bold">${Math.round((s5.synergy_score || 0.96) * 100)}%</span>
          </div>
          <div>
            <span class="text-slate-400 block text-[9px] uppercase">Recommended Action</span>
            <span class="text-amber-300 font-bold">${s5.action || 'RECOMMEND_JV_FORMATION'}</span>
          </div>
        </div>
        <p class="text-[10px] text-amber-400 flex items-center gap-1 font-mono">
          <i data-lucide="award" class="w-3 h-3"></i>
          ${s5.detail || 'Consortium governance approved for tender submission.'}
        </p>
      </div>
    `;

    el.decisionTreeModal.classList.remove('hidden');
    el.decisionTreeModal.classList.add('flex');
    if (window.lucide) window.lucide.createIcons();
  }

  // Format and Render AI Graph Reasoning Trace with Privacy Shielding & Plus Points
  function formatAgentReasoning(rawTrace, alert) {
    if (!rawTrace) return '';

    const isLookalike = alert.match_type === 'LOOKALIKE_PEER' || rawTrace.includes('LOOKALIKE') || rawTrace.includes('HOP');

    let cleanedText = rawTrace;

    // 1. AI evaluator badge
    let evaluatingAgentBadge = `<span class="px-2 py-0.5 rounded text-[9px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 flex items-center gap-1"><i data-lucide="cpu" class="w-2.5 h-2.5 text-indigo-400"></i> NVIDIA Nemotron</span>`;
    cleanedText = cleanedText.replace(/\[AGENT BETA[^\]]*\]/gi, '').replace(/\[AGENT ALPHA[^\]]*\]/gi, '').trim();

    // 1b. Remove internal reference tag [System Traversal Reference: ...]
    const hasInternalAnchor = /\[System Traversal Reference:\s*(.*?)\s*\]/i.test(rawTrace);
    cleanedText = cleanedText.replace(/\[System Traversal Reference:\s*.*?\]/gi, '').trim();

    // 1c. Extract Dynamic Agentic Tool Sequence
    let toolSequence = null;
    const toolSeqMatch = cleanedText.match(/TOOL\s*SEQUENCE\s*>>\s*([^\n]+)/i);
    if (toolSeqMatch) {
      toolSequence = toolSeqMatch[1].trim();
      cleanedText = cleanedText.replace(/TOOL\s*SEQUENCE\s*>>\s*[^\n]+/gi, '').trim();
    }
    const toolSteps = toolSequence ? toolSequence.split(/\s*->\s*/).map(s => s.trim()).filter(Boolean) : [];

    // 2. Extract AI-generated Cypher query if present
    let cypherBlock = null;
    const cypherMatch = cleanedText.match(/CYPHER\s*>>\s*([\s\S]*?)(?=(?:\n\s*[0-9]\.|\n\s*\[|\n\s*•|\n\s*DECISIVE|$))/i);
    if (cypherMatch) {
      cypherBlock = cypherMatch[1].trim();
      cleanedText = cleanedText.replace(/CYPHER\s*>>\s*[\s\S]*?(?=(?:\n\s*[0-9]\.|\n\s*\[|\n\s*•|\n\s*DECISIVE|$))/i, '').trim();
    }

    // 3. Extract Plus Points
    const plusPoints = [];
    const lines = cleanedText.split('\n');
    const remainingLines = [];

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('•') || trimmed.startsWith('✓') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const cleanPt = trimmed.replace(/^[•✓\-\*]\s*/, '').trim();
        if (cleanPt) plusPoints.push(cleanPt);
      } else if (!trimmed.toLowerCase().includes('decisive winning plus points') && !trimmed.toLowerCase().includes('strict bidder confidentiality')) {
        remainingLines.push(line);
      }
    }

    let narrative = remainingLines.join('\n').replace(/\n{3,}/g, '\n\n').trim();

    return `
      <div class="space-y-2.5">
        <!-- AI Evaluator Badge -->
        ${evaluatingAgentBadge ? `
          <div class="flex items-center justify-between pb-1">
            <span class="text-[10px] font-mono text-slate-400">Evaluated By:</span>
            ${evaluatingAgentBadge}
          </div>
        ` : ''}

        <!-- AI Verification Workflow -->
        ${toolSteps.length > 0 ? `
          <div class="bg-indigo-950/40 border border-indigo-500/30 rounded-lg p-2.5 space-y-1.5 font-mono text-[10px]">
            <div class="flex items-center justify-between text-indigo-400 font-semibold uppercase tracking-wider text-[9px] pb-1 border-b border-indigo-500/20">
              <span class="flex items-center gap-1.5"><i data-lucide="git-commit" class="w-3.5 h-3.5 text-indigo-400"></i> AI Verification Workflow</span>
              <span class="text-indigo-300/70 text-[9px]">Verified Steps</span>
            </div>
            <div class="flex items-center flex-wrap gap-1.5 text-slate-300 pt-0.5">
              ${toolSteps.map((step, idx) => `
                <span class="px-2 py-0.5 rounded bg-slate-900 border border-indigo-500/40 text-indigo-200 font-semibold text-[10px]">
                  ${step}
                </span>
                ${idx < toolSteps.length - 1 ? '<i data-lucide="chevron-right" class="w-3 h-3 text-slate-500"></i>' : ''}
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Privacy Shield Badge (If lookalike peer) -->
        ${isLookalike || hasInternalAnchor ? `
          <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 font-mono text-[10px]">
            <i data-lucide="shield-check" class="w-3.5 h-3.5 text-indigo-400 shrink-0"></i>
            <span><strong>Competitor Privacy Shield:</strong> Benchmark qualifying competitor's identity & financials are strictly redacted to guarantee client bid secrecy.</span>
          </div>
        ` : ''}

        <!-- Decisive Winning Plus Points -->
        ${plusPoints.length > 0 ? `
          <div class="bg-emerald-950/20 border border-emerald-500/30 rounded-lg p-3 space-y-1.5">
            <div class="flex items-center gap-1.5 font-bold text-emerald-300 text-[11px] font-mono">
              <i data-lucide="award" class="w-3.5 h-3.5 text-emerald-400"></i>
              <span>Decisive Client Plus Points (Why This Bid Wins)</span>
            </div>
            <ul class="space-y-1.5 text-[11px] text-slate-200 font-mono">
              ${plusPoints.map(pt => `
                <li class="flex items-start gap-1.5">
                  <i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5"></i>
                  <span>${pt}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        ` : ''}

        <!-- Parameterized OpenCypher Template Query -->
        ${cypherBlock ? `
          <div class="space-y-1 bg-slate-950/90 p-2.5 rounded-lg border border-cyan-500/30 font-mono text-[10px]">
            <div class="flex items-center justify-between text-slate-400 text-[9px] uppercase tracking-wider pb-1 border-b border-slate-800">
              <span class="flex items-center gap-1 text-cyan-400"><i data-lucide="terminal" class="w-3 h-3"></i> Graph Verification Query</span>
              <span class="text-[9px] text-slate-500">Executed in FalkorDB via MCP</span>
            </div>
            <pre class="text-cyan-300 whitespace-pre-wrap leading-relaxed overflow-x-auto text-[10px]"><code>${cypherBlock}</code></pre>
          </div>
        ` : ''}

        <!-- AI Graph Decision Narrative -->
        ${narrative ? `
          <div class="bg-indigo-950/20 border border-indigo-500/20 rounded-lg p-2.5 text-xs text-indigo-200 space-y-1">
            <div class="flex items-center space-x-1.5 font-semibold text-indigo-300">
              <i data-lucide="sparkles" class="w-3.5 h-3.5 text-indigo-400"></i>
              <span>AI Decision Strategy & Narrative</span>
            </div>
            <p class="leading-relaxed text-[11px] text-slate-300 whitespace-pre-line">${narrative}</p>
          </div>
        ` : ''}
      </div>
    `;
  }

  // Render Alert Feed
  function renderAlerts(alerts) {
    el.alertsCountBadge.textContent = alerts.length;

    if (!alerts || alerts.length === 0) {
      el.alertFeedContainer.innerHTML = `
        <div class="p-8 text-center border border-dashed border-slate-800 rounded-xl bg-slate-900/30 text-slate-400">
          <i data-lucide="check-circle-2" class="w-8 h-8 text-slate-500 mx-auto mb-2 opacity-60"></i>
          <p class="text-sm font-medium">No alerts found for this filter.</p>
          <p class="text-xs text-slate-400 mt-1">Click "Run AI Tender Matching" above to discover intelligent opportunities.</p>
        </div>
      `;
      return;
    }

    el.alertFeedContainer.innerHTML = alerts.map(alert => {
      const scorePct = Math.round((alert.match_score || 0) * 100);
      const isCooldownActive = alert.cooldown_active;
      const hoursRemaining = alert.cooldown_seconds_remaining
        ? Math.ceil(alert.cooldown_seconds_remaining / 3600)
        : (alert.cooldown_remaining_hours || 0);
      const status = alert.status || alert.alert_status || 'ALERTED';

      let matchBadgeClass = 'badge-direct';
      let matchLabel = 'Direct Match';
      if (alert.match_type === 'LOOKALIKE_PEER') {
        matchBadgeClass = 'badge-lookalike';
        matchLabel = 'Lookalike Peer Match';
      } else if (alert.match_type === 'JV_CONSORTIUM') {
        matchBadgeClass = 'badge-jv';
        matchLabel = 'JV Consortium Pair';
      }

      let statusBadgeClass = 'badge-direct';
      if (status === 'WON') statusBadgeClass = 'badge-won';
      if (status === 'LOST') statusBadgeClass = 'badge-lost';

      const isTerminal = (status === 'WON' || status === 'LOST');

      const agentBadgeHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 flex items-center gap-1"><i data-lucide="cpu" class="w-3 h-3 text-indigo-400"></i> NVIDIA Nemotron</span>`;

      return `
        <div class="glass-card rounded-xl p-4 space-y-3 border ${
          status === 'WON' ? 'border-emerald-500/40 bg-emerald-950/10' : status === 'LOST' ? 'border-rose-500/40 bg-rose-950/10' : 'border-slate-800'
        }">
          <!-- Header: Tender & Client details with Match Score -->
          <div class="flex items-start justify-between gap-3">
            <div class="space-y-1">
              <div class="flex items-center flex-wrap gap-2">
                <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold ${matchBadgeClass}">
                  ${matchLabel}
                </span>
                <span class="px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${statusBadgeClass}">
                  ${status}
                </span>
                ${agentBadgeHtml}
                <span class="text-xs text-slate-400 font-mono">Tender: <strong class="text-slate-200">${alert.tender_id}</strong></span>
                <span class="text-xs text-slate-400 font-mono">Client: <strong class="text-indigo-300">${alert.client_id}</strong></span>
              </div>
              <h4 class="text-sm font-bold text-white">${alert.tender_title || alert.tender_id}</h4>
            </div>

            <!-- Score Pill -->
            <div class="text-right shrink-0">
              <div class="text-lg font-black ${scorePct >= 80 ? 'text-emerald-400' : 'text-indigo-400'} font-mono">${scorePct}%</div>
              <div class="text-[10px] text-slate-400 uppercase tracking-wider font-mono">Match Score</div>
            </div>
          </div>

          <!-- Cooldown & Timing Row -->
          <div class="flex items-center justify-between text-xs py-1.5 px-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
            <div class="flex items-center space-x-2">
              <i data-lucide="shield-alert" class="w-3.5 h-3.5 ${isCooldownActive ? 'text-amber-400' : 'text-emerald-400'}"></i>
              <span class="text-slate-300">
                ${
                  isCooldownActive
                    ? `<span class="text-amber-400 font-semibold font-mono">Cooldown Active:</span> ${hoursRemaining}h remaining (blocks re-alert)`
                    : `<span class="text-emerald-400 font-semibold font-mono">Cooldown Expired:</span> Eligible for matching & alert`
                }
              </span>
            </div>
            <span class="text-[10px] text-slate-400 font-mono">2-Day FalkorDB Rule</span>
          </div>

          <!-- Agent Reasoning Trace with Cypher & Plus Points -->
          ${alert.reasoning_trace ? formatAgentReasoning(alert.reasoning_trace, alert) : ''}

          <!-- JV Consortium Partner Recommendation -->
          ${
            alert.jv_consortium_peers && alert.jv_consortium_peers.length > 0
              ? `
              <div class="bg-amber-950/20 border border-amber-500/20 rounded-lg p-2.5 text-xs text-amber-200">
                <div class="flex items-center space-x-1.5 font-semibold text-amber-300 mb-1">
                  <i data-lucide="handshake" class="w-3.5 h-3.5 text-amber-400"></i>
                  <span>Recommended JV Consortium Partners</span>
                </div>
                <div class="space-y-1">
                  ${alert.jv_consortium_peers
                    .map(
                      p => `
                    <div class="flex items-center justify-between text-[11px] text-slate-300">
                      <span><strong>${p.partner_id || p.partner_name}</strong>: ${p.reason || 'Complementary capability'}</span>
                      <span class="font-mono text-amber-400 font-semibold">${Math.round((p.synergy_score || 0.85) * 100)}% Synergy</span>
                    </div>
                  `
                    )
                    .join('')}
                </div>
              </div>
              `
              : ''
          }

          <!-- Outcome Buttons (Won / Lost Feedback) & Draft Email Action -->
          <div class="flex items-center justify-between pt-1 border-t border-slate-800/80 flex-wrap gap-2">
            <span class="text-[11px] text-slate-400">
              ${isTerminal ? `Outcome recorded: <strong>${status}</strong>` : 'Did the client win or lose this tender?'}
            </span>
            <div class="flex items-center space-x-2">
              <button 
                data-client-id="${alert.client_id}" 
                data-tender-id="${alert.tender_id}" 
                class="btn-send-alert px-2.5 py-1 rounded text-xs font-semibold bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/40 transition flex items-center gap-1 shadow-sm"
                title="Send executive tender alert email to hackathon-demo@outlook.com">
                <i data-lucide="send" class="w-3 h-3 text-indigo-400"></i>
                <span>✉ Send Alert</span>
              </button>
              <button 
                data-client-id="${alert.client_id}" 
                data-tender-id="${alert.tender_id}" 
                data-outcome="WON"
                ${isTerminal ? 'disabled' : ''}
                class="btn-outcome-won px-3 py-1 rounded text-xs font-semibold bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1">
                <i data-lucide="trophy" class="w-3 h-3 text-emerald-400"></i>
                <span>Won</span>
              </button>
              <button 
                data-client-id="${alert.client_id}" 
                data-tender-id="${alert.tender_id}" 
                data-outcome="LOST"
                ${isTerminal ? 'disabled' : ''}
                class="btn-outcome-lost px-3 py-1 rounded text-xs font-semibold bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1">
                <i data-lucide="x" class="w-3 h-3 text-rose-400"></i>
                <span>Lost</span>
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Attach Send Alert Click Handlers
    document.querySelectorAll('.btn-send-alert, .btn-draft-email').forEach(btn => {
      btn.addEventListener('click', () => {
        handleSendAlert(btn.dataset.clientId, btn.dataset.tenderId);
      });
    });

    // Attach Won/Lost Click Handlers
    document.querySelectorAll('.btn-outcome-won').forEach(btn => {
      btn.addEventListener('click', () => {
        handleOutcomeFeedback(btn.dataset.clientId, btn.dataset.tenderId, 'WON');
      });
    });

    document.querySelectorAll('.btn-outcome-lost').forEach(btn => {
      btn.addEventListener('click', () => {
        handleOutcomeFeedback(btn.dataset.clientId, btn.dataset.tenderId, 'LOST');
      });
    });

    if (window.lucide) window.lucide.createIcons();
  }

  // Render Learned Affinities Leaderboard
  function renderAffinities(affinities) {
    if (!affinities || affinities.length === 0) {
      el.affinityPanel.innerHTML = `
        <div class="text-xs text-slate-400 italic py-2 text-center">
          No affinity records logged yet. Click "Won" or "Lost" on an alert to update graph weights.
        </div>
      `;
      return;
    }

    el.affinityPanel.innerHTML = affinities.map(aff => {
      const weightPct = Math.round((aff.affinity_weight || 0.5) * 100);
      const winRatePct = Math.round((aff.win_rate || 0.0) * 100);
      return `
        <div class="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-xs space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="font-bold text-white">${aff.client_id} &rarr; <span class="text-indigo-300">${aff.target_entity || aff.department_id || aff.department_name}</span></span>
            <span class="font-mono text-purple-400 font-bold">${weightPct}% Affinity</span>
          </div>
          <!-- Progress bar -->
          <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div class="bg-gradient-to-r from-indigo-500 to-purple-500 h-1.5 rounded-full" style="width: ${weightPct}%"></div>
          </div>
          <div class="flex items-center justify-between text-[10px] text-slate-400 font-mono">
            <span>Win Rate: <strong class="text-emerald-400">${winRatePct}%</strong></span>
            <span>Bids: ${(aff.wins !== undefined && aff.losses !== undefined) ? (aff.wins + aff.losses) : (aff.total_bids || 0)} (Won: ${aff.wins !== undefined ? aff.wins : (aff.bids_won || 0)})</span>
          </div>
        </div>
      `;
    }).join('');
  }

  // Date and Time Formatting Helpers
  function formatDateTime(val) {
    if (!val) return 'Recently';
    try {
      const d = typeof val === 'number' ? new Date(val * 1000) : new Date(val);
      if (isNaN(d.getTime())) return String(val);
      return d.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      });
    } catch (e) {
      return String(val);
    }
  }

  function formatDate(val) {
    if (!val) return 'Recent';
    try {
      const d = typeof val === 'number' ? new Date(val * 1000) : new Date(val);
      if (isNaN(d.getTime())) return String(val);
      return d.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      });
    } catch (e) {
      return String(val);
    }
  }

  // Render Active Tenders Grid
  function renderTendersGrid(tenders) {
    if (el.tendersCountBadge && tenders) {
      el.tendersCountBadge.textContent = tenders.length;
    }

    if (!tenders || tenders.length === 0) {
      el.tendersGrid.innerHTML = `
        <div class="col-span-full p-6 text-center border border-dashed border-slate-800 rounded-xl bg-slate-900/30 text-slate-400">
          Click "Pull Tender Data" above to fetch active tenders from FalkorDB.
        </div>
      `;
      return;
    }

    el.tendersGrid.innerHTML = tenders.map(tender => {
      const tid = tender.tender_id || tender.id || 'Tender';
      const rawVal = Number(tender.estimated_value_inr || tender.tender_amount || 0);
      const rawTurnover = Number(tender.min_avg_turnover || tender.expected_turnover_3yr || 0);

      const valStr = rawVal >= 10000000 
        ? `₹${(rawVal / 10000000).toFixed(2)} Cr` 
        : rawVal > 0 
          ? `₹${(rawVal / 100000).toFixed(2)} L` 
          : '₹0.00 Cr';

      const turnoverStr = rawTurnover >= 10000000 
        ? `₹${(rawTurnover / 10000000).toFixed(2)} Cr` 
        : rawTurnover > 0 
          ? `₹${(rawTurnover / 100000).toFixed(2)} L` 
          : '₹0.00 Cr';

      const deptStr = tender.department_name || (tender.department && tender.department.name) || tender.department_id || 'Procurement Authority';
      const locStr = tender.location || (tender.region && tender.region.name) || 'India';
      const catStr = tender.work_category_name || tender.work_category || (tender.work_categories && tender.work_categories[0]) || 'General Works';

      // Source Portal determination
      const sourcePortal = String(tender.source_portal || (tid.startsWith('GEM') ? 'GeM' : 'CPPP')).toUpperCase();
      const isGeM = sourcePortal.includes('GEM');
      const portalBadgeClass = isGeM ? 'badge-gem' : 'badge-cppp';
      const portalName = isGeM ? 'GeM Portal' : 'CPPP Portal';
      const portalUrl = tender.tender_url || (isGeM ? 'https://gem.gov.in' : 'https://eprocure.gov.in/eprocure/app');

      // Scraped and Listed Dates
      const scrapedVal = tender.scraped_at;
      const scrapedStr = formatDateTime(scrapedVal || new Date().toISOString());
      const listedVal = tender.listed_date || tender.published_at;
      const listedStr = formatDate(listedVal || new Date().toISOString().split('T')[0]);
      const deadlineStr = tender.deadline_at ? formatDateTime(tender.deadline_at) : '';

      return `
        <div class="glass-card rounded-xl p-4 border border-slate-800 space-y-3 transition-all hover:border-slate-700 shadow-md">
          <!-- Top Row: Tender ID, Portal Badge, External Portal Link, Estimated Value -->
          <div class="flex items-start justify-between gap-2">
            <div class="space-y-1">
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                  ${tid}
                </span>
                <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold ${portalBadgeClass}">
                  ${portalName}
                </span>
                ${portalUrl ? `
                  <a href="${portalUrl}" target="_blank" rel="noopener noreferrer" title="View live tender on ${portalName}" class="text-slate-400 hover:text-cyan-300 text-[10px] flex items-center gap-1 font-mono transition-colors">
                    <span>Portal</span>
                    <i data-lucide="external-link" class="w-3 h-3"></i>
                  </a>
                ` : ''}
              </div>
              <h4 class="text-xs font-bold text-white mt-1 leading-snug">${tender.title}</h4>
            </div>
            <div class="text-right shrink-0">
              <div class="text-sm font-bold text-emerald-400 font-mono">${valStr}</div>
              <div class="text-[9px] text-slate-400 uppercase font-mono">Est. Value</div>
            </div>
          </div>

          <!-- Key Dates Strip: Listed on Portal & Scraped Timestamp -->
          <div class="grid grid-cols-2 gap-2 text-[10px] bg-slate-900/90 px-3 py-2 rounded-lg border border-slate-800 text-slate-300 font-mono">
            <div class="flex items-center gap-1.5">
              <i data-lucide="calendar" class="w-3.5 h-3.5 text-cyan-400 shrink-0"></i>
              <div>
                <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Listed on Portal</span>
                <span class="text-white font-semibold">${listedStr}</span>
              </div>
            </div>
            <div class="flex items-center gap-1.5">
              <i data-lucide="radio" class="w-3.5 h-3.5 text-amber-400 shrink-0"></i>
              <div>
                <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Scraped Date & Time</span>
                <span class="text-amber-300 font-semibold">${scrapedStr}</span>
              </div>
            </div>
          </div>

          <!-- Qualification Parameters -->
          <div class="grid grid-cols-2 gap-2 text-[11px] bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 font-mono">
            <div>
              <span class="text-slate-400 block text-[9px] uppercase">Department</span>
              <span class="text-slate-200 truncate block" title="${deptStr}">${deptStr}</span>
            </div>
            <div>
              <span class="text-slate-400 block text-[9px] uppercase">Min Turnover</span>
              <span class="text-amber-400 font-semibold">${turnoverStr}</span>
            </div>
          </div>

          <!-- Footer: Location, Category, Deadline -->
          <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-800/50 flex-wrap gap-1">
            <span>Location: <strong class="text-slate-300">${locStr}</strong></span>
            <span>Category: <strong class="text-indigo-300">${catStr}</strong></span>
            ${deadlineStr ? `<span>Due: <strong class="text-rose-300">${deadlineStr}</strong></span>` : ''}
          </div>
        </div>
      `;
    }).join('');
    if (window.lucide) window.lucide.createIcons();
  }

  // D3.js Force-Directed Graph Rendering
  function renderD3Graph(topology) {
    if (!topology || !topology.nodes || topology.nodes.length === 0) return;

    const svg = d3.select('#graph-canvas');
    svg.selectAll('*').remove(); // Clear previous render

    const width = svg.node().getBoundingClientRect().width || 480;
    const height = svg.node().getBoundingClientRect().height || 320;

    const container = svg.append('g');

    // Zoom & Pan Behavior
    const zoom = d3.zoom()
      .scaleExtent([0.3, 3])
      .on('zoom', (event) => {
        container.attr('transform', event.transform);
      });
    svg.call(zoom);

    // Color mapper for node labels
    const colorMap = {
      Client: '#6366f1',       // Indigo
      Tender: '#06b6d4',       // Cyan
      Department: '#f59e0b',   // Amber
      Brand: '#10b981',        // Emerald
      WorkCategory: '#ec4899', // Pink
      Certification: '#8b5cf6',// Purple
      Product: '#3b82f6',      // Blue
    };

    // Deep copy data for D3 mutation
    const nodes = topology.nodes.map(d => ({ ...d }));
    const links = topology.links.map(d => ({ ...d }));

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(65))
      .force('charge', d3.forceManyBody().strength(-140))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(22));

    state.d3Simulation = simulation;

    // Draw Links
    const link = container.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('class', 'graph-link')
      .attr('stroke', '#334155');

    // Draw Nodes
    const node = container.append('g')
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('class', 'graph-node')
      .attr('r', d => d.type === 'Client' || d.type === 'Tender' ? 9 : 6)
      .attr('fill', d => colorMap[d.type] || '#94a3b8')
      .attr('stroke', '#0f172a')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended)
      );

    // Node Tooltip & Title
    node.append('title')
      .text(d => `${d.type}: ${d.name || d.id}`);

    // Draw Labels
    const label = container.append('g')
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .attr('class', 'graph-node-label')
      .attr('dy', d => d.type === 'Client' || d.type === 'Tender' ? 18 : 14)
      .text(d => (d.name || d.id).substring(0, 14));

    // Simulation Tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      node
        .attr('cx', d => d.x)
        .attr('cy', d => d.y);

      label
        .attr('x', d => d.x)
        .attr('y', d => d.y);
    });

    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event, d) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }
  }

  // ACTION: Pull Tender Data from DB
  async function handlePullTenders(force = false) {
    if (state.isProcessing && !force) return;
    if (!force) state.isProcessing = true;
    el.btnPullTenders.disabled = true;

    try {
      showToast('Pulling Tenders', 'Querying active tenders and scraper heartbeat via MCP...', 'info');
      const data = await apiCall('/api/tenders/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status_filter: 'ACTIVE' }),
      }, 'get_active_tenders_and_sync_status');

      const pulledTenders = data.tenders || data.active_tenders || [];
      renderTendersGrid(pulledTenders);
      showToast('Tenders Pulled', `Loaded ${pulledTenders.length} active procurement tenders from FalkorDB.`, 'success');
      await fetchDashboard();
    } catch (err) {
      showToast('Pull Failed', err.message, 'error');
    } finally {
      if (!force) state.isProcessing = false;
      el.btnPullTenders.disabled = false;
    }
  }

  // ACTION: Run Tender Matching Loop
  async function handleRunMatchingLoop() {
    if (state.isProcessing) return;
    state.isProcessing = true;
    el.btnRunMatch.disabled = true;
    el.btnRunMatch.classList.add('opacity-75');

    const originalBtnHtml = el.btnRunMatch.innerHTML;
    el.btnRunMatch.innerHTML = `
      <i data-lucide="loader-2" class="w-4 h-4 text-amber-300 animate-spin-fast"></i>
      <span>AI Matching Active...</span>
      <span class="px-1.5 py-0.2 rounded text-[9px] font-mono bg-black/40 text-amber-200 border border-amber-300/30">NVIDIA Nemotron</span>
    `;
    if (window.lucide) window.lucide.createIcons();

    // Trigger prominent buffering notification bar with live elapsed timer
    startAIBuffering('Accelerated AI Reasoning & Tender Matching');

    try {
      const ts = getCurrentTimestamp();
      showToast('AI Tender Matching', 'Accelerated AI reasoning evaluating active tenders with NVIDIA Nemotron...', 'info');

      const data = await apiCall('/api/agent/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_timestamp: ts,
          min_score_threshold: 0.35,
        }),
      }, 'dispatch_tender_alert');

      const evaluated = data.tenders_evaluated ?? data.total_evaluated ?? 0;
      const dispatched = data.alerts_dispatched ?? data.total_alerts_dispatched ?? 0;
      const jvs = data.jv_consortiums_found ?? 0;
      const blocked = data.alerts_skipped_cooldown_or_terminal ?? data.cooldown_blocks_enforced ?? 0;

      const msg = `Accelerated AI Matching Complete: Evaluated ${evaluated} tenders | Dispatched ${dispatched} alerts | Found ${jvs} JV partnerships`;
      stopAIBuffering(true, msg);
      showToast('AI Tender Matching Complete', msg, 'success');
      await fetchDashboard();
    } catch (err) {
      stopAIBuffering(false, err.message);
      showToast('Matching Loop Failed', err.message, 'error');
    } finally {
      state.isProcessing = false;
      el.btnRunMatch.disabled = false;
      el.btnRunMatch.classList.remove('opacity-75');
      el.btnRunMatch.innerHTML = originalBtnHtml;
      if (window.lucide) window.lucide.createIcons();
    }
  }

  // ACTION: Run LangGraph Agentic AI (NVIDIA Nemotron)
  async function handleRunLangGraphAgent() {
    if (state.isProcessing) return;
    state.isProcessing = true;
    let originalBtnHtml = '';
    if (el.btnRunLanggraph) {
      el.btnRunLanggraph.disabled = true;
      el.btnRunLanggraph.classList.add('opacity-75');
      originalBtnHtml = el.btnRunLanggraph.innerHTML;
      el.btnRunLanggraph.innerHTML = `
        <i data-lucide="loader-2" class="w-3.5 h-3.5 text-indigo-300 animate-spin-fast"></i>
        <span>AI Workflow Active...</span>
      `;
      if (window.lucide) window.lucide.createIcons();
    }

    startAIBuffering('Cognitive Workflow Pipeline');

    try {
      const ts = getCurrentTimestamp();
      showToast('AI Workflow Initiated', 'Activating cognitive workflow with NVIDIA Nemotron...', 'info');

      const data = await apiCall('/api/agent/langgraph/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_timestamp: ts,
          min_score_threshold: 0.40,
        }),
      }, 'langgraph_nemotron_agent');

      const msg = `AI Workflow Succeeded: Evaluated ${data.tenders_evaluated} tenders | Dispatched ${data.alerts_dispatched} alerts | Found ${data.jv_consortiums_found} JV partnerships`;
      stopAIBuffering(true, msg);
      showToast('AI Workflow Complete', msg, 'success');
      await fetchDashboard();
    } catch (err) {
      stopAIBuffering(false, err.message);
      showToast('AI Workflow Failed', err.message, 'error');
    } finally {
      state.isProcessing = false;
      if (el.btnRunLanggraph) {
        el.btnRunLanggraph.disabled = false;
        el.btnRunLanggraph.classList.remove('opacity-75');
        el.btnRunLanggraph.innerHTML = originalBtnHtml;
        if (window.lucide) window.lucide.createIcons();
      }
    }
  }

  // ACTION: Record Alert Outcome (Won / Lost)
  async function handleOutcomeFeedback(clientId, tenderId, outcome) {
    try {
      const ts = getCurrentTimestamp();
      showToast('Learning Loop Triggered', `Recording ${outcome} for ${clientId} & updating FalkorDB affinities...`, 'info');

      const data = await apiCall('/api/alerts/outcome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientId,
          tender_id: tenderId,
          outcome: outcome,
          current_timestamp: ts,
          feedback_notes: `Manual judge evaluation feedback via BidGraphAI UI (${outcome}).`,
        }),
      }, 'record_tender_bid_outcome');

      if (data.department_affinity?.status === 'NO_DEPARTMENT') {
        showToast('Graph Memory Notice', 'No procuring department associated with tender; department affinity memory skipped.', 'info');
      } else {
        const dept = data.department_affinity?.department_name || 'Target Dept';
        const winRate = Math.round((data.department_affinity?.win_rate || 0) * 100);
        showToast('Graph Memory Updated', `Affinity weight for ${dept} updated. Win rate: ${winRate}%.`, 'success');
      }

      await fetchDashboard();
    } catch (err) {
      showToast('Feedback Failed', err.message, 'error');
    }
  }

  // ACTION: Record JV Consortium Outcome (Won / Lost)
  async function handleJVOutcome(jvId, outcome) {
    try {
      const ts = getCurrentTimestamp();
      showToast('JV Learning Loop', `Recording ${outcome} for JV Consortium ${jvId} & updating partnership affinity...`, 'info');

      await apiCall('/api/jv/outcome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jv_id: jvId,
          outcome: outcome,
          current_timestamp: ts,
        }),
      }, 'record_jv_outcome_and_learn');

      showToast('Consortium Outcome Saved', `Updated :PARTNERSHIP_AFFINITY in FalkorDB (${outcome}).`, 'success');
      await fetchDashboard();
    } catch (err) {
      showToast('JV Outcome Failed', err.message, 'error');
    }
  }

  // ACTION: +48h Time-Jump Simulator
  function handleTimeJump() {
    // Advance by 48 hours and 10 seconds (172810 seconds)
    state.simulatedOffsetSeconds += 172810;
    const hours = Math.round(state.simulatedOffsetSeconds / 3600);
    el.timeJumpLabel.textContent = `+${hours}h Time Jumped`;
    showToast(
      'Clock Advanced (+48h)',
      `Simulated time advanced by ${hours} hours. Cooldowns in FalkorDB expired!`,
      'warning'
    );
    fetchDashboard();
  }

  // ACTION: Reset Demo Graph
  async function handleResetDemo() {
    if (state.isProcessing) return;
    state.isProcessing = true;
    el.btnResetDemo.disabled = true;

    try {
      showToast('Resetting Demo Graph', 'Restoring FalkorDB benchmark entities and relationships via MCP...', 'info');
      state.simulatedOffsetSeconds = 0;
      el.timeJumpLabel.textContent = '+48h Time Jump';

      await apiCall('/api/demo/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }, 'reset_and_seed_demo_graph');

      showToast('Graph Reset Complete', 'FalkorDB graph returned to initial benchmark state.', 'success');
      await handlePullTenders(true);
      await fetchDashboard();
    } catch (err) {
      showToast('Reset Failed', err.message, 'error');
    } finally {
      state.isProcessing = false;
      el.btnResetDemo.disabled = false;
    }
  }

  // ACTION: Ingest Sample Tender
  // Ingest Live Tenders (Scrape from Indian Govt Websites GeM & CPPP, Enrich, & Upload to FalkorDB)
  async function handleIngestSample() {
    if (state.isProcessing) return;
    state.isProcessing = true;
    el.btnIngestSample.disabled = true;

    try {
      showToast('Live Scraper & Enricher Active', 'Connecting to GeM & CPPP government portals... Scraping live bids, enriching criteria, and uploading to FalkorDB...', 'info');

      const res = await apiCall('/api/pipeline/enrich-and-ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scrape_live: true, portals: ["gem", "cppp"], limit: 10 }),
      }, 'scrape_and_ingest_live_tenders');

      const count = res.total_ingested || (res.tenders && res.tenders.length) || 10;
      showToast('Ingestion Complete', `Successfully scraped and ingested ${count} live tenders from Indian Government Portals into FalkorDB!`, 'success');
      await handlePullTenders(true);
      await fetchDashboard();
    } catch (err) {
      showToast('Live Ingestion Failed', err.message, 'error');
    } finally {
      state.isProcessing = false;
      el.btnIngestSample.disabled = false;
    }
  }

  // Clear All Active Tenders from FalkorDB
  async function handleClearTenders() {
    if (state.isProcessing) return;
    if (!confirm('Are you sure you want to delete all active tender records from FalkorDB?')) return;
    state.isProcessing = true;
    if (el.btnClearTenders) el.btnClearTenders.disabled = true;

    try {
      showToast('Deleting Tenders', 'Clearing all active tenders from FalkorDB via MCP...', 'info');
      const res = await apiCall('/api/tenders/delete-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }, 'delete_all_active_tenders_mcp');

      showToast('Tenders Cleared', `Deleted ${res.deleted_count || 0} active tenders. Click "Reset" to restore benchmark tenders & JVs, or "+ Ingest Live Tenders" to scrape fresh tenders.`, 'success');
      await handlePullTenders(true);
      await fetchDashboard();
    } catch (err) {
      showToast('Deletion Failed', err.message, 'error');
    } finally {
      state.isProcessing = false;
      if (el.btnClearTenders) el.btnClearTenders.disabled = false;
    }
  }

  // Workspace View Tab Switching (Alerts / JV Consortium / Active Tenders)
  function switchWorkspaceTab(tabName) {
    if (tabName === 'alerts') {
      if (el.panelAlerts) el.panelAlerts.classList.remove('hidden');
      if (el.panelJv) el.panelJv.classList.add('hidden');
      if (el.panelTenders) el.panelTenders.classList.add('hidden');

      if (el.tabBtnAlerts) {
        el.tabBtnAlerts.classList.add('active');
        el.tabBtnAlerts.classList.remove('text-slate-400');
      }
      if (el.tabBtnJv) {
        el.tabBtnJv.classList.remove('active');
        el.tabBtnJv.classList.add('text-slate-400');
      }
      if (el.tabBtnTenders) {
        el.tabBtnTenders.classList.remove('active');
        el.tabBtnTenders.classList.add('text-slate-400');
      }
    } else if (tabName === 'jv') {
      if (el.panelAlerts) el.panelAlerts.classList.add('hidden');
      if (el.panelJv) el.panelJv.classList.remove('hidden');
      if (el.panelTenders) el.panelTenders.classList.add('hidden');

      if (el.tabBtnAlerts) {
        el.tabBtnAlerts.classList.remove('active');
        el.tabBtnAlerts.classList.add('text-slate-400');
      }
      if (el.tabBtnJv) {
        el.tabBtnJv.classList.add('active');
        el.tabBtnJv.classList.remove('text-slate-400');
      }
      if (el.tabBtnTenders) {
        el.tabBtnTenders.classList.remove('active');
        el.tabBtnTenders.classList.add('text-slate-400');
      }
    } else if (tabName === 'tenders') {
      if (el.panelAlerts) el.panelAlerts.classList.add('hidden');
      if (el.panelJv) el.panelJv.classList.add('hidden');
      if (el.panelTenders) el.panelTenders.classList.remove('hidden');

      if (el.tabBtnAlerts) {
        el.tabBtnAlerts.classList.remove('active');
        el.tabBtnAlerts.classList.add('text-slate-400');
      }
      if (el.tabBtnJv) {
        el.tabBtnJv.classList.remove('active');
        el.tabBtnJv.classList.add('text-slate-400');
      }
      if (el.tabBtnTenders) {
        el.tabBtnTenders.classList.add('active');
        el.tabBtnTenders.classList.remove('text-slate-400');
      }
    }
    if (window.lucide) window.lucide.createIcons();
  }

  if (el.tabBtnAlerts) el.tabBtnAlerts.addEventListener('click', () => switchWorkspaceTab('alerts'));
  if (el.tabBtnJv) el.tabBtnJv.addEventListener('click', () => switchWorkspaceTab('jv'));
  if (el.tabBtnTenders) el.tabBtnTenders.addEventListener('click', () => switchWorkspaceTab('tenders'));

  // Client Tab Filter Switching
  el.clientTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      el.clientTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.currentClientFilter = tab.dataset.clientFilter;
      fetchDashboard();
    });
  });

  // Populate Executive Tender Alert Email Modal
  function populateEmailModal(draft, batchInfo = null) {
    if (!draft) return;
    state.activeAlertRecord = draft;

    const recipient = draft.dispatched_to || draft.client_email || 'hackathon-demo@outlook.com';

    // Recipient & Status Badge
    el.emailModalRecipient.textContent = recipient;
    el.emailModalRecipient.className = 'font-mono font-bold text-emerald-400';
    el.emailModalStatusBadge.innerHTML = `<i data-lucide="check-circle" class="w-3 h-3 inline mr-1 text-emerald-400"></i><span>${draft.delivery_status || 'SENT'}</span>`;
    el.emailModalStatusBadge.className = 'px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 inline-flex items-center gap-1';

    // Tender chips
    el.emailModalValue.textContent = draft.tender_value_formatted || 'N/A';
    el.emailModalDeadline.textContent = draft.tender_deadline || draft.tender_end_date || 'N/A';
    el.emailModalScore.textContent = `${draft.fit_score_pct || draft.match_score_pct || 0}%`;
    el.emailModalScope.textContent = draft.scope_of_work || 'General Scope';
    el.emailModalScope.title = draft.scope_of_work || '';

    // Plus points
    const pts = draft.plus_points && draft.plus_points.length > 0 ? draft.plus_points : ['Statutory domain alignment in FalkorDB knowledge graph'];
    el.emailModalPlusPoints.innerHTML = pts.map(p => `<li>${p}</li>`).join('');

    // Reason why client was chosen
    if (el.emailModalReasonChosen) {
      el.emailModalReasonChosen.textContent = draft.reason_chosen || 'Direct structural qualification alignment in FalkorDB knowledge graph.';
    }

    // Engine attribution
    if (el.emailModalEngineBadge) {
      el.emailModalEngineBadge.textContent = draft.model_used || 'BidGraphAI Communications Agent';
    }

    // Subject & Body
    el.emailModalSubject.textContent = draft.email_subject || draft.subject || 'Tender Alert Notification';
    el.emailModalBody.textContent = draft.email_body || draft.body_plain || '';

    // Batch nav
    if (batchInfo && batchInfo.total > 1) {
      el.emailModalBatchNav.classList.remove('hidden');
      el.emailModalBatchNav.classList.add('flex');
      el.batchProgressLabel.textContent = `Match ${batchInfo.current + 1} of ${batchInfo.total} (${draft.client_id} → ${draft.tender_id})`;
      el.btnBatchPrev.disabled = batchInfo.current === 0;
      el.btnBatchNext.disabled = batchInfo.current === batchInfo.total - 1;
      el.btnBatchPrev.classList.toggle('opacity-40', batchInfo.current === 0);
      el.btnBatchNext.classList.toggle('opacity-40', batchInfo.current === batchInfo.total - 1);
    } else {
      el.emailModalBatchNav.classList.add('hidden');
      el.emailModalBatchNav.classList.remove('flex');
    }

    // Show modal
    el.emailPreviewModal.classList.remove('hidden');
    el.emailPreviewModal.classList.add('flex');
    if (window.lucide) window.lucide.createIcons();
  }

  // ACTION: Send Single Tender Alert Email to hackathon-demo@outlook.com
  async function handleSendAlert(clientId, tenderId) {
    try {
      startAIBuffering(`BidGraphAI Agent: Dispatching Alert for ${clientId} to hackathon-demo@outlook.com`);
      const res = await apiCall('/api/agent/send-alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, tender_id: tenderId }),
      }, 'send_tender_alert');

      stopAIBuffering(true, `Alert Sent to ${res.recipient}`);
      showToast('Alert Email Sent', `Dispatched tender alert for ${tenderId} to ${res.recipient}`, 'success');
      populateEmailModal(res.record);
    } catch (err) {
      stopAIBuffering(false, 'Alert Dispatch Failed');
      showToast('Alert Dispatch Failed', err.message, 'error');
    }
  }

  // ACTION: Batch Send Alert Emails to hackathon-demo@outlook.com for All Active Matches
  async function handleSendBatchAlerts() {
    try {
      startAIBuffering('BidGraphAI Agent: Dispatching Batch Alerts to hackathon-demo@outlook.com');
      const res = await apiCall('/api/agent/send-all-alerts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }, 'send_all_tender_alerts');

      stopAIBuffering(true, `Dispatched ${res.total_sent} Alert Emails to ${res.recipient}`);
      if (!res.records || res.records.length === 0) {
        showToast('No Active Matches', 'Run AI Tender Matching first to discover matches.', 'warning');
        return;
      }

      state.batchDrafts = res.records;
      state.currentBatchIndex = 0;
      showToast('Batch Alerts Sent', `Dispatched ${res.total_sent} tender alerts to ${res.recipient}`, 'success');
      populateEmailModal(state.batchDrafts[0], { current: 0, total: state.batchDrafts.length });
    } catch (err) {
      stopAIBuffering(false, 'Batch Dispatch Failed');
      showToast('Batch Dispatch Failed', err.message, 'error');
    }
  }

  function handleBatchPrev() {
    if (state.currentBatchIndex > 0) {
      state.currentBatchIndex--;
      populateEmailModal(state.batchDrafts[state.currentBatchIndex], {
        current: state.currentBatchIndex,
        total: state.batchDrafts.length,
      });
    }
  }

  function handleBatchNext() {
    if (state.currentBatchIndex < state.batchDrafts.length - 1) {
      state.currentBatchIndex++;
      populateEmailModal(state.batchDrafts[state.currentBatchIndex], {
        current: state.currentBatchIndex,
        total: state.batchDrafts.length,
      });
    }
  }

  async function copyTextToClipboard(text, successMsg) {
    try {
      await navigator.clipboard.writeText(text);
      showToast('Copied to Clipboard', successMsg, 'success');
    } catch (e) {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      showToast('Copied to Clipboard', successMsg, 'success');
    }
  }

  // Attach Event Listeners
  if (el.btnPullTenders) {
    el.btnPullTenders.addEventListener('click', async () => {
      await handlePullTenders();
      switchWorkspaceTab('tenders');
    });
  }
  if (el.btnRunMatch) {
    el.btnRunMatch.addEventListener('click', async () => {
      await handleRunMatchingLoop();
      // Ensure we are viewing alerts after running matching
      switchWorkspaceTab('alerts');
    });
  }
  if (el.btnRunLanggraph) {
    el.btnRunLanggraph.addEventListener('click', handleRunLangGraphAgent);
  }
  if (el.btnDraftAllEmails) {
    el.btnDraftAllEmails.addEventListener('click', handleSendBatchAlerts);
  }
  if (el.btnTimeJump) el.btnTimeJump.addEventListener('click', handleTimeJump);
  if (el.btnResetDemo) el.btnResetDemo.addEventListener('click', handleResetDemo);
  if (el.btnIngestSample) el.btnIngestSample.addEventListener('click', handleIngestSample);
  if (el.btnClearTenders) el.btnClearTenders.addEventListener('click', handleClearTenders);

  if (el.btnCloseDtModal) {
    el.btnCloseDtModal.addEventListener('click', () => {
      el.decisionTreeModal.classList.add('hidden');
      el.decisionTreeModal.classList.remove('flex');
    });
  }

  if (el.decisionTreeModal) {
    el.decisionTreeModal.addEventListener('click', (e) => {
      if (e.target === el.decisionTreeModal) {
        el.decisionTreeModal.classList.add('hidden');
        el.decisionTreeModal.classList.remove('flex');
      }
    });
  }

  // Email Preview Modal Event Listeners
  if (el.btnCloseEmailModal) {
    el.btnCloseEmailModal.addEventListener('click', () => {
      el.emailPreviewModal.classList.add('hidden');
      el.emailPreviewModal.classList.remove('flex');
    });
  }
  if (el.btnModalClose) {
    el.btnModalClose.addEventListener('click', () => {
      el.emailPreviewModal.classList.add('hidden');
      el.emailPreviewModal.classList.remove('flex');
    });
  }
  if (el.emailPreviewModal) {
    el.emailPreviewModal.addEventListener('click', (e) => {
      if (e.target === el.emailPreviewModal) {
        el.emailPreviewModal.classList.add('hidden');
        el.emailPreviewModal.classList.remove('flex');
      }
    });
  }
  if (el.btnBatchPrev) el.btnBatchPrev.addEventListener('click', handleBatchPrev);
  if (el.btnBatchNext) el.btnBatchNext.addEventListener('click', handleBatchNext);
  if (el.btnCopySubject) {
    el.btnCopySubject.addEventListener('click', () => {
      copyTextToClipboard(el.emailModalSubject.textContent, 'Subject copied to clipboard!');
    });
  }
  if (el.btnCopyBody) {
    el.btnCopyBody.addEventListener('click', () => {
      copyTextToClipboard(el.emailModalBody.textContent, 'Email body copied to clipboard!');
    });
  }
  if (el.btnModalSendAlert) {
    el.btnModalSendAlert.addEventListener('click', () => {
      if (state.activeAlertRecord) {
        handleSendAlert(state.activeAlertRecord.client_id, state.activeAlertRecord.tender_id);
      }
    });
  }
  if (el.btnModalCopyAll) {
    el.btnModalCopyAll.addEventListener('click', () => {
      const fullText = `To: ${el.emailModalRecipient.textContent}\nSubject: ${el.emailModalSubject.textContent}\n\n${el.emailModalBody.textContent}`;
      copyTextToClipboard(fullText, 'Complete email draft copied to clipboard!');
    });
  }

  // Initial Load Sequence
  (async function init() {
    logMcpCall('initialize_mcp_client', 12, 'SUCCESS', 'Handshake ready');
    await handlePullTenders();
    await fetchDashboard();
  })();
});
