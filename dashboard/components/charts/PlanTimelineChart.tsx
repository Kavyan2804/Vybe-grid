import { Badge } from '../badges';

export type PlanTimelinePoint = {
  hour: string;
  solarKw: number;
  batteryKw: number;
  dieselKw: number;
  demandKw: number;
  status?: 'live' | 'forecast';
};

type PlanTimelineChartProps = {
  points: PlanTimelinePoint[];
};

export function PlanTimelineChart({ points }: PlanTimelineChartProps) {
  const maxKw = Math.max(...points.flatMap((point) => [point.solarKw, point.batteryKw, point.dieselKw, point.demandKw]), 1);
  const width = 720;
  const height = 260;
  const left = 46;
  const right = 18;
  const top = 18;
  const bottom = 44;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;

  const toX = (index: number) => left + (chartWidth * index) / Math.max(1, points.length - 1);
  const toY = (value: number) => top + chartHeight - (value / maxKw) * chartHeight;
  const demandPath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${toX(index)} ${toY(point.demandKw)}`).join(' ');

  return (
    <div className="timeline-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Dispatch plan timeline">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = top + chartHeight * ratio;
          return <line key={ratio} x1={left} x2={width - right} y1={y} y2={y} className="chart-grid" />;
        })}
        <path d={demandPath} className="demand-line" />
        {points.map((point, index) => {
          const x = toX(index);
          const solarHeight = chartHeight - (toY(point.solarKw) - top);
          const batteryHeight = chartHeight - (toY(point.batteryKw) - top);
          const dieselHeight = chartHeight - (toY(point.dieselKw) - top);
          return (
            <g key={`${point.hour}-${index}`}>
              <rect x={x - 15} y={top + chartHeight - solarHeight} width="8" height={solarHeight} className="bar-solar" rx="2" />
              <rect x={x - 4} y={top + chartHeight - batteryHeight} width="8" height={batteryHeight} className="bar-battery" rx="2" />
              <rect x={x + 7} y={top + chartHeight - dieselHeight} width="8" height={dieselHeight} className="bar-diesel" rx="2" />
              <circle cx={x} cy={toY(point.demandKw)} r="4" className="demand-dot" />
              <text x={x} y={height - 18} textAnchor="middle" className="chart-label">
                {point.hour}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">
        <span><i className="legend-solar" /> Solar</span>
        <span><i className="legend-battery" /> Battery</span>
        <span><i className="legend-diesel" /> Diesel</span>
        <span><i className="legend-demand" /> Demand</span>
        <Badge tone={points.some((point) => point.status === 'live') ? 'live' : 'forecast'}>
          {points.some((point) => point.status === 'live') ? 'LIVE + FORECAST' : 'FORECAST'}
        </Badge>
      </div>
    </div>
  );
}
