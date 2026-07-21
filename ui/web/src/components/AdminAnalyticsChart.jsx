import { Bar } from 'react-chartjs-2'

// Hour-of-day request histogram (24 UTC bars). Data comes from
// /api/admin/analytics/summary's hourly_histogram (always 24 zero-filled
// entries, so bars render even for quiet hours).
export default function AdminAnalyticsChart({ hourly }) {
  const data = {
    labels: hourly.map((b) => b.hour),
    datasets: [
      {
        data: hourly.map((b) => b.count),
        backgroundColor: 'rgba(192, 132, 252, 0.55)',
        hoverBackgroundColor: 'rgba(192, 132, 252, 0.9)',
        borderRadius: 3,
      },
    ],
  }

  const options = {
    animation: { duration: 400 },
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => `${items[0].label}:00 UTC`,
          label: (item) => ` ${item.parsed.y} requests`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          color: '#9d7cb8',
          font: { size: 9 },
          callback: (v) => (v % 3 === 0 ? v : ''),
        },
        border: { display: false },
      },
      y: {
        beginAtZero: true,
        grid: { color: '#2b1c45' },
        ticks: { color: '#9d7cb8', font: { size: 10 }, precision: 0 },
        border: { display: false },
      },
    },
  }

  return (
    <div className="h-[160px]">
      <Bar data={data} options={options} />
    </div>
  )
}
