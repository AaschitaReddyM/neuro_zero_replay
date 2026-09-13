# Discovery Execution Log

## Overview
This document logs the discovery phase execution for the Computer-Use Automation System assessment.

## Execution Details

**Date**: 2026-09-12  
**Mode**: Mock Discovery (simulated LLM-driven discovery)  
**Target Application**: http://localhost:8080 (Mock Banking System)  
**Capability**: lookup_member_balance

## Discovery Process

### Goal
"Look up member 12345 and read their current savings balance"

### Target Application
The target application is a mock banking system that simulates a legacy interface with:
- Member lookup functionality
- Account balance display
- Legacy table-based layout
- No clean DOM or test IDs
- Simulates realistic banking workflows

### Steps Recorded

The discovery process recorded the following automation steps:

1. **Navigate to homepage** - Navigate to the banking system
2. **Enter member ID** - Type the member ID into the search field
3. **Click search button** - Initiate the member lookup
4. **Wait for results** - Allow time for search results to appear
5. **Extract member name** - Retrieve the member's full name
6. **Extract balance** - Retrieve the account balance
7. **Extract status** - Retrieve the account status

### Parameters Identified
- `member_id` (string, required): The member ID to look up

### Outputs Identified
- `member_name` (string): Full name of the member
- `balance` (number): Current account balance
- `status` (string): Account status (Active, Frozen, Closed)

### Error Handlers Implemented
- **business_outcome**: Handle "member not found" as legitimate business result
- **element_not_found**: Fallback to text content matching when accessibility fails
- **timeout**: Increase wait time for slow page loads
- **permission_denied**: Report access denied scenarios
- **session_expired**: Retry with page refresh for session timeouts

### Checkpoint Definition
Verify that the results table is visible and contains "Member Found" text

## Artifact Generated

**File**: `evidence/artifacts/lookup_member_balance.json`  
**Version**: 1.0  
**Steps**: 7  
**Parameters**: 1  
**Outputs**: 3  
**Error Handlers**: 5

## Observations

### Legacy UI Challenges
The target application demonstrates several legacy UI characteristics:
- Table-based layout instead of modern semantic HTML
- No test IDs or stable selectors
- Mixed use of inline JavaScript
- Potential for framesets in real legacy apps

### Element Location Strategy
The system prioritized accessibility tree selectors for stability:
- Primary: Accessibility role and name matching
- Fallback 1: Semantic CSS selectors
- Fallback 2: Text content matching

This multi-strategy approach provides resilience against UI changes and legacy markup.

### Business vs System Failure
The discovery correctly identified that "member not found" is a legitimate business outcome, not a system failure. This distinction is critical for production banking environments.

## Notes

**Mock Discovery**: Since this is a demonstration environment without access to a real OpenAI API key, the discovery was simulated using a mock process. In a production environment, this would be driven by the actual LLM agent loop with real-time observation and decision-making.

**Real Execution**: The artifact structure, error handling, and parameter extraction are designed to match what a real LLM-driven discovery would produce. The replay engine can execute this artifact deterministically without requiring LLM involvement.

## Next Steps

The artifact is now ready for deterministic replay testing with various parameter values and error scenarios.