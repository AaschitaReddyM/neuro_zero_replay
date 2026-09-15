"""LLM client for agent decision-making supporting Gemini and OpenAI."""
import json
import aiohttp
from typing import Dict, Any, List, Optional
from src.utils.config import Config
from src.utils.logging import get_logger
from src.safety.guardrails import redact_sensitive_data

logger = get_logger(__name__)


class LLMClient:
    """Client for interacting with LLM APIs (Gemini or OpenAI)."""
    
    def __init__(self):
        """Initialize the LLM client based on configuration."""
        self.provider = Config.LLM_PROVIDER.lower()
        if not Config.OPENAI_API_KEY and Config.GEMINI_API_KEY:
            self.provider = "gemini"
            
        self.gemini_key = Config.GEMINI_API_KEY
        self.gemini_model = Config.GEMINI_MODEL
        self.openai_key = Config.OPENAI_API_KEY
        self.openai_model = Config.OPENAI_MODEL
        
        if self.provider == "openai" and self.openai_key:
            from openai import AsyncOpenAI
            self.openai_client = AsyncOpenAI(api_key=self.openai_key)
        else:
            self.openai_client = None
            
        logger.info("LLMClient initialized", provider=self.provider, 
                    model=self.gemini_model if self.provider == "gemini" else self.openai_model)
        
    async def decide_next_action(self, goal: str, current_state: Dict[str, Any], 
                                action_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Decide the next action based on current state and goal."""
        
        system_prompt = """You are an autonomous web automation agent executing goals against a banking application.
You observe the current page state and accessibility tree and decide the exact next action to take.

Available actions:
1. navigate: Go to an allowed URL.
   {"action_type": "navigate", "value": "http://localhost:8080", "reasoning": "..."}

2. click: Click a button, tab, or link.
   {"action_type": "click", "target_role": "button", "target_name": "Search", "reasoning": "..."}

3. type: Fill text into an input field.
   {"action_type": "type", "target_role": "textbox", "target_name": "Member ID", "value": "12345", "reasoning": "..."}

4. extract: Extract text or data from the result container. Use a selector like '#result-container'.
   {"action_type": "extract", "target_selector": "#result-container", "output_key": "result_details", "reasoning": "Extract result information"}

5. wait: Pause for asynchronous UI updates.
   {"action_type": "wait", "value": "1000", "reasoning": "..."}

6. done: The goal is fully satisfied. Return the extracted outputs and a checkpoint condition to verify completion.
   {
     "action_type": "done",
     "reasoning": "Information retrieved successfully",
     "outputs": {"item_name": "...", "amount": "..."},
     "checkpoint": {
       "strategy": "semantic_selector",
       "value": "#result-container",
       "text_contains": "Operation Complete"
     }
   }

Respond ONLY with a valid JSON object. Be concise, precise, and efficient."""
        
        # Redact any sensitive information before assembling LLM prompt
        redacted_state = redact_sensitive_data(current_state)
        
        user_prompt = f"""Goal: {goal}

Current Page State:
{self._format_state(redacted_state)}

Action History:
{self._format_history(action_history)}

What is the next single action to take towards the goal?"""
        
        if self.provider == "gemini":
            return await self._call_gemini(system_prompt, user_prompt)
        else:
            return await self._call_openai(system_prompt, user_prompt)
            
    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Execute request against Google Gemini REST API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_prompt}\n\n{user_prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as response:
                if response.status != 200:
                    err_text = await response.text()
                    logger.error("Gemini API error", status=response.status, body=err_text)
                    raise RuntimeError(f"Gemini API returned status {response.status}: {err_text}")
                data = await response.json()
                try:
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                    decision = self._parse_response(content)
                    logger.info("Gemini decision generated", action_type=decision.get("action_type"))
                    return decision
                except (KeyError, IndexError) as e:
                    logger.error("Unexpected Gemini response structure", response=data)
                    raise RuntimeError(f"Unexpected response format from Gemini: {str(e)}")
                    
    async def _call_openai(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Execute request against OpenAI API."""
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            decision = self._parse_response(content)
            logger.info("OpenAI decision generated", action_type=decision.get("action_type"))
            return decision
        except Exception as e:
            logger.error("OpenAI decision failed", error=str(e))
            raise
            
    def _format_state(self, state: Dict[str, Any]) -> str:
        """Format the current state for the LLM."""
        if not state:
            return "No state available"
            
        formatted = []
        if "url" in state:
            formatted.append(f"URL: {state['url']}")
        if "page_title" in state:
            formatted.append(f"Title: {state['page_title']}")
        if "accessibility_tree" in state:
            formatted.append("Interactive Elements (Accessibility Tree):")
            formatted.append(self._format_accessibility_tree(state["accessibility_tree"]))
        if "text_content" in state:
            formatted.append(f"Visible Page Text: {state['text_content'][:600]}...")
            
        return "\n".join(formatted)
        
    def _format_accessibility_tree(self, tree: Dict[str, Any], indent: int = 0) -> str:
        """Format accessibility tree for LLM consumption."""
        lines = []
        prefix = "  " * indent
        
        role = tree.get("role", "unknown")
        name = tree.get("name", "")
        
        if name:
            lines.append(f"{prefix}{role}: \"{name}\"")
        else:
            lines.append(f"{prefix}{role}")
            
        if "children" in tree:
            for child in tree["children"]:
                lines.append(self._format_accessibility_tree(child, indent + 1))
                
        return "\n".join(lines)
        
    def _format_history(self, history: List[Dict[str, Any]]) -> str:
        """Format action history for the LLM."""
        if not history:
            return "No actions taken yet."
            
        formatted = []
        for i, action in enumerate(history, 1):
            formatted.append(f"{i}. {action.get('action_type', 'unknown')}: {action.get('description', '')}")
            
        return "\n".join(formatted)
        
    def _parse_response(self, response_content: str) -> Dict[str, Any]:
        """Parse the LLM response JSON."""
        cleaned = response_content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM response as JSON", content=response_content)
            return {
                "action_type": "wait",
                "value": "1000",
                "reasoning": "Failed to parse LLM response, waiting 1s"
            }