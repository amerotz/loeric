for s in 100 101 69 420; do
	python3 loeric paper_examples/slides/slide23.mid --config new_conf.json -bpm 150 -o 0 -i 1 -c 20 --save --seed $s --output-dir artifacts
done
