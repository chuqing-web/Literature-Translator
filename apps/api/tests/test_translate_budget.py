from app.services.translate import estimate_source_lines, translation_char_budget


def test_heading_budget_stays_near_source_length():
    src = "III. METHOD"
    budget = translation_char_budget(src, block_type="heading", bbox_h=14, font_size=11)
    assert budget <= len(src) + 20
    assert budget >= 6


def test_title_budget_is_tight():
    src = "Uncertainty-Aware Generalization Framework"
    budget = translation_char_budget(src, block_type="title", bbox_h=22, font_size=16)
    assert budget <= int(len(src) * 1.18) + 4 + 6  # allow capacity slack
    assert budget < len(src) * 1.5


def test_body_budget_allows_moderate_growth():
    src = (
        "State Space Models (SSM) describe systems in terms of their internal "
        "states and observations over time."
    )
    budget = translation_char_budget(src, block_type="text", bbox_h=48, font_size=10)
    assert budget >= len(src)
    assert budget <= int(len(src) * 1.3) + 24


def test_single_line_bbox_limits_capacity():
    src = "For observation yt, calculated using the observation matrix C, feedthrough matrix D, and observation noise vt,"
    budget = translation_char_budget(src, block_type="text", bbox_h=16, font_size=10)
    # One-line seat → tight budget, not a long paragraph expansion.
    assert estimate_source_lines(src, 16, 10) <= 2
    assert budget < len(src) * 1.45
