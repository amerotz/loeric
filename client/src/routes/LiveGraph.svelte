<script>
  import { onMount } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let values = [];       // array of numbers

  let canvas;
  let chart;

  onMount(() => {
    canvas.style.backgroundColor = 'white';
    canvas.style.border = '1px solid #ccc';
    canvas.style.display = 'block';
      canvas.style.width = '100%';
    canvas.style.height = `100%`;
    chart = new Chart(canvas, {
  type: 'line',
  data: {
    labels: Array(20).fill(''),   // fixed size labels
    datasets: [{
      data: Array(20).fill(0),    // initial 20 zeros
      borderColor: 'rgba(75,192,192,1)',
      backgroundColor: 'rgba(75,192,192,0.2)',
      fill: true,
      tension: 0.4,
      pointRadius: 0
    }]
  },
  options: {
    responsive: true,
    animation: false,
    scales: {
      x: { ticks: { display: false }, grid: { drawBorder: false } },
      y: { min: 0, max: 1, ticks: { display: false }, grid: { drawBorder: false } }
    },
    plugins: { legend: { display: false } }
  }
});
});


  // Update chart when values change
  $: if (chart) {
    chart.data.labels = values.map((_, i) => i + 1);
    chart.data.datasets[0].data = values;
    chart.update();
  }
</script>

<canvas bind:this={canvas}  ></canvas>
