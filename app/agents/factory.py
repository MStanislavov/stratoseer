"""Agent factory: creates singleton agents (mock or LLM-powered)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.base import AgentProtocol
from app.agents.ceo_agent import CEOAgent
from app.agents.cfo_agent import CFOAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.data_formatter import DataFormatterAgent
from app.agents.goal_extractor import GoalExtractorAgent
from app.agents.url_validator import URLValidatorAgent
from app.agents.web_scraper import WebScraperAgent
from app.llm.prompt_loader import PromptLoader


@dataclass
class AgentModelConfig:
    """Per-agent model assignments, populated from settings."""

    goal_extractor: str = ""
    web_scraper: str = ""
    data_formatter: str = ""
    ceo: str = ""
    cfo: str = ""
    cover_letter: str = ""
    url_validator: str = ""


class AgentFactory:
    """Creates stateless singleton agents.

    When llm is None, all agents run in mock mode (no LLM calls).
    When llm is provided, agents use structured output.
    Per-agent model overrides are applied via agent_models config.
    """

    def __init__(
        self,
        llm: Any | None = None,
        prompt_loader: PromptLoader | None = None,
        search_tool: Any | None = None,
        policy_engine: Any | None = None,
        agent_models: AgentModelConfig | None = None,
    ):
        self._llm = llm
        self._prompt_loader = prompt_loader
        self._search_tool = search_tool
        self._policy_engine = policy_engine
        self._agent_models = agent_models or AgentModelConfig()

        # Singleton agent instances
        self._goal_extractor: GoalExtractorAgent | None = None
        self._web_scraper: WebScraperAgent | None = None
        self._data_formatter: DataFormatterAgent | None = None
        self._ceo: CEOAgent | None = None
        self._cfo: CFOAgent | None = None
        self._cover_letter: CoverLetterAgent | None = None
        self._url_validator: URLValidatorAgent | None = None

        # Cache of ChatOpenAI instances keyed by model name
        self._llm_cache: dict[str, Any] = {}

    def _get_llm(self, model_override: str) -> Any | None:
        """Return an LLM instance for the given model, or the default LLM.

        If model_override is set and differs from the base LLM's model,
        create a new Agent LLM with that model (cached).
        """
        if self._llm is None:
            return None

        if not model_override:
            return self._llm

        # Check if the override matches the base LLM already
        base_model = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "")
        if model_override == base_model:
            return self._llm

        if model_override not in self._llm_cache:
            # Create a new LLM with the same settings but a different model
            from langchain_openai import ChatOpenAI

            self._llm_cache[model_override] = ChatOpenAI(
                model=model_override,
                temperature=self._llm.temperature,
                api_key=self._llm.openai_api_key,
            )
        return self._llm_cache[model_override]

    @property
    def is_live(self) -> bool:
        """Return True if agents will use a real LLM, False for mock mode."""
        return self._llm is not None

    def create_goal_extractor(self) -> AgentProtocol:
        """Return the singleton GoalExtractorAgent, creating it on first call."""
        if self._goal_extractor is None:
            self._goal_extractor = GoalExtractorAgent(
                llm=self._get_llm(self._agent_models.goal_extractor),
                prompt_loader=self._prompt_loader,
            )
        return self._goal_extractor

    def create_web_scraper(self) -> AgentProtocol:
        """Return the singleton WebScraperAgent, creating it on first call."""
        if self._web_scraper is None:
            self._web_scraper = WebScraperAgent(
                llm=self._get_llm(self._agent_models.web_scraper),
                prompt_loader=self._prompt_loader,
                search_tool=self._search_tool,
            )
        return self._web_scraper

    def create_data_formatter(self) -> AgentProtocol:
        """Return the singleton DataFormatterAgent, creating it on first call."""
        if self._data_formatter is None:
            self._data_formatter = DataFormatterAgent(
                llm=self._get_llm(self._agent_models.data_formatter),
                prompt_loader=self._prompt_loader,
            )
        return self._data_formatter

    def create_ceo(self) -> AgentProtocol:
        """Return the singleton CEOAgent, creating it on first call."""
        if self._ceo is None:
            self._ceo = CEOAgent(
                llm=self._get_llm(self._agent_models.ceo),
                prompt_loader=self._prompt_loader,
            )
        return self._ceo

    def create_cfo(self) -> AgentProtocol:
        """Return the singleton CFOAgent, creating it on first call."""
        if self._cfo is None:
            self._cfo = CFOAgent(
                llm=self._get_llm(self._agent_models.cfo),
                prompt_loader=self._prompt_loader,
            )
        return self._cfo

    def create_url_validator(self) -> AgentProtocol:
        """Return the singleton URLValidatorAgent, creating it on first call."""
        if self._url_validator is None:
            self._url_validator = URLValidatorAgent(
                llm=self._get_llm(self._agent_models.url_validator),
                prompt_loader=self._prompt_loader,
            )
        return self._url_validator

    def create_cover_letter_agent(self) -> AgentProtocol:
        """Return the singleton CoverLetterAgent, creating it on first call."""
        if self._cover_letter is None:
            self._cover_letter = CoverLetterAgent(
                llm=self._get_llm(self._agent_models.cover_letter),
                prompt_loader=self._prompt_loader,
            )
        return self._cover_letter
