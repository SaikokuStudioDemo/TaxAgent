"""
Rule Evaluation Service
Evaluates approval_rules against a document (receipt or invoice)
and returns the first matching rule_id and its steps.
"""
from typing import Optional, Tuple
from bson import ObjectId
from app.db.mongodb import get_database


def _eval_condition(field: str, operator: str, rule_value, doc_value) -> bool:
    """Evaluate a single condition against a document field value."""
    try:
        ops = {
            ">=": lambda a, b: a >= b,
            ">":  lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            "<":  lambda a, b: a < b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        fn = ops.get(operator)
        return fn(doc_value, rule_value) if fn else False
    except Exception:
        return False


async def evaluate_approval_rules(
    corporate_id: str,
    document_type: str,  # "receipt" | "received_invoice" | "issued_invoice"
    document: dict,
) -> Tuple[Optional[str], list]:
    """
    Find the first active approval rule that matches the given document.

    Priority:
    1. If document has project_id → look for a project-specific rule first
    2. Otherwise, evaluate normal document-type rules (highest amount threshold first)

    Returns:
        (rule_id, steps) if a match is found, else (None, [])
    """
    db = get_database()

    # Priority 1: project-specific rule
    project_id = document.get("project_id")
    if project_id:
        proj_rule = await db["approval_rules"].find_one({
            "corporate_id": corporate_id,
            "applies_to": "project",
            "project_id": project_id,
            "active": True,
        })
        if proj_rule:
            return str(proj_rule["_id"]), proj_rule.get("steps", [])
        # No project rule found → fall through to normal rules (may result in no match → 承認不要)

    cursor = db["approval_rules"].find({
        "corporate_id": corporate_id,
        "applies_to": document_type,
        "active": True,
    })
    rules = await cursor.to_list(length=200)

    # Sort rules: highest amount condition first for specificity
    def sort_key(rule):
        for cond in rule.get("conditions", []):
            if cond.get("field") == "amount":
                return cond.get("value", 0)
        return 0

    rules.sort(key=sort_key, reverse=True)

    for rule in rules:
        conditions = rule.get("conditions", [])
        all_match = True
        for cond in conditions:
            field = cond.get("field", "")
            # "always" means this rule applies unconditionally — skip evaluation
            if field == "always":
                continue
            operator = cond.get("operator", ">=")
            rule_val = cond.get("value")
            doc_val = document.get(field) or document.get("total_amount") if field == "amount" else document.get(field)
            if doc_val is None or not _eval_condition(field, operator, rule_val, doc_val):
                all_match = False
                break
        if all_match:
            return str(rule["_id"]), rule.get("steps", [])

    return None, []


async def get_rule_steps(rule_id: str) -> list:
    """Return the steps of a given rule_id."""
    db = get_database()
    try:
        rule = await db["approval_rules"].find_one({"_id": ObjectId(rule_id)})
        return rule.get("steps", []) if rule else []
    except Exception:
        return []
