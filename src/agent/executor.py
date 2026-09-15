import logging
from langchain_core.prompts import ChatPromptTemplate

from src.agent.llm import get_phase3_llm
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import ActionGeneratorTool, QuoteSelectorTool, ThemeClustererTool

logger = logging.getLogger(__name__)


class AgentExecutorWrapper:
    def __init__(self, agent, tools, verbose: bool = True, max_iterations: int = 15):
        self.agent = agent
        self.tools = tools
        self.verbose = verbose
        self.max_iterations = max_iterations

    def invoke(self, input_data: dict, config: dict | None = None):
        if hasattr(self.agent, "invoke"):
            return self.agent.invoke(input_data, config=config)
        return self.agent(input_data)


def build_agent_executor():
    """
    Factory function creating a configured LangChain agent executor
    wired with the three analysis tools: ThemeClustererTool, QuoteSelectorTool,
    and ActionGeneratorTool, powered by the Phase 3 LLM (Gemini).

    Compatible with both LangChain v0.x (AgentExecutor) and v1.x (create_agent).
    """
    llm = get_phase3_llm(temperature=0.3)
    tools = [ThemeClustererTool(), QuoteSelectorTool(), ActionGeneratorTool()]

    # Try LangChain v1.x create_agent first
    try:
        from langchain.agents import create_agent
        agent = create_agent(llm, tools=tools, system_prompt=SYSTEM_PROMPT)
        return AgentExecutorWrapper(agent=agent, tools=tools, verbose=True, max_iterations=15)
    except (ImportError, Exception):
        pass

    # Fallback: LangChain v0.x API (AgentExecutor)
    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])
        agent = create_tool_calling_agent(llm, tools, prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=15,
            handle_parsing_errors=True,
        )
    except Exception as exc:
        logger.error("Failed to build agent executor: %s", exc)
        raise
