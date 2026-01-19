from typing import Optional
from .workflow import Workflow
from .worknode import WorkAction

class WorkflowRecorder:
    """
    Temporary recorder for building Workflows during a single task execution.
    Supports automatic workflow decomposition when tags change.
    """

    def __init__(self, task: str, workflow: Workflow):
        self.task = task
        self.current_workflow = workflow
        self.completed_workflows = []  # Store completed workflows
        
        # 用于"延迟完成"的缓存
        self._pending_from_node_id: Optional[str] = None
        self._pending_action: Optional[WorkAction] = None
        self._pending_success: bool = True
        
        # Workflow decomposition support
        self._current_tag: str = ""
        self._workflow_counter: int = 1


    def on_new_node(self, current_node_id: str) -> None:
        """
        Called when transitioning to a new node. Completes any pending transition.
        
        Args:
            current_node_id: The ID of the node we're transitioning to
        """
        if self._pending_from_node_id is not None:
            self.current_workflow.add_transition(
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
        When task is done, flush the recorder by completing current workflow and clearing pending transitions.
        """
        self._clear_pending_transition()
        
        # Complete the current workflow if it has content
        if self.current_workflow.tag and (len(self.current_workflow.path) > 0 or self._current_tag):
            self._complete_current_workflow()

    def set_tag(self, tag: str) -> None:
        """
        Set the tag for the current workflow. If tag changes, decompose into a new workflow.
        
        Args:
            tag: The tag to set for the workflow
        """
        # Skip empty or None tags
        if not tag or not tag.strip():
            return
            
        tag = tag.strip()
        
        # First tag - set it directly
        if self._current_tag == "":
            self._current_tag = tag
            self.current_workflow.tag = tag
            return
        
        # Same tag - no change needed
        if self._current_tag == tag:
            return
            
        # Different tag - decompose workflow
        if self._current_tag != tag:
            self._complete_current_workflow()
            self._start_new_workflow(tag)
    
    def _complete_current_workflow(self) -> None:
        """Complete the current workflow and add it to completed workflows."""
        if self.current_workflow.tag and len(self.current_workflow.path) > 0:
            self.completed_workflows.append(self.current_workflow)
            print(f"✅ Completed workflow: {self.current_workflow.tag} with {len(self.current_workflow.path)} transitions")
    
    def _start_new_workflow(self, tag: str) -> None:
        """Start a new workflow with the given tag."""
        import uuid
        
        # Create new workflow with a unique ID
        new_workflow_id = f"{self.current_workflow.id}_sub_{self._workflow_counter}"
        self._workflow_counter += 1
        
        # Create new workflow instance
        from .workflow import Workflow
        self.current_workflow = Workflow(id=new_workflow_id, task=self.task)
        self.current_workflow.tag = tag
        self._current_tag = tag
        
        print(f"🔄 Started new sub-workflow: {tag} (ID: {new_workflow_id})")
    
    def get_all_workflows(self) -> list:
        """Get all workflows (completed + current)."""
        workflows = self.completed_workflows.copy()
        
        # Add current workflow if it has content
        if self.current_workflow.tag and len(self.current_workflow.path) > 0:
            workflows.append(self.current_workflow)
        elif self.current_workflow.tag:  # Has tag but no transitions yet
            workflows.append(self.current_workflow)
            
        return workflows
    
    def _clear_pending_transition(self) -> None:
        """Clear any pending transition data."""
        self._pending_from_node_id = None
        self._pending_action = None
        self._pending_success = True
