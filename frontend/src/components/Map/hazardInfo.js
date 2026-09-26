// Shared hazard information for the public map.
// Severity codes match HazardZone.SEVERITY_CHOICES in backend/apps/hazards/models.py.

export const SEVERITY = {
  Red: {
    label: 'High risk',
    color: '#d64545',
    tint: '#fcebeb',
    text: '#a12f2f',
    advice: 'Immediate action is required. Prepare to evacuate and follow barangay officials.',
  },
  Orange: {
    label: 'Medium risk',
    color: '#d99a00',
    tint: '#fdf5de',
    text: '#7a5700',
    advice: 'Conditions could get worse. Watch for updates and know your evacuation route.',
  },
  Green: {
    label: 'Low risk',
    color: '#1f9d55',
    tint: '#e8f6ee',
    text: '#16693a',
    advice: 'The area is safe. Standard monitoring is in place.',
  },
};

const UNKNOWN_SEVERITY = {
  label: 'Not rated',
  color: '#6a778d',
  tint: '#eef1f5',
  text: '#43516a',
  advice: 'Check back for updates from the DRRMO.',
};

export function severityInfo(code) {
  return SEVERITY[code] || UNKNOWN_SEVERITY;
}

// Hazard types shown as filter chips on the map
export const HAZARD_TYPES = ['Flood', 'Landslide', 'Fire'];

// Turns names like "Flood", "Floods" or "flash flood" into one key
export function hazardKey(type = '') {
  const t = type.toLowerCase();
  if (t.includes('flood')) return 'Flood';
  if (t.includes('landslide')) return 'Landslide';
  if (t.includes('fire')) return 'Fire';
  return 'Other';
}

// SVG path data for each hazard icon (24 x 24 viewBox)
const ICON_PATHS = {
  Flood: 'M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z',
  Landslide: 'M3 20l6-12 4 7 3-4 5 9z',
  Fire: 'M12 3c1 4 5 5.5 5 10.5A5 5 0 0 1 7 13.5C7 11 8.5 9.5 9.5 8.5c0 2 1 3 2 3 0-3-.5-5.5.5-8.5z',
  Other: 'M12 4l9 16H3z M12 10v4 M12 17v.5',
};

export function hazardIconPath(type) {
  return ICON_PATHS[hazardKey(type)];
}

// Short "What to do" steps shown in the details panel
export const GUIDANCE = {
  Flood: [
    'Move valuables and appliances to a higher place.',
    'Keep your go-bag, flashlight and phone charger ready.',
    'Do not walk or drive through floodwater, even if it looks shallow.',
    'Evacuate right away when barangay officials tell you to.',
  ],
  Landslide: [
    'Watch for new cracks in the ground, leaning trees or poles.',
    'Stay away from steep slopes during heavy or long rain.',
    'Leave immediately if you hear rumbling or cracking sounds.',
    'Do not return until the DRRMO says the area is safe.',
  ],
  Fire: [
    'Keep doorways and alleys clear so everyone can get out.',
    'Unplug appliances and never leave cooking unattended.',
    'If there is fire, get out first, then call the fire station.',
    'Stay low under smoke and never go back inside for belongings.',
  ],
  Other: [
    'Stay alert and follow updates from the DRRMO.',
    'Keep your go-bag ready.',
    'Follow instructions from barangay officials.',
  ],
};

export function guidanceFor(type) {
  return GUIDANCE[hazardKey(type)];
}

export const DRRMO_HOTLINE = { label: '(032) 407-5928', tel: 'tel:+63324075928' };