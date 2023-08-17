rm paper_examples/generated -fr
for d in paper_examples/*; do
	echo $d
	for t in $d/*.mid; do
		echo "\t"$t
		python3 loeric $t -i 0 -o 0 --config $d/conf.json --save --output-dir paper_examples/generated --seed 69420
	done
done
