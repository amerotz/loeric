<script lang="ts">
  import { onMount } from "svelte";

  export let values: number[] = [];
  export let width = 150;
  export let height = 100;
  export let color = "lime";

  let canvas: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D;

  onMount(() => {
    ctx = canvas.getContext("2d");
    draw();
  });

  $: if (ctx) draw();

  function draw() {
    ctx.clearRect(0, 0, width, height);
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;

    const len = values.length;
    if (len === 0) return;

    const maxVal = Math.max(...values, 1);
    const minVal = Math.min(...values, 0);

    values.forEach((v, i) => {
      const x = (i / (len - 1)) * width;
      const y = height - ((v - minVal) / (maxVal - minVal)) * height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.stroke();
  }
</script>

<canvas bind:this={canvas} {width} {height} class="rounded-lg bg-gray-900"></canvas>

