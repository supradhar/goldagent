from .base_agent import BaseAgent
from .personas.persona_configs import PERSONA_CONFIGS
from loguru import logger

class DynamicAgent(BaseAgent):
	"""Generic agent that takes any persona config."""
	pass  # All logic in BaseAgent

class AgentRegistry:
	"""Manages the full swarm of 50-100 agents."""
	def __init__(self):
		self.agents = []
		self._load_agents()

	def _load_agents(self):
		"""Load all agents from config."""
		for config in PERSONA_CONFIGS:
			agent = DynamicAgent(config)
			self.agents.append(agent)
		logger.info(f"Loaded {len(self.agents)} agents into registry")

	def get_agents_by_type(self, agent_type: str):
		return [a for a in self.agents if a.agent_type == agent_type]

	def get_all_agents(self):
		return self.agents

	def get_agent_count(self):
		return len(self.agents)
