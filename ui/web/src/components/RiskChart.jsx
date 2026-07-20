import { Line } from 'react-chartjs-2'

function bucketColor(v) {
  if (v < 25) return '#34d399'
  if (v < 50) return '#fbbf24'
  if (v < 75) return '#fb923c'
  return '#f43f5e'
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
          if (!chartArea) return 'rgba(244,63,94,.2)'
          const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
          g.addColorStop(0, 'rgba(244,63,94,.35)')
          g.addColorStop(0.5, 'rgba(251,146,60,.2)')
          g.addColorStop(1, 'rgba(52,211,153,.0)')
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
        grid: { color: '#2b1c45' },
        ticks: {
          color: '#9d7cb8',
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
