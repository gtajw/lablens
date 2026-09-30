'use client';
import { useMemo, useState } from 'react';
import { number, unit } from '@/lib/format';
import type { Point } from '@/lib/types';

export function Chart({ points, xLabel, yLabel, xUnit, yUnit, fitted, summary }: {
  points: Point[]; xLabel: string; yLabel: string; xUnit: string; yUnit: string; fitted: boolean; summary?: string;
}) {
  const [mode, setMode] = useState<'fit' | 'residual'>('fit');
  const residual = fitted && mode === 'residual';
  const data = useMemo(() => points.filter(p => Number.isFinite(p.transformed_x) && Number.isFinite(p.transformed_y)), [points]);
  const W = 680, H = 330, left = 78, top = 24, width = 575, height = 244;
  const xs = data.map(p => p.transformed_x);
  const ys = data.flatMap(p => residual ? [p.residual] : fitted ? [p.transformed_y, p.predicted_y] : [p.transformed_y]);
  let minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  if (!data.length) { minX = 0; maxX = 5; minY = 0; maxY = 1; }
  if (residual) { const bound = Math.max(Math.abs(minY), Math.abs(maxY)) || 1; minY = -bound; maxY = bound; }
  const spreadX = maxX - minX || Math.abs(maxX) * 0.1 || 1;
  const spreadY = maxY - minY || Math.abs(maxY) * 0.1 || 1;
  minX -= spreadX * .07; maxX += spreadX * .07;
  minY -= spreadY * .12; maxY += spreadY * .12;
  const px = (x: number) => left + (x - minX) / (maxX - minX) * width;
  const py = (y: number) => top + height - (y - minY) / (maxY - minY) * height;
  const stride = Math.max(1, Math.ceil(data.length / 200));
  const visible = data.filter((_, i) => i % stride === 0 || i === data.length - 1);
  const fittedLine = [...data].sort((a, b) => a.transformed_x - b.transformed_x).filter((_, i) => i % stride === 0 || i === data.length - 1)
    .map(p => `${px(p.transformed_x)},${py(p.predicted_y)}`).join(' ');
  return <figure className="chart-card">
    <div className="chart-head"><div><h2>{residual ? 'Residuals' : 'Your measurements, in context'}</h2><p>{fitted ? `${data.length} measurements · canonical units` : 'Raw data preview · run an analysis to fit a model'}</p></div>
      {fitted && <div className="segmented" aria-label="Chart view"><button type="button" aria-pressed={!residual} onClick={() => setMode('fit')}>Fit</button><button type="button" aria-pressed={residual} onClick={() => setMode('residual')}>Residuals</button></div>}
    </div>
    <svg className="plot" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary || `${xLabel} versus ${yLabel}; ${data.length} raw measurements. Exact values are in the data table.`}>
      <title>{residual ? 'Residual = observed − predicted' : `${yLabel} versus ${xLabel}`}</title>
      <defs><pattern id="plot-dots" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".65" fill="#dae3ec" /></pattern></defs>
      <rect x={left} y={top} width={width} height={height} fill="url(#plot-dots)" />
      {Array.from({ length: 5 }, (_, i) => {
        const y = top + i * height / 4, x = left + i * width / 4;
        return <g key={i}><line x1={left} x2={left + width} y1={y} y2={y} className="grid-line" /><text x={left - 13} y={y + 4} textAnchor="end">{number(maxY - i * (maxY - minY) / 4, 3)}</text><text x={x} y={top + height + 24} textAnchor="middle">{number(minX + i * (maxX - minX) / 4, 3)}</text></g>;
      })}
      <line x1={left} x2={left} y1={top} y2={top + height} className="axis" /><line x1={left} x2={left + width} y1={top + height} y2={top + height} className="axis" />
      {residual && <line x1={left} x2={left + width} y1={py(0)} y2={py(0)} stroke="#65788d" strokeDasharray="5 5" />}
      {fitted && !residual && <polyline points={fittedLine} fill="none" stroke="#0a887f" strokeWidth="2.5" />}
      {visible.map(p => <circle key={p.point_index} cx={px(p.transformed_x)} cy={py(residual ? p.residual : p.transformed_y)} r="4.7" fill="#3478cf" stroke="white" strokeWidth="1.8"><title>{`Row ${p.point_index + 1}: x ${number(p.transformed_x)}, ${residual ? 'residual' : 'y'} ${number(residual ? p.residual : p.transformed_y)}`}</title></circle>)}
      <text x={left + width / 2} y={H - 8} textAnchor="middle" className="axis-label">{xLabel} ({unit(xUnit)})</text>
      <text transform={`translate(18 ${top + height / 2}) rotate(-90)`} textAnchor="middle" className="axis-label">{residual ? 'Residual' : yLabel} ({unit(yUnit)})</text>
    </svg>
    <figcaption><div className="legend"><span><i className="point-key" />{residual ? 'Observed − predicted' : 'Measurements'}</span>{fitted && !residual && <span><i className="line-key" />Fitted values</span>}</div><span>{stride > 1 ? `Showing ${visible.length} points; all ${data.length} are included in the fit and export.` : fitted ? 'Inspect exact values in the table below.' : 'Nothing has been fitted yet.'}</span></figcaption>
  </figure>;
}
