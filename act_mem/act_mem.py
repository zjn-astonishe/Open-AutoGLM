from .workflow import WorkGraph, Workflow
from typing import List
import json
import os

class ActionMemory:
    """
    Class representing the memory structure for storing work nodes.
    
    Attributes:
        work_nodes (Dict[str, WorkNode]): A dictionary mapping node IDs to WorkNode instances.
    """
    
    def __init__(self, memory_dir: str) -> None:
        self.memory_dir = memory_dir
        self.workgraphs: List[WorkGraph] = []
        self.workflows: List[Workflow] = []

        
    def add_work_graph(self, app_name: str) -> WorkGraph:
        """
        Add a work graph to the memory.
        
        Args:
            app_name (str): The name of the app whose work graph is to be added.
        """
        tmp = WorkGraph(app_name)
        self.workgraphs.append(tmp)
        return tmp
        
    def get_work_graph(self, app_name: str) -> WorkGraph | None:
        """
        Find a work graph by app name.
        
        Args:
            app_name (str): The name of the app whose work graph is to be found.
        
        Returns:
            WorkGraph | None: The found work graph or None if not found.
        """
        for graph in self.workgraphs:
            if graph.app == app_name:
                return graph
        return None
    
    def create_workflow(self, task: str) -> Workflow:
        workflow = self.find_workflow(task)
        if workflow is None:
            workflow = Workflow(task=task)
            self.workflows.append(workflow)
        return workflow
        
    def find_workflow(self, task: str) -> Workflow:
        for workflow in self.workflows:
            if task == workflow.task:
                return workflow
        return None
    
    def print_workgraphs(self) -> None:
        """
        Print all work graphs in the memory.
        """
        if self.workgraphs is None:
            print("No work graphs in memory.")
            return
        for graph in self.workgraphs:
            print(f"WorkGraph for app: {graph.app}")
            for node_id, node in graph.nodes.items():
                print(f"  Node ID: {node_id}, Elements Info: {node.elements_info}, Tasks: {node.tasks}")
                for action in node.actions:
                    print(f"    Action: {action.action_type}, Description: {action.description}, Zone Path: {action.zone_path}")
                print(f"\n")
    
    def to_json(self) -> None:
        """
        Save all work graphs to separate JSON files by app name.
        """
        # 确保目录存在
        os.makedirs(self.memory_dir, exist_ok=True)
        
        for graph in self.workgraphs:
            graph_data = {
                "app": graph.app,
                "nodes": {},
                "workflow": []
            }
            
            # Process nodes
            for node_id, node in graph.nodes.items():
                node_data = {
                    "id": node.id,
                    "elements_info": node.elements_info,
                    "tasks": node.tasks,
                    "actions": [
                        {
                            "action_type": action.action_type,
                            "description": action.description,
                            "zone_path": action.zone_path
                        } for action in node.actions
                    ]
                }
                graph_data["nodes"][node_id] = node_data
            
            # Process workflows
            for workflow in graph.workflow:
                workflow_data = {
                    "task": workflow.task,
                    "path": workflow.path
                }
                graph_data["workflow"].append(workflow_data)
            
            # 保存为单独的文件，文件名包含应用名
            filename = f"{graph.app.replace(' ', '_').replace('/', '_')}_graph.json"
            filepath = os.path.join(self.memory_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
                
            print(f"Saved work graph for app '{graph.app}' to {filepath}")

    def from_json(self) -> None:
        """
        Load all work graphs from JSON files in the memory directory.
        """
        for filename in os.listdir(self.memory_dir):
            if filename.endswith("_graph.json"):
                filepath = os.path.join(self.memory_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    graph_data = json.load(f)
                    
                graph = WorkGraph(graph_data["app"])
                
                # Process nodes
                for node_id, node_data in graph_data["nodes"].items():
                    node = graph.create_node(node_data["elements_info"])
                    node.id = node_data["id"]
                    node.tasks = node_data["tasks"]
                    for action_data in node_data["actions"]:
                        node.add_action(
                            action_type=action_data["action_type"],
                            description=action_data["description"],
                            zone_path=action_data.get("zone_path")
                        )
