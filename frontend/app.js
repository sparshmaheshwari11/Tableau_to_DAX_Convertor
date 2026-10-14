const $ = (id) => document.getElementById(id);
const state = { lastResult: null, file: null, bulkRows: null };

async function checkHealth() {
  try {
    const response = await fetch('/api/health');
    const data = await response.json();
    $('engineStatus').textContent = data.gemini_configured ? 'Local engine + Gemini ready' : 'Local engine ready';
  } catch (_) { $('engineStatus').textContent = 'Engine status unavailable'; }
}
function setError(message) { $('errorBanner').textContent = message; $('errorBanner').classList.remove('hidden'); }
function clearError() { $('errorBanner').textContent = ''; $('errorBanner').classList.add('hidden'); }
function setBusy(busy) { $('convertBtn').disabled = busy; $('convertBtn').innerHTML = busy ? '<span class="button-spark">✦</span> Converting…' : '<span class="button-spark">✦</span> Convert to DAX <span class="button-arrow">→</span>'; }
function updateCount() { $('charCount').textContent = `${$('tableauExpression').value.length} characters`; }
function renderResult(data) {
  state.lastResult = data;
  $('daxExpression').value = data.dax || '';
  $('copyBtn').disabled = !data.dax;
  $('resultStatus').textContent = data.method === 'gemini-fallback' ? 'Gemini-assisted · review output' : data.needs_ai ? 'Complex expression · needs review' : 'Local conversion · no API call';
  $('methodBadge').textContent = data.method === 'gemini-fallback' ? 'GEMINI FALLBACK' : data.needs_ai ? 'NEEDS REVIEW' : 'LOCAL RULES';
  $('methodBadge').classList.toggle('ai', data.method === 'gemini-fallback');
  $('explanationText').textContent = data.explanation || '';
  const warnings = data.warnings || [];
  $('warningsList').replaceChildren();
  warnings.forEach((warning) => { const item = document.createElement('div'); item.className = 'warning-item'; item.textContent = `⚠ ${warning}`; $('warningsList').appendChild(item); });
  $('resultDetails').classList.remove('hidden');
}
async function convertExpression() {
  clearError();
  const expression = $('tableauExpression').value.trim();
  if (!expression) { setError('Paste a Tableau expression first.'); $('tableauExpression').focus(); return; }
  setBusy(true);
  try {
    const response = await fetch('/api/convert', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expression, table_name: $('tableName').value.trim(), calculated_field_name: $('fieldName').value.trim(), model_context: $('modelContext').value.trim(), use_ai: $('useAi').checked }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Conversion failed.');
    renderResult(data);
  } catch (error) { setError(error.message || 'Could not reach the conversion service. Check that the backend is running.'); }
  finally { setBusy(false); }
}
function resetWorkspace() {
  $('tableauExpression').value = ''; $('daxExpression').value = ''; $('fieldName').value = ''; $('tableName').value = ''; $('modelContext').value = '';
  $('copyBtn').disabled = true; $('resultStatus').textContent = 'Waiting for expression'; $('resultDetails').classList.add('hidden'); $('advancedFields').classList.add('hidden'); $('advancedBtn').textContent = '+ Model context'; $('advancedBtn').setAttribute('aria-expanded', 'false'); clearError(); updateCount();
}
async function copyDax() {
  const text = $('daxExpression').value;
  if (!text) return;
  try { await navigator.clipboard.writeText(text); $('copyBtn').textContent = '✓ Copied'; setTimeout(() => $('copyBtn').textContent = '▢ Copy DAX', 1400); }
  catch (_) { $('daxExpression').select(); document.execCommand('copy'); }
}
function downloadCsv(rows, originalName) {
  if (!rows || !rows.length) return;
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const quote = (value) => { const s = value == null ? '' : String(value); return `"${s.replace(/"/g, '""')}"`; };
  const csv = [columns.map(quote).join(','), ...rows.map(row => columns.map(col => quote(row[col])).join(','))].join('\r\n');
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${(originalName || 'tableau_expressions').replace(/\.(xlsx|xls|csv)$/i, '')}_dax_converted.csv`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
async function convertFile() {
  const file = state.file; if (!file) return;
  $('bulkConvertBtn').disabled = true; $('bulkConvertBtn').textContent = 'Converting file…'; $('bulkMessage').textContent = 'Processing expressions. Complex rows use Gemini only when enabled.';
  try {
    const form = new FormData(); form.append('file', file); form.append('expression_column', $('expressionColumn').value.trim()); form.append('table_name', $('bulkTableName').value.trim()); form.append('use_ai', String($('bulkUseAi').checked));
    const response = await fetch('/api/convert-file', { method: 'POST', body: form }); const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Bulk conversion failed.');
    state.bulkRows = data.rows; const converted = data.rows.filter(row => String(row['Conversion Status'] || '').includes('Converted') || String(row['Conversion Status'] || '').includes('AI converted')).length;
    $('bulkMessage').textContent = `Processed ${data.count} rows. ${converted} converted; ${data.count - converted} skipped or flagged for review.`;
    const download = document.createElement('a'); download.href = '#'; download.className = 'download-link'; download.textContent = '↓ Download converted CSV'; download.addEventListener('click', (event) => { event.preventDefault(); downloadCsv(state.bulkRows, file.name); }); $('bulkMessage').appendChild(document.createElement('br')); $('bulkMessage').appendChild(download);
  } catch (error) { $('bulkMessage').textContent = error.message || 'Could not process the file.'; }
  finally { $('bulkConvertBtn').disabled = !state.file; $('bulkConvertBtn').innerHTML = 'Convert file <span>→</span>'; }
}
function acceptFile(file) {
  if (!file) return;
  if (!/\.(xlsx|xls|csv)$/i.test(file.name)) { $('bulkMessage').textContent = 'Please choose an .xlsx, .xls, or .csv file.'; return; }
  if (file.size > 10 * 1024 * 1024) { $('bulkMessage').textContent = 'File is larger than 10 MB.'; return; }
  state.file = file; $('fileName').textContent = file.name; $('bulkConvertBtn').disabled = false; $('bulkMessage').textContent = '';
}
$('tableauExpression').addEventListener('input', updateCount);
$('convertBtn').addEventListener('click', convertExpression);
$('clearBtn').addEventListener('click', resetWorkspace);
$('copyBtn').addEventListener('click', copyDax);
$('exampleBtn').addEventListener('click', () => { $('tableauExpression').value = "IF SUM([Sales]) > 1000 THEN 'High' ELSE 'Standard' END"; $('fieldName').value = 'Sales Segment'; $('tableName').value = 'Sales_Data'; updateCount(); $('tableauExpression').focus(); });
$('advancedBtn').addEventListener('click', () => { const open = $('advancedFields').classList.toggle('hidden') === false; $('advancedBtn').textContent = open ? '− Hide context' : '+ Model context'; $('advancedBtn').setAttribute('aria-expanded', String(open)); });
$('bulkToggle').addEventListener('click', () => { const open = $('bulkPanel').classList.toggle('hidden') === false; $('bulkToggle').innerHTML = open ? 'Hide upload <span>↑</span>' : 'Upload expressions <span>→</span>'; });
$('browseBtn').addEventListener('click', () => $('bulkFile').click());
$('bulkFile').addEventListener('change', event => acceptFile(event.target.files[0]));
$('bulkConvertBtn').addEventListener('click', convertFile);
const dropZone = $('dropZone');
['dragenter', 'dragover'].forEach(eventName => dropZone.addEventListener(eventName, event => { event.preventDefault(); dropZone.classList.add('dragover'); }));
['dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, event => { event.preventDefault(); dropZone.classList.remove('dragover'); }));
dropZone.addEventListener('drop', event => acceptFile(event.dataTransfer.files[0]));
$('tableauExpression').addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') convertExpression(); });
updateCount(); checkHealth();
