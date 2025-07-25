<script lang="ts">
	let fileInput: HTMLInputElement

	export let onUpload: (formData: FormData) => void

	export let accepted: string
	export let name = "upload"

	async function selectFile() {
		fileInput.click()
	}

	async function upload() {
		const file = fileInput.files?.item(0)
		if (file) {
			const formData = new FormData()
			formData.append(name, file)

			onUpload(formData)
		}
	}
</script>

<input class="hidden" type="file" accept="{accepted}" name={name} onchange={upload} bind:this={fileInput}/>
<button onclick={selectFile}>
	<slot><span class="material-symbols-outlined">upload</span></slot>
</button>
