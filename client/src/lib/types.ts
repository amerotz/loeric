export interface Musician {
	id: string,
	name: string,
	config: string,
	midiIn: string,
	midiOut: string,
	instrument: string,
	controls: {
		name: string,
		control: number,
		value: number
	}[]
}

export interface Options {
	'trackList': string[],
	'outputs': string[],
	'inputs': string[],
	'instruments': string[],
	'audio_inputs': { [id: string]: number },
	'audio_outputs': { [id: string]: number }
}

export interface Track {
	'name': string,
	'time': string,
	'key': string,
	'tempo': number,
	'config': any
}

export enum LoericPlayingState {
	STOPPED = 'STOPPED',
	PAUSED = 'PAUSED',
	PLAYING = 'PLAYING',
}

export interface LoericState {
	'track': Track,
	'state': LoericPlayingState,
	'options': Options
	'musicians': Musician[],
}
