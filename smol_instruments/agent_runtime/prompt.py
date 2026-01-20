"""
Dynamic tool description generation for smolagents.

Tool names and descriptions are extracted from Tool objects, not hardcoded.
"""

from typing import List
from smolagents import Tool


def generate_tool_descriptions(tools: List[Tool]) -> str:
    """
    Generate formatted tool descriptions from Tool objects.
    
    Args:
        tools: List of Tool instances
        
    Returns:
        Formatted string with tool descriptions
    """
    descriptions = []
    
    for tool in tools:
        # Skip final_answer as it's handled by smolagents
        if tool.name == "final_answer":
            continue
            
        # Format: tool_name(arg1, arg2): Description
        if tool.inputs:
            args = ", ".join(tool.inputs.keys())
            desc = f"- {tool.name}({args}): {tool.description}"
        else:
            desc = f"- {tool.name}(): {tool.description}"
        
        descriptions.append(desc)
    
    return "\n".join(descriptions)
