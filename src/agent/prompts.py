from __future__ import annotations

"""Prompt templates used by the AuDRA-Rad agent."""


SYSTEM_PROMPT = """You are AuDRA-Rad, an AI assistant for radiology follow-up recommendations.

Your role:
- Analyze radiology reports for actionable findings
- Match findings to evidence-based guidelines (Fleischner, ACR)
- Recommend appropriate follow-up imaging or referrals
- Flag uncertain cases for radiologist review

Guidelines:
- Always cite which guideline you're applying
- Consider patient risk factors (smoking, age, comorbidities)
- Be conservative - when uncertain, flag for human review
- Never recommend "no follow-up" for suspicious findings
- Explain your reasoning clearly

You have access to these tools:
- parse_report: Extract findings from report text
- retrieve_guidelines: Search medical guidelines
- match_recommendation: Determine appropriate follow-up
- validate_safety: Check for contraindications
- generate_task: Create follow-up order

Think step-by-step. Use chain-of-thought reasoning.
"""


PARSE_PROMPT = """Extract all clinically significant findings from this radiology report.

Report:
{report_text}

For each finding, extract:
- Type (nodule, mass, lesion, opacity)
- Size in mm
- Anatomical location
- Characteristics (solid, ground-glass, spiculated, calcified, etc.)

Return as JSON array:
[
  {{
    "type": "ground-glass nodule",
    "size_mm": 3,
    "location": "RUL",
    "characteristics": ["ground-glass", "solitary"],
    "context": "relevant surrounding text"
  }}
]

If no significant findings, return empty array: []
"""


ANALYZE_PROMPT = """Given this finding, determine what follow-up is needed.

Finding:
{finding_json}

Patient Context:
{patient_context}

Relevant Guidelines:
{guidelines_list}

Analysis:
1. Which guideline applies to this finding?
2. What are the key decision factors (size, characteristics, risk)?
3. What follow-up is recommended?
4. What is the timeframe?
5. What is the urgency level?

Think through each step, then provide recommendation as JSON:
{{
  "follow_up_type": "CT Chest without contrast",
  "timeframe_months": 6,
  "urgency": "routine",
  "reasoning": "Your step-by-step explanation",
  "citation": "Fleischner 2017, Subsolid Nodules <6mm"
}}
"""


VALIDATE_PROMPT = """Review this recommendation for safety and appropriateness.

Recommendation:
{recommendation_json}

Original Finding:
{finding_json}

Guidelines:
{guidelines_list}

Questions:
1. Does the recommendation align with the cited guideline?
2. Are there any contraindications or safety concerns?
3. Should this be flagged for radiologist review?

Flag if:
- Finding is >30mm (large mass)
- Characteristics are suspicious (spiculated, irregular borders)
- Recommendation doesn't clearly match a guideline
- Patient has high-risk factors not addressed

Return JSON:
{{
  "is_safe": true/false,
  "concerns": ["list any concerns"],
  "requires_human_review": true/false,
  "explanation": "reasoning"
}}
"""


REACT_PROMPT = """You are processing a radiology report. Use ReAct pattern: Thought → Action → Observation.

Current State:
{state_summary}

Available Actions:
- parse_report
- retrieve_guidelines (for a specific finding)
- match_recommendation (for a specific finding)
- validate_safety (for a recommendation)
- generate_task (create follow-up order)
- FINISH (all tasks complete)

Thought: [Reason about what to do next]
Action: [Choose one action]
Action Input: [Provide input for the action]

Continue until all findings have follow-up tasks or are flagged for review.
"""


def format_prompt(template: str, **kwargs: str) -> str:
    """Fill in template placeholders with provided values."""

    return template.format(**kwargs)
