import type { AnalysisRequest, Column } from './types';
export type Draft = { title: string; name: string; columns: Column[]; rows: [string, string][]; transform: AnalysisRequest['x_transform']['kind']; family: 'linear' | 'quadratic'; intercept: 'free' | 'fixed_zero'; rationale: string; shift: string; claim: string; claimKey: 'linear' | 'quadratic'; sample: boolean };
export const samples: Record<string, Draft> = {
  acceleration: { title: 'Acceleration & time', name: 'Synthetic acceleration measurements', columns: [
    { role: 'independent', position: 0, name: 'Time', symbol: 't', unit_input: 's' },
    { role: 'dependent', position: 1, name: 'Acceleration', symbol: 'a', unit_input: 'm/s^2' }],
    rows: [['0.8', '0.01344'], ['1.8', '0.06804'], ['2.8', '0.16464'], ['3.8', '0.30324'], ['4.8', '0.48384']],
    transform: 'square', family: 'linear', intercept: 'fixed_zero', rationale: 'This synthetic example assumes acceleration is proportional to time squared.', shift: '', claim: 'm/s^2', claimKey: 'linear', sample: true },
  spring: { title: 'Spring extension & force', name: 'Synthetic spring measurements', columns: [
    { role: 'independent', position: 0, name: 'Extension', symbol: 'x', unit_input: 'cm' },
    { role: 'dependent', position: 1, name: 'Force', symbol: 'F', unit_input: 'N' }],
    rows: [['1', '0.51'], ['2', '0.97'], ['3', '1.52'], ['4', '1.98'], ['5', '2.53'], ['6', '2.99']],
    transform: 'identity', family: 'linear', intercept: 'free', rationale: '', shift: '', claim: 'N/m', claimKey: 'linear', sample: true },
  reciprocal: { title: 'A transform with a missing domain', name: 'Synthetic domain check', columns: [
    { role: 'independent', position: 0, name: 'Time', symbol: 't', unit_input: 's' },
    { role: 'dependent', position: 1, name: 'Distance', symbol: 'd', unit_input: 'm' }],
    rows: [['0', '0'], ['1', '2'], ['2', '4'], ['3', '6']],
    transform: 'reciprocal', family: 'linear', intercept: 'free', rationale: '', shift: '', claim: '', claimKey: 'linear', sample: true },
};
export const freshDraft = (): Draft => ({ title: 'Untitled experiment', name: 'Measurements', columns: [
  { role: 'independent', position: 0, name: 'Time', symbol: 'x', unit_input: 's' },
  { role: 'dependent', position: 1, name: 'Distance', symbol: 'y', unit_input: 'm' }],
  rows: [['', ''], ['', ''], ['', '']], transform: 'identity', family: 'linear', intercept: 'free', rationale: '', shift: '', claim: '', claimKey: 'linear', sample: false });
