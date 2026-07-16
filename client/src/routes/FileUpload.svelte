<script lang="ts">
/*
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
*/
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
