"""Browser automation layer using Playwright."""
from typing import Any, Dict, List, Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from src.artifact.schemas import TargetLocation, LocationStrategy, ActionType
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserAutomation:
    """High-level browser automation interface."""
    
    def __init__(self, headless: bool = True):
        """Initialize browser automation."""
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
    async def start(self) -> None:
        """Start the browser and create a new context."""
        logger.info("Starting browser", headless=self.headless)
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.page = await self.context.new_page()
        logger.info("Browser started successfully")
        
    async def stop(self) -> None:
        """Stop the browser and clean up resources."""
        logger.info("Stopping browser")
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")
        
    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        logger.info("Navigating to URL", url=url)
        await self.page.goto(url, wait_until="networkidle")
        logger.info("Navigation completed")
        
    async def get_accessibility_tree(self) -> Dict[str, Any]:
        """Get the accessibility tree of the current page."""
        snapshot = await self.page.accessibility.snapshot()
        return snapshot
        
    async def get_page_content(self) -> str:
        """Get the text content of the current page."""
        return await self.page.inner_text("body")
        
    async def take_screenshot(self, path: str) -> None:
        """Take a screenshot and save it to the specified path."""
        await self.page.screenshot(path=path, full_page=True)
        logger.info("Screenshot saved", path=path)
        
    async def find_element(self, target: TargetLocation) -> Optional[Any]:
        """Find an element using the specified location strategy with fallbacks."""
        strategies = [target.strategy] + target.fallback_strategies
        
        for strategy in strategies:
            try:
                element = await self._find_by_strategy(strategy, target)
                if element:
                    logger.info("Element found", strategy=strategy.value)
                    return element
            except Exception as e:
                logger.warning("Element not found with strategy", 
                             strategy=strategy.value, error=str(e))
                continue
                
        logger.error("Element not found with any strategy", target=target)
        return None
        
    async def _find_by_strategy(self, strategy: LocationStrategy, target: TargetLocation) -> Optional[Any]:
        """Find element using a specific strategy."""
        if strategy == LocationStrategy.ACCESSIBILITY_ROLE:
            return await self._find_by_accessibility(target)
        elif strategy == LocationStrategy.SEMANTIC_SELECTOR:
            return await self._find_by_semantic(target)
        elif strategy == LocationStrategy.TEXT_CONTENT:
            return await self._find_by_text(target)
        elif strategy == LocationStrategy.TEST_ID:
            return await self._find_by_test_id(target)
        elif strategy == LocationStrategy.XPATH:
            return await self._find_by_xpath(target)
        elif strategy == LocationStrategy.CSS_SELECTOR:
            return await self._find_by_css(target)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
            
    async def _find_by_accessibility(self, target: TargetLocation) -> Optional[Any]:
        """Find element by accessibility role and name."""
        # Use Playwright's role selector
        if target.role and target.name:
            selector = f"[role=\"{target.role}\"][name=\"{target.name}\"]"
            return await self.page.query_selector(selector)
        elif target.role:
            selector = f"[role=\"{target.role}\"]"
            return await self.page.query_selector(selector)
        return None
        
    async def _find_by_semantic(self, target: TargetLocation) -> Optional[Any]:
        """Find element by semantic HTML selector."""
        return await self.page.query_selector(target.value)
        
    async def _find_by_text(self, target: TargetLocation) -> Optional[Any]:
        """Find element by text content."""
        return await self.page.query_selector(f"text={target.value}")
        
    async def _find_by_test_id(self, target: TargetLocation) -> Optional[Any]:
        """Find element by test ID."""
        return await self.page.get_by_test_id(target.value)
        
    async def _find_by_xpath(self, target: TargetLocation) -> Optional[Any]:
        """Find element by XPath."""
        return await self.page.query_selector(f"xpath={target.value}")
        
    async def _find_by_css(self, target: TargetLocation) -> Optional[Any]:
        """Find element by CSS selector."""
        return await self.page.query_selector(target.value)
        
    async def execute_action(self, action_type: ActionType, target: TargetLocation, 
                           value: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Execute an action on a target element."""
        element = await self.find_element(target)
        if not element:
            return False, f"Element not found: {target}"
            
        try:
            if action_type == ActionType.CLICK:
                await element.click()
                logger.info("Click action executed")
            elif action_type == ActionType.TYPE:
                await element.fill(value or "")
                logger.info("Type action executed", value_length=len(value or ""))
            elif action_type == ActionType.EXTRACT:
                text = await element.inner_text()
                logger.info("Extract action executed", text_length=len(text))
                return True, text
            elif action_type == ActionType.SELECT:
                await element.select_option(value)
                logger.info("Select action executed", value=value)
            elif action_type == ActionType.WAIT:
                await self.page.wait_for_timeout(int(value) if value else 1000)
                logger.info("Wait action executed")
            elif action_type == ActionType.SUBMIT:
                await element.click()  # Submit forms by clicking submit button
                logger.info("Submit action executed")
            elif action_type == ActionType.CONFIRM:
                await element.click()  # Confirm dialogs by clicking confirm button
                logger.info("Confirm action executed")
            else:
                return False, f"Unknown action type: {action_type}"
                
            return True, None
        except Exception as e:
            logger.error("Action execution failed", action_type=action_type.value, error=str(e))
            return False, str(e)
            
    async def wait_for_element(self, target: TargetLocation, timeout: int = 5000) -> bool:
        """Wait for an element to become visible."""
        try:
            element = await self.find_element(target)
            if element:
                await element.wait_for(state="visible", timeout=timeout)
                return True
            return False
        except Exception as e:
            logger.warning("Wait for element failed", error=str(e))
            return False
            
    async def check_checkpoint(self, target: TargetLocation, text_contains: Optional[str] = None) -> bool:
        """Check if a checkpoint condition is met."""
        element = await self.find_element(target)
        if not element:
            return False
            
        if text_contains:
            text = await element.inner_text()
            return text_contains.lower() in text.lower()
            
        return True