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


    def on_new_node(self, current_node_id: str):
        
        if self._pending_from_node_id is not None:
            self.workflow.add_transition(
                from_node_id=self._pending_from_node_id,
                to_node_id=current_node_id,
                action=self._pending_action,
                success=self._pending_success,
            )
            
        self._pending_from_node_id = None
        self._pending_action = None
        self._pending_success = True
        
    def on_action_executed(
        self, 
        from_node_id: str,
        action: WorkAction,
        success: bool,
    ):
        self._pending_from_node_id = from_node_id
        self._pending_action = action
        self._pending_success = success
    
    def flush(self):
        """
        When task is done, flush the recorder.
        """
        self._pending_from_node_id = None
        self._pending_action = None
        self._pending_success = True

    def set_tag(self, tag: str):
        if self.workflow.tag == "":
            self.workflow.tag = tag