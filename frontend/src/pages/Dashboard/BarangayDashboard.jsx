import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { useAuth } from '../../context/AuthContext';
import { barangaysApi } from '../../api/barangaysApi';
import { reportsApi } from '../../api/reportApi';
import { guidanceApi } from '../../api/guidanceApi';
import { hazardsApi } from '../../api/hazardsApi';
import { Icon, Toast, fieldErrors, formatDateTime, timeAgo } from './admin/adminShared';
import { HazardIcon, ImpactChips, StatusTag } from './reportShared';
import '../css/Dashboard.css';
import '../css/AdminDashboard.css';
import '../css/DRRMODashboard.css';
import '../css/BarangayDashboard.css';

const SEVERITIES = [
  { value: 'Low', hint: 'Minor, no immediate danger' },
  { value: 'Moderate', hint: 'Could get worse, needs watching' },
  { value: 'High', hint: 'People at risk, needs action now' },
];

const COUNTS = [
  { key: 'casualties_dead', label: 'Dead' },
  { key: 'casualties_injured', label: 'Injured' },
  { key: 'casualties_missing', label: 'Missing' },
  { key: 'displaced', label: 'Displaced' },
];

const REPORT_TABS = ['All', 'Pending', 'Validated', 'Rejected'];
const TAB_LABEL = { All: 'All', Pending: 'Awaiting review', Validated: 'Validated', Rejected: 'Rejected' };

function emptyForm(user) {
  return {
    barangay: user?.assigned_barangay?.id ? String(user.assigned_barangay.id) : '',
    hazard_type: '',
    description: '',
    severity_estimate: '',
    casualties_dead: 0,
    casualties_injured: 0,
    casualties_missing: 0,
    displaced: 0,
    position: user?.position || '',
    agency: user?.assigned_barangay?.name ? `Barangay ${user.assigned_barangay.name}` : '',
  };
}

function Stepper({ id, label, value, onChange }) {
  const n = Number(value) || 0;
  return (
    <div className="brg-stepper">
      <label htmlFor={id}>{label}</label>
      <div className="brg-stepper-box">
        <button type="button" onClick={() => onChange(Math.max(0, n - 1))} aria-label={`Fewer ${label.toLowerCase()}`} disabled={n <= 0}>−</button>
        <input
          id={id}
          type="number"
          min="0"
          inputMode="numeric"
          value={value}
          onChange={(e) => onChange(e.target.value === '' ? '' : Math.max(0, parseInt(e.target.value, 10) || 0))}
          onBlur={() => { if (value === '') onChange(0); }}
        />
        <button type="button" onClick={() => onChange(n + 1)} aria-label={`More ${label.toLowerCase()}`}>+</button>
      </div>
    </div>
  );
}

function GuidanceItem({ item }) {
  const [open, setOpen] = useState(false);
  const type = item.hazard_type_detail?.name || 'General';
  return (
    <li className={`brg-guide ${open ? 'is-open' : ''}`}>
      <button type="button" className="brg-guide-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <HazardIcon type={type} />
        <span className="brg-guide-text">
          <strong>{item.title}</strong>
          <span>{type}{item.timeline_phase ? ` · ${item.timeline_phase} the hazard` : ''}</span>
        </span>
        <Icon name="chevronRight" size={16} className="brg-guide-chevron" />
      </button>
      {open && <p className="brg-guide-body">{item.body}</p>}
    </li>
  );
}

export default function BarangayDashboard() {
  const { user } = useAuth();
  const assigned = user?.assigned_barangay;

  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [barangays, setBarangays] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [guidance, setGuidance] = useState([]);

  const [form, setForm] = useState(() => emptyForm(user));
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const [tab, setTab] = useState('All');
  const [search, setSearch] = useState('');

  const refreshReports = useCallback(() => (
    reportsApi.list()
      .then((data) => setReports(Array.isArray(data) ? data : data.results || []))
      .catch(() => setReports([]))
      .finally(() => setLoading(false))
  ), []);

  useEffect(() => {
    refreshReports();
    barangaysApi.list()
      .then((geo) => {
        const list = (geo?.features || [])
          // The GeoJSON id sits on the feature itself, not inside properties
          .map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }))
          .filter((b) => b.id != null && b.name)
          .sort((a, b) => a.name.localeCompare(b.name));
        setBarangays(list);
      })
      .catch(() => setBarangays([]));
    hazardsApi.types().then((data) => setHazardTypes(data.results || data)).catch(() => setHazardTypes([]));
    guidanceApi.list().then((data) => setGuidance((data.results || data).filter((g) => g.is_published !== false).slice(0, 4))).catch(() => setGuidance([]));
  }, [refreshReports]);

  // The signed-in user may arrive after the first render
  useEffect(() => {
    if (!user) return;
    setForm((f) => ({
      ...f,
      barangay: f.barangay || (user.assigned_barangay?.id ? String(user.assigned_barangay.id) : ''),
      position: f.position || user.position || '',
      agency: f.agency || (user.assigned_barangay?.name ? `Barangay ${user.assigned_barangay.name}` : ''),
    }));
  }, [user]);

  const clearToast = useCallback(() => setToast(null), []);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
    if (errors[field] || errors.form) setErrors((e) => ({ ...e, [field]: undefined, form: undefined }));
  }

  function validate() {
    const e = {};
    if (!form.barangay) e.barangay = 'Choose the barangay where this is happening.';
    if (!form.hazard_type) e.hazard_type = 'Choose the type of hazard.';
    if (form.description.trim().length < 10) e.description = 'Describe what you are seeing in a sentence or two.';
    if (!form.severity_estimate) e.severity_estimate = 'Choose how serious it looks.';
    return e;
  }

  async function submit(e) {
    e.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) return;

    setBusy(true);
    try {
      await reportsApi.submit({
        barangay: Number(form.barangay),
        hazard_type: Number(form.hazard_type),
        description: form.description.trim(),
        severity_estimate: form.severity_estimate,
        casualties_dead: Number(form.casualties_dead) || 0,
        casualties_injured: Number(form.casualties_injured) || 0,
        casualties_missing: Number(form.casualties_missing) || 0,
        displaced: Number(form.displaced) || 0,
        position: form.position.trim(),
        agency: form.agency.trim(),
      });
      setForm({ ...emptyForm(user), position: form.position, agency: form.agency });
      setErrors({});
      setTab('All');
      setToast({ id: Date.now(), tone: 'good', message: 'Report sent. The DRRMO will review it shortly.' });
      refreshReports();
    } catch (err) {
      setErrors(fieldErrors(err));
    } finally {
      setBusy(false);
    }
  }

  const counts = useMemo(() => {
    const c = { All: reports.length, Pending: 0, Validated: 0, Rejected: 0 };
    reports.forEach((r) => { if (c[r.status] !== undefined) c[r.status] += 1; });
    return c;
  }, [reports]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return reports
      .filter((r) => tab === 'All' || r.status === tab)
      .filter((r) => !q || [r.hazard_type_details?.name, r.barangay_details?.name, r.description, r.review_note, r.severity_estimate]
        .some((v) => (v || '').toLowerCase().includes(q)));
  }, [reports, tab, search]);

  const lastReport = reports[0];
  const barangayName = assigned?.name || barangays.find((b) => String(b.id) === String(form.barangay))?.name;

  return (
    <div className="db adm drm brg">
      <PublicNavbar />
      <div className="adm-wrap">
        <header className="adm-header">
          <div>
            <p className="adm-eyebrow">{assigned ? `Barangay ${assigned.name}` : 'Barangay personnel'}</p>
            <h1>Barangay dashboard</h1>
            <p className="adm-lede">Report incidents in your barangay to the DRRMO and follow their review.</p>
          </div>
          <div className="adm-header-side">
            <Link to="/map" className="adm-btn adm-btn-ghost adm-btn-sm drm-map-link">
              View hazard map <Icon name="arrowRight" size={15} />
            </Link>
          </div>
        </header>

        <div className="adm-metrics">
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-navy"><Icon name="list" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Reports submitted</span>
              <span className="adm-metric-value">{loading ? '—' : counts.All}</span>
              <span className="adm-metric-note">{lastReport ? `Last one ${timeAgo(lastReport.created_at).toLowerCase()}` : 'None yet'}</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-amber"><Icon name="clock" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Awaiting review</span>
              <span className="adm-metric-value">{loading ? '—' : counts.Pending}</span>
              <span className="adm-metric-note">Being checked by the DRRMO</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon adm-metric-green"><Icon name="check" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Validated</span>
              <span className="adm-metric-value">{loading ? '—' : counts.Validated}</span>
              <span className="adm-metric-note">Confirmed by the DRRMO</span>
            </div>
          </div>
          <div className="adm-metric">
            <span className="adm-metric-icon brg-metric-red"><Icon name="x" size={20} /></span>
            <div className="adm-metric-text">
              <span className="adm-metric-label">Rejected</span>
              <span className="adm-metric-value">{loading ? '—' : counts.Rejected}</span>
              <span className="adm-metric-note">{counts.Rejected ? 'See the DRRMO\'s reason' : 'None rejected'}</span>
            </div>
          </div>
        </div>

        <div className="brg-grid">
          {/* ---------- Submit form ---------- */}
          <form className="adm-card brg-form" onSubmit={submit} noValidate>
            <div className="adm-card-head">
              <div>
                <h2>Submit an incident report</h2>
                <p>Tell the DRRMO what is happening. Fields marked * are required.</p>
              </div>
            </div>

            {errors.form && <div className="adm-alert" role="alert"><Icon name="info" size={16} />{errors.form}</div>}

            <div className="brg-step">
              <h3><span className="adm-step">1</span>Where and what</h3>
              <div className={`adm-field ${errors.barangay ? 'has-error' : ''}`}>
                <label htmlFor="brg-barangay">Barangay<span className="adm-req">*</span></label>
                {assigned ? (
                  <div className="brg-locked">
                    <Icon name="building" size={16} />
                    <span><strong>{assigned.name}</strong> · your assigned barangay</span>
                  </div>
                ) : (
                  <select id="brg-barangay" value={form.barangay} onChange={(e) => set('barangay', e.target.value)}>
                    <option value="">{barangays.length ? 'Select a barangay' : 'Loading barangays…'}</option>
                    {barangays.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                )}
                {errors.barangay && <p className="adm-field-error">{errors.barangay}</p>}
              </div>

              <div className={`adm-field ${errors.hazard_type ? 'has-error' : ''}`}>
                <label>Type of hazard<span className="adm-req">*</span></label>
                <div className="brg-choice-row" role="radiogroup" aria-label="Type of hazard">
                  {hazardTypes.length === 0 && <span className="adm-muted">Loading hazard types…</span>}
                  {hazardTypes.map((t) => {
                    const checked = String(form.hazard_type) === String(t.id);
                    return (
                      <label key={t.id} className={`brg-choice ${checked ? 'is-checked' : ''}`}>
                        <input type="radio" name="hazard_type" value={t.id} checked={checked} onChange={() => set('hazard_type', String(t.id))} />
                        <HazardIcon type={t.name} size="sm" />
                        {t.name}
                      </label>
                    );
                  })}
                </div>
                {errors.hazard_type && <p className="adm-field-error">{errors.hazard_type}</p>}
              </div>
            </div>

            <div className="brg-step">
              <h3><span className="adm-step">2</span>What are you seeing?</h3>
              <div className={`adm-field ${errors.description ? 'has-error' : ''}`}>
                <label htmlFor="brg-desc">Description<span className="adm-req">*</span></label>
                <textarea
                  id="brg-desc"
                  rows={4}
                  maxLength={1000}
                  value={form.description}
                  onChange={(e) => set('description', e.target.value)}
                  placeholder="Exact location (purok or sitio), what happened, how bad it looks, and what help is needed."
                />
                <div className="brg-desc-foot">
                  {errors.description ? <p className="adm-field-error">{errors.description}</p> : <span />}
                  <span className="brg-count">{form.description.length}/1000</span>
                </div>
              </div>

              <div className={`adm-field ${errors.severity_estimate ? 'has-error' : ''}`}>
                <label>How serious is it?<span className="adm-req">*</span></label>
                <div className="brg-severity" role="radiogroup" aria-label="How serious is it">
                  {SEVERITIES.map((s) => {
                    const checked = form.severity_estimate === s.value;
                    return (
                      <label key={s.value} className={`brg-sev brg-sev-${s.value.toLowerCase()} ${checked ? 'is-checked' : ''}`}>
                        <input type="radio" name="severity" value={s.value} checked={checked} onChange={() => set('severity_estimate', s.value)} />
                        <strong>{s.value}</strong>
                        <span>{s.hint}</span>
                      </label>
                    );
                  })}
                </div>
                {errors.severity_estimate && <p className="adm-field-error">{errors.severity_estimate}</p>}
              </div>
            </div>

            <div className="brg-step">
              <h3><span className="adm-step">3</span>People affected</h3>
              <div className="brg-steppers">
                {COUNTS.map((c) => (
                  <Stepper key={c.key} id={`brg-${c.key}`} label={c.label} value={form[c.key]} onChange={(v) => set(c.key, v)} />
                ))}
              </div>
              <p className="adm-field-hint">Leave at 0 if no one was affected. Displaced means people who had to leave their homes.</p>
            </div>

            <div className="brg-step">
              <h3><span className="adm-step">4</span>Your details</h3>
              <div className="adm-form-grid adm-grid-2">
                <div className="adm-field">
                  <label htmlFor="brg-position">Position</label>
                  <input id="brg-position" value={form.position} onChange={(e) => set('position', e.target.value)} placeholder="e.g. Barangay Secretary" />
                </div>
                <div className="adm-field">
                  <label htmlFor="brg-agency">Office or agency</label>
                  <input id="brg-agency" value={form.agency} onChange={(e) => set('agency', e.target.value)} placeholder="e.g. Barangay Lagtang" />
                </div>
              </div>
              <p className="adm-field-hint">Sent as {user?.full_name || 'you'}{barangayName ? ` for Barangay ${barangayName}` : ''}.</p>
            </div>

            <div className="brg-submit">
              <button type="submit" className="adm-btn adm-btn-primary" disabled={busy}>
                <Icon name="arrowRight" size={16} />
                {busy ? 'Sending…' : 'Send report to DRRMO'}
              </button>
            </div>
          </form>

          {/* ---------- Your reports + guidance ---------- */}
          <div className="brg-side">
            <section className="adm-card adm-card-flush">
              <div className="drm-section-head">
                <h2>Your reports</h2>
                <p>Track what the DRRMO decided on each report you sent.</p>
              </div>
              <nav className="adm-tabs drm-status-tabs" role="tablist" aria-label="Report status">
                {REPORT_TABS.map((t) => (
                  <button key={t} type="button" role="tab" aria-selected={tab === t} className={`adm-tab ${tab === t ? 'is-active' : ''}`} onClick={() => setTab(t)}>
                    {TAB_LABEL[t]}
                    <span className="adm-tab-count">{counts[t]}</span>
                  </button>
                ))}
              </nav>
              <div className="adm-toolbar">
                <div className="adm-search drm-search">
                  <Icon name="search" size={16} />
                  <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search your reports…" aria-label="Search your reports" />
                </div>
              </div>

              {loading ? (
                <p className="adm-empty">Loading your reports…</p>
              ) : visible.length === 0 ? (
                <div className="adm-empty">
                  <Icon name={search ? 'search' : 'list'} size={28} />
                  <p>{search ? 'No reports match your search.' : reports.length ? 'No reports in this list.' : 'You haven\'t sent any reports yet.'}</p>
                </div>
              ) : (
                <ul className="drm-list">
                  {visible.map((r) => (
                    <li key={r.id} className="drm-report brg-report">
                      <HazardIcon type={r.hazard_type_details?.name} />
                      <div className="drm-report-body">
                        <div className="drm-report-head">
                          <span className="drm-report-title">
                            {r.hazard_type_details?.name || 'Incident'}
                            <span className="drm-report-place">{r.barangay_details?.name ? ` · ${r.barangay_details.name}` : ''}</span>
                          </span>
                          <StatusTag status={r.status} />
                        </div>
                        <p className="drm-report-desc">{r.description}</p>
                        <ImpactChips report={r} />
                        <p className="drm-report-meta">
                          <span title={formatDateTime(r.created_at)}>Sent {timeAgo(r.created_at).toLowerCase()}</span>
                          {r.severity_estimate && <span>Severity: {r.severity_estimate}</span>}
                          {r.reviewed_at && <span>Reviewed {timeAgo(r.reviewed_at).toLowerCase()}</span>}
                        </p>
                        {r.review_note && (
                          <div className={`brg-note ${r.status === 'Rejected' ? 'is-bad' : ''}`}>
                            <strong>DRRMO note</strong>
                            {r.review_note}
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="adm-card">
              <div className="adm-card-head">
                <div>
                  <h2>Safety guidance</h2>
                  <p>Latest advice published by the DRRMO.</p>
                </div>
                <Link to="/what-to-do" className="adm-link">All guides <Icon name="arrowRight" size={14} /></Link>
              </div>
              {guidance.length === 0 ? (
                <p className="adm-muted">No guidance published yet.</p>
              ) : (
                <ul className="brg-guides">
                  {guidance.map((g) => <GuidanceItem key={g.id} item={g} />)}
                </ul>
              )}
            </section>
          </div>
        </div>
      </div>
      <Toast key={toast?.id} toast={toast} onDone={clearToast} />
    </div>
  );
}