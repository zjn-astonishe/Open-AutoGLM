"""Error pattern analysis and prevention for PhoneAgent."""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class ErrorPattern:
    """Represents a detected error pattern."""
    pattern_type: str
    description: str
    failed_actions: List[Dict[str, Any]]
    context_conditions: List[str]
    suggested_alternatives: List[str]
    confidence: float


class ErrorAnalyzer:
    """Analyzes action failures and identifies error patterns."""
    
    def __init__(self):
        self.error_history = []
        self.error_patterns = {}
        self.action_failure_count = defaultdict(int)
        
    def analyze_failure(self, 
                       action: Dict[str, Any], 
                       reflection_result: Dict[str, Any],
                       ui_context: Dict[str, Any],
                       recent_history: List[Dict[str, Any]]) -> Optional[ErrorPattern]:
        """
        Analyze a failed action to identify error patterns.
        
        Args:
            action: The failed action
            reflection_result: Reflection analysis of the failure
            ui_context: Current UI state information
            recent_history: Recent action history
            
        Returns:
            ErrorPattern if a pattern is detected, None otherwise
        """
        failure_info = {
            "action": action,
            "reflection": reflection_result,
            "ui_context": ui_context,
            "timestamp": len(self.error_history),
            "recent_actions": recent_history[-5:] if recent_history else []
        }
        
        self.error_history.append(failure_info)
        
        # Detect specific error patterns
        error_pattern = self._detect_error_pattern(failure_info)
        
        if error_pattern:
            pattern_key = f"{error_pattern.pattern_type}_{error_pattern.description}"
            self.error_patterns[pattern_key] = error_pattern
            
        return error_pattern
    
    def _detect_error_pattern(self, failure_info: Dict[str, Any]) -> Optional[ErrorPattern]:
        """Detect specific error patterns from failure information."""
        action = failure_info["action"]
        reflection = failure_info["reflection"]
        recent_actions = failure_info["recent_actions"]
        
        # Pattern 1: Repeated same action failure
        if self._is_repeated_action_failure(action, recent_actions):
            return ErrorPattern(
                pattern_type="repeated_failure",
                description=f"Repeated {action.get('action', 'unknown')} action failing",
                failed_actions=[action] + [a for a in recent_actions if a.get("action") == action.get("action")],
                context_conditions=self._extract_ui_conditions(failure_info["ui_context"]),
                suggested_alternatives=self._suggest_alternatives_for_repeated_failure(action),
                confidence=0.8
            )
        
        # Pattern 2: Wrong element targeting
        if self._is_wrong_element_targeting(reflection):
            return ErrorPattern(
                pattern_type="wrong_element",
                description="Targeting wrong UI element",
                failed_actions=[action],
                context_conditions=self._extract_ui_conditions(failure_info["ui_context"]),
                suggested_alternatives=self._suggest_element_alternatives(action, failure_info["ui_context"]),
                confidence=0.7
            )
        
        # Pattern 3: Timing issues
        if self._is_timing_issue(reflection):
            return ErrorPattern(
                pattern_type="timing_issue",
                description="Action executed too early or UI not ready",
                failed_actions=[action],
                context_conditions=["UI_NOT_READY", "LOADING_STATE"],
                suggested_alternatives=["Wait for UI to stabilize", "Check for loading indicators"],
                confidence=0.6
            )
        
        # Pattern 4: Input validation errors
        if self._is_input_validation_error(action, reflection):
            return ErrorPattern(
                pattern_type="input_validation",
                description="Input text rejected or invalid format",
                failed_actions=[action],
                context_conditions=self._extract_ui_conditions(failure_info["ui_context"]),
                suggested_alternatives=self._suggest_input_alternatives(action),
                confidence=0.75
            )
        
        return None
    
    def _is_repeated_action_failure(self, current_action: Dict[str, Any], recent_actions: List[Dict[str, Any]]) -> bool:
        """Check if the same action has failed multiple times recently."""
        action_type = current_action.get("action")
        element = current_action.get("element")
        
        similar_failures = 0
        for action in recent_actions[-3:]:  # Check last 3 actions
            if (action.get("action") == action_type and 
                action.get("element") == element):
                similar_failures += 1
        
        return similar_failures >= 2
    
    def _is_wrong_element_targeting(self, reflection: Dict[str, Any]) -> bool:
        """Check if the failure is due to targeting wrong element."""
        reasoning = reflection.get("reflection_reasoning", "").lower()
        abnormal_states = reflection.get("abnormal_states", "").lower()
        
        wrong_element_indicators = [
            "wrong element", "incorrect target", "element not found",
            "no response", "element not clickable", "element disabled"
        ]
        
        return any(indicator in reasoning or indicator in abnormal_states 
                  for indicator in wrong_element_indicators)
    
    def _is_timing_issue(self, reflection: Dict[str, Any]) -> bool:
        """Check if the failure is due to timing issues."""
        reasoning = reflection.get("reflection_reasoning", "").lower()
        abnormal_states = reflection.get("abnormal_states", "").lower()
        
        timing_indicators = [
            "loading", "not ready", "still processing", "animation",
            "transition", "delay needed", "too fast", "ui not stable"
        ]
        
        return any(indicator in reasoning or indicator in abnormal_states 
                  for indicator in timing_indicators)
    
    def _is_input_validation_error(self, action: Dict[str, Any], reflection: Dict[str, Any]) -> bool:
        """Check if the failure is due to input validation."""
        if action.get("action") != "Type":
            return False
            
        reasoning = reflection.get("reflection_reasoning", "").lower()
        abnormal_states = reflection.get("abnormal_states", "").lower()
        
        validation_indicators = [
            "invalid format", "validation error", "format required",
            "invalid input", "text rejected", "field validation"
        ]
        
        return any(indicator in reasoning or indicator in abnormal_states 
                  for indicator in validation_indicators)
    
    def _extract_ui_conditions(self, ui_context: Dict[str, Any]) -> List[str]:
        """Extract relevant UI conditions from context."""
        conditions = []
        
        # Add element count condition
        element_count = ui_context.get("element_count", 0)
        if element_count > 20:
            conditions.append("COMPLEX_UI")
        elif element_count < 5:
            conditions.append("SIMPLE_UI")
        
        # Add app context
        current_app = ui_context.get("current_app", "")
        if current_app:
            conditions.append(f"APP_{current_app.upper()}")
        
        return conditions
    
    def _suggest_alternatives_for_repeated_failure(self, action: Dict[str, Any]) -> List[str]:
        """Suggest alternatives for repeated action failures."""
        action_type = action.get("action")
        
        if action_type == "Tap":
            return [
                "Try long press instead of tap",
                "Look for alternative UI elements with similar function",
                "Check if element is scrolled out of view",
                "Wait for UI to stabilize before tapping"
            ]
        elif action_type == "Type":
            return [
                "Clear field before typing",
                "Check input format requirements",
                "Try typing shorter text first",
                "Look for input validation messages"
            ]
        elif action_type == "Swipe":
            return [
                "Try different swipe direction",
                "Use shorter swipe distance",
                "Check if element is scrollable",
                "Try tap instead of swipe"
            ]
        
        return ["Try a different approach", "Check UI state before action"]
    
    def _suggest_element_alternatives(self, action: Dict[str, Any], ui_context: Dict[str, Any]) -> List[str]:
        """Suggest alternative elements to target."""
        return [
            "Look for elements with similar text or function",
            "Check for buttons or links near the target area",
            "Try elements with keywords related to the task",
            "Look for alternative navigation paths"
        ]
    
    def _suggest_input_alternatives(self, action: Dict[str, Any]) -> List[str]:
        """Suggest alternatives for input validation errors."""
        text = action.get("text", "")
        
        suggestions = [
            "Check field requirements (format, length, etc.)",
            "Try simpler input without special characters"
        ]
        
        # Specific suggestions based on input content
        if any(char in text for char in "!@#$%^&*()"):
            suggestions.append("Remove special characters from input")
        
        if len(text) > 50:
            suggestions.append("Try shorter input text")
        
        if text.isdigit():
            suggestions.append("Check if numeric format is correct")
        
        return suggestions
    
    def get_prevention_guidance(self, 
                              current_action: Dict[str, Any],
                              ui_context: Dict[str, Any]) -> Optional[str]:
        """
        Get guidance to prevent known error patterns.
        
        Args:
            current_action: Action about to be executed
            ui_context: Current UI context
            
        Returns:
            Prevention guidance string if applicable
        """
        guidance_parts = []
        
        # Check for known error patterns
        for pattern_key, pattern in self.error_patterns.items():
            if self._action_matches_pattern(current_action, pattern):
                guidance_parts.append(
                    f"⚠️ Warning: Similar action failed before ({pattern.description}). "
                    f"Consider: {'; '.join(pattern.suggested_alternatives[:2])}"
                )
        
        # Check action failure count
        action_signature = f"{current_action.get('action', '')}_{current_action.get('element', '')}"
        failure_count = self.action_failure_count.get(action_signature, 0)
        
        if failure_count >= 2:
            guidance_parts.append(
                f"⚠️ This exact action has failed {failure_count} times. "
                f"Consider alternative approach or different element."
            )
        
        return "\n".join(guidance_parts) if guidance_parts else None
    
    def _action_matches_pattern(self, action: Dict[str, Any], pattern: ErrorPattern) -> bool:
        """Check if current action matches a known error pattern."""
        # Simple matching based on action type and context
        if not pattern.failed_actions:
            return False
        
        failed_action = pattern.failed_actions[0]
        return (action.get("action") == failed_action.get("action") and
                action.get("element") == failed_action.get("element"))
    
    def record_action_result(self, action: Dict[str, Any], success: bool):
        """Record the result of an action for failure tracking."""
        action_signature = f"{action.get('action', '')}_{action.get('element', '')}"
        
        if not success:
            self.action_failure_count[action_signature] += 1
        else:
            # Reset failure count on success
            self.action_failure_count[action_signature] = 0
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of detected error patterns."""
        return {
            "total_failures": len(self.error_history),
            "detected_patterns": len(self.error_patterns),
            "pattern_types": list(set(p.pattern_type for p in self.error_patterns.values())),
            "most_failed_actions": dict(sorted(self.action_failure_count.items(), 
                                             key=lambda x: x[1], reverse=True)[:5])
        }
