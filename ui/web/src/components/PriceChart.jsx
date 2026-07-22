import { Line } from 'react-chartjs-2'

// timeseries defaults to [] so a card that hasn't loaded (or whose timeseries
// request failed) renders an empty chart frame instead of throwing on .map and
// taking the whole card down with it — the score hero above is still valid.
export default function PriceChart({ timeseries = [], color }) {
  const data = {
    labels: timeseries.map((d) => d.date),
    datasets: [
      {
        data: timeseries.map((d) => d.close),
        borderColor: color,
        backgroundColor: (ctx) => {
          const { chart } = ctx
          const { ctx: c, chartArea } = chart
          if (!chartArea) return color + '22'
          const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
          g.addColorStop(0, color + '44')
          g.addColorStop(1, color + '00')
          return g
        },
        borderWidth: 1.5,
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 4,
      },
    ],
  }

  const options = {
    animation: { duration: 500 },
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: { label: (i) => ` $${i.parsed.y.toFixed(2)}` },
      },
    },
    scales: {
      x: { display: false },
      y: {
        grid: { color: '#2b1c45' },
        ticks: { color: '#9d7cb8', font: { size: 10 } },
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
