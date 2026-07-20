from teachback.learning_safety import personal_decision_boundary


def test_medical_goal_declines_personal_diagnosis_but_allows_academic_question() -> None:
    assert personal_decision_boundary("medical", "Can you diagnose my rash and tell me what treatment to take?")
    assert personal_decision_boundary("medical", "Explain the academic distinction between diagnosis and prognosis.") is None


def test_finance_goal_declines_personal_trade_but_allows_academic_question() -> None:
    assert personal_decision_boundary("finance", "Should I buy this stock for my portfolio today?")
    assert personal_decision_boundary("finance", "Explain how a diversified portfolio changes risk exposure.") is None
