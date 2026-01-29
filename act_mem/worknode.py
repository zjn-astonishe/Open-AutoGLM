from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class WorkAction:
    """Represents an action from one WorkNode to another."""
    action_type: str
    description: str
    zone_path: Optional[str] = None
    reflection_result: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    # Additional parameters for specific actions
    direction: Optional[str] = None  # For swipe actions
    distance: Optional[int] = None   # For swipe actions
    text: Optional[str] = None       # For text input actions


class WorkNode:
    """
    Node representing a focused interaction region (subtask) on the phone.

    Attributes:
        id (str): Unique node identifier.
        elements_info (List[Dict[str, str]]): List of elements associated with this node.
        tasks (Dict[str, List[WorkAction]]): Mapping from task descriptions to lists of WorkActions.
    """
    
    def __init__(self, id: str, elements_info: List[Dict[str, str]]) -> None:
        self.id: str = id
        self.elements_info: List[Dict[str, str]] = elements_info
        self.tasks: List[str] = []
        self.actions: List[WorkAction] = []
        self.tag: List[str] = []
        
    def add_task(self, task: str) -> None:
        if task not in self.tasks:
            self.tasks.append(task)

    def add_action(
            self, 
            action_type: str, 
            description: str, 
            zone_path: Optional[str] = None,
            direction: Optional[str] = None,
            distance: Optional[int] = None, 
            text: Optional[str] = None,
            reflection_result: Optional[Dict[str, Any]] = None
        ) -> WorkAction:
        for action in self.actions:
            if action.zone_path == zone_path:
                return action
        action = WorkAction(
            action_type=action_type,
            description=description,
            zone_path=zone_path,
            reflection_result=reflection_result,
            confidence_score=reflection_result.get('confidence_score') if reflection_result else None,
            direction=direction,
            distance=distance,
            text=text
        )
        self.actions.append(action)
        return action
    
    def add_tag(self, tag: str) -> None:
        if tag not in self.tag:
            # print(f"Adding tag {tag} to node {self.id}")
            self.tag.append(tag)

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "elements_info": self.elements_info,
            "tasks": self.tasks,
            "actions": [
                {
                    "action_type": action.action_type,
                    "description": action.description,
                    "zone_path": action.zone_path,
                    "reflection_result": action.reflection_result,
                    "confidence_score": action.confidence_score,
                    "direction": action.direction,
                    "distance": action.distance,
                    "text": action.text
                } for action in self.actions
            ],
            "tag": self.tag
        }
