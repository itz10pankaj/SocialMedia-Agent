// Personal Social Media Agent - Dashboard Frontend Logic

let currentDraft = null;
let isEditing = false;

// DOM Elements
const ollamaDot = document.getElementById('ollama-dot');
const ollamaText = document.getElementById('ollama-text');
const btnRunPipeline = document.getElementById('btn-run-pipeline');
const loadingOverlay = document.getElementById('loading-overlay');
const toastContainer = document.getElementById('toast-container');

// Draft Card Elements
const badgeDraftId = document.getElementById('badge-draft-id');
const badgeStatus = document.getElementById('badge-status');
const badgeStyle = document.getElementById('badge-style');
const badgeWordCount = document.getElementById('badge-word-count');
const postTimestamp = document.getElementById('post-timestamp');
const draftTopic = document.getElementById('draft-topic');
const draftAngle = document.getElementById('draft-angle');
const postViewBody = document.getElementById('post-view-body');
const postEditBody = document.getElementById('post-edit-body');
const btnToggleEdit = document.getElementById('btn-toggle-edit');
const btnApprove = document.getElementById('btn-approve');
const btnCopy = document.getElementById('btn-copy');
const btnShareLinkedIn = document.getElementById('btn-share-linkedin');
const sourcesList = document.getElementById('sources-list');

// Sidebar Containers
const trendsContainer = document.getElementById('trends-container');
const trendsCount = document.getElementById('trends-count');
const historyContainer = document.getElementById('history-container');

// Toast Notification Helper
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✓' : 'ℹ'}</span> <span>${message}</span>`;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Check Health & Ollama Status
async function checkHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    if (data.status === 'ok' && data.ollama && !data.ollama.error) {
      ollamaDot.className = 'status-dot';
      ollamaText.textContent = `Ollama: ${data.ollama.model} (Ready)`;
    } else {
      ollamaDot.className = 'status-dot error';
      ollamaText.textContent = 'Ollama: Offline';
    }
  } catch (err) {
    ollamaDot.className = 'status-dot error';
    ollamaText.textContent = 'Ollama: Offline';
  }
}

// Format relative date
function formatRelativeDate(dateStr) {
  if (!dateStr) return 'Recently';
  const d = new Date(dateStr);
  const diffHours = Math.round((new Date() - d) / (1000 * 60 * 60));
  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// Parse Style from Angle
function parseStyleAndAngle(angleRaw) {
  if (!angleRaw) return { style: 'ANALYSIS', angle: '' };
  const match = angleRaw.match(/^\[(.*?)\]\s*(.*)$/);
  if (match) {
    return { style: match[1].toUpperCase(), angle: match[2] };
  }
  return { style: 'ANALYSIS', angle: angleRaw };
}

// Render Draft in Studio Card
function renderDraft(draft) {
  currentDraft = draft;
  if (!draft) {
    postViewBody.textContent = 'No drafts created yet. Click "Run Pipeline Now" to generate your first post!';
    return;
  }

  badgeDraftId.textContent = `Draft #${draft.id}`;
  badgeWordCount.textContent = `${draft.word_count || draft.text.split(/\s+/).length} words`;
  
  // Status Badge
  badgeStatus.textContent = draft.status;
  if (draft.status === 'APPROVED') {
    badgeStatus.className = 'badge badge-approved';
    btnApprove.textContent = '✓ Approved';
    btnApprove.disabled = true;
    btnApprove.style.opacity = '0.7';
  } else {
    badgeStatus.className = 'badge badge-pending';
    btnApprove.textContent = '✓ Approve Post';
    btnApprove.disabled = false;
    btnApprove.style.opacity = '1';
  }

  // Style & Angle
  const { style, angle } = parseStyleAndAngle(draft.angle);
  badgeStyle.textContent = style;
  draftTopic.textContent = draft.topic || 'Engineering Discovery';
  draftAngle.textContent = angle || 'Core technical insight for developers';
  postTimestamp.textContent = `Generated ${formatRelativeDate(draft.created_at)} · 🌐`;

  // Content
  postViewBody.textContent = draft.text;
  postEditBody.value = draft.text;

  // Render Sources
  sourcesList.innerHTML = '';
  if (draft.sources && draft.sources.length > 0) {
    draft.sources.forEach(src => {
      const a = document.createElement('a');
      a.className = 'source-item';
      a.href = src.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.innerHTML = `<span>🔗</span> <span>[${src.source || 'web'}] ${src.title || src.url}</span>`;
      sourcesList.appendChild(a);
    });
  } else {
    sourcesList.innerHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">No external source links</span>';
  }

  // Highlight active in history
  document.querySelectorAll('.history-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id == draft.id);
  });
}

// Load Drafts and History
async function loadDrafts(selectId = null) {
  try {
    const res = await fetch('/drafts?limit=15');
    const drafts = await res.json();
    
    // Render History list
    historyContainer.innerHTML = '';
    drafts.forEach(d => {
      const item = document.createElement('div');
      item.className = 'history-item';
      item.dataset.id = d.id;
      item.innerHTML = `
        <span class="history-topic">#${d.id}: ${d.topic || 'Tech News'}</span>
        <span class="badge ${d.status === 'APPROVED' ? 'badge-approved' : 'badge-pending'}">${d.status}</span>
      `;
      item.addEventListener('click', () => {
        if (isEditing) toggleEdit(false);
        renderDraft(d);
      });
      historyContainer.appendChild(item);
    });

    // Select specific or latest
    const selected = selectId ? drafts.find(d => d.id === selectId) : drafts[0];
    renderDraft(selected);
  } catch (err) {
    console.error('Failed to load drafts:', err);
  }
}

// Load Today's Ranked Trends
async function loadTrends() {
  try {
    const runsRes = await fetch('/runs?limit=1');
    const runs = await runsRes.json();
    if (!runs || runs.length === 0) return;

    const latestRunId = runs[0].id;
    const itemsRes = await fetch(`/runs/${latestRunId}/items`);
    const items = await itemsRes.json();

    trendsContainer.innerHTML = '';
    const relevant = items.filter(i => i.status === 'sent_to_llm' || i.status === 'chosen');
    trendsCount.textContent = `${relevant.length} sent to LLM`;

    relevant.forEach(item => {
      const card = document.createElement('a');
      card.className = 'trend-card';
      card.href = item.url;
      card.target = '_blank';
      card.rel = 'noopener noreferrer';

      let sourceClass = 'source-rss';
      if (item.source.includes('hackernews')) sourceClass = 'source-hn';
      else if (item.source.includes('reddit')) sourceClass = 'source-reddit';
      else if (item.source.includes('github')) sourceClass = 'source-github';

      const tags = (item.matched_keywords || []).slice(0, 3).map(k => `<span class="tag-item">#${k}</span>`).join('');

      card.innerHTML = `
        <div class="trend-header">
          <span class="source-pill ${sourceClass}">${item.source}</span>
          <span class="trend-score">⭐ ${Math.round(item.score)} | Score: ${item.rank_score}</span>
        </div>
        <div class="trend-title">${item.title}</div>
        <div class="trend-tags">${tags}</div>
      `;
      trendsContainer.appendChild(card);
    });
  } catch (err) {
    console.error('Failed to load trends:', err);
  }
}

// Toggle Edit Mode
function toggleEdit(save = false) {
  if (isEditing) {
    if (save && currentDraft) {
      saveDraftEdit();
    }
    postViewBody.style.display = 'block';
    postEditBody.style.display = 'none';
    btnToggleEdit.textContent = '✏️ Edit Draft';
    btnToggleEdit.className = 'btn btn-secondary btn-sm';
    isEditing = false;
  } else {
    postViewBody.style.display = 'none';
    postEditBody.style.display = 'block';
    postEditBody.focus();
    btnToggleEdit.textContent = '💾 Save Edits';
    btnToggleEdit.className = 'btn btn-primary btn-sm';
    isEditing = true;
  }
}

// Save Draft Edit via PATCH
async function saveDraftEdit() {
  if (!currentDraft) return;
  const newText = postEditBody.value.trim();
  try {
    const res = await fetch(`/drafts/${currentDraft.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: newText })
    });
    if (res.ok) {
      const updated = await res.json();
      currentDraft.text = updated.text;
      currentDraft.word_count = updated.word_count;
      postViewBody.textContent = updated.text;
      badgeWordCount.textContent = `${updated.word_count} words`;
      showToast('Draft edits saved successfully!');
    }
  } catch (err) {
    showToast('Failed to save draft edits', 'info');
  }
}

// Approve Draft
async function approveDraft() {
  if (!currentDraft) return;
  try {
    const res = await fetch(`/drafts/${currentDraft.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'APPROVED' })
    });
    if (res.ok) {
      currentDraft.status = 'APPROVED';
      badgeStatus.textContent = 'APPROVED';
      badgeStatus.className = 'badge badge-approved';
      btnApprove.textContent = '✓ Approved';
      btnApprove.disabled = true;
      btnApprove.style.opacity = '0.7';
      showToast(`Draft #${currentDraft.id} approved for LinkedIn!`);
      loadDrafts(currentDraft.id);
    }
  } catch (err) {
    showToast('Failed to approve draft', 'info');
  }
}

// Copy Post Text to Clipboard
async function copyPost() {
  if (!currentDraft || !currentDraft.text) return;
  try {
    await navigator.clipboard.writeText(currentDraft.text);
    showToast('Post copied to clipboard!');
  } catch (err) {
    showToast('Failed to copy to clipboard', 'info');
  }
}

// Open LinkedIn Share Intent
function shareToLinkedIn() {
  if (!currentDraft || !currentDraft.text) return;
  const encodedText = encodeURIComponent(currentDraft.text);
  const shareUrl = `https://www.linkedin.com/feed/?shareActive=true&text=${encodedText}`;
  window.open(shareUrl, '_blank', 'noopener,noreferrer');
  showToast('Opening LinkedIn feed...');
}

// Run Pipeline Now
async function runPipeline() {
  loadingOverlay.classList.add('active');
  try {
    const res = await fetch('/run?force=true&wait=true', { method: 'POST' });
    const runResult = await res.json();
    loadingOverlay.classList.remove('active');
    if (runResult.status === 'OK' && runResult.draft_id) {
      showToast(`Pipeline complete! Draft #${runResult.draft_id} created.`);
      await loadDrafts(runResult.draft_id);
      await loadTrends();
    } else {
      showToast(`Pipeline status: ${runResult.status}`, 'info');
      await loadDrafts();
      await loadTrends();
    }
  } catch (err) {
    loadingOverlay.classList.remove('active');
    showToast('Pipeline execution failed', 'info');
  }
}

// Event Listeners
btnToggleEdit.addEventListener('click', () => toggleEdit(isEditing));
btnApprove.addEventListener('click', approveDraft);
btnCopy.addEventListener('click', copyPost);
btnShareLinkedIn.addEventListener('click', shareToLinkedIn);
btnRunPipeline.addEventListener('click', runPipeline);

// Initialize
checkHealth();
loadDrafts();
loadTrends();
setInterval(checkHealth, 30000);
