#!/usr/bin/env python3
"""
Script to update workflow JSON files to standardize action format.
Only Swipe actions should have direction and distance.
Only Type actions should have text.
All other actions should have these fields as null.
"""

import json
import re
import os
from pathlib import Path


def update_action_format(action):
    """Update a single action to conform to the required format."""
    # Initialize the fields to null/None by default
    action.setdefault("direction", None)
    action.setdefault("distance", None)
    action.setdefault("text", None)
    
    # Set to null if not swipe/type
    if action.get("action_type") != "Swipe":
        action["direction"] = None
        action["distance"] = None
    else:
        # For Swipe actions, set reasonable defaults if not already set
        if action["direction"] is None:
            # Try to infer direction from description
            desc = action.get("description", "").lower()
            if "down" in desc:
                action["direction"] = "down"
            elif "up" in desc:
                action["direction"] = "up"
            elif "left" in desc:
                action["direction"] = "left"
            elif "right" in desc:
                action["direction"] = "right"
            else:
                action["direction"] = "down"  # default
        
        if action["distance"] is None:
            # Set distance based on description or default
            desc = action.get("description", "").lower()
            if "far" in desc or "maximum" in desc or "minimum" in desc or "max" in desc or "min" in desc:
                action["distance"] = "long"
            elif "short" in desc or "slightly" in desc:
                action["distance"] = "short"
            else:
                action["distance"] = "short"  # default
    
    if action.get("action_type") != "Type":
        action["text"] = None
    else:
        # For Type actions, extract text from description if not already set
        if action["text"] is None:
            # Extract text from description using regex
            desc = action.get("description", "")
            # Look for text like "Type 'something' into the field"
            match = re.search(r'Type ["\']([^"\']*)["\']', desc)
            if match:
                action["text"] = match.group(1)
            else:
                # Try to find any quoted text in the description
                matches = re.findall(r'["\']([^"\']+)["\']', desc)
                if matches:
                    # Take the first meaningful match (not likely to be a UI element)
                    for match in matches:
                        if len(match) > 0 and not match.startswith('@'):
                            action["text"] = match
                            break
                else:
                    action["text"] = ""  # default to empty string

    return action


def process_workflow_file(file_path):
    """Process a single workflow file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Process each workflow in the file
    for workflow in data:
        for path_item in workflow.get('path', []):
            if 'action' in path_item:
                path_item['action'] = update_action_format(path_item['action'])
    
    # Write back to file
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    workflow_dir = Path("/home/zjn/Code/Agent/Open-AutoGLM/output/memory2/workflow")
    
    # Get all JSON files in the workflow directory
    json_files = list(workflow_dir.glob("*.json"))
    
    print(f"Processing {len(json_files)} workflow files...")
    
    for file_path in json_files:
        print(f"Processing {file_path.name}...")
        try:
            process_workflow_file(file_path)
            print(f"  ✓ Completed {file_path.name}")
        except Exception as e:
            print(f"  ✗ Error processing {file_path.name}: {str(e)}")
    
    print("Done!")


if __name__ == "__main__":
    main()