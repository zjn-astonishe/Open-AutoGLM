import os
import json
import uuid
from typing import List, Dict, Any
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
        Save work graphs and workflows to JSON files, merging with existing data if files exist.
        - Work graphs: Merge nodes (update existing nodes by ID, add new nodes)
        - Workflows: Merge paths (append new paths, deduplicate by from/to node IDs)
        """
        self._ensure_directories()
        self._save_work_graphs()
        self._save_workflows()
    
    def _ensure_directories(self) -> None:
        """Ensure necessary directories exist."""
        os.makedirs(self.memory_dir, exist_ok=True)
        graph_dir = os.path.join(self.memory_dir, "graph")
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        os.makedirs(graph_dir, exist_ok=True)
        os.makedirs(workflow_dir, exist_ok=True)
    
    def _save_work_graphs(self) -> None:
        """Save work graphs to JSON files."""
        graph_dir = os.path.join(self.memory_dir, "graph")
        
        for graph in self.workgraphs:
            graph_data = graph.to_json()
            app_name = graph.app
            filename = f"{app_name.replace(' ', '_').replace('/', '_')}.json"
            filepath = os.path.join(graph_dir, filename)
            
            existing_data = self._load_existing_graph_data(filepath, app_name)
            merged_nodes = {**existing_data["nodes"], **graph_data["nodes"]}
            merged_graph_data = {
                "app": app_name,
                "nodes": merged_nodes
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(merged_graph_data, f, ensure_ascii=False, indent=2)
                
            print(f"Saved work graph for app '{graph.app}' to {filepath}")
    
    def _load_existing_graph_data(self, filepath: str, app_name: str) -> Dict[str, Any]:
        """Load existing graph data from file, with error handling."""
        existing_data = {"app": app_name, "nodes": {}}
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                if existing_data.get("app") != app_name:
                    print(f"Warning: Mismatched app in {filepath}, will reset.")
                    existing_data = {"app": app_name, "nodes": {}}
            except (json.JSONDecodeError, KeyError):
                print(f"Warning: Corrupted file {filepath}, will reset.")
                existing_data = {"app": app_name, "nodes": {}}
        
        return existing_data
    
    def _save_workflows(self) -> None:
        """Save workflows to JSON files."""
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        
        for workflow in self.workflows:
            workflow_data = workflow.to_json()
            tag = workflow.tag
            
            task_filename = f"{tag.replace('.', '_').strip()}.json"
            task_filepath = os.path.join(workflow_dir, task_filename)

            existing_workflows = self._load_existing_workflows(task_filepath)
            
            if self._workflow_already_exists(workflow, existing_workflows, task_filepath):
                continue

            existing_workflows.append(workflow_data)
            with open(task_filepath, 'w', encoding='utf-8') as f:
                json.dump(existing_workflows, f, ensure_ascii=False, indent=2)
                
            print(f"Saved workflow for task '{workflow.task}' to {task_filepath}")
    
    def _load_existing_workflows(self, filepath: str) -> list:
        """Load existing workflows from file, with error handling."""
        existing_workflows = []
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing_workflows = json.load(f)
                if not isinstance(existing_workflows, list):
                    print(f"Warning: Invalid workflow file format in {filepath}, resetting.")
                    existing_workflows = []
            except json.JSONDecodeError:
                print(f"Warning: Corrupted workflow file {filepath}, resetting.")
                existing_workflows = []
        
        return existing_workflows
    
    def _workflow_already_exists(self, workflow: Workflow, existing_workflows: list, filepath: str) -> bool:
        """Check if workflow already exists in the file."""
        workflow_ids = [wf.get("id") for wf in existing_workflows if isinstance(wf, dict) and "id" in wf]
        if workflow.id in workflow_ids:
            print(f"Workflow (id: {workflow.id}) already exists in {filepath}, skipping.")
            return True
        
        # workflow_tasks = [wf.get("task") for wf in existing_workflows if isinstance(wf, dict) and "task" in wf]
        # if workflow.task in workflow_tasks:
        #     print(f"Workflow (task: {workflow.task}) already exists in {filepath}, skipping.")
        #     return True
        
        return False
    
    def from_json(
            self, 
            target_tag: str | None = None
        ) -> None:
        """
        Load work graphs and workflows from JSON files, filtered by target apps/tasks.
        """
        
        # 确保目录存在
        graph_dir = os.path.join(self.memory_dir, "graph")
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        
        # 加载工作图
        if os.path.exists(graph_dir):
            for filename in os.listdir(graph_dir):
                if filename.endswith(".json"):
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

                        if target_tag and node_data["tag"] != target_tag:  # 检查标签是否匹配
                            continue

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
                                    zone_path=action_data.get("zone_path"),  # 使用get方法，如果不存在则为None
                                    reflection_result=action_data.get("reflection_result"),
                                    confidence_score=action_data.get("confidence_score")
                                )
                                node.actions.append(action)
                        
                        # 将节点添加到图中
                        graph.nodes[node.id] = node
                    
                    # 将图添加到内存中
                    if not graph.is_empty():
                        self.workgraphs.append(graph)
                        print(f"Loaded work graph for app '{graph_data['app']}' from {filepath}")
        
        # 加载工作流
        if os.path.exists(workflow_dir):
            for filename in os.listdir(workflow_dir):
                if filename.endswith(".json"):
                    # 从文件名提取tag
                    filepath = os.path.join(workflow_dir, filename)
                    tag = os.path.splitext(filename)[0]
                    tag = tag.replace('_', '.')
                    
                    # 如果指定了target_tag且当前tag不匹配，则跳过
                    if target_tag and tag != target_tag:
                        continue
                    
                    file_workflows = []
                    try:
                        # 读取文件并校验格式（必须是列表）
                        with open(filepath, 'r', encoding='utf-8') as f:
                            file_workflows = json.load(f)
                        if not isinstance(file_workflows, list):
                            print(f"Warning: {filepath} is not a valid workflow list (not a JSON array), skipping.")
                            continue
                    except json.JSONDecodeError:
                        print(f"Warning: Corrupted JSON file {filepath}, skipping load.")
                        continue
                    except Exception as e:
                        print(f"Error loading {filepath}: {str(e)}, skipping.")
                        continue

                    # 遍历文件内的每个 Workflow 实例（核心修正：遍历数组）
                    for workflow_data in file_workflows:
                        # 跳过非字典格式的无效数据
                        if not isinstance(workflow_data, dict):
                            print(f"Warning: Invalid workflow data in {filepath} (not a dict), skipping.")
                            continue

                        # 检查 ID 是否已存在（避免重复加载）
                        existing_workflow = next((w for w in self.workflows if w.id == workflow_data.get("id")), None)
                        if existing_workflow:
                            print(f"Workflow with id {workflow_data.get('id')} already exists, skipping load from {filepath}.")
                            continue

                        # 校验必要字段（id/task 不能为空）
                        if not workflow_data.get("id") or not workflow_data.get("task"):
                            print(f"Warning: Workflow in {filepath} missing id/task, skipping.")
                            continue

                        # 创建 Workflow 实例
                        workflow = Workflow(
                            id=workflow_data["id"],
                            task=workflow_data["task"]
                        )

                        # 设置标签，使用从文件名提取并恢复的tag
                        workflow.tag = tag

                        # 加载路径（path 字段，可选）
                        if "path" in workflow_data and isinstance(workflow_data["path"], list):
                            for transition_data in workflow_data["path"]:
                                # 校验 transition 数据格式
                                if not isinstance(transition_data, dict) or "action" not in transition_data:
                                    print(f"Warning: Invalid transition data in {filepath}, skipping this transition.")
                                    continue
                                action_data = transition_data["action"]
                                # 创建 WorkAction 实例（容错：字段缺失用 get）
                                action = WorkAction(
                                    action_type=action_data.get("action_type", ""),
                                    description=action_data.get("description", ""),
                                    zone_path=action_data.get("zone_path")  # 不存在则为 None
                                )
                                # 创建 WorkTransition 实例
                                transition = WorkTransition(
                                    from_node_id=transition_data.get("from_node_id", ""),
                                    to_node_id=transition_data.get("to_node_id", ""),
                                    action=action,
                                    success=transition_data.get("success", True)  # 默认为 True
                                )
                                workflow.path.append(transition)

                        # 将合法的 Workflow 添加到内存
                        self.workflows.append(workflow)
                        print(f"Loaded workflow (id: {workflow.id}) for task '{workflow.task}' from {filepath}")
