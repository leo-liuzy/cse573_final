""" Contains the Episodes for Navigation. """
import random
import torch
import time
import sys
from constants import *
from environment import Environment
from utils.net_util import gpuify
import numpy as np
from math import sqrt


class Episode:
    """ Episode for Navigation. """
    def __init__(self, args, gpu_id, rank, strict_done=False):
        super(Episode, self).__init__()

        self._env = None

        self.gpu_id = gpu_id
        self.strict_done = strict_done
        self.task_data = None
        self.glove_embedding = None

        self.seed = args.seed + rank
        random.seed(self.seed)

        with open('./datasets/objects/int_objects.txt') as f:
            int_objects = [s.strip() for s in f.readlines()]
        with open('./datasets/objects/rec_objects.txt') as f:
            rec_objects = [s.strip() for s in f.readlines()]
        
        self.objects = int_objects + rec_objects
        self.actions_list = [{'action': a} for a in ADVANCED_ACTIONS]
        self.actions_taken = []
        self.done_each_action = [0, 0]  # store agents' judgements
        self.successes = [0, 0]
        # self.seen_objects = [0 for _ in range(len(self.objects))]
        self.success = False
        self.distances = [float('inf'), float('inf')]
        self.args = args

    @property
    def environment(self):
        return self._env

    def state_for_agent(self):
        return self.environment.current_frame

    def step(self, action_as_int):
        action = self.actions_list[action_as_int]
        self.actions_taken.append(action)
        return self.action_step(action)

    def action_step(self, action):
        self.environment.step(action)
        reward, terminal, action_was_successful = self.judge(action)

        return reward, terminal, action_was_successful

    def slow_replay(self, delay=0.2):
        # Reset the episode
        self._env.reset(self.cur_scene, change_seed=False)
        
        for action in self.actions_taken:
            self.action_step(action)
            time.sleep(delay)
    @staticmethod
    def cal_distance(pos1, pos2):
        dx = pos1['x'] - pos2['x']
        dy = pos1['y'] - pos2['y']
        dz = pos1['z'] - pos2['z']
        return sqrt(dx**2 + dy**2 + dz**2)

    def judge(self, action):
        """ Judge the last event. """
        # TODO: change for two objects
        # immediate reward
        reward = STEP_PENALTY

        # all_done = False

        action_was_successful = self.environment.last_action_success
        all_done = False
        if action['action'] in [PICKUP_OBJECT, COOK]:

            done_action_id = [PICKUP_OBJECT, COOK].index(action['action'])

            self.done_each_action[done_action_id] = 1

            if action_was_successful:
                self.successes[done_action_id] = 1
                reward += SUCCESS_REWARD

        if self.successes[0] and self.target != 'Microwave':
            # if tomato in hand
            self.target = 'Microwave'
            self.distance = float("Inf")

        if self.args.improve:
            objects = self._env.last_event.metadata['objects']
            agent_pos = self._env.last_event.metadata['agent']['position']

            visible_objects = [o['objectType'] for o in objects if o['visible']]
            if self.target in visible_objects:
                object_meta = [o for o in objects if o['objectType'] == self.target]
                assert len(object_meta) == 1
                object_meta = object_meta[0]
                pos = object_meta['position']
                distance2agent = self.cal_distance(pos, agent_pos)
                if distance2agent < self.distances:
                    # if we are getting closer to the object \and
                    # the object is not "done"(consider by the agent) yet.
                    reward -= STEP_PENALTY
                    self.distances = distance2agent
            # if self.target in visible_objects and action['action'] in ['LookUp', 'LookDown', 'RotateLeft', 'RotateRight']:
            #     reward -= STEP_PENALTY * 0.5

        if not action_was_successful:
            reward += STEP_PENALTY * 2

        assert all_done in [True, False]
        self.success = all(self.successes)
        all_done = self.success
        # print("action: {}, success: {}, reward: {}".format(action['action'], action_was_successful, reward))
        return reward, all_done, action_was_successful

    def new_episode(self, args, scene, change_seed=True):
        
        if self._env is None:
            if args.arch == 'osx':
                local_executable_path = './datasets/builds/thor-local-OSXIntel64.app/Contents/MacOS/thor-local-OSXIntel64'
            else:
                local_executable_path = './datasets/builds/thor-local-Linux64'
            
            self._env = Environment(
                    grid_size=args.grid_size,
                    fov=args.fov,
                    local_executable_path=local_executable_path,
                    randomize_objects=args.randomize_objects,
                    seed=self.seed)
            self._env.start(scene, self.gpu_id)
        else:
            self._env.reset(scene, change_seed=change_seed)

        # For now, single target.BowlTomato
        self.target = 'Tomato'
        self.success = False
        self.done_each_action = [0 for _ in self.done_each_action]
        self.successes = [0 for _ in self.successes]
        self.cur_scene = scene
        if change_seed:
            self.actions_taken = []
        self.distances = float('inf')
        
        return True