# Agent Evaluation Framework

This directory contains the testing framework for the Arabic Restaurant Ordering Agent. It uses a terminal-based runner to simulate user interactions (LLM-customer) with our agents and then judges (LLMs) the performance of the agents.

## Overview

The evaluation framework exercises the agent's full flow—greeting, location collection, ordering, and checkout—using defined user personas and scenarios.

## Quick Start

Run the full evaluation suite:

```bash
python tests/run_eval.py
```

## detailed Usage

> `OPENROUTER_API_KEY` is required to run the whole evaluation suite.

### 1. Run All Scenarios
Executes all defined scenarios in `tests/evaluator/customer_llm.py`:

```bash
python tests/run_eval.py
```

### 2. Run Specific Scenario
Run a single test case by its ID:

```bash
python tests/run_eval.py --scenario simple_pickup
# OR
python tests/run_eval.py --scenario simple_delivery
```

### 3. Run with LLM Judges

```bash
python tests/run_eval.py --judges gpt-4 claude-3-opus
```

To skip judging (faster execution):
```bash
python tests/run_eval.py --no-judge
```

### 4. Verbose Logging
See detailed message exchanges and tool calls:

```bash
python tests/run_eval.py -v
```

## Output

Results are saved to `tests/logs/YYYYMMDD_HHMMSS/`:
- **report.md**: Human-readable summary of results.
- **report.json**: Machine-readable full results.
- **[scenario_id].json**: Individual trace for each test run.