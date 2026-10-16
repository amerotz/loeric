# This file is part of LOERIC.

# LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.

for i in $(seq 1 $2);
do
	sem -j+0 loeric $1 -r $3 -hi 0.75 -bpm 180 -hic 22 -ic 21 --no-prompt --no-end-note -mc $i --seed $i --save --output-dir ~/git/loeric-other/tunes/multi --name loeric_$i --config $4 --sync --create-sync --create-out --create-in &
done
sem --wait
