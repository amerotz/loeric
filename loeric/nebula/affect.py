# install python modules
import logging
import os
import sys
from random import random, randrange
from time import sleep, time
import mido

# import project modules
from loeric.nebula.hivemind import DataBorg

# [STREAMING]
stream_list = [
    'mic_in',
    'rnd_poetry',
    'move_rnn',
    'affect_rnn',
    'self_awareness',
]

class Affect:
    def __init__(
        self,
        speed: int = 5,
    ):
        """
        Analyses the constant stream of data being emitted from the NNets. Sets up
        a series of gesture mapped loops which selects a specific stream.
        certain behaviours are determined by the chosen stream.
        In a poetic sense this feels the music and datastreams and g
        ates an output depending on range parameters.
        Args:
            ai_signal_obj: GotAISignal object for data emissions
            speed: behavioural speed of processes (this is currently being superceeded by temperature)
        """

        # set global path
        sys.path.insert(0, os.path.abspath('..'))

        # open a hivemind
        self.hivemind = DataBorg()

        # start operating vars
        self.running = True

        # calculate the inverse of speed
        # NewValue = (((OldValue - OldMin) * (NewMax - NewMin)) / (OldMax - OldMin)) + NewMin
        self.global_speed = ((speed - 1) * (0.1 - 1) / (10 - 1)) + 1
        logging.info(
            'user def speed = %f, global speed = %f', speed, self.global_speed
        )

        # own the signal object for emission
        self.midi_outport = mido.open_output()

    def gesture_manager(self):
        """
        Listens to the realtime incoming signal that is stored in the dataclass ("mic_in")
        and calculates an affectual response based on general boundaries:
            HIGH - if input stream is LOUD (0.8+) then emit, smash a random fill and break out to Daddy cycle...
            MEDIUM - if input energy is 0.3-0.8 then emit, a jump out of child loop
            LOW - nothing happens, continues with cycles
        """

        # names for affect listening
        # stream_list = stream_list
        stream_list_len = len(stream_list)
        # little val for emission control avoiding repeated vals
        self.old_val = 0

        self.rhythm_rate = self.hivemind.rhythm_rate

        while self.hivemind.running:
            # flag for breaking a phrase from big affect signal
            self.hivemind.interrupt_bang = True

            #############################
            # Phrase-level gesture gate: 3 - 8 seconds
            #############################
            # calc rhythmic intensity based on self-awareness factor & global speed
            intensity = self.hivemind.self_awareness
            logging.debug(
                '////////////////////////   intensity =  %fintensity', intensity
            )

            phrase_length = randrange(300, 800) / 100  # + self.global_speed
            phrase_loop_end = time() + phrase_length

            logging.debug(
                '\t\t\t\t\t\t\t\t=========AFFECT - Daddy cycle started ==========='
            )
            logging.debug(
                "                 interrupt_listener: started! Duration =  %f seconds",
                phrase_length,
            )

            while time() < phrase_loop_end:
                logging.info('================')

                # if a major break out then go to Daddy cycle and restart
                if not self.hivemind.interrupt_bang:
                    logging.info(
                        "-----------------------------INTERRUPT----------------------------"
                    )
                    break

                # generate rhythm rate here
                self.rhythm_rate = (
                    randrange(10, 80) / 100
                )  # * self.global_speed

                # self.rhythm_rate = self.hivemind.rhythm_rate

                logging.debug(
                    '\t\t\t\t\t\t\t\t=========Hello - child cycle 1 started ==========='
                )

                ##################################################################
                # choose thought stream from data streams from Nebula/ live inputs
                ##################################################################

                # randomly pick an input stream for this cycle
                # 63% will be mic in for Steve!!
                # either mic_in, random, net generation or self-awareness
                if random() > 0.63:
                    rnd = randrange(stream_list_len)
                    rnd_stream = stream_list[rnd] # random from list
                else:
                    rnd_stream = stream_list[0] # live mic in
                self.hivemind.thought_train_stream = rnd_stream
                logging.info(f'Random stream choice = {rnd_stream}')

                #############################
                # Rhythm-level gesture gate: .5-2 seconds
                # THis streams the chosen data
                #############################
                # rhythmic loop 0.5-2 (or 1-4) secs, unless interrupt bang
                rhythm_loop = time() + (randrange(500, 2000) / 1000)
                logging.debug('end time = %f', rhythm_loop)

                while time() < rhythm_loop:
                    logging.debug(
                        '\t\t\t\t\t\t\t\t=========Hello - baby cycle 2 ==========='
                    )

                    # make the master output the current value of the affect stream
                    # 1. go get the current value from dict
                    thought_train = getattr(self.hivemind, rnd_stream)
                    logging.info(
                        f'######################           Affect stream output {rnd_stream} == {thought_train}'
                    )

                    # 2. send to Master Output
                    self.hivemind.master_stream = thought_train

                    # emit data
                    logging.info(
                        f'\t\t ==============  thought_train output = {thought_train}'
                    )
                    self.emitter(thought_train)

                    # 3. modify speed and accel through self awareness
                    # calc rhythmic intensity based on self-awareness factor & global speed
                    self_awareness = getattr(self.hivemind, 'self_awareness')
                    logging.debug(
                        f'////////////////////////   self_awareness =  {self_awareness}'
                    )

                    ######################################
                    #
                    # Makes a response to chosen thought stream
                    #
                    ######################################

                    if thought_train >= 0.7:
                        logging.info('interrupt > HIGH !!!!!!!!!')

                        # A - refill dict with random
                        self.hivemind.randomiser()

                        # B - jumps out of this loop into daddy
                        self.hivemind.interrupt_bang = False

                        # C - emit
                        self.emitter(thought_train)

                        # D- break out of this loop, and next (cos of flag)
                        break

                    # MEDIUM
                    # if middle loud fill dict with random, all processes norm
                    elif 0.3 < thought_train < 0.7:
                        logging.info('interrupt MIDDLE -----------')

                        # emit
                        self.emitter(thought_train)

                        # A. jumps out of current local loop, but not main one
                        break

                    # LOW
                    # nothing happens here
                    elif thought_train <= 0.3:
                        logging.info('interrupt LOW -----------')

                    # and wait for a cycle
                    sleep(self.rhythm_rate)

        logging.info('quitting gesture manager thread')

    def emitter(self, incoming_emission: float):
        """
        Sends the stream output from the gesture manager through the
        emissions systems to other scripts.
        Args:
            incoming_emission: output float from gesture manager
        """
        if incoming_emission != self.old_val:

            cc_value = int(incoming_emission * 127)

            # self.ai_signal.ai_str.emit(str(incoming_emission))
            msg = mido.Message(type='control_change',
                               value=cc_value
                               )

            self.midi_outport.send(msg)

            logging.info(
                 '//////////////////                   EMITTING and making sound'
            )

        self.old_val = incoming_emission
