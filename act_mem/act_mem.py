from .workflow import WorkGraph, Workflow, WorkTransition
from .worknode import WorkAction
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
        # 检查是否已存在同名app的graph，如果存在则返回已有的graph而不是创建新的
        existing_graph = self.get_work_graph(app_name)
        if existing_graph:
            return existing_graph
        
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
                print(f"Found existing workflow for task: {task}")
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
        
        # Print workflows
        if self.workflows:
            print("Workflows:")
            for workflow in self.workflows:
                print(f"  Task: {workflow.task}")
                for transition in workflow.path:
                    print(f"    Transition from {transition.from_node_id} to {transition.to_node_id}")
                    print(f"      Action: {transition.action.action_type}, Description: {transition.action.description}, Zone Path: {transition.action.zone_path}")
                print(f"\n")
    
    def to_json(self) -> None:
        """
        Save all work graphs to separate JSON files by app name.
        Also save workflows separately by task.
        """
        # 确保目录存在
        os.makedirs(self.memory_dir, exist_ok=True)
        
        # Save work graphs by app name
        for graph in self.workgraphs:
            graph_data = {
                "app": graph.app,
                "nodes": {},
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
            
            # 保存为单独的文件，文件名包含应用名
            filename = f"{graph.app.replace(' ', '_').replace('/', '_')}_graph.json"
            filepath = os.path.join(self.memory_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
                
            print(f"Saved work graph for app '{graph.app}' to {filepath}")

        # Save workflows separately by task
        for workflow in self.workflows:
            workflow_data = {
                "task": workflow.task,
                "path": []
            }
            
            for transition in workflow.path:
                transition_data = {
                    "from_node_id": transition.from_node_id,
                    "to_node_id": transition.to_node_id,
                    "action": {
                        "action_type": transition.action.action_type,
                        "description": transition.action.description,
                        "zone_path": transition.action.zone_path
                    },
                    "success": transition.success
                }
                workflow_data["path"].append(transition_data)
            
            # 保存为单独的文件，文件名包含任务描述
            task_filename = f"{workflow.tag.replace('.', '_').strip()}.json"
            task_filepath = os.path.join(self.memory_dir, "workflow", task_filename)
            
            with open(task_filepath, 'w', encoding='utf-8') as f:
                json.dump(workflow_data, f, ensure_ascii=False, indent=2)
                
            print(f"Saved workflow for task '{workflow.task}' to {task_filepath}")
    
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
                
                # 将加载的graph添加到当前实例的workgraphs列表中
                self.workgraphs.append(graph)

        # 加载工作流文件
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        if os.path.exists(workflow_dir):
            for filename in os.listdir(workflow_dir):
                filepath = os.path.join(workflow_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    workflow_data = json.load(f)
                    
                # 检查是否已存在相同task的workflow
                existing_workflow = self.find_workflow(workflow_data["task"])
                if existing_workflow:
                    # 如果存在，将加载的路径添加到现有workflow中
                    for transition_data in workflow_data["path"]:
                        action_data = transition_data["action"]
                        action = WorkAction(
                            action_type=action_data["action_type"],
                            description=action_data["description"],
                            zone_path=action_data.get("zone_path")
                        )
                        
                        existing_workflow.path.append(WorkTransition(
                            from_node_id=transition_data["from_node_id"],
                            to_node_id=transition_data["to_node_id"],
                            action=action,
                            success=transition_data.get("success", True)
                        ))
                else:
                    # 如果不存在，创建新的workflow
                    workflow = Workflow(workflow_data["task"])
                    
                    for transition_data in workflow_data["path"]:
                        action_data = transition_data["action"]
                        action = WorkAction(
                            action_type=action_data["action_type"],
                            description=action_data["description"],
                            zone_path=action_data.get("zone_path")
                        )
                        
                        workflow.path.append(WorkTransition(
                            from_node_id=transition_data["from_node_id"],
                            to_node_id=transition_data["to_node_id"],
                            action=action,
                            success=transition_data.get("success", True)
                        ))
                    
                    # 将新创建的workflow添加到当前实例的workflows列表中
                    self.workflows.append(workflow)
