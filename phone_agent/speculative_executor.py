"""Speculative executor for predicting future UI states and actions."""

import json
import random
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass

from phone_agent.device_factory import get_device_factory
from phone_agent.actions.handler import parse_action
from phone_agent.context_manager import StructuredContext
from phone_agent.actions.handler import ActionHandler

from act_mem.act_mem import ActionMemory
from act_mem.workflow import Workflow, WorkGraph
from act_mem.worknode import WorkNode, WorkAction


@dataclass
class SpeculativeNode:
    """Represents a speculative future node with its UI XML."""
    
    node_id: str
    elements_info: List[Dict[str, Any]]
    confidence: float
    source_workflow: str
    transition_action: Optional[WorkAction] = None


@dataclass
class SpeculativePrediction:
    """Represents a prediction of future actions and UI states."""
    
    next_action: Dict[str, Any]
    predicted_nodes: List[SpeculativeNode]
    confidence_score: float
    reasoning: str


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
        self.confidence_threshold = 0.6  # Minimum confidence for including predictions
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
        relevant_workflows = self._find_relevant_workflows(current_app, task)
        print(f"Found {len(relevant_workflows)} relevant workflows for app '{current_app}' and task '{task}'")
        if not relevant_workflows:
            return None
        
        # Find current position in workflows
        current_node_matches = self._find_current_node_matches(current_elements, relevant_workflows)
        
        if not current_node_matches:
            return None
        
        # Predict future nodes
        self._future_nodes = self._predict_future_nodes(current_node_matches)
        
        if not self._future_nodes:
            return None
        
        # Format speculative context
        return self._format_speculative_context(self._future_nodes, task)
    
    def _find_relevant_workflows(self, current_app: str, task: str) -> List[Workflow]:
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
                        all_matches.append((node, workflow, i, similarity))
        
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
            next_node = self._find_node_by_id(next_transition.from_node_id)
            
            if next_node:
                
                # Calculate confidence for next step
                confidence = self._calculate_confidence(1, next_transition)
                
                if confidence >= self.confidence_threshold:
                    speculative_node = SpeculativeNode(
                        node_id=next_node.id,
                        elements_info=next_node.elements_info,
                        confidence=confidence,
                        source_workflow=workflow.id,
                        transition_action=next_transition.action
                    )
                    future_nodes.append(speculative_node)
        
        # Predict UI state after next (2 steps ahead)
        next_next_position = position + 2
        if next_next_position < len(workflow.path):
            next_next_transition = workflow.path[next_next_position]
            next_next_node = self._find_node_by_id(next_next_transition.from_node_id)
            
            if next_next_node:
                
                # Calculate confidence for two steps ahead (lower confidence)
                confidence = self._calculate_confidence(2, next_next_transition)
                
                if confidence >= self.confidence_threshold:
                    speculative_node = SpeculativeNode(
                        node_id=next_next_node.id,
                        elements_info=next_next_node.elements_info,
                        confidence=confidence,
                        source_workflow=workflow.id,
                        transition_action=next_next_transition.action
                    )
                    future_nodes.append(speculative_node)
        
        # Sort by confidence and return top nodes (limit to 2: next + next-next)
        
        future_nodes.sort(key=lambda x: x.confidence, reverse=True)
        # print(f"Future nodes: {[ (node.node_id, node.confidence) for node in future_nodes ]}")
        return future_nodes[:self.max_speculative_nodes]
    
  
    def _calculate_confidence(
        self, 
        step_ahead: int, 
        transition: Any
    ) -> float:
        """Calculate confidence score for a predicted node."""
        base_confidence = 0.8
        
        # Reduce confidence based on step distance
        distance_penalty = 0.1 * (step_ahead - 1)
        
        # Adjust based on transition success rate
        success_bonus = 0.1 if getattr(transition, 'success', True) else -0.2
        
        # Add some randomness to avoid deterministic behavior
        random_factor = random.uniform(-0.05, 0.05)
        
        confidence = base_confidence - distance_penalty + success_bonus + random_factor
        return max(0.0, min(1.0, confidence))
    
    def _format_speculative_context(
        self, 
        future_nodes: List[SpeculativeNode], 
        task: str
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
                f"Confidence: {node.confidence:.2f}",
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
                f"Confidence: {node.confidence:.2f}",
                "Key UI Elements:"
            ])
            
            # Add key UI elements
            for j, element in enumerate(node.elements_info):  # Fewer elements for distant prediction
                content = element.get('content', '').strip()
                if content:
                    context_lines.append(f"  C{j+1}: {content}")
        
        return '\n'.join(context_lines)
    
    def executor(self, prediction: Dict[str, str], tag: str) -> None:
        """
        Execute speculative predictions by storing them in action memory.
        
        Args:
            prediction: List of predicted actions
        """

        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(device_id=self.device_id)

        current_elements = []

        for i, e in enumerate(screenshot.elements, 1):
            current_elements.append({
                "content": e.elem_id,
                "bbox": e.bbox,
            })
        for i in range(len(self._future_nodes)):
            is_match = self._elements_match(current_elements, self._future_nodes[i].elements_info)
            print(f"Elements match with speculative node: {is_match}")
            if is_match:
                for e1 in current_elements:
                    for e2 in self._future_nodes[i].elements_info:
                        if e1['content'] == e2['content']:
                            e2['bbox'] = e1['bbox']
                            break
                for j in range(len(self._future_nodes[i].elements_info)):
                    if i == 0:
                        self._future_nodes[i].elements_info[j]['id'] = f"B{j+1}"
                    elif i == 1:
                        self._future_nodes[i].elements_info[j]['id'] = f"C{j+1}"
                print(f"predictive action content: {list(prediction.values())[i]}")
                action, element_content = parse_action(list(prediction.values())[i], self._future_nodes[i].elements_info)
                if action == "Finish":
                    print("Speculative action is Finish, skipping execution.")
                    continue

                if ('element' not in action) or (action['element'] and element_content):
                    print(f"Executing speculative action: {action}")
                    try:
                        result = self.action_handler.execute(action, screenshot.width, screenshot.height)
                        # TODO
                        # Convert single prediction action to dictionary format expected by add_history_entry
                        action_dict = {list(prediction.keys())[i]: list(prediction.values())[i]}
                        self._context.add_history_entry(content="", action=action_dict, tag=tag)
                        
                    except Exception as e:
                        print(f"Speculative action execution error: {e}")
                        break

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
        if similarity > self._elements_match_threshold:
            print(f"Element similarity: {similarity:.2f}")
        return similarity > self._elements_match_threshold  # 70% similarity threshold
