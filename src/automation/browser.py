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
        
    async def find_element(self, target: TargetLocation, timeout: int = 3000) -> Optional[Any]:
        """Find a Playwright Locator using the specified location strategy with fallbacks."""
        strategies = [target.strategy] + target.fallback_strategies
        
        for strategy in strategies:
            try:
                locator = await self._find_by_strategy(strategy, target)
                if locator is not None:
                    # Verify element is attached and visible
                    if await locator.count() > 0:
                        strategy_name = strategy.value
                        target.resolved_strategy = strategy_name
                        logger.info("Element resolved", strategy=strategy_name, role=target.role, name=target.name)
                        return locator
            except Exception as e:
                logger.debug("Strategy resolution failed", strategy=strategy.value, error=str(e))
                continue
                
        logger.error("Element not found with any strategy", target=str(target))
        return None
        
    async def _find_by_strategy(self, strategy: LocationStrategy, target: TargetLocation) -> Optional[Any]:
        """Find element using a specific Playwright locator strategy."""
        if strategy == LocationStrategy.ACCESSIBILITY_ROLE:
            return await self._find_by_accessibility(target)
        elif strategy == LocationStrategy.SEMANTIC_SELECTOR:
            return await self._find_by_semantic(target)
        elif strategy == LocationStrategy.TEXT_CONTENT:
            return await self._find_by_text(target)
        elif strategy == LocationStrategy.TEST_ID:
            return self._find_by_test_id(target)
        elif strategy == LocationStrategy.XPATH:
            return self._find_by_xpath(target)
        elif strategy == LocationStrategy.CSS_SELECTOR:
            return self._find_by_css(target)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
            
    async def _find_by_accessibility(self, target: TargetLocation) -> Optional[Any]:
        """Find element by accessibility role and name using Playwright's get_by_role."""
        if target.role:
            name = target.name
            if not name and target.value and ":" in target.value:
                name = target.value.split(":", 1)[1]
            if name:
                loc_exact = self.page.get_by_role(target.role, name=name, exact=True)
                if await loc_exact.count() > 0:
                    return loc_exact.first
            loc = self.page.get_by_role(target.role, name=name, exact=False)
            if await loc.count() > 0:
                return loc.first
        # Fallback to label if role alone or name exists
        if target.name:
            loc_exact = self.page.get_by_label(target.name, exact=True)
            if await loc_exact.count() > 0:
                return loc_exact.first
            loc = self.page.get_by_label(target.name, exact=False)
            if await loc.count() > 0:
                return loc.first
        return None
        
    async def _find_by_semantic(self, target: TargetLocation) -> Optional[Any]:
        """Find element by semantic selector, label, or derived ID."""
        # 1. If target.value is a valid CSS selector (not a composite role:name)
        if target.value and not (":" in target.value and not target.value.startswith(("#", ".", "["))):
            try:
                loc = self.page.locator(target.value)
                if await loc.count() > 0:
                    return loc.first
            except Exception:
                pass
            if target.value in ("#result-container", ".result-container", "#result"):
                try:
                    loc = self.page.locator(".result-container:visible, #lookup-result:visible, .result:visible")
                    if await loc.count() > 0:
                        return loc.first
                except Exception:
                    pass
                
        # 2. Try accessible label matching if name is available
        if target.name:
            loc_exact = self.page.get_by_label(target.name, exact=True)
            if await loc_exact.count() > 0:
                return loc_exact.first
            loc = self.page.get_by_label(target.name, exact=False)
            if await loc.count() > 0:
                return loc.first
                
            # 3. Try semantic ID derived from name (e.g., 'Member ID' -> '#member-id')
            derived_id = f"#{target.name.lower().replace(' ', '-')}"
            try:
                loc = self.page.locator(derived_id)
                if await loc.count() > 0:
                    return loc.first
            except Exception:
                pass
        return None
        
    async def _find_by_text(self, target: TargetLocation) -> Optional[Any]:
        """Find element by text content."""
        text_val = target.name or target.value
        if text_val and ":" in text_val and not text_val.startswith(("#", ".")):
            text_val = text_val.split(":", 1)[1]
        if text_val:
            loc_exact = self.page.get_by_text(text_val, exact=True)
            if await loc_exact.count() > 0:
                return loc_exact.first
            loc = self.page.get_by_text(text_val, exact=False)
            if await loc.count() > 0:
                return loc.first
        return None
        
    def _find_by_test_id(self, target: TargetLocation) -> Optional[Any]:
        """Find element by test ID (Playwright get_by_test_id is synchronous)."""
        if target.value:
            return self.page.get_by_test_id(target.value).first
        return None
        
    def _find_by_xpath(self, target: TargetLocation) -> Optional[Any]:
        """Find element by XPath."""
        if target.value:
            return self.page.locator(f"xpath={target.value}").first
        return None
        
    def _find_by_css(self, target: TargetLocation) -> Optional[Any]:
        """Find element by CSS selector."""
        if target.value and not (":" in target.value and not target.value.startswith(("#", ".", "["))):
            return self.page.locator(target.value).first
        return None
        
    async def execute_action(self, action_type: ActionType, target: Optional[TargetLocation] = None, 
                           value: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Execute an action with Playwright auto-waiting."""
        try:
            # Handle non-targeted actions
            if action_type == ActionType.NAVIGATE:
                nav_url = value or (target.value if target else "")
                if not nav_url:
                    return False, "NAVIGATE requires a target URL"
                await self.navigate(nav_url)
                return True, None
                
            if action_type == ActionType.WAIT:
                wait_time = int(value) if value and str(value).isdigit() else 1000
                if target and target.value and not str(target.value).isdigit():
                    loc = await self.find_element(target)
                    if loc:
                        try:
                            await loc.wait_for(state="visible", timeout=wait_time)
                        except Exception:
                            pass
                # Always pause for the specified wait duration (e.g. for backend/async processing)
                await self.page.wait_for_timeout(wait_time)
                return True, None

            # Targeted actions require a target element
            if not target:
                return False, f"Target required for action {action_type.value}"
                
            element = await self.find_element(target)
            if not element:
                return False, f"Element not found: strategy={target.strategy.value} value='{target.value}'"
                
            if action_type == ActionType.CLICK:
                await element.click()
                logger.info("Click action executed")
            elif action_type == ActionType.TYPE:
                await element.fill(value or "")
                logger.info("Type action executed", value_length=len(value or ""))
            elif action_type == ActionType.EXTRACT:
                text = await element.inner_text()
                # Clean bullet characters or excess formatting if present
                clean_text = text.replace("●", "").strip()
                import hashlib
                val_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:8]
                logger.info("Extract action executed", length=len(clean_text), hash=val_hash)
                return True, clean_text
            elif action_type == ActionType.SELECT:
                await element.select_option(value)
                logger.info("Select action executed", value=value)
            elif action_type == ActionType.SUBMIT:
                await element.click()
                logger.info("Submit action executed")
            elif action_type == ActionType.CONFIRM:
                await element.click()
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
            element = await self.find_element(target, timeout=timeout)
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
            if text_contains and self.page:
                try:
                    text_loc = self.page.get_by_text(text_contains)
                    if await text_loc.count() > 0 and await text_loc.first.is_visible():
                        return True
                except Exception:
                    pass
            return False
            
        if text_contains:
            text = await element.inner_text()
            return text_contains.lower() in text.lower()
            
        return await element.is_visible()