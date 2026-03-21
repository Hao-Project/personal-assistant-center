const grid = document.getElementById('task-grid');
let pollingTimers = {};

async function fetchTasks() {
  const res = await fetch('/api/tasks');
  return res.json();
}

function formatTime(iso) {
  if (!iso) return 'Never';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function statusInfo(s) {
  if (!s || s.state === 'idle') return { dot: 'idle', label: 'Never run' };
  if (s.state === 'running')    return { dot: 'running', label: 'Running...' };
  if (s.success)                return { dot: 'success', label: `Last run: ${formatTime(s.finished_at)}` };
  return                               { dot: 'failed',  label: `Failed: ${formatTime(s.finished_at)}` };
}

function buildCard(task) {
  const { dot, label } = statusInfo(task.status);
  const isRunning = task.status?.state === 'running';

  const card = document.createElement('div');
  card.className = 'card';
  card.id = `card-${task.id}`;
  card.innerHTML = `
    <div class="card-top">
      <span class="card-icon">${task.icon}</span>
      <div class="card-meta">
        <div class="card-name">${task.name}</div>
        <div class="card-description">${task.description}</div>
      </div>
    </div>
    <div class="status-row">
      <span class="status-dot ${dot}"></span>
      <span class="status-label">${label}</span>
    </div>
    <div class="card-actions">
      <button class="btn-run" id="run-${task.id}" onclick="runTask('${task.id}')" ${isRunning ? 'disabled' : ''}>
        ${isRunning ? 'Running...' : 'Run'}
      </button>
      ${isRunning ? `<button class="btn-stop" onclick="stopTask('${task.id}')">Stop</button>` : ''}
      <button class="btn-log" onclick="showLog('${task.id}', '${task.name}')">Log</button>
    </div>
  `;
  return card;
}

function updateCard(task) {
  const existing = document.getElementById(`card-${task.id}`);
  const newCard = buildCard(task);
  if (existing) {
    existing.replaceWith(newCard);
  } else {
    grid.appendChild(newCard);
  }
}

async function loadTasks() {
  const tasks = await fetchTasks();
  tasks.forEach(updateCard);
}

async function runTask(taskId) {
  await fetch(`/api/tasks/${taskId}/run`, { method: 'POST' });
  const tasks = await fetchTasks();
  const task = tasks.find(t => t.id === taskId);
  if (task) updateCard(task);
  pollStatus(taskId);
}

function pollStatus(taskId) {
  if (pollingTimers[taskId]) clearInterval(pollingTimers[taskId]);

  pollingTimers[taskId] = setInterval(async () => {
    const res = await fetch(`/api/tasks/${taskId}/status`);
    const status = await res.json();

    if (status.state !== 'running') {
      clearInterval(pollingTimers[taskId]);
      delete pollingTimers[taskId];
      // Refresh the full card
      const tasks = await fetchTasks();
      const task = tasks.find(t => t.id === taskId);
      if (task) updateCard(task);
    }
  }, 2000);
}

async function stopTask(taskId) {
  await fetch(`/api/tasks/${taskId}/stop`, { method: 'POST' });
  const tasks = await fetchTasks();
  const task = tasks.find(t => t.id === taskId);
  if (task) updateCard(task);
}

async function showLog(taskId, taskName) {
  document.getElementById('log-title').textContent = `Log — ${taskName}`;
  document.getElementById('log-content').textContent = 'Loading...';
  document.getElementById('log-modal').classList.remove('hidden');

  const res = await fetch(`/api/tasks/${taskId}/log`);
  const data = await res.json();
  const content = document.getElementById('log-content');
  content.textContent = data.log || 'No log available.';
  content.scrollTop = content.scrollHeight;
}

function closeLog() {
  document.getElementById('log-modal').classList.add('hidden');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeLog();
});

// Init
loadTasks();

// Re-check any already-running tasks on page load
(async () => {
  const tasks = await fetchTasks();
  tasks.forEach(t => {
    if (t.status?.state === 'running') pollStatus(t.id);
  });
})();
