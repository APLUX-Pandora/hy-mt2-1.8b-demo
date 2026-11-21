'use strict';
const $ = id => document.getElementById(id);
const longMode = location.pathname === '/long';
const maxCharacters = longMode ? 20000 : 2000;
const order = ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ar', 'th'];
let capabilities, activeJob = null, stream = null, running = false, output = '';
let complete = false, guard = null, stopTimer = null, online = false, reloading = false;
const {requestJSON, streamGuard, exportText} = HyTransport;
const characters = text => [...text].length;
let followLatest = true, activeSegment = null, scrollFrame = null, expectedSourceTop = 0;
let measuredSourcePosition = -1, measuredSourceWidth = 0;
const outputPane = $('result').parentElement;
function setFollowing(value) {
  const resumed = value && !followLatest;
  followLatest = value;
  $('resume-follow').hidden = !longMode || !running || value;
  if (resumed) { measuredSourcePosition = -1; scheduleFollowing(); }
}
function sourcePosition() {
  if (!activeSegment) return 0;
  const points = [...$('input').value];
  const prefix = points.slice(0, activeSegment.start).join('');
  const piece = points.slice(activeSegment.start, activeSegment.end).join('');
  if (activeSegment.completed) return prefix.length + piece.length;
  // Paragraph breaks provide a reading cue, not model word alignment.
  const translated = output.slice(activeSegment.outputStart).trimStart();
  const paragraph = [...translated.matchAll(/\r?\n[ \t]*\r?\n+/g)].length;
  const breaks = [...piece.matchAll(/\r?\n[ \t]*\r?\n+/g)];
  const index = Math.min(paragraph, breaks.length);
  return prefix.length + (index ? breaks[index - 1].index + breaks[index - 1][0].length : 0);
}
function followSource() {
  if (!longMode || !activeSegment) return;
  const input = $('input'), position = sourcePosition();
  if (position === measuredSourcePosition && input.clientWidth === measuredSourceWidth) return;
  const mirror = document.createElement('div'), style = getComputedStyle(input);
  for (const key of ['font', 'lineHeight', 'letterSpacing', 'wordSpacing', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'tabSize', 'textIndent', 'textTransform', 'direction']) mirror.style[key] = style[key];
  Object.assign(mirror.style, {position: 'fixed', top: '-100000px', left: '0', width: `${input.clientWidth}px`,
    boxSizing: 'border-box', whiteSpace: 'pre-wrap', overflowWrap: 'break-word', visibility: 'hidden'});
  mirror.textContent = input.value.slice(0, position);
  const marker = document.createElement('span'); marker.textContent = '\u200b'; mirror.appendChild(marker);
  document.body.appendChild(mirror);
  input.scrollTop = Math.max(0, marker.offsetTop - input.clientHeight * .2);
  expectedSourceTop = input.scrollTop;
  mirror.remove(); measuredSourcePosition = position; measuredSourceWidth = input.clientWidth;
}
function scheduleFollowing() {
  if (scrollFrame !== null) return;
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = null;
    if (!followLatest) return;
    outputPane.scrollTop = outputPane.scrollHeight;
    followSource();
  });
}
outputPane.addEventListener('scroll', () => {
  if (running) setFollowing(outputPane.scrollHeight - outputPane.clientHeight - outputPane.scrollTop <= 32);
});
$('input').addEventListener('scroll', () => {
  if (running && Math.abs($('input').scrollTop - expectedSourceTop) > 2) setFollowing(false);
});
$('resume-follow').onclick = () => { setFollowing(true); scheduleFollowing(); };
window.addEventListener('resize', () => { measuredSourcePosition = -1; if (running) scheduleFollowing(); });

function message(text, error = false) { $('status').textContent = text; $('status').classList.toggle('error', error); }
function count() { $('count').textContent = `${characters($('input').value).toLocaleString()} / ${maxCharacters.toLocaleString()} characters`; }
function segmentProgress(completed = 0, total = 0, current = 0, state = 'Ready') {
  if (!longMode) return;
  $('segment-total').textContent = total || '—';
  $('segment-current').textContent = current ? `${current} / ${total}` : '—';
  $('segment-completed').textContent = completed;
  $('segment-state').textContent = state;
  $('segment-meter').setAttribute('aria-valuemax', total || 1);
  $('segment-meter').setAttribute('aria-valuenow', completed);
  $('segment-meter').setAttribute('aria-valuetext', `${completed} of ${total} segments complete`);
  $('segment-fill').style.width = `${total ? completed / total * 100 : 0}%`;
}
function resetResult() {
  activeSegment = null; followLatest = true; measuredSourcePosition = -1;
  $('input').scrollTop = 0; expectedSourceTop = 0; outputPane.scrollTop = 0;
  $('resume-follow').hidden = true;
  segmentProgress();
  complete = false; output = ''; $('result').textContent = ''; $('placeholder').hidden = false;
  $('copy').disabled = $('download').disabled = true; $('output-count').textContent = 'Ready when you are';
  $('segment-status').textContent = longMode ? 'Independent segment context' : 'Live output. Local inference.';
  for (const id of ['first', 'generation', 'speed']) $(id).textContent = '—';
}
function setRunning(value) {
  running = value; document.body.classList.toggle('busy', value); $('progress').hidden = !value || longMode;
  $('stop').hidden = !value; $('stop').disabled = value && !activeJob;
  for (const id of ['source', 'target', 'swap', 'clear', 'translate']) $(id).disabled = value;
  $('input').readOnly = value; $('input').disabled = false;
  $('resume-follow').hidden = !longMode || !value || followLatest;
  for (const id of ['short-tab', 'long-tab']) { $(id).tabIndex = value ? -1 : 0; $(id).setAttribute('aria-disabled', String(value)); }
  $('translate').disabled = value || reloading || !online || capabilities?.model_state !== 'ready';
  $('reload-model').hidden = capabilities?.model_state === 'ready' || !capabilities?.reload_available;
  $('reload-model').disabled = value || reloading || capabilities?.model_state === 'reloading';
  $('reload-model').textContent = reloading ? 'Reloading…' : 'Reload model';
  $('translate').textContent = value && !reloading ? 'Translating…' : 'Translate ↗';
}
function loadSample(language) {
  if (running) return;
  $('source').value = language;
  if ($('target').value === language) $('target').value = language === 'en' ? 'zh' : 'en';
  $('input').value = (longMode ? capabilities.long_samples : capabilities.samples).find(s => s.language === language).text;
  count(); resetResult(); message('Sample loaded. Edit the text or translate.');
}
function showOutput() {
  $('result').textContent = output; $('placeholder').hidden = !!output;
  $('output-count').textContent = `${characters(output).toLocaleString()} characters`;
  scheduleFollowing();
}
async function translate() {
  if (running || reloading || !online || capabilities?.model_state !== 'ready') return;
  if (!$('input').value.trim()) { message('Enter text to translate.', true); $('input').focus(); return; }
  if (characters($('input').value) > maxCharacters) { message(`Enter up to ${maxCharacters.toLocaleString()} characters.`, true); return; }
  resetResult(); setRunning(true); if (longMode) $('segment-state').textContent = 'Preparing segments…'; message('Starting translation…');
  try {
    const job = await requestJSON('/api/jobs', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: $('input').value, source: $('source').value, target: $('target').value, mode: longMode ? 'long' : 'short'})});
    if (!job || typeof job.id !== 'string' || !/^[a-f0-9]{32}$/.test(job.id)) throw new Error('Invalid job response.');
    activeJob = job.id; $('stop').disabled = false; stream = new EventSource(`/api/jobs/${job.id}/events`);
    const current = stream;
    guard = streamGuard(() => interrupted('Translation connection timed out. Incomplete output kept.'),
      ((longMode ? capabilities.long_timeout : capabilities.request_timeout) + 30) * 1000);
    stream.onopen = () => { if (stream === current) guard.touch(); };
    // Closed streams can still have queued callbacks; never apply them to a new job.
    const listen = (kind, handler) => current.addEventListener(kind, event => {
      if (stream !== current) return;
      guard.touch();
      try { handler(event); } catch (_) { interrupted('Invalid translation response. Incomplete output kept.'); }
    });
    listen('keep-alive', () => {});
    listen('segment', event => {
      const data = JSON.parse(event.data);
      if (data.current && Number.isInteger(data.source_start) && Number.isInteger(data.source_end)) {
        if (!activeSegment || activeSegment.number !== data.current) {
          activeSegment = {number: data.current, start: data.source_start, end: data.source_end,
            outputStart: output.length, completed: false};
        }
        activeSegment.completed = data.completed === data.current;
        scheduleFollowing();
      }
      segmentProgress(data.completed, data.total, data.current, data.current === 0 ? 'Segments ready' : data.completed === data.total ? 'Complete' : 'Translating…');
      message(data.current === 0 ? `Prepared ${data.total} segments.` : data.completed === data.current ? `Segment ${data.current} complete.` : `Translating segment ${data.current} of ${data.total}…`);
    });
    listen('delta', event => {
      const data = JSON.parse(event.data); if (typeof data.text !== 'string') throw new Error();
      output += data.text; showOutput(); if (!longMode) message('Translating…');
    });
    listen('done', event => {
      const data = JSON.parse(event.data); if (typeof data.text !== 'string' || typeof data.cancelled !== 'boolean') throw new Error();
      const limited = data.finish_reason === 'length';
      complete = !(data.cancelled || limited); output = data.text || output; showOutput();
      $('first').textContent = `${Math.round(data.stats.first_token_ms)} ms`;
      $('generation').textContent = `${(data.stats.generation_ms / 1000).toFixed(2)} s`;
      $('speed').textContent = data.stats.tokens_per_second.toFixed(1);
      if (longMode) segmentProgress(data.completed_segments, data.total_segments, Number($('segment-current').textContent.split(' / ')[0]) || 0, data.cancelled ? 'Stopped' : limited ? 'Incomplete' : 'Complete');
      finish();
      if (data.cancelled) message(`${data.message || 'Stopped'}. Partial translation kept.`);
      else if (limited) message('Generation limit reached. Partial translation kept.');
      else message('Translation complete.');
    });
    listen('error', event => {
      const data = event.data ? JSON.parse(event.data) : {};
      if (data.model_state) capabilities.model_state = data.model_state;
      interrupted(data.error || 'Connection interrupted. Incomplete output kept.');
    });
  } catch (error) {
    if (error.modelState) capabilities.model_state = error.modelState;
    interrupted(error.message);
  }
}
function cancelBestEffort(id) {
  if (id) requestJSON(`/api/jobs/${id}/cancel`, {method: 'POST'}, 5000).catch(() => {});
}
function interrupted(text) {
  complete = false;
  const id = activeJob; finish(); cancelBestEffort(id);
  if (longMode) $('segment-state').textContent = 'Incomplete';
  message(text, true); refreshInfo(false);
}

function finish() {
  if (guard) guard.stop(); guard = null; clearTimeout(stopTimer); stopTimer = null;
  if (stream) stream.close(); stream = null; activeJob = null; setRunning(false);
  $('copy').textContent = complete ? 'Copy' : 'Copy incomplete';
  $('download').textContent = complete ? 'Download' : 'Download incomplete';
  if (output && !complete) $('output-count').textContent = `${characters(output).toLocaleString()} characters · Incomplete`;
  $('copy').disabled = $('download').disabled = !output;
}
$('segment-panel').hidden = !longMode;
if (longMode) $('input').removeAttribute('maxlength');
$(longMode ? 'long-tab' : 'short-tab').setAttribute('aria-current', 'page');
$('help').textContent = longMode ? 'Up to 20,000 characters. Around 1,500 characters per segment, split at sentence boundaries and checked against the token budget. Changing the source loads its sample.' : $('help').textContent;
for (const id of ['short-tab', 'long-tab']) $(id).onclick = event => { if (running) event.preventDefault(); };
$('translate').onclick = translate;
$('stop').onclick = async () => {
  if (!activeJob) return;
  const id = activeJob;
  $('stop').disabled = true; message('Stopping…');
  try {
    await requestJSON(`/api/jobs/${id}/cancel`, {method: 'POST'}, 5000);
    if (activeJob === id) stopTimer = setTimeout(() => interrupted('Stop was not confirmed. Incomplete output kept.'), 10000);
  } catch (error) { if (activeJob === id) interrupted(error.message); }
};
$('reload-model').onclick = async () => {
  if (running || reloading) return;
  reloading = true; setRunning(true); $('stop').hidden = true;
  message('Reloading the model…'); $('connection').textContent = 'Reloading';
  try {
    await requestJSON('/api/model/reload', {method: 'POST'}, 60000);
    message('Model reloaded. Ready to translate.');
  } catch (error) { message(error.message, true); }
  finally { reloading = false; await refreshInfo(false); setRunning(false); }
};
$('retry-connection').onclick = () => refreshInfo(true);
$('clear').onclick = () => { $('input').value = ''; count(); resetResult(); message('Enter text or change the source language to load a sample.'); $('input').focus(); };
$('input').oninput = () => { count(); resetResult(); };
$('input').onkeydown = event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); translate(); } };
$('source').onchange = () => loadSample($('source').value);
$('target').onchange = () => {
  if ($('source').value === $('target').value) loadSample(order.find(x => x !== $('target').value));
  else resetResult();
};
$('swap').onclick = () => {
  const source = $('source').value; $('source').value = $('target').value; $('target').value = source;
  if (output) {
    $('input').value = output; count(); resetResult(); message('Languages swapped. Ready to translate.');
  } else loadSample($('source').value);
};
$('copy').onclick = async () => {
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(exportText(output, complete));
    else {
      const area = document.createElement('textarea'); area.value = exportText(output, complete); area.style.position = 'fixed'; area.style.opacity = '0';
      document.body.appendChild(area); area.select(); const copied = document.execCommand('copy'); area.remove();
      if (!copied) throw new Error('Copy is unavailable. Select and copy the translation manually.');
    }
    message(complete ? 'Translation copied.' : 'Incomplete translation copied with a warning.');
  } catch (error) { message(error.message, true); }
};
$('download').onclick = () => {
  const url = URL.createObjectURL(new Blob([exportText(output, complete)], {type: 'text/plain;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = `translation-${$('source').value}-${$('target').value}${complete ? '' : '-incomplete'}.txt`;
  document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
window.addEventListener('beforeunload', () => { if (activeJob) navigator.sendBeacon(`/api/jobs/${activeJob}/cancel`); });
async function refreshInfo(initial = false) {
  try {
    const info = await requestJSON('/api/info');
    if (!info || !['ready', 'failed', 'reloading'].includes(info.model_state) ||
        ![info.request_timeout, info.long_timeout].every(value => Number.isFinite(value) && value > 0) ||
        !order.every(code => typeof info.languages?.[code] === 'string' &&
          [info.samples, info.long_samples].every(samples => Array.isArray(samples) &&
            samples.some(sample => sample.language === code && typeof sample.text === 'string')))) {
      throw new Error('Invalid translator capabilities');
    }
    const first = !capabilities; capabilities = info; online = true;
    if (first) {
      for (const id of ['source', 'target']) for (const code of order) {
        const option = document.createElement('option'); option.value = code; option.textContent = info.languages[code]; $(id).appendChild(option);
      }
      $('source').value = 'zh'; $('target').value = 'en';
      if (!$('input').value) loadSample('zh');
    }
    $('indicator').classList.toggle('ready', info.model_state === 'ready');
    $('connection').textContent = info.model_state === 'failed' ? 'Reload required' : info.model_state === 'reloading' ? 'Reloading' : 'Ready';
    $('retry-connection').hidden = info.model_state !== 'reloading';
    if (info.model_state === 'failed') message('Reload the model before translating again.', true);
    else if (initial) message(info.busy ? 'The device is busy. Wait before translating.' : 'Ready to translate.');
  } catch (_) {
    online = false; $('indicator').classList.remove('ready'); $('connection').textContent = 'Unavailable';
    $('retry-connection').hidden = false;
    if (initial) message('Unable to connect. Retry connection when the device is available.', true);
  }
  setRunning(running);
}
refreshInfo(true);
