from reviews import active_spec_change_candidates, refresh_spec_candidate_lifecycle


def review(recommendation_id: str, *, version: int = 2) -> dict:
    return {
        "recommendation_id": recommendation_id,
        "review_model_version": version,
        "theme_driver": "Earnings / guidance momentum",
        "original_action": "buy_now",
        "original_confirmation_state": "overconfirmed",
        "expected_horizon": "1-2 weeks",
        "outcome": "failed",
        "spec_change_candidate": True,
    }


def test_legacy_candidate_is_superseded():
    reviews = [review("snow", version=1)]

    assert refresh_spec_candidate_lifecycle(reviews) is True
    assert reviews[0]["candidate_status"] == "superseded"
    assert active_spec_change_candidates(reviews) == []


def test_single_current_review_remains_observation():
    reviews = [review("one")]

    refresh_spec_candidate_lifecycle(reviews)

    assert reviews[0]["candidate_status"] == "observation"
    assert active_spec_change_candidates(reviews) == []


def test_two_independent_reviews_open_one_cohort():
    reviews = [review("one"), review("two")]
    reviews[0]["ticker"] = "ONE"
    reviews[1]["ticker"] = "TWO"

    refresh_spec_candidate_lifecycle(reviews)

    assert len(active_spec_change_candidates(reviews)) == 2
    assert {item["candidate_status"] for item in reviews} == {"open"}


def test_duplicate_ticker_reviews_remain_observations():
    reviews = [review("one"), review("two")]
    reviews[0]["ticker"] = "LTC"
    reviews[1]["ticker"] = "LTC"

    refresh_spec_candidate_lifecycle(reviews)

    assert active_spec_change_candidates(reviews) == []
    assert {item["candidate_status"] for item in reviews} == {"observation"}
