"""Secrets are replaced before anything is saved or shown (rca/redaction.py)."""

from rca.redaction import MARK, redact


def test_keys_tokens_and_passwords_are_replaced_in_any_structure():
    value = {"error": "key gsk_abcdefghijklmnop1234, Bearer abc.def.ghi12345",
             "items": ["password=hunter22", "api_key: xyz123", "org_01kv7s5kaef5zrph"], "count": 3}

    assert redact(value) == {"error": f"key {MARK}, {MARK}", "items": [f"password={MARK}", f"api_key: {MARK}", MARK],
                             "count": 3}


def test_ordinary_text_of_an_investigation_is_left_alone():
    text = "Connection pool timeouts on CI-PAYMENT-DB after CHG-2026-00871; token bucket of the gateway is full."

    assert redact(text) == text
