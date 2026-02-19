"""
Tests for QueryClassifier.
"""
import pytest

from app.services.query_classifier import QueryType, classify, extract_tag_tokens


# ── TAG_LOOKUP ────────────────────────────────────────────────────────────────

def test_classify_explicit_plc_tag():
    assert classify("What does CONV_RUN do?") == QueryType.TAG_LOOKUP


def test_classify_multiple_tags():
    assert classify("How are CONV_RUN and PUMP_SPD related?") == QueryType.TAG_LOOKUP


def test_classify_tag_lookup_with_question_words():
    assert classify("Describe the tag MOTOR_FLT") == QueryType.TAG_LOOKUP


# ── IO_LOOKUP ─────────────────────────────────────────────────────────────────

def test_classify_slot_query():
    assert classify("What is at slot 1:2:0?") == QueryType.IO_LOOKUP


def test_classify_rio_query():
    assert classify("Show me the RIO mapping for rack 2") == QueryType.IO_LOOKUP


def test_classify_srio_query():
    assert classify("Which SRIO modules are on network segment 3?") == QueryType.IO_LOOKUP


def test_classify_module_keyword():
    assert classify("What module is in slot 3?") == QueryType.IO_LOOKUP


# ── ROUTINE_FLOW ──────────────────────────────────────────────────────────────

def test_classify_routine_query():
    assert classify("Explain the logic in the startup routine") == QueryType.ROUTINE_FLOW


def test_classify_ladder_logic():
    assert classify("How does the ladder logic for estop work?") == QueryType.ROUTINE_FLOW


# ── COMMISSION_PROGRESS ───────────────────────────────────────────────────────

def test_classify_commissioning_status():
    assert classify("What is the commissioning progress for zone 3?") == QueryType.COMMISSION_PROGRESS


def test_classify_punch_list():
    assert classify("Show me outstanding punch list items") == QueryType.COMMISSION_PROGRESS


# ── SYSTEM_FLOW ───────────────────────────────────────────────────────────────

def test_classify_system_flow():
    assert classify("Explain the system startup sequence") == QueryType.SYSTEM_FLOW


def test_classify_safety_system():
    assert classify("How does the safety interlock work?") == QueryType.SYSTEM_FLOW


# ── DOCUMENTATION ─────────────────────────────────────────────────────────────

def test_classify_general_what_question():
    assert classify("What is an add-on instruction?") == QueryType.DOCUMENTATION


def test_classify_explain():
    assert classify("Explain how the drive is configured") == QueryType.DOCUMENTATION


# ── IO takes priority over tag (slot keyword wins) ────────────────────────────

def test_io_wins_over_tag_when_slot_present():
    # "slot" keyword → IO_LOOKUP even if there's also a tag-like token
    result = classify("What tag is at slot 1:3:0 for CONV_RUN?")
    assert result == QueryType.IO_LOOKUP


# ── extract_tag_tokens ────────────────────────────────────────────────────────

def test_extract_tag_tokens_finds_uppercase():
    tokens = extract_tag_tokens("Tag CONV_RUN is also linked to PUMP_SPD.")
    assert "CONV_RUN" in tokens
    assert "PUMP_SPD" in tokens


def test_extract_tag_tokens_filters_stopwords():
    tokens = extract_tag_tokens("WHAT DOES THIS TAG DO?")
    assert "WHAT" not in tokens
    assert "DOES" not in tokens
    assert "THIS" not in tokens
    assert "TAG" not in tokens


def test_extract_tag_tokens_empty():
    assert extract_tag_tokens("") == []
    assert extract_tag_tokens("How are you?") == []
