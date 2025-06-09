for i in $(seq 1 $2);
do
	sem -j+0 loeric $1 -r $3 -hi 0.75 -bpm 180 -hic 22 -ic 21 --no-prompt --no-end-note -mc $i --seed $i --save --output-dir ~/git/loeric-other/tunes/multi --name loeric_$i --config $4 --sync --create-sync --create-out --create-in &
done
sem --wait
