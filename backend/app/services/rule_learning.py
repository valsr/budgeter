"""Real-time rule learning: after a manual category assignment, try to spot
a repeatable pattern and propose turning it into a rule (docs/requirements.md
§3.1's "final say stays with the user" principle — this only ever proposes,
never persists or auto-applies anything on its own).

Note: app/services/dedupe.py has its own unrelated MatchType enum
(EXACT/NEAR/NONE, for import dedup). This module uses app.models.rule's
MatchType (ANY/ALL) for rule construction — don't confuse the two.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.rule import ConditionField, ConditionOperator, MatchType
from app.models.transaction import Transaction, TransactionType
from app.services import categorization
from app.services.dedupe import normalize_name
from app.services.rule_engine import (
    Condition,
    RuleSpec,
    TransactionContext,
    evaluate_rule,
    find_matching_rule,
)

MIN_LEARNING_SAMPLE_SIZE = 3
TIER1_MIN_LCS_RATIO = 0.5
TIER2_MIN_LCS_RATIO = 0.3
MIN_LCS_LENGTH = 4

# Placeholder id/priority for ad-hoc, unpersisted rules run through
# evaluate_rule() during validation — those fields are never read by it.
_PLACEHOLDER = -1


@dataclass
class LearnedCondition:
    field: ConditionField
    operator: ConditionOperator
    value: str


@dataclass
class LearnedRuleCandidate:
    tier: int  # 1 (name only) or 2 (name + amount)
    match_type: MatchType
    conditions: list[LearnedCondition]
    target_category_id: int


def longest_common_substring(names: list[str]) -> str:
    """Longest substring common to every string in `names` (true multi-string
    LCS, not a prefix and not a pairwise reduction). Empty input, or no
    substring shared by all of them, returns "".
    """
    if not names:
        return ""
    if len(names) == 1:
        return names[0]

    anchor = min(names, key=len)
    n = len(anchor)
    for length in range(n, 0, -1):
        seen: set[str] = set()
        for start in range(0, n - length + 1):
            candidate = anchor[start : start + length]
            if candidate in seen:
                continue
            seen.add(candidate)
            if all(candidate in other for other in names):
                return candidate
    return ""


def _lcs_from_candidates(names: list[str], min_ratio: float) -> str | None:
    """Normalize, extract the LCS, and require it to clear BOTH the
    absolute floor and the ratio-of-shortest-name bar (not either/or).
    """
    normalized = [normalize_name(n) for n in names]
    shortest_len = min(len(n) for n in normalized)
    if shortest_len == 0:
        return None

    lcs = longest_common_substring(normalized).strip()
    if len(lcs) < MIN_LCS_LENGTH:
        return None
    if len(lcs) < min_ratio * shortest_len:
        return None
    return lcs


def build_candidate_rule(
    lcs: str,
    target_category_id: int,
    amount_condition: LearnedCondition | None = None,
) -> LearnedRuleCandidate:
    conditions = [LearnedCondition(field=ConditionField.NAME, operator=ConditionOperator.CONTAINS, value=lcs)]
    tier = 1
    if amount_condition is not None:
        conditions.append(amount_condition)
        tier = 2
    return LearnedRuleCandidate(
        tier=tier, match_type=MatchType.ALL, conditions=conditions, target_category_id=target_category_id
    )


def _candidate_to_rule_spec(candidate: LearnedRuleCandidate) -> RuleSpec:
    return RuleSpec(
        id=_PLACEHOLDER,
        match_type=candidate.match_type,
        priority=_PLACEHOLDER,
        target_category_id=candidate.target_category_id,
        conditions=[Condition(field=c.field, operator=c.operator, value=c.value) for c in candidate.conditions],
    )


def _all_categorized_single_split_transactions(db: Session) -> list[Transaction]:
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.splits))
        .where(Transaction.type == TransactionType.NORMAL)
    )
    transactions = db.execute(stmt).scalars().unique().all()
    return [t for t in transactions if len(t.splits) == 1 and t.splits[0].category_id is not None]


def find_validation_conflicts(db: Session, candidate: LearnedRuleCandidate) -> list[Transaction]:
    """Transactions the candidate rule would match but whose real category
    differs from the candidate's target -- i.e. saving this rule would
    misclassify them. Scans every categorized transaction system-wide, not
    just the same-category candidate pool: ground truth is the user's
    actual categorizations, not just same-name-pattern entries.
    """
    spec = _candidate_to_rule_spec(candidate)
    conflicts = []
    for txn in _all_categorized_single_split_transactions(db):
        split = txn.splits[0]
        if split.category_id == candidate.target_category_id:
            continue
        ctx = TransactionContext(date=txn.date, name=txn.name, account_id=txn.account_id, amount=float(split.amount))
        if evaluate_rule(spec, ctx):
            conflicts.append(txn)
    return conflicts


def separate_amount_clusters(
    target_amounts: list[float], opposing_amounts: list[float]
) -> tuple[float, ConditionOperator] | None:
    """Find a boundary (the midpoint between the two clusters' nearest
    edges) that cleanly separates target from opposing. Ties (equal
    max/min) don't count as separating -- a boundary sitting exactly on an
    observed value would misclassify that value itself.
    """
    if not target_amounts or not opposing_amounts:
        return None

    target_max, target_min = max(target_amounts), min(target_amounts)
    opposing_max, opposing_min = max(opposing_amounts), min(opposing_amounts)

    if target_max < opposing_min:
        return (target_max + opposing_min) / 2, ConditionOperator.LESS_THAN
    if opposing_max < target_min:
        return (opposing_max + target_min) / 2, ConditionOperator.GREATER_THAN
    return None


def find_learning_candidates(
    db: Session, category_id: int, exclude_transaction_id: int | None = None
) -> list[Transaction]:
    """Other whole-transaction categorizations already assigned to
    `category_id`: normal (non-transfer), single-split transactions.
    Mirrors categorization.list_eligible_for_suggestion's eligibility
    shape but selects a specific confirmed category instead of "uncategorized".
    """
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.splits))
        .where(Transaction.type == TransactionType.NORMAL)
    )
    if exclude_transaction_id is not None:
        stmt = stmt.where(Transaction.id != exclude_transaction_id)

    transactions = db.execute(stmt).scalars().unique().all()
    return [t for t in transactions if len(t.splits) == 1 and t.splits[0].category_id == category_id]


def filter_out_rule_matched(candidates: list[Transaction], rule_specs: list[RuleSpec]) -> list[Transaction]:
    """Drop any candidate that matches ANY existing rule's conditions at
    all, regardless of which category that rule targets -- already
    "claimed" by a rule, so it's redundant as training data for a new one.
    """
    if not rule_specs:
        return list(candidates)
    kept = []
    for txn in candidates:
        split = txn.splits[0]
        ctx = TransactionContext(date=txn.date, name=txn.name, account_id=txn.account_id, amount=float(split.amount))
        if find_matching_rule(rule_specs, ctx) is None:
            kept.append(txn)
    return kept


def learn_rule_for_category(
    db: Session, candidate_pool: list[Transaction], target_category_id: int
) -> LearnedRuleCandidate | None:
    """Top-level pipeline: tier 1 (name only) -> tier 2 (name + amount) ->
    None if neither produces a rule that doesn't conflict with existing
    categorized data.
    """
    if len(candidate_pool) < MIN_LEARNING_SAMPLE_SIZE:
        return None

    names = [t.name for t in candidate_pool]
    # abs(): AMOUNT conditions now compare magnitude only (rule_engine's
    # _field_value abs()es it), so the boundary this clusters toward must be
    # computed on magnitude too, or a rule learned from all-negative (or
    # all-positive) amounts would separate at a threshold on the wrong side
    # of zero and never fire.
    target_amounts = [abs(float(t.splits[0].amount)) for t in candidate_pool]

    tier1_lcs = _lcs_from_candidates(names, TIER1_MIN_LCS_RATIO)
    if tier1_lcs is not None:
        candidate = build_candidate_rule(tier1_lcs, target_category_id)
        if not find_validation_conflicts(db, candidate):
            return candidate
        # else: falls through to tier 2 below

    tier2_lcs = _lcs_from_candidates(names, TIER2_MIN_LCS_RATIO)
    if tier2_lcs is None:
        return None

    name_only_candidate = build_candidate_rule(tier2_lcs, target_category_id)
    opposing = find_validation_conflicts(db, name_only_candidate)
    if not opposing:
        # No conflicting cluster to derive an amount boundary from --
        # nothing for tier 2 to separate against, so it can't help here.
        return None

    opposing_amounts = [abs(float(t.splits[0].amount)) for t in opposing]
    boundary = separate_amount_clusters(target_amounts, opposing_amounts)
    if boundary is None:
        return None
    midpoint, operator = boundary

    amount_condition = LearnedCondition(field=ConditionField.AMOUNT, operator=operator, value=str(midpoint))
    candidate = build_candidate_rule(tier2_lcs, target_category_id, amount_condition=amount_condition)
    # Defense-in-depth, not expected to ever trigger: `opposing` already
    # covers every other-category transaction the (broader) name-only
    # condition matches, and `boundary` sits strictly beyond all of their
    # amounts -- so nothing that made it into `opposing` can also satisfy
    # this narrower 2-condition rule, and nothing outside `opposing` could
    # conflict without first failing the name-only check above.
    if find_validation_conflicts(db, candidate):
        return None
    return candidate


def confirm_matching_uncategorized(db: Session, rule_spec: RuleSpec) -> list[Transaction]:
    """One-time backfill for the learned-rule Add flow: directly sets
    category_id (not suggested_category_id) on every currently-uncategorized
    transaction the rule matches. Used only by POST /api/rules/learn --
    plain rule creation (POST /api/rules) stays suggest-only via
    categorization.run_categorization.
    """
    pool = categorization.list_eligible_for_suggestion(db, None)
    confirmed = []
    for txn in pool:
        split = txn.splits[0]
        ctx = TransactionContext(date=txn.date, name=txn.name, account_id=txn.account_id, amount=float(split.amount))
        if evaluate_rule(rule_spec, ctx):
            split.category_id = rule_spec.target_category_id
            split.suggested_category_id = None
            split.suggestion_source = None
            confirmed.append(txn)
    db.commit()
    return confirmed
