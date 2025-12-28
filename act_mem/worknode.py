from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class WorkAction:
    """Represents an action from one WorkNode to another."""
    action_type: str
    description: str
    zone_path: Optional[str] = None


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

    def add_action(self, action_type: str, description: str, zone_path: Optional[str] = None) -> WorkAction:
        for action in self.actions:
            if action.zone_path == zone_path:
                return action
        action = WorkAction(
            action_type=action_type,
            description=description,
            zone_path=zone_path
        )
        self.actions.append(action)
        return action
    
    def add_tag(self, tag: str) -> None:
        if tag not in self.tag:
            self.tag.append(tag)

    def to_json(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "elements_info": self.elements_info,
            "tasks": self.tasks,
            "actions": [
                {
                    "action_type": action.action_type,
                    "description": action.description,
                    "zone_path": action.zone_path
                } for action in self.actions
            ],
            "tag": self.tag
        }
    
    

