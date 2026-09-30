'use client';
import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronDown, FlaskConical, FolderOpen, HelpCircle, History, Info, LoaderCircle, Plus, ShieldCheck, SlidersHorizontal, Sparkles, Table2, Trash2, TriangleAlert, Upload, X } from 'lucide-react';
import { api, ApiError, downloadJson, setCsrf } from '@/lib/api';
import { date, number, ruleTitles, unit } from '@/lib/format';
import { freshDraft, samples, type Draft } from '@/lib/examples';
import type { Analysis, AnalysisRequest, AnalysisSummary, Dataset, Explanation, Page, Point, Project, Row, Session } from '@/lib/types';
import { Chart } from './chart';

const transforms = [{ value: 'identity', label: 'Unchanged', math: 'x' }, { value: 'square', label: 'Square', math: 'x²' }, { value: 'square_root', label: 'Square root', math: '√x' }, { value: 'reciprocal', label: 'Reciprocal', math: '1/x' }] as const;
const numericPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,4})?$/;
const clone = <T,>(value: T): T => structuredClone(value);

function rowsFromDraft(draft: Draft): Row[] {
  if (draft.rows.length < 2 || draft.rows.length > 5000) throw new Error('Include between 2 and 5,000 measurements.');
  return draft.rows.map((row, i) => {
    const cells = row.map(raw => {
      raw = raw.trim();
      if (!numericPattern.test(raw) || raw.length > 64 || !Number.isFinite(Number(raw)) || Math.abs(Number(raw)) > 1e100) throw new Error(`Row ${i + 1}: enter a finite number in each cell.`);
      return { raw, value: Number(raw) };
    });
    return { x: cells[0], y: cells[1] };
  });
}

export function Workspace() {
  const [session, setSession] = useState<Session | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [draft, setDraft] = useState<Draft>(() => clone(samples.acceleration));
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState('Opening workspace');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [tab, setTab] = useState<'analysis' | 'history'>('analysis');
  const [table, setTable] = useState<'derived' | 'raw'>('derived');
  const [tablePage, setTablePage] = useState(0);
  const [digits, setDigits] = useState(6);
  const [savedFingerprint, setSavedFingerprint] = useState('');
  const [resultFingerprint, setResultFingerprint] = useState('');
  const [editorPage, setEditorPage] = useState(0);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [help, setHelp] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<'project' | 'workspace' | null>(null);
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const uploadDialog = useRef<HTMLDialogElement>(null);
  const helpDialog = useRef<HTMLDialogElement>(null);
  const initialized = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const inputKey = useRef<{ fingerprint: string; project: string; dataset: string; analysis: string } | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const dataFingerprint = JSON.stringify({ columns: draft.columns, rows: draft.rows, name: draft.name });
  const fingerprint = JSON.stringify(draft);
  const stale = !!result && resultFingerprint !== fingerprint;
  const blocked = !!busy || !session;

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    void (async () => {
      try {
        const current = await api<Session>('/session'); setSession(current); setCsrf(current.csrf.token);
        const list = await api<Page<Project>>('/projects?limit=50'); setProjects(list.items);
      } catch (e) { showError(e); }
      finally { setBusy(''); }
    })();
  }, []);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => {
    if (confirmDelete) deleteDialog.current?.showModal(); else deleteDialog.current?.close();
  }, [confirmDelete]);
  useEffect(() => { if (uploadFile) uploadDialog.current?.showModal(); else uploadDialog.current?.close(); }, [uploadFile]);
  useEffect(() => { if (help) helpDialog.current?.showModal(); else helpDialog.current?.close(); }, [help]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (project && dataFingerprint !== savedFingerprint) { e.preventDefault(); } };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [project, dataFingerprint, savedFingerprint]);

  function showError(e: unknown) {
    const message = e instanceof Error ? e.message : 'Something went wrong. Please retry.';
    setError(e instanceof ApiError && e.requestId ? `${message} Reference: ${e.requestId.slice(0, 8)}.` : message);
  }
  async function perform(label: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(label); setError(''); setNotice('');
    try { await action(); } catch (e) { showError(e); } finally { setBusy(''); }
  }
  function update<K extends keyof Draft>(key: K, value: Draft[K]) { setDraft(current => ({ ...current, [key]: value, sample: key === 'title' ? current.sample : false })); }
  function reset(next: Draft) {
    if (project && dataFingerprint !== savedFingerprint && !window.confirm('Leave these unsaved measurement edits? Saved versions will remain available.')) return;
    setDraft(clone(next)); setProject(null); setDataset(null); setDatasets([]); setResult(null); setExplanation(null);
    setHistory([]); setHistoryCursor(null); setSavedFingerprint(''); setResultFingerprint(''); setEditorPage(0); setError(''); setNotice(''); setTab('analysis');
    inputKey.current = null;
  }
  async function refreshProjects() { const list = await api<Page<Project>>('/projects?limit=50'); setProjects(list.items); }
  async function refreshHistory(id: string) {
    const list = await api<Page<AnalysisSummary>>(`/projects/${id}/analyses?limit=20`); setHistory(list.items); setHistoryCursor(list.next_cursor);
  }
  async function loadDataset(id: string, saved: Dataset): Promise<Draft> {
    const first = await api<Dataset>(`/projects/${id}/datasets/${saved.id}`);
    const rows = [...(first.rows || [])];
    let offset = first.next_offset;
    while (offset !== null && offset !== undefined) {
      const next = await api<Dataset>(`/projects/${id}/datasets/${saved.id}?offset=${offset}`); rows.push(...(next.rows || [])); offset = next.next_offset;
    }
    const columns = [...first.columns].sort((a, b) => a.role === 'independent' ? -1 : b.role === 'independent' ? 1 : 0)
      .map(c => ({ role: c.role, position: c.position, name: c.name, symbol: c.symbol, unit_input: c.unit_input }));
    const next = { ...freshDraft(), title: project?.title || draft.title, name: first.display_name, columns,
      rows: rows.map(r => [r.x.raw, r.y.raw] as [string, string]) };
    setDataset({ ...first, rows });
    setSavedFingerprint(JSON.stringify({ columns: next.columns, rows: next.rows, name: next.name }));
    setEditorPage(0); setTablePage(0);
    return next;
  }
  async function openProject(selected: Project) {
    if (project && dataFingerprint !== savedFingerprint && !window.confirm('Leave these unsaved measurement edits?')) return;
    await perform('Opening experiment', async () => {
      setProject(selected); setResult(null); setExplanation(null); setTab('analysis');
      const list = await api<Page<Dataset>>(`/projects/${selected.id}/datasets?limit=50`); setDatasets(list.items);
      let current = { ...freshDraft(), title: selected.title };
      if (list.items[0]) current = { ...(await loadDataset(selected.id, list.items[0])), title: selected.title };
      else { setDataset(null); setSavedFingerprint(''); }
      setDraft(current);
      await refreshHistory(selected.id);
      setNotice('Experiment opened. Choose a saved analysis from History, or run a new one.');
    });
  }
  async function ensureProject(key: string): Promise<Project> {
    if (project) return project;
    if (!draft.title.trim()) throw new Error('Give this experiment a title.');
    const saved = await api<Project>('/projects', { method: 'POST', data: { title: draft.title.trim(), course_label: null, unit_label: null }, key });
    setProject(saved); return saved;
  }
  async function analyze() {
    await perform('Checking measurements', async () => {
      const rows = rowsFromDraft(draft);
      if (draft.intercept === 'fixed_zero' && draft.rationale.trim().length < 10) throw new Error('Explain the zero-intercept assumption in at least 10 characters.');
      const shift = draft.shift.trim() ? Number(draft.shift) : null;
      if (shift !== null && !Number.isFinite(shift)) throw new Error('The origin shift must be a finite number.');
      if (!inputKey.current || inputKey.current.fingerprint !== fingerprint) inputKey.current = { fingerprint, project: crypto.randomUUID(), dataset: crypto.randomUUID(), analysis: crypto.randomUUID() };
      const keys = inputKey.current;
      const savedProject = await ensureProject(keys.project);
      let savedDataset = dataset;
      if (!savedDataset || savedFingerprint !== dataFingerprint) {
        setBusy('Saving a new data version');
        savedDataset = await api<Dataset>(`/projects/${savedProject.id}/datasets/manual`, { method: 'POST', data: { display_name: draft.name, columns: draft.columns, rows }, key: keys.dataset });
        setDataset({ ...savedDataset, rows }); setSavedFingerprint(dataFingerprint);
        const list = await api<Page<Dataset>>(`/projects/${savedProject.id}/datasets?limit=50`); setDatasets(list.items);
      }
      setBusy('Analyzing your measurements');
      const request: AnalysisRequest = { dataset_version_id: savedDataset.id,
        x_transform: { kind: draft.transform, input_role: 'independent', time_origin_shift: shift },
        y_transform: { kind: 'identity', input_role: 'dependent', time_origin_shift: null },
        model: { family: draft.family, intercept_policy: draft.intercept, intercept_rationale: draft.intercept === 'fixed_zero' ? draft.rationale.trim() : null, fit_method: 'ordinary_least_squares' },
        student_claim: draft.claim.trim() ? { coefficient_key: draft.claimKey, unit_input: draft.claim.trim() } : null, display_precision: digits };
      const output = await api<Analysis>(`/projects/${savedProject.id}/analyses`, { method: 'POST', data: request, key: keys.analysis });
      setResult(output); setResultFingerprint(fingerprint); setExplanation(null); setTab('analysis'); setTablePage(0);
      setNotice(output.status === 'succeeded' ? 'Analysis saved. Check the findings before interpreting your coefficients.' : 'Analysis saved with findings. No invalid rows were dropped.');
      await refreshHistory(savedProject.id); await refreshProjects();
    });
  }
  async function openAnalysis(item: AnalysisSummary) {
    if (!project) return;
    await perform('Opening saved analysis', async () => {
      const output = await api<Analysis>(`/projects/${project.id}/analyses/${item.id}`);
      const selected = await api<Dataset>(`/projects/${project.id}/datasets/${item.dataset_version_id}`);
      const data = await loadDataset(project.id, selected);
      const conf = item.configuration;
      const next: Draft = { ...data, title: project.title, transform: conf.x_transform.kind, family: conf.model.family,
        intercept: conf.model.intercept_policy, rationale: conf.model.intercept_rationale || '', shift: conf.x_transform.time_origin_shift?.toString() || '',
        claim: conf.student_claim?.unit_input || '', claimKey: conf.student_claim?.coefficient_key || 'linear' };
      setDraft(next); setResult(output); setResultFingerprint(JSON.stringify(next)); setExplanation(null); setTab('analysis');
      setNotice('Viewing the original saved result. It has not been recalculated.');
    });
  }
  async function importCsv() {
    if (!uploadFile) return;
    await perform('Importing measurements', async () => {
      const saved = await ensureProject(crypto.randomUUID());
      const form = new FormData(); form.append('file', uploadFile);
      form.append('metadata', JSON.stringify({ display_name: uploadName || 'Imported measurements', columns: draft.columns }));
      const imported = await api<Dataset>(`/projects/${saved.id}/datasets/csv`, { method: 'POST', data: form });
      const next = await loadDataset(saved.id, imported); setDraft({ ...next, title: saved.title });
      setResult(null); setExplanation(null); setUploadFile(null); setNotice('CSV imported as an immutable data version. Select a model to analyze it.');
      const list = await api<Page<Dataset>>(`/projects/${saved.id}/datasets?limit=50`); setDatasets(list.items); await refreshProjects();
    });
  }
  async function exportResult() {
    if (!project || !result) return;
    await perform('Preparing reproducibility bundle', async () => {
      const bundle = await api<{ filename: string; content_json: string; sha256: string }>(`/projects/${project.id}/analyses/${result.analysis.id}/exports`, { method: 'POST', data: { format: 'json', include_explanation_id: null } });
      downloadJson(bundle.filename, bundle.content_json, bundle.sha256); setNotice('Export downloaded with raw measurements, settings, results, and integrity checks.');
    });
  }
  async function remove() {
    const kind = confirmDelete; setConfirmDelete(null);
    await perform('Deleting saved data', async () => {
      if (kind === 'workspace') { await api('/session', { method: 'DELETE' }); window.location.reload(); return; }
      if (project) await api(`/projects/${project.id}`, { method: 'DELETE' });
      setProject(null); setDataset(null); setDatasets([]); setResult(null); setHistory([]); setDraft(freshDraft()); setSavedFingerprint('');
      await refreshProjects(); setNotice('Experiment and all of its measurements, analyses, and explanations deleted.');
    });
  }

  const x = draft.columns.find(c => c.role === 'independent')!;
  const y = draft.columns.find(c => c.role === 'dependent')!;
  const preview: Point[] = draft.rows.flatMap(([a, b], i) => numericPattern.test(a) && numericPattern.test(b) && Number.isFinite(Number(a)) && Number.isFinite(Number(b))
    ? [{ point_index: i, transformed_x: Number(a), transformed_y: Number(b), predicted_y: Number(b), residual: 0 }] : []);
  const successful = result?.status === 'succeeded';
  const graphX = successful ? dataset?.columns.find(c => c.role === 'independent') || x : x;
  const graphY = successful ? dataset?.columns.find(c => c.role === 'dependent') || y : y;
  const points = successful ? result.series || [] : preview;
  const visibleRows = table === 'derived' && successful ? result.series || [] : dataset?.rows || [];
  const displayData = Array.isArray(visibleRows) ? visibleRows.slice(tablePage * 20, tablePage * 20 + 20) : [];
  const transformLabel = transforms.find(t => t.value === (successful ? result.analysis.configuration.x_transform.kind : draft.transform))!;

  return <div className="app-shell">
    <aside className="sidebar" aria-label="Workspace navigation">
      <a className="brand" href="/" aria-label="LabLens home"><span className="brand-icon"><Activity size={25} /></span>Lab<span>Lens</span></a>
      <div className="sidebar-section-label">YOUR LAB NOTEBOOK</div>
      <button className="new-project" disabled={blocked} onClick={() => reset(freshDraft())}><Plus size={18} /> New experiment</button>
      <nav className="project-list" aria-label="Saved experiments">{projects.length === 0 ? <div className="sidebar-empty"><FolderOpen size={24} /><p>Your experiments will appear here after you analyze or import data.</p></div> : projects.map(p => <button className={`project-link ${project?.id === p.id ? 'selected' : ''}`} key={p.id} onClick={() => void openProject(p)} disabled={blocked}><FlaskConical size={17} /><span>{p.title}<small>{p.latest_dataset_version ? `${p.latest_dataset_version} data version${p.latest_dataset_version === 1 ? '' : 's'}` : 'No measurements yet'}</small></span></button>)}</nav>
      <div className="sidebar-bottom"><div className="private-note"><ShieldCheck size={19} /><div><strong>Your private workspace</strong><p>No name or school required. Export before clearing cookies.</p>{session && <small>Saved until {date(session.principal.expires_at)}</small>}</div></div>
        <button className="sidebar-help" onClick={() => setHelp(true)}><BookOpen size={17} />How LabLens works</button><a className="sidebar-help" href="/privacy"><ShieldCheck size={17} />Privacy & data</a>
        <span className="sidebar-footer">BUILT FOR THE MOMENT IT CLICKS.</span>
      </div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><FlaskConical size={17} /><span>Lab notebook</span><span>/</span><strong>{project ? 'Saved experiment' : 'New experiment'}</strong></div><button className="help-button" aria-label="Quick guide" onClick={() => setHelp(true)}><HelpCircle size={18} /><span>Quick guide</span></button></header>
      <main id="main" className="workspace">
        <div className="workspace-title"><div><div className="eyebrow">EXPERIMENT WORKSPACE</div><h1>{project?.title || draft.title}</h1><p>Make sense of your measurements. Keep your assumptions visible.</p></div><button className="button secondary export-button" onClick={() => void exportResult()} disabled={blocked || !result}><ArrowDownToLine size={17} />Export result</button></div>
        <div className="workspace-bar"><div className="workspace-tabs" aria-label="Workspace view"><button aria-pressed={tab === 'analysis'} onClick={() => setTab('analysis')}><SlidersHorizontal size={16} />Analysis</button><button aria-pressed={tab === 'history'} onClick={() => setTab('history')}><History size={16} />History<span className="count-badge">{history.length}{historyCursor ? '+' : ''}</span></button></div><span className="save-status">{busy ? <><LoaderCircle size={14} className="spin" />{busy}</> : dataset && dataFingerprint === savedFingerprint ? <><Check size={14} />Data version {dataset.version_number} saved</> : <>Unsaved measurements</>}</span></div>
        {error && <div className="message error-message" role="alert" tabIndex={-1} ref={errorRef}><TriangleAlert size={19} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={18} /></button></div>}
        <div className="sr-only" role="status" aria-live="polite">{busy || notice}</div>
        {notice && <div className="message notice-message"><Check size={17} /><span>{notice}</span></div>}
        {tab === 'history' ? <section className="panel history-panel"><div className="panel-header"><h2>Saved analyses</h2><span className="pill">Immutable results</span></div><p className="muted">Each run preserves its data version, model choices, and findings. Opening a result never recalculates it.</p>
          {history.length ? <div className="history-list">{history.map(item => <button key={item.id} disabled={blocked} onClick={() => void openAnalysis(item)}><span className={`history-status ${item.status}`}><Activity size={18} /></span><span><strong>{item.configuration.model.family === 'linear' ? 'Linear' : 'Quadratic'} · {transforms.find(t => t.value === item.configuration.x_transform.kind)?.label} x</strong><small>{item.configuration.model.intercept_policy === 'free' ? 'Free intercept' : 'Zero intercept'} · {date(item.created_at)} · {item.id.slice(0, 8)}</small></span><span className={`pill ${item.status === 'succeeded' ? 'teal' : 'amber'}`}>{item.status}</span><ArrowRight size={18} /></button>)}</div> : <div className="empty-state"><History size={36} /><h3>No analyses yet</h3><p>Run an analysis to keep a reproducible record of your work.</p><button className="button primary" onClick={() => setTab('analysis')}>Back to measurements</button></div>}
          {historyCursor && <button className="button secondary" disabled={blocked} onClick={() => void perform('Loading history', async () => { const page = await api<Page<AnalysisSummary>>(`/projects/${project!.id}/analyses?cursor=${encodeURIComponent(historyCursor)}`); setHistory(h => [...h, ...page.items]); setHistoryCursor(page.next_cursor); })}>Load more analyses</button>}
          {project && <div className="danger-zone"><p>Deleting this experiment removes every data version and result.</p><button className="button danger" disabled={blocked} onClick={() => setConfirmDelete('project')}><Trash2 size={16} />Delete experiment</button></div>}
        </section> : <div className="analysis-layout">
          <section className="input-panel panel" aria-label="Measurement and model settings">
            <div className="panel-header"><h2><span className="step-number">1</span>Measurements</h2><span className="mono subtle">{draft.rows.length} rows</span></div>
            <div className="sample-picker"><label htmlFor="sample-select">Explore a sample</label><div className="select-wrap"><select id="sample-select" disabled={blocked} value="" onChange={e => { if (e.target.value) reset(samples[e.target.value]); }}><option value="">Choose an example…</option><option value="acceleration">Acceleration & time · unit check</option><option value="spring">Spring extension · cm to m</option><option value="reciprocal">Reciprocal · domain check</option></select><ChevronDown size={15} /></div>{draft.sample && <small>Sample loaded · synthetic data, not student records</small>}</div>
            <label className="field">Experiment title<input value={draft.title} maxLength={120} disabled={!!project || blocked} onChange={e => update('title', e.target.value)} /></label>
            <div className="variables-grid">{draft.columns.map((col, index) => <div key={col.role} className="variable-card"><span className="variable-type">{col.role === 'independent' ? 'X · INDEPENDENT' : 'Y · DEPENDENT'}</span><label className="field">Variable name<input aria-label={`${col.role === 'independent' ? 'X' : 'Y'} variable name`} value={col.name} maxLength={64} disabled={blocked} onChange={e => update('columns', draft.columns.map((c, i) => i === index ? { ...c, name: e.target.value } : c))} /></label><label className="field">Unit<input aria-label={`${col.role === 'independent' ? 'X' : 'Y'} unit`} value={col.unit_input} maxLength={64} disabled={blocked} onChange={e => update('columns', draft.columns.map((c, i) => i === index ? { ...c, unit_input: e.target.value } : c))} placeholder="e.g. m/s^2" /></label></div>)}</div>
            <div className="measurement-table-wrap"><table className="measurement-table"><caption className="sr-only">Editable raw measurements</caption><thead><tr><th scope="col">#</th><th scope="col">{x.name || 'x'} <span>({x.unit_input})</span></th><th scope="col">{y.name || 'y'} <span>({y.unit_input})</span></th><th scope="col"><span className="sr-only">Remove row</span></th></tr></thead><tbody>{draft.rows.slice(editorPage * 20, editorPage * 20 + 20).map((row, i) => { const at = editorPage * 20 + i; return <tr key={at}><th scope="row">{at + 1}</th>{row.map((value, axis) => <td key={axis}><input aria-label={`Row ${at + 1} ${axis === 0 ? 'x' : 'y'}`} inputMode="decimal" value={value} disabled={blocked} onChange={e => update('rows', draft.rows.map((r, index) => index === at ? axis === 0 ? [e.target.value, r[1]] : [r[0], e.target.value] : r))} /></td>)}<td><button className="row-delete" aria-label={`Remove row ${at + 1}`} disabled={blocked || draft.rows.length <= 2} onClick={() => { update('rows', draft.rows.filter((_, n) => n !== at)); if (i === 0 && editorPage) setEditorPage(editorPage - 1); }}><X size={13} /></button></td></tr>; })}</tbody></table></div>
            {draft.rows.length > 20 && <div className="pagination"><button disabled={!editorPage || blocked} onClick={() => setEditorPage(p => p - 1)}>Previous</button><span>{editorPage + 1} / {Math.ceil(draft.rows.length / 20)}</span><button disabled={(editorPage + 1) * 20 >= draft.rows.length || blocked} onClick={() => setEditorPage(p => p + 1)}>Next</button></div>}
            <div className="table-actions"><button disabled={blocked || draft.rows.length >= 5000} onClick={() => { update('rows', [...draft.rows, ['', '']]); setEditorPage(Math.floor(draft.rows.length / 20)); }}><Plus size={15} />Add row</button><button disabled={blocked} onClick={() => fileInput.current?.click()}><Upload size={15} />Import CSV</button><input ref={fileInput} type="file" accept=".csv,text/csv" className="sr-only" tabIndex={-1} aria-label="Choose CSV file" onChange={e => { const file = e.target.files?.[0]; if (file) { if (file.size > 1048576) setError('CSV files must be 1 MiB or smaller.'); else { setUploadFile(file); setUploadName(file.name.replace(/\.csv$/i, '')); } } e.target.value = ''; }} /></div>
            {datasets.length > 1 && <label className="field versions">Saved data version<select value={dataset?.id || ''} disabled={blocked} onChange={e => { const selected = datasets.find(d => d.id === e.target.value); if (selected && project) void perform('Opening data version', async () => { const next = await loadDataset(project.id, selected); setDraft(next); setResult(null); }); }}>{datasets.map(d => <option key={d.id} value={d.id}>v{d.version_number} · {d.row_count} rows · {d.display_name}</option>)}</select></label>}
            <div className="panel-divider" />
            <div className="panel-header"><h2><span className="step-number">2</span>Model & assumptions</h2></div>
            <fieldset className="transform-picker"><legend>Transform x</legend><div>{transforms.map(t => <button key={t.value} title={t.label} disabled={blocked} aria-pressed={draft.transform === t.value} onClick={() => update('transform', t.value)}><span>{t.math}</span><small>{t.label}</small></button>)}</div></fieldset>
            <div className="form-two"><label className="field">Model<select value={draft.family} disabled={blocked} onChange={e => { update('family', e.target.value as Draft['family']); if (e.target.value === 'linear') update('claimKey', 'linear'); }}><option value="linear">Linear</option><option value="quadratic">Quadratic</option></select></label><label className="field">Intercept<select value={draft.intercept} disabled={blocked} onChange={e => update('intercept', e.target.value as Draft['intercept'])}><option value="free">Fit freely</option><option value="fixed_zero">Fix at zero</option></select></label></div>
            <div className="model-equation" aria-label="Model equation"><span>y = </span>{draft.intercept === 'free' && <>b₀ + </>}b₁z{draft.family === 'quadratic' && <> + b₂z²</>}<small>z = {transforms.find(t => t.value === draft.transform)?.math}{draft.shift && ' after origin shift'}</small></div>
            {draft.intercept === 'fixed_zero' && <label className="field rationale">Why should the intercept be zero?<textarea value={draft.rationale} minLength={10} maxLength={280} rows={2} disabled={blocked} onChange={e => update('rationale', e.target.value)} placeholder="State the physical assumption, not just that the line looks better." /><small>10–280 characters. LabLens records this assumption; it does not validate it.</small></label>}
            <details className="advanced"><summary>Origin shift & coefficient unit check</summary><label className="field">Subtract an origin from x ({x.unit_input})<input value={draft.shift} disabled={blocked} onChange={e => update('shift', e.target.value)} inputMode="decimal" placeholder="Optional · e.g. 0.5" /><small>Applied before transforming x.</small></label><label className="field">Your expected coefficient unit<input value={draft.claim} disabled={blocked} onChange={e => update('claim', e.target.value)} placeholder="Optional · e.g. m/s^4" /></label>{draft.family === 'quadratic' && <label className="field">Coefficient to check<select value={draft.claimKey} onChange={e => update('claimKey', e.target.value as Draft['claimKey'])}><option value="linear">Linear term b₁</option><option value="quadratic">Quadratic term b₂</option></select></label>}</details>
            <button className="button primary analyze-button" disabled={blocked} onClick={() => void analyze()}>{busy ? <LoaderCircle className="spin" size={19} /> : <Activity size={19} />}{busy || 'Analyze measurements'}{!busy && <ArrowRight size={17} />}</button>
            <p className="input-footnote"><ShieldCheck size={13} />Use measurement values only. No personal information.</p>
          </section>
          <section className="output-column" aria-label="Analysis results">
            {stale && <div className="message stale-message"><Info size={18} /><span>Settings have changed. This is the previous saved result; run a new analysis to apply your edits.</span></div>}
            {!result && <div className="learning-banner"><span className="banner-icon"><Sparkles size={21} /></span><div><strong>A good fit is only part of the story.</strong><p>Does the slope have the right units? Does zero really mean zero? Start with a sample and check your reasoning.</p></div></div>}
            {result && result.status !== 'succeeded' && <div className="rejected-banner"><TriangleAlert size={25} /><div><h2>{result.status === 'rejected' ? 'Let’s check the setup first' : 'This analysis could not finish'}</h2><p>{result.status === 'rejected' ? 'The data or model failed a required check. No coefficients were fitted, and no measurements were dropped.' : 'The saved data remains intact. Review the findings and try a new analysis.'}</p></div></div>}
            <Chart points={points} xLabel={successful ? `${graphX.name}${result.analysis.configuration.x_transform.kind === 'identity' ? '' : ` · ${transformLabel.math}`}` : x.name} yLabel={graphY.name} xUnit={successful ? result.provenance.transformed_x_unit || x.unit_input : x.unit_input} yUnit={successful ? result.provenance.canonical_units.y : y.unit_input} fitted={!!successful} summary={result?.chart_summary} />
            {successful && <>
              <div className="metrics-row"><div><span>R² <span className="metric-hint">· centered</span></span><strong>{number(result.metrics?.r_squared, digits)}</strong><small>{result.metrics?.r_squared === null ? 'All y values are identical' : 'Goodness of fit, not physical proof'}</small></div><div><span>Root mean squared error</span><strong>{number(result.metrics?.rmse, digits)} <em>{unit(result.provenance.canonical_units.y)}</em></strong><small>In the same units as y</small></div><div><span>Measurements</span><strong>{result.metrics?.n}<em> / {result.metrics?.n}</em></strong><small>Every source row included</small></div></div>
              <section className="panel coefficients"><div className="panel-header"><h2>What the coefficients mean</h2><label className="precision">Digits<select aria-label="Significant digits" value={digits} onChange={e => setDigits(Number(e.target.value))}>{[3,4,5,6,7,8,9,10].map(n => <option key={n}>{n}</option>)}</select></label></div>
                <div className="coefficient-list">{result.coefficients?.map(c => <div className="coefficient" key={c.key}><div><span className="coefficient-symbol">{c.key === 'intercept' ? 'b₀' : c.key === 'linear' ? 'b₁' : 'b₂'}</span><div><strong>{c.key === 'intercept' ? 'Intercept' : c.key === 'linear' ? 'Linear coefficient' : 'Quadratic coefficient'}</strong><small>{c.ordinal === 0 ? 'y unit' : `y unit ÷ transformed x unit${c.ordinal === 2 ? '²' : ''}`}</small></div></div><div className="coefficient-value"><strong>{number(c.value, digits)} <span>{unit(c.unit)}</span></strong><small>Standard error {number(c.standard_error, digits)} {unit(c.unit)}</small></div></div>)}</div>
                {result.analysis.configuration.model.intercept_policy === 'fixed_zero' && <div className="fixed-intercept"><span>b₀ = 0</span><small>Fixed by assumption · not a fitted coefficient</small></div>}
                <p className="small-print">Standard errors describe uncertainty under ordinary least-squares assumptions. They are not measurement accuracy.</p>
              </section>
            </>}
            {result && <section className="panel findings-panel"><div className="panel-header"><h2><span className="step-number">3</span>Check your reasoning</h2><span className="pill">{result.findings.length} findings</span></div><div className="findings-list">{result.findings.map(f => <article className={`finding ${f.severity}`} key={f.rule_id}>{f.severity === 'info' ? <Info size={19} /> : <TriangleAlert size={19} />}<div><h3>{ruleTitles[f.rule_id] || f.rule_id.split('.').pop()?.replaceAll('_', ' ').toLowerCase()}</h3><p>{f.message}</p>{f.rule_id === 'UNIT.COEFFICIENT_DIMENSION_MISMATCH' && <div className="unit-comparison"><span>Your unit <b>{unit(String(f.evidence.claimed_unit))}</b></span><ArrowRight size={16} /><span>Derived unit <b>{unit(String(f.evidence.derived_unit))}</b></span></div>}{Array.isArray(f.evidence.offending_indices) && <p className="evidence">Check row{(f.evidence.offending_indices as number[]).length > 1 ? 's' : ''} {(f.evidence.offending_indices as number[]).map(i => i + 1).join(', ')}{Number(f.evidence.offending_count) > 20 ? ` and ${Number(f.evidence.offending_count) - 20} more` : ''}.</p>}<details className="evidence-detail"><summary>Rule & evidence</summary><code>{f.rule_id}</code><pre>{JSON.stringify(f.evidence, null, 2)}</pre></details></div>{f.blocking && <span className="pill red">Blocks fit</span>}</article>)}</div>
              <div className="explain-box"><div><Sparkles size={19} /><div><strong>A little more explanation?</strong><p>Findings stay authoritative. Optional AI only rephrases them.</p></div></div><button className="button secondary" disabled={blocked} onClick={() => void perform('Preparing explanation', async () => { const prose = await api<Explanation>(`/projects/${project!.id}/analyses/${result.analysis.id}/explanations`, { method: 'POST', data: { reading_level: 'standard', locale: 'en-US', focus_rule_ids: null } }); setExplanation(prose); })}>{session?.capabilities.ai ? 'Explain findings' : 'Read the guide'}</button></div>
              {explanation && <div className="explanation"><span className="pill">{explanation.status === 'succeeded' ? 'AI-generated explanation · verify against findings' : 'Deterministic guide · AI unavailable'}</span><p>{explanation.status === 'succeeded' ? explanation.text : explanation.fallback_text}</p></div>}
            </section>}
            {result && <section className="panel data-panel"><div className="panel-header"><h2><Table2 size={18} />Behind the graph</h2><div className="segmented"><button aria-pressed={table === 'derived'} onClick={() => { setTable('derived'); setTablePage(0); }} disabled={!successful}>Derived</button><button aria-pressed={table === 'raw'} onClick={() => { setTable('raw'); setTablePage(0); }}>Raw data</button></div></div>
              <div className="data-table-scroll" tabIndex={0} aria-label="Scrollable data table"><table className="results-table"><caption>{table === 'derived' && successful ? 'Canonical transformed measurements and residuals' : 'Original measurements, preserved exactly as entered'}</caption><thead><tr><th scope="col">Row</th><th scope="col">{table === 'derived' && successful ? 'Transformed x' : 'Raw x'}</th><th scope="col">{table === 'derived' && successful ? 'Observed y' : 'Raw y'}</th>{table === 'derived' && successful && <><th scope="col">Predicted y</th><th scope="col">Residual</th></>}</tr></thead><tbody>{displayData.map((row, i) => <tr key={i}><th scope="row">{tablePage * 20 + i + 1}</th>{'transformed_x' in row ? <><td>{number(row.transformed_x, digits)}</td><td>{number(row.transformed_y, digits)}</td><td>{number(row.predicted_y, digits)}</td><td>{number(row.residual, digits)}</td></> : <><td>{row.x.raw}</td><td>{row.y.raw}</td></>}</tr>)}</tbody></table></div>
              {visibleRows.length > 20 && <div className="pagination"><button disabled={!tablePage} onClick={() => setTablePage(p => p - 1)}>Previous</button><span>{tablePage + 1} / {Math.ceil(visibleRows.length / 20)}</span><button disabled={(tablePage + 1) * 20 >= visibleRows.length} onClick={() => setTablePage(p => p + 1)}>Next</button></div>}
              <div className="provenance"><span>Engine {result.analysis.engine_version} · Rules {result.analysis.rule_set_version}</span><span title={result.provenance.dataset_sha256}>Data SHA-256 {result.provenance.dataset_sha256.slice(0, 12)}…</span></div>
            </section>}
            {!result && <div className="before-analysis"><div><span className="step-number">2</span><h3>Declare the model</h3><p>Choose a transformation and state your intercept assumption.</p></div><div><span className="step-number">3</span><h3>Question the result</h3><p>Inspect units and residuals before drawing a conclusion.</p></div></div>}
          </section>
        </div>}
        <footer className="workspace-footer"><span>LabLens · Your reasoning matters more than a perfect line.</span><a href="/about">About & credits</a><button disabled={blocked} onClick={() => setConfirmDelete('workspace')}>Clear this workspace</button></footer>
      </main>
    </div>
    <dialog className="modal" ref={deleteDialog} onCancel={() => setConfirmDelete(null)} aria-labelledby="delete-title"><h2 id="delete-title">Delete {confirmDelete === 'workspace' ? 'all workspace data' : 'this experiment'}?</h2><p>This permanently removes saved measurements, analyses, and explanations. Download any results you want to keep first.</p><div className="modal-actions"><button className="button secondary" onClick={() => setConfirmDelete(null)}>Keep my work</button><button className="button danger" onClick={() => void remove()}>Delete permanently</button></div></dialog>
    <dialog className="modal" ref={uploadDialog} onCancel={() => setUploadFile(null)} aria-labelledby="upload-title"><h2 id="upload-title">Import two-column CSV</h2><p>{uploadFile?.name} · {uploadFile ? number(uploadFile.size / 1024, 3) : 0} KiB</p><label className="field">Dataset name<input value={uploadName} maxLength={120} onChange={e => setUploadName(e.target.value)} /></label><p>Use UTF-8, comma-separated numbers, and these exact headers in this order:</p><code className="csv-header">{[...draft.columns].sort((a,b) => a.position-b.position).map(c => c.name).join(',')}</code><p className="small-print">Confirm the variable names and units in the measurement panel before importing. Do not upload personal information.</p>{error && <p className="modal-error" role="alert">{error}</p>}<div className="modal-actions"><button className="button secondary" disabled={!!busy} onClick={() => setUploadFile(null)}>Cancel</button><button className="button primary" disabled={blocked} onClick={() => void importCsv()}>{busy || 'Import measurements'}</button></div></dialog>
    <dialog className="modal guide-modal" ref={helpDialog} onCancel={() => setHelp(false)} aria-labelledby="help-title"><button className="modal-close" aria-label="Close quick guide" onClick={() => setHelp(false)}><X size={20} /></button><span className="eyebrow">QUICK GUIDE</span><h2 id="help-title">The reasoning behind the line</h2><ol className="guide-steps"><li><strong>Enter measurements and units.</strong><p>Use manual entry or a two-column CSV. Type units like m, cm, s, N, m/s^2, or 1 for dimensionless values.</p></li><li><strong>Choose what you want to test.</strong><p>LabLens converts to canonical units, subtracts any chosen x origin, then transforms x. The model fits the transformed x, called z.</p></li><li><strong>Read the dimensions.</strong><p>If acceleration (m/s²) is plotted against time² (s²), the slope is m/s⁴. Its numerical value alone cannot tell you what it means.</p></li><li><strong>Inspect residuals and assumptions.</strong><p>A high R² does not prove your physical model. A zero intercept needs a reason. Quadratic means b₀ + b₁z + b₂z²; for y = az², square x and use a linear model with zero intercept.</p></li><li><strong>Keep a reproducible record.</strong><p>Analyses preserve the original data and settings. Export a JSON bundle before your workspace expires or you clear browser cookies.</p></li></ol><p className="small-print">LabLens helps you examine your reasoning. It does not grade your work or write a lab conclusion.</p><button className="button primary" onClick={() => setHelp(false)}>Back to my experiment</button></dialog>
  </div>;
}
