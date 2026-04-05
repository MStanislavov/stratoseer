"""Agent factory: creates singleton agents backed by LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.base import AgentProtocol
from app.agents.ceo_agent import CEOAgent
from app.agents.cfo_agent import CFOAgent
from app.agents.cover_letter_agent import CoverLetterAgent
from app.agents.data_formatter import DataFormatterAgent
from app.agents.goal_extractor import GoalExtractorAgent
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


class AgentFactory:
    """Creates stateless singleton agents backed by a ChatOpenAI LLM.

    Per-agent model overrides are applied via agent_models config.
    """

    def __init__(
        self,
        llm: Any,
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

        # Cache of ChatOpenAI instances keyed by model name
        self._llm_cache: dict[str, Any] = {}

    def _get_budget_output_tokens(self, agent_name: str) -> int | None:
        """Look up the max_output_tokens budget for an agent, or None if unavailable."""
        if self._policy_engine is None:
            return None
        try:
            budget = self._policy_engine.get_budget(agent_name)
            return budget.max_output_tokens
        except KeyError:
            return None

    def _get_llm(self, model_override: str, max_tokens: int | None = None) -> Any:
        """Return an LLM instance for the given model, or the default LLM.

        If model_override is set and differs from the base LLM's model,
        create a new Agent LLM with that model (cached).
        When max_tokens is provided, it caps the LLM's output token count.
        """
        if not model_override and max_tokens is None:
            return self._llm

        # Check if the override matches the base LLM already
        base_model = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "")
        if model_override == base_model and max_tokens is None:
            return self._llm

        cache_key = (model_override or base_model, max_tokens)
        if cache_key not in self._llm_cache:
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, Any] = {
                "model": model_override or base_model,
                "temperature": self._llm.temperature,
                "api_key": self._llm.openai_api_key,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            self._llm_cache[cache_key] = ChatOpenAI(**kwargs)
        return self._llm_cache[cache_key]

    def create_goal_extractor(self) -> AgentProtocol:
        """Return the singleton GoalExtractorAgent, creating it on first call."""
        if self._goal_extractor is None:
            self._goal_extractor = GoalExtractorAgent(
                llm=self._get_llm(
                    self._agent_models.goal_extractor,
                    max_tokens=self._get_budget_output_tokens("goal_extractor"),
                ),
                prompt_loader=self._prompt_loader,
            )
        return self._goal_extractor

    def create_web_scraper(self) -> AgentProtocol:
        """Return the singleton WebScraperAgent, creating it on first call."""
        if self._web_scraper is None:
            from app.llm.url_fetch_tool import URLFetchTool

            budget = None
            if self._policy_engine:
                try:
                    budget = self._policy_engine.get_budget("web_scrapers")
                except KeyError:
                    pass

            # Per-category budget overrides (e.g. web_scraper_job)
            category_max_steps: dict[str, int] = {}
            category_min_searches: dict[str, int] = {}
            category_min_results: dict[str, int] = {}
            if self._policy_engine:
                for cat in ("job", "cert", "course", "event", "group", "trend"):
                    try:
                        cat_budget = self._policy_engine.get_budget(f"web_scraper_{cat}")
                        category_max_steps[cat] = cat_budget.max_steps
                        if cat_budget.min_searches:
                            category_min_searches[cat] = cat_budget.min_searches
                        if cat_budget.min_results:
                            category_min_results[cat] = cat_budget.min_results
                    except KeyError:
                        pass

            self._web_scraper = WebScraperAgent(
                llm=self._get_llm(
                    self._agent_models.web_scraper,
                    max_tokens=budget.max_output_tokens if budget else None,
                ),
                prompt_loader=self._prompt_loader,
                search_tool=self._search_tool,
                fetch_tool=URLFetchTool(),
                max_steps=budget.max_steps if budget else 5,
                category_max_steps=category_max_steps or None,
                category_min_searches=category_min_searches or None,
                category_min_results=category_min_results or None,
            )
        return self._web_scraper

    def create_data_formatter(self) -> AgentProtocol:
        """Return the singleton DataFormatterAgent, creating it on first call."""
        if self._data_formatter is None:
            self._data_formatter = DataFormatterAgent(
                llm=self._get_llm(
                    self._agent_models.data_formatter,
                    max_tokens=self._get_budget_output_tokens("data_formatter"),
                ),
                prompt_loader=self._prompt_loader,
            )
        return self._data_formatter

    def create_ceo(self) -> AgentProtocol:
        """Return the singleton CEOAgent, creating it on first call."""
        if self._ceo is None:
            self._ceo = CEOAgent(
                llm=self._get_llm(
                    self._agent_models.ceo,
                    max_tokens=self._get_budget_output_tokens("ceo"),
                ),
                prompt_loader=self._prompt_loader,
            )
        return self._ceo

    def create_cfo(self) -> AgentProtocol:
        """Return the singleton CFOAgent, creating it on first call."""
        if self._cfo is None:
            self._cfo = CFOAgent(
                llm=self._get_llm(
                    self._agent_models.cfo,
                    max_tokens=self._get_budget_output_tokens("cfo"),
                ),
                prompt_loader=self._prompt_loader,
            )
        return self._cfo

    def create_cover_letter_agent(self) -> AgentProtocol:
        """Return the singleton CoverLetterAgent, creating it on first call."""
        if self._cover_letter is None:
            self._cover_letter = CoverLetterAgent(
                llm=self._get_llm(
                    self._agent_models.cover_letter,
                    max_tokens=self._get_budget_output_tokens("cover_letter_agent"),
                ),
                prompt_loader=self._prompt_loader,
            )
        return self._cover_letter
