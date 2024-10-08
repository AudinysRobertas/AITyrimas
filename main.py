import os
import random
import sys
import time
from functools import partial
from typing import Any

import cupy as cp
import cv2
import gymnasium as gym
import numpy as np
import stable_baselines3 as sb3
import torch
import yaml
from metadrive import MetaDriveEnv, SafeMetaDriveEnv
from metadrive.component.sensors.rgb_camera import RGBCamera
from metadrive.envs.base_env import BaseEnv
from metadrive.policy.idm_policy import IDMPolicy
from stable_baselines3.common.vec_env import SubprocVecEnv


class Policy:
    def __init__(self, config: dict) -> None:
        self.seed = config["seed"]

    def get_action(self, obs: np.ndarray) -> np.ndarray:
        return np.array([0, 1])


class DataCollector:
    def __init__(self, config: dict, policy:Policy=None) -> None:
        self.seed = config["seed"]
        self.config = config
        # self.envs = 
        self.policy = policy

    def create_env(self, env_config: dict[str, Any], seed: int = None) -> gym.Env:
        # lidar data still retuned be env
        print(seed)
        sim_config = env_config["environment"].copy()
        sim_config.update(
            {
                "image_observation": True,
                "vehicle_config": dict(image_source="main_camera"),
                "sensors": {"main_camera": ()},
                "agent_policy": IDMPolicy,  # drive with IDM policy
                "image_on_cuda": True,
                "window_size": tuple(env_config["environment"]["window_size"]),
                "start_seed": seed if seed is None else self.seed,
                "use_render":False,
                "show_interface":False,
                "show_logo":False,
                "show_fps":False,
            }
        )
        env = MetaDriveEnv(sim_config)
        return env

    def show_view(self, observations: np.ndarray | cp.ndarray) -> None:
        frames = observations[0]["image"]
        if len(frames.shape) == 4:
            image = frames[..., -1] * 255  # [0., 1.] to [0, 255]
        elif len(frames.shape) == 5:        
            frames = frames[:, ..., -1]
            image = np.concatenate([f for f in frames], axis=1)
            image *= 255
        image: np.array = cp.asnumpy(image.astype(np.uint8))

        cv2.imshow("frame", image)
        if cv2.waitKey(1) == ord("q"):
            return

    def collect_frames(self) -> np.ndarray|cp.ndarray:
        frames = []
        seed = self.config["seed"]
        total_samples = self.config["training"]["batch_size"]
        if self.config["simulation"]["simulations_count"] == 1:
            env = self.create_env(self.config, seed)
            start_time = time.perf_counter()
            env.reset()
            for frame_index in range(total_samples):
                obs = env.step(env.action_space.sample())
                if self.config["simulation"]["show_view"]:
                    self.show_view(obs)
                frames.append(obs[:3])
                if obs[2] or obs[3]:
                    env.reset()
            end_time = time.perf_counter()
            print("FPS:", frame_index / (end_time - start_time))
            print("Time elapsed:", end_time - start_time)

            # observations = list(zip(*(frames[1:])))
            # test = [timestep["image"] for timestep in observations[0]]
            # test = cp.stack(test, axis=0)
            # return test
        else:
            envs_count = self.config["simulation"]["simulations_count"]
            parallel_envs = SubprocVecEnv(
                [
                    partial(self.create_env, self.config, seed+index)
                    for index in range(envs_count)
                ]
            )
            start_time = time.perf_counter()
            obs = parallel_envs.reset()
            for frame_index in range(total_samples):
                actions = np.array(
                    [parallel_envs.action_space.sample() for _ in range(envs_count)]
                )
                parallel_envs.step_async(actions)
                obs = parallel_envs.step_wait()
                if self.config["simulation"]["show_view"]:
                    self.show_view(obs)
                frames.append(obs[:3])
            end_time = time.perf_counter()
            print("FPS:", frame_index * envs_count / (end_time - start_time))
            print("Time elapsed:", end_time - start_time)
        return frames


def main() -> None:
    config: dict = yaml.safe_load(open("configs/main.yaml", "r"))
    print(f"Cores count: {os.cpu_count()}")
    random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    np.random.seed(config["seed"])
    collector = DataCollector(config)
    frames = collector.collect_frames()
    print(len(frames))
    # env = create_env(config)
    # run(env)


if __name__ == "__main__":
    main()
    sys.exit(0)





