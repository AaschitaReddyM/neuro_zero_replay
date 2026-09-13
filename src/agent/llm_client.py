"""LLM client for agent decision-making."""
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from src.utils.config import Config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Client for interacting with OpenAI's API."""
    
    def __init__(self):
        """Initialize the LLM client."""
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL
        
    async def decide_next_action(self, goal: str, current_state: Dict[str, Any], 
                                action_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Decide the next action based on current state and goal."""
        
        system_prompt = """You are an AI agent that interacts with web applications to accomplish specific goals. 
You observe the current state of the application and decide what action to take next.

Available actions:
- navigate: Go to a URL
- click: Click on an element
- type: Type text into an input field
- extract: Extract text/data from the page
- wait: Wait for a condition or time
- select: Select an option from a dropdown
- submit: Submit a form
- confirm: Confirm a dialog or action

When responding, provide a JSON object with this structure:
{
  "action_type": "navigate|click|type|extract|wait|select|submit|confirm",
  "target_description": "Human-readable description of what to interact with",
  "target_role": "Accessibility role (e.g., textbox, button, link)",
  "target_name": "Accessibility name or label",
  "value": "Value to type or URL to navigate (if applicable)",
  "reasoning": "Why you chose this action"
}

Be concise and specific. Focus on accomplishing the goal efficiently."""
        
        user_prompt = f"""Goal: {goal}

Current state:
{self._format_state(current_state)}

Action history:
{self._format_history(action_history)}

What should I do next?"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            decision = self._parse_response(response.choices[0].message.content)
            logger.info("LLM decision made", action_type=decision.get("action_type"))
            return decision
            
        except Exception as e:
            logger.error("LLM decision failed", error=str(e))
            raise
            
    def _format_state(self, state: Dict[str, Any]) -> str:
        """Format the current state for the LLM."""
        if not state:
            return "No state available"
            
        formatted = []
        if "url" in state:
            formatted.append(f"Current URL: {state['url']}")
        if "page_title" in state:
            formatted.append(f"Page title: {state['page_title']}")
        if "accessibility_tree" in state:
            formatted.append("Page content (accessibility tree):")
            formatted.append(self._format_accessibility_tree(state["accessibility_tree"]))
        if "text_content" in state:
            formatted.append(f"Page text: {state['text_content'][:500]}...")
            
        return "\n".join(formatted)
        
    def _format_accessibility_tree(self, tree: Dict[str, Any], indent: int = 0) -> str:
        """Format accessibility tree for LLM consumption."""
        lines = []
        prefix = "  " * indent
        
        role = tree.get("role", "unknown")
        name = tree.get("name", "")
        
        if name:
            lines.append(f"{prefix}{role}: {name}")
        else:
            lines.append(f"{prefix}{role}")
            
        if "children" in tree:
            for child in tree["children"]:
                lines.append(self._format_accessibility_tree(child, indent + 1))
                
        return "\n".join(lines)
        
    def _format_history(self, history: List[Dict[str, Any]]) -> str:
        """Format action history for the LLM."""
        if not history:
            return "No actions taken yet"
            
        formatted = []
        for i, action in enumerate(history, 1):
            formatted.append(f"{i}. {action.get('action_type', 'unknown')}: {action.get('description', '')}")
            
        return "\n".join(formatted)
        
    def _parse_response(self, response_content: str) -> Dict[str, Any]:
        """Parse the LLM response."""
        import json
        try:
            return json.loads(response_content)
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM response as JSON", content=response_content)
            return {
                "action_type": "wait",
                "reasoning": "Failed to parse response, waiting as fallback"
            }