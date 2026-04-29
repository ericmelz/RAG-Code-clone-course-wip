from dataclasses import dataclass
from langgraph.graph import END, StateGraph, START

from app.chat.agents.quality_control_agent.nodes.retrieval import retriever
from app.chat.agents.quality_control_agent.nodes.generation import generator
from app.chat.agents.quality_control_agent.nodes.assessor import assessor
from app.chat.agents.quality_control_agent.nodes.conflict_handler import conflict_handler
from app.chat.agents.quality_control_agent.state import QCChatAgentState


@dataclass(frozen=True)
class Nodes:
    RETRIEVER = "qc_retriever"
    GENERATOR = "qc_generator"
    ASSESSOR = "qc_assessor"
    CONFLICT_HANDLER = "qc_conflict_handler"


def _route_after_assessment(state: QCChatAgentState) -> str:
    return "conflict" if state.has_contradiction else "end"


builder = StateGraph(QCChatAgentState)
builder.add_node(Nodes.RETRIEVER, retriever)
builder.add_node(Nodes.GENERATOR, generator)
builder.add_node(Nodes.ASSESSOR, assessor)
builder.add_node(Nodes.CONFLICT_HANDLER, conflict_handler)

builder.add_edge(START, Nodes.RETRIEVER)
builder.add_edge(Nodes.RETRIEVER, Nodes.GENERATOR)
builder.add_edge(Nodes.GENERATOR, Nodes.ASSESSOR)
builder.add_conditional_edges(
    Nodes.ASSESSOR,
    _route_after_assessment,
    {"conflict": Nodes.CONFLICT_HANDLER, "end": END},
)
builder.add_edge(Nodes.CONFLICT_HANDLER, END)

qc_chat_agent = builder.compile()
