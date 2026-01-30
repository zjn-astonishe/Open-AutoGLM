import uuid
from typing import Dict, List, Any
from dataclasses import dataclass
from .worknode import WorkNode, WorkAction
from sentence_transformers import SentenceTransformer
import numpy as np

@dataclass
class WorkTransition:
    from_node_id: str
    action: WorkAction
    to_node_id: str
    success: bool=True

class Workflow:

    """
    Data structure representing a workflow, which is a sequence of WorkNodes.

    This class encapsulates all information about a workflow:
    - A list of WorkNodes.
    - A mapping from node IDs to WorkNodes.

    Attributes:
        task (str): Task description.
        path (List[str]): Sequence of node IDs representing the transition order.
    """

    def __init__(self, id: str, task: str) -> None:
        self.id: str = id
        self.task = task
        model = SentenceTransformer('./model/sentence-transformers/all-MiniLM-L6-v2')
        self.task_embedding = model.encode(task)
        self.tag: str = ""
        self.tag_embedding = None  # 初始化为None，而不是空列表
        self.path: List[WorkTransition] = []   # sequence of node IDs representing the transition order.
        self.step = 0
        self.timecost = 0

    def add_transition(self, from_node_id: str, to_node_id: str, action: WorkAction, success: bool=True):
        if self.get_start_id() == None or from_node_id == self.get_last_id():
            self.path.append(WorkTransition(from_node_id=from_node_id, to_node_id=to_node_id, action=action, success=success))
        else:
            print(f"Transition from {from_node_id} to {to_node_id} does not match this workflow. The workflow start id is {self.get_start_id()}, last id is {self.get_last_id()}")
            for transition in self.path:
                print(f"{transition}")
            raise ValueError("This transition does not match this workflow.")

    def get_start_id(self) -> str | None:
        return self.path[0].from_node_id if self.path else None
    
    def get_last_id(self) -> str | None:
        return self.path[-1].to_node_id if self.path else None
    
    def set_step(self, step: int) -> None:
        self.step = step
    
    def set_timecost(self, timecost: float) -> None:
        self.timecost = timecost

    def set_tag(self, tag: str) -> None:
        self.tag = tag
        model = SentenceTransformer('./model/sentence-transformers/all-MiniLM-L6-v2')
        self.tag_embedding = model.encode(tag)

    def to_json(self) -> Dict[str, Any]:
        workflow_data = {
            "id": self.id,
            "tag": self.tag,
            "tag_embedding": self.tag_embedding.tolist() if self.tag_embedding is not None else [],  # 添加检查
            "task": self.task,
            "task_embedding": self.task_embedding.tolist(),
            "step": self.step,
            "timecost": self.timecost,
            "path": []
        }
        for transition in self.path:
            workflow_data["path"].append({
                "from_node_id": transition.from_node_id,
                "to_node_id": transition.to_node_id,
                "action": {
                    "action_type": transition.action.action_type,
                    "description": transition.action.description,
                    "zone_path": transition.action.zone_path,
                    "direction": transition.action.direction,
                    "distance": transition.action.distance,
                    "text": transition.action.text
                },
                "success": transition.success
            })
        return workflow_data

class WorkGraph:

    """
    Data structure representing a graph of WorkNodes.

    This class encapsulates all information about a graph of WorkNodes:
    - A name for the app. Each app has a unique WorkGraph. 
    - A list of WorkNodes.
    - A mapping from node IDs to WorkNodes.

    Attributes:
        app (str): Name of the app.
        nodes (Dict[str, WorkNode]): Mapping from node IDs to WorkNodes.
    """

    def __init__(self, app: str):
        self.app = app
        self.nodes: Dict[str, WorkNode] = {}    # id -> WorkNode
        
    def create_node(self, elements_info: List[Dict[str, str]]) -> WorkNode:
        for node in self.nodes.values():
            if node.elements_info == elements_info:
                return node
        node_id = str(uuid.uuid4())
        node = WorkNode(id=node_id, elements_info=elements_info)
        # print(f"Node id {node_id} created, {node.id}")
        self.nodes[node_id] = node
        return node
        
    def get_node_by_id(self, node_id: str) -> WorkNode | None:
        return self.nodes.get(node_id)
    
    def get_id_by_node(self, node: WorkNode) -> str | None:
        for id, n in self.nodes.items():
            if n == node:
                return id
        return None
    
    def add_task(self, node_id: str, task: str) -> None:
        node = self.get_node_by_id(node_id)
        if node:
            node.add_task(task)
        else:
            raise ValueError(f"Node {node_id} not found in graph")
    
    def add_action(self, from_node_id: str, action: WorkAction) -> None:
        node = self.get_node_by_id(from_node_id)
        if node:
            node.add_action(action)
        else:
            raise ValueError(f"Node {from_node_id} not found in graph")
    
    def to_json(self) -> Dict[str, Any]:
        graph_data = {
            "app": self.app,
            "nodes": {}
        }
        for node_id, node in self.nodes.items():
            graph_data["nodes"][node_id] = node.to_json()

        return graph_data

    def is_empty(self) -> bool:
        return len(self.nodes) == 0