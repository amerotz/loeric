Usage
=====

.. _installation:

Installation
------------
To use the package, clone the repository

.. code-block:: console

   git clone https://github.com/amerotz/loeric

Then create a virtual environment with

.. code-block:: bash

   python -m venv <environment name>

Activate the environment you created with

.. code-block:: bash

   source <environment name>/bin/activate

Then install the required packages with

.. code-block:: bash

   pip install -r requirements.txt

Performing a tune
-----------------
To perform a tune, invoke:

.. code-block: bash
   python loeric <tune MIDI file> [command line arguments]

where the possible arguments are

* ``source``: the midi file to play;
* ``-h, --help``: show the help message and exit;
* ``--list_ports``: list available input and output MIDI ports and exit;
* ``-c CONTROL, --control CONTROL``: the MIDI control signal number to use as human control;
* ``-hi HUMAN_IMPACT, --human_impact HUMAN_IMPACT``: the percentage of human impact over the performance (0: only generated, 1:only human);
* ``-i INPUT, --input INPUT``: the input MIDI port for the control signal;
* ``-o OUTPUT, --output OUTPUT``: the output MIDI port for the performance;
* ``-mc MIDI_CHANNEL, --midi-channel MIDI_CHANNEL``: the output MIDI channel for the performance;
* ``-t TRANSPOSE, --transpose TRANSPOSE``: the number of semitones to transpose the tune of;
* ``-r REPEAT, --repeat REPEAT``: how many times the tune should be repeated;
* ``-bpm BPM``: the tempo of the performance. If None, defaults to the original file's tempo;
* ``--save``: whether or not to export the performance. Playback will be disabled;
* ``--no-prompt``: whether or not to wait for user input before starting;
* ``--config CONFIG``: the path to a configuration file. Every option included in the configuration file will override command line arguments.

For example, to play the tune ``butterfly.mid`` on output port ``0`` on MIDI channel ``2``, while reading control input on control signal ``42`` on input port ``0``, with a human impact of ``0.5``, transposing by ``10`` semitones, repeating ``3`` times, at ``200`` BPM

.. code-block:: bash

   python loeric butterfly.mid -o 0 -mc 2 -c 42 -i 0 -hi 0.5 -t 10 -r 3 -bpm 200

All of these parameters and many internal ones can be changed with a configuration file:

.. code-block:: bash

   python loeric butterfly.mid --config conf.json

The configuration file has precedence over command line arguments. That means that if there is a field corresponding to performance BPM in the configuration file, the bpm flag in the command invocation will be ignored.

Some parameters are not specified in the configuration file and need to be given always as arguments; these are:

* the input port;
* the output port;
* repeats;
* saving;
* prompting.
   

Live Interaction
----------------
TBA



