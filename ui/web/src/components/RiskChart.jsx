import { Line } from 'react-chartjs-2'

function bucketColor(v) {
  if (v < 25) return '#3fb950'
  if (v < 50) return '#d29922'
  if (v < 75) return '#f0883e'
  return '#f85149'
}

export default function RiskChart({ timeseries }) {
  const data = {
    labels: timeseries.map((d) => d.date),
    datasets: [
      {
        data: timeseries.map((d) => d.risk_score),
        borderWidth: 1.5,
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 4,
        backgroundColor: (ctx) => {
          const { chart } = ctx
          const { ctx: c, chartArea } = chart
          if (!chartArea) return 'rgba(248,81,73,.2)'
          const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
          g.addColorStop(0, 'rgba(248,81,73,.35)')
          g.addColorStop(0.5, 'rgba(240,136,62,.2)')
          g.addColorStop(1, 'rgba(63,185,80,.0)')
          return g
        },
        segment: {
          borderColor: (ctx) => bucketColor(ctx.p1.parsed.y),
        },
      },
    ],
  }

  const options = {
    animation: { duration: 500 },
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { mode: 'index', intersect: false },
    },
    scales: {
      x: { display: false },
      y: {
        min: 0,
        max: 100,
        grid: { color: '#21262d' },
        ticks: {
          color: '#8b949e',
          font: { size: 10 },
          callback: (v) => ([0, 25, 50, 75, 100].includes(v) ? v : ''),
        },
        border: { display: false },
      },
    },
  }

  return (
    <div className="h-[110px]">
      <Line data={data} options={options} />
    </div>
  )
}
