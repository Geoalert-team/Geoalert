// Matches HazardZone.SEVERITY_CHOICES in apps/hazards/models.py â€” the API
// returns the raw code ('Red'/'Orange'/'Green'), not the display label.
export const SEVERITY_COLORS = {
  Red: '#D6483F',
  Orange: '#E08A3C',
  Green: '#4E9E6E',
};

export const SEVERITY_LABELS = {
  Red: 'Extreme',
  Orange: 'Moderate',
  Green: 'Low',
};

export function severityColor(code) {
  return SEVERITY_COLORS[code] || '#7E9296';
}

export function severityLabel(code) {
  return SEVERITY_LABELS[code] || code;
}
