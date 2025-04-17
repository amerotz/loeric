How does LOERIC work?
=====================

LOERIC reads a MIDI file and outputs it note by note (or, more exactly, MIDI event by MIDI event) after having processed each note (event) according to some performance rules.
LOERIC models three performance aspects:

* Ornamentation;
* Dynamics;
* Tempo.

These aspects are easily mappable onto MIDI parameters (e.g. pitch, velocity, event time) and make the system compatible with any MIDI application.

Contours
--------
For each of the modeled aspects, LOERIC estimates a note-wise "intensity contour" that tries to model "performance intensity" at a given moment. This will map to overall velocity, tempo drift and chance of ornamenting notes.

There are various ways of computing such contours: the ones we use so far rely on a measure of "note importance" found in Ó Canainn's book "Traditional Music Of Ireland". A more in-depth explanation is available in our (soon available) submission to CMMR 2023.

Ornaments
---------

We model a few kinds of ornaments consistent with Irish traditional music practice, among the most common ones.

Rolls & cuts
^^^^^^^^^^^^

These ornaments accentuate a note or break note repetitions by adding "acciaccaturas" to notes, from above in the case of cuts, from above and then below in the case of rolls. Rolls are equivalent to the classical "gruppettos", but tend to be snappier and less structured.

Slides
^^^^^^

Slides consist in sliding into notes from below. This is very common on non-pitch-quantized instruments, such as the fiddle and the violin, or in instruments that allow considerable amounts of bending (e.g. the tin whistle).

Dropping notes
^^^^^^^^^^^^^^

Sometimes notes can just be dropped, for no reason other than fingers not being fast enough or willingly to leave more space in the performance. We consider this an ornament since it can be easily modeled as such.

Errors
^^^^^^

Errors are just errors: you play the wrong note because you miss the right one. We allow for both chromatic and diatonic errors, trying to match the use of chromatic (e.g. the violin) or diatonic instruments (e.g. the concertina). Again, we consider this an ornament since it can be easily modeled as such.

Dynamics
--------

Dynamics are modeled via MIDI velocity. The correspondent intensity contour is mapped in the interval ``[0,127]`` and set as the note velocity. We further accentuate every note that falls on a beat by increasing its velocity by a fixed amount.

Tempo
--------

Tempo is modeled as a shift in performance BPM, with lower intensity corresponding to a slower tempo and higher intensity to a faster tempo.
In the first iteration of the system, the maximum amount of tempo drift was modeled as a percentage of the original tempo (e.g. 10% slower). We have now switched to a fixed amount of BPM around the original tempo (e.g. ±10 BPM).

Microtiming
^^^^^^^^^^^

By "microtiming" we mean a random shift of MIDI event times in the order of milliseconds (in practice, could be set to any value). Microtiming is most useful when having more than one instrument playing, as it outphases the instruments and makes the sound of the ensemble more natural, instead of completely synchronized. At the moment microtiming is not contour-dependent since it is not explicitly connected to performance intensity, but rather the normal imperfections of human playing.
