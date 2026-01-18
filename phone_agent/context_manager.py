"""Context manager for structured conversation context."""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from phone_agent.model.client import MessageBuilder


@dataclass
class ContextSection:
    """Base class for context sections."""
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """Convert section to OpenAI message format."""
        raise NotImplementedError


@dataclass
class SystemPromptSection(ContextSection):
    """System prompt section containing the main system instructions."""
    
    prompt: str
    
    def to_messages(self) -> List[Dict[str, Any]]:
        return [MessageBuilder.create_system_message(self.prompt)]


@dataclass
class TaskDescriptionSection(ContextSection):
    """Task description section containing the user's original request."""
    
    task: str
    timestamp: Optional[str] = None
    
    def to_messages(self) -> List[Dict[str, Any]]:
        content = f"# Task Description\n\n{self.task}"
        if self.timestamp:
            content += f"\n\n**Started at:** {self.timestamp}"
        content += "\n\n---\n\n"
        
        return [MessageBuilder.create_user_message(content)]


@dataclass
class HistoryEntry:
    """Single entry in the action history."""
    
    step: int
    thinking: str
    action_description: str
    action_code: str
    success: bool
    timestamp: Optional[str] = None


@dataclass
class HistorySection(ContextSection):
    """History section containing previous actions and thoughts."""
    
    entries: List[HistoryEntry] = field(default_factory=list)
    max_entries: int = 10  # Limit history to prevent context overflow
    
    def add_entry(self, entry: HistoryEntry) -> None:
        """Add a new history entry, maintaining max_entries limit."""
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            # Keep the most recent entries
            self.entries = self.entries[-self.max_entries:]
    
    def to_messages(self) -> List[Dict[str, Any]]:
        if not self.entries:
            return []
        
        # Create a condensed history summary
        history_content = "# Action History\n\n"
        
        for entry in self.entries:  # Show last 5 entries in detail
            status = "✅" if entry.success else "❌"
            history_content += f"**Step {entry.step}** {status}\n"
            # history_content += f"- {entry.thinking[:100]}{'...' if len(entry.thinking) > 100 else ''}\n"
            history_content += f"- {entry.thinking}\n"
            # history_content += f"- Action: {entry.action_description}\n"
            # history_content += f"- Code: `{entry.action_code}`\n\n"
        
        history_content += "---\n\n"
        
        return [MessageBuilder.create_assistant_message(history_content)]


@dataclass
class ReflectionEntry:
    """Single reflection analysis entry."""
    
    step: int
    action_type: str
    action_description: str
    success: bool
    confidence_score: float
    reasoning: str
    suggestions: str
    timestamp: Optional[str] = None


@dataclass
class ReflectionSection(ContextSection):
    """Reflection section containing action analysis and insights."""
    
    entries: List[ReflectionEntry] = field(default_factory=list)
    max_entries: int = 5  # Keep recent reflections
    
    def add_reflection(self, entry: ReflectionEntry) -> None:
        """Add a new reflection entry."""
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
    
    def to_messages(self) -> List[Dict[str, Any]]:
        if not self.entries:
            return []
        
        # Only include reflection if the most recent action failed or had low confidence
        latest_entry = self.entries[-1]
        
        # Only show reflection if the latest action was problematic
        if latest_entry.success and latest_entry.confidence_score >= 0.7:
            return []
        
        reflection_content = "# Previous Action Issue\n\n"
        
        status = "⚠️" if not latest_entry.success else "🔍"
        confidence = f"(confidence: {latest_entry.confidence_score:.2f})"
        
        reflection_content += f"**{status} Step {latest_entry.step}** - {latest_entry.action_type} {confidence}\n"
        reflection_content += f"- Issue: {latest_entry.reasoning}\n"
        if latest_entry.suggestions:
            reflection_content += f"- Suggestion: {latest_entry.suggestions}\n"
        reflection_content += "\n---\n\n"
        
        return [MessageBuilder.create_assistant_message(reflection_content)]


@dataclass
class ScreenshotSection(ContextSection):
    """Screenshot section containing the current UI image."""
    
    image_base64: Optional[str] = None
    width: int = 0
    height: int = 0
    timestamp: Optional[str] = None
    
    def to_messages(self) -> List[Dict[str, Any]]:
        if not self.image_base64:
            return []
        
        content = "# Current Screen\n\n"
        if self.width and self.height:
            content += f"**Resolution:** {self.width}x{self.height}\n"
        if self.timestamp:
            content += f"**Captured at:** {self.timestamp}\n"
        content += "\n---\n\n"
        
        return [MessageBuilder.create_user_message(
            text=content,
            image_base64=self.image_base64
        )]


@dataclass
class ScreenInfoSection(ContextSection):
    """Screen info section containing structured UI element data."""
    
    current_app: str = ""
    elements: List[Dict[str, Any]] = field(default_factory=list)
    extra_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_messages(self) -> List[Dict[str, Any]]:
        # Build structured screen info
        screen_info = {
            "current_app": self.current_app,
            "elements": self.elements,
            **self.extra_info
        }
        
        content = f"# Screen Info\n\n{json.dumps(screen_info, ensure_ascii=False, indent=2)}\n\n---\n\n"
        
        return [MessageBuilder.create_user_message(content)]


class StructuredContext:
    """
    Structured context manager that organizes conversation context into logical sections.
    
    This replaces the simple list-based _context with a more organized structure:
    - System Prompt: Core instructions and capabilities
    - Task Description: User's original request
    - History: Previous actions and thoughts (condensed)
    - Reflection: Analysis and insights from recent actions
    - Screenshot: Current UI image
    - Screen Info: Structured UI element data
    """
    
    def __init__(self):
        self.system_prompt = SystemPromptSection("")
        self.task_description = TaskDescriptionSection("")
        self.history = HistorySection()
        self.reflection = ReflectionSection()
        self.screenshot = ScreenshotSection()
        self.screen_info = ScreenInfoSection()
        
        self._step_count = 0
    
    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt."""
        self.system_prompt.prompt = prompt
    
    def set_task(self, task: str, timestamp: Optional[str] = None) -> None:
        """Set the task description."""
        self.task_description.task = task
        self.task_description.timestamp = timestamp
    
    def add_action(
        self,
        thinking: str,
        action_description: str,
        action_code: str,
        success: bool,
        timestamp: Optional[str] = None
    ) -> None:
        """Add an action to the history."""
        self._step_count += 1
        entry = HistoryEntry(
            step=self._step_count,
            thinking=thinking,
            action_description=action_description,
            action_code=action_code,
            success=success,
            timestamp=timestamp
        )
        self.history.add_entry(entry)
    
    def add_reflection(
        self,
        action_type: str,
        action_description: str = "",
        success: bool = True,
        confidence: float = 0.5,
        reasoning: str = "",
        suggestions: str = "",
        timestamp: Optional[str] = None
    ) -> None:
        """Add a reflection analysis."""
        entry = ReflectionEntry(
            step=self._step_count,
            action_type=action_type,
            action_description=action_description,
            success=success,
            confidence_score=confidence,
            reasoning=reasoning,
            suggestions=suggestions,
            timestamp=timestamp
        )
        self.reflection.add_reflection(entry)
    
    def set_screenshot(
        self,
        image_base64: str,
        width: int = 0,
        height: int = 0,
        timestamp: Optional[str] = None
    ) -> None:
        """Set the current screenshot."""
        self.screenshot.image_base64 = image_base64
        self.screenshot.width = width
        self.screenshot.height = height
        self.screenshot.timestamp = timestamp
    
    def set_screen_info(
        self,
        current_app: str,
        elements: List[Dict[str, Any]],
        **extra_info
    ) -> None:
        """Set the screen info."""
        self.screen_info.current_app = current_app
        self.screen_info.elements = elements
        self.screen_info.extra_info = extra_info
    
    def add_screenshot(self, image_base64: str, width: int = 0, height: int = 0, timestamp: Optional[str] = None) -> None:
        """Add screenshot to context (alias for set_screenshot)."""
        self.set_screenshot(image_base64, width, height, timestamp)
    
    def add_screen_info(self, screen_info: Dict[str, Any]) -> None:
        """Add screen info to context."""
        current_app = screen_info.get("current_app", "")
        elements = screen_info.get("elements", [])
        # Remove known keys and pass the rest as extra_info
        extra_info = {k: v for k, v in screen_info.items() if k not in ["current_app", "elements"]}
        self.set_screen_info(current_app, elements, **extra_info)
    
    def add_history_entry(self, content: str, action: Dict[str, Any] | None = None) -> None:
        """Add a history entry (thinking/response) to context."""
        # Add thinking content as a history entry
        self._step_count += 1
        entry = HistoryEntry(
            step=self._step_count,
            thinking=content,
            action_description=list(action.keys())[0],  # Will be filled when action is executed
            action_code=list(action.values())[0],  # Will be filled when action is executed
            success=True  # Default to True, will be updated based on action result
        )
        self.history.add_entry(entry)
    
    def clear_current_step(self) -> None:
        """Clear current step's temporary data to save context space."""
        # Clear screenshot and screen info to save space
        # Keep them available but mark as cleared for context optimization
        self.screenshot = ScreenshotSection()
        self.screen_info = ScreenInfoSection()
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        Convert the structured context to OpenAI message format.
        
        Returns messages in the following order:
        1. System Prompt
        2. Task Description (only on first step)
        3. History (condensed, recent actions only)
        4. Reflection (only important insights)
        5. Screenshot (current UI)
        6. Screen Info (current UI elements)
        """
        messages = []
        
        # 1. System Prompt (always first)
        messages.extend(self.system_prompt.to_messages())
        
        # 2. Task Description (only if this is the first step or task changed)
        messages.extend(self.task_description.to_messages())
        
        # 3. History (condensed recent actions)
        messages.extend(self.history.to_messages())
        
        # 4. Reflection (only important insights)
        messages.extend(self.reflection.to_messages())
        
        # 5. Screenshot (current UI state)
        messages.extend(self.screenshot.to_messages())
        
        # 6. Screen Info (current UI elements)
        messages.extend(self.screen_info.to_messages())
        
        return messages
    
    def reset(self) -> None:
        """Reset the context for a new task."""
        self.task_description = TaskDescriptionSection("")
        self.history = HistorySection()
        self.reflection = ReflectionSection()
        self.screenshot = ScreenshotSection()
        self.screen_info = ScreenInfoSection()
        self._step_count = 0
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of the current context state."""
        return {
            "step_count": self._step_count,
            "task": self.task_description.task,
            "history_entries": len(self.history.entries),
            "reflection_entries": len(self.reflection.entries),
            "has_screenshot": bool(self.screenshot.image_base64),
            "current_app": self.screen_info.current_app,
            "element_count": len(self.screen_info.elements)
        }
    
    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count
