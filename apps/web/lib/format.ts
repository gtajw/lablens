export function number(value: number | null | undefined, digits = 6): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'Not defined';
  if (value === 0) return '0';
  return Number(value.toPrecision(digits)).toString();
}
const superscript: Record<string, string> = { '-': '⁻', '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹' };
export function unit(text: string): string {
  return text.replace(/\*\*\s*(-?\d+(?:\.\d+)?)/g, (_, power: string) => power.includes('.') ? `^(${power})` : power.split('').map(c => superscript[c]).join('')).replace(/\s+/g, '').replace(/\*/g, '·');
}
export function date(text: string): string { return new Date(text).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }); }

export const ruleTitles: Record<string, string> = {
  'UNIT.COEFFICIENT_DIMENSION_MISMATCH': 'The slope unit needs another look',
  'MODEL.FIXED_ZERO_ASSUMPTION': 'Zero intercept is an assumption',
  'MODEL.SHIFT_WITH_FIXED_ZERO': 'Your origin shift changes the zero point',
  'INTERPRETATION.FIT_NOT_PHYSICAL_PROOF': 'A fit is evidence, not proof',
  'TRANSFORM.DOMAIN_INVALID': 'This transform cannot use every row',
  'MODEL.INSUFFICIENT_POINTS': 'More measurements needed',
  'MODEL.INSUFFICIENT_DISTINCT_X': 'More distinct x values needed',
  'METRIC.R_SQUARED_UNDEFINED': 'R² is undefined for constant y',
};
