"""Speculative executor for predicting future UI states and actions."""

import ast
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer

from phone_agent.device_factory import get_device_factory
from phone_agent.context_manager import StructuredContext
from phone_agent.actions.handler import ActionHandler

from act_mem.act_mem import ActionMemory
from act_mem.workflow import Workflow, WorkGraph
from act_mem.worknode import WorkNode, WorkAction
from act_mem.workrecorder import WorkflowRecorder



@dataclass
class SpeculativeNode:
    """Represents a speculative future node with its UI XML."""
    
    node_id: str
    elements_info: List[Dict[str, Any]]
    source_workflow: str
    transition_action: Optional[WorkAction] = None


class SpeculativeExecutor:
    """
    Executor for speculative prediction of future UI states and actions.
    
    This class analyzes loaded workflows to predict possible future UI states
    and includes them in the prompt to help the model make better decisions
    by considering potential next steps.
    """
    
    def __init__(
            self, 
            memory: ActionMemory, 
            device_id: str,
            context: StructuredContext,
            confirmation_callback: Callable[[str], bool] | None = None,
            takeover_callback: Callable[[str], None] | None = None,
        ) -> None:
        """
        Initialize the speculative executor.
        
        Args:
            memory: ActionMemory instance containing loaded workflows and workgraphs
        """
        self._memory = memory
        self._context = context
        self.device_id = device_id
        self._future_nodes = []
        self.max_speculative_nodes = 2  # Maximum number of future nodes to predict
        self._elements_match_threshold = 0.7  # Similarity threshold for matching UI elements
        self.action_handler = ActionHandler(
            device_id=device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )
    def get_speculative_context(
        self, 
        current_app: str, 
        current_elements: List[Dict[str, Any]], 
        task: str
    ) -> Optional[str]:
        """
        Generate speculative context by predicting future UI states.
        
        Args:
            current_app: Current application name
            current_elements: Current UI elements
            task: Current task description
            
        Returns:
            Formatted string containing speculative UI context, or None if no predictions
        """
        # Find relevant workflows for the current app and task
        relevant_workflows = self._find_relevant_workflows(current_app)
        print(f"Found {len(relevant_workflows)} relevant workflows for app '{current_app}' and task '{task}'")
        if not relevant_workflows:
            return None
        
        # Find current position in workflows
        current_node_matches = self._find_current_node_matches(current_elements, relevant_workflows)
        
        if not current_node_matches:
            return None
        
        # Predict future nodes
        # print("Predicting future UI states based on current matches...")
        self._future_nodes = self._predict_future_nodes(current_node_matches)
        
        if not self._future_nodes:
            return None
        
        # Format speculative context
        return self._format_speculative_context(self._future_nodes)
    
    def _find_relevant_workflows(self, current_app: str) -> List[Workflow]:
        """Find workflows relevant to the current app and task."""
        relevant_workflows = []
        
        for workflow in self._memory.historical_workflows:
            # Check if workflow is for the same app (by checking if any nodes belong to this app)
            workflow_apps = set()
            for transition in workflow.path:
                # Find the workgraph that contains this node
                for workgraph in self._memory.historical_workgraphs:
                    if transition.from_node_id in workgraph.nodes.keys():
                        workflow_apps.add(workgraph.app)
                        break
            
            if current_app in workflow_apps:
                relevant_workflows.append(workflow)
        
        return relevant_workflows
    
    def _find_current_node_matches(
        self, 
        current_elements: List[Dict[str, Any]], 
        workflows: List[Workflow]
    ) -> List[Tuple[WorkNode, Workflow, int]]:
        """
        Find nodes in workflows that match the current UI state.
        Returns only the highest similarity match.
        
        Returns:
            List containing at most one tuple (matching_node, workflow, position_in_workflow)
        """
        all_matches = []
        
        for workflow in workflows:
            for i, transition in enumerate(workflow.path):
                # Find the node in workgraphs
                node = self._find_node_by_id(transition.from_node_id)
                if node:
                    # Calculate similarity score for this node
                    similarity = self._calculate_elements_similarity(current_elements, node.elements_info)
                    if similarity > self._elements_match_threshold:
                        # print(f"Node {node.id} similarity {similarity:.2f} above threshold")
                        all_matches.append((node, workflow, i, similarity))
                    # else:
                        # print(f"Node {node.id} similarity {similarity:.2f} below threshold")
        
        if not all_matches:
            return []
        
        # Sort by similarity and return only the best match
        all_matches.sort(key=lambda x: x[3], reverse=True)
        best_match = all_matches[0]
        
        print(f"Selected best match with similarity: {best_match[3]:.2f}")
        
        # Return without similarity score (maintain original interface)
        return [(best_match[0], best_match[1], best_match[2])]
    
    def _find_node_by_id(self, node_id: str) -> Optional[WorkNode]:
        """Find a node by its ID across all workgraphs."""
        for workgraph in self._memory.historical_workgraphs:
            if node_id in workgraph.nodes:
                return workgraph.nodes[node_id]
        return None
    
    def _calculate_elements_similarity(
        self, 
        current_elements: List[Dict[str, Any]], 
        stored_elements: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate similarity score between current and stored elements.
        
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not current_elements or not stored_elements:
            return 0.0
        
        # Simple matching based on element content and types
        current_contents = set()
        stored_contents = set()
        
        for elem in current_elements:
            content = elem.get('content', '').strip()
            if content:
                current_contents.add(content)
        
        for elem in stored_elements:
            content = elem.get('content', '').strip()
            if content:
                stored_contents.add(content)
        
        if not current_contents or not stored_contents:
            return 0.0
        
        # Calculate similarity ratio
        intersection = current_contents.intersection(stored_contents)
        union = current_contents.union(stored_contents)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _predict_future_nodes(
        self, 
        current_matches: List[Tuple[WorkNode, Workflow, int]]
    ) -> List[SpeculativeNode]:
        """
        Predict future nodes based on workflow patterns.
        
        Specifically predicts:
        1. The next UI state (after current action)
        2. The UI state after that (two steps ahead)
        
        Uses the highest similarity current node match for prediction.
        """
        if not current_matches:
            return []
        
        # Since _find_current_node_matches now returns only the best match,
        # we can directly use the first (and only) match
        current_node, workflow, position = current_matches[0]
        # print(f"Predicting future nodes based on workflow '{workflow.id}' at position {position}, current node: {current_node.id}")
        future_nodes = []
        
        # Predict next UI state (1 step ahead)
        next_position = position + 1
        if next_position < len(workflow.path):
            next_transition = workflow.path[next_position]
            print(f"Next transition: {next_transition.from_node_id}")
            next_node = self._find_node_by_id(next_transition.from_node_id)
            
            if next_node:

                speculative_node = SpeculativeNode(
                    node_id=next_node.id,
                    elements_info=next_node.elements_info,
                    source_workflow=workflow.id,
                    transition_action=next_transition.action
                )
                future_nodes.append(speculative_node)

        # Predict UI state after next (2 steps ahead)
        next_next_position = position + 2
        if next_next_position < len(workflow.path):
            next_next_transition = workflow.path[next_next_position]
            print(f"Next Next transition: {next_next_transition.from_node_id}")
            next_next_node = self._find_node_by_id(next_next_transition.from_node_id)
            
            if next_next_node:
                
                speculative_node = SpeculativeNode(
                    node_id=next_next_node.id,
                    elements_info=next_next_node.elements_info,
                    source_workflow=workflow.id,
                    transition_action=next_next_transition.action
                )
                future_nodes.append(speculative_node)
                
        return future_nodes[:self.max_speculative_nodes]
    
    def _format_speculative_context(
        self, 
        future_nodes: List[SpeculativeNode]
    ) -> str:
        """Format speculative nodes into context string for the model."""
        if not future_nodes:
            return ""
        
        print(f"Formatting speculative context for {len(future_nodes)} future nodes")

        context_lines = []
        
        # Format the first node (next step)
        if len(future_nodes) >= 1:
            node = future_nodes[0]
            context_lines.append("--- NEXT UI STATE (after current action) ---")
            context_lines.extend([
                "Key UI Elements:"
            ])
            
            # Add key UI elements with XML structure
            for j, element in enumerate(node.elements_info):  # Show more elements for better context
                content = element.get('content', '').strip()
                if content:
                    context_lines.append(f"  B{j+1}: {content}")
            
        
        # Format the second node (two steps ahead)
        if len(future_nodes) >= 2:
            node = future_nodes[1]
            context_lines.append("--- UI STATE AFTER NEXT (two steps ahead) ---")
            context_lines.extend([
                "Key UI Elements:"
            ])
            
            # Add key UI elements
            for j, element in enumerate(node.elements_info):  # Fewer elements for distant prediction
                content = element.get('content', '').strip()
                if content:
                    context_lines.append(f"  C{j+1}: {content}")
        
        return '\n'.join(context_lines)
    
    async def parse_action(self, action_code: str, before_elements_index: int, elements_info: List[Dict[str, str]], is_portal: bool = True) -> Tuple[dict[str, Any], str]:
        """
        Parse action from model response.

        Args:
            action_code: The raw action string from the model.

        Returns:
            Parsed action dictionary.

        Raises:
            ValueError: If the response cannot be parsed.
        """
        try:
            action_code = action_code.strip()
            if action_code.startswith("do"):
                # Use AST parsing instead of eval for safety
                try:
                    # Escape special characters (newlines, tabs, etc.) for valid Python syntax
                    action_code = action_code.replace('\n', '\\n')
                    action_code = action_code.replace('\r', '\\r')
                    action_code = action_code.replace('\t', '\\t')

                    tree = ast.parse(action_code, mode="eval")
                    if not isinstance(tree.body, ast.Call):
                        raise ValueError("Expected a function call")

                    call = tree.body
                    # Extract keyword arguments safely
                    action = {"_metadata": "do"}
                    for keyword in call.keywords:
                        key = keyword.arg
                        value = ast.literal_eval(keyword.value)
                        action[key] = value
                    
                    # Convert element ID to actual coordinates if needed
                    if "element" in action and isinstance(action["element"], str):
                        element_id = action["element"]
                        # Find the element with matching ID in elements_info
                        for e2 in self._future_nodes[before_elements_index].elements_info:
                            if element_id == e2["id"]:
                                print(f"Found element with id: {element_id}")
                                if is_portal:
                                    e2_content = f"{e2['resourceId']}/{e2['className']}/{e2['content']}"
                                else:
                                    e2_content = e2["content"]
                                print(f"Element content: {e2_content}")
                                for e1 in elements_info:
                                    if is_portal:
                                        e1_content = f"{e1["resourceId"]}/{e1["className"]}/{e1["content"]}"
                                    else:
                                        e1_content = e1["content"]
                        
                                    if e1_content == e2_content:
                                        print(f"Element content remained the same: {e1_content}")
                                        bbox = e1['bbox']
                                        break                                        
                                    # else:
                                    #     model = SentenceTransformer('./model/sentence-transformers/all-MiniLM-L6-v2')
                                    #     e1_embedding = model.encode(e1_content)
                                    #     e2_embedding = model.encode(e2_content)
                                    #     similarity = self._memory._calculate_cosine_similarity(e1_embedding, e2_embedding)
                                    #     if similarity > 0.9:  # High similarity threshold
                                    #         print(f"Element content {e1_content} remained the same with similarity {similarity}")
                                    #         bbox = e1['bbox']
                                    #         break
                                if bbox:
                                    center_x = (bbox[0][0] + bbox[1][0]) // 2
                                    center_y = (bbox[0][1] + bbox[1][1]) // 2
                                    # Convert to relative coordinates (0-1000 scale)
                                    action["element"] = [center_x, center_y]
                                    if not is_portal:
                                        return action, e1["content"]
                                    else:
                                        return action, f"{e1["resourceId"]}/{e1["className"]}/{e1["content"]}"
                                else:
                                    return None, None

                        return None, None
                        
                    return action, None
                except (SyntaxError, ValueError) as e:
                    raise ValueError(f"Failed to parse do() action: {e}")
            else:
                raise ValueError(f"Failed to parse action: {action_code}")
        except Exception as e:
            raise ValueError(f"Failed to parse action: {e}")

    
    async def executor(
            self, 
            prediction: Dict[str, str], 
            # tag: str, 
            recorder=None, 
            initial_screenshot=None, 
            is_portal: bool = True
        ):
        """
        Execute speculative predictions by storing them in action memory.
        
        Args:
            prediction: List of predicted actions
            recorder: WorkflowRecorder instance for recording actions (optional)
            initial_screenshot: Initial screenshot to use (optional, will capture if not provided)
            
        Returns:
            The final screenshot after all speculative actions, or None if no actions executed
        """

        device_factory = await get_device_factory()
        
        # Use provided screenshot or capture new one
        if initial_screenshot is not None:
            screenshot = initial_screenshot
        else:
            screenshot = await device_factory.get_screenshot(device_id=self.device_id)
        final_screenshot = screenshot

        current_elements = []

        if not is_portal:
            for e in screenshot.elements:
                current_elements.append({
                    "content": e.elem_id,
                    "bbox": e.bbox,
                })
        else:
            for e in screenshot.elements:
                current_elements.append({
                    "resourceId": e.resourceId,
                    "className": e.className,
                    "content": e.content_desc,
                    "bbox": e.bounds,
                })

        # Track if we need to complete agent.py's pending transition
        # Only complete it if we actually execute at least one speculative action
        pending_transition_completed = False
        
        # Track the previous to_node to reuse as from_node in next iteration
        for i in range(len(self._future_nodes)):
            is_match = self._elements_match(current_elements, self._future_nodes[i].elements_info)
            print(f"Elements match with speculative node: {is_match}")
            if is_match:
                # IMPORTANT: Complete any pending transition from agent.py before first speculative action
                # Only do this once, when we're sure we'll execute at least one action
                if not pending_transition_completed and recorder and recorder._pending_from_node_id is not None:
                    # Get current app and work graph
                    current_app = await device_factory.get_current_app(self.device_id)
                    work_graph = self._memory.get_work_graph(current_app)
                    if work_graph is None:
                        work_graph = self._memory.add_work_graph(current_app)
                    
                    # Create to_node for agent.py's action
                    after_elements = []
                    if not is_portal:
                        for e in screenshot.elements:
                            after_elements.append({
                                "content": e.elem_id,
                                "option": e.checked,
                                "focused": e.focused,
                                "path": e.get_xpath()
                            })
                    else:
                        for e in screenshot.elements:
                            after_elements.append({
                                "resourceId": e.resourceId,
                                "className": e.className,
                                "content": e.content_desc,
                                "checked": e.state_desc,
                            })
                    
                    to_node = work_graph.create_node(after_elements)
                    # to_node.add_tag(tag=tag)
                    
                    # Complete agent.py's pending transition
                    recorder.on_new_node(current_node_id=to_node.id)
                    pending_transition_completed = True
                    print("✅ Completed agent.py's pending transition before first speculative action")
                
                for j in range(len(self._future_nodes[i].elements_info)):
                    if i == 0:
                        self._future_nodes[i].elements_info[j]['id'] = f"B{j+1}"
                    elif i == 1:
                        self._future_nodes[i].elements_info[j]['id'] = f"C{j+1}"
                print(f"predictive action content: {list(prediction.values())[i]}")
                
                # print(f"predictive action elements_info: {self._future_nodes[i].elements_info}")
                action, element_content = await self.parse_action(list(prediction.values())[i], i, current_elements)

                if action is None:
                    break

                if action == "Finish":
                    print("Speculative action is Finish, skipping execution.")
                    break

                if ('element' not in action) or (action['element'] and element_content):
                    print(f"Executing speculative action: {action}")
                    try:
                        # Record action to memory - get from_node before execution
                        from_node_id = None
                        node_action = None
                        
                        if recorder:
                            # Get current app
                            current_app = await device_factory.get_current_app(self.device_id)
                            
                            # Get or create work graph for current app
                            work_graph = self._memory.get_work_graph(current_app)
                            if work_graph is None:
                                work_graph = self._memory.add_work_graph(current_app)

                            workflow = self._memory.get_current_workflow()
                            
                            # IMPORTANT: Get the last node ID from workflow to ensure consistency
                            # This must match what the workflow expects as the from_node
                            from_node_id = workflow.get_last_id()
                            
                            if from_node_id is None:
                                # This shouldn't happen, but handle it gracefully
                                print("⚠️ Warning: workflow has no last node, cannot record speculative action")
                                continue
                            
                            from_node = work_graph.get_node_by_id(from_node_id)
                            
                            if from_node is None:
                                # Node not found in graph, skip recording
                                print(f"⚠️ Warning: from_node {from_node_id} not found in work_graph")
                                continue

                            # Get current elements for from_node
                            before_elements = []
                            if not is_portal:
                                for e in screenshot.elements:
                                    before_elements.append({
                                        "content": e.elem_id,
                                        "option": e.checked,
                                        "focused": e.focused,
                                        "path": e.get_xpath()
                                    })
                            else:
                                for e in screenshot.elements:
                                    before_elements.append({
                                        "resourceId": e.resourceId,
                                        "className": e.className,
                                        "content": e.content_desc,
                                        "checked": e.state_desc,
                                    })
                            
                            # Add action to from_node based on action type
                            if action["action"] == "Type":
                                zone_path = None
                                if element_content:
                                    if not is_portal:
                                        for e in before_elements:
                                            if e["content"] == element_content:
                                                zone_path = e["path"]
                                                break
                                    else:
                                        zone_path = element_content
                                node_action = from_node.add_action(
                                    action_type=action["action"],
                                    description=list(prediction.keys())[i],
                                    text=action.get("text"),
                                    zone_path=zone_path,
                                )
                            elif action["action"] == "Swipe":
                                # Find matching element path
                                zone_path = None
                                if element_content:
                                    if not is_portal:
                                        for e in before_elements:
                                            if e["content"] == element_content:
                                                zone_path = e["path"]
                                                break
                                    else:
                                        zone_path = element_content
                                node_action = from_node.add_action(
                                    action_type=action["action"],
                                    description=list(prediction.keys())[i],
                                    zone_path=zone_path,
                                    direction=action.get("direction"),
                                    distance=action.get("dist")
                                )
                            else:
                                # For Click and other actions
                                zone_path = None
                                if element_content:
                                    if not is_portal:
                                        for e in before_elements:
                                            if e["content"] == element_content:
                                                zone_path = e["path"]
                                                break
                                    else:
                                        zone_path = element_content
                                node_action = from_node.add_action(
                                    action_type=action["action"],
                                    description=list(prediction.keys())[i],
                                    zone_path=zone_path
                                )
                                
                        # Execute the action
                        result = await self.action_handler.execute(action, screenshot.width, screenshot.height)
                        
                        # After execution, create to_node and record transition
                        if recorder and from_node_id and node_action:
                            # Record action execution with from_node_id
                            recorder.on_action_executed(
                                from_node_id=from_node_id,
                                action=node_action,
                                success=result.success
                            )
                            
                            # Get screenshot after action execution to create to_node
                            after_screenshot = await device_factory.get_screenshot(device_id=self.device_id)
                            after_elements = []
                            if not is_portal:
                                for e in after_screenshot.elements:
                                    after_elements.append({
                                        "content": e.elem_id,
                                        "option": e.checked,
                                        "focused": e.focused,
                                        "path": e.get_xpath()
                                    })
                            else:
                                for e in after_screenshot.elements:
                                    after_elements.append({
                                        "resourceId": e.resourceId,
                                        "className": e.className,
                                        "content": e.content_desc,
                                        "checked": e.state_desc,
                                    })
                            
                            # Create to_node
                            to_node = work_graph.create_node(after_elements)
                            # to_node.add_tag(tag=tag)
                            
                            # Complete the transition by recording the to_node
                            recorder.on_new_node(current_node_id=to_node.id)
                            
                            # Update screenshot and current_elements for next iteration
                            screenshot = after_screenshot
                            final_screenshot = after_screenshot
                            
                            # Update current_elements for next speculative action matching
                            current_elements = []
                            if not is_portal:
                                for e in screenshot.elements:
                                    current_elements.append({
                                        "content": e.elem_id,
                                        "bbox": e.bbox,
                                    })
                            else:
                                for e in screenshot.elements:
                                    current_elements.append({
                                        "resourceId": e.resourceId,
                                        "className": e.className,
                                        "content": e.content_desc,
                                        "bbox": e.bounds,
                                    })
                        
                        action_dict = {list(prediction.keys())[i]: list(prediction.values())[i]}
                        print(f"Speculative action executed and recorded: {action_dict}")
                        # self._context.add_history_entry(content="", action=action_dict, tag=tag)
                        self._context.add_history_entry(content="", action=action_dict)
                        
                    except Exception as e:
                        print(f"Speculative action execution error: {e}")
                        break
            else:
                break

        return final_screenshot

    def _elements_match(
        self, 
        current_elements: List[Dict[str, Any]], 
        stored_elements: List[Dict[str, Any]]
    ) -> bool:
        """
        Check if current UI elements match stored elements.
        
        Uses a similarity-based approach rather than exact matching.
        """
        similarity = self._calculate_elements_similarity(current_elements, stored_elements)
        print(f"Element similarity: {similarity:.2f}")
        return similarity > self._elements_match_threshold  # 70% similarity threshold
