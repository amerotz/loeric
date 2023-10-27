"""
Embodied AI Engine Prototype AKA "Nebula".
This object takes a live signal (such as body tracking,
or real-time sound analysis) and generates a response that
aims to be felt as co-creative. The response is a flow of
neural network emissions data packaged as a dictionary,
and is gestural over time. This, when plugged into a responding
script (such as a sound generator, or QT graphics) gives
the feeling of the AI creating in-the-moment with the
human in-the-loop.

© Craig Vear 2023
craig.vear@nottingham.ac.uk
"""

import logging
from random import random, randrange

# import python modules
from threading import Thread
from time import sleep

import numpy as np
import tensorflow as tf

from loeric.nebula.affect import Affect

# install local modules
from loeric.nebula.hivemind import DataBorg
from loeric.nebula.listener import Listener

class NNet:
    """
    Makes an object  for each neural net in AI factory.

    Args:
        name: name of NNet - must align to name of object
        model: location of ML model for this NNet
        nnet_feed: NNet output value from DataBorg to use as input value
        live_feed: Human input value from DataBorg to use as input value
    """

    def __init__(
        self,
        name: str,
        model: str,
        nnet_feed: str,
        live_feed: str = None,
    ):

        self.hivemind = DataBorg()
        self.name = name
        self.nnet_feed = nnet_feed
        self.live_feed = live_feed
        self.which_feed = "net"

        self.model = tf.keras.models.load_model(model)
        print(f"{name} initialized")

    def make_prediction(self, in_val: float):
        """
        Makes a prediction for this NNet.
        Args:
            in_val: 1D input value for this NNet might be feedback or live input
        """
        # make prediction
        prediction = self.model.predict(in_val, verbose=0)

        # get random variable from prediction and save to data dict
        individual_val = prediction[0][randrange(4)]
        setattr(self.hivemind, self.name, individual_val)
        logging.debug(
            f"NNet {self.name} in: {in_val} predicted {individual_val}"
        )


class NebulaAI(Affect, Listener):
    """
    Nebula is the core "director" of an AI factory.
       It generates data in response to incoming percepts
      from human-in-the-loop interactions, and responds
      in-the-moment to the gestural input of live data.
      There are 4 components:
          Nebula: as "director" it coordinates the overall
              operations of the AI Factory
          AIFactory: builds the neural nets that form the
              factory, coordinates data exchange,
              and liases with the common data dict
          NebulaDataClass: is the central dataclass that
              holds and shares all the  data exchanges
              in the AI factory
          Affect: receives the live percept input from
              the client and produces an affectual response
              to it's energy input, which in turn interferes
              with the data generation.

      Args:
          ai_signal_object: a GotAISignal object for emitting data
          speed: general tempo/ feel of Nebula's response (0.5 ~ moderate fast, 1 ~ moderato; 2 ~ presto)


    Builds the individual neural nets that constitute the AI factory.
    This will need modifying if and when a new AI factory design is implemented.
    NB - the list of netnames will also need updating
    """

    def __init__(
        self,
        # ai_signal_obj: GotAISignal,
        speed: int = 1,
    ):
        Affect.__init__(self, speed)   # (self, ai_signal_obj, speed)
        Listener.__init__(self)

        print('Building the AI Factory')

        self.net_logging = False
        self.hivemind = DataBorg()
        self.global_speed = speed
        self.running = True
        self.all_nets_predicting = True

        # instantiate nets as objects and make models
        print('NNet1 - MoveRNN initialization')
        self.move_rnn = NNet(
            name="move_rnn",
            model='ai/models/EMR-full-sept-2021_RNN_skeleton_data.nose.x.h5',
            nnet_feed='move_rnn',
            live_feed=str(),
        )

        print('NNet2 - AffectRNN initialization')
        self.affect_rnn = NNet(
            name="affect_rnn",
            model='ai/models/EMR-full-sept-2021_conv2D_move-affect.h5',
            nnet_feed='affect_rnn',
            live_feed=str(),
        )

        print('NNet3- MoveAffectCONV2 initialization')
        self.move_affect_conv2 = NNet(
            name="move_affect_conv2",
            model='ai/models/EMR-full-sept-2021_conv2D_move-affect.h5',
            nnet_feed='move_affect_conv2',
            live_feed=str(),
        )

        print('NNet4 - AffectMoveCONV2 initialization')
        self.affect_move_conv2 = NNet(
            name="affect_move_conv2",
            model='ai/models/EMR-full-sept-2021_conv2D_affect-move.h5',
            nnet_feed='affect_rnn',
            live_feed=str(),
        )

        print('NNet5 - self_awareness initialization')
        self.self_awareness = NNet(
            name="self_awareness",
            model='ai/models/EMR-full-sept-2021_conv2D_move-affect.h5',
            nnet_feed='master_stream',
            live_feed=str(),
        )

        self.netlist = [
            self.move_rnn,
            self.affect_rnn,
            self.move_affect_conv2,
            self.affect_move_conv2,
            self.self_awareness,
        ]

    def thread_loop(self):
        """
        Declares all threads, and sets them spinning
        """
        print("making AI threads")
        t1 = Thread(target=self.make_data)
        t2 = Thread(target=self.gesture_manager)
        t3 = Thread(target=self.snd_listen)

        t1.start()
        t2.start()
        t3.start()

    def make_data(self):
        """
        Makes a prediction for each NNet in the AI factory.

        Do not disturb - it has its own life cycle
        """

        while self.hivemind.running:
            # get the first rhythm rate from the hivemind
            rhythm_rate = self.hivemind.rhythm_rate

            # make a prediction for each of the NNets in the factory
            if self.all_nets_predicting:
                for net in self.netlist:
                    in_val = self.get_seed(net)
                    net.make_prediction(in_val)

            # or just the current one (with dependent if not self)
            else:
                current_stream = self.hivemind.thought_train_stream
                for net in self.netlist:
                    if net.name == current_stream:
                        if net.nnet_feed != net.name:
                            # get the net that feeds it

                            feed_net = getattr(self.netlist, net.nnet_feed)
                            in_val_dependent = self.get_seed(feed_net)
                            net.make_prediction(in_val_dependent)

                        in_val_self = self.get_seed(net)
                        net.make_prediction(in_val_self)

                        break

            # creates a stream of random poetry
            self.hivemind.rnd_poetry = random()

            # rest with chronos pulse
            sleep(rhythm_rate)

    def get_seed(self, net_name: NNet) -> float:
        """
        Gets the seed data for a given NNet from the original init.
        Args:
            net_name: the name of the NNet object
        Returns: the current seed from hivemind
        """
        which_feed = net_name.which_feed
        if which_feed == "net":
            seed_source = net_name.nnet_feed
            seed = getattr(self.hivemind, seed_source)
        else:
            seed_source = net_name.live_feed
            seed = getattr(self.hivemind, seed_source)
        return self.get_in_val(seed)

    def get_in_val(self, input_val):
        """
        Get the current value and reshape ready for input for prediction.
        Args:
            input_val: the float value to be reshaped for NNet prediction input data
        """
        input_val = np.reshape(input_val, (1, 1, 1))
        input_val = tf.convert_to_tensor(input_val, np.float32)
        return input_val

    def terminate(self):
        """
        This controls all termination runnings.
        Quit the loop like a grown up
        """
        self.hivemind.running = False
