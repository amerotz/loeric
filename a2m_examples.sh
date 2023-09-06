#rm new_abc/ -fr
#mkdir new_abc/mid -p
#for t in mid/*.mid; do
	#midi2abc $t -o new_abc/$t.abc
#done
mv new_abc/mid new_abc/abc
mkdir new_abc/mid/abc -p
for t in new_abc/abc/*abc; do
	echo $t
	abc2midi $t -o new_abc/mid/$t -BF 2
done
