import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { useAuth } from '../../context/AuthContext';
import { barangaysApi } from '../../api/barangaysApi';
import { reportsApi } from '../../api/reportApi';
import { guidanceApi } from '../../api/guidanceApi';
import { hazardsApi } from '../../api/hazardsApi';
import { Icon, Toast, fieldErrors, formatDateTime, timeAgo } from './admin/adminShared';
import { HazardIcon, ReportPhotos, StatusTag } from './reportShared';
import ConfirmHazardCard from '../../components/Verify/ConfirmHazardCard';
import LocationPicker from '../../components/Map/LocationPicker';
import PurokPreviewMap from '../../components/Map/PurokPreviewMap';
import { puroksOf } from '../../components/Map/purokStyle';
import {
  MAX_PUROKS, hazardSwitchErrors, isFireType, localNow, placeLabel, purokOptions, purokPins, reportPayload,
  validateReport, withBarangay, withHazardType,
} from './fireReport';
import '../css/Dashboard.css';
import '../css/AdminDashboard.css';
import '../css/DRRMODashboard.css';
import '../css/BarangayDashboard.css';

const SEVERITIES = [
  { value: 'Low', hint: 'Minor, no immediate danger' },
  { value: 'Moderate', hint: 'Could get worse, needs watching' },
  { value: 'High', hint: 'People at risk, needs action now' },
];

const POSITIONS = [
  'Punong Barangay',
  'Barangay Kagawad',
  'Barangay Secretary',
  'Barangay Treasurer',
  'SK Chairperson',
  'BDRRM Officer',
  'Barangay Tanod',
  'Barangay Health Worker',
];

const OFFICES = [
  'Office of the Punong Barangay',
  'Barangay Council',
  'BDRRM Committee',
  'Barangay Peacekeeping Action Team',
  'Barangay Health Center',
  'Sangguniang Kabataan',
];

// A saved value outside the list (e.g. an older free-text entry) stays selectable
function withCurrent(options, current) {
  return current && !options.includes(current) ? [current, ...options] : options;
}

// Matches MAX_PHOTO_BYTES in apps/reports/serializers.py. Checked here as
// well so a 12 MB photo is refused before it is pushed up a barangay's
// connection, not after.
const MAX_PHOTO_MB = 5;

// Matches MAX_PHOTOS_PER_REPORT in apps/reports/serializers.py
const MAX_PHOTOS = 5;

const REPORT_TABS = ['All', 'Pending', 'Validated', 'Rejected'];
const TAB_LABEL = { All: 'All', Pending: 'Awaiting review', Validated: 'Validated', Rejected: 'Rejected' };

/**
 * The barangay this account is assigned to, as a string id or ''.
 *
 * Two serializers return this field in two shapes: the signed-in user comes
 * from UserSerializer, where assigned_barangay is a plain id, while the
 * admin user list nests an object. Reading `.id` off the number gave
 * undefined, which left the form's barangay empty while the UI still treated
 * the account as assigned — the field locked itself to a barangay it could
 * not name and the form refused to submit, with no dropdown to escape with.
 * Accepting both shapes means neither serializer can break this again.
 */
function assignedBarangayId(user) {
  const value = user?.assigned_barangay;
  if (value === null || value === undefined || value === '') return '';
  return String(value?.id ?? value);
}

function emptyForm(user) {
  return {
    barangay: assignedBarangayId(user),
    hazard_type: '',
    description: '',
    severity_estimate: '',
    position: user?.position || '',
    agency: '',
    location: null, // optional map pin [lat, lng]; fires use their puroks instead
    // Fire reports only: when it started (and whether the reporter changed
    // it), and the ids of the puroks it is in
    started_at: localNow(),
    started_at_edited: false,
    puroks: [],
  };
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
  const assignedId = assignedBarangayId(user);

  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [barangays, setBarangays] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [guidance, setGuidance] = useState([]);

  const [form, setForm] = useState(() => emptyForm(user));
  // The photo is a File, not a form value, so it lives outside `form`.
  // preview is an object URL and has to be revoked, or every re-pick leaks
  // the previous image for as long as the page is open.
  // Each entry is { file, preview, key }. preview is an object URL and has
  // to be revoked by hand, or every pick leaks the image for as long as the
  // page stays open.
  const [photos, setPhotos] = useState([]);
  const fileInput = useRef(null);
  const [errors, setErrors] = useState({});
  // Barangay outlines by id, so the pin map can centre on the right one
  const [barangayShapes, setBarangayShapes] = useState(new Map());
  // Purok outlines, so a fire report's pin can name its purok
  const [purokGeo, setPurokGeo] = useState(null);
  // 'loading' | 'ready' | 'failed': a fire report can't name its puroks
  // without the list, so a failed load says so and offers to try again
  const [purokStatus, setPurokStatus] = useState('loading');
  const loadPuroks = useCallback(() => {
    setPurokStatus('loading');
    barangaysApi.puroks()
      .then((geo) => { setPurokGeo(geo); setPurokStatus('ready'); })
      .catch(() => { setPurokGeo(null); setPurokStatus('failed'); });
  }, []);
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
        setBarangayShapes(new Map((geo?.features || []).map((f) => [String(f.id ?? f.properties?.id), f])));
        const list = (geo?.features || [])
          // The GeoJSON id sits on the feature itself, not inside properties
          .map((f) => ({ id: f.id ?? f.properties?.id, name: f.properties?.name }))
          .filter((b) => b.id != null && b.name)
          .sort((a, b) => a.name.localeCompare(b.name));
        setBarangays(list);
      })
      .catch(() => setBarangays([]));
    loadPuroks();
    hazardsApi.types().then((data) => setHazardTypes(data.results || data)).catch(() => setHazardTypes([]));
    guidanceApi.list().then((data) => setGuidance((data.results || data).filter((g) => g.is_published !== false).slice(0, 4))).catch(() => setGuidance([]));
  }, [refreshReports, loadPuroks]);

  // The signed-in user may arrive after the first render
  useEffect(() => {
    if (!user) return;
    setForm((f) => ({
      ...f,
      barangay: f.barangay || assignedBarangayId(user),
      position: f.position || user.position || '',
    }));
  }, [user]);

  const clearToast = useCallback(() => setToast(null), []);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
    if (errors[field] || errors.form) setErrors((e) => ({ ...e, [field]: undefined, form: undefined }));
  }

  // Release every preview if the page is left mid-report. The ref keeps the
  // current list without making this effect re-run on each pick, which would
  // revoke the URLs of images still on screen.
  const photosRef = useRef(photos);
  photosRef.current = photos;
  useEffect(() => () => {
    photosRef.current.forEach((p) => URL.revokeObjectURL(p.preview));
  }, []);

  function clearPhotos() {
    photos.forEach((p) => URL.revokeObjectURL(p.preview));
    setPhotos([]);
    if (fileInput.current) fileInput.current.value = '';
    setErrors((e) => ({ ...e, photos: undefined }));
  }

  function removePhoto(key) {
    setPhotos((list) => {
      const gone = list.find((p) => p.key === key);
      if (gone) URL.revokeObjectURL(gone.preview);
      return list.filter((p) => p.key !== key);
    });
    setErrors((e) => ({ ...e, photos: undefined }));
  }

  function addPhotos(fileList) {
    const picked = Array.from(fileList || []);
    // Clearing the input matters: without it, choosing the same file again
    // fires no change event and the photo silently does not come back.
    if (fileInput.current) fileInput.current.value = '';
    if (picked.length === 0) return;

    const problems = [];
    const accepted = [];

    for (const file of picked) {
      if (!file.type.startsWith('image/')) {
        problems.push(`${file.name} is not a photo.`);
      } else if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
        problems.push(`${file.name} is ${(file.size / 1024 / 1024).toFixed(1)} MB.`);
      } else {
        accepted.push(file);
      }
    }

    setPhotos((list) => {
      const room = MAX_PHOTOS - list.length;
      if (accepted.length > room) {
        problems.push(`Only ${MAX_PHOTOS} photos can be attached to one report.`);
      }
      const added = accepted.slice(0, Math.max(0, room)).map((file) => ({
        file,
        preview: URL.createObjectURL(file),
        // Date.now() alone collides when several files are added at once
        key: `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`,
      }));
      return [...list, ...added];
    });

    setErrors((e) => ({
      ...e,
      photos: problems.length
        ? `${problems.join(' ')} Photos must be JPG or PNG, each under ${MAX_PHOTO_MB} MB.`
        : undefined,
      form: undefined,
    }));
  }

  // A fire report asks when and where (the BFP log's columns A-F) instead
  // of how serious it is
  const fire = isFireType(hazardTypes, form.hazard_type);
  const barangayPuroks = useMemo(() => puroksOf(purokGeo, form.barangay), [purokGeo, form.barangay]);
  const hasPuroks = Boolean(barangayPuroks?.features.length);
  const purokChoices = useMemo(
    () => purokOptions(purokGeo, form.barangay, form.puroks),
    [purokGeo, form.barangay, form.puroks],
  );
  const chosenPuroks = useMemo(() => {
    const byId = new Map((barangayPuroks?.features || []).map((f) => [String(f.id), f]));
    return form.puroks.map((id) => byId.get(id)).filter(Boolean);
  }, [barangayPuroks, form.puroks]);

  function validate() {
    return validateReport(form, { fire, hasPuroks, purokStatus });
  }

  function chooseHazard(id) {
    setForm((f) => withHazardType(f, id, { fire: isFireType(hazardTypes, id) }));
    setErrors((e) => ({ ...hazardSwitchErrors(e), hazard_type: undefined, form: undefined }));
  }

  function chooseBarangay(id) {
    setForm((f) => withBarangay(f, id));
    setErrors((e) => ({ ...e, barangay: undefined, puroks: undefined, form: undefined }));
  }

  function setStartedAt(value) {
    setForm((f) => ({ ...f, started_at: value, started_at_edited: true }));
    if (errors.started_at || errors.form) setErrors((e) => ({ ...e, started_at: undefined, form: undefined }));
  }

  function addPurok(id) {
    if (!id) return;
    setForm((f) => (f.puroks.includes(id) || f.puroks.length >= MAX_PUROKS ? f : { ...f, puroks: [...f.puroks, id] }));
    if (errors.puroks || errors.form) setErrors((e) => ({ ...e, puroks: undefined, form: undefined }));
  }

  function removePurok(id) {
    setForm((f) => ({ ...f, puroks: f.puroks.filter((p) => p !== id) }));
  }

  async function submit(e) {
    e.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) return;

    setBusy(true);
    try {
      await reportsApi.submit({ ...reportPayload(form, { fire }), photos: photos.map((p) => p.file) });
      setForm({ ...emptyForm(user), position: form.position, agency: form.agency });
      clearPhotos();
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
  // The name from the API, or looked up in the list the page already loaded
  // if an older backend is serving this build.
  const assignedName = user?.assigned_barangay_name
    || user?.assigned_barangay?.name
    || barangays.find((b) => String(b.id) === assignedId)?.name
    || '';
  const barangayName = assignedName
    || barangays.find((b) => String(b.id) === String(form.barangay))?.name;

  return (
    <div className="db adm drm brg">
      <PublicNavbar />
      <div className="adm-wrap">
        <header className="adm-header">
          <div>
            <p className="adm-eyebrow">{assignedName ? `Barangay ${assignedName}` : 'Barangay personnel'}</p>
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

        {/* ---------- Ground confirmation ----------
            Above the report form on purpose: answering a hazard that is
            already live matters more than filing a new report. The card
            brings its own db- styling; this page's root carries .db. */}
        <ConfirmHazardCard />

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
                {assignedId && assignedName ? (
                  <div className="brg-locked">
                    <Icon name="building" size={16} />
                    <span><strong>{assignedName}</strong> · your assigned barangay</span>
                  </div>
                ) : (
                  <select id="brg-barangay" value={form.barangay} onChange={(e) => chooseBarangay(e.target.value)}>
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
                        <input type="radio" name="hazard_type" value={t.id} checked={checked} onChange={() => chooseHazard(String(t.id))} />
                        <HazardIcon type={t.name} size="sm" />
                        {t.name}
                      </label>
                    );
                  })}
                </div>
                {errors.hazard_type && <p className="adm-field-error">{errors.hazard_type}</p>}
              </div>

              {fire && (
                <div className={`adm-field ${errors.started_at ? 'has-error' : ''}`}>
                  <label htmlFor="brg-started">When it started<span className="adm-req">*</span></label>
                  <input
                    id="brg-started"
                    type="datetime-local"
                    value={form.started_at}
                    max={localNow()}
                    onChange={(e) => setStartedAt(e.target.value)}
                  />
                  {errors.started_at && <p className="adm-field-error">{errors.started_at}</p>}
                </div>
              )}

              {fire ? (
                <>
                  <div className={`adm-field ${errors.puroks ? 'has-error' : ''}`}>
                    <label htmlFor="brg-purok-add">
                      Purok / Sitio
                      {hasPuroks || purokStatus !== 'ready'
                        ? <span className="adm-req">*</span>
                        : <span className="brg-optional">optional</span>}
                    </label>
                    {chosenPuroks.length > 0 && (
                      <div className="db-chips brg-purok-chips">
                        {chosenPuroks.map((f) => (
                          <span key={f.id} className="db-chip brg-purok-chip">
                            {f.properties?.name}
                            <button
                              type="button"
                              onClick={() => removePurok(String(f.id))}
                              aria-label={`Remove ${f.properties?.name}`}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    {purokStatus === 'loading' && <p className="adm-muted">Loading the puroks…</p>}
                    {purokStatus === 'failed' && (
                      <div className="adm-alert" role="alert">
                        <Icon name="info" size={16} />
                        The purok list didn&apos;t load.
                        <button type="button" className="adm-btn adm-btn-ghost adm-btn-sm" onClick={loadPuroks}>Try again</button>
                      </div>
                    )}
                    {purokStatus === 'ready' && hasPuroks && (
                      <select
                        id="brg-purok-add"
                        value=""
                        onChange={(e) => addPurok(e.target.value)}
                        disabled={form.puroks.length >= MAX_PUROKS || purokChoices.length === 0}
                      >
                        <option value="">
                          {form.puroks.length >= MAX_PUROKS
                            ? `Up to ${MAX_PUROKS} puroks`
                            : form.puroks.length ? '+ Add another purok' : 'Choose the purok or sitio'}
                        </option>
                        {purokChoices.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                      </select>
                    )}
                    {errors.puroks && <p className="adm-field-error">{errors.puroks}</p>}
                  </div>

                  <div className="adm-field">
                    <label>Where exactly</label>
                    <PurokPreviewMap
                      barangay={barangayShapes.get(String(form.barangay)) || null}
                      puroks={chosenPuroks}
                      pins={purokPins(purokGeo, form.puroks)}
                    />
                  </div>
                </>
              ) : (
                <div className={`adm-field ${errors.location ? 'has-error' : ''}`}>
                  <label>
                    Where exactly <span className="brg-optional">optional</span>
                  </label>
                  <p className="adm-muted" style={{ margin: '0 0 6px', fontSize: '.8rem' }}>
                    Drop a pin where you saw it. Pins from several reports let the DRRMO draw the hazard
                    zone around what was actually seen.
                  </p>
                  <LocationPicker
                    value={form.location}
                    onChange={(v) => set('location', v)}
                    barangay={barangayShapes.get(String(form.barangay)) || null}
                  />
                  {errors.location && <p className="adm-field-error">{errors.location}</p>}
                </div>
              )}
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
                  placeholder={fire
                    ? 'What is burning, how big it is, whether it is spreading, and what help is needed.'
                    : 'Exact location (purok or sitio), what happened, how bad it looks, and what help is needed.'}
                />
                <div className="brg-desc-foot">
                  {errors.description ? <p className="adm-field-error">{errors.description}</p> : <span />}
                  <span className="brg-count">{form.description.length}/1000</span>
                </div>
              </div>

              {/* capture="environment" opens the rear camera straight away on
                  a phone, which is how most of these will be taken. On a
                  laptop it is ignored and this is an ordinary file picker. */}
              <div className={`adm-field ${errors.photos ? 'has-error' : ''}`}>
                <label htmlFor="brg-photo">
                  Photos <span className="brg-optional">optional</span>
                  {photos.length > 0 && (
                    <span className="brg-photo-count">{photos.length} of {MAX_PHOTOS}</span>
                  )}
                </label>

                {photos.length > 0 && (
                  <ul className="brg-photo-grid">
                    {photos.map((p) => (
                      <li key={p.key} className="brg-photo-thumb">
                        <img src={p.preview} alt={`Attached: ${p.file.name}`} />
                        <button
                          type="button"
                          className="brg-photo-remove"
                          onClick={() => removePhoto(p.key)}
                          title={`Remove ${p.file.name}`}
                          aria-label={`Remove ${p.file.name}`}
                        >
                          <Icon name="x" size={14} strokeWidth={3} />
                        </button>
                        <span className="brg-photo-size">
                          {(p.file.size / 1024 / 1024).toFixed(1)} MB
                        </span>
                      </li>
                    ))}
                  </ul>
                )}

                {photos.length < MAX_PHOTOS && (
                  <label className="brg-photo-drop" htmlFor="brg-photo">
                    <Icon name="camera" size={22} />
                    <span>
                      <strong>{photos.length ? 'Add another photo' : 'Add photos'}</strong>
                      <small>JPG or PNG, up to {MAX_PHOTO_MB} MB each</small>
                    </span>
                  </label>
                )}

                <input
                  id="brg-photo"
                  ref={fileInput}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  multiple
                  className="brg-photo-input"
                  onChange={(e) => addPhotos(e.target.files)}
                />
                {errors.photos
                  ? <p className="adm-field-error">{errors.photos}</p>
                  : (
                    <p className="adm-hint">
                      Pictures of what you can see help the DRRMO judge this faster —
                      a wide shot of how far it reaches and a close one of how bad it is.
                    </p>
                  )}
              </div>

              {/* Not for fires: their level comes from the purok's history,
                  and DRRMO records how bad it was when closing */}
              {!fire && (
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
              )}
            </div>

            <div className="brg-step">
              <h3><span className="adm-step">3</span>Your details</h3>
              <div className="adm-form-grid adm-grid-2">
                <div className="adm-field">
                  <label htmlFor="brg-position">Position</label>
                  <select id="brg-position" value={form.position} onChange={(e) => set('position', e.target.value)}>
                    <option value="">Select a position</option>
                    {withCurrent(POSITIONS, form.position).map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div className="adm-field">
                  <label htmlFor="brg-agency">Office or agency</label>
                  <select id="brg-agency" value={form.agency} onChange={(e) => set('agency', e.target.value)}>
                    <option value="">Select an office</option>
                    {withCurrent(OFFICES, form.agency).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
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
                        <ReportPhotos report={r} alt={`Photo you sent with the ${r.hazard_type_details?.name || 'incident'} report`} />
                        <p className="drm-report-meta">
                          <span title={formatDateTime(r.created_at)}>Sent {timeAgo(r.created_at).toLowerCase()}</span>
                          {r.started_at && <span>Started {formatDateTime(r.started_at)}</span>}
                          {placeLabel(r) && <span>{placeLabel(r)}</span>}
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