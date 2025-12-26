import os
import json
import uuid
from typing import List
from .worknode import WorkAction, WorkNode
from .workflow import WorkGraph, Workflow, WorkTransition

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
        id = str(uuid.uuid4())
        workflow = Workflow(id=id, task=task)
        self.workflows.append(workflow)
        return workflow
        
    def find_workflow(self, task: str) -> List[Workflow]:
        workflows = []
        for workflow in self.workflows:
            if task == workflow.task:
                workflows.append(workflow)
        return workflows
    
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
            filepath = os.path.join(self.memory_dir, "graph", filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
                
            print(f"Saved work graph for app '{graph.app}' to {filepath}")

        # Save workflows separately by task
        for workflow in self.workflows:
            workflow_data = {
                "id": workflow.id,
                "tag": workflow.tag,
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
        
        # 确保目录存在
        graph_dir = os.path.join(self.memory_dir, "graph")
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        
        # 加载工作图
        if os.path.exists(graph_dir):
            for filename in os.listdir(graph_dir):
                if filename.endswith("_graph.json"):
                    filepath = os.path.join(graph_dir, filename)
                    
                    with open(filepath, 'r', encoding='utf-8') as f:
                        graph_data = json.load(f)
                    
                    # 检查是否已存在同名app的graph，如果存在则跳过加载
                    existing_graph = self.get_work_graph(graph_data["app"])
                    if existing_graph:
                        print(f"Work graph for app '{graph_data['app']}' already exists, skipping load.")
                        continue
                    
                    # 创建新的WorkGraph实例
                    graph = WorkGraph(app=graph_data["app"])
                    
                    # 加载节点
                    for node_id, node_data in graph_data["nodes"].items():
                        # 创建WorkNode实例
                        node = WorkNode(
                            id=node_data["id"],
                            elements_info=node_data["elements_info"]
                        )
                        
                        # 设置节点的任务列表
                        node.tasks = node_data["tasks"] if "tasks" in node_data else []
                        
                        # 设置节点的动作列表
                        if "actions" in node_data:
                            for action_data in node_data["actions"]:
                                action = WorkAction(
                                    action_type=action_data["action_type"],
                                    description=action_data["description"],
                                    zone_path=action_data.get("zone_path")  # 使用get方法，如果不存在则为None
                                )
                                node.actions.append(action)
                        
                        # 将节点添加到图中
                        graph.nodes[node.id] = node
                    
                    # 将图添加到内存中
                    self.workgraphs.append(graph)
                    print(f"Loaded work graph for app '{graph_data['app']}' from {filepath}")
        
        # 加载工作流
        if os.path.exists(workflow_dir):
            for filename in os.listdir(workflow_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(workflow_dir, filename)
                    
                    with open(filepath, 'r', encoding='utf-8') as f:
                        workflow_data = json.load(f)
                    
                    # 创建新的Workflow实例
                    workflow = Workflow(
                        id=workflow_data["id"],
                        task=workflow_data["task"]
                    )
                    
                    # 设置工作流的标签
                    if "tag" in workflow_data:
                        workflow.tag = workflow_data["tag"]
                    
                    # 加载路径
                    if "path" in workflow_data:
                        for transition_data in workflow_data["path"]:
                            action_data = transition_data["action"]
                            action = WorkAction(
                                action_type=action_data["action_type"],
                                description=action_data["description"],
                                zone_path=action_data.get("zone_path")  # 使用get方法，如果不存在则为None
                            )
                            
                            transition = WorkTransition(
                                from_node_id=transition_data["from_node_id"],
                                to_node_id=transition_data["to_node_id"],
                                action=action,
                                success=transition_data.get("success", True)  # 默认为True
                            )
                            
                            workflow.path.append(transition)
                    
                    # 将工作流添加到内存中
                    self.workflows.append(workflow)
                    print(f"Loaded workflow for task '{workflow_data['task']}' from {filepath}")
