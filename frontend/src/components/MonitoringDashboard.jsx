import React, { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const MonitoringDashboard = ({ testId }) => {
  const [metrics, setMetrics] = useState({
    labels: [],
    vus: [],
    rps: [],
    responseTime: [],
    errorRate: [],
  });

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/ws/metrics/${testId}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setMetrics(prev => ({
        labels: [...prev.labels, new Date().toLocaleTimeString()],
        vus: [...prev.vus, data.vus],
        rps: [...prev.rps, data.rps],
        responseTime: [...prev.responseTime, data.response_time],
        errorRate: [...prev.errorRate, data.error_rate],
      }));
    };

    return () => {
      ws.close();
    };
  }, [testId]);

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
    },
    scales: {
      y: {
        beginAtZero: true,
      },
    },
  };

  const charts = [
    {
      title: 'Virtual Users (VUs)',
      data: {
        labels: metrics.labels,
        datasets: [{
          label: 'VUs',
          data: metrics.vus,
          borderColor: 'rgb(75, 192, 192)',
          tension: 0.1,
        }],
      },
    },
    {
      title: 'Requests per Second (RPS)',
      data: {
        labels: metrics.labels,
        datasets: [{
          label: 'RPS',
          data: metrics.rps,
          borderColor: 'rgb(255, 99, 132)',
          tension: 0.1,
        }],
      },
    },
    {
      title: 'Response Time (ms)',
      data: {
        labels: metrics.labels,
        datasets: [{
          label: 'Response Time',
          data: metrics.responseTime,
          borderColor: 'rgb(54, 162, 235)',
          tension: 0.1,
        }],
      },
    },
    {
      title: 'Error Rate (%)',
      data: {
        labels: metrics.labels,
        datasets: [{
          label: 'Error Rate',
          data: metrics.errorRate,
          borderColor: 'rgb(255, 159, 64)',
          tension: 0.1,
        }],
      },
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 p-4">
      {charts.map((chart, index) => (
        <div key={index} className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-lg font-semibold mb-4">{chart.title}</h3>
          <Line options={chartOptions} data={chart.data} />
        </div>
      ))}
    </div>
  );
};

export default MonitoringDashboard; 