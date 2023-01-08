from abc import ABC, abstractmethod
from .vectorobservation import VectorObservation
from .vectoragent import VectorAgent
from dataclasses import dataclass

from typing import Optional, List, Tuple

import gym
import torch

class PlayerException(Exception):
    """ Raise when players in the environment are incorrectly set """


@dataclass
class DummyEnv():
    """
    Environment representing a partner agent's observation and action space.
    """
    observation_space: gym.spaces.Space
    action_space: gym.spaces.Space


class VectorMultiAgentEnv(ABC):
    """
    Base class for all Multi-agent environments.

    :param ego_ind: The player that the ego represents
    :param n_players: The number of players in the game
    :param resample_policy: The resampling policy to use
    - (see set_resample_policy)
    :param partners: Lists of agents to choose from for the partner players
    :param ego_extractor: Function to extract Observation into the type the
        ego expects
    """

    def __init__(self,
                 num_envs: int,
                 device: torch.device,
                 ego_ind: int = 0,
                 n_players: int = 2,
                 resample_policy: str = "default",
                 partners: Optional[List[List[VectorAgent]]] = None):
        self.num_envs = num_envs
        self.device = device
        
        self.ego_ind = ego_ind
        self.n_players = n_players
        if partners is not None:
            if len(partners) != n_players - 1:
                raise PlayerException(
                    "The number of partners needs to equal the number \
                    of non-ego players")

            for plist in partners:
                if not isinstance(plist, list) or not plist:
                    raise PlayerException(
                        "Sublist for each partner must be nonempty list")

        self.partners = partners or [[]] * (n_players - 1)
        self.partnerids = [0] * (n_players - 1)

        self._obs: Tuple[Optional[np.ndarray], ...] = tuple()

        # self._dones = torch.zeros((n_players, num_envs), dtype=torch.bool, device=device)
        # self._alives = torch.ones((n_players, num_envs), dtype=torch.bool, device=device)
        self._actions = None
        self.set_resample_policy(resample_policy)

    def getDummyEnv(self, player_num: int):
        """
        Returns a dummy environment with just an observation and action
        space that a partner agent can use to construct their policy network.

        :param player_num: the partner number to query
        """
        return self

    def _get_partner_num(self, player_num: int) -> int:
        if player_num == self.ego_ind:
            raise PlayerException(
                "Ego agent is not set by the environment")
        elif player_num > self.ego_ind:
            return player_num - 1
        return player_num

    def add_partner_agent(self, agent: VectorAgent, player_num: int = 1) -> None:
        """
        Add agent to the list of potential partner agents. If there are
        multiple agents that can be a specific player number, the environment
        randomly samples from them at the start of every episode.

        :param agent: VectorAgent to add
        :param player_num: the player number that this new agent can be
        """
        self.partners[self._get_partner_num(player_num)].append(agent)

    def set_partnerid(self, agent_id: int, player_num: int = 1) -> None:
        """
        Set the current partner agent to use

        :param agent_id: agent_id to use as current partner
        """
        partner_num = self._get_partner_num(player_num)
        assert(agent_id >= 0 and agent_id < len(self.partners[partner_num]))
        self.partnerids[partner_num] = agent_id

    def resample_random(self) -> None:
        """ Randomly resamples each partner policy """
        self.partnerids = [np.random.randint(len(plist))
                           for plist in self.partners]

    def resample_round_robin(self) -> None:
        """
        Sets the partner policy to the next option on the list for round-robin
        sampling.

        Note: This function is only valid for 2-player environments
        """
        self.partnerids = [(self.partnerids[0] + 1) % len(self.partners[0])]

    def set_resample_policy(self, resample_policy: str) -> None:
        """
        Set the resample_partner method to round "robin" or "random"

        :param resample_policy: The new resampling policy to use.
        - Valid values are: "default", "robin", "random"
        """
        if resample_policy == "default":
            resample_policy = "robin" if self.n_players == 2 else "random"

        if resample_policy == "robin" and self.n_players != 2:
            raise PlayerException(
                "Cannot do round robin resampling for >2 players")

        if resample_policy == "robin":
            self.resample_partner = self.resample_round_robin
        elif resample_policy == "random":
            self.resample_partner = self.resample_random
        else:
            raise PlayerException(
                f"Invalid resampling policy: {resample_policy}")

    def _get_actions(self, obs, ego_act=None):
        actions = []
        for player, ob in zip(range(self.n_players), obs):
            if player == self.ego_ind:
                actions.append(ego_act)
            else:
                p = self._get_partner_num(player)
                agent = self.partners[p][self.partnerids[p]]
                actions.append(agent.get_action(ob))
        if self._actions is None:
            self._actions = torch.stack(actions)
        else:
            torch.stack(actions, out=self._actions)
        return self._actions

    def _update_players(self, rews, done):
        # self._dones = (self._dones & torch.logical_not(self._alives)) | done
        # self._alives = torch.stack([o.active for o in self._obs], out=self._alives)
        
        for i in range(self.n_players - 1):
            playernum = i + (0 if i < self.ego_ind else 1)
            nextrew = rews[playernum]
            nextdone = done  # self._dones[playernum]
            self.partners[i][self.partnerids[i]].update(nextrew, nextdone)
        
    def step(
                self,
                action: torch.Tensor
            ):
        """
        Run one timestep from the perspective of the ego-agent. This involves
        calling the ego_step function and the alt_step function to get to the
        next observation of the ego agent.

        Accepts the ego-agent's action and returns a tuple of (observation,
        reward, done, info) from the perspective of the ego agent.

        :param action: An action provided by the ego-agent.

        :returns:
            observation: Ego-agent's next observation
            reward: Amount of reward returned after previous action
            done: Whether the episode has ended
            info: Extra information about the environment
        """

        acts = self._get_actions(self._obs, action)
        self._obs, rews, done, info = self.n_step(acts)
        
        self._update_players(rews, done)

        ego_obs = self._obs[self.ego_ind]
        ego_rew = rews[self.ego_ind]
        ego_done = done  # self._dones[self.ego_ind]
        return ego_obs, ego_rew, ego_done, info

    def reset(self):
        """
        Reset environment to an initial state and return the first observation
        for the ego agent.

        :returns: Ego-agent's first observation
        """
        self.resample_partner()
        self._obs = self.n_reset()

        # self._alives.fill_(1)
        # self._dones.fill_(0)

        ego_obs = self._obs[self.ego_ind]

        return ego_obs

    @abstractmethod
    def n_step(
                    self,
                    actions: torch.Tensor,
                ):
        """
        Perform the actions specified by the agents that will move. This
        function returns a tuple of (next agents, observations, both rewards,
        done, info).

        This function is called by the `step` function.

        :param actions: List of action provided agents that are acting on this
        step.

        :returns:
            observations: List representing the next VectorObservations
            rewards: Tensor representing the rewards of all agents: num_agents x num_envs
            done: Whether the episodes have ended
            info: Extra information about the environment
        """

    @abstractmethod
    def n_reset(self):
        """
        Reset the environment and return which agents will move first along
        with their initial observations.

        This function is called by the `reset` function.

        :returns:
            observations: List of VectorObservations representing the observations of
                each agent
        """


def to_torch(a):
    return a.detach().clone()


class MadronaEnv(VectorMultiAgentEnv):

    def __init__(self, num_envs, gpu_id, sim, debug_compile=True):
        super().__init__(num_envs, device=torch.device('cuda', gpu_id))

        self.sim = sim

        self.static_dones = self.sim.done_tensor().to_torch()
        
        self.static_active_agents = self.sim.active_agent_tensor().to_torch().to(torch.bool)
        self.static_actions = self.sim.action_tensor().to_torch()
        self.static_observations = self.sim.observation_tensor().to_torch()
        self.static_agent_states = self.sim.agent_state_tensor().to_torch()
        self.static_action_masks = self.sim.action_mask_tensor().to_torch().to(torch.bool)
        self.static_rewards = self.sim.reward_tensor().to_torch()
        self.static_worldID = self.sim.world_id_tensor().to_torch().to(torch.long)
        self.static_agentID = self.sim.agent_id_tensor().to_torch().to(torch.long)

        self.static_scattered_active_agents = self.static_active_agents.detach().clone()
        self.static_scattered_observations = self.static_observations.detach().clone()
        self.static_scattered_agent_states = self.static_agent_states.detach().clone()
        self.static_scattered_action_masks = self.static_action_masks.detach().clone()
        self.static_scattered_rewards = self.static_rewards.detach().clone()

        self.static_scattered_active_agents[self.static_agentID, self.static_worldID] = self.static_active_agents
        self.static_scattered_observations[self.static_agentID, self.static_worldID, :] = self.static_observations
        self.static_scattered_agent_states[self.static_agentID, self.static_worldID, :] = self.static_agent_states
        self.static_scattered_action_masks[self.static_agentID, self.static_worldID, :] = self.static_action_masks
        self.static_scattered_rewards[self.static_agentID, self.static_worldID] = self.static_rewards

        self.infos = [{}] * self.num_envs

    def n_step(self, actions):
        self.static_actions.copy_(actions[self.static_agentID, self.static_worldID, :])

        self.sim.step()

        self.static_scattered_active_agents[self.static_agentID, self.static_worldID] = self.static_active_agents
        self.static_scattered_observations[self.static_agentID, self.static_worldID, :] = self.static_observations
        self.static_scattered_agent_states[self.static_agentID, self.static_worldID, :] = self.static_agent_states
        self.static_scattered_action_masks[self.static_agentID, self.static_worldID, :] = self.static_action_masks
        self.static_scattered_rewards[self.static_agentID, self.static_worldID] = self.static_rewards

        obs = [VectorObservation(to_torch(self.static_scattered_active_agents[i]),
                                 to_torch(self.static_scattered_observations[i]),
                                 to_torch(self.static_scattered_agent_states[i]),
                                 to_torch(self.static_scattered_action_masks[i]))
               for i in range(2)]

        return obs, to_torch(self.static_scattered_rewards), to_torch(self.static_dones), self.infos

    def n_reset(self):
        self.static_scattered_active_agents[self.static_agentID, self.static_worldID] = self.static_active_agents
        self.static_scattered_observations[self.static_agentID, self.static_worldID, :] = self.static_observations
        self.static_scattered_agent_states[self.static_agentID, self.static_worldID, :] = self.static_agent_states
        self.static_scattered_action_masks[self.static_agentID, self.static_worldID, :] = self.static_action_masks
        self.static_scattered_rewards[self.static_agentID, self.static_worldID] = self.static_rewards

        obs = [VectorObservation(to_torch(self.static_scattered_active_agents[i]),
                                 to_torch(self.static_scattered_observations[i]),
                                 to_torch(self.static_scattered_agent_states[i]),
                                 to_torch(self.static_scattered_action_masks[i]))
               for i in range(2)]
        return obs

    def close(self, **kwargs):
        pass