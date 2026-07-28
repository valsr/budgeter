import datetime as dt

import pytest

from app.models.account import AccountType
from app.models.rule import ConditionField, ConditionOperator, MatchType
from app.services import accounts as accounts_svc
from app.services import categories as categories_svc
from app.services import rule_learning
from app.services import rules as rules_svc
from app.services import transactions as txn_svc
from app.services.rule_learning import (
    LearnedCondition,
    build_candidate_rule,
    confirm_matching_uncategorized,
    filter_out_rule_matched,
    find_learning_candidates,
    find_validation_conflicts,
    learn_rule_for_category,
    longest_common_substring,
    separate_amount_clusters,
)
from app.services.rule_engine import Condition, RuleSpec


class TestLongestCommonSubstring:
    def test_common_prefix_across_three(self):
        result = longest_common_substring(["mcdonalds 775", "mcdonalds 756", "mcdonalds 123"])
        assert result == "mcdonalds "

    def test_common_substring_not_anchored_at_start(self):
        result = longest_common_substring(["xxhelloxx", "yyhelloyy", "zzhellozz"])
        assert result == "hello"

    def test_no_common_substring_returns_empty(self):
        assert longest_common_substring(["abc", "xyz"]) == ""

    def test_single_string_returns_itself(self):
        assert longest_common_substring(["solo"]) == "solo"

    def test_empty_list_returns_empty(self):
        assert longest_common_substring([]) == ""


class TestLcsFromCandidates:
    def test_at_exact_ratio_and_floor_passes(self):
        # shortest=8 chars, 50% ratio -> threshold 4.0; lcs "abcd" is 4 chars: clears both bars exactly.
        lcs = rule_learning._lcs_from_candidates(["abcdxxxx", "abcdyyyy"], 0.5)
        assert lcs == "abcd"

    def test_below_ratio_fails_even_if_above_floor(self):
        # shortest=10 chars, 50% ratio -> threshold 5.0; lcs "abcd" is 4 chars: clears the 4-char floor but not the ratio.
        lcs = rule_learning._lcs_from_candidates(["abcdxxxxxx", "abcdyyyyyy"], 0.5)
        assert lcs is None

    def test_below_floor_fails_even_if_above_ratio(self):
        # shortest=4 chars, 50% ratio -> threshold 2.0; lcs "abc" is 3 chars: clears the ratio but not the 4-char floor.
        lcs = rule_learning._lcs_from_candidates(["abcx", "abcy"], 0.5)
        assert lcs is None

    def test_relaxed_ratio_finds_shorter_pattern(self):
        # same names as the ratio-failure case above, but at the relaxed 30% bar: threshold 3.0, "abcd" (4) clears it.
        lcs = rule_learning._lcs_from_candidates(["abcdxxxxxx", "abcdyyyyyy"], 0.3)
        assert lcs == "abcd"

    def test_name_that_normalizes_to_empty_never_anchors_a_match(self):
        # "###" strips to "" under normalize_name -- shortest_len is 0, so
        # there's no meaningful ratio to compare against.
        assert rule_learning._lcs_from_candidates(["###", "mcdonalds 775"], 0.5) is None


class TestSeparateAmountClusters:
    def test_target_below_opposing(self):
        result = separate_amount_clusters([9.99, 5.44, 6.55], [16.55, 16.44])
        assert result == ((9.99 + 16.44) / 2, ConditionOperator.LESS_THAN)

    def test_target_above_opposing(self):
        result = separate_amount_clusters([200.0, 250.0], [10.0, 40.0])
        assert result == ((40.0 + 200.0) / 2, ConditionOperator.GREATER_THAN)

    def test_interleaved_amounts_do_not_separate(self):
        assert separate_amount_clusters([10.0, 50.0], [30.0]) is None

    def test_tied_edges_do_not_separate(self):
        assert separate_amount_clusters([10.0, 20.0], [20.0, 30.0]) is None

    def test_empty_side_never_separates(self):
        assert separate_amount_clusters([], [10.0]) is None
        assert separate_amount_clusters([10.0], []) is None


@pytest.fixture()
def account(db_session):
    return accounts_svc.create_account(db_session, name="Main", type=AccountType.ASSET, opening_balance=1000)


@pytest.fixture()
def category(db_session):
    return categories_svc.create_category(db_session, "personal_dining")


@pytest.fixture()
def other_category(db_session):
    return categories_svc.create_category(db_session, "shared_dining")


class TestFindLearningCandidates:
    def test_matches_only_single_split_same_category(self, db_session, account, category, other_category):
        target = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "McDonalds #1", [(category.id, -10.0)]
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 2), "McDonalds #2", [(other_category.id, -10.0)]
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 3), "Costco", [(category.id, -60.0), (other_category.id, -10.0)]
        )
        txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 4), "Uncategorized", [(None, -5.0)])

        result = find_learning_candidates(db_session, category.id)
        assert [t.id for t in result] == [target.id]

    def test_excludes_transfers(self, db_session, account, category):
        other = accounts_svc.create_account(db_session, name="Card", type=AccountType.LIABILITY, opening_balance=0)
        txn_svc.create_transfer(db_session, account.id, other.id, dt.date(2026, 1, 1), "Payment", 10.0)
        assert find_learning_candidates(db_session, category.id) == []

    def test_respects_exclude_transaction_id(self, db_session, account, category):
        txn1 = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "McDonalds #1", [(category.id, -10.0)]
        )
        txn2 = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 2), "McDonalds #2", [(category.id, -10.0)]
        )
        result = find_learning_candidates(db_session, category.id, exclude_transaction_id=txn1.id)
        assert [t.id for t in result] == [txn2.id]


class TestFilterOutRuleMatched:
    def test_excludes_candidates_matching_any_rule(self, db_session, account, category, other_category):
        rules_svc.create_rule(
            db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "starbucks")], other_category.id
        )
        claimed = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "Starbucks #1", [(category.id, -5.0)]
        )
        free = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 2), "McDonalds #1", [(category.id, -5.0)]
        )
        pool = [claimed, free]
        rule_specs = rules_svc.rules_to_specs(rules_svc.list_rules(db_session))

        result = filter_out_rule_matched(pool, rule_specs)
        assert [t.id for t in result] == [free.id]

    def test_no_rules_keeps_everything(self, db_session, account, category):
        txn = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "McDonalds #1", [(category.id, -5.0)]
        )
        assert filter_out_rule_matched([txn], []) == [txn]


class TestFindValidationConflicts:
    def test_finds_transactions_matched_but_wrong_category(self, db_session, account, category, other_category):
        conflicting = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "McDonalds #999", [(other_category.id, -5.0)]
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 2), "McDonalds #1", [(category.id, -5.0)]
        )
        candidate = build_candidate_rule("mcdonalds", category.id)

        conflicts = find_validation_conflicts(db_session, candidate)
        assert [t.id for t in conflicts] == [conflicting.id]

    def test_no_conflict_when_all_matches_share_target_category(self, db_session, account, category):
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "McDonalds #1", [(category.id, -5.0)]
        )
        candidate = build_candidate_rule("mcdonalds", category.id)
        assert find_validation_conflicts(db_session, candidate) == []


class TestLearnRuleForCategory:
    def _mcdonalds_txn(self, db_session, account, category, suffix, day=1):
        return txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, day), f"McDonalds #{suffix}", [(category.id, -10.0)]
        )

    def test_below_minimum_sample_size_returns_none(self, db_session, account, category):
        self._mcdonalds_txn(db_session, account, category, "775", day=1)
        self._mcdonalds_txn(db_session, account, category, "756", day=2)
        pool = find_learning_candidates(db_session, category.id)
        assert len(pool) == 2
        assert learn_rule_for_category(db_session, pool, category.id) is None

    def test_tier1_success(self, db_session, account, category):
        self._mcdonalds_txn(db_session, account, category, "775", day=1)
        self._mcdonalds_txn(db_session, account, category, "756", day=2)
        self._mcdonalds_txn(db_session, account, category, "123", day=3)
        pool = find_learning_candidates(db_session, category.id)

        result = learn_rule_for_category(db_session, pool, category.id)
        assert result is not None
        assert result.tier == 1
        assert result.match_type == MatchType.ALL
        assert result.conditions == [LearnedCondition(ConditionField.NAME, ConditionOperator.CONTAINS, "mcdonalds")]
        assert result.target_category_id == category.id

    def test_tier1_conflict_falls_through_to_tier2(self, db_session, account, category, other_category):
        # target cluster: low-amount "amazon" purchases -> category
        for i, amount in enumerate([9.99, 5.44, 6.55]):
            txn_svc.create_transaction(
                db_session, account.id, dt.date(2026, 1, i + 1), f"Amazon Mktp #{i}", [(category.id, -amount)]
            )
        # opposing: a high-amount "amazon" purchase in a different category -- forces tier 1 to conflict
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 10), "Amazon Mktp #99", [(other_category.id, -16.44)]
        )
        pool = find_learning_candidates(db_session, category.id)

        result = learn_rule_for_category(db_session, pool, category.id)
        assert result is not None
        assert result.tier == 2
        assert len(result.conditions) == 2
        name_cond, amount_cond = result.conditions
        assert name_cond.field == ConditionField.NAME
        assert amount_cond.field == ConditionField.AMOUNT
        # Stored amounts are negative (withdrawals): -9.99 is numerically
        # GREATER than -16.44, so the smaller-spend (target) cluster sits
        # above the boundary, not below it.
        assert amount_cond.operator == ConditionOperator.GREATER_THAN
        midpoint = float(amount_cond.value)
        assert -16.44 < midpoint < -9.99

    def test_tier2_fails_when_amounts_interleave(self, db_session, account, category, other_category):
        for i, amount in enumerate([9.99, 30.0, 6.55]):
            txn_svc.create_transaction(
                db_session, account.id, dt.date(2026, 1, i + 1), f"Amazon Mktp #{i}", [(category.id, -amount)]
            )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 10), "Amazon Mktp #99", [(other_category.id, -16.44)]
        )
        pool = find_learning_candidates(db_session, category.id)
        assert learn_rule_for_category(db_session, pool, category.id) is None

    def test_no_opposing_cluster_means_no_tier2(self, db_session, account, category):
        # names too dissimilar for tier 1 (50%), similar enough for tier 2 (30%), but no
        # conflicting category anywhere -- nothing to derive an amount boundary from.
        names = ["Zebra Shop AAAA", "Zebra Diner BBBB", "Zebra Cafe CCCC"]
        for i, name in enumerate(names):
            txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, i + 1), name, [(category.id, -10.0)])
        pool = find_learning_candidates(db_session, category.id)
        assert learn_rule_for_category(db_session, pool, category.id) is None

    def test_no_common_pattern_at_all_fails_both_tiers(self, db_session, account, category):
        # disjoint letter sets -- share no substring whatsoever, so even the
        # relaxed 30% tier-2 bar finds nothing to work with.
        names = ["qwerty", "asdfgh", "zxcvbn"]
        for i, name in enumerate(names):
            txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, i + 1), name, [(category.id, -10.0)])
        pool = find_learning_candidates(db_session, category.id)
        assert learn_rule_for_category(db_session, pool, category.id) is None

    def test_tier2_reject_when_2_condition_rule_still_conflicts(self, db_session, account, category, other_category):
        third_category = categories_svc.create_category(db_session, "business_meals")
        for i, amount in enumerate([9.99, 5.44, 6.55]):
            txn_svc.create_transaction(
                db_session, account.id, dt.date(2026, 1, i + 1), f"Amazon Mktp #{i}", [(category.id, -amount)]
            )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 10), "Amazon Mktp #99", [(other_category.id, -16.44)]
        )
        # this one matches the name pattern AND falls on the "target" side of the midpoint,
        # but belongs to a third category entirely -- the 2-condition rule still misclassifies it.
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 11), "Amazon Mktp #50", [(third_category.id, -7.00)]
        )
        pool = find_learning_candidates(db_session, category.id)
        assert learn_rule_for_category(db_session, pool, category.id) is None


class TestConfirmMatchingUncategorized:
    def test_confirms_matching_and_leaves_others_untouched(self, db_session, account, category, other_category):
        matching = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "McDonalds #1", [(None, -5.0)]
        )
        non_matching = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 2), "Starbucks", [(None, -5.0)]
        )
        already_categorized = txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 3), "McDonalds #2", [(other_category.id, -5.0)]
        )
        rule_spec = RuleSpec(
            id=-1,
            match_type=MatchType.ALL,
            priority=-1,
            target_category_id=category.id,
            conditions=[Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "mcdonalds")],
        )

        confirmed = confirm_matching_uncategorized(db_session, rule_spec)
        assert [t.id for t in confirmed] == [matching.id]

        refreshed_match = txn_svc.get_transaction(db_session, matching.id)
        assert refreshed_match.splits[0].category_id == category.id
        assert refreshed_match.splits[0].suggested_category_id is None
        assert refreshed_match.splits[0].suggestion_source is None

        refreshed_non_match = txn_svc.get_transaction(db_session, non_matching.id)
        assert refreshed_non_match.splits[0].category_id is None

        refreshed_already = txn_svc.get_transaction(db_session, already_categorized.id)
        assert refreshed_already.splits[0].category_id == other_category.id
