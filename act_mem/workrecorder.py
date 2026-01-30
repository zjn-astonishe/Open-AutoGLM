from typing import Optional
from .workflow import Workflow
from .worknode import WorkAction

class WorkflowRecorder:
    """
    Temporary recorder for building a Workflow during a single task execution.
    """

    def __init__(self, task: str, workflow: Workflow):
        self.task = task
        self.workflow = workflow
        
        # 用于“延迟完成”的缓存
        self._pending_from_node_id: Optional[str] = None
        self._pending_action: Optional[WorkAction] = None
        self._pending_success: bool = True


    def on_new_node(self, current_node_id: str) -> None:
        """
        Called when transitioning to a new node. Completes any pending transition.
        
        Args:
            current_node_id: The ID of the node we're transitioning to
        """
        if self._pending_from_node_id is not None:
            self.workflow.add_transition(
                from_node_id=self._pending_from_node_id,
                to_node_id=current_node_id,
                action=self._pending_action,
                success=self._pending_success,
            )    
        self._clear_pending_transition()
        
    def on_action_executed(
        self, 
        from_node_id: str,
        action: WorkAction,
        success: bool,
    ) -> None:
        """
        Called when an action is executed. Stores the transition details for later completion.
        
        Args:
            from_node_id: The ID of the node where the action was executed
            action: The action that was executed
            success: Whether the action was successful
        """
        self._pending_from_node_id = from_node_id
        self._pending_action = action
        self._pending_success = success
    
    def flush(self) -> None:
        """
        When task is done, flush the recorder by clearing any pending transitions.
        """
        self._clear_pending_transition()

    def set_tag(self, tag: str) -> None:
        """
        Set the tag for the workflow if it hasn't been set already.
        
        Args:
            tag: The tag to set for the workflow
        """
        if self.workflow.tag == "":
            self.workflow.set_tag(tag)
    
    def _clear_pending_transition(self) -> None:
        """Clear any pending transition data."""
        self._pending_from_node_id = None
        self._pending_action = None
        self._pending_success = True
