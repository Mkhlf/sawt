#!/usr/bin/env python3
"""
Agent Evaluation - Uses terminal to test agent like a real user.

Usage:
    # Run all scenarios
    python tests/run_eval.py

    # Run specific scenario
    python tests/run_eval.py --scenario simple_pickup

    # Run with LLM judges for scoring
    python tests/run_eval.py --judges gpt-5.2 claude-4.5-opus

    # Skip judging (faster)
    python tests/run_eval.py --no-judge

    # Verbose mode
    python tests/run_eval.py -v
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluator.terminal_runner import TerminalRunner
from evaluator.customer_llm import get_persona, get_all_personas
from evaluator.judge import LLMJudge, EvaluationResult, DEFAULT_JUDGES
from evaluator.report import (
    generate_markdown_report,
    generate_json_report,
    save_individual_result,
)
from evaluator.runner import ScenarioResult


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run agent evaluation tests via terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        help="Run a specific scenario by ID (e.g., simple_pickup, simple_delivery)",
    )
    
    parser.add_argument(
        "--judges", "-j",
        nargs="+",
        default=DEFAULT_JUDGES,
        help=f"Judge models to use (default: {DEFAULT_JUDGES})",
    )
    
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM evaluation (only run scenarios)",
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="tests/logs",
        help="Output directory for results",
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout per scenario in seconds (default: 120)",
    )
    
    return parser.parse_args()


async def run_evaluation(args):
    """Main evaluation function using terminal runner."""
    
    # Get API key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY not set")
        sys.exit(1)
    
    # Get scenarios
    if args.scenario:
        persona = get_persona(args.scenario)
        if not persona:
            all_personas = get_all_personas()
            print(f"❌ Scenario '{args.scenario}' not found")
            print(f"   Available: {[p.scenario_id for p in all_personas]}")
            sys.exit(1)
        scenario_ids = [args.scenario]
    else:
        all_personas = get_all_personas()
        scenario_ids = [p.scenario_id for p in all_personas]
    
    print(f"\n{'='*60}")
    print(f"🧪 Agent Evaluation (Terminal Mode)")
    print(f"{'='*60}")
    print(f"📋 Scenarios: {len(scenario_ids)}")
    print(f"🔍 Judges: {', '.join(args.judges) if not args.no_judge else 'None'}")
    print(f"📁 Output: {args.output_dir}")
    print(f"{'='*60}\n")
    
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize runner and judge
    runner = TerminalRunner(verbose=args.verbose, timeout=args.timeout)
    judge = LLMJudge(api_key, judges=args.judges) if not args.no_judge else None
    
    # Run scenarios
    scenario_results: list[ScenarioResult] = []
    evaluation_results: list[EvaluationResult] = []
    
    for i, scenario_id in enumerate(scenario_ids):
        persona = get_persona(scenario_id)
        
        print(f"\n[{i+1}/{len(scenario_ids)}] {scenario_id}")
        print(f"    Goal: {persona.goal[:50]}...")
        
        try:
            result = await runner.run_scenario_via_terminal(scenario_id)
            scenario_results.append(result)
            
            status = "✅" if result.success else "❌"
            print(f"    Status: {status} ({result.duration_ms}ms)")
            print(f"    Turns: {len(result.messages) // 2}")
            
            # Evaluate with judges
            if judge and result.success:
                print(f"    Judging...")
                eval_result = await judge.evaluate(result, persona.success_criteria)
                evaluation_results.append(eval_result)
                print(f"    Score: {eval_result.average_score:.1f}/10")
            else:
                evaluation_results.append(EvaluationResult(
                    scenario_id=scenario_id,
                    scenario_name=persona.goal[:30],
                    judge_results=[],
                    average_score=0.0,
                ))
            
            # Save result
            save_individual_result(result, evaluation_results[-1], output_dir)
            
        except Exception as e:
            print(f"    ❌ Error: {e}")
            failed = ScenarioResult(
                scenario_id=scenario_id,
                scenario_name=persona.goal[:30],
                messages=[],
                final_order=None,
                final_session={},
                duration_ms=0,
                success=False,
                error=str(e),
            )
            scenario_results.append(failed)
            evaluation_results.append(EvaluationResult(
                scenario_id=scenario_id,
                scenario_name=scenario_id,
                judge_results=[],
                average_score=0.0,
            ))
    
    # Generate reports
    print(f"\n{'='*60}")
    print("📊 Reports")
    print(f"{'='*60}")
    
    md_report = generate_markdown_report(scenario_results, evaluation_results, output_dir / "report.md")
    print(f"📄 {md_report}")
    
    json_report = generate_json_report(scenario_results, evaluation_results, output_dir / "report.json")
    print(f"📄 {json_report}")
    
    # Summary
    print(f"\n{'='*60}")
    print("📈 Summary")
    print(f"{'='*60}")
    
    successful = sum(1 for r in scenario_results if r.success)
    avg_score = sum(e.average_score for e in evaluation_results) / len(evaluation_results) if evaluation_results else 0
    
    print(f"✅ Passed: {successful}/{len(scenario_ids)}")
    if not args.no_judge:
        print(f"📊 Average Score: {avg_score:.1f}/10")
    print(f"📁 Results: {output_dir}")
    print(f"{'='*60}\n")


def main():
    args = parse_args()
    asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
