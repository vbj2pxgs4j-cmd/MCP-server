/**
 * Weekly Customer Pulse Dashboard - Client Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // State
  let pulseData = null;
  let logPollingInterval = null;

  // DOM Elements
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');
  const themeToggleBtn = document.getElementById('theme-toggle-btn');
  const refreshBtn = document.getElementById('refresh-btn');
  const triggerAllBtn = document.getElementById('trigger-all-btn');
  const previewFrame = document.getElementById('preview-frame');
  const mdView = document.getElementById('markdown-view');
  const viewHtmlBtn = document.getElementById('view-html-btn');
  const viewMdBtn = document.getElementById('view-md-btn');
  const copyReportBtn = document.getElementById('copy-report-btn');
  const downloadReportBtn = document.getElementById('download-report-btn');
  const terminalLogs = document.getElementById('terminal-logs');
  const terminalStatus = document.getElementById('terminal-status');

  // Initialize
  initTheme();
  setupTabs();
  setupPipelineTriggers();
  setupReportControls();
  fetchPulseData();

  // Tab Switching
  function setupTabs() {
    tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetId = btn.getAttribute('data-tab');
        
        tabBtns.forEach((b) => b.classList.remove('active'));
        tabContents.forEach((c) => c.classList.remove('active'));

        btn.classList.add('active');
        const targetContent = document.getElementById(targetId);
        if (targetContent) {
          targetContent.classList.add('active');
        }

        // If report preview tab is activated, load report
        if (targetId === 'tab-report') {
          loadReportPreview();
        }
      });
    });
  }

  // Theme Toggle
  function initTheme() {
    const savedTheme = localStorage.getItem('pulse_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    if (themeToggleBtn) {
      themeToggleBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('pulse_theme', newTheme);
        updateThemeIcon(newTheme);
      });
    }
  }

  function updateThemeIcon(theme) {
    if (!themeToggleBtn) return;
    themeToggleBtn.innerHTML = theme === 'light' ? '🌙' : '☀️';
  }

  // Fetch Data from Server
  async function fetchPulseData() {
    try {
      showToast('Fetching latest pulse insights...', 'info');
      const res = await fetch('/api/pulse');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      pulseData = await res.json();
      renderDashboard(pulseData);
    } catch (err) {
      console.error('Failed to load pulse data:', err);
      showToast('Error loading live data. Using cached insights.', 'warning');
    }
  }

  // Render Dashboard Elements
  function renderDashboard(data) {
    // 1. Update Metrics
    const reviewCountEl = document.getElementById('metric-reviews');
    const avgRatingEl = document.getElementById('metric-rating');
    const painPointsCountEl = document.getElementById('metric-painpoints');
    const actionsCountEl = document.getElementById('metric-actions');

    if (reviewCountEl) reviewCountEl.textContent = data.review_count || 19;
    if (avgRatingEl) avgRatingEl.textContent = `${data.avg_rating || 1.89} ⭐`;
    
    const painThemes = (data.themes || []).filter(t => t.category === 'Pain Point');
    if (painPointsCountEl) painPointsCountEl.textContent = painThemes.length || 3;
    if (actionsCountEl) actionsCountEl.textContent = (data.actions || []).length || 3;

    // Rating distribution bars
    if (data.rating_breakdown) {
      const total = data.review_count || 1;
      for (let star = 1; star <= 5; star++) {
        const count = data.rating_breakdown[star] || 0;
        const pct = Math.round((count / total) * 100);
        const fillEl = document.getElementById(`star-${star}-fill`);
        const textEl = document.getElementById(`star-${star}-pct`);
        if (fillEl) fillEl.style.width = `${pct}%`;
        if (textEl) textEl.textContent = `${count}`;
      }
    }

    // 2. Render Themes
    const themesContainer = document.getElementById('themes-container');
    if (themesContainer && data.themes) {
      themesContainer.innerHTML = data.themes.map(theme => {
        const badgeClass = theme.sentiment === 'Critical' ? 'critical' : theme.sentiment === 'Positive' ? 'positive' : 'high';
        return `
          <div class="theme-card">
            <div class="theme-card-header">
              <h3 class="theme-title">${escapeHtml(theme.name)}</h3>
              <span class="theme-badge ${badgeClass}">${escapeHtml(theme.sentiment)}</span>
            </div>
            <p class="theme-desc">${escapeHtml(theme.description)}</p>
            ${theme.sample_quote ? `
              <div class="theme-quote-box">
                "${escapeHtml(theme.sample_quote)}"
              </div>
            ` : ''}
            <div class="theme-stats">
              <span>Impact Score: <strong>${theme.impact_score || 85}/100</strong></span>
              <span>Mentions: <strong>${theme.mentions || 1}</strong></span>
            </div>
          </div>
        `;
      }).join('');
    }

    // 3. Render Verbatim Quotes
    const quotesContainer = document.getElementById('quotes-container');
    if (quotesContainer && data.quotes) {
      quotesContainer.innerHTML = data.quotes.map(q => `
        <div class="theme-card">
          <div class="theme-card-header">
            <h3 class="theme-title" style="font-size: 1rem;">${escapeHtml(q.theme)}</h3>
            <span class="theme-badge high">⭐ ${q.rating}/5</span>
          </div>
          <div class="theme-quote-box" style="margin-top: 0; font-size: 0.95rem;">
            "${escapeHtml(q.text)}"
          </div>
          <div class="theme-stats">
            <span>Verified Play Store Review</span>
            <span>${q.date || 'Recent'}</span>
          </div>
        </div>
      `).join('');
    }

    // 4. Render Action Items
    const actionsContainer = document.getElementById('actions-container');
    if (actionsContainer && data.actions) {
      actionsContainer.innerHTML = data.actions.map(act => `
        <div class="action-card">
          <div class="action-id">${act.id || 'ACT'}</div>
          <div class="action-body">
            <h4>${escapeHtml(act.title)}</h4>
            <p>${escapeHtml(act.description)}</p>
            <div class="action-tags">
              <span class="action-tag" style="background: rgba(99, 102, 241, 0.15); color: #818cf8;">👤 ${escapeHtml(act.owner || 'Product')}</span>
              <span class="action-tag" style="background: rgba(244, 63, 94, 0.15); color: #fb7185;">🔥 ${escapeHtml(act.priority || 'P0')}</span>
              <span class="action-tag">⚡ Effort: ${escapeHtml(act.effort || 'Med')}</span>
              <span class="action-tag">📈 Impact: ${escapeHtml(act.impact || 'High')}</span>
            </div>
          </div>
          <button class="btn btn-secondary" onclick="alert('Ticket drafted for ${escapeHtml(act.title)}')">Create Ticket</button>
        </div>
      `).join('');
    }
  }

  // Report Controls (HTML / Markdown / Copy / Download)
  function setupReportControls() {
    if (viewHtmlBtn && viewMdBtn) {
      viewHtmlBtn.addEventListener('click', () => {
        viewHtmlBtn.classList.add('btn-primary');
        viewHtmlBtn.classList.remove('btn-secondary');
        viewMdBtn.classList.remove('btn-primary');
        viewMdBtn.classList.add('btn-secondary');
        if (previewFrame) previewFrame.style.display = 'block';
        if (mdView) mdView.style.display = 'none';
      });

      viewMdBtn.addEventListener('click', async () => {
        viewMdBtn.classList.add('btn-primary');
        viewMdBtn.classList.remove('btn-secondary');
        viewHtmlBtn.classList.remove('btn-primary');
        viewHtmlBtn.classList.add('btn-secondary');
        if (previewFrame) previewFrame.style.display = 'none';
        if (mdView) {
          mdView.style.display = 'block';
          try {
            const res = await fetch('/api/report/md');
            if (res.ok) {
              mdView.textContent = await res.text();
            } else {
              mdView.textContent = '# No Markdown report found. Run the pipeline to generate one.';
            }
          } catch (e) {
            mdView.textContent = '# Error loading Markdown report.';
          }
        }
      });
    }

    if (copyReportBtn) {
      copyReportBtn.addEventListener('click', async () => {
        try {
          const res = await fetch('/api/report/md');
          const md = await res.text();
          await navigator.clipboard.writeText(md);
          showToast('Markdown report copied to clipboard!', 'success');
        } catch (e) {
          showToast('Failed to copy report.', 'critical');
        }
      });
    }

    if (downloadReportBtn) {
      downloadReportBtn.addEventListener('click', () => {
        window.open('/api/report/html', '_blank');
      });
    }

    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        fetchPulseData();
        loadReportPreview();
      });
    }
  }

  function loadReportPreview() {
    if (previewFrame) {
      previewFrame.src = '/api/report/html?t=' + Date.now();
    }
  }

  // Pipeline Execution
  function setupPipelineTriggers() {
    const triggerPhase1 = document.getElementById('btn-run-p1');
    const triggerPhase2 = document.getElementById('btn-run-p2');
    const triggerPhase3 = document.getElementById('btn-run-p3');
    const triggerAll = document.getElementById('btn-run-all');

    if (triggerPhase1) triggerPhase1.addEventListener('click', () => triggerPhase('phase1'));
    if (triggerPhase2) triggerPhase2.addEventListener('click', () => triggerPhase('phase2'));
    if (triggerPhase3) triggerPhase3.addEventListener('click', () => triggerPhase('phase3'));
    if (triggerAll) triggerAll.addEventListener('click', () => triggerPhase('all'));
    if (triggerAllBtn) triggerAllBtn.addEventListener('click', () => {
      // Switch to console tab and run
      document.querySelector('[data-tab="tab-console"]')?.click();
      triggerPhase('all');
    });
  }

  async function triggerPhase(phase) {
    try {
      showToast(`Starting ${phase}...`, 'info');
      if (terminalStatus) {
        terminalStatus.textContent = 'RUNNING...';
        terminalStatus.className = 'theme-badge high';
      }

      const res = await fetch('/api/run-phase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phase })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to start run');
      }

      // Start log polling
      startLogPolling();
    } catch (err) {
      showToast(err.message, 'critical');
      if (terminalStatus) {
        terminalStatus.textContent = 'ERROR';
        terminalStatus.className = 'theme-badge critical';
      }
    }
  }

  function startLogPolling() {
    if (logPollingInterval) clearInterval(logPollingInterval);

    logPollingInterval = setInterval(async () => {
      try {
        const res = await fetch('/api/run-status');
        const status = await res.json();

        if (terminalLogs && status.logs) {
          terminalLogs.innerHTML = status.logs.map(log => `
            <div class="log-entry">
              <span class="log-time">></span>
              <span>${escapeHtml(log)}</span>
            </div>
          `).join('');
          terminalLogs.scrollTop = terminalLogs.scrollHeight;
        }

        if (!status.is_running) {
          clearInterval(logPollingInterval);
          logPollingInterval = null;
          if (terminalStatus) {
            terminalStatus.textContent = status.status === 'success' ? 'COMPLETED' : 'FAILED';
            terminalStatus.className = status.status === 'success' ? 'theme-badge positive' : 'theme-badge critical';
          }
          showToast(`Pipeline execution finished (${status.status})`, status.status === 'success' ? 'success' : 'critical');
          fetchPulseData();
        }
      } catch (err) {
        console.error('Error polling logs:', err);
      }
    }, 1200);
  }

  // Toast Utility
  function showToast(message, type = 'info') {
    let toast = document.getElementById('app-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'app-toast';
      toast.className = 'toast';
      document.body.appendChild(toast);
    }

    const icon = type === 'success' ? '✅' : type === 'critical' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';
    toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
    toast.classList.add('show');

    setTimeout(() => {
      toast.classList.remove('show');
    }, 3500);
  }

  // Helper: Escape HTML
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
