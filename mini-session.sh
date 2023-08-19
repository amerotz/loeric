for t in mini_session/*.mid; do
	for c in mini_session/*.json; do
		python3 loeric $t -i 0 -o 0 --config $c --save --output-dir $c-1 --seed 42069 -bpm 150 -t 2
	done
done
