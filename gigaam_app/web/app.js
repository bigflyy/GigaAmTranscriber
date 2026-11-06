// GigaAM window logic. Python owns the state (gigaam_app/controller.py); this page draws it.
//
// Page -> Python: pywebview.api.<method>(...), see Api in gigaam_app/window.py.
// Python -> page: gigaam.receive({seq, kind, data}) for each change. The page asks for a
// full snapshot once (api.ready) and then applies messages newer than that snapshot.
'use strict';

const $ = (id) => document.getElementById(id);

const ICONS = {
  done: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
  failed: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M12 6v7M12 17.5v.5"/></svg>',
  cancelled: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M6 12h12"/></svg>',
  remove: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
};

const state = {
  booted: false,
  seq: 0,               // sequence number of the last applied message
  early: [],            // messages that arrived before the snapshot
  files: [],
  engine: { state: 'idle', text: '' },
  settings: {},
  options: { models: [], devices: [], formats: [] },
  selected: null,       // id of the file shown on the right
  followRunning: true,  // show the running file when the next one starts
  lines: new Map(),     // file id -> [{start, end, text}] already fetched
  view: 'file',         // 'file' or 'settings'
};

let api = null;  // pywebview.api once the bridge is ready

// ------------------------------------------------------------------ helpers

function clock(seconds) {
  // 00:09, 12:04, 1:02:03 - the timecode shown before each line.
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600), m = Math.floor(total / 60) % 60, s = total % 60;
  const two = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function fileById(id) {
  return state.files.find((file) => file.id === id) || null;
}

let toastTimer = 0;
function toast(text) {
  const node = $('toast');
  node.textContent = text;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 2500);
}

function showError(text, source) {
  $('banner-text').textContent = text;
  $('banner').dataset.source = source || '';
  $('banner').hidden = false;
}

async function call(name, ...args) {
  // Every bridge call goes through here, so a failure always shows up in the window.
  try {
    return await api[name](...args);
  } catch (error) {
    showError(`Ошибка: ${error && error.message ? error.message : error}`);
    return null;
  }
}

// ------------------------------------------------------------------ file list

function renderFiles() {
  const list = $('files');
  const keep = new Map([...list.children].map((node) => [node.dataset.id, node]));
  list.textContent = '';
  for (const file of state.files) {
    const node = keep.get(file.id) || buildFileItem(file.id);
    updateFileItem(node, file);
    list.appendChild(node);
  }
  if (state.selected && !fileById(state.selected)) state.selected = null;
  if (!state.selected && state.files.length) {
    const running = state.files.find((file) => file.state === 'running');
    select((running || state.files[0]).id, false);
  } else {
    renderMain();
  }
}

function buildFileItem(id) {
  const node = el('li', 'file');
  node.dataset.id = id;
  node.tabIndex = 0;
  node.setAttribute('role', 'button');
  node.innerHTML = '<span class="state"></span><div class="info"><div class="name"></div>'
    + '<div class="detail"></div><div class="mini-bar"><div></div></div></div>'
    + `<button class="icon remove" type="button" aria-label="Убрать из списка">${ICONS.remove}</button>`;
  node.addEventListener('click', (event) => {
    if (event.target.closest('.remove')) return;
    select(id, true);
  });
  node.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(id, true); }
    if (event.key === 'Delete') removeFile(id);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const sibling = event.key === 'ArrowDown' ? node.nextElementSibling : node.previousElementSibling;
      if (sibling) { sibling.focus(); select(sibling.dataset.id, true); }
    }
  });
  node.querySelector('.remove').addEventListener('click', () => removeFile(id));
  return node;
}

function updateFileItem(node, file) {
  node.className = `file ${file.state}${file.id === state.selected ? ' selected' : ''}`;
  node.setAttribute('aria-current', file.id === state.selected ? 'true' : 'false');
  node.title = file.path;
  const icon = node.querySelector('.state');
  icon.className = `state ${file.state}`;
  icon.innerHTML = ICONS[file.state] || '';
  node.querySelector('.name').textContent = file.name;
  const running = file.state === 'running';
  node.querySelector('.detail').textContent = file.detail;
  node.querySelector('.detail').hidden = running;
  node.querySelector('.mini-bar').hidden = !running;
  node.querySelector('.mini-bar div').style.width = `${Math.round((file.progress || 0) * 100)}%`;
  // A running file is cancelled from the right pane, not removed from the list.
  node.querySelector('.remove').hidden = !file.can_remove;
}

function updateOneFile(file) {
  const index = state.files.findIndex((item) => item.id === file.id);
  if (index < 0) return;
  const before = state.files[index];
  state.files[index] = file;
  const node = $('files').querySelector(`[data-id="${CSS.escape(file.id)}"]`);
  if (node) updateFileItem(node, file);
  if (file.state === 'running' && before.state !== 'running') onStarted(file);
  if (file.id === state.selected) renderMain();
}

function onStarted(file) {
  // A new file started: show it unless the user is reading another file on purpose.
  state.lines.set(file.id, []);
  if (state.followRunning || !state.selected) select(file.id, false);
}

function select(id, byUser) {
  if (byUser) {
    const file = fileById(id);
    state.followRunning = !!file && file.state === 'running';
  }
  const changed = state.selected !== id;
  state.selected = id;
  for (const node of $('files').children) {
    const on = node.dataset.id === id;
    node.classList.toggle('selected', on);
    node.setAttribute('aria-current', on ? 'true' : 'false');
  }
  if (changed) showLines(id);
  if (byUser && state.view === 'settings') setView('file');
  renderMain();
}

async function removeFile(id) {
  const file = fileById(id);
  if (!file || !file.can_remove) return;
  await call('remove', id);
}

// ------------------------------------------------------------------ right pane

function setView(view) {
  state.view = view;
  renderMain();
}

function renderMain() {
  const empty = state.files.length === 0;
  $('view-settings').hidden = state.view !== 'settings';
  $('view-empty').hidden = state.view === 'settings' || !empty;
  $('view-file').hidden = state.view === 'settings' || empty;
  if (state.view === 'settings' || empty) return;
  const file = fileById(state.selected);
  if (!file) return;
  $('file-name').textContent = file.name;
  $('file-name').title = file.path;
  $('file-status').textContent = file.status;
  $('file-cancel').hidden = !file.can_cancel;
  $('file-cancel').disabled = !!file.cancelling;
  $('file-retry').hidden = !file.can_retry;
  $('file-remove').hidden = !file.can_remove;
  const bar = $('file-bar');
  bar.hidden = file.state !== 'running';
  bar.firstElementChild.style.width = `${Math.round((file.progress || 0) * 100)}%`;
  renderSaved(file);
  $('text-label').textContent = file.state === 'running' ? 'Текст появляется по ходу' : 'Текст';
  $('copy').disabled = !file.segments;
  const lines = state.lines.get(file.id);
  if (lines && lines.length === 0) {
    const text = $('text');
    if (!text.firstChild || text.firstChild.className === 'placeholder') {
      text.textContent = '';
      text.appendChild(el('p', 'placeholder', placeholderFor(file)));
    }
  }
}

function placeholderFor(file) {
  if (file.state === 'waiting') return 'Файл ждёт своей очереди.';
  if (file.state === 'running') return 'Текст появится здесь, как только будет распознан первый фрагмент.';
  if (file.state === 'failed') return 'Текста нет: распознавание не удалось.';
  return 'Речь не найдена.';
}

function renderSaved(file) {
  const outputs = file.outputs || [];
  const box = $('saved');
  box.hidden = !outputs.some((item) => item.path);
  const list = $('saved-list');
  list.textContent = '';
  for (const item of outputs) {
    const chip = el('button', item.path ? 'chip' : 'chip missing');
    chip.type = 'button';
    chip.dataset.format = item.format;
    chip.appendChild(el('b', '', item.short));
    chip.appendChild(document.createTextNode(item.path ? item.label : `+ ${item.label}`));
    chip.title = item.path ? `Открыть ${item.path}` : `Создать файл: ${item.label}`;
    chip.addEventListener('click', () => (item.path
      ? call('open_output', file.id, item.format)
      : call('create_output', file.id, item.format)));
    list.appendChild(chip);
  }
}

// ------------------------------------------------------------------ live text

async function showLines(id) {
  const text = $('text');
  text.textContent = '';
  if (!id) return;
  const answer = await call('segments', id);
  if (!answer || state.selected !== id) return;
  state.lines.set(id, answer);
  drawLines(id);
}

function drawLines(id) {
  const text = $('text');
  text.textContent = '';
  const lines = state.lines.get(id) || [];
  const fragment = document.createDocumentFragment();
  for (const line of lines) fragment.appendChild(lineNode(line));
  text.appendChild(fragment);
  renderMain();
}

function lineNode(line) {
  const p = el('p');
  const time = el('time', '', clock(line.start));
  time.dateTime = `PT${line.start.toFixed(1)}S`;
  p.appendChild(time);
  p.appendChild(document.createTextNode(line.text));
  return p;
}

function onSegment(data) {
  let lines = state.lines.get(data.id);
  if (!lines) return;  // never shown; fetched in full when selected
  if (data.index < lines.length) return;  // already in the fetched list
  if (data.index > lines.length) {  // missed one: fetch the whole list again
    state.lines.delete(data.id);
    if (state.selected === data.id) showLines(data.id);
    return;
  }
  lines.push(data);
  if (state.selected !== data.id) return;
  const text = $('text');
  const placeholder = text.querySelector('.placeholder');
  if (placeholder) placeholder.remove();
  // Follow new text only while the reader is at the end.
  const atEnd = text.scrollHeight - text.scrollTop - text.clientHeight < 40;
  text.appendChild(lineNode(data));
  if (atEnd) text.scrollTop = text.scrollHeight;
}

function applyTimes(on) {
  $('times').checked = on;
  $('text').classList.toggle('with-times', on);
}

async function copyText() {
  const file = fileById(state.selected);
  if (!file) return;
  const text = await call('copy_text', file.id, $('times').checked);
  if (text === null) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    // Older engines or no permission: the selection-based copy still works.
    const area = el('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  toast('Текст скопирован');
}

// ------------------------------------------------------------------ engine and settings

function renderEngine() {
  const box = $('engine');
  box.className = `engine ${state.engine.state}`;
  $('engine-text').textContent = state.engine.text;
  box.title = state.engine.detail || '';
}

function renderSettings() {
  const settings = state.settings;
  const options = state.options;
  const models = $('models');
  models.textContent = '';
  for (const model of options.models) {
    const label = el('label', 'choice');
    const input = el('input');
    input.type = 'radio';
    input.name = 'model';
    input.value = model.key;
    input.checked = settings.model === model.key;
    input.addEventListener('change', () => changeSetting({ model: model.key }));
    const body = el('div');
    body.appendChild(el('div', 'choice-title', model.title));
    body.appendChild(el('div', 'choice-note', model.note));
    label.append(input, body);
    models.appendChild(label);
  }
  const devices = $('devices');
  devices.textContent = '';
  for (const device of options.devices) {
    const label = el('label');
    const input = el('input');
    input.type = 'radio';
    input.name = 'device';
    input.value = device.key;
    input.checked = settings.device === device.key;
    input.addEventListener('change', () => changeSetting({ device: device.key }));
    label.append(input, document.createTextNode(device.label));
    devices.appendChild(label);
  }
  $('threads').max = options.cpu_count || 64;
  $('threads').value = settings.cpu_threads;
  const formats = $('formats');
  formats.textContent = '';
  for (const format of options.formats) {
    const label = el('label');
    const input = el('input');
    input.type = 'checkbox';
    input.value = format.key;
    input.checked = (settings.outputs || []).includes(format.key);
    input.addEventListener('change', () => {
      const chosen = [...formats.querySelectorAll('input:checked')].map((box) => box.value);
      if (!chosen.length) { input.checked = true; toast('Нужен хотя бы один формат'); return; }
      changeSetting({ outputs: chosen });
    });
    label.append(input, document.createTextNode(format.label));
    formats.appendChild(label);
  }
  $('config-note').textContent = options.config_note || '';
  applyTimes(!!settings.include_timestamps);
}

async function changeSetting(change) {
  $('save-note').textContent = '';
  await call('set_settings', change);
}

// ------------------------------------------------------------------ download dialog

function onDownload(data) {
  const dialog = $('download');
  if (data.phase === 'ask') {
    $('download-title').textContent = `Скачать модель ${data.model}`;
    $('download-text').textContent = data.text;
    $('download-folder').textContent = data.folder;
    $('download-progress').hidden = true;
    $('download-yes').hidden = $('download-no').hidden = false;
    $('download-stop').hidden = true;
    if (!dialog.open) dialog.showModal();
    return;
  }
  if (data.phase === 'progress') {
    $('download-progress').hidden = false;
    $('download-yes').hidden = $('download-no').hidden = true;
    $('download-stop').hidden = false;
    $('download-stop').disabled = false;
    $('download-progress').querySelector('.bar div').style.width = `${Math.round(data.fraction * 100)}%`;
    $('download-status').textContent = data.status;
    if (!dialog.open) dialog.showModal();
    return;
  }
  // done, cancelled or failed: close the dialog; the reason shows elsewhere.
  if (dialog.open) dialog.close();
  if (data.text) toast(data.text);
}

// ------------------------------------------------------------------ messages from Python

function apply(message) {
  if (message.seq <= state.seq) return;
  state.seq = message.seq;
  const data = message.data;
  switch (message.kind) {
    case 'files': state.files = data; renderFiles(); break;
    case 'file': updateOneFile(data); break;
    case 'segment': onSegment(data); break;
    case 'engine':
      state.engine = data;
      renderEngine();
      // A model loaded: an old "could not load" banner is no longer true.
      if (data.state === 'ready' && $('banner').dataset.source === 'engine') $('banner').hidden = true;
      break;
    case 'settings': state.settings = data; renderSettings(); break;
    case 'options': state.options = data; renderSettings(); break;
    case 'download': onDownload(data); break;
    case 'error': showError(data.text, data.source); break;
    case 'notice': toast(data.text); break;
    case 'confirm_close': askClose(data.text); break;
    case 'lines_reset': state.lines.set(data.id, []); if (state.selected === data.id) drawLines(data.id); break;
    default: break;
  }
}

// The user closed the window while a file or a download runs; Python kept it open.
function askClose(text) {
  $('confirm-close-text').textContent = text;
  if (!$('confirm-close').open) $('confirm-close').showModal();
  $('confirm-close-no').focus();
}

window.gigaam = {
  receive(message) {
    if (!state.booted) state.early.push(message);
    else apply(message);
  },
};

async function boot() {
  api = window.pywebview.api;
  const snapshot = await call('ready');
  if (!snapshot) return;
  state.seq = snapshot.seq;
  state.options = snapshot.options;
  state.settings = snapshot.settings;
  state.engine = snapshot.engine;
  state.files = snapshot.files;
  state.booted = true;
  renderSettings();
  renderEngine();
  renderFiles();
  renderMain();
  for (const message of state.early.splice(0)) apply(message);
}

// ------------------------------------------------------------------ wiring

async function pickFiles() {
  state.followRunning = true;
  await call('pick_files');
}

$('add').addEventListener('click', pickFiles);
$('add-empty').addEventListener('click', pickFiles);
$('open-settings').addEventListener('click', () => setView(state.view === 'settings' ? 'file' : 'settings'));
$('close-settings').addEventListener('click', () => setView('file'));
$('banner-close').addEventListener('click', () => { $('banner').hidden = true; });
$('file-cancel').addEventListener('click', () => state.selected && call('cancel', state.selected));
$('file-retry').addEventListener('click', () => { state.followRunning = true; call('retry', state.selected); });
$('file-remove').addEventListener('click', () => removeFile(state.selected));
$('show-folder').addEventListener('click', () => call('show_folder', state.selected));
$('copy').addEventListener('click', copyText);
$('times').addEventListener('change', () => {
  applyTimes($('times').checked);
  call('set_settings', { include_timestamps: $('times').checked });
});
$('threads').addEventListener('change', () => {
  const value = Math.max(0, Math.floor(Number($('threads').value) || 0));
  $('threads').value = value;
  changeSetting({ cpu_threads: value });
});
$('save-default').addEventListener('click', async () => {
  const note = await call('save_default');
  if (note) $('save-note').textContent = note;
});
$('download-yes').addEventListener('click', () => call('download'));
$('download-no').addEventListener('click', () => { $('download').close(); call('decline_download'); });
$('download-stop').addEventListener('click', () => { $('download-stop').disabled = true; call('cancel_download'); });
$('download').addEventListener('cancel', (event) => {
  // Esc: same as "Не сейчас" while asking; ignored while downloading.
  event.preventDefault();
  if (!$('download-yes').hidden) { $('download').close(); call('decline_download'); }
});

$('confirm-close-no').addEventListener('click', () => $('confirm-close').close());
$('confirm-close-yes').addEventListener('click', () => call('close_anyway'));

// Drag and drop. Python receives the drop itself (it needs the real paths, which the
// page cannot see); the page only shows where to drop.
let dragDepth = 0;
const hasFiles = (event) => event.dataTransfer && [...event.dataTransfer.types].includes('Files');
document.addEventListener('dragenter', (event) => {
  if (!hasFiles(event)) return;
  dragDepth += 1;
  $('drop-overlay').hidden = false;
});
document.addEventListener('dragleave', () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) $('drop-overlay').hidden = true;
});
document.addEventListener('dragover', (event) => { if (hasFiles(event)) event.preventDefault(); });
document.addEventListener('drop', (event) => {
  event.preventDefault();
  dragDepth = 0;
  $('drop-overlay').hidden = true;
  state.followRunning = true;
});

// Ctrl+O adds files; Ctrl+, opens settings.
document.addEventListener('keydown', (event) => {
  if (!event.ctrlKey || event.altKey) return;
  if (event.code === 'KeyO') { event.preventDefault(); pickFiles(); }
  if (event.code === 'Comma') { event.preventDefault(); setView('settings'); }
});

if (window.pywebview && window.pywebview.api) boot();
else window.addEventListener('pywebviewready', boot, { once: true });
