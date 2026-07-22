import {
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'

// LineController/BarController are the chart-type registrations themselves
// — the scale/element pieces alone aren't enough for react-chartjs-2's
// <Line>/<Bar> to render anything.
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  BarElement,
  BarController,
  Filler,
  Tooltip
)
