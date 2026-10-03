"""Command-line entry point.

Examples:
    python main.py                                   # baseline scenario, multi-agent, mock mode
    python main.py --scenario budget_reduction
    python main.py --mode baseline                   # single-agent baseline
    python main.py --mode compare --scenario all     # MAS vs single agent, every scenario
    python main.py --llm                             # use an LLM if OPENAI_API_KEY is set
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agents import create_agents
from config import DEFAULT_MAX_ROUNDS, OUTPUTS_DIR, load_settings
from environment import ClinicalTrialEnvironment
from llm import ChatClient, build_client
from logger import LINE, EventLogger, format_result, setup_logging
from models import ScenarioResult
from negotiation import NegotiationEngine
from scenarios import SCENARIOS, load_scenario
from single_agent import SingleAgentPlanner, format_single_agent


def run_multi_agent(scenario_key: str, llm_client: ChatClient | None = None,
                    max_rounds: int = DEFAULT_MAX_ROUNDS, output_dir: Path | None = OUTPUTS_DIR) -> ScenarioResult:
    """Run one multi-agent negotiation and (optionally) save JSON/TXT/JSONL outputs."""
    scenario = load_scenario(scenario_key)
    environment = ClinicalTrialEnvironment(scenario)
    agents = create_agents(environment, llm_client)
    events = EventLogger()
    engine = NegotiationEngine(environment, agents, events, max_rounds, "llm" if llm_client else "mock")
    result = engine.run(scenario)
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{scenario_key}.json").write_text(json.dumps(result.to_dict(), indent=2, default=str),
                                                          encoding="utf-8")
        (output_dir / f"{scenario_key}.txt").write_text(format_result(result), encoding="utf-8")
        events.save(output_dir / f"{scenario_key}_events.jsonl")
    return result


def run_single_agent(scenario_key: str, llm_client: ChatClient | None = None,
                     output_dir: Path | None = OUTPUTS_DIR) -> dict[str, Any]:
    result = SingleAgentPlanner(load_scenario(scenario_key), llm_client).plan()
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        serializable = {k: v for k, v in result.items() if not k.startswith("_")}
        (output_dir / f"{scenario_key}_single_agent.json").write_text(json.dumps(serializable, indent=2),
                                                                       encoding="utf-8")
    return result


def format_comparison(rows: list[tuple[str, ScenarioResult, dict[str, Any]]]) -> str:
    header = f"{'Scenario':<22}{'MAS status':<14}{'Rounds':>7}{'MAS viol.':>10}{'Single viol.':>14}"
    out = [LINE, "MULTI-AGENT vs SINGLE-AGENT", LINE, header, "-" * len(header)]
    for key, mas, single in rows:
        out.append(f"{key:<22}{mas.status.value:<14}{mas.metrics['rounds']:>7}"
                   f"{mas.metrics['constraint_violations']:>10}{single['constraint_violations']:>14}")
    out += ["", "Single agent: 1 reasoning process, blended objective, saw ALL private constraints, no vetoes.",
            "Multi-agent : 4 independent processes, private constraints, explicit negotiation, vetoes.", LINE]
    return "\n".join(out)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-agent clinical trial protocol negotiation with hidden objectives "
                    "(academic proof-of-concept, synthetic data only).")
    parser.add_argument("--mode", choices=["multi-agent", "baseline", "compare"], default="multi-agent",
                        help="multi-agent negotiation, single-agent baseline, or both side by side")
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="baseline",
                        help="which scenario to run (default: baseline)")
    parser.add_argument("--llm", action="store_true", help="use an LLM for agent reasoning (needs OPENAI_API_KEY)")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS, help="round limit (default 10)")
    parser.add_argument("--no-transcript", action="store_true", help="hide the public transcript")
    parser.add_argument("--summary", action="store_true", help="print only the final result section")
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR, help="where results are saved")
    parser.add_argument("--verbose", action="store_true", help="debug logging of every event")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    settings = load_settings()
    client = build_client(settings, args.llm)
    print(f"Reasoning mode: {'LLM (' + settings.model + ')' if client else 'MOCK (deterministic)'}")
    keys = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    comparison: list[tuple[str, ScenarioResult, dict[str, Any]]] = []

    for key in keys:
        if args.mode in ("multi-agent", "compare"):
            result = run_multi_agent(key, client, args.max_rounds, args.output_dir)
            text = format_result(result, show_transcript=not (args.no_transcript or args.summary))
            if args.summary:
                text = text[text.index("FINAL RESULT") - len(LINE) - 1:]
            print(text)
        if args.mode in ("baseline", "compare"):
            single = run_single_agent(key, client, args.output_dir)
            print(format_single_agent(single))
            if args.mode == "compare":
                comparison.append((key, result, single))
    if comparison:
        print(format_comparison(comparison))
    print(f"\nOutputs saved to: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
