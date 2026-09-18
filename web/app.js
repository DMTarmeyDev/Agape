const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

let FILE = null;
let INTAKE = null;
let CURRENT_JOB = '';
let QUALITY = 'standard';
let SOURCE_MODE = 'paste';
let SETUP = {settings:{}};
let SYSTEM = {};
let selectedExperience = 'basic';
let PROGRESS = {jobId:'', last:0, stage:'', stageChecks:0, lastChangedAt:Date.now()};
let MAINFRAME_INSTANCE = '';
let MAINFRAME_BUILD = '';
let RESEARCH_PROGRESS = {timer:null, startedAt:0, percent:0};
let LAST_EXTRA_INTAKE_ID = '';
let DOWNLOAD_MANAGER = {
  open:false, jobId:'', startedAt:0,
  preparation:{name:'Result preparation',status:'idle',progress:0,stage:'Waiting',instruction:'Start creating a result to see its progress here.',eta:''},
  items:[]
};

async function api(url, opt={}) {
  let response;
  try {
    response = await fetch(url, opt);
  } catch (rawError) {
    const error = new Error(rawError?.name === 'AbortError'
      ? 'Agape local connection timed out.'
      : 'Agape local connection was interrupted.');
    error.network = true;
    error.url = url;
    error.cause = rawError;
    throw error;
  }
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { data = {raw:text}; }
  if (!response.ok) {
    const error = new Error(data.error || data.message || text || `HTTP ${response.status}`);
    error.status = response.status;
    error.url = url;
    throw error;
  }
  return data;
}

function formatDuration(seconds) {
  const n = Math.max(0, Math.round(Number(seconds) || 0));
  if (n < 60) return `${n}s`;
  const m = Math.floor(n / 60), s = n % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60), rm = m % 60;
  return `${h}h ${rm}m`;
}

function estimateRemaining(percent, startedAt) {
  const p = Number(percent);
  const elapsed = Math.max(0, (Date.now() - Number(startedAt || Date.now())) / 1000);
  if (!Number.isFinite(p) || p <= 3 || p >= 100 || elapsed < 1) return '';
  const remaining = elapsed * (100 - p) / Math.max(1, p);
  if (!Number.isFinite(remaining) || remaining > 6 * 3600) return '';
  return `Estimated remaining: ~${formatDuration(remaining)}`;
}

function researchProgressPaint(percent, stage, text, failed=false) {
  const box = $('researchProgress');
  if (!box) return;
  box.classList.remove('hidden');
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  RESEARCH_PROGRESS.percent = p;
  $('researchBar').style.width = `${p}%`;
  $('researchBar').classList.toggle('failed', Boolean(failed));
  $('researchPercent').textContent = `${Math.round(p)}%`;
  $('researchStage').textContent = stage || 'Researching';
  $('researchText').textContent = text || 'Agape is researching public information.';
}

function startResearchProgress() {
  if (RESEARCH_PROGRESS.timer) clearInterval(RESEARCH_PROGRESS.timer);
  RESEARCH_PROGRESS = {timer:null, startedAt:Date.now(), percent:8};
  researchProgressPaint(8, 'Preparing research', 'Saving your current brief before the public-information search starts.');
  RESEARCH_PROGRESS.timer = setInterval(() => {
    const elapsed = Math.max(1, Math.round((Date.now() - RESEARCH_PROGRESS.startedAt) / 1000));
    let p = RESEARCH_PROGRESS.percent;
    let stage = 'Searching public information';
    let text = `Agape is checking public sources for the unresolved fields · ${elapsed}s elapsed.`;
    if (elapsed < 3) {
      p = Math.min(22, p + 4);
      stage = 'Saving brief';
      text = `Saving your current answers before research · ${elapsed}s elapsed.`;
    } else if (elapsed < 12) {
      p = Math.min(62, p + 3.5);
    } else {
      p = Math.min(90, p + 1.2);
      stage = 'Checking and applying findings';
      text = `Agape is checking evidence and applying safe public facts · ${elapsed}s elapsed.`;
    }
    researchProgressPaint(p, stage, text);
  }, 900);
}

function finishResearchProgress(ok=true, message='Research complete. The brief has been updated.') {
  if (RESEARCH_PROGRESS.timer) clearInterval(RESEARCH_PROGRESS.timer);
  RESEARCH_PROGRESS.timer = null;
  researchProgressPaint(100, ok ? 'Research complete' : 'Research stopped', message, !ok);
}

function canonicalStatusLabel(value) {
  const raw=String(value?.status_label || value?.display_status || value?.work_status || value?.status || value || '').trim();
  const key=raw.toUpperCase().replace(/[ -]+/g,'_');
  if (['PASS','COMPLETE','COMPLETED','SUCCESS','DONE'].includes(key)) return 'Complete';
  if (['BLOCKED','ACTION_REQUIRED','NEEDS_ATTENTION'].includes(key)) return 'Needs attention';
  if (['FAIL','FAILED','ERROR'].includes(key)) return 'Failed';
  if (['QUEUED','PENDING'].includes(key)) return 'Queued';
  if (['RUNNING','WORKING','IN_PROGRESS','START','STARTED','UNKNOWN'].includes(key)) return 'Working';
  return raw || 'Saved';
}

function downloadStatusLabel(status) {
  return ({preparing:'Preparing',ready:'Ready',downloading:'Downloading',completed:'Completed',failed:'Failed',idle:'Waiting'})[status] || String(status || 'Waiting');
}

function downloadInstruction(item) {
  if (item.status === 'preparing') return 'Agape is still creating/checking this result. You do not need to do anything yet.';
  if (item.status === 'ready') return 'The file is ready. Press Download to save it to your computer.';
  if (item.status === 'downloading') return 'Keep this Agape window open until this file reaches 100%.';
  if (item.status === 'completed') return 'Saved successfully. You can download it again or open the folder containing Agape’s generated copy.';
  if (item.status === 'failed' && item.kind === 'preparation') return 'Result creation stopped before a new file was produced. Fix the problem shown below, then press Create result again.';
  if (item.status === 'failed') return 'The file was not downloaded. Read the error below, then press Retry download.';
  return item.instruction || 'Waiting for Agape.';
}

const DOWNLOAD_HISTORY_KEY = 'agape.download-manager.v2';

function saveDownloadManagerState() {
  try {
    const rows = DOWNLOAD_MANAGER.items.slice(0,80).map(x => ({...x,status:x.status==='downloading'?'ready':x.status}));
    localStorage.setItem(DOWNLOAD_HISTORY_KEY, JSON.stringify(rows));
  } catch {}
}

function restoreDownloadManagerState() {
  try {
    const rows = JSON.parse(localStorage.getItem(DOWNLOAD_HISTORY_KEY) || '[]');
    if (Array.isArray(rows)) DOWNLOAD_MANAGER.items = rows.filter(x => x && x.jobId && Number.isFinite(Number(x.index))).slice(0,80);
  } catch {}
}

function historyResultFiles(item) {
  const root = item?.result || {};
  const candidates = [root, root?.job, root?.result, root?.job?.result];
  for (const value of candidates) {
    if (!value || typeof value !== 'object') continue;
    const files = Array.isArray(value.files) ? value.files : (value.file ? [value.file] : []);
    if (files.length) return files;
  }
  return [];
}

async function hydrateDownloadHistory() {
  restoreDownloadManagerState();
  try {
    const data = await api('/api/recent?limit=100');
    const existing = new Set(DOWNLOAD_MANAGER.items.map(x => `${x.jobId}:${x.index}`));
    for (const work of (data.items || [])) {
      const jobId=String(work.external_job_id || ''); if (!jobId) continue;
      historyResultFiles(work).forEach((file,index) => {
        const key=`${jobId}:${index}`; if (existing.has(key)) return;
        const rawName=typeof file==='string'?file:(file.name||file.file||file.path||`File ${index+1}`);
        DOWNLOAD_MANAGER.items.push({index,jobId,name:String(rawName).split(/[\\/]/).pop(),projectTitle:work.title||'',status:'ready',progress:100,stage:'Saved result',eta:'Ready now',error:''});
        existing.add(key);
      });
    }
    DOWNLOAD_MANAGER.items=DOWNLOAD_MANAGER.items.slice(0,80); saveDownloadManagerState(); renderDownloadManager();
  } catch { renderDownloadManager(); }
}

function renderDownloadManager() {
  const panel = $('downloadManagerPanel');
  const button = $('downloadManagerButton');
  const badge = $('downloadManagerBadge');
  const host = $('downloadManagerItems');
  if (!panel || !button || !badge || !host) return;
  const prep = DOWNLOAD_MANAGER.preparation;
  const rows = [];
  if (prep && prep.status !== 'idle') rows.push({...prep,kind:'preparation'});
  const currentJob = String(DOWNLOAD_MANAGER.jobId || CURRENT_JOB || '');
  DOWNLOAD_MANAGER.items
    .filter(item => currentJob && String(item.jobId || '') === currentJob)
    .forEach(item => rows.push({...item,kind:'file'}));
  const active = rows.filter(x => ['preparing','downloading'].includes(x.status)).length;
  const completed = rows.filter(x => ['ready','completed'].includes(x.status)).length;
  button.classList.toggle('hidden', !rows.length);
  badge.classList.toggle('hidden', !rows.length);
  badge.textContent = active ? `${active} active` : `${completed} ready`;
  panel.classList.toggle('hidden', !DOWNLOAD_MANAGER.open || !rows.length);
  host.innerHTML = rows.map(row => {
    const pct = Math.max(0, Math.min(100, Number(row.progress) || 0));
    const eta = row.eta || '';
    const error = row.error ? `<p class="download-error"><b>Problem:</b> ${esc(row.error)}</p>` : '';
    let actions = '';
    if (row.kind === 'file') {
      const downloadText = row.status === 'completed' ? 'Download again' : row.status === 'failed' ? 'Retry download' : 'Download';
      if (row.status !== 'downloading') actions += `<button type="button" data-dm-download="${row.index}" data-dm-job="${esc(row.jobId||'')}">${downloadText}</button>`;
      if (row.jobId) actions += `<button type="button" data-dm-open="${row.index}" data-dm-job="${esc(row.jobId)}">Open folder</button>`;
    }
    const project = row.projectTitle ? `<span>${esc(row.projectTitle)}</span>` : '';
    return `<article class="download-item" data-status="${esc(row.status)}"><div class="download-item-head"><div><div class="download-item-name">${esc(row.name)}</div><div class="download-meta"><span class="download-status">${esc(downloadStatusLabel(row.status))}</span>${project}<span>${esc(row.stage || '')}</span>${eta ? `<span>${esc(eta)}</span>` : ''}</div></div><strong>${Math.round(pct)}%</strong></div><div class="progress"><span class="${row.status==='failed'?'failed':''}" style="width:${pct}%"></span></div><p class="download-instruction">${esc(downloadInstruction(row))}</p>${error}${actions ? `<div class="download-actions">${actions}</div>` : ''}</article>`;
  }).join('') || '<p class="muted">No active or completed downloads yet.</p>';
  host.querySelectorAll('[data-dm-download]').forEach(node => node.onclick = () => downloadManagedFile(node.dataset.dmJob, Number(node.dataset.dmDownload)));
  host.querySelectorAll('[data-dm-open]').forEach(node => node.onclick = () => openGeneratedFolder(node.dataset.dmJob, Number(node.dataset.dmOpen)));
}

function beginResultPreparation(text='Agape is preparing the result.', percent=1) {
  DOWNLOAD_MANAGER.startedAt = Date.now();
  DOWNLOAD_MANAGER.jobId = '';
  // A new creation run owns a fresh manager view. Previous files remain in
  // Results/history but must never look like outputs from this new job.
  DOWNLOAD_MANAGER.items = [];
  DOWNLOAD_MANAGER.preparation = {name:'Result preparation',status:'preparing',progress:Number(percent)||1,stage:'Starting',instruction:text,eta:''};
  renderDownloadManager();
}

function updateResultPreparation(jobId, percent, stage, instruction='') {
  if (!DOWNLOAD_MANAGER.startedAt) DOWNLOAD_MANAGER.startedAt = Date.now();
  if (jobId) DOWNLOAD_MANAGER.jobId = jobId;
  const p = Math.max(Number(DOWNLOAD_MANAGER.preparation.progress)||0, Math.min(100, Number(percent)||0));
  DOWNLOAD_MANAGER.preparation = {
    ...DOWNLOAD_MANAGER.preparation,
    name:'Result preparation', status:p >= 100 ? 'completed' : 'preparing', progress:p,
    stage:stage || DOWNLOAD_MANAGER.preparation.stage || 'Working',
    instruction:instruction || DOWNLOAD_MANAGER.preparation.instruction || 'Agape is preparing the result.',
    eta:p >= 100 ? 'Ready now' : estimateRemaining(p, DOWNLOAD_MANAGER.startedAt),
  };
  renderDownloadManager();
}

function registerResultFiles(result, jobId='') {
  const files = Array.isArray(result?.files) ? result.files : (result?.file ? [result.file] : []);
  DOWNLOAD_MANAGER.jobId = jobId || DOWNLOAD_MANAGER.jobId;
  updateResultPreparation(DOWNLOAD_MANAGER.jobId, 100, 'Finished', 'Agape finished creating and validating the result.');
  const title = String(INTAKE?.project_name || INTAKE?.ai_fill?.project_name || INTAKE?.ai_fill?.title || '');
  const fresh = files.map((file,index) => {
    const rawName = typeof file === 'string' ? file : (file.name || file.file || file.path || `File ${index+1}`);
    return {index,jobId:DOWNLOAD_MANAGER.jobId,projectTitle:title,name:String(rawName).split(/[\\/]/).pop(),status:'ready',progress:100,stage:'Ready to download',eta:'Ready now',error:''};
  });
  const keys = new Set(fresh.map(x => `${x.jobId}:${x.index}`));
  DOWNLOAD_MANAGER.items = fresh.slice(0,80);
  saveDownloadManagerState();
  renderDownloadManager();
  return files;
}

function filenameFromDisposition(value, fallback) {
  const text = String(value || '');
  const utf = text.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf) { try { return decodeURIComponent(utf[1].replace(/["']/g,'')); } catch {} }
  const plain = text.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1] : fallback;
}

async function downloadManagedFile(jobId, index) {
  if (!jobId) return toast('This result does not have a downloadable job yet.');
  const item = DOWNLOAD_MANAGER.items.find(x => String(x.jobId||'') === String(jobId||'') && Number(x.index) === Number(index));
  if (!item) return;
  item.status = 'downloading'; item.progress = 0; item.stage = 'Connecting'; item.eta = ''; item.error = '';
  DOWNLOAD_MANAGER.open = true; renderDownloadManager();
  const started = performance.now();
  try {
    const response = await fetch(`/api/work/${encodeURIComponent(jobId)}/download?index=${Number(index)}`);
    if (!response.ok) {
      const text = await response.text();
      let detail = text;
      try { detail = JSON.parse(text).error || text; } catch {}
      throw new Error(detail || `Download failed with HTTP ${response.status}`);
    }
    const total = Number(response.headers.get('Content-Length') || 0);
    const contentType = response.headers.get('Content-Type') || 'application/octet-stream';
    const filename = filenameFromDisposition(response.headers.get('Content-Disposition'), item.name || `agape-result-${index+1}`);
    const chunks = [];
    let received = 0;
    if (response.body?.getReader) {
      const reader = response.body.getReader();
      while (true) {
        const {done,value} = await reader.read();
        if (done) break;
        chunks.push(value); received += value.byteLength;
        const elapsed = Math.max(.05, (performance.now() - started) / 1000);
        const speed = received / elapsed;
        item.progress = total > 0 ? Math.min(99, received * 100 / total) : Math.min(95, Math.max(5, item.progress + 8));
        item.stage = total > 0 ? `${received.toLocaleString()} of ${total.toLocaleString()} bytes` : `${received.toLocaleString()} bytes received`;
        item.eta = total > received && speed > 0 ? `Estimated remaining: ~${formatDuration((total-received)/speed)}` : '';
        renderDownloadManager();
      }
    } else {
      const blob = await response.blob();
      chunks.push(new Uint8Array(await blob.arrayBuffer())); received = blob.size;
    }
    if (received <= 0) throw new Error('Agape returned an empty file.');
    const blob = new Blob(chunks,{type:contentType});
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl; a.download = filename; a.style.display = 'none';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
    item.name = filename; item.status = 'completed'; item.progress = 100; item.stage = `${received.toLocaleString()} bytes saved`; item.eta = 'Finished';
    renderDownloadManager();
    toast(`${filename} downloaded`);
  } catch (error) {
    item.status = 'failed'; item.stage = 'Download failed'; item.eta = ''; item.error = String(error?.message || error);
    renderDownloadManager();
  }
}

async function openGeneratedFolder(jobId, index) {
  if (!jobId) return toast('No generated file is available yet.');
  try {
    const data = await api(`/api/work/${encodeURIComponent(jobId)}/open-folder?index=${Number(index)}`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    toast(data.simulated ? 'Folder action verified in QA mode' : 'Opened generated file location');
  } catch (error) {
    const item = DOWNLOAD_MANAGER.items.find(x => Number(x.index) === Number(index));
    if (item) item.error = `Could not open folder: ${error?.message || error}`;
    renderDownloadManager();
  }
}

if ($('downloadManagerButton')) $('downloadManagerButton').onclick = () => { DOWNLOAD_MANAGER.open = true; renderDownloadManager(); };
if ($('closeDownloadManager')) $('closeDownloadManager').onclick = () => { DOWNLOAD_MANAGER.open = false; renderDownloadManager(); };

function page(id) {
  document.querySelectorAll('.page').forEach(node => node.classList.toggle('active', node.id === id));
  document.querySelectorAll('nav button').forEach(node => node.classList.toggle('active', node.dataset.page === id));
  if (id === 'results') loadRecent();
  if (id === 'settings') loadSettings();
  if (id === 'projects') loadProjects();
  if (id === 'workspace') loadWorkspace();
}
document.querySelectorAll('nav button').forEach(button => button.onclick = () => page(button.dataset.page));

let STATUS_VIEW_REFRESHING=false;
async function refreshVisibleStatusView() {
  if (STATUS_VIEW_REFRESHING || document.visibilityState === 'hidden') return;
  const active=document.querySelector('.page.active')?.id || '';
  if (!['results','projects','workspace'].includes(active)) return;
  STATUS_VIEW_REFRESHING=true;
  try {
    if (active === 'results') await loadRecent();
    else if (active === 'projects') await loadProjects();
    else if (active === 'workspace') await loadWorkspace();
  } finally { STATUS_VIEW_REFRESHING=false; }
}
setInterval(refreshVisibleStatusView, 5000);
window.addEventListener('focus', () => refreshVisibleStatusView().catch(()=>{}));
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refreshVisibleStatusView().catch(()=>{}); });

function setStep(step) {
  [1,2,3].forEach(n => $(`stepIndicator${n}`).classList.toggle('active', n === step));
}

function file64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function setSourceMode(mode) {
  if (!['paste','upload','project'].includes(mode)) mode = 'paste';
  SOURCE_MODE = mode;
  document.querySelectorAll('[data-source-mode]').forEach(button => button.classList.toggle('selected', button.dataset.sourceMode === mode));
  $('sourcePastePanel').classList.toggle('hidden', mode !== 'paste');
  $('sourceUploadPanel').classList.toggle('hidden', mode !== 'upload');
  $('sourceProjectPanel').classList.toggle('hidden', mode !== 'project');
  updateSourceStatus();
}
document.querySelectorAll('[data-source-mode]').forEach(button => button.onclick = () => setSourceMode(button.dataset.sourceMode));

function activeSourceReady() {
  if (SOURCE_MODE === 'paste') return Boolean($('sourceText').value.trim());
  if (SOURCE_MODE === 'upload') return Boolean(FILE);
  if (SOURCE_MODE === 'project') return Number($('project').value || 0) > 0;
  return false;
}


function renderProjectStarters() {
  const select = $('sourceTemplateSelect');
  const load = $('loadSourceTemplate');
  const help = $('sourceTemplateHelp');
  if (!select || !load) return;
  const rows = Array.isArray(window.AGAPE_PROJECT_TEMPLATES) ? window.AGAPE_PROJECT_TEMPLATES : [];
  select.innerHTML = '<option value="">Blank source</option>' + rows.map(row => `<option value="${esc(row.id)}">${esc(row.name)}</option>`).join('');

  const selectedTemplate = () => rows.find(row => String(row.id) === String(select.value || '')) || null;
  const refreshTemplateChoice = () => {
    const row = selectedTemplate();
    load.disabled = !row;
    if (help) help.textContent = row ? String(row.description || 'Load this template into the editable source box.') : 'Start blank, or choose a built-in template and load it into the editable source box.';
  };
  select.onchange = refreshTemplateChoice;
  load.onclick = () => {
    const row = selectedTemplate();
    if (!row) return;
    const current = String($('sourceText').value || '').trim();
    if (current && current !== String(row.source_text || '').trim() && !window.confirm('Replace the current pasted source with this template?')) return;
    $('sourceText').value = String(row.source_text || '');
    $('task').value = String(row.task || '');
    setSourceMode('paste');
    updateSourceStatus();
    toast(`Loaded template: ${row.name}`);
    $('sourceText').focus();
  };
  refreshTemplateChoice();
}

async function recoverProjects() {
  const button = $('recoverProjects');
  const box = $('recoveryResult');
  if (!button || !box) return;
  button.disabled = true;
  box.classList.remove('hidden','bad','ready');
  box.textContent = 'Scanning old Agape databases and creating a safety backup…';
  try {
    const data = await api('/api/projects/recover', {method:'POST', body:JSON.stringify({})});
    const names = data.recovered_projects || [];
    box.classList.add('ready');
    box.innerHTML = `<b>Recovery complete.</b> ${Number(data.projects_added||0)} project(s) restored, ${Number(data.messages_added||0)} message(s) restored from ${Number(data.databases_scanned||0)} database(s).` +
      (names.length ? `<br><small>Restored: ${names.map(esc).join(', ')}</small>` : '<br><small>No missing user projects were found.</small>') +
      (data.backup ? `<br><small>Safety backup: ${esc(data.backup)}</small>` : '');
    await loadProjects();
  } catch (err) {
    box.classList.add('bad');
    box.textContent = 'Project recovery failed: ' + (err?.message || String(err));
  } finally {
    button.disabled = false;
  }
}

function updateSourceStatus() {
  const box = $('sourceStatus');
  box.classList.remove('ready','bad');
  if (SOURCE_MODE === 'paste') {
    const chars = $('sourceText').value.trim().length;
    box.textContent = chars ? `Ready — ${chars.toLocaleString()} characters of pasted text will be checked and used.` : 'Paste some text to continue.';
  } else if (SOURCE_MODE === 'upload') {
    box.textContent = FILE ? `Ready — ${FILE.name} will be extracted, checked for writing issues and used.` : 'Choose a document to continue.';
  } else {
    const pid = Number($('project').value || 0);
    const option = $('project').selectedOptions[0];
    box.textContent = pid ? `Ready — Agape will use saved project “${option?.textContent || 'selected project'}”.` : 'Choose a saved project to continue.';
  }
  if (activeSourceReady()) box.classList.add('ready');
}

async function loadProjects() {
  const data = await api('/api/projects').catch(() => ({projects:[]}));
  const rows = data.projects || [];
  $('project').innerHTML = '<option value="0">Choose a saved project</option>' + rows.map(p => `<option value="${Number(p.id)||0}">${esc(p.name)}</option>`).join('');
  $('projectList').innerHTML = rows.length ? rows.map(p => `
    <div class="project-row">
      <button class="result-file project-use" data-pid="${Number(p.id)||0}">
        <span><b>${esc(p.name)}</b><br><small>${esc(p.goal || p.description || 'Saved project')}</small></span>
        <span><b>${esc(canonicalStatusLabel(p))}</b><br><small>Use as source -></small></span>
      </button>
      <button class="project-delete" data-delete-pid="${Number(p.id)||0}" data-delete-name="${esc(p.name)}" title="Permanently delete this project">Delete</button>
    </div>`).join('') : '<p class="muted">No saved user projects are currently available.</p>';
  document.querySelectorAll('[data-pid]').forEach(button => button.onclick = () => {
    $('project').value = button.dataset.pid;
    setSourceMode('project');
    page('home');
    setStep(1);
    $('sourceCard').scrollIntoView({behavior:'smooth'});
  });
  document.querySelectorAll('[data-delete-pid]').forEach(button => button.onclick = async event => {
    event.stopPropagation();
    const projectId = Number(button.dataset.deletePid || 0);
    const projectName = button.dataset.deleteName || 'this project';
    if (!projectId || !window.confirm(`Permanently delete "${projectName}"?

This removes the saved project and its Core project data. Existing generated results remain in Results & versions.`)) return;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Deleting...';
    try {
      await api('/api/projects/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({project_id:projectId})});
      if (Number($('project').value || 0) === projectId) $('project').value = '0';
      await loadProjects();
      if ($('workspace')?.classList.contains('active')) await loadWorkspace();
    } catch (error) {
      button.disabled = false;
      button.textContent = originalText;
      window.alert('Agape could not delete this project: ' + (error?.message || error));
    }
  });
  updateSourceStatus();
}

if ($('recoverProjects')) $('recoverProjects').onclick = recoverProjects;
$('file').onchange = () => {
  FILE = $('file').files[0] || null;
  $('fileLabel').textContent = FILE ? FILE.name : 'Choose a document';
  updateSourceStatus();
};
$('sourceText').addEventListener('input', updateSourceStatus);
$('project').addEventListener('change', updateSourceStatus);

function applyQuality(value) {
  QUALITY = value === 'gold' ? 'gold' : 'standard';
  document.querySelectorAll('.quality').forEach(button => button.classList.toggle('selected', button.dataset.quality === QUALITY));
  const allowChoice = selectedExperience !== 'basic';
  $('qualityInline').classList.toggle('hidden', !allowChoice);
  $('goldOptions').classList.toggle('hidden', !allowChoice || QUALITY !== 'gold');
  $('qualityHelp').textContent = allowChoice
    ? 'Choose faster creation or deeper multi-AI review.'
    : `Using ${QUALITY === 'gold' ? 'Gold Standard' : 'Create Now'} from Settings. Technical choices stay hidden in Basic mode.`;
}
document.querySelectorAll('.quality').forEach(button => button.onclick = () => applyQuality(button.dataset.quality));

function applyExperienceUI() {
  selectedExperience = SETUP.settings?.experience || selectedExperience || 'basic';
  applyQuality(SETUP.settings?.quality || QUALITY || 'standard');
  if ($('allDetails')) $('allDetails').open = selectedExperience === 'advanced';
  if ($('technicalDetails')) $('technicalDetails').classList.toggle('hidden', selectedExperience === 'basic');
}

async function boot() {
  try {
    const health = await api('/api/health');
    MAINFRAME_INSTANCE = String(health.instance_id || '');
    MAINFRAME_BUILD = String(health.build || '');
    $('status').textContent = 'Ready';
    SETUP = {settings: health.settings || {}};
    selectedExperience = SETUP.settings.experience || 'basic';
    QUALITY = SETUP.settings.quality || 'standard';
    applyExperienceUI();
    await loadProjects();
    renderProjectStarters();
    await hydrateDownloadHistory();
    if (!SETUP.settings.setup_complete) {
      SETUP = await api('/api/setup/status');
      selectedExperience = SETUP.settings.experience || 'basic';
      QUALITY = SETUP.settings.quality || 'standard';
      applyExperienceUI();
      renderSetupRecommendation();
      $('setup').classList.remove('hidden');
    }
  } catch (error) {
    $('status').textContent = 'Needs attention';
    showError(error);
  }
}

function setPrepareBusy(on) {
  $('analyse').disabled = on;
  $('analyse').textContent = on ? 'Preparing with AI…' : 'Prepare with AI';
}

async function intakePrepareStatus(id) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try { return await api(`/api/intake-prepare/${encodeURIComponent(id)}`, {signal:controller.signal}); }
  finally { clearTimeout(timer); }
}

async function mainframeHealth(timeoutMs=4000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try { return await api('/api/health', {signal:controller.signal}); }
  finally { clearTimeout(timer); }
}

async function waitForIntakePreparation(id) {
  let networkErrors = 0;
  let knownInstance = MAINFRAME_INSTANCE;
  while (true) {
    try {
      const row = await intakePrepareStatus(id);
      networkErrors = 0;
      const status = String(row.status || '').toUpperCase();
      const percent = Math.max(0, Math.min(100, Number(row.progress || 0)));
      const message = row.message || 'Preparing source';
      $('sourceStatus').textContent = `${message} · ${Math.round(percent)}%`;
      $('sourceStatus').classList.remove('bad');
      $('sourceStatus').classList.add('ready');
      if (['COMPLETE','COMPLETED','PASS','SUCCESS','DONE'].includes(status)) return row.result || row;
      if (['FAILED','FAIL','ERROR','BLOCKED'].includes(status)) throw Error(row.error || row.message || 'Source preparation failed.');
      await sleep(1200);
    } catch (error) {
      if (!error?.network) throw error;
      networkErrors += 1;
      let detail = `Agape connection interrupted — reconnecting to source preparation… (${networkErrors})`;
      if (networkErrors % 3 === 0) {
        try {
          const health = await mainframeHealth();
          const instance = String(health.instance_id || '');
          if (instance && knownInstance && instance !== knownInstance) {
            detail = 'Agape Mainframe restarted — resuming the saved source-preparation job…';
          } else {
            detail = 'Agape Mainframe is back — reconnecting to the saved source-preparation job…';
          }
          knownInstance = instance || knownInstance;
          MAINFRAME_INSTANCE = instance || MAINFRAME_INSTANCE;
          MAINFRAME_BUILD = String(health.build || MAINFRAME_BUILD);
        } catch (_) {
          // Keep the normal reconnect message while the local server is offline.
        }
      }
      $('sourceStatus').textContent = detail;
      $('sourceStatus').classList.remove('bad');
      $('sourceStatus').classList.add('ready');
      if (networkErrors >= 12) {
        const offline = new Error('Agape Mainframe is offline. Open “Agape - Start” from the Desktop, then press Prepare with AI again. The interrupted source request has been saved for recovery.');
        offline.network = false;
        throw offline;
      }
      await sleep(Math.min(6000, 750 + networkErrors * 400));
    }
  }
}

async function startIntakePreparation(payload) {
  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      return await api('/api/intake/start', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(payload),
      });
    } catch (error) {
      lastError = error;
      if (!error?.network) throw error;
      $('sourceStatus').textContent = `Agape connection interrupted while starting preparation — retrying (${attempt}/3)…`;
      await sleep(800 * attempt);
    }
  }
  throw lastError || Error('Agape could not start source preparation.');
}

$('analyse').onclick = async () => {
  if (!activeSourceReady()) {
    $('sourceStatus').textContent = SOURCE_MODE === 'paste' ? 'Paste some source text first.' : SOURCE_MODE === 'upload' ? 'Choose a document first.' : 'Choose a saved project first.';
    $('sourceStatus').classList.remove('ready');
    $('sourceStatus').classList.add('bad');
    return;
  }
  try {
    setPrepareBusy(true);
    $('sourceStatus').textContent = 'Agape is checking the writing and filling the brief…';
    $('sourceStatus').classList.remove('bad');
    $('sourceStatus').classList.add('ready');

    const projectId = SOURCE_MODE === 'project' ? Number($('project').value || 0) : 0;
    const sourceText = SOURCE_MODE === 'paste' ? $('sourceText').value.trim() : '';
    const fileData = SOURCE_MODE === 'upload' && FILE ? await file64(FILE) : '';
    const fileName = SOURCE_MODE === 'upload' && FILE ? FILE.name : '';

    const prepareRequestId = `WEB-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const started = await startIntakePreparation({
      prepare_request_id: prepareRequestId,
      source_mode: SOURCE_MODE,
      source_text: sourceText,
      file_name: fileName,
      file_data_base64: fileData,
      project_id: projectId,
      instruction: $('task').value.trim(),
      also_pdf: true,
    });
    if (!started.prepare_job_id) throw Error('Agape did not return a source-preparation job.');
    const data = await waitForIntakePreparation(started.prepare_job_id);

    INTAKE = data.intake || data;
    renderIntake(INTAKE);
    await loadProjects();
    if ($('workspaceTree')) await loadWorkspace();
    $('intakeCard').classList.remove('hidden');
    $('progressCard').classList.add('hidden');
    setStep(2);
    $('intakeCard').scrollIntoView({behavior:'smooth'});
  } catch (error) {
    const message = error?.network
      ? 'Agape could not reconnect to the local server. Restart Agape, then press Prepare with AI again.'
      : (error.message || error);
    $('sourceStatus').textContent = `Agape could not prepare this source: ${message}`;
    $('sourceStatus').classList.remove('ready');
    $('sourceStatus').classList.add('bad');
    console.error(error);
  } finally {
    setPrepareBusy(false);
  }
};

function fieldValue(row) {
  return typeof row === 'object' && row !== null ? String(row.value ?? '') : String(row ?? '');
}
function fieldLabel(key) {
  return key.replaceAll('_',' ').replace(/\b\w/g, ch => ch.toUpperCase());
}
function humanFieldReason(key, row, priority=false) {
  const raw = row && typeof row === 'object' ? String(row.reason || row.status || '') : '';
  const low = raw.toLowerCase();
  const value = fieldValue(row).trim().toLowerCase();
  if (value === 'none' || low.includes('no reliable or relevant value') || low.includes('could not responsibly infer')) {
    return priority ? 'Add this if it is known and relevant. Agape will not invent it.' : 'Not established from the current source yet.';
  }
  return raw;
}
function fieldMarkup(key, row, priority=false) {
  const reason = humanFieldReason(key,row,priority);
  const value = fieldValue(row).trim().toLowerCase() === 'none' ? '' : fieldValue(row);
  return `<label class="${priority ? 'priority-field' : ''}"><span>${esc(fieldLabel(key))}</span><textarea data-field="${esc(key)}" rows="3" spellcheck="true" autocapitalize="sentences" placeholder="${priority ? 'Add if known' : ''}">${esc(value)}</textarea>${reason ? `<small>${esc(reason)}</small>` : ''}</label>`;
}

function writingCheckMarkup(report) {
  if (!report || !report.ok) return '';
  const safe = Number(report.safe_corrections_applied || 0);
  const spelling = Number(report.spelling_issue_count || 0);
  const grammar = Number(report.grammar_issue_count || 0);
  const lineBreaks = Number(report.escaped_line_breaks_normalized || 0);
  const suggestions = [...(report.spelling_suggestions || []), ...(report.grammar_suggestions || [])].slice(0,12);
  let summary = safe || spelling || grammar
    ? `Writing check complete · ${safe} safe correction${safe===1?'':'s'} applied · ${spelling} spelling suggestion${spelling===1?'':'s'} · ${grammar} grammar flag${grammar===1?'':'s'}.`
    : 'Writing check complete — no obvious spelling or grammar problems were found.';
  if (lineBreaks) summary += ` ${lineBreaks} escaped line-break marker${lineBreaks===1?' was':'s were'} normalised before checking.`;
  const structuredSkipped = Number(report.structured_lines_skipped||0);
  if (structuredSkipped) summary += ` ${structuredSkipped} technical/structured line${structuredSkipped===1?' was':'s were'} excluded from prose suggestions.`;
  if (!report.dictionary_available) summary += ' Dictionary spelling suggestions are unavailable, but mechanical grammar checks still ran.';
  if (!suggestions.length) return `<b>${esc(summary)}</b>`;
  return `<b>${esc(summary)}</b><details><summary>See writing suggestions</summary><ul>${suggestions.map(x => `<li>${esc(x.word || x.text || x.issue || 'Writing issue')} → ${esc(x.suggestion || '')}</li>`).join('')}</ul></details>`;
}

function renderIntake(intake) {
  INTAKE = intake;
  const fields = intake.ai_fill?.fields || {};
  const entries = Object.entries(fields);
  const questions = intake.unresolved_questions || [];
  const opportunities = Array.isArray(intake.extra_information_opportunities) ? intake.extra_information_opportunities : [];
  const researchable = new Set(opportunities.map(q => String(q.field_id || '')));
  const userQuestions = questions.filter(q => !Boolean(q.researchable) && !researchable.has(String(q.field_id || '')));
  const unresolved = new Set(userQuestions.map(q => String(q.field_id || '')));
  const allUnresolved = new Set(questions.map(q => String(q.field_id || '')));

  const established = Number.isFinite(Number(intake.established_count))
    ? Number(intake.established_count)
    : entries.filter(([,row]) => {
        const value = fieldValue(row).trim();
        const status = String(row?.status || '').toLowerCase();
        return value && value.toLowerCase() !== 'none' && status !== 'unresolved';
      }).length;
  $('intakeSummary').textContent = `${established} established · ${userQuestions.length} need your input${opportunities.length ? ` · ${opportunities.length} public research opportunit${opportunities.length===1?'y':'ies'}` : ''}`;
  $('intakeReady').textContent = userQuestions.length ? 'Review' : 'Ready';

  const writing = intake.upload?.writing_check || intake.writing_check || null;
  const writingHtml = writingCheckMarkup(writing);
  $('writingCheck').classList.toggle('hidden', !writingHtml);
  $('writingCheck').innerHTML = writingHtml;

  const missingDetails = $('missingDetails');
  const missingWasOpen = Boolean(missingDetails?.open);
  missingDetails.classList.toggle('hidden', !userQuestions.length);
  $('missingSummary').textContent = `${userQuestions.length} item${userQuestions.length===1?'':'s'} need your input`;
  $('missingBox').innerHTML = userQuestions.length
    ? `<b>${userQuestions.length} item${userQuestions.length===1?'':'s'} need information from you.</b><br><span class="muted">These are private, user-specific or not safely discoverable from public sources. Agape will not invent them.</span>`
    : '';
  if (!userQuestions.length) missingDetails.open = false; else missingDetails.open = missingWasOpen;

  const extra = $('extraInfoDetails');
  const currentExtraIntakeId = String(intake.id || '');
  const sameExtraIntake = currentExtraIntakeId && currentExtraIntakeId === LAST_EXTRA_INTAKE_ID;
  const extraWasOpen = sameExtraIntake && Boolean(extra?.open);
  extra.classList.toggle('hidden', !opportunities.length);
  $('extraInfoSummary').textContent = 'Extra information could be gathered';
  $('extraInfoCount').textContent = String(opportunities.length);
  $('extraInfoList').innerHTML = opportunities.map(x => {
    const raw=String(x.reason || '');
    const reason=(raw.toLowerCase().includes('no reliable or relevant value') || raw.toLowerCase().includes('could not responsibly infer'))
      ? 'Agape has not confirmed this from the saved source yet. Public research may strengthen it.'
      : (raw || x.question || 'Public research could strengthen this project.');
    return `<div class="research-opportunity"><b>${esc(x.label || 'Public information')}</b><br><span class="muted">${esc(reason)}</span></div>`;
  }).join('');
  if (!opportunities.length) { extra.open=false; $('researchProgress').classList.add('hidden'); } else { extra.open=extraWasOpen; }
  LAST_EXTRA_INTAKE_ID = currentExtraIntakeId;

  const priorityRows = entries.filter(([key]) => unresolved.has(String(key)));
  $('priorityFields').classList.toggle('hidden', !priorityRows.length);
  $('priorityFields').innerHTML = priorityRows.map(([key,row]) => fieldMarkup(key,row,true)).join('');

  const resolvedRows = entries.filter(([key]) => !allUnresolved.has(String(key)));
  $('formFields').innerHTML = resolvedRows.map(([key,row]) => fieldMarkup(key,row,false)).join('');
  $('allDetails').classList.toggle('hidden', !resolvedRows.length);
  if (selectedExperience !== 'advanced') $('allDetails').open = false;

  applyExperienceUI();
}

function collectAnswers() {
  const answers = {};
  document.querySelectorAll('[data-field]').forEach(node => {
    if (node.value.trim()) answers[node.dataset.field] = node.value.trim();
  });
  return answers;
}

async function saveIntakeEdits() {
  if (!INTAKE?.id) return INTAKE;
  const data = await api(`/api/intake/${encodeURIComponent(INTAKE.id)}/answers`, {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({answers:collectAnswers()}),
  });
  INTAKE = data.intake || data;
  return INTAKE;
}

$('findMissing').onclick = async () => {
  try {
    $('findMissing').disabled = true;
    $('findMissing').textContent = 'Researching…';
    startResearchProgress();
    await saveIntakeEdits();
    researchProgressPaint(Math.max(25, RESEARCH_PROGRESS.percent), 'Searching public information', 'Agape is checking public information for the unresolved fields.');
    const data = await api(`/api/intake/${encodeURIComponent(INTAKE.id)}/improve`, {method:'POST'});
    renderIntake(data.intake || data);
    finishResearchProgress(true, 'Research complete. Safe public information has been applied to the brief.');
    toast('Public information gathered');
  } catch (error) {
    finishResearchProgress(false, `Research stopped: ${error.message || error}`);
    $('missingBox').innerHTML = `<b>Agape could not complete the research pass.</b><br>${esc(error.message || error)}`;
  } finally {
    $('findMissing').disabled = false;
    $('findMissing').textContent = 'Gather public information';
  }
};

$('reviseForm').onclick = async () => {
  const instruction = $('formRevision').value.trim();
  if (!instruction) return toast('Type the change you want first');
  try {
    $('reviseForm').disabled = true;
    $('reviseForm').textContent = 'Applying…';
    await saveIntakeEdits();
    const data = await api(`/api/intake/${encodeURIComponent(INTAKE.id)}/revise`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({instruction}),
    });
    renderIntake(data.intake || data);
    $('formRevision').value = '';
    if ($('briefChangeDetails')) $('briefChangeDetails').open = false;
    toast('Brief updated');
  } catch (error) {
    showError(error);
  } finally {
    $('reviseForm').disabled = false;
    $('reviseForm').textContent = 'Apply change';
  }
};

$('createDocument').onclick = async () => {
  try {
    if (!INTAKE) throw Error('Prepare the source with AI first.');
    $('createDocument').disabled = true;
    $('createDocument').textContent = 'Starting…';
    await saveIntakeEdits();
    setStep(3);
    working(QUALITY === 'gold' ? 'Creating Gold Standard result…' : 'Creating validated result…', 20);
    const payload = {
      task: $('task').value.trim() || 'Create the completed document from this brief.',
      project_id: Number(INTAKE.project_id || 0),
      intake_id: INTAKE.id,
      file_name: 'prepared-intake.txt',
      quality: QUALITY,
      reviewer_count: Number($('reviewerCount').value || 3),
      also_pdf: true,
      coding: {
        model_mode: $('projectCodingModel')?.value || SETUP.settings?.coding_model_mode || 'auto-coding',
        agent: $('projectCodingAgent')?.value || SETUP.settings?.coding_agent || 'auto',
        manager: $('projectCodeManager')?.value || SETUP.settings?.code_manager || 'agape',
      },
    };
    const data = await api('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    $('tech').textContent = JSON.stringify(data,null,2);
    if (data.job_id) {
      CURRENT_JOB = data.job_id;
      await poll(data.job_id);
    } else if (data.result) {
      finishResult(data.result, '');
    } else {
      throw Error('Agape did not return a job or result.');
    }
  } catch (error) {
    showError(error);
  } finally {
    $('createDocument').disabled = false;
    $('createDocument').textContent = 'Create result';
  }
};

function clampProgress(value, max=100) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.min(max, n)) : 0;
}

function setProgress(value, stage='Working') {
  const before = PROGRESS.last;
  const next = Math.max(PROGRESS.last, clampProgress(value));
  PROGRESS.last = Math.round(next * 10) / 10;
  if (PROGRESS.last > before + 0.01) PROGRESS.lastChangedAt = Date.now();
  if (stage) PROGRESS.stage = stage;
  $('progressBar').style.width = `${PROGRESS.last}%`;
  if ($('progressPercent')) $('progressPercent').textContent = `${Math.round(PROGRESS.last)}%`;
  if ($('progressStage')) $('progressStage').textContent = PROGRESS.stage || 'Working';
  return PROGRESS.last;
}

function resetProgress(percent=0, stage='Starting') {
  PROGRESS = {jobId:'', last:0, stage:'', stageChecks:0, lastChangedAt:Date.now()};
  setProgress(percent, stage);
}

function stageBand(job) {
  const detail = String(job.message || '').toLowerCase();
  const text = `${job.stage || ''} ${detail}`.toLowerCase();
  if (/complete|completed|success|done|document ready/.test(text)) return [100,100,'Finished'];
  // Prefer the worker's concrete activity over the broad parent stage name.
  // This prevents impossible combinations such as "Planning · 94%".
  if (/reading project brief/.test(detail)) return [20,27,'Reading brief'];
  if (/planning document structure/.test(detail)) return [22,34,'Planning'];
  if (/starting ai draft|ai drafting|ai draft|specialist ai|lead editor/.test(detail)) return [33,62,'Drafting'];
  if (/gathering research|research ready/.test(detail)) return [28,43,'Researching'];
  if (/validat|repair/.test(detail)) return [46,82,'Validating'];
  if (/building the document|primary document ready/.test(detail)) return [53,92,'Building document'];
  if (/creating pdf|pdf copy/.test(detail)) return [57,97,'Creating PDF'];
  if (/saving document history|final checks/.test(detail)) return [58,99,'Finalising'];
  if (/final/.test(text)) return [88,95,'Finalising'];
  if (/gold|review|lead/.test(text)) return [65,89,'Reviewing'];
  if (/repair/.test(text)) return [58,82,'Repairing'];
  if (/document creation|creating|draft|writer/.test(text)) return [20,65,'Creating'];
  if (/validat/.test(text)) return [82,99,'Validating'];
  if (/work|project loop|running/.test(text)) return [20,92,'Working'];
  if (/prepar|route|load|source/.test(text)) return [8,22,'Preparing'];
  return [3,18,'Queued'];
}

function jobProgress(job) {
  const state = String(job.status || job.state || '').toUpperCase();
  if (['PASS','COMPLETE','COMPLETED','SUCCESS','DONE'].includes(state)) return {value:100, stage:'Finished'};
  const reported = Number(job.progress ?? job.percent ?? job.progress_percent);
  const [floor, ceiling, label] = stageBand(job);
  if (Number.isFinite(reported)) {
    const stageCeiling = ceiling >= 100 ? 100 : Math.max(floor, ceiling - 0.1);
    return {value:Math.max(floor, Math.min(stageCeiling, reported)), stage:label};
  }
  const key = `${label}:${job.stage || ''}`;
  if (PROGRESS.stage !== key) PROGRESS.stageChecks = 0;
  PROGRESS.stageChecks += 1;
  const creep = Math.min(ceiling - 1, Math.max(floor, PROGRESS.last + Math.max(0.15, (ceiling-floor)/80)));
  return {value:creep, stage:label};
}

function working(text, percent) {
  $('progressCard').classList.remove('hidden');
  $('progressBar').classList.remove('failed');
  $('progressTitle').textContent = 'Working…';
  $('progressText').textContent = text;
  beginResultPreparation(text, percent);
  resetProgress(percent, 'Starting');
  if ($('technicalDetails')) $('technicalDetails').classList.toggle('hidden', selectedExperience === 'basic');
  $('progressCard').scrollIntoView({behavior:'smooth'});
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function jobStatus(id) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try { return await api(`/api/work/${encodeURIComponent(id)}`, {signal:controller.signal}); }
  finally { clearTimeout(timer); }
}

async function poll(id) {
  let checks = 0;
  let errors = 0;
  const started = Date.now();
  CURRENT_JOB = id;
  while (CURRENT_JOB === id) {
    try {
      const wrapper = await jobStatus(id);
      const job = wrapper.job || wrapper;
      checks += 1;
      errors = 0;
      $('tech').textContent = JSON.stringify(job,null,2);
      const state = String(job.status || job.state || '').toUpperCase();
      const elapsed = Math.max(1, Math.round((Date.now()-started)/1000));
      const p = jobProgress(job);
      PROGRESS.jobId = id;
      setProgress(p.value, p.stage);
      const unchangedFor = Math.max(0, Math.round((Date.now()-(PROGRESS.lastChangedAt || started))/1000));
      const baseMessage = job.message || `Agape is working · ${state || 'IN PROGRESS'}`;
      updateResultPreparation(id, p.value, p.stage, baseMessage);
      $('progressText').textContent = unchangedFor >= 20
        ? `${baseMessage} · still active · ${elapsed}s`
        : `${baseMessage} · ${elapsed}s`;
      if (['PASS','COMPLETE','COMPLETED','SUCCESS','DONE'].includes(state)) return finishResult(job.result || job, id);
      if (['FAIL','FAILED','ERROR','BLOCKED','ACTION_REQUIRED'].includes(state)) return showError(Error(job.error || job.message || state));
      await sleep(checks < 10 ? 1500 : checks < 60 ? 2500 : 4000);
    } catch (error) {
      errors += 1;
      const elapsed = Math.max(1, Math.round((Date.now()-started)/1000));
      $('tech').textContent = `Status check ${errors} failed: ${error?.message || error}`;
      $('progressText').textContent = `Agape is still working. Reconnecting to job status… · ${elapsed}s`;
      if (errors >= 60) return showError(Error(`Agape could not reconnect to the running job. The job may still be running; open Results after restarting Agape. Last error: ${error?.message || error}`));
      await sleep(Math.min(10000, 1500 + errors*750));
    }
  }
}

function finishResult(result, jobId='') {
  CURRENT_JOB = jobId || CURRENT_JOB;
  setStep(3);
  $('progressCard').classList.remove('hidden');
  $('progressTitle').textContent = 'Finished';
  $('progressText').textContent = 'Agape completed the work.';
  $('progressBar').classList.remove('failed');
  setProgress(100, 'Finished');
  const files = registerResultFiles(result, jobId);
  let html = '<div class="notice okbox"><b>Result ready.</b> Previous versions are preserved.</div>';
  files.forEach((file,index) => {
    const name = typeof file === 'string' ? file : (file.name || file.file || file.path || `File ${index+1}`);
    html += `<div class="result-file"><span>${esc(String(name).split(/[\\/]/).pop())}</span>${jobId ? `<button type="button" class="secondary" data-result-download="${index}">Download</button>` : ''}</div>`;
  });
  if (jobId) {
    const qualityChoice = selectedExperience === 'basic' ? '' : `<select id="revisionQuality"><option value="standard" ${QUALITY==='standard'?'selected':''}>Create Now</option><option value="gold" ${QUALITY==='gold'?'selected':''}>Gold Standard</option></select>`;
    html += `<div class="ai-change"><h3>Change this result with AI</h3><p class="muted">Agape keeps this version and creates a new one.</p><textarea id="resultRevision" rows="3" spellcheck="true" autocapitalize="sentences" placeholder="Example: Shorten the executive summary and make the tone suitable for a bank."></textarea><div class="row"><button id="reviseResult" class="primary">Create revised version</button>${qualityChoice}</div></div>`;
  }
  $('result').innerHTML = html;
  document.querySelectorAll('[data-result-download]').forEach(button => button.onclick = () => downloadManagedFile(jobId, Number(button.dataset.resultDownload)));
  if (jobId) $('reviseResult').onclick = () => reviseResult(jobId);
  if ($('technicalDetails')) $('technicalDetails').classList.toggle('hidden', selectedExperience === 'basic');
  loadRecent().catch(() => {});
  if ($('workspaceTree')) loadWorkspace().catch(() => {});
  loadProjects().catch(() => {});
}

async function reviseResult(jobId) {
  const instruction = $('resultRevision').value.trim();
  if (!instruction) return toast('Type the changes you want first');
  try {
    setStep(3);
    working('Creating a new version from your instruction…',20);
    const quality = $('revisionQuality')?.value || QUALITY;
    const data = await api(`/api/work/${encodeURIComponent(jobId)}/revise`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({instruction,quality_mode:quality})});
    if (!data.job_id) throw Error('Revision job did not start.');
    CURRENT_JOB = data.job_id;
    await poll(data.job_id);
  } catch (error) { showError(error); }
}

function showError(error) {
  setStep(3);
  $('progressCard').classList.remove('hidden');
  $('progressTitle').textContent = 'Agape needs attention';
  $('progressText').textContent = String(error.message || error);
  $('progressBar').classList.add('failed');
  setProgress(100, 'Stopped');
  DOWNLOAD_MANAGER.jobId = CURRENT_JOB || DOWNLOAD_MANAGER.jobId;
  DOWNLOAD_MANAGER.preparation = {...DOWNLOAD_MANAGER.preparation,status:'failed',progress:100,stage:'Stopped',eta:'',error:String(error.message || error)};
  renderDownloadManager();
  $('tech').textContent = String(error.stack || error);
  $('technicalDetails').classList.remove('hidden');
  console.error(error);
}

function toast(text) {
  $('status').textContent = text;
  setTimeout(() => $('status').textContent = 'Ready', 1800);
}

async function resumeRecentJob(id) {
  if (!id) return;
  page('home');
  setStep(3);
  working('Checking the saved Agape job after restart…',25);
  CURRENT_JOB = id;
  await poll(id);
}

async function loadRecent() {
  const data = await api('/api/recent').catch(() => ({items:[]}));
  const rows = data.items || [];
  $('recent').innerHTML = rows.map(item => {
    const jobId = String(item.external_job_id || '');
    return `<div class="result-file"><span><b>${esc(item.title || item.route)}</b><br><small>${esc(item.created_at)} · ${esc(canonicalStatusLabel(item))}</small></span>${jobId ? `<button data-resume-job="${esc(jobId)}">Check / resume →</button>` : `<span>${esc(item.route)}</span>`}</div>`;
  }).join('') || '<p class="muted">No work yet.</p>';
  document.querySelectorAll('[data-resume-job]').forEach(button => button.onclick = () => resumeRecentJob(button.dataset.resumeJob));
}



// V5.0 Workspace -----------------------------------------------------------
const TODO_KEY = 'agape.workspace.todos.v1';
let WORKSPACE_DATA = {projects:[],jobs:[]};

function readTodos() {
  try {
    const rows = JSON.parse(localStorage.getItem(TODO_KEY) || '[]');
    return Array.isArray(rows) ? rows : [];
  } catch { return []; }
}
function writeTodos(rows) { localStorage.setItem(TODO_KEY, JSON.stringify(rows)); }
function renderTodos() {
  if (!$('todoList')) return;
  const rows = readTodos();
  $('todoCount').textContent = String(rows.filter(x => !x.done).length);
  $('todoList').innerHTML = rows.length ? rows.map(row => `<div class="todo-row ${row.done?'done':''}" data-todo="${esc(row.id)}"><input type="checkbox" ${row.done?'checked':''} aria-label="Mark to-do complete"><span class="todo-text">${esc(row.text)}</span><button class="todo-delete" title="Delete">×</button></div>`).join('') : '<p class="muted">Nothing waiting. Add a to-do when you want Agape to remember the next job.</p>';
  document.querySelectorAll('[data-todo]').forEach(node => {
    node.querySelector('input').onchange = event => {
      const next = readTodos().map(x => x.id === node.dataset.todo ? {...x,done:event.target.checked} : x);
      writeTodos(next); renderTodos();
    };
    node.querySelector('.todo-delete').onclick = () => { writeTodos(readTodos().filter(x => x.id !== node.dataset.todo)); renderTodos(); };
  });
  bindWorkspaceContextMenus();
}
function addTodo(text) {
  const value = String(text || '').trim(); if (!value) return;
  const rows = readTodos();
  rows.unshift({id:String(Date.now())+'-'+Math.random().toString(16).slice(2),text:value,done:false,created_at:new Date().toISOString()});
  writeTodos(rows); renderTodos();
}
function workspaceOpen(kind,id) {
  const preview = $('workspacePreview'); const tab = $('workspaceTab');
  if (kind === 'project') {
    const item = WORKSPACE_DATA.projects.find(x => String(x.id) === String(id)); if (!item) return;
    tab.textContent = item.name || 'Project';
    preview.innerHTML = `<div class="workspace-preview-card"><div class="step-label">Project</div><h2>${esc(item.name || 'Untitled project')}</h2><p>${esc(item.goal || item.description || 'Saved Agape project')}</p><dl><dt>Project ID</dt><dd>${esc(item.id)}</dd><dt>Status</dt><dd>${esc(canonicalStatusLabel(item))}</dd></dl><div class="row"><button class="primary" id="workspaceUseProject">Use as source</button><button id="workspaceProjectTodo">Add to to-do</button></div></div>`;
    $('workspaceUseProject').onclick = () => { $('project').value = String(item.id); setSourceMode('project'); page('home'); setStep(1); };
    $('workspaceProjectTodo').onclick = () => addTodo(`Continue project: ${item.name || 'Untitled project'}`);
  } else {
    const item = WORKSPACE_DATA.jobs.find(x => String(x.external_job_id || x.id || '') === String(id)); if (!item) return;
    const title = item.title || item.route || 'Result'; tab.textContent = title;
    preview.innerHTML = `<div class="workspace-preview-card"><div class="step-label">Result / job</div><h2>${esc(title)}</h2><dl><dt>Status</dt><dd>${esc(canonicalStatusLabel(item))}</dd><dt>Created</dt><dd>${esc(item.created_at || '')}</dd><dt>Route</dt><dd>${esc(item.route || '')}</dd></dl>${item.external_job_id ? `<button class="primary" id="workspaceResumeJob">Check / resume job</button>`:''}</div>`;
    if ($('workspaceResumeJob')) $('workspaceResumeJob').onclick = () => resumeRecentJob(item.external_job_id);
  }
  document.querySelectorAll('.tree-file').forEach(x => x.classList.toggle('active', x.dataset.kind===kind && String(x.dataset.id)===String(id)));
}
function renderWorkspaceTree() {
  const projects = WORKSPACE_DATA.projects || []; const jobs = WORKSPACE_DATA.jobs || [];
  $('workspaceTree').innerHTML = `<details class="tree-folder" open><summary>Projects <span class="muted">(${projects.length})</span></summary><div class="tree-children">${projects.map(p => `<button class="tree-file" data-kind="project" data-id="${esc(p.id)}"><span class="file-icon">▣</span>${esc(p.name || 'Untitled project')}</button>`).join('') || '<p class="muted">No projects</p>'}</div></details><details class="tree-folder" open><summary>Results <span class="muted">(${jobs.length})</span></summary><div class="tree-children">${jobs.map(j => {const id=j.external_job_id||j.id||'';return `<button class="tree-file" data-kind="job" data-id="${esc(id)}"><span class="file-icon">▤</span>${esc(j.title || j.route || 'Result')}</button>`}).join('') || '<p class="muted">No results</p>'}</div></details>`;
  document.querySelectorAll('.tree-file').forEach(button => button.onclick = () => workspaceOpen(button.dataset.kind,button.dataset.id));
  bindWorkspaceContextMenus();
}
function renderWorkspaceJobs() {
  const jobs = WORKSPACE_DATA.jobs || []; $('jobCount').textContent = String(jobs.length);
  $('workspaceJobs').innerHTML = jobs.length ? jobs.slice(0,20).map(j => { const id=j.external_job_id||j.id||''; return `<div class="job-row" data-workspace-job="${esc(id)}"><b>${esc(j.title || j.route || 'Agape job')}</b><small>${esc(j.created_at || '')}</small><br><span class="job-status ${esc(String(j.status||'').toLowerCase())}">${esc(canonicalStatusLabel(j))}</span></div>`; }).join('') : '<p class="muted">No recent jobs.</p>';
  bindWorkspaceContextMenus();
}
async function loadWorkspace() {
  if (!$('workspaceTree')) return;
  const [p,r] = await Promise.all([api('/api/projects').catch(()=>({projects:[]})),api('/api/recent').catch(()=>({items:[]}))]);
  WORKSPACE_DATA = {projects:p.projects || [],jobs:r.items || []};
  renderWorkspaceTree(); renderWorkspaceJobs(); renderTodos();
}
if ($('workspaceRefresh')) $('workspaceRefresh').onclick = loadWorkspace;
if ($('workspaceCollapseAll')) $('workspaceCollapseAll').onclick = () => document.querySelectorAll('#workspaceTree details').forEach(x => x.open=false);
if ($('workspaceAddTodo')) $('workspaceAddTodo').onclick = () => { $('todoForm').classList.remove('hidden'); $('todoInput').focus(); };
if ($('todoCancel')) $('todoCancel').onclick = () => { $('todoForm').classList.add('hidden'); $('todoInput').value=''; };
if ($('todoForm')) $('todoForm').onsubmit = event => { event.preventDefault(); addTodo($('todoInput').value); $('todoInput').value=''; $('todoForm').classList.add('hidden'); };


// V5.1 Context menus -------------------------------------------------------
function contextMenuHide() {
  const menu = $('workspaceContextMenu');
  if (menu) { menu.classList.add('hidden'); menu.innerHTML=''; }
}
function contextMenuShow(event, title, actions) {
  const menu = $('workspaceContextMenu'); if (!menu) return;
  event.preventDefault(); event.stopPropagation();
  const buttons = actions.filter(Boolean).map((a,index) => a.separator ? '<div class="context-separator"></div>' : `<button type="button" role="menuitem" data-context-index="${index}" class="${a.danger?'context-danger':''}">${esc(a.label)}</button>`).join('');
  menu.innerHTML = `<div class="context-label">${esc(title || 'Options')}</div>${buttons}`;
  menu.classList.remove('hidden');
  const pad=8, width=Math.min(300,Math.max(210,menu.offsetWidth||210)), height=menu.offsetHeight||250;
  menu.style.left=Math.max(pad,Math.min(event.clientX,window.innerWidth-width-pad))+'px';
  menu.style.top=Math.max(pad,Math.min(event.clientY,window.innerHeight-height-pad))+'px';
  menu.querySelectorAll('[data-context-index]').forEach(button => button.onclick=async()=>{
    const action=actions[Number(button.dataset.contextIndex)]; contextMenuHide();
    try { await action.run(); } catch (error) { console.error('CONTEXT_ACTION_FAILED',error); }
  });
  const first=menu.querySelector('button'); if(first) first.focus();
}
async function copyWorkspaceText(text) {
  const value=String(text||'');
  if(navigator.clipboard && navigator.clipboard.writeText) await navigator.clipboard.writeText(value);
}
function projectContextActions(id) {
  const item=WORKSPACE_DATA.projects.find(x=>String(x.id)===String(id)); if(!item) return [];
  return [
    {label:'Open',run:()=>workspaceOpen('project',id)},
    {label:'Use as source',run:()=>{ $('project').value=String(item.id); setSourceMode('project'); page('home'); setStep(1); }},
    {label:'Add to to-do',run:()=>addTodo(`Continue project: ${item.name||'Untitled project'}`)},
    {separator:true},
    {label:'Copy project name',run:()=>copyWorkspaceText(item.name||'Untitled project')},
    {label:'Copy project ID',run:()=>copyWorkspaceText(item.id)}
  ];
}
function jobContextActions(id) {
  const item=WORKSPACE_DATA.jobs.find(x=>String(x.external_job_id||x.id||'')===String(id)); if(!item) return [];
  const title=item.title||item.route||'Agape job';
  return [
    {label:'Open details',run:()=>workspaceOpen('job',id)},
    item.external_job_id ? {label:'Check / resume job',run:()=>resumeRecentJob(item.external_job_id)} : null,
    {label:'Add to to-do',run:()=>addTodo(`Check job: ${title}`)},
    {separator:true},
    {label:'Copy job name',run:()=>copyWorkspaceText(title)},
    {label:'Copy job ID',run:()=>copyWorkspaceText(item.external_job_id||item.id||'')}
  ];
}
function todoContextActions(id) {
  const item=readTodos().find(x=>String(x.id)===String(id)); if(!item) return [];
  return [
    {label:item.done?'Mark as not done':'Mark complete',run:()=>{ writeTodos(readTodos().map(x=>x.id===id?{...x,done:!x.done}:x)); renderTodos(); }},
    {label:'Edit',run:()=>{ const next=window.prompt('Edit to-do',item.text); if(next!==null && String(next).trim()){ writeTodos(readTodos().map(x=>x.id===id?{...x,text:String(next).trim()}:x)); renderTodos(); }}},
    {label:'Copy text',run:()=>copyWorkspaceText(item.text)},
    {separator:true},
    {label:'Delete',danger:true,run:()=>{ writeTodos(readTodos().filter(x=>x.id!==id)); renderTodos(); }}
  ];
}
function bindWorkspaceContextMenus() {
  document.querySelectorAll('#workspaceTree .tree-file').forEach(node=>node.oncontextmenu=event=>contextMenuShow(event,node.dataset.kind==='project'?'Project options':'Result options',node.dataset.kind==='project'?projectContextActions(node.dataset.id):jobContextActions(node.dataset.id)));
  document.querySelectorAll('#todoList [data-todo]').forEach(node=>node.oncontextmenu=event=>contextMenuShow(event,'To-do options',todoContextActions(node.dataset.todo)));
  document.querySelectorAll('#workspaceJobs [data-workspace-job]').forEach(node=>node.oncontextmenu=event=>contextMenuShow(event,'Job options',jobContextActions(node.dataset.workspaceJob)));
}
if ($('workspaceTree')) $('workspaceTree').oncontextmenu = event => { if(event.target===$('workspaceTree')) contextMenuShow(event,'Workspace',[{label:'Refresh',run:loadWorkspace},{label:'Add to-do',run:()=>{$('todoForm').classList.remove('hidden');$('todoInput').focus();}},{label:'Collapse folders',run:()=>document.querySelectorAll('#workspaceTree details').forEach(x=>x.open=false)}]); };
document.addEventListener('click',event=>{ const menu=$('workspaceContextMenu'); if(menu && !menu.contains(event.target)) contextMenuHide(); });
document.addEventListener('keydown',event=>{ if(event.key==='Escape') contextMenuHide(); });
window.addEventListener('blur',contextMenuHide);

function renderSetupRecommendation() {
  const rec = SETUP.plan?.recommended || {};
  $('recommendation').textContent = `Recommended: ${(rec.recommended_experience || 'basic').replace(/^./,x=>x.toUpperCase())}. ${(rec.notes || []).join(' ')}`;
  document.querySelectorAll('.profile').forEach(node => node.classList.toggle('selected', node.dataset.exp === selectedExperience));
}
document.querySelectorAll('.profile').forEach(button => button.onclick = () => {
  selectedExperience = button.dataset.exp;
  document.querySelectorAll('.profile').forEach(node => node.classList.toggle('selected', node === button));
});

function setupStep(n) {
  [1,2,3,4].forEach(x => $(`setup${x}`).classList.toggle('hidden',x!==n));
  document.querySelectorAll('.setup-progress span').forEach((node,index) => node.classList.toggle('on',index<n));
}
$('setupNext').onclick = async () => {
  const data = await api(`/api/setup/plan?experience=${encodeURIComponent(selectedExperience)}`);
  SYSTEM = data.system;
  renderSetupPlan(data.plan);
  setupStep(2);
};
function renderSetupPlan(plan) {
  $('systemSummary').innerHTML = `<b>${esc(SYSTEM.os_name || SYSTEM.platform || 'Computer')}</b> · ${esc(SYSTEM.ram_gb || '?')} GB RAM<br><span class="muted">${esc((plan.recommended?.notes || []).join(' '))}</span>`;
  $('setupCaps').innerHTML = (plan.capabilities || []).map(cap => `<label class="setup-cap"><input type="checkbox" data-cap="${esc(cap.id)}" ${cap.required||cap.recommended_now?'checked':''} ${cap.required?'disabled':''}><span><b>${esc(cap.name)}</b><br><small>${esc(cap.reason)}</small></span></label>`).join('');
}
$('setupBack').onclick = () => setupStep(1);
$('setupApply').onclick = async () => {
  const caps = [...document.querySelectorAll('[data-cap]:checked')].map(node => node.dataset.cap);
  const data = await api('/api/setup/apply', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({experience:selectedExperience,selected_capabilities:caps})});
  SETUP.settings = data.settings;
  applyExperienceUI();
  await loadApiKeys(true);
  setupStep(3);
};
$('finishSetup').onclick = () => { $('setup').classList.add('hidden'); loadSettings(); };

async function loadSettings() {
  const data = await api('/api/setup/status');
  SETUP = data;
  SYSTEM = data.system;
  selectedExperience = data.settings.experience;
  QUALITY = data.settings.quality;
  $('settingExperience').value = data.settings.experience;
  $('settingQuality').value = data.settings.quality;
  $('settingRouter').value = data.settings.router;
  $('settingCodingModel').value = data.settings.coding_model_mode || 'auto-coding';
  $('settingCodingAgent').value = data.settings.coding_agent || 'auto';
  $('settingCodeManager').value = data.settings.code_manager || 'agape';
  if ($('projectCodingModel')) $('projectCodingModel').value = data.settings.coding_model_mode || 'auto-coding';
  if ($('projectCodingAgent')) $('projectCodingAgent').value = data.settings.coding_agent || 'auto';
  if ($('projectCodeManager')) $('projectCodeManager').value = data.settings.code_manager || 'agape';
  applyExperienceUI();
  const caps = await api('/api/capabilities');
  renderCapabilities(caps.capabilities || []);
  renderComputer(data.system);
  await loadApprovedInstallers();
  await loadCodingTools();
  await loadQAStatus();
  await loadTestingTools();
  await loadApiKeys(false);
}
function renderCapabilities(rows) {
  $('capabilities').innerHTML = rows.filter(x => !x.hidden).map(cap => `<div class="cap-row"><div><b>${esc(cap.name)}</b> <span class="${cap.ready?'ok':'warn'}">${cap.ready?'Ready':'Available on demand'}</span><br><small>${esc(cap.summary)}</small></div><div class="cap-actions"><label><input type="checkbox" class="capToggle" data-id="${esc(cap.id)}" ${cap.enabled?'checked':''}> enabled</label></div></div>`).join('');
  document.querySelectorAll('.capToggle').forEach(node => node.onchange = saveCaps);
}
async function saveCaps() {
  const enabled = [...document.querySelectorAll('.capToggle:checked')].map(node => node.dataset.id);
  for (const required of ['ai-routing','projects']) if (!enabled.includes(required)) enabled.unshift(required);
  await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled_capabilities:enabled})});
}
function renderComputer(system) {
  $('computer').innerHTML = `<p><b>${esc(system.os_name || system.platform || 'Computer')}</b><br>${esc(system.cpu || '')}<br>RAM: ${esc(system.ram_gb || '?')} GB · Free drive: ${esc(system.free_disk_gb || '?')} GB</p>`;
}
$('saveExperience').onclick = async () => {
  selectedExperience = $('settingExperience').value;
  const plan = await api(`/api/setup/plan?experience=${encodeURIComponent(selectedExperience)}`);
  const caps = (plan.plan.capabilities || []).filter(x => x.required || x.recommended_now).map(x => x.id);
  const data = await api('/api/setup/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({experience:selectedExperience,selected_capabilities:caps})});
  SETUP.settings = data.settings;
  applyExperienceUI();
  toast('Saved');
};
$('saveQuality').onclick = async () => {
  const data = await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quality:$('settingQuality').value})});
  SETUP.settings = data.settings;
  QUALITY = data.settings.quality;
  applyExperienceUI();
  toast('Saved');
};
$('saveRouter').onclick = async () => { await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({router:$('settingRouter').value})}); toast('Saved'); };
$('saveCodingTools').onclick = async () => {
  const patch={coding_model_mode:$('settingCodingModel').value,coding_agent:$('settingCodingAgent').value,code_manager:$('settingCodeManager').value};
  const data=await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)});
  SETUP.settings=data.settings;
  if ($('projectCodingModel')) $('projectCodingModel').value=data.settings.coding_model_mode;
  if ($('projectCodingAgent')) $('projectCodingAgent').value=data.settings.coding_agent;
  if ($('projectCodeManager')) $('projectCodeManager').value=data.settings.code_manager;
  toast('Coding defaults saved');
};
$('refreshServices').onclick = async () => { $('services').textContent = JSON.stringify(await api('/api/services'),null,2); };
$('refreshEvents').onclick = async () => { $('events').textContent = JSON.stringify(await api('/api/events'),null,2); };

async function codingToolAction(tool, action) {
  const button = document.querySelector(`[data-coding-tool="${tool}"][data-coding-action="${action}"]`);
  if (button) button.disabled = true;
  try {
    const data = await api('/api/coding/tools/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool,action})});
    if(data && data.ok===false) throw new Error(data.message || data.error || data.output || 'Coding tool action did not complete');
    toast(data.message || (action==='install'?'Installation completed':'Done'));
    setTimeout(loadCodingTools, 1200);
  } catch (error) {
    toast(error.message || String(error));
  } finally { if (button) button.disabled = false; }
}
async function installCodingSupport(kind, packageName) {
  const button = document.querySelector(`[data-support-package="${packageName}"]`);
  if (button) button.disabled = true;
  try {
    await api('/api/support/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,package:packageName})});
    toast('Installed ' + packageName);
    await loadCodingTools();
  } catch (error) { toast(error.message || String(error)); }
  finally { if (button) button.disabled = false; }
}
async function loadCodingTools() {
  const box=$('codingToolStatus'); if(!box)return;
  try {
    const data=await api('/api/coding/tools');
    const agentMap=Object.fromEntries((data.agents||[]).map(x=>[x.id,x]));
    const mgrMap=Object.fromEntries((data.managers||[]).map(x=>[x.id,x]));
    const card=(title,item,actions)=>`<div class="tool-card"><div><b>${esc(title)}</b> <span class="${item?.ready?'ok':'warn'}">${item?.ready?'Ready':item?.planned?'Planned':'Not installed'}</span><br><small>${esc(item?.summary||'')}</small>${item?.windows_note?`<br><small>${esc(item.windows_note)}</small>`:''}</div><div class="tool-actions">${actions}</div></div>`;
    box.innerHTML =
      card('Aider',agentMap.aider, agentMap.aider?.ready ? '' : '<button data-support-package="aider-chat" onclick="installCodingSupport(\'pip\',\'aider-chat\')">Install Aider</button>') +
      card('OpenHands',agentMap.openhands, agentMap.openhands?.ready ? '<button data-coding-tool="openhands" data-coding-action="open" onclick="codingToolAction(\'openhands\',\'open\')">Open OpenHands</button>' : '<button data-coding-tool="openhands" data-coding-action="install" onclick="codingToolAction(\'openhands\',\'install\')">Install OpenHands</button><button class="secondary" data-coding-tool="openhands" data-coding-action="help" onclick="codingToolAction(\'openhands\',\'help\')">Setup instructions</button>') +
      card('Open Interpreter',agentMap['open-interpreter'], agentMap['open-interpreter']?.ready ? '' : '<button data-coding-tool="open-interpreter" data-coding-action="help" onclick="codingToolAction(\'open-interpreter\',\'help\')">Project / install info</button>') +
      card('Theia Lite',mgrMap['theia-lite'],'<span class="muted">Embedded build option; not downloaded automatically.</span>') +
      card('Theia Full',mgrMap['theia-full'], mgrMap['theia-full']?.ready ? '<button data-coding-tool="theia-full" data-coding-action="open" onclick="codingToolAction(\'theia-full\',\'open\')">Open</button>' : '<button data-coding-tool="theia-full" data-coding-action="download" onclick="codingToolAction(\'theia-full\',\'download\')">Download Theia</button>') +
      card('VS Code',mgrMap.vscode, mgrMap.vscode?.ready ? '<button data-coding-tool="vscode" data-coding-action="open" onclick="codingToolAction(\'vscode\',\'open\')">Open</button>' : '<button data-support-package="vscode" onclick="installCodingSupport(\'winget\',\'vscode\')">Install VS Code</button><button class="secondary" data-coding-tool="vscode" data-coding-action="download" onclick="codingToolAction(\'vscode\',\'download\')">Download page</button>');
  } catch(error) { box.innerHTML=`<p class="bad">Could not check coding tools: ${esc(error.message||error)}</p>`; }
}
if ($('refreshCodingTools')) $('refreshCodingTools').onclick=loadCodingTools;


let API_KEY_PROVIDERS=[];
function renderApiKeyProviderOptions(selectId) {
  const node=$(selectId); if(!node)return;
  const current=node.value;
  node.innerHTML=API_KEY_PROVIDERS.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('');
  if(current && API_KEY_PROVIDERS.some(x=>x.id===current)) node.value=current;
}
async function loadApiKeys(forSetup=false) {
  const target=forSetup?$('setupKeyStatus'):$('apiKeyStatus');
  try {
    const data=await api('/api/keys/status');
    API_KEY_PROVIDERS=data.providers||[];
    renderApiKeyProviderOptions('apiKeyProvider');
    renderApiKeyProviderOptions('setupKeyProvider');
    if(target) target.innerHTML=(API_KEY_PROVIDERS.map(x=>`<div class="tool-card"><div><b>${esc(x.name)}</b> <span class="${x.configured?'ok':'muted'}">${x.configured?'Configured':'Not configured'}</span><br><small>${esc(x.why||'')}</small></div>${!forSetup && x.configured?`<div class="tool-actions"><button class="secondary" data-remove-api-key="${esc(x.id)}">Remove</button></div>`:''}</div>`).join('') || '<span class="muted">No providers available.</span>') + (data.import_file_found?`<p class="notice">API-KEYS.local.json detected and can be imported.</p>`:'');
    if(!forSetup) document.querySelectorAll('[data-remove-api-key]').forEach(btn=>btn.onclick=()=>removeApiKey(btn.dataset.removeApiKey));
    return data;
  } catch(error) { if(target) target.innerHTML=`<span class="bad">Could not check API keys: ${esc(error.message||error)}</span>`; return null; }
}
async function saveOneApiKey(providerId,valueId,statusId) {
  const provider=$(providerId).value, value=$(valueId).value.trim(), target=$(statusId);
  if(!value){ if(target) target.innerHTML='<span class="warn">Paste a key first, or skip and add it later.</span>'; return; }
  try {
    await api('/api/keys/set',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider,value})});
    $(valueId).value='';
    if(target) target.innerHTML='<span class="ok">Key saved. You can add another provider or continue.</span>';
    await loadApiKeys(statusId==='setupKeyStatus');
  } catch(error){ if(target) target.innerHTML=`<span class="bad">${esc(error.message||error)}</span>`; }
}
async function importApiKeys(forSetup=false) {
  const target=forSetup?$('setupKeyStatus'):$('apiKeyStatus');
  try {
    const data=await api('/api/keys/import',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(target) target.innerHTML=`<span class="ok">${esc(data.message||'Imported')}</span>`;
    await loadApiKeys(forSetup);
  } catch(error){ if(target) target.innerHTML=`<span class="warn">${esc(error.message||error)} You can add keys one at a time instead.</span>`; }
}
async function removeApiKey(provider){
  if(!confirm('Remove this saved API key from Agape?'))return;
  await api('/api/keys/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider})});
  toast('API key removed'); await loadApiKeys(false);
}
if($('showApiKey')) $('showApiKey').onchange=()=>{$('apiKeyValue').type=$('showApiKey').checked?'text':'password';};
if($('setupShowKey')) $('setupShowKey').onchange=()=>{$('setupKeyValue').type=$('setupShowKey').checked?'text':'password';};
if($('saveApiKey')) $('saveApiKey').onclick=()=>saveOneApiKey('apiKeyProvider','apiKeyValue','apiKeyStatus');
if($('refreshApiKeys')) $('refreshApiKeys').onclick=()=>loadApiKeys(false);
if($('importApiKeys')) $('importApiKeys').onclick=()=>importApiKeys(false);
if($('setupSaveKey')) $('setupSaveKey').onclick=()=>saveOneApiKey('setupKeyProvider','setupKeyValue','setupKeyStatus');
if($('setupImportKeys')) $('setupImportKeys').onclick=()=>importApiKeys(true);
if($('setupKeysContinue')) $('setupKeysContinue').onclick=()=>setupStep(4);

function qaReportSummary(report) {
  if (!report) return '<span class="muted">No real-click run recorded yet.</span>';
  const status=report.status||'UNKNOWN';
  const cls=status==='PASS'?'ok':'bad';
  const screenshots=(report.screenshots||[]).length;
  return `<b class="${cls}">${esc(status)}</b> · ${esc(report.pass_count||0)} passed · ${esc(report.fail_count||0)} failed · ${screenshots} screenshots<br><small>${esc(report.finished_at||'')}</small>${report.error?`<br><small class="bad">${esc(report.error)}</small>`:''}`;
}
async function loadQAStatus() {
  const browserBox=$('browserQAStatus'), desktopBox=$('desktopQAStatus');
  try {
    const q=await api('/api/qa/browser');
    browserBox.innerHTML=`<b>Playwright:</b> ${q.playwright_python?'<span class="ok">Ready</span>':'<span class="bad">Missing</span>'} · <b>Browser:</b> ${q.browser_executable?'<span class="ok">Ready</span>':'<span class="warn">Needs Chromium</span>'}<br>${qaReportSummary(q.last_report)}`;
    $('installQAChromium').classList.toggle('hidden',!!q.browser_executable);
  } catch(error) { browserBox.innerHTML=`<span class="bad">Browser QA status failed: ${esc(error.message||error)}</span>`; }
  try {
    const d=await api('/api/qa/desktop');
    desktopBox.innerHTML=`<b>Desktop automation:</b> ${d.windows?(d.pywinauto?'<span class="ok">Ready</span>':'<span class="warn">Support package not installed</span>'):'<span class="muted">Windows only</span>'}<br><small>${esc(d.summary||'')}</small>`;
    $('installDesktopQA').classList.toggle('hidden',!d.windows||d.pywinauto);
    $('probeVSCode').classList.toggle('hidden',!d.windows||!d.pywinauto||!d.vscode_ready);
    $('probeTheia').classList.toggle('hidden',!d.windows||!d.pywinauto||!d.theia_ready);
  } catch(error) { desktopBox.innerHTML=`<span class="bad">Desktop QA status failed: ${esc(error.message||error)}</span>`; }
}
async function runBrowserQA() {
  const button=$('runBrowserQA'); button.disabled=true; button.textContent='Running real clicks…';
  $('browserQAStatus').innerHTML='<span class="warn">Chromium is clicking through Agape now…</span>';
  try {
    const result=await api('/api/qa/browser/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'safe'})});
    $('browserQAStatus').innerHTML=qaReportSummary(result);
    toast(result.ok?'Real click test passed':'Real click test failed');
  } catch(error) {
    $('browserQAStatus').innerHTML=`<span class="bad">Real click test failed: ${esc(error.message||error)}</span>`;
    await loadQAStatus();
  } finally { button.disabled=false; button.textContent='Run real UI click test'; }
}
async function installQAChromium() {
  const b=$('installQAChromium');b.disabled=true;
  try { await api('/api/qa/browser/install-chromium',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});toast('Test Chromium installed');await loadQAStatus(); }
  catch(error){toast(error.message||String(error));} finally {b.disabled=false;}
}
async function installDesktopQA() {
  const b=$('installDesktopQA');b.disabled=true;
  try { await api('/api/support/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'pip',package:'pywinauto'})});toast('Windows UI automation installed');await loadQAStatus(); }
  catch(error){toast(error.message||String(error));} finally {b.disabled=false;}
}
async function probeDesktop(manager) {
  const box=$('desktopQAStatus');
  box.innerHTML=`<span class="warn">Launching and detecting ${esc(manager)}…</span>`;
  try { const r=await api('/api/qa/desktop/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({manager})});box.innerHTML=`<span class="ok">Desktop probe PASS</span><br><small>${esc((r.titles||[]).join(' | ')||('PID '+r.pid))}</small>`; }
  catch(error){box.innerHTML=`<span class="bad">Desktop probe failed: ${esc(error.message||error)}</span>`;}
}
if ($('runBrowserQA')) $('runBrowserQA').onclick=runBrowserQA;
if ($('refreshQA')) $('refreshQA').onclick=loadQAStatus;
if ($('installQAChromium')) $('installQAChromium').onclick=installQAChromium;
if ($('installDesktopQA')) $('installDesktopQA').onclick=installDesktopQA;
if ($('probeVSCode')) $('probeVSCode').onclick=()=>probeDesktop('vscode');
if ($('probeTheia')) $('probeTheia').onclick=()=>probeDesktop('theia-full');


async function loadApprovedInstallers() {
  const box = $('approvedInstallers');
  if (!box) return;
  try {
    const data = await api('/api/security/approved-installers');
    const rows = data.approved || [];
    if (!rows.length) { box.innerHTML = '<p class="muted">No installers are currently trusted. Agape will ask before adding one.</p>'; return; }
    box.innerHTML = rows.map(x => `<div class="approval-row"><div><b>${esc(x.name || 'Approved installer')}</b><br><small>${esc(x.kind==='signed_publisher'?'Signed publisher':'Exact installer')} · ${esc(x.signature_status || 'Unknown signature')}</small><br><code>${esc((x.sha256 || x.certificate_thumbprint || '').slice(0,32))}${(x.sha256 || x.certificate_thumbprint || '').length>32?'…':''}</code><br><small>Approved ${esc(x.approved_at || '')}</small></div><button data-revoke-approval="${esc(x.id || '')}">Revoke</button></div>`).join('');
    document.querySelectorAll('[data-revoke-approval]').forEach(button => button.onclick = async () => {
      if (!confirm('Remove this installer approval? Agape will ask again next time.')) return;
      await api('/api/security/approved-installers/revoke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:button.dataset.revokeApproval})});
      await loadApprovedInstallers();
      toast('Approval removed');
    });
  } catch (error) {
    box.innerHTML = `<p class="bad">Could not load installer approvals: ${esc(error.message)}</p>`;
  }
}

// Explicit browser spellchecking for every current and dynamically-created edit field.
document.querySelectorAll('textarea,input[type="text"]').forEach(node => { node.spellcheck = true; node.autocapitalize = 'sentences'; });
setSourceMode('paste');
setStep(1);
boot();


async function loadTestingTools(){
  const box=$('testingToolStatus');
  if(!box)return;
  try{
    const data=await api('/api/testing/tools');
    const rows=data.tools||[];
    box.innerHTML=rows.map(t=>{const tier=t.tier==='advanced'?'Full Developer/Admin':t.tier==='standard'?'Standard':'Essential';return `<div class="cap-row"><div><b>${esc(t.name)}</b> ${t.recommended?'<span class="ok">Standard</span>':`<span class="muted">${esc(tier)}</span>`}<br><small>${esc(t.why)}</small><br><small class="muted">${esc(t.cost)}</small>${t.detail?`<br><small class="muted">Status: ${esc(t.detail)}</small>`:''}</div><div class="cap-actions"><span class="${t.installed?'ok':'warn'}">${t.installed?'Installed':'Not installed'}</span>${t.installed?'':`<button class="secondary installTestingTool" data-tool="${esc(t.id)}">Install</button>`}</div></div>`}).join('') || '<p class="muted">No testing tools reported.</p>';
    document.querySelectorAll('.installTestingTool').forEach(btn=>btn.onclick=()=>installTestingTool(btn.dataset.tool));
  }catch(e){box.innerHTML=`<p class="bad">Could not check testing tools: ${esc(String(e.message||e))}</p>`;}
}
async function installTestingTool(id){
  const names={axe:'axe accessibility testing',schemathesis:'Schemathesis API testing',zap:'OWASP ZAP security scanner',lighthouse:'Lighthouse CI',k6:'Grafana k6 load testing','appium-windows':'Appium Windows desktop testing','appium-android':'Appium Android testing'};
  if(!confirm(`Install ${names[id]||id}?\n\nThis is optional and may download software from its normal package source.`))return;
  toast(`Installing ${names[id]||id}…`);
  try{
    const r=await api('/api/testing/tools/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:id})});
    toast(r.ok?'Testing tool installed':'Testing tool install did not complete');
  }catch(e){toast(`Install failed: ${String(e.message||e)}`);}
  await loadTestingTools();
}
if($('refreshTestingTools')) $('refreshTestingTools').onclick=loadTestingTools;
if($('installRecommendedTesting')) $('installRecommendedTesting').onclick=async()=>{
  if(!confirm('Install the Standard testing set?\n\nThis installs the lighter everyday developer checks: accessibility, API edge cases and Lighthouse. ZAP, load testing and Android tooling stay in Full Developer/Admin.'))return;
  const data=await api('/api/testing/tools');
  for(const id of (data.recommended_ids||[])){
    const row=(data.tools||[]).find(x=>x.id===id);
    if(row && !row.installed){await api('/api/testing/tools/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:id})}).catch(()=>null);}
  }
  await loadTestingTools();
  toast('Standard testing tools install attempt finished');
};

// R2.4: coherent installation profiles. These preserve the existing experience
// setting values for backwards compatibility while making downloads explicit.
const INSTALL_PROFILE_META={
  basic:{label:'Essential / Low use',warning:'Installs no heavy optional toolchain. Agape core, documents and research remain available.'},
  standard:{label:'Standard / Medium use',warning:'Adds Git, VS Code, Node, Chromium QA, axe, Schemathesis and Lighthouse.'},
  advanced:{label:'Full Developer/Admin / High use',warning:'Large install. Adds Standard tools plus Ollama/Aider support, OWASP ZAP + Java, k6, Appium Android prerequisites and OpenHands through WSL. WSL/Android setup can require a restart or device/emulator setup.'}
};
function profileStatus(text,cls='muted'){
  const box=$('installProfileStatus');if(!box)return;
  box.className='notice '+cls;box.textContent=text;
}
async function profileCall(label,fn,rows){
  profileStatus('Working on: '+label+'…','warn');
  try{const out=await fn();rows.push({label,ok:out?.ok!==false,detail:out?.message||out?.error||''});return out;}
  catch(e){rows.push({label,ok:false,detail:String(e.message||e)});return null;}
}
async function installUsageProfile(exp){
  const meta=INSTALL_PROFILE_META[exp]||INSTALL_PROFILE_META.basic;
  if(!confirm(`Use ${meta.label}?\n\n${meta.warning}\n\nAgape will only start optional installers after this confirmation.`))return;
  const rows=[];
  const plan=await profileCall('saving Agape profile',()=>api(`/api/setup/plan?experience=${encodeURIComponent(exp)}`),rows);
  if(plan?.plan){
    const caps=(plan.plan.capabilities||[]).filter(x=>x.required||x.recommended_now).map(x=>x.id);
    await profileCall('enabling profile capabilities',()=>api('/api/setup/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({experience:exp,selected_capabilities:caps})}),rows);
  }
  if(exp!=='basic'){
    for(const [kind,pkg,label] of [
      ['winget','git','Git'],['winget','vscode','VS Code'],['winget','node','Node.js LTS']
    ]) await profileCall('install/check '+label,()=>api('/api/support/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,package:pkg})}),rows);
    for(const [id,label] of [['axe','axe accessibility'],['schemathesis','Schemathesis'],['lighthouse','Lighthouse CI']])
      await profileCall('install/check '+label,()=>api('/api/testing/tools/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:id})}),rows);
    await profileCall('install/check Chromium QA',()=>api('/api/qa/browser/install-chromium',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),rows);
  }
  if(exp==='advanced'){
    await profileCall('install/check Aider',()=>api('/api/support/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'pip',package:'aider-chat'})}),rows);
    await profileCall('install/check Ollama',()=>api('/api/support/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'winget',package:'ollama'})}),rows);
    for(const [id,label] of [['zap','OWASP ZAP + Java'],['k6','k6 load testing'],['appium-android','Appium Android']])
      await profileCall('install/check '+label,()=>api('/api/testing/tools/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:id})}),rows);
    await profileCall('install/check OpenHands',()=>api('/api/coding/tools/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:'openhands',action:'install'})}),rows);
  }
  const failed=rows.filter(x=>!x.ok);
  const done=rows.filter(x=>x.ok).length;
  profileStatus(`${meta.label}: ${done}/${rows.length} steps completed${failed.length?`. ${failed.length} need attention: `+failed.map(x=>x.label+(x.detail?' — '+x.detail:'')).join(' | '):'. Ready.'}`,failed.length?'warn':'ready');
  await loadSettings().catch(()=>null);
}
if($('installProfileBasic')) $('installProfileBasic').onclick=()=>installUsageProfile('basic');
if($('installProfileStandard')) $('installProfileStandard').onclick=()=>installUsageProfile('standard');
if($('installProfileAdvanced')) $('installProfileAdvanced').onclick=()=>installUsageProfile('advanced');
