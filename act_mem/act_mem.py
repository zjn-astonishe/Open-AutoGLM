import os
import json
import uuid
import numpy as np
from typing import List, Dict, Any
from .worknode import WorkAction, WorkNode
from .workflow import WorkGraph, Workflow, WorkTransition
from sentence_transformers import SentenceTransformer

class ActionMemory:
    """
    Class representing the memory structure for storing work nodes.
    
    Attributes:
        workgraphs (List[WorkGraph]): Current runtime work graphs.
        workflows (List[Workflow]): Current runtime workflows.
        historical_workgraphs (List[WorkGraph]): Historical work graphs loaded from JSON files.
        historical_workflows (List[Workflow]): Historical workflows loaded from JSON files.
    """
    
    def __init__(self, memory_dir: str) -> None:
        self.memory_dir = memory_dir
        
        # 当前运行时的记录
        self.workgraphs: List[WorkGraph] = []
        self.workflows: List[Workflow] = []
        
        # 从JSON加载的历史记录，与当前运行时记录分开
        self.historical_workgraphs: List[WorkGraph] = []
        self.historical_workflows: List[Workflow] = []

        
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
        Find a work graph by app name in current runtime graphs.
        
        Args:
            app_name (str): The name of the app whose work graph is to be found.
        
        Returns:
            WorkGraph | None: The found work graph or None if not found.
        """
        for graph in self.workgraphs:
            if graph.app == app_name:
                return graph
        return None
    
    def get_historical_work_graph(self, app_name: str) -> WorkGraph | None:
        """
        Find a work graph by app name in historical graphs.
        
        Args:
            app_name (str): The name of the app whose work graph is to be found.
        
        Returns:
            WorkGraph | None: The found work graph or None if not found.
        """
        for graph in self.historical_workgraphs:
            if graph.app == app_name:
                return graph
        return None
    
    def create_workflow(self, task: str) -> Workflow:
        id = str(uuid.uuid4())
        workflow = Workflow(id=id, task=task)
        self.workflows.append(workflow)
        return workflow
        
    def find_workflow(self, task: str) -> List[Workflow]:
        """
        Find workflows by task in current runtime workflows.
        
        Args:
            task (str): The task to search for.
        
        Returns:
            List[Workflow]: List of matching workflows.
        """
        workflows = []
        for workflow in self.workflows:
            if task == workflow.task:
                workflows.append(workflow)
        return workflows
    
    def find_historical_workflow(self, task: str) -> List[Workflow]:
        """
        Find workflows by task in historical workflows.
        
        Args:
            task (str): The task to search for.
        
        Returns:
            List[Workflow]: List of matching historical workflows.
        """
        workflows = []
        for workflow in self.historical_workflows:
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
    
    def _calculate_cosine_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1 (np.ndarray): First embedding vector
            embedding2 (np.ndarray): Second embedding vector
            
        Returns:
            float: Cosine similarity score between -1 and 1
        """
        try:
            # 确保embedding是一维数组
            embedding1 = np.array(embedding1).flatten()
            embedding2 = np.array(embedding2).flatten()
            
            # 检查形状是否匹配
            if embedding1.shape != embedding2.shape:
                print(f"Warning: Embedding shapes don't match after flattening: {embedding1.shape} vs {embedding2.shape}")
                return 0.0
            
            # 计算余弦相似度
            similarity = np.dot(embedding1, embedding2) / (
                np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
            )
            return float(similarity)
        except Exception as e:
            print(f"Warning: Error calculating cosine similarity: {str(e)}")
            return 0.0
    
    def from_json(
            self, 
            task: str,
            target_tag: str | None = None,
            similarity_threshold: float = 0.5,
            tag_similarity_threshold: float = 0.8,
        ) -> None:
        """
        Load work graphs and workflows from JSON files into historical memory, filtered by target apps/tasks.
        First filters by target_tag, then by task embedding similarity.
        
        Note: This method loads data into historical_workgraphs and historical_workflows,
        keeping them separate from current runtime records to avoid confusion.
        
        Args:
            task (str): The task description to match against
            target_tag (str | None): Optional tag to filter by first
            similarity_threshold (float): Minimum cosine similarity threshold for task embedding matching (default: 0.7)
            tag_similarity_threshold (float): Minimum cosine similarity threshold for tag matching when target_tag is provided (default: 0.8)
        """
        
        # 计算输入task的embedding用于相似度比较
        model = SentenceTransformer('./model/sentence-transformers/all-MiniLM-L6-v2')
        task_embedding = model.encode(task)
        
        # 如果提供了target_tag，也计算其embedding用于tag相似度匹配
        target_tag_embedding = None
        if target_tag:
            target_tag_embedding = model.encode(target_tag)
        
        # 确保目录存在
        graph_dir = os.path.join(self.memory_dir, "graph")
        workflow_dir = os.path.join(self.memory_dir, "workflow")
        
        # 收集需要加载的节点ID
        required_node_ids = set()
        
        # 第一步：加载和筛选工作流
        if os.path.exists(workflow_dir):
            for filename in os.listdir(workflow_dir):
                if filename.endswith(".json"):
                    # 从文件名提取tag
                    filepath = os.path.join(workflow_dir, filename)
                    tag = os.path.splitext(filename)[0]
                    tag = tag.replace('_', '.')
                    
                    # 如果指定了target_tag，进行tag匹配（支持精确匹配和语义相似度匹配）
                    if target_tag:
                        tag_matches = False
                        
                        # 首先尝试精确匹配
                        if tag == target_tag:
                            tag_matches = True
                            # print(f"Tag exact match: {tag}")
                        
                        # 如果精确匹配失败，尝试语义相似度匹配
                        elif target_tag_embedding is not None:
                            try:
                                tag_embedding = model.encode(tag)
                                tag_similarity = self._calculate_cosine_similarity(target_tag_embedding, tag_embedding)
                                
                                if tag_similarity >= tag_similarity_threshold:
                                    tag_matches = True
                                    # print(f"Tag semantic match: {tag} (similarity: {tag_similarity:.3f})")
                                else:
                                    print(f"Tag similarity too low: {tag} (similarity: {tag_similarity:.3f})")

                            except Exception as e:
                                print(f"Warning: Error calculating tag similarity for {tag}: {str(e)}")
                        
                        # 如果tag不匹配，跳过此文件
                        if not tag_matches:
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

                        # 检查 ID 是否已存在于历史记录中（避免重复加载）
                        existing_workflow = next((w for w in self.historical_workflows if w.id == workflow_data.get("id")), None)
                        if existing_workflow:
                            print(f"Historical workflow with id {workflow_data.get('id')} already exists, skipping load from {filepath}.")
                            continue

                        # 校验必要字段（id/task 不能为空）
                        if not workflow_data.get("id") or not workflow_data.get("task"):
                            print(f"Warning: Workflow in {filepath} missing id/task, skipping.")
                            continue

                        # 基于task embedding进行相似度筛选
                        if "task_embedding" in workflow_data:
                            try:
                                # 从JSON中加载保存的embedding
                                saved_embedding = np.array(workflow_data["task_embedding"])
                                
                                # 计算余弦相似度
                                similarity = self._calculate_cosine_similarity(task_embedding, saved_embedding)
                                
                                # 如果相似度低于阈值，跳过此workflow
                                if similarity < similarity_threshold:
                                    print(f"Workflow task '{workflow_data['task']}' similarity {similarity:.3f} below threshold {similarity_threshold}, skipping.")
                                    continue
                                else:
                                    print(f"Workflow task '{workflow_data['task']}' similarity {similarity:.3f} above threshold, loading.")
                                    
                            except Exception as e:
                                print(f"Warning: Error calculating similarity for workflow in {filepath}: {str(e)}, loading anyway.")

                        # 创建 Workflow 实例
                        workflow = Workflow(
                            id=workflow_data["id"],
                            task=workflow_data["task"]
                        )

                        # 设置标签，使用从文件名提取并恢复的tag
                        workflow.tag = tag
                        
                        # 如果有保存的embedding，直接使用，否则重新计算
                        if "task_embedding" in workflow_data:
                            try:
                                workflow.task_embedding = np.array(workflow_data["task_embedding"])
                            except:
                                # 如果加载失败，重新计算
                                workflow.task_embedding = model.encode(workflow.task)
                        else:
                            # 如果没有保存的embedding，重新计算
                            workflow.task_embedding = model.encode(workflow.task)

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
                                    zone_path=action_data.get("zone_path"),  # 不存在则为 None
                                    reflection_result=action_data.get("reflection_result"),
                                    confidence_score=action_data.get("confidence_score"),
                                    direction=action_data.get("direction"),
                                    distance=action_data.get("distance"),
                                    text=action_data.get("text")
                                )
                                # 创建 WorkTransition 实例
                                transition = WorkTransition(
                                    from_node_id=transition_data.get("from_node_id", ""),
                                    to_node_id=transition_data.get("to_node_id", ""),
                                    action=action,
                                    success=transition_data.get("success", True)  # 默认为 True
                                )
                                workflow.path.append(transition)

                        # 收集workflow中涉及的节点ID
                        for transition in workflow.path:
                            if transition.from_node_id:
                                required_node_ids.add(transition.from_node_id)
                            if transition.to_node_id:
                                required_node_ids.add(transition.to_node_id)

                        # 将合法的 Workflow 添加到历史记录内存
                        self.historical_workflows.append(workflow)
                        print(f"Loaded historical workflow (id: {workflow.id}) for task '{workflow.task}' from {filepath}")

        # 第二步：根据workflow中的节点ID加载相关的workgraph节点
        if required_node_ids and os.path.exists(graph_dir):
            print(f"Loading nodes for {len(required_node_ids)} required node IDs: {list(required_node_ids)[:5]}{'...' if len(required_node_ids) > 5 else ''}")
            
            for filename in os.listdir(graph_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(graph_dir, filename)
                    
                    with open(filepath, 'r', encoding='utf-8') as f:
                        graph_data = json.load(f)
                    
                    # 检查是否已存在同名app的历史graph
                    existing_graph = self.get_historical_work_graph(graph_data["app"])
                    if existing_graph:
                        # 如果历史graph已存在，检查是否需要加载新的节点
                        graph = existing_graph
                        print(f"Historical work graph for app '{graph_data['app']}' already exists, checking for new nodes.")
                    else:
                        # 创建新的WorkGraph实例并添加到历史记录
                        graph = WorkGraph(app=graph_data["app"])
                        self.historical_workgraphs.append(graph)
                    
                    nodes_loaded = 0
                    
                    # 只加载required_node_ids中包含的节点
                    for node_id, node_data in graph_data["nodes"].items():
                        # 只加载workflow中需要的节点
                        if node_id not in required_node_ids:
                            continue
                        
                        # 检查节点是否已经存在于graph中
                        if node_id in graph.nodes:
                            print(f"Node {node_id} already exists in graph for app '{graph_data['app']}', skipping.")
                            continue

                        # 检查标签是否匹配（如果指定了target_tag）
                        if target_tag:
                            node_tag = node_data.get("tag")
                            node_tag_matches = False
                            
                            # 处理节点标签（现在是单个字符串或None）
                            if node_tag:
                                # 首先尝试精确匹配
                                if node_tag == target_tag:
                                    node_tag_matches = True
                                # 如果精确匹配失败，尝试语义相似度匹配
                                elif target_tag_embedding is not None:
                                    try:
                                        node_tag_embedding = model.encode(node_tag)
                                        tag_similarity = self._calculate_cosine_similarity(target_tag_embedding, node_tag_embedding)
                                        if tag_similarity >= tag_similarity_threshold:
                                            node_tag_matches = True
                                    except Exception:
                                        pass
                            
                            # 如果节点tag不匹配，跳过此节点
                            if not node_tag_matches:
                                print(f"Node {node_id} tag '{node_tag}' does not match target tag '{target_tag}', skipping.")
                                continue

                        # 创建WorkNode实例
                        node = WorkNode(
                            id=node_data["id"],
                            elements_info=node_data["elements_info"]
                        )
                        
                        # 设置节点的任务列表
                        node.tasks = node_data["tasks"] if "tasks" in node_data else []
                        
                        # 设置节点的标签（单个字符串）
                        node.tag = node_data.get("tag")
                        
                        # 设置节点的动作列表
                        if "actions" in node_data:
                            for action_data in node_data["actions"]:
                                action = WorkAction(
                                    action_type=action_data["action_type"],
                                    description=action_data["description"],
                                    zone_path=action_data.get("zone_path"),  # 使用get方法，如果不存在则为None
                                    reflection_result=action_data.get("reflection_result"),
                                    confidence_score=action_data.get("confidence_score"),
                                    direction=action_data.get("direction"),
                                    distance=action_data.get("distance"),
                                    text=action_data.get("text")
                                )
                                node.actions.append(action)
                        
                        # 将节点添加到图中
                        graph.nodes[node.id] = node
                        nodes_loaded += 1
                    
                    # 只有当加载了新节点时才打印消息
                    if nodes_loaded > 0:
                        if existing_graph:
                            print(f"Added {nodes_loaded} new nodes to existing historical work graph for app '{graph_data['app']}' from {filepath}")
                        else:
                            print(f"Loaded historical work graph for app '{graph_data['app']}' with {nodes_loaded} nodes from {filepath}")
