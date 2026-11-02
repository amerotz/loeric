How does LOERIC work?
=====================

LOERIC takes in input a monophonic score in MIDI or ABC format and a configuration file describing the behaviour of the system.

LOERIC's core paradigm is the following: the input tune is processed note-by-note through a series of modules, each implementing specific musical performance rules (e.g., applying swing, changing dynamics, replacing some notes with other notes, etc).

Most modules make these decisions based on various note-wise attributes, which are either attributes of the note itself (e.g., pitch or timing) or specially computed and stored in contours, e.g. rhythmic patterns, phrase arcs, ornament probability etc. The number, type and order of modules is specified in configuration files, alongside eventual module parameters and which contours they take in input.

Contours are also the core of LOERIC's interaction: its contours can be weighted with usually generated signals to steer the system's performance in various ways. For example, one setup involves sending LOERIC the volume of the human musician and connecting it to LOERIC's dynamics, so that if the musician is playing softly, LOERIC's velocity contour will be veraged with it and the system will play softly too. Both how much influence the user signal has on LOERIC and how it affects which contours can be defined in the configuration file.
