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
  // Long notes (several file names) stay longer: about 60 ms per character, 2.5 s at least.
  toastTimer = setTimeout(() => { node.hidden = true; }, Math.max(2500, text.length * 60));
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
    // Nothing chosen yet: the running file, else the newest (files from earlier sessions come first).
    select((running || state.files[state.files.length - 1]).id, false);
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
  if (changed) { hideBar(); showLines(id); }
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
  if (view !== 'file') hideBar();
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
  // Which model made (or is making) this text: files of earlier sessions may differ from the settings.
  $('file-model').textContent = file.model ? `Модель: ${file.model}` : '';
  $('file-model').hidden = !file.model;
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
  renderAudioBar(file);
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
  wordTimes = null;  // the word index of the player is built again on demand
  const text = $('text');
  text.textContent = '';
  const lines = state.lines.get(id) || [];
  const fragment = document.createDocumentFragment();
  for (const line of lines) fragment.appendChild(lineNode(line));
  text.appendChild(fragment);
  renderMain();
}

// Word confidence (plan 03 B2): how sure the model was of a word, 0..1 (null when not known:
// text typed by hand, older files). Underline style: below Settings doubt_light a word is
// doubtful (d1, dotted), below doubt_strong likely wrong (d2, wavy). Colour style: every
// word gets a colour that slides smoothly through the steps --conf-0 (sure, green) ..
// --conf-4 (red), placed at the GRADIENT confidences; the class c0..c4 is the nearest
// step, the fallback where color-mix is missing.
const GRADIENT = [0.98, 0.92, 0.85, 0.75, 0.60];

function doubtLevel(confidence) {
  const light = state.settings.doubt_light || 0.97;
  const strong = state.settings.doubt_strong || 0.80;
  return confidence < strong ? 'd2' : confidence < light ? 'd1' : '';
}

function wordColor(confidence) {
  // The two gradient steps around the confidence, mixed in proportion (oklab keeps the
  // in-between colours bright). The tokens differ per theme, so the mix follows the theme.
  if (confidence >= GRADIENT[0]) return 'var(--conf-0)';
  for (let step = 1; step < GRADIENT.length; step++) {
    if (confidence >= GRADIENT[step]) {
      const share = (confidence - GRADIENT[step]) / (GRADIENT[step - 1] - GRADIENT[step]);
      return `color-mix(in oklab, var(--conf-${step - 1}) ${(share * 100).toFixed(1)}%, var(--conf-${step}))`;
    }
  }
  return `var(--conf-${GRADIENT.length - 1})`;
}

function markWord(span) {
  // The classes and the colour of one word span, from its data-c.
  const confidence = Number(span.dataset.c);
  span.classList.remove('d1', 'd2', 'c0', 'c1', 'c2', 'c3', 'c4');
  const level = doubtLevel(confidence);
  if (level) span.classList.add(level);
  let step = GRADIENT.findIndex((bound) => confidence >= bound);
  if (step < 0) step = GRADIENT.length - 1;
  span.classList.add(`c${step}`);
  span.style.setProperty('--wc', wordColor(confidence));
}

function markAllWords() {
  // The thresholds changed in Settings: mark the shown words again.
  for (const span of $('text').querySelectorAll('.w[data-c]')) markWord(span);
}

function lineNode(line) {
  // Each word is its own span (data-w = its index in the line, the line's data-seg = its index
  // in the file), so a selection maps back to word times (plan 03).
  const p = el('p');
  p.dataset.seg = line.index;
  const time = el('time', 'playable', clock(line.start));
  time.dateTime = `PT${line.start.toFixed(1)}S`;
  time.title = 'Прослушать эту строку';
  p.appendChild(time);
  const words = line.words || [];
  if (!words.length) {
    p.appendChild(document.createTextNode(line.text));
    return p;
  }
  words.forEach((word, index) => {
    if (index) p.appendChild(document.createTextNode(' '));
    const span = el('span', 'w', word[2]);
    span.dataset.w = index;
    const confidence = word[3];
    if (confidence !== null && confidence !== undefined) {
      span.dataset.c = confidence;
      markWord(span);
    }
    p.appendChild(span);
  });
  return p;
}

async function refreshLines(id) {
  // The text of a file changed (a part was fixed): draw it again where the reader was.
  state.lines.delete(id);
  if (state.selected !== id) return;
  const top = $('text').scrollTop;
  const answer = await call('segments', id);
  if (!answer || state.selected !== id) return;
  state.lines.set(id, answer);
  drawLines(id);
  $('text').scrollTop = top;
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

function applyDoubts(on, style) {
  // The "Сомнения" switch shows or hides the marks; Settings picks underline or colours.
  $('doubts').checked = on;
  const text = $('text');
  text.classList.toggle('doubts-underline', on && style !== 'colors');
  text.classList.toggle('doubts-colors', on && style === 'colors');
}

function showConfidence(event) {
  // The number appears on hover: on marked words, or on every word in the colour style.
  const word = event.target.closest && event.target.closest('.w');
  if (!word || word.dataset.c === undefined) return;
  const text = $('text');
  const percent = Math.round(Number(word.dataset.c) * 100);
  if (text.classList.contains('doubts-colors')) word.title = `Уверенность модели: ${percent} %`;
  else if (!text.classList.contains('doubts-underline')) word.title = '';
  else if (word.classList.contains('d2')) word.title = `Скорее ошибка: уверенность модели ${percent} %`;
  else if (word.classList.contains('d1')) word.title = `Возможно ошибка: уверенность модели ${percent} %`;
  else word.title = '';
}

async function copyText(forLlm) {
  // forLlm: the text with doubtful words marked as word[?66%] and a note on the marks.
  const file = fileById(state.selected);
  if (!file) return;
  const text = await call('copy_text', file.id, $('times').checked, !!forLlm);
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
  toast(forLlm ? 'Текст для ИИ скопирован' : 'Текст скопирован');
}

// ------------------------------------------------------------------ fixing a selected part (plan 03)
//
// Selecting words in a finished file's text shows a small bar above them: listen, recognise
// again (RNNT, CTC and Whisper side by side), or edit by hand. Python does the work
// (controller.clip, reread, apply_fix); the page maps the selection to word positions.

const MAX_REREAD_SECONDS = 25;  // gigaam_app/fix.py MAX_SECONDS
let selection = null;   // {fileId, first: [line, word], last: [line, word]} under the bar
let pointerDown = false;
const fix = { fileId: null, first: null, last: null, request: null, current: '' };

function fixableFile() {
  const file = fileById(state.selected);
  return file && (file.state === 'done' || file.state === 'cancelled') && file.segments ? file : null;
}

function wordOf(fileId, position) {
  const lines = state.lines.get(fileId) || [];
  const line = lines[position[0]];
  return line && line.words ? line.words[position[1]] : null;
}

function wordsBetween(fileId, first, last) {
  const lines = state.lines.get(fileId) || [];
  const found = [];
  for (let index = first[0]; index <= last[0]; index += 1) {
    const words = (lines[index] && lines[index].words) || [];
    const from = index === first[0] ? first[1] : 0;
    const to = index === last[0] ? last[1] : words.length - 1;
    for (let w = from; w <= to; w += 1) found.push(words[w][2]);
  }
  return found;
}

function selectedWords() {
  // The first and last word the browser selection touches with at least one character.
  const chosen = window.getSelection();
  if (!chosen || chosen.isCollapsed || !chosen.rangeCount) return null;
  const range = chosen.getRangeAt(0);
  const text = $('text');
  if (!text.contains(range.startContainer) || !text.contains(range.endContainer)) return null;
  let first = null;
  let last = null;
  for (const span of text.querySelectorAll('.w')) {
    const node = span.firstChild;
    if (!node) continue;
    const size = node.length;
    const endsBefore = range.comparePoint(node, size) < 0
      || (range.startContainer === node && range.startOffset === size);
    if (endsBefore) continue;
    const startsAfter = range.comparePoint(node, 0) > 0
      || (range.endContainer === node && range.endOffset === 0);
    if (startsAfter) break;
    const position = [Number(span.parentNode.dataset.seg), Number(span.dataset.w)];
    if (!first) first = position;
    last = position;
  }
  return first ? { first, last, range } : null;
}

function hideBar() {
  $('sel-bar').hidden = true;
  selection = null;
}

function updateBar() {
  const file = state.view === 'file' ? fixableFile() : null;
  const found = file ? selectedWords() : null;
  if (!found) { hideBar(); return; }
  selection = { fileId: file.id, first: found.first, last: found.last };
  $('sel-bar').hidden = false;
  placeBar(found.range);
}

function placeBar(range) {
  // Above the selection (below it when there is no room), inside the text area.
  const bar = $('sel-bar');
  const host = $('view-file').getBoundingClientRect();
  const area = $('text').getBoundingClientRect();
  const box = range.getBoundingClientRect();
  const firstLine = range.getClientRects()[0] || box;
  bar.style.visibility = box.bottom < area.top || box.top > area.bottom ? 'hidden' : '';
  let top = box.top - bar.offsetHeight - 8;
  if (top < area.top) top = box.bottom + 8;
  const left = Math.max(8, Math.min(firstLine.left - host.left, host.width - bar.offsetWidth - 8));
  bar.style.top = `${top - host.top}px`;
  bar.style.left = `${left}px`;
}

// ---- playing a part

const player = new Audio();
let playingButton = null;

function setPlayLabel(button, on) {
  if (button && button.tagName === 'BUTTON') button.innerHTML = on ? '&#9632; Стоп' : '&#9654; Слушать';
}

function stopPlaying() {
  player.pause();
  setPlayLabel(playingButton, false);
  playingButton = null;
}

async function playPart(fileId, first, last, button) {
  const again = playingButton === button && !player.paused;
  stopPlaying();
  if (again) return;  // the same button stops it
  const clip = await call('clip', fileId, first, last);
  if (!clip) return;
  player.src = clip.url;
  playingButton = button;
  setPlayLabel(button, true);
  try {
    await player.play();
  } catch (error) {
    stopPlaying();
    toast('Не удалось воспроизвести звук');
  }
}

player.addEventListener('ended', stopPlaying);

function playLine(index) {
  // A timecode plays from its line and keeps going (plan 05 B2).
  const file = fixableFile();
  const lines = file ? state.lines.get(file.id) || [] : [];
  const line = lines[index];
  if (!line) return;
  const first = line.words && line.words.length ? line.words[0][0] : line.start;
  playFrom(first);
}

// ---- the player for the whole file (plan 05)
//
// The file's sound comes from Python's local server (controller.audio): the file itself
// when the window plays its format, else a copy made once. Play/pause, time, seek and
// speed sit in a bar under the text; the word being spoken is highlighted and the text
// follows it unless the reader scrolled away in the last few seconds.

const filePlayer = new Audio();
filePlayer.preload = 'metadata';
const audio = { fileId: null, url: null, waiting: null, converted: false, stopAt: null };
let wordTimes = null;      // [[start, end, line, word]] of the shown file, sorted by start
let nowWord = null;        // the highlighted span
let readerScrolled = 0;    // when the reader last scrolled the text by hand (ms)
let seeking = false;       // the seek bar is being dragged

function playerFile() {
  // The file the bar is for: a finished or cancelled file on screen.
  const file = fileById(state.selected);
  return file && (file.state === 'done' || file.state === 'cancelled') && file.segments ? file : null;
}

function renderAudioBar(file) {
  const show = !!file && (file.state === 'done' || file.state === 'cancelled') && !!file.segments;
  $('audio-bar').hidden = !show;
  if (audio.fileId && (!show || audio.fileId !== file.id)) resetAudio();
  if (show && audio.fileId !== file.id) showTime(0, file.duration || 0);
}

function resetAudio() {
  filePlayer.pause();
  filePlayer.removeAttribute('src');
  filePlayer.load();
  Object.assign(audio, { fileId: null, url: null, waiting: null, converted: false, stopAt: null });
  markNow(null);
  showPlaying(false);
}

function showTime(now, total) {
  $('audio-time').textContent = `${clock(now)} / ${clock(total)}`;
  if (!seeking) $('audio-seek').value = total ? Math.round((now / total) * 1000) : 0;
}

function showPlaying(on) {
  $('audio-play').innerHTML = on ? '&#10074;&#10074;' : '&#9654;';
  $('audio-play').setAttribute('aria-label', on ? 'Пауза' : 'Слушать');
  $('audio-play').title = on ? 'Пауза (пробел)' : 'Слушать (пробел)';
}

async function loadAudio(convert) {
  // Ask Python where the selected file's sound is; wait for a copy when one is being made.
  const file = playerFile();
  if (!file) return false;
  if (audio.fileId === file.id && audio.url && !convert) return true;
  const answer = await call('audio', file.id, !!convert);
  if (!answer || playerFile() !== file) return false;
  Object.assign(audio, { fileId: file.id, converted: !!convert });
  let url = answer.url;
  if (answer.preparing) {
    $('audio-time').textContent = 'Готовлю звук...';
    $('audio-play').disabled = true;
    url = await new Promise((resolve) => { audio.waiting = { id: file.id, resolve }; });
    $('audio-play').disabled = false;
    if (audio.fileId !== file.id) return false;
  }
  if (!url) {
    showTime(0, file.duration || 0);
    return false;
  }
  audio.url = url;
  filePlayer.src = url;
  filePlayer.playbackRate = Number($('audio-speed').value);
  return true;
}

function onAudioReady(data) {
  // A playable copy is ready (or could not be made: url null).
  if (audio.waiting && audio.waiting.id === data.id) {
    const { resolve } = audio.waiting;
    audio.waiting = null;
    resolve(data.url);
  }
}

async function playFrom(seconds, stopAt) {
  // Play the shown file from a time; stopAt (seconds) pauses there (a selection).
  stopPlaying();  // the fix dialog's clip
  if (!(await loadAudio(false))) return;
  audio.stopAt = stopAt === undefined ? null : stopAt;
  try {
    if (filePlayer.readyState < 1) await new Promise((resolve, reject) => {
      filePlayer.addEventListener('loadedmetadata', resolve, { once: true });
      filePlayer.addEventListener('error', reject, { once: true });
    });
    filePlayer.currentTime = Math.max(0, seconds);
    readerScrolled = 0;  // a new start: follow the words again
    await filePlayer.play();
  } catch (error) {
    // The error listener below tries the converted copy.
  }
}

async function togglePlay() {
  if (!playerFile()) return;
  if (!filePlayer.paused) { filePlayer.pause(); return; }
  stopPlaying();
  if (!(await loadAudio(false))) return;
  audio.stopAt = null;
  try { await filePlayer.play(); } catch (error) { /* handled by the error listener */ }
}

function buildWordTimes() {
  const lines = state.lines.get(state.selected) || [];
  wordTimes = [];
  lines.forEach((line) => (line.words || []).forEach((word, index) => {
    wordTimes.push([word[0], word[1], line.index, index]);
  }));
  wordTimes.sort((a, b) => a[0] - b[0]);
}

function wordAt(seconds) {
  // The last word that started by this time (binary search); null before the first one.
  if (!wordTimes) buildWordTimes();
  let low = 0, high = wordTimes.length - 1, found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (wordTimes[middle][0] <= seconds) { found = middle; low = middle + 1; } else high = middle - 1;
  }
  return found < 0 ? null : wordTimes[found];
}

function markNow(span) {
  if (nowWord === span) return;
  if (nowWord) nowWord.classList.remove('now');
  nowWord = span;
  if (!span) return;
  span.classList.add('now');
  // Follow the words, unless the reader scrolled away in the last few seconds.
  if (Date.now() - readerScrolled < 4000) return;
  const box = $('text').getBoundingClientRect();
  const word = span.getBoundingClientRect();
  if (word.top < box.top + 8 || word.bottom > box.bottom - 8) span.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function followPlayer() {
  // Runs on every frame while playing: time, seek bar, the spoken word, the selection's end.
  const now = filePlayer.currentTime;
  if (audio.stopAt !== null && now >= audio.stopAt) {
    filePlayer.pause();
    audio.stopAt = null;
  }
  showTime(now, filePlayer.duration || (playerFile() || {}).duration || 0);
  const word = wordAt(now);
  const span = word && word[1] + 1.0 >= now
    ? $('text').querySelector(`p[data-seg="${word[2]}"] .w[data-w="${word[3]}"]`) : null;
  markNow(span);
  if (!filePlayer.paused) requestAnimationFrame(followPlayer);
}

filePlayer.addEventListener('play', () => { showPlaying(true); requestAnimationFrame(followPlayer); });
filePlayer.addEventListener('pause', () => showPlaying(false));
filePlayer.addEventListener('ended', () => { showPlaying(false); markNow(null); });
filePlayer.addEventListener('timeupdate', () => { if (filePlayer.paused) followPlayer(); });
filePlayer.addEventListener('error', async () => {
  // The window cannot play this file as it is: ask once for a converted copy.
  if (!audio.fileId || audio.converted || !filePlayer.getAttribute('src')) {
    if (audio.fileId) toast('Не удалось воспроизвести звук');
    return;
  }
  const at = filePlayer.currentTime || 0;
  if (await loadAudio(true)) playFrom(at);
});

// ---- the fix dialog

function keyOf(word) {
  return word.toLowerCase().replace(/ё/g, 'е').replace(/[^\p{L}\p{N}]/gu, '');
}

function markedText(text, current) {
  // The reading with the words that differ from the current text marked (longest common subsequence).
  const words = text.split(/\s+/).filter(Boolean);
  const a = words.map(keyOf);
  const b = current.split(/\s+/).filter(Boolean).map(keyOf);
  const table = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  // Walk the table: a reading word is unchanged when it is part of the common subsequence.
  const same = new Array(a.length).fill(false);
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { same[i] = true; i += 1; j += 1; } else if (table[i + 1][j] >= table[i][j + 1]) i += 1; else j += 1;
  }
  const node = el('div', 'reading-text');
  words.forEach((word, index) => {
    if (index) node.appendChild(document.createTextNode(' '));
    node.appendChild(same[index] ? document.createTextNode(word) : el('mark', '', word));
  });
  return node;
}

function readingItem(key, title, status) {
  const item = el('li', 'reading quiet');
  item.dataset.model = key;
  const body = el('div', 'reading-body');
  body.appendChild(el('div', 'reading-model', title));
  body.appendChild(el('div', 'reading-text', status));
  item.appendChild(body);
  return item;
}

function whisperInstalled() {
  const whisper = (state.options.models || []).find((model) => model.key === 'Whisper');
  return !!(whisper && whisper.installed);
}

function openFix(reread) {
  if (!selection) return;
  const { fileId, first, last } = selection;
  const start = wordOf(fileId, first)[0];
  const end = wordOf(fileId, last)[1];
  Object.assign(fix, { fileId, first, last, request: null, current: wordsBetween(fileId, first, last).join(' ') });
  window.getSelection().removeAllRanges();
  hideBar();
  $('fix-range').textContent = `${clock(start)} - ${clock(end)}, ${(end - start).toFixed(1)} с`;
  $('fix-text').value = fix.current;
  $('fix-terms').value = state.settings.terms || '';
  $('fix-terms').hidden = !whisperInstalled();
  $('fix-readings').textContent = '';
  $('fix-note').textContent = whisperInstalled() ? ''
    : 'Whisper не скачана: её можно скачать в настройках. Она лучше пишет английские термины.';
  $('fix-reread').disabled = false;
  $('fix').showModal();
  if (reread) startReread();
  else $('fix-text').focus();
}

async function startReread() {
  const start = wordOf(fix.fileId, fix.first)[0];
  const end = wordOf(fix.fileId, fix.last)[1];
  if (end - start > MAX_REREAD_SECONDS) {
    $('fix-note').textContent = `Распознать заново можно не больше ${MAX_REREAD_SECONDS} секунд речи: выделите часть поменьше.`;
    return;
  }
  $('fix-reread').disabled = true;
  const answer = await call('reread', fix.fileId, fix.first, fix.last, $('fix-terms').value);
  if (!answer) { $('fix-reread').disabled = false; return; }
  fix.request = answer.request;
  const list = $('fix-readings');
  list.textContent = '';
  const now = readingItem('', 'Сейчас', fix.current);
  now.className = 'reading current';
  list.appendChild(now);
  const status = answer.waiting ? 'Ждёт: сначала закончится распознавание файла...' : 'Распознаю...';
  for (const model of answer.models) list.appendChild(readingItem(model.key, model.title, status));
}

function onReading(data) {
  if (!$('fix').open || data.request !== fix.request) return;
  const item = data.model ? $('fix-readings').querySelector(`[data-model="${CSS.escape(data.model)}"]`) : null;
  if (data.phase === 'loading' && item) {
    item.querySelector('.reading-text').textContent = 'Загрузка модели...';
  } else if (data.phase === 'result' && item) {
    const body = item.querySelector('.reading-body');
    body.querySelector('.reading-text').remove();
    if (data.error) {
      body.appendChild(el('div', 'reading-text', `Ошибка: ${data.error}`));
    } else if (!data.text) {
      body.appendChild(el('div', 'reading-text', 'Ничего не распознано'));
    } else if (data.same) {
      body.appendChild(el('div', 'reading-text', 'Так же, как сейчас'));
    } else {
      item.className = 'reading';
      body.appendChild(markedText(data.text, fix.current));
      const take = el('button', '', 'Взять');
      take.type = 'button';
      take.title = 'Поставить этот вариант вместо выделенного текста';
      take.addEventListener('click', () => saveFix(data.text, data.model));
      item.appendChild(take);
    }
  } else if (data.phase === 'done') {
    $('fix-reread').disabled = false;
  }
}

async function saveFix(text, model) {
  if (!text.trim()) { toast('Пустой текст: оставьте хотя бы одно слово'); return; }
  if (!model && text.trim().split(/\s+/).join(' ') === fix.current) { $('fix').close(); return; }
  const done = await call('apply_fix', fix.fileId, fix.first, fix.last, text, model || null);
  if (done) {
    $('fix').close();
    toast('Текст исправлен, сохранённые файлы обновлены');
  }
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
  // The language choice only matters for Whisper; GigaAM recognises Russian only.
  const chosen = options.models.find((model) => model.key === settings.model);
  $('language-box').hidden = !(chosen && chosen.language);
  const language = $('language');
  language.textContent = '';
  for (const item of options.languages || []) {
    const option = el('option', '', item.label);
    option.value = item.key;
    language.appendChild(option);
  }
  language.value = settings.language || 'auto';
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
  const style = settings.doubt_style || 'underline';
  for (const input of document.querySelectorAll('input[name="doubt-style"]')) input.checked = input.value === style;
  applyDoubts(settings.doubt_marks !== false, style);
  if (typeof settings.player_volume === 'number') { filePlayer.volume = settings.player_volume; showVolume(); }
  $('doubt-light').value = Math.round((settings.doubt_light || 0.97) * 100);
  $('doubt-strong').value = Math.round((settings.doubt_strong || 0.80) * 100);
  markAllWords();
}

async function changeSetting(change) {
  $('reset-note').textContent = '';
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
    case 'lines_changed': refreshLines(data.id); break;
    case 'audio_ready': onAudioReady(data); break;
    case 'reading': onReading(data); break;
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
$('copy').addEventListener('click', () => copyText(false));
$('copy-llm').addEventListener('click', () => copyText(true));
$('times').addEventListener('change', () => {
  applyTimes($('times').checked);
  call('set_settings', { include_timestamps: $('times').checked });
});
$('doubts').addEventListener('change', () => {
  applyDoubts($('doubts').checked, state.settings.doubt_style || 'underline');
  call('set_settings', { doubt_marks: $('doubts').checked });
});
for (const input of document.querySelectorAll('input[name="doubt-style"]')) {
  input.addEventListener('change', () => changeSetting({ doubt_style: input.value }));
}
$('text').addEventListener('mouseover', showConfidence);
for (const id of ['doubt-light', 'doubt-strong']) {
  $(id).addEventListener('change', () => {
    // Percent in the fields, 0..1 in the settings; the wavy threshold stays below the dotted one.
    const light = Math.floor(Number($('doubt-light').value)) / 100;
    const strong = Math.floor(Number($('doubt-strong').value)) / 100;
    if (!(strong > 0 && strong < light && light <= 1)) {
      toast('Порог волны должен быть меньше порога пунктира');
      $('doubt-light').value = Math.round((state.settings.doubt_light || 0.97) * 100);
      $('doubt-strong').value = Math.round((state.settings.doubt_strong || 0.80) * 100);
      return;
    }
    changeSetting({ doubt_light: light, doubt_strong: strong });
  });
}
$('language').addEventListener('change', () => changeSetting({ language: $('language').value }));
$('threads').addEventListener('change', () => {
  const value = Math.max(0, Math.floor(Number($('threads').value) || 0));
  $('threads').value = value;
  changeSetting({ cpu_threads: value });
});
$('reset-settings').addEventListener('click', async () => {
  if (await call('reset_settings')) $('reset-note').textContent = 'Настройки сброшены.';
});
$('download-yes').addEventListener('click', () => call('download'));
$('download-no').addEventListener('click', () => { $('download').close(); call('decline_download'); });
$('download-stop').addEventListener('click', () => { $('download-stop').disabled = true; call('cancel_download'); });
$('download').addEventListener('cancel', (event) => {
  // Esc: same as "Не сейчас" while asking; ignored while downloading.
  event.preventDefault();
  if (!$('download-yes').hidden) { $('download').close(); call('decline_download'); }
});

// Selecting words: the bar appears when the mouse is released (not while dragging) or after
// a keyboard selection, and follows the text when it scrolls.
document.addEventListener('pointerdown', (event) => {
  if (!event.target.closest('#sel-bar')) pointerDown = true;
});
document.addEventListener('pointerup', () => { pointerDown = false; setTimeout(updateBar, 0); });
let selectionTimer = 0;
document.addEventListener('selectionchange', () => {
  clearTimeout(selectionTimer);
  selectionTimer = setTimeout(() => { if (!pointerDown) updateBar(); }, 120);
});
$('text').addEventListener('scroll', () => {
  const chosen = window.getSelection();
  if (selection && chosen && chosen.rangeCount) placeBar(chosen.getRangeAt(0));
});
window.addEventListener('resize', () => { if (selection) updateBar(); });
$('text').addEventListener('click', (event) => {
  const time = event.target.closest('time.playable');
  if (time && fixableFile()) playLine(Number(time.parentNode.dataset.seg));
  else if (event.altKey) {
    // Alt+click on a word plays from that word.
    const word = event.target.closest('.w');
    const line = word && word.parentNode.dataset.seg;
    const times = word && wordOf(state.selected, [Number(line), Number(word.dataset.w)]);
    if (times) playFrom(times[0]);
  }
});
// Clicking the bar must not clear the selection it is about.
$('sel-bar').addEventListener('mousedown', (event) => event.preventDefault());
$('sel-play').addEventListener('click', () => {
  if (!selection) return;
  playFrom(wordOf(selection.fileId, selection.first)[0], wordOf(selection.fileId, selection.last)[1]);
});
$('sel-reread').addEventListener('click', () => openFix(true));
$('sel-edit').addEventListener('click', () => openFix(false));
$('fix-play').addEventListener('click', () => { filePlayer.pause(); playPart(fix.fileId, fix.first, fix.last, $('fix-play')); });
$('fix-reread').addEventListener('click', startReread);
$('fix-terms').addEventListener('keydown', (event) => { if (event.key === 'Enter') startReread(); });
$('fix-cancel').addEventListener('click', () => $('fix').close());
$('fix-save').addEventListener('click', () => saveFix($('fix-text').value, null));
$('fix').addEventListener('close', () => { stopPlaying(); fix.request = null; });
// A click outside the dialog (on its backdrop) closes it, unless the text was changed by hand:
// a stray click must not lose an edit (Esc and "Otmena" still close it).
$('fix').addEventListener('click', (event) => {
  if (event.target !== $('fix')) return;
  const box = $('fix').getBoundingClientRect();
  const outside = event.clientX < box.left || event.clientX > box.right
    || event.clientY < box.top || event.clientY > box.bottom;
  const edited = $('fix-text').value.trim().split(/\s+/).join(' ') !== fix.current;
  if (outside && !edited) $('fix').close();
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

$('audio-play').addEventListener('click', togglePlay);
// After a mouse click the bar's controls give the focus back, so Space keeps playing and
// pausing instead of pressing the last control again (keyboard users keep their focus).
for (const id of ['audio-play', 'audio-mute', 'audio-speed']) {
  $(id).addEventListener(id === 'audio-speed' ? 'change' : 'click', (event) => {
    if (id === 'audio-speed' || event.detail > 0) $(id).blur();
  });
}
$('audio-seek').addEventListener('input', () => {
  seeking = true;
  const total = filePlayer.duration || (playerFile() || {}).duration || 0;
  $('audio-time').textContent = `${clock((Number($('audio-seek').value) / 1000) * total)} / ${clock(total)}`;
});
$('audio-seek').addEventListener('change', async () => {
  seeking = false;
  const share = Number($('audio-seek').value) / 1000;
  if (!(await loadAudio(false))) return;
  if (filePlayer.readyState < 1) await new Promise((resolve) => filePlayer.addEventListener('loadedmetadata', resolve, { once: true }));
  filePlayer.currentTime = share * filePlayer.duration;
  readerScrolled = 0;
  followPlayer();
});
$('audio-speed').addEventListener('change', () => { filePlayer.playbackRate = Number($('audio-speed').value); });

function showVolume() {
  // The speaker shows muted or the level; the slider shows 0 while muted.
  const silent = filePlayer.muted || filePlayer.volume === 0;
  $('audio-mute').innerHTML = silent ? '&#128263;' : filePlayer.volume < 0.5 ? '&#128265;' : '&#128266;';
  $('audio-mute').title = filePlayer.muted ? 'Включить звук' : 'Выключить звук';
  $('audio-mute').setAttribute('aria-label', $('audio-mute').title);
  $('audio-volume').value = filePlayer.muted ? 0 : Math.round(filePlayer.volume * 100);
}

$('audio-volume').addEventListener('input', () => {
  filePlayer.volume = Number($('audio-volume').value) / 100;
  filePlayer.muted = false;
  showVolume();
});
// The level is kept for the next start (Settings.player_volume); muting is not.
$('audio-volume').addEventListener('change', () => call('set_settings', { player_volume: filePlayer.volume }));
$('audio-mute').addEventListener('click', () => {
  filePlayer.muted = !filePlayer.muted;
  if (!filePlayer.muted && filePlayer.volume === 0) filePlayer.volume = 1;
  showVolume();
});
for (const kind of ['wheel', 'touchmove']) {
  $('text').addEventListener(kind, () => { readerScrolled = Date.now(); }, { passive: true });
}

// Space plays or pauses the file, unless typing or a dialog is open. On the seek bar it
// plays too, as in common players (owner, 2026-11-08).
document.addEventListener('keydown', (event) => {
  if (event.code !== 'Space' || event.ctrlKey || event.altKey || event.metaKey) return;
  const target = event.target;
  if (target.closest && target.closest('input:not([type=range]), textarea, select, button, dialog[open]')) return;
  if (document.querySelector('dialog[open]') || $('audio-bar').hidden || state.view !== 'file') return;
  event.preventDefault();
  togglePlay();
});

// Ctrl+O adds files; Ctrl+, opens settings.
document.addEventListener('keydown', (event) => {
  if (!event.ctrlKey || event.altKey) return;
  if (event.code === 'KeyO') { event.preventDefault(); pickFiles(); }
  if (event.code === 'Comma') { event.preventDefault(); setView('settings'); }
});

if (window.pywebview && window.pywebview.api) boot();
else window.addEventListener('pywebviewready', boot, { once: true });
