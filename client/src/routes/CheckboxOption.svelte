<script type="ts">
	export let title;
	export let description;
	export let _bind;
	export let _onchange;

	$: _bind
</script>

<label class="flex gap-3 justify-between">
 <div class="flex flex-col">
		<span class="text-gray-400 font-bold">{title}</span>
		<span class="text-gray-300">{description}</span>
	</div>
	<input 	class="col-span-1 rounded-md border-gray-300 text-orange-600 transition"
			type="checkbox"
			bind:checked={_bind}
			onchange={_onchange()}
	/>
</label>
