<script lang="ts">
  import type { MusicianControl } from "$lib/types";

  export let controls: MusicianControl[] = [];
  export let musicianId: string;
  export let apiPut: (action: string, data: any) => Promise<void> = async () => {};

  // Local reactive values for the sliders
  let controlValues: Record<string, number> = {};

  // Keep values in sync if controls update from server
  $: if (controls) {
    controls.forEach(c => {
        controlValues[c.control] = c.value;
    }
    );
    console.log(controlValues)
  }

  async function controlChange(event: Event) {
    const input = event.target as HTMLInputElement;
    const controlId = input.getAttribute("data-control");
    if (!controlId) return;

    const value = +input.value;
    controlValues[controlId] = value;
    await apiPut("control", { id: musicianId, control: controlId, value });
  }
</script>

{#if controls.length > 0}
  <div class="flex w-full justify-evenly">
    {#each controls as control}
      <label class="flex flex-col w-24 gap-5">
        <span class="text-center h-12">{control.name}</span>
        <input
          class="place-self-center"
          type="range"
          step="0.01"
          max="1"
          min="0"
          data-control={control.control}
          bind:value={controlValues[control.control]}
          on:input={controlChange}
        />
      </label>
    {/each}
  </div>
{:else}
  <div class="text-2xl text-center place-self-center w-full">
    No interaction setup.<br> Sit back and have a listen!
  </div>
{/if}
