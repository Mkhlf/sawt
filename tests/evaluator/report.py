"""
Report generator - creates evaluation reports.

Generates markdown and JSON reports from evaluation results.
"""

import json
from datetime import datetime
from pathlib import Path
from dataclasses import asdict
from typing import Any

from .runner import ScenarioResult
from .judge import EvaluationResult


def _score_emoji(score: float) -> str:
    """Get emoji for score range."""
    if score >= 8:
        return "✅"
    elif score >= 6:
        return "⚠️"
    else:
        return "❌"


def generate_markdown_report(
    scenario_results: list[ScenarioResult],
    evaluation_results: list[EvaluationResult],
    output_path: Path,
) -> Path:
    """
    Generate a markdown report from evaluation results.
    
    Args:
        scenario_results: Results from running scenarios
        evaluation_results: Scores from LLM judges
        output_path: Where to save the report
        
    Returns:
        Path to the generated report
    """
    lines = [
        "# Agent Evaluation Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## Summary",
        "",
    ]
    
    # Calculate overall stats
    total_scenarios = len(scenario_results)
    successful = sum(1 for r in scenario_results if r.success)
    avg_score = sum(e.average_score for e in evaluation_results) / len(evaluation_results) if evaluation_results else 0
    
    lines.extend([
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Scenarios Run | {total_scenarios} |",
        f"| Successful | {successful}/{total_scenarios} |",
        f"| Average Score | {avg_score:.1f}/10 {_score_emoji(avg_score)} |",
        "",
        "---",
        "",
        "## Scenario Results",
        "",
    ])
    
    # Table header
    lines.extend([
        "| Scenario | Status | Avg Score | Task | Efficiency | Correctness | Arabic | Errors |",
        "|----------|--------|-----------|------|------------|-------------|--------|--------|",
    ])
    
    # Scenario rows
    for sr, er in zip(scenario_results, evaluation_results):
        status = "✅" if sr.success else "❌"
        avg = f"{er.average_score:.1f}"
        
        # Get average across judges for each criterion
        if er.judge_results:
            task = sum(jr.scores.task_completion for jr in er.judge_results) / len(er.judge_results)
            eff = sum(jr.scores.efficiency for jr in er.judge_results) / len(er.judge_results)
            corr = sum(jr.scores.correctness for jr in er.judge_results) / len(er.judge_results)
            arab = sum(jr.scores.arabic_quality for jr in er.judge_results) / len(er.judge_results)
            err = sum(jr.scores.error_handling for jr in er.judge_results) / len(er.judge_results)
        else:
            task = eff = corr = arab = err = 0
            
        lines.append(
            f"| {sr.scenario_name} | {status} | {avg} | {task:.1f} | {eff:.1f} | {corr:.1f} | {arab:.1f} | {err:.1f} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## Detailed Results",
        "",
    ])
    
    # Detailed results for each scenario
    for sr, er in zip(scenario_results, evaluation_results):
        lines.extend([
            f"### {sr.scenario_name}",
            "",
            f"**Status:** {'✅ Success' if sr.success else '❌ Failed'}  ",
            f"**Duration:** {sr.duration_ms}ms  ",
            f"**Average Score:** {er.average_score:.1f}/10",
            "",
        ])
        
        # Final state
        lines.extend([
            "#### Final State",
            "```json",
            json.dumps(sr.final_session, ensure_ascii=False, indent=2),
            "```",
            "",
        ])
        
        # Judge comments
        if er.judge_results:
            lines.append("#### Judge Comments")
            lines.append("")
            for jr in er.judge_results:
                lines.extend([
                    f"**{jr.model}** (Avg: {jr.scores.average:.1f})",
                    f"> {jr.scores.comments}",
                    "",
                ])
        
        lines.append("---")
        lines.append("")
    
    # Write report
    report_content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_content, encoding="utf-8")
    
    return output_path


def generate_json_report(
    scenario_results: list[ScenarioResult],
    evaluation_results: list[EvaluationResult],
    output_path: Path,
) -> Path:
    """
    Generate a JSON report from evaluation results.
    
    Args:
        scenario_results: Results from running scenarios
        evaluation_results: Scores from LLM judges
        output_path: Where to save the report
        
    Returns:
        Path to the generated report
    """
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_scenarios": len(scenario_results),
            "successful": sum(1 for r in scenario_results if r.success),
            "average_score": sum(e.average_score for e in evaluation_results) / len(evaluation_results) if evaluation_results else 0,
        },
        "scenarios": [],
    }
    
    for sr, er in zip(scenario_results, evaluation_results):
        report["scenarios"].append({
            "scenario": sr.to_dict(),
            "evaluation": er.to_dict(),
        })
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return output_path


def save_individual_result(
    scenario_result: ScenarioResult,
    evaluation_result: EvaluationResult,
    output_dir: Path,
) -> Path:
    """
    Save individual scenario result to a file.
    
    Args:
        scenario_result: Result from running scenario
        evaluation_result: Scores from judges
        output_dir: Directory to save results
        
    Returns:
        Path to saved file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{scenario_result.scenario_id}_{timestamp}.json"
    filepath = output_dir / filename
    
    result = {
        "scenario": scenario_result.to_dict(),
        "evaluation": evaluation_result.to_dict(),
    }
    
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return filepath
